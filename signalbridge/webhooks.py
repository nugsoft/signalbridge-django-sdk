"""
Verifying that an inbound webhook really came from SignalBridge.

The gateway signs the RAW request body with HMAC-SHA256 and sends the digest in
``X-SignalBridge-Signature``. Two details are easy to get wrong by hand, and
both are silent:

* Sign the raw body, not a re-encoded copy of the parsed payload. Re-encoding
  only matches while your JSON key order happens to match the sender's. In
  Django that means ``request.body``, never ``json.dumps(request.data)``.
* Compare in constant time. A plain ``==`` leaks the expected digest a byte at
  a time to anyone willing to measure.
"""

import hashlib
import hmac
from typing import Optional, Union

HEADER = "X-SignalBridge-Signature"
EVENT_HEADER = "X-SignalBridge-Event"

#: Django exposes headers in META under this key.
META_KEY = "HTTP_X_SIGNALBRIDGE_SIGNATURE"


def _as_bytes(value: Union[str, bytes]) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else value


def sign(payload: Union[str, bytes], secret: str) -> str:
    """The signature a given body should carry. Useful in your own tests."""
    digest = hmac.new(_as_bytes(secret), _as_bytes(payload), hashlib.sha256).hexdigest()

    return "sha256={}".format(digest)


def verify(payload: Union[str, bytes], signature: Optional[str], secret: str) -> bool:
    """
    Verify a raw body against a signature header.

    The header may arrive with or without the ``sha256=`` prefix.
    """
    if not signature or not secret:
        return False

    provided = signature[7:] if signature.startswith("sha256=") else signature

    expected = hmac.new(_as_bytes(secret), _as_bytes(payload), hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, provided)


def verify_request(request, secret: str) -> bool:
    """
    Verify a Django ``HttpRequest`` carrying a SignalBridge webhook.

    Reads ``request.body``, which is the raw bytes as received.
    """
    signature = request.META.get(META_KEY) or request.headers.get(HEADER)

    return verify(request.body, signature, secret)
