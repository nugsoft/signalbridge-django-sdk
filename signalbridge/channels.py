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

        :param is_test: A label only — the message is still sent and charged
        :param sender_id: Deprecated and ignored. The gateway sends every
            message as NUGSOFT, the only sender ID registered with its vendors
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

        :param is_test: A label only — the messages are still sent and charged
        :param sender_id: Deprecated and ignored; see send()
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
    """
    WhatsApp through SignalBridge.

    WhatsApp only lets a business start a conversation with a template it has
    approved, so the flow is: create_template() once, wait for the
    template.approved webhook, then send_template() as often as needed. Free
    text (send()) and Flows (send_flow()) are delivered only within 24 hours
    of the person's last message. SignalBridge holds every WhatsApp
    credential and handles Flow encryption — nothing here needs Meta access.
    """

    # -- Sending ---------------------------------------------------------

    def send(
        self,
        recipient: str,
        message: str,
        metadata: Optional[Dict] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send free text. WhatsApp delivers it only within 24 hours of the
        person's last message; to start a conversation use send_template().
        """
        self._require_recipient(recipient)

        if not message or not message.strip():
            raise ValidationException("Message is required")

        if len(message) > 4096:
            raise ValidationException("WhatsApp message exceeds maximum length of 4096 characters")

        return self._request('POST', '/whatsapp/send', json={
            'recipient': recipient,
            'message': message,
            **self._common(metadata, scheduled_at),
        })

    def send_template(
        self,
        recipient: str,
        template_name: str,
        variables: Optional[List[str]] = None,
        language: Optional[str] = None,
        header: Optional[Dict] = None,
        flow: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send one of your approved templates.

        :param variables: Values for {{1}}, {{2}}, ... in order (the code, for
            an authentication template)
        :param header: For a template that starts with a file:
            {"type": "document"|"image"|"video", "url": ..., "filename": ...}
        :param flow: For a template with a Flow button: {"data": {...}}
        """
        self._require_recipient(recipient)

        if not template_name or not template_name.strip():
            raise ValidationException("Template name is required")

        variables = list(variables or [])

        if any(isinstance(value, (dict, list)) for value in variables):
            raise ValidationException(
                "send_template() takes the variables as a plain list, e.g. ['John', 'UGX 50,000']. "
                "The Meta \"components\" structure is built by SignalBridge."
            )

        payload = {
            'recipient': recipient,
            'template': template_name,
            'variables': [str(value) for value in variables],
            **self._common(metadata, scheduled_at),
        }

        for key, value in (('language', language), ('header', header), ('flow', flow)):
            if value is not None:
                payload[key] = value

        return self._request('POST', '/whatsapp/send', json=payload)

    def send_flow(
        self,
        recipient: str,
        flow_name: str,
        body: str,
        button: str,
        header: Optional[str] = None,
        footer: Optional[str] = None,
        screen: Optional[str] = None,
        data: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send one of your published Flows as an interactive message (within 24
        hours of the person's last message). The answers arrive as a
        flow.completed webhook.

        :param screen: Open on this screen; left out, your data endpoint is asked
        """
        self._require_recipient(recipient)

        flow = {'name': flow_name, 'body': body, 'button': button}

        for key, value in (('header', header), ('footer', footer), ('screen', screen), ('data', data)):
            if value is not None:
                flow[key] = value

        return self._request('POST', '/whatsapp/send', json={
            'recipient': recipient,
            'flow': flow,
            **self._common(metadata, scheduled_at),
        })

    # -- Templates -------------------------------------------------------

    def list_templates(self, status: Optional[str] = None) -> Dict[str, Any]:
        """:param status: pending, approved, rejected, paused or disabled"""
        return self._request('GET', '/whatsapp/templates', params={'status': status} if status else None)

    def get_template(self, template_id: int, refresh: bool = False) -> Dict[str, Any]:
        """:param refresh: Ask WhatsApp for the latest review status"""
        return self._request('GET', '/whatsapp/templates/{}'.format(template_id), params={'refresh': 1} if refresh else None)

    def create_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a template for WhatsApp's review: name, category
        (utility|marketing|authentication), language, body, examples, header,
        footer, buttons — or, for authentication, code_expiration_minutes.
        """
        return self._request('POST', '/whatsapp/templates', json=template)

    def delete_template(self, template_id: int) -> Dict[str, Any]:
        return self._request('DELETE', '/whatsapp/templates/{}'.format(template_id))

    # -- Flows -----------------------------------------------------------

    def list_flows(self) -> Dict[str, Any]:
        return self._request('GET', '/whatsapp/flows')

    def get_flow(self, flow_id: int, refresh: bool = False) -> Dict[str, Any]:
        return self._request('GET', '/whatsapp/flows/{}'.format(flow_id), params={'refresh': 1} if refresh else None)

    def create_flow(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a Flow as a draft from its JSON (name, categories, flow_json,
        endpoint_url). Give endpoint_url if it fetches live data: SignalBridge
        forwards those calls there as plain JSON, signed with the
        endpoint_secret in the response (shown once).
        """
        return self._request('POST', '/whatsapp/flows', json=flow)

    def update_flow(self, flow_id: int, changes: Dict[str, Any]) -> Dict[str, Any]:
        """:param changes: flow_json (drafts only), endpoint_url"""
        return self._request('PUT', '/whatsapp/flows/{}'.format(flow_id), json=changes)

    def publish_flow(self, flow_id: int) -> Dict[str, Any]:
        return self._request('POST', '/whatsapp/flows/{}/publish'.format(flow_id))

    def regenerate_flow_secret(self, flow_id: int) -> Dict[str, Any]:
        return self._request('POST', '/whatsapp/flows/{}/regenerate-secret'.format(flow_id))

    def delete_flow(self, flow_id: int) -> Dict[str, Any]:
        """Delete a draft, or retire a published Flow."""
        return self._request('DELETE', '/whatsapp/flows/{}'.format(flow_id))

    # -- Received messages -----------------------------------------------

    def received(self, **filters) -> Dict[str, Any]:
        """Messages customers sent you, newest first. Filters: from, type, since, per_page, page."""
        return self._request('GET', '/whatsapp/received', params=filters or None)

    def get_received(self, message_id: int) -> Dict[str, Any]:
        return self._request('GET', '/whatsapp/received/{}'.format(message_id))

    def download_media(self, message_id: int) -> bytes:
        """The file a customer sent (photo, document, voice note, video), as bytes."""
        return self._request('GET', '/whatsapp/received/{}/media'.format(message_id), timeout=120, binary=True)

    # -- Plumbing --------------------------------------------------------

    @staticmethod
    def _require_recipient(recipient: str) -> None:
        if not recipient or not recipient.strip():
            raise ValidationException("Recipient is required")

    @staticmethod
    def _common(metadata: Optional[Dict], scheduled_at: Optional[datetime]) -> Dict[str, Any]:
        common = {}

        if metadata is not None:
            common['metadata'] = metadata

        if scheduled_at is not None:
            common['scheduled_at'] = scheduled_at.isoformat() if hasattr(scheduled_at, 'isoformat') else scheduled_at

        return common


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
