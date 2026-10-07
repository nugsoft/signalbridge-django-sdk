"""
SignalBridge API Client
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import segments, webhooks
from .channels import MobileMoneyChannel, SmsChannel, UssdChannel, WhatsAppChannel
from .exceptions import (
    InsufficientBalanceException,
    InsufficientPermissionsException,
    NoClientException,
    RateLimitedException,
    ServiceUnavailableException,
    SignalBridgeException,
    UnauthorizedException,
    ValidationException,
)

logger = logging.getLogger(__name__)

#: The production gateway. Override with SIGNALBRIDGE_URL in settings.
DEFAULT_BASE_URL = 'https://signal-bridge.nugsoftapps.net/api'

#: Methods that may be retried automatically.
#:
#: POST is deliberately absent. The gateway charges a message the moment it
#: accepts one, so a retried POST can send the same SMS twice and bill for both.
#: urllib3 retries on connection and read errors as well as on the statuses
#: below, and a read timeout says nothing about whether the gateway processed
#: the request — which is exactly when a retry is most dangerous.
SAFE_RETRY_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


class SignalBridgeClient:
    """Django client for SignalBridge SMS Gateway"""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30
    ):
        self.token = token or getattr(settings, 'SIGNALBRIDGE_TOKEN', None)
        self.base_url = (
            base_url or
            getattr(settings, 'SIGNALBRIDGE_URL', DEFAULT_BASE_URL)
        ).rstrip('/')
        self.timeout = timeout

        if not self.token:
            raise SignalBridgeException("SIGNALBRIDGE_TOKEN is missing from settings")

        self.session = self._create_session()

        self.sms = SmsChannel(self)
        self.whatsapp = WhatsAppChannel(self)
        self.mobile_money = MobileMoneyChannel(self)
        self.ussd = UssdChannel(self)

    # -----------------------------
    # SMS (proxies to the channel)
    # -----------------------------

    def send_sms(
        self,
        recipient: str,
        message: str,
        metadata: Optional[Dict] = None,
        is_test: bool = False,
        sender_id: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        return self.sms.send(
            recipient=recipient,
            message=message,
            metadata=metadata,
            is_test=is_test,
            sender_id=sender_id,
            scheduled_at=scheduled_at,
        )

    def send_batch(
        self,
        messages: List[Dict],
        is_test: bool = False,
        sender_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.sms.send_batch(messages, is_test=is_test, sender_id=sender_id)

    def get_message_status(self, message_id: int, refresh: bool = False) -> Dict[str, Any]:
        return self.sms.status(message_id, refresh=refresh)

    def get_messages(self, **filters) -> Dict[str, Any]:
        return self.sms.messages(**filters)

    # -----------------------------
    # Balance
    # -----------------------------

    def get_balance(self, currency: str = 'UGX') -> Dict[str, Any]:
        currency = currency.upper()

        # Scoped by token as well as currency: one process may hold clients for
        # more than one account, and they must not read each other's balance.
        cache_key = "sb_balance_{}_{}".format(self._token_fingerprint(), currency)

        cached = cache.get(cache_key)

        if cached:
            return cached

        data = self._make_request('GET', '/balance', params={'currency': currency})
        cache.set(cache_key, data, 60)

        return data

    def get_balance_summary(self) -> Dict[str, Any]:
        return self._make_request('GET', '/balance/summary')

    def get_transactions(
        self,
        per_page: int = 15,
        page: int = 1,
        transaction_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {'per_page': per_page, 'page': page}

        if transaction_type:
            params['type'] = transaction_type
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        return self._make_request('GET', '/balance/transactions', params=params)

    def request_credit(
        self,
        amount: float,
        currency: str = 'UGX',
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ask the administrators for a top-up. This does not move money."""
        payload: Dict[str, Any] = {'amount': amount, 'currency': currency.upper()}

        if description:
            payload['description'] = description

        return self._make_request('POST', '/balance/add-credit', json=payload)

    # -----------------------------
    # Tokens
    # -----------------------------

    def get_tokens(self) -> Dict[str, Any]:
        return self._make_request('GET', '/tokens')

    def revoke_current_token(self) -> Dict[str, Any]:
        return self._make_request('DELETE', '/tokens/current')

    # -----------------------------
    # Webhooks
    # -----------------------------

    def list_webhooks(self) -> Dict[str, Any]:
        return self._make_request('GET', '/webhooks')

    def create_webhook(
        self,
        url: str,
        events: Optional[List[str]] = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """The signing secret is returned once, in this response only."""
        return self._make_request('POST', '/webhooks', json={
            'url': url,
            'events': events or ['*'],
            'is_active': is_active,
        })

    def get_webhook(self, webhook_id: int) -> Dict[str, Any]:
        return self._make_request('GET', '/webhooks/{}'.format(webhook_id))

    def update_webhook(self, webhook_id: int, **data) -> Dict[str, Any]:
        return self._make_request('PUT', '/webhooks/{}'.format(webhook_id), json=data)

    def delete_webhook(self, webhook_id: int) -> Dict[str, Any]:
        return self._make_request('DELETE', '/webhooks/{}'.format(webhook_id))

    def regenerate_webhook_secret(self, webhook_id: int) -> Dict[str, Any]:
        return self._make_request(
            'POST', '/webhooks/{}/regenerate-secret'.format(webhook_id)
        )

    def verify_webhook_signature(self, request, secret: str) -> bool:
        """
        Verify an inbound webhook from a Django request.

        Reads request.body — the raw bytes — because the signature covers those,
        not a re-encoded copy of the parsed payload.
        """
        return webhooks.verify_request(request, secret)

    # -----------------------------
    # Exports
    # -----------------------------

    def export_messages(self, **filters) -> str:
        """Message history as raw CSV."""
        return self._make_request(
            'GET', '/export/messages', params=filters, timeout=120, raw=True
        )

    def export_transactions(self, **filters) -> str:
        """Transaction history as raw CSV."""
        return self._make_request(
            'GET', '/export/transactions', params=filters, timeout=120, raw=True
        )

    # -----------------------------
    # Estimation Helpers
    # -----------------------------

    def calculate_segments(self, message: str) -> int:
        """
        Segments a message will be split into.

        Delegates to the segments module so this and the gateway cannot
        disagree — see signalbridge/segments.py.
        """
        return segments.count(message)

    def estimate_cost(self, message: str, segment_price: float) -> float:
        return segments.estimate_cost(message, segment_price)

    # -----------------------------
    # Core Request Handling
    # -----------------------------

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json=None,
        params=None,
        timeout=None,
        raw: bool = False,
        binary: bool = False,
    ):
        url = "{}{}".format(self.base_url, endpoint if endpoint.startswith('/') else '/' + endpoint)
        timeout = timeout or self.timeout

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=json,
                params=params,
                timeout=timeout
            )

            if response.status_code >= 400:
                self._handle_error(response)

            if binary:
                # Files (a customer's photo or PDF) must not be decoded as text.
                return response.content

            return response.text if raw else self._safe_json(response)

        except requests.exceptions.RequestException as exc:
            logger.exception("SignalBridge API request failed")
            raise SignalBridgeException(str(exc))

    def _token_fingerprint(self) -> str:
        """A short, non-reversible tag for cache keys."""
        import hashlib

        return hashlib.sha256(self.token.encode('utf-8')).hexdigest()[:12]

    def _safe_json(self, response):
        try:
            return response.json()
        except ValueError:
            return {
                "success": False,
                "status_code": response.status_code,
                "raw_response": response.text
            }

    def _handle_error(self, response):
        try:
            data = response.json()
        except ValueError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        status = response.status_code
        message = data.get("message", "SignalBridge API error")

        logger.error(
            "SignalBridge API Error [%s]: %s",
            status,
            message,
            extra={"data": data}
        )

        if status == 401:
            raise UnauthorizedException(message)
        elif status == 402:
            raise InsufficientBalanceException(message, data.get('data'))
        elif status == 403:
            # The gateway returns 403 both for a token missing an ability and
            # for a user with no client at all. The message distinguishes them.
            lowered = message.lower()

            if 'permission' in lowered or 'role' in lowered or data.get('required_ability'):
                raise InsufficientPermissionsException(message, data)

            raise NoClientException(message)
        elif status == 404:
            # A JSON 404 is SignalBridge answering — usually a message or
            # webhook that does not exist. Only a 404 that did not come from
            # the gateway (no JSON message) points at a wrong base URL.
            raise SignalBridgeException(
                message if "message" in data
                else "API endpoint not found. Verify SIGNALBRIDGE_URL — it must include /api.",
                status,
                data,
            )
        elif status == 422:
            raise ValidationException(message, data.get('errors'), data)
        elif status == 429:
            raise RateLimitedException(message)
        elif status == 503:
            raise ServiceUnavailableException(message)
        else:
            raise SignalBridgeException(message, status, data)

    # -----------------------------
    # Session + Retry
    # -----------------------------

    def _create_session(self):
        session = requests.Session()

        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            # Reads only. See SAFE_RETRY_METHODS: retrying a send can bill and
            # deliver the same message twice.
            allowed_methods=SAFE_RETRY_METHODS,
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update({
            'Authorization': 'Bearer {}'.format(self.token),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

        return session


# -----------------------------
# Singleton Instance
# -----------------------------
_client_instance = None


def get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = SignalBridgeClient()
    return _client_instance


def reset_client():
    """Drop the cached client — useful in tests and after changing settings."""
    global _client_instance
    _client_instance = None
