"""
Client tests. Every request is faked: a test that reached the real gateway
would send a real SMS and bill the account.
"""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from signalbridge.client import SAFE_RETRY_METHODS, SANDBOX_URL, SignalBridgeClient
from signalbridge.sandbox import MagicNumbers
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

    def test_a_file_is_sent_on_its_own(self):
        calls = self.fake_request(FakeResponse(payload={}))

        self.client.whatsapp.send_media(
            '256700000000', 'document', 'https://files.example.com/report.pdf',
            caption='Term 2 report', filename='report.pdf',
        )

        self.assertEqual(calls[0]['url'], 'https://gateway.test/api/whatsapp/send')
        self.assertEqual(calls[0]['json']['media'], {
            'type': 'document', 'url': 'https://files.example.com/report.pdf', 'caption': 'Term 2 report', 'filename': 'report.pdf',
        })
        self.assertNotIn('message', calls[0]['json'])

    def test_a_file_of_an_unknown_type_or_on_plain_http_is_refused_before_sending(self):
        calls = self.fake_request(FakeResponse(payload={}))

        for media_type, url in (('gif', 'https://example.com/a.gif'), ('image', 'http://example.com/a.jpg')):
            with self.assertRaises(ValidationException):
                self.client.whatsapp.send_media('256700000000', media_type, url)

        self.assertEqual(calls, [])

    def test_reply_buttons_are_sent_with_their_ids_and_a_text_header(self):
        calls = self.fake_request(FakeResponse(payload={}))

        self.client.whatsapp.send_buttons(
            '256700000000', 'Can you make it?',
            {'confirm_4821': 'Confirm', 'reschedule_4821': 'Reschedule'},
            header='Tomorrow, 10:00', footer='Acme Clinic',
        )

        self.assertEqual(calls[0]['json']['interactive'], {
            'type': 'buttons',
            'body': 'Can you make it?',
            'buttons': [{'id': 'confirm_4821', 'title': 'Confirm'}, {'id': 'reschedule_4821', 'title': 'Reschedule'}],
            'header': {'type': 'text', 'text': 'Tomorrow, 10:00'},
            'footer': 'Acme Clinic',
        })

    def test_more_than_three_buttons_are_refused_before_sending(self):
        calls = self.fake_request(FakeResponse(payload={}))

        with self.assertRaisesRegex(ValidationException, 'send_list'):
            self.client.whatsapp.send_buttons('256700000000', 'Pick', {'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D'})

        self.assertEqual(calls, [])

    def test_a_list_and_a_link_button_are_sent_as_interactive_messages(self):
        calls = self.fake_request(FakeResponse(payload={}), FakeResponse(payload={}))

        self.client.whatsapp.send_list('256700000000', 'Which branch?', 'Choose a branch', [
            {'title': 'Kampala', 'rows': [{'id': 'kla_central', 'title': 'Central', 'description': 'Open until 8pm'}]},
        ])
        self.client.whatsapp.send_link_button('256700000000', 'Your invoice is ready.', 'Pay now', 'https://pay.example.com/inv/42')

        self.assertEqual(calls[0]['json']['interactive']['type'], 'list')
        self.assertEqual(calls[0]['json']['interactive']['button'], 'Choose a branch')
        self.assertEqual(calls[0]['json']['interactive']['sections'][0]['rows'][0]['id'], 'kla_central')
        self.assertEqual(calls[1]['json']['interactive'], {
            'type': 'cta_url', 'body': 'Your invoice is ready.', 'button': 'Pay now', 'url': 'https://pay.example.com/inv/42',
        })

    def test_a_list_of_more_than_ten_options_is_refused_before_sending(self):
        self.fake_request(FakeResponse(payload={}))

        with self.assertRaises(ValidationException):
            self.client.whatsapp.send_list('256700000000', 'Pick', 'Open', [
                {'title': 'All', 'rows': [{'id': 'r{}'.format(i), 'title': 'R{}'.format(i)} for i in range(11)]},
            ])

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

    MOBILE_MONEY_REFERENCE = '0b6f2c1e-7d3a-4a5b-9c8d-1e2f3a4b5c6d'

    def mobile_money_transaction(self, **overrides):
        return {
            'reference': self.MOBILE_MONEY_REFERENCE,
            'direction': 'collection',
            'status': 'pending',
            'status_message': 'Request is being processed',
            'phone': '256700000000',
            'amount': '5000.00',
            'currency': 'UGX',
            **overrides,
        }

    def test_mobile_money_sends_only_what_the_gateway_reads_and_returns_its_reference(self):
        calls = self.fake_request(FakeResponse(202, {'success': True, 'data': self.mobile_money_transaction()}))

        tx = self.client.mobile_money.initiate('256700000000', 5000, 'ugx', note='Invoice')

        self.assertEqual(tx['data']['reference'], self.MOBILE_MONEY_REFERENCE)
        self.assertEqual(calls[0]['json'], {
            'phone': '256700000000',
            'amount': 5000,
            'currency': 'UGX',
            'note': 'Invoice',
        })

    def test_mobile_money_takes_no_reference_of_your_own(self):
        calls = self.fake_request(FakeResponse(payload={}))

        with self.assertRaises(TypeError):
            self.client.mobile_money.initiate('256700000000', 5000, reference='INV-1')

        self.assertEqual(calls, [])

    def test_mobile_money_refuses_a_note_longer_than_the_gateway_takes(self):
        calls = self.fake_request(FakeResponse(payload={}))

        with self.assertRaises(ValidationException):
            self.client.mobile_money.initiate('256700000000', 5000, note='x' * 101)

        self.assertEqual(calls, [])

    def test_mobile_money_switched_off_is_reported_as_unavailable(self):
        self.fake_request(FakeResponse(403, {'success': False, 'message': 'Mobile money collections are not available yet.'}))

        with self.assertRaisesMessage(ServiceUnavailableException, 'Mobile money collections are not available yet.'):
            self.client.mobile_money.initiate('256700000000', 5000)

    def test_mobile_money_without_the_ability_is_still_a_permissions_error(self):
        self.fake_request(FakeResponse(403, {
            'success': False,
            'message': 'This API token does not have permission to perform this action. Required ability: mobile-money:send.',
        }))

        with self.assertRaises(InsufficientPermissionsException):
            self.client.mobile_money.initiate('256700000000', 5000)

    def test_a_refused_payment_says_why_and_keeps_the_transaction(self):
        self.fake_request(FakeResponse(422, {
            'success': False,
            'message': 'The payment request was refused.',
            'data': self.mobile_money_transaction(status='failed', status_message='Amount must be at least 500'),
        }))

        with self.assertRaises(ValidationException) as raised:
            self.client.mobile_money.initiate('256700000000', 100)

        self.assertEqual(str(raised.exception), 'The payment request was refused: Amount must be at least 500')
        self.assertEqual(raised.exception.get_data()['reference'], self.MOBILE_MONEY_REFERENCE)

    def test_mobile_money_is_verified_by_its_reference(self):
        calls = self.fake_request(FakeResponse(payload={'success': True, 'data': self.mobile_money_transaction(status='completed')}))

        result = self.client.mobile_money.verify(self.MOBILE_MONEY_REFERENCE)

        self.assertEqual(result['data']['status'], 'completed')
        self.assertEqual(calls[0]['url'], 'https://gateway.test/api/mobile-money/transactions/' + self.MOBILE_MONEY_REFERENCE)

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


class SandboxTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def fake_request(self, client, *responses):
        calls = []

        def handler(method, url, json=None, params=None, timeout=None):
            calls.append({'method': method, 'url': url, 'json': json})
            return responses[len(calls) - 1] if len(calls) <= len(responses) else responses[-1]

        patcher = patch.object(client.session, 'request', side_effect=handler)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def test_the_sandbox_setting_points_the_client_at_the_sandbox(self):
        with self.settings(SIGNALBRIDGE_SANDBOX=True, SIGNALBRIDGE_URL=None):
            client = SignalBridgeClient(token='sandbox-token')

        self.assertEqual(client.base_url, SANDBOX_URL)
        self.assertTrue(client.is_sandbox)
        self.assertFalse(SignalBridgeClient(token='live-token').is_sandbox)

    def test_an_explicit_url_wins_over_the_sandbox_setting(self):
        with self.settings(SIGNALBRIDGE_SANDBOX=True, SIGNALBRIDGE_URL='https://gateway.test/api'):
            client = SignalBridgeClient(token='t')

        self.assertEqual(client.base_url, 'https://gateway.test/api')

    def test_the_sandbox_tools_hit_their_routes(self):
        client = SignalBridgeClient(token='sandbox-token', base_url=SANDBOX_URL)
        calls = self.fake_request(client, FakeResponse(payload={}))
        tools = client.sandbox_tools

        tools.magic_numbers()
        tools.customer_message(MagicNumbers.DELIVERED, type='interactive', reply_to_message_id=42, reply_id='confirm_42')
        tools.set_message_status(42, 'read')
        tools.add_credit()

        self.assertEqual([(c['method'], c['url']) for c in calls], [
            ('GET', SANDBOX_URL + '/sandbox'),
            ('POST', SANDBOX_URL + '/sandbox/whatsapp/customer-message'),
            ('POST', SANDBOX_URL + '/sandbox/messages/42/status'),
            ('POST', SANDBOX_URL + '/sandbox/credit'),
        ])
        self.assertEqual(calls[1]['json'], {'from': '256700000001', 'type': 'interactive', 'reply_to_message_id': 42, 'reply_id': 'confirm_42'})
        self.assertEqual(calls[2]['json'], {'status': 'read'})

    def test_the_sandbox_tools_on_live_say_where_they_live(self):
        client = SignalBridgeClient(token='live-token')
        self.fake_request(client, FakeResponse(status_code=404, payload={'message': 'Not Found'}))

        with self.assertRaisesRegex(SignalBridgeException, 'only in the sandbox'):
            client.sandbox_tools.add_credit()

    def test_a_message_that_is_not_yours_is_still_reported_as_such(self):
        client = SignalBridgeClient(token='sandbox-token', base_url=SANDBOX_URL)
        self.fake_request(client, FakeResponse(status_code=404, payload={'success': False, 'message': 'Message not found.'}))

        with self.assertRaisesRegex(SignalBridgeException, 'Message not found.'):
            client.sandbox_tools.set_message_status(99, 'delivered')

    def test_an_unknown_status_is_refused_before_sending(self):
        client = SignalBridgeClient(token='sandbox-token', base_url=SANDBOX_URL)
        calls = self.fake_request(client, FakeResponse(payload={}))

        with self.assertRaises(ValidationException):
            client.sandbox_tools.set_message_status(1, 'lost')

        self.assertEqual(calls, [])
