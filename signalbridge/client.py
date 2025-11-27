"""
SignalBridge API Client
"""

import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime
from django.conf import settings
from django.apps import AppConfig
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import (
    InsufficientBalanceException,
    NoClientException,
    ServiceUnavailableException,
    SignalBridgeException,
    ValidationException,
)

logger = logging.getLogger(__name__)


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
            getattr(settings, 'SIGNALBRIDGE_URL', 'https://signal-bridge.nugsoftstaging.com/api')
        )
        self.timeout = timeout

        if not self.token:
            raise SignalBridgeException("SIGNALBRIDGE_TOKEN is missing from settings")

        self.session = self._create_session()

    # -----------------------------
    # Public API
    # -----------------------------

    def send_sms(self, recipient: str, message: str, metadata: Optional[Dict] = None,
                 is_test: bool = False, scheduled_at: Optional[datetime] = None) -> Dict:

        if not recipient:
            raise ValidationException("Recipient is required")

        if not message:
            raise ValidationException("Message is required")

        payload = {
            'recipient': recipient,
            'message': message,
            'metadata': metadata or {},
            'is_test': is_test,
        }

        if scheduled_at:
            payload['scheduled_at'] = scheduled_at.isoformat()

        return self._make_request('POST', '/sms/send', json=payload)

    def send_batch(self, messages: List[Dict], is_test: bool = False) -> Dict:

        if not isinstance(messages, list) or not messages:
            raise ValidationException("Messages must be a non-empty list")

        payload = {'messages': messages, 'is_test': is_test}
        return self._make_request('POST', '/sms/send-batch', json=payload, timeout=60)

    def get_balance(self, currency: str = 'UGX') -> Dict:
        cache_key = f"sb_balance_{currency}"

        if cached := cache.get(cache_key):
            return cached

        data = self._make_request('GET', '/balance', params={'currency': currency})
        cache.set(cache_key, data, 60)
        return data

    def get_balance_summary(self) -> Dict:
        return self._make_request('GET', '/balance/summary')

    def get_transactions(self, per_page=15, page=1, transaction_type=None, start_date=None, end_date=None):

        params = {'per_page': per_page, 'page': page}

        if transaction_type:
            params['type'] = transaction_type
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date

        return self._make_request('GET', '/balance/transactions', params=params)

    def get_tokens(self):
        return self._make_request('GET', '/tokens')

    def revoke_current_token(self):
        return self._make_request('DELETE', '/tokens/current')

    # -----------------------------
    # Estimation Helpers
    # -----------------------------

    def calculate_segments(self, message: str) -> int:
        length = len(message)
        is_unicode = not self._is_gsm_7bit(message)

        if is_unicode:
            return 1 if length <= 70 else -(-length // 67)

        return 1 if length <= 160 else -(-length // 153)

    def estimate_cost(self, message: str, segment_price: float) -> float:
        return self.calculate_segments(message) * segment_price

    def _is_gsm_7bit(self, text: str) -> bool:
        gsm_chars = (
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ "
            "!\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
            "¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        return all(char in gsm_chars for char in text)

    # -----------------------------
    # Core Request Handling
    # -----------------------------

    def _make_request(self, method, endpoint, json=None, params=None, timeout=None):

        url = f"{self.base_url.rstrip('/')}{endpoint}"
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

            return self._safe_json(response)

        except requests.exceptions.RequestException as exc:
            logger.exception("SignalBridge API request failed")
            raise SignalBridgeException(str(exc))

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

        status = response.status_code
        message = data.get("message", "SignalBridge API error")

        logger.error(
            "SignalBridge API Error [%s]: %s",
            status,
            message,
            extra={"data": data}
        )

        if status == 402:
            raise InsufficientBalanceException(message, data.get('data'))
        elif status == 403:
            raise NoClientException(message)
        elif status == 422:
            raise ValidationException(message, data.get('errors'), data)
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
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        session.headers.update({
            'Authorization': f'Bearer {self.token}',
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
