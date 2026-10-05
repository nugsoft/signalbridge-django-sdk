"""
Channel clients, mirroring the Laravel and PHP SDKs.

Each channel is a thin wrapper over the transport on ``SignalBridgeClient``:
``client.sms``, ``client.whatsapp``, ``client.mobile_money`` and ``client.ussd``.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from . import segments
from .exceptions import ServiceUnavailableException, ValidationException


class BaseChannel:
    """Shares the transport with the client that created it."""

    def __init__(self, client):
        self._client = client

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        return self._client._make_request(method, endpoint, **kwargs)


class SmsChannel(BaseChannel):
    def send(
        self,
        recipient: str,
        message: str,
        metadata: Optional[Dict] = None,
        is_test: bool = False,
        sender_id: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send a single SMS message.

        :param scheduled_at: Send at this time instead of now (must be future)
        """
        if not recipient or not recipient.strip():
            raise ValidationException("Recipient is required")

        if not message or not message.strip():
            raise ValidationException("Message is required")

        if len(message) > 1000:
            raise ValidationException("Message exceeds maximum length of 1000 characters")

        payload: Dict[str, Any] = {
            'recipient': recipient,
            'message': message,
            'metadata': metadata or {},
            'is_test': is_test,
        }

        if sender_id:
            payload['sender_id'] = sender_id

        if scheduled_at:
            payload['scheduled_at'] = (
                scheduled_at.isoformat() if hasattr(scheduled_at, 'isoformat') else scheduled_at
            )

        return self._request('POST', '/sms/send', json=payload)

    def send_batch(
        self,
        messages: List[Dict],
        is_test: bool = False,
        sender_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send up to 100 messages in one request.

        Each entry needs 'recipient' and 'message'; 'metadata' and
        'scheduled_at' are optional per message.
        """
        if not isinstance(messages, list) or not messages:
            raise ValidationException("Messages must be a non-empty list")

        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValidationException("Message at index {} must be a dict".format(index))

            if not message.get('recipient'):
                raise ValidationException("Message at index {} is missing 'recipient'".format(index))

            if not message.get('message'):
                raise ValidationException("Message at index {} is missing 'message'".format(index))

        payload: Dict[str, Any] = {'messages': messages, 'is_test': is_test}

        if sender_id:
            payload['sender_id'] = sender_id

        # A batch takes longer than a single send. It is still never retried
        # automatically: the gateway charges each message when it accepts it.
        return self._request('POST', '/sms/send-batch', json=payload, timeout=60)

    def status(self, message_id: int, refresh: bool = False) -> Dict[str, Any]:
        """
        One message's delivery status.

        :param refresh: Ask the vendor live rather than returning the stored
            status. Rate limited, and rarely needed — the gateway polls vendors
            in the background.
        """
        params = {'refresh': 1} if refresh else None

        return self._request('GET', '/sms/messages/{}'.format(message_id), params=params)

    def messages(self, **filters) -> Dict[str, Any]:
        """
        List messages with their delivery status.

        Pass ``ids`` to follow up a batch — the ids come back from
        ``send_batch()``. The 'summary' key counts the whole filtered set, not
        just the current page, so one call answers "how did that batch go".
        """
        ids = filters.get('ids')

        if isinstance(ids, (list, tuple)):
            filters['ids'] = ','.join(str(value) for value in ids)

        return self._request('GET', '/sms/messages', params=filters)

    def calculate_segments(self, message: str) -> int:
        return segments.count(message)

    def estimate_cost(self, message: str, segment_price: float) -> float:
        return segments.estimate_cost(message, segment_price)


class WhatsAppChannel(BaseChannel):
    def send(
        self,
        recipient: str,
        message: str,
        metadata: Optional[Dict] = None,
        is_test: bool = False,
    ) -> Dict[str, Any]:
        """Send a plain-text WhatsApp message."""
        if not recipient or not recipient.strip():
            raise ValidationException("Recipient is required")

        if not message or not message.strip():
            raise ValidationException("Message is required")

        if len(message) > 4096:
            raise ValidationException("WhatsApp message exceeds maximum length of 4096 characters")

        return self._request('POST', '/whatsapp/send', json={
            'recipient': recipient,
            'message': message,
            'metadata': metadata or {},
            'is_test': is_test,
        })

    def send_template(
        self,
        recipient: str,
        template_name: str,
        components: Optional[List[Dict]] = None,
        language: str = 'en_US',
        metadata: Optional[Dict] = None,
        is_test: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp template message (pre-approved by Meta).

        Required for starting a conversation outside the 24-hour window.
        """
        if not recipient or not recipient.strip():
            raise ValidationException("Recipient is required")

        if not template_name or not template_name.strip():
            raise ValidationException("Template name is required")

        return self._request('POST', '/whatsapp/send', json={
            'recipient': recipient,
            'template': template_name,
            'components': components or [],
            'language': language,
            'metadata': metadata or {},
            'is_test': is_test,
        })


class MobileMoneyChannel(BaseChannel):
    def initiate(
        self,
        phone: str,
        amount: float,
        currency: str = 'UGX',
        reference: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate a collection (request-to-pay). The subscriber approves on their
        handset; the result arrives by webhook or through ``verify()``.
        """
        if not phone or not phone.strip():
            raise ValidationException("Phone number is required")

        if amount <= 0:
            raise ValidationException("Amount must be greater than zero")

        payload: Dict[str, Any] = {
            'phone': phone,
            'amount': amount,
            'currency': currency.upper(),
        }

        if reference:
            payload['reference'] = reference

        # 'note' is the text shown to the payer, and the only descriptive field
        # the gateway reads.
        if note:
            payload['note'] = note

        return self._request('POST', '/mobile-money/initiate', json=payload)

    def verify(self, transaction_id: str) -> Dict[str, Any]:
        """Poll the status of a transaction returned by ``initiate()``."""
        if not transaction_id or not transaction_id.strip():
            raise ValidationException("Transaction ID is required")

        return self._request('GET', '/mobile-money/transactions/{}'.format(transaction_id))

    def disburse(self, phone: str, amount: float, currency: str = 'UGX', **options) -> Dict[str, Any]:
        """
        Send money to a subscriber's wallet.

        Not available yet: the gateway exposes no disbursement endpoint. Calling
        through would 404, which reads as a bad base URL and sends you looking
        in the wrong place.
        """
        raise ServiceUnavailableException(
            "Mobile money disbursement is not available yet: the SignalBridge API does not "
            "expose /mobile-money/disburse. Use initiate() to collect payments. Contact the "
            "SignalBridge team if you need payouts enabled."
        )


class UssdChannel(BaseChannel):
    """
    USSD support is planned. The endpoints below reflect the intended contract;
    the gateway's USSD routes are not active yet, so calls come back as errors.
    """

    def push(
        self,
        phone: str,
        service_code: str,
        message: str,
        reference: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if not phone or not phone.strip():
            raise ValidationException("Subscriber phone number is required")

        if not service_code or not service_code.strip():
            raise ValidationException("USSD service code is required")

        if not message or not message.strip():
            raise ValidationException("Message is required")

        if len(message) > 182:
            raise ValidationException("USSD message exceeds maximum length of 182 characters")

        return self._request('POST', '/ussd/push', json={
            'phone': phone,
            'service_code': service_code,
            'message': message,
            'reference': reference,
            'metadata': metadata or {},
        })

    def session(self, session_id: str) -> Dict[str, Any]:
        if not session_id or not session_id.strip():
            raise ValidationException("Session ID is required")

        return self._request('GET', '/ussd/sessions/{}'.format(session_id))

    def respond(self, session_id: str, message: str, end_session: bool = False) -> Dict[str, Any]:
        if not session_id or not session_id.strip():
            raise ValidationException("Session ID is required")

        if not message or not message.strip():
            raise ValidationException("Response message is required")

        if len(message) > 182:
            raise ValidationException("USSD response exceeds maximum length of 182 characters")

        return self._request('POST', '/ussd/sessions/{}/respond'.format(session_id), json={
            'message': message,
            'end_session': end_session,
        })
