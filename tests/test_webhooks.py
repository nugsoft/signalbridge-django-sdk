"""Webhook signature verification."""

from django.test import SimpleTestCase

from signalbridge import webhooks

SECRET = 'webhook-signing-secret'


class FakeRequest:
    def __init__(self, body, signature=None):
        self.body = body.encode('utf-8') if isinstance(body, str) else body
        self.META = {}
        self.headers = {}

        if signature is not None:
            self.META[webhooks.META_KEY] = signature


class WebhookSignatureTests(SimpleTestCase):
    def test_a_correctly_signed_payload_is_accepted(self):
        payload = '{"event":"message.delivered","message_id":42}'

        self.assertTrue(webhooks.verify(payload, webhooks.sign(payload, SECRET), SECRET))

    def test_a_bare_hex_digest_is_accepted(self):
        payload = '{"event":"message.sent"}'
        signed = webhooks.sign(payload, SECRET).removeprefix('sha256=')

        self.assertTrue(webhooks.verify(payload, signed, SECRET))

    def test_a_tampered_payload_fails(self):
        signature = webhooks.sign('{"message_id":42}', SECRET)

        self.assertFalse(webhooks.verify('{"message_id":43}', signature, SECRET))

    def test_the_wrong_secret_fails(self):
        payload = '{"event":"message.sent"}'

        self.assertFalse(webhooks.verify(payload, webhooks.sign(payload, 'other'), SECRET))

    def test_a_missing_signature_or_secret_fails(self):
        payload = '{"event":"message.sent"}'

        self.assertFalse(webhooks.verify(payload, None, SECRET))
        self.assertFalse(webhooks.verify(payload, '', SECRET))
        self.assertFalse(webhooks.verify(payload, webhooks.sign(payload, SECRET), ''))

    def test_a_django_request_is_verified_against_its_raw_body(self):
        payload = '{"event":"message.delivered","message_id":42}'
        request = FakeRequest(payload, webhooks.sign(payload, SECRET))

        self.assertTrue(webhooks.verify_request(request, SECRET))

    def test_a_django_request_without_a_signature_fails(self):
        request = FakeRequest('{"event":"message.sent"}')

        self.assertFalse(webhooks.verify_request(request, SECRET))

    def test_bytes_and_strings_verify_the_same(self):
        payload = '{"event":"message.sent"}'
        signature = webhooks.sign(payload, SECRET)

        self.assertTrue(webhooks.verify(payload.encode('utf-8'), signature, SECRET))
