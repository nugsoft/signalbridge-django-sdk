"""
Client tests. Every request is faked: a test that reached the real gateway
would send a real SMS and bill the account.
"""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from signalbridge.client import SAFE_RETRY_METHODS, SignalBridgeClient
from signalbridge.exceptions import (
    InsufficientBalanceException,
    InsufficientPermissionsException,
    NoClientException,
    RateLimitedException,
    ServiceUnavailableException,
    SignalBridgeException,
    UnauthorizedException,
    ValidationException,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.content = self.text.encode('utf-8')

    def json(self):
        if self._payload is None:
            raise ValueError('no json')

        return self._payload


class ClientTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = SignalBridgeClient(token='test-token', base_url='https://gateway.test/api')

    def fake_request(self, *responses):
        """Patch the session and record the calls made."""
        calls = []

        def handler(method, url, json=None, params=None, timeout=None):
            calls.append({
                'method': method,
                'url': url,
                'json': json,
                'params': params,
                'timeout': timeout,
            })

            return responses[len(calls) - 1] if len(calls) <= len(responses) else responses[-1]

        patcher = patch.object(self.client.session, 'request', side_effect=handler)
        patcher.start()
        self.addCleanup(patcher.stop)

        return calls


class UrlTests(ClientTestCase):
    def test_requests_keep_the_api_prefix(self):
        calls = self.fake_request(FakeResponse(payload={'success': True}))

        self.client.send_sms('256700000000', 'Hello')

        self.assertEqual(calls[0]['url'], 'https://gateway.test/api/sms/send')

    def test_a_trailing_slash_on_the_base_url_is_tolerated(self):
        client = SignalBridgeClient(token='t', base_url='https://gateway.test/api/')

        with patch.object(client.session, 'request', return_value=FakeResponse(payload={})) as request:
            client.get_balance_summary()

        self.assertEqual(request.call_args.kwargs['url'], 'https://gateway.test/api/balance/summary')

    def test_each_endpoint_is_addressed_correctly(self):
        calls = self.fake_request(*[FakeResponse(payload={}) for _ in range(6)])

        self.client.get_message_status(42)
        self.client.get_messages(ids=[1, 2])
        self.client.list_webhooks()
        self.client.export_messages()
        self.client.request_credit(100)
        self.client.revoke_current_token()

        self.assertEqual([call['url'] for call in calls], [
            'https://gateway.test/api/sms/messages/42',
            'https://gateway.test/api/sms/messages',
            'https://gateway.test/api/webhooks',
            'https://gateway.test/api/export/messages',
            'https://gateway.test/api/balance/add-credit',
            'https://gateway.test/api/tokens/current',
        ])


class RetryPolicyTests(SimpleTestCase):
    def test_posts_are_never_retried_automatically(self):
        # The gateway charges a message when it accepts it, so a retried POST
        # can bill and deliver the same SMS twice.
        self.assertNotIn('POST', SAFE_RETRY_METHODS)

        client = SignalBridgeClient(token='t', base_url='https://gateway.test/api')
        adapter = client.session.get_adapter('https://gateway.test/api')

        allowed = adapter.max_retries.allowed_methods

        self.assertNotIn('POST', allowed)
        self.assertIn('GET', allowed)

    def test_reads_are_still_retried(self):
        client = SignalBridgeClient(token='t', base_url='https://gateway.test/api')
        retries = client.session.get_adapter('https://gateway.test/api').max_retries

        self.assertEqual(retries.total, 3)
        self.assertIn(503, retries.status_forcelist)


class SendTests(ClientTestCase):
    def test_a_sender_id_is_sent(self):
        calls = self.fake_request(FakeResponse(payload={'success': True}))

        self.client.send_sms('256700000000', 'Hello', sender_id='NUGSOFT')

        self.assertEqual(calls[0]['json']['sender_id'], 'NUGSOFT')

    def test_no_sender_id_key_when_none_is_given(self):
        calls = self.fake_request(FakeResponse(payload={'success': True}))

        self.client.send_sms('256700000000', 'Hello')

        self.assertNotIn('sender_id', calls[0]['json'])

    def test_a_batch_posts_every_message_with_a_longer_timeout(self):
        calls = self.fake_request(FakeResponse(payload={'success': True}))

        self.client.send_batch([
            {'recipient': '256700000000', 'message': 'One'},
            {'recipient': '256700000001', 'message': 'Two'},
        ], sender_id='NUGSOFT')

        self.assertEqual(len(calls[0]['json']['messages']), 2)
        self.assertEqual(calls[0]['json']['sender_id'], 'NUGSOFT')
        self.assertEqual(calls[0]['timeout'], 60)

    def test_an_empty_recipient_is_refused_before_any_request(self):
        calls = self.fake_request(FakeResponse(payload={}))

        with self.assertRaises(ValidationException):
            self.client.send_sms('  ', 'Hello')

        self.assertEqual(calls, [])

    def test_an_over_long_message_is_refused(self):
        with self.assertRaises(ValidationException):
            self.client.send_sms('256700000000', 'a' * 1001)

    def test_a_batch_entry_without_a_recipient_is_refused(self):
        with self.assertRaises(ValidationException):
            self.client.send_batch([{'message': 'No recipient'}])

    def test_message_ids_are_joined_for_the_listing_filter(self):
        calls = self.fake_request(FakeResponse(payload={}))

        self.client.get_messages(ids=[1, 2, 3])

        self.assertEqual(calls[0]['params']['ids'], '1,2,3')

    def test_a_refresh_is_only_requested_when_asked_for(self):
        calls = self.fake_request(FakeResponse(payload={}), FakeResponse(payload={}))

        self.client.get_message_status(5)
        self.client.get_message_status(5, refresh=True)

        self.assertIsNone(calls[0]['params'])
        self.assertEqual(calls[1]['params'], {'refresh': 1})


class ChannelTests(ClientTestCase):
    def test_whatsapp_sends_text_and_templates(self):
        calls = self.fake_request(FakeResponse(payload={}), FakeResponse(payload={}))

        self.client.whatsapp.send('256700000000', 'Hello')
        self.client.whatsapp.send_template(
            '256700000000', 'fee_reminder', ['John', 'UGX 50,000'],
            header={'type': 'document', 'url': 'https://files.example.com/r.pdf', 'filename': 'r.pdf'},
        )

        self.assertEqual(calls[0]['url'], 'https://gateway.test/api/whatsapp/send')
        self.assertEqual(calls[1]['json']['template'], 'fee_reminder')
        self.assertEqual(calls[1]['json']['variables'], ['John', 'UGX 50,000'])
        self.assertEqual(calls[1]['json']['header']['type'], 'document')
        self.assertNotIn('components', calls[1]['json'])

    def test_the_old_components_structure_is_refused_with_an_explanation(self):
        self.fake_request(FakeResponse(payload={}))

        with self.assertRaisesRegex(ValidationException, 'plain list'):
            self.client.whatsapp.send_template('256700000000', 'order_confirmation', [
                {'type': 'body', 'parameters': [{'type': 'text', 'text': 'John'}]},
            ])

    def test_a_flow_is_sent_as_an_interactive_message(self):
        calls = self.fake_request(FakeResponse(payload={}))

        self.client.whatsapp.send_flow('256700000000', 'spa_booking', 'Book your next session', 'Book now', screen='BOOKING')

        self.assertEqual(calls[0]['json']['flow'], {
            'name': 'spa_booking', 'body': 'Book your next session', 'button': 'Book now', 'screen': 'BOOKING',
        })

    def test_whatsapp_templates_flows_and_received_messages_hit_the_right_routes(self):
        calls = self.fake_request(*([FakeResponse(payload={'success': True})] * 8 + [FakeResponse(text='%PDF-1.4')]))
        whatsapp = self.client.whatsapp

        whatsapp.create_template({'name': 'fee_reminder'})
        whatsapp.list_templates('approved')
        whatsapp.get_template(4, refresh=True)
        whatsapp.delete_template(4)
        whatsapp.create_flow({'name': 'spa_booking'})
        whatsapp.update_flow(3, {'endpoint_url': 'https://spa.example.com/flow'})
        whatsapp.publish_flow(3)
        whatsapp.received(since='2026-10-07')
        media = whatsapp.download_media(7)

        self.assertEqual([(c['method'], c['url'].replace('https://gateway.test/api', ''), c['params']) for c in calls], [
            ('POST', '/whatsapp/templates', None),
            ('GET', '/whatsapp/templates', {'status': 'approved'}),
            ('GET', '/whatsapp/templates/4', {'refresh': 1}),
            ('DELETE', '/whatsapp/templates/4', None),
            ('POST', '/whatsapp/flows', None),
            ('PUT', '/whatsapp/flows/3', None),
            ('POST', '/whatsapp/flows/3/publish', None),
            ('GET', '/whatsapp/received', {'since': '2026-10-07'}),
            ('GET', '/whatsapp/received/7/media', None),
        ])
        self.assertEqual(media, b'%PDF-1.4')

    def test_mobile_money_sends_the_note_the_gateway_reads(self):
        calls = self.fake_request(FakeResponse(payload={}))

        self.client.mobile_money.initiate('256700000000', 5000, 'ugx', reference='INV-1', note='Invoice')

        self.assertEqual(calls[0]['json'], {
            'phone': '256700000000',
            'amount': 5000,
            'currency': 'UGX',
            'reference': 'INV-1',
            'note': 'Invoice',
        })

    def test_disbursement_reports_that_it_is_unavailable(self):
        with self.assertRaises(ServiceUnavailableException):
            self.client.mobile_money.disburse('256700000000', 5000)

    def test_an_over_long_ussd_message_is_refused(self):
        with self.assertRaises(ValidationException):
            self.client.ussd.push('256700000000', '*123#', 'a' * 183)


class ErrorMappingTests(ClientTestCase):
    def assert_raises_for(self, status, payload, expected):
        self.fake_request(FakeResponse(status_code=status, payload=payload))

        with self.assertRaises(expected):
            self.client.send_sms('256700000000', 'Hello')

    def test_unauthorized(self):
        self.assert_raises_for(401, {'message': 'Unauthenticated.'}, UnauthorizedException)

    def test_insufficient_balance_carries_the_figures(self):
        self.fake_request(FakeResponse(status_code=402, payload={
            'message': 'Insufficient balance.',
            'data': {'required_balance': 75, 'current_balance': 10, 'segments': 1},
        }))

        with self.assertRaises(InsufficientBalanceException) as caught:
            self.client.send_sms('256700000000', 'Hello')

        self.assertEqual(caught.exception.required_balance, 75)
        self.assertEqual(caught.exception.current_balance, 10)

    def test_a_missing_ability_is_a_permissions_error(self):
        self.fake_request(FakeResponse(status_code=403, payload={
            'message': 'This API token does not have permission to perform this action.',
            'required_ability': 'sms:send',
        }))

        with self.assertRaises(InsufficientPermissionsException) as caught:
            self.client.send_sms('256700000000', 'Hello')

        self.assertEqual(caught.exception.required_ability, 'sms:send')

    def test_a_missing_resource_reports_what_the_gateway_said(self):
        self.fake_request(FakeResponse(status_code=404, payload={
            'success': False,
            'message': 'Message not found.',
        }))

        with self.assertRaises(SignalBridgeException) as caught:
            self.client.get_message_status(999)

        self.assertIn('Message not found.', str(caught.exception))

    def test_a_404_that_is_not_from_the_gateway_points_at_the_base_url(self):
        self.fake_request(FakeResponse(status_code=404, text='<html>Not Found</html>'))

        with self.assertRaises(SignalBridgeException) as caught:
            self.client.get_message_status(999)

        self.assertIn('Verify SIGNALBRIDGE_URL', str(caught.exception))

    def test_no_client_is_still_its_own_error(self):
        self.assert_raises_for(
            403,
            {'message': 'No client associated with your account.'},
            NoClientException,
        )

    def test_validation_errors_are_readable(self):
        self.fake_request(FakeResponse(status_code=422, payload={
            'message': 'Invalid',
            'errors': {'recipient': ['The recipient must be a valid phone number.']},
        }))

        with self.assertRaises(ValidationException) as caught:
            self.client.send_sms('256700000000', 'Hello')

        self.assertEqual(
            caught.exception.get_first_error(),
            'The recipient must be a valid phone number.',
        )

    def test_rate_limited(self):
        self.assert_raises_for(429, {'message': 'Too many requests.'}, RateLimitedException)

    def test_service_unavailable(self):
        self.assert_raises_for(503, {'message': 'Unavailable'}, ServiceUnavailableException)

    def test_a_404_points_at_the_configured_url(self):
        self.fake_request(FakeResponse(status_code=404, payload={}))

        with self.assertRaises(SignalBridgeException) as caught:
            self.client.send_sms('256700000000', 'Hello')

        self.assertIn('SIGNALBRIDGE_URL', str(caught.exception))

    def test_a_server_error_is_retryable(self):
        self.fake_request(FakeResponse(status_code=500, payload={'message': 'Server error'}))

        with self.assertRaises(SignalBridgeException) as caught:
            self.client.send_sms('256700000000', 'Hello')

        self.assertTrue(caught.exception.is_retryable())


class BalanceCacheTests(ClientTestCase):
    def test_a_balance_is_cached_per_token(self):
        first = SignalBridgeClient(token='token-one', base_url='https://gateway.test/api')
        second = SignalBridgeClient(token='token-two', base_url='https://gateway.test/api')

        with patch.object(first.session, 'request', return_value=FakeResponse(payload={'data': {'balance': 1}})):
            self.assertEqual(first.get_balance()['data']['balance'], 1)

        with patch.object(second.session, 'request', return_value=FakeResponse(payload={'data': {'balance': 2}})) as request:
            self.assertEqual(second.get_balance()['data']['balance'], 2)
            # A different token must not read the first client's cached balance.
            self.assertTrue(request.called)

    def test_a_repeat_read_comes_from_the_cache(self):
        with patch.object(self.client.session, 'request', return_value=FakeResponse(payload={'data': {'balance': 5}})) as request:
            self.client.get_balance('UGX')
            self.client.get_balance('ugx')

            self.assertEqual(request.call_count, 1)


class ConfigTests(SimpleTestCase):
    @override_settings(SIGNALBRIDGE_TOKEN=None)
    def test_a_missing_token_is_refused(self):
        with self.assertRaises(SignalBridgeException):
            SignalBridgeClient(base_url='https://gateway.test/api')

    def test_an_explicit_token_wins_over_the_setting(self):
        client = SignalBridgeClient(token='explicit', base_url='https://gateway.test/api')

        self.assertEqual(client.session.headers['Authorization'], 'Bearer explicit')

    def test_the_default_url_is_the_production_gateway(self):
        from signalbridge.client import DEFAULT_BASE_URL

        self.assertEqual(DEFAULT_BASE_URL, 'https://signal-bridge.nugsoftapps.net/api')
