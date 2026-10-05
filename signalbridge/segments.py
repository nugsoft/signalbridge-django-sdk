"""
How SignalBridge counts SMS segments.

This must agree with the gateway's own ``BalanceService::calculateSegments()``,
character for character, and with the PHP and Laravel SDKs. When it does not,
``estimate_cost()`` quotes one figure and the invoice shows another.

Three mistakes were in this SDK's own copy of the maths, and all three are easy
to reintroduce:

* The alphabet must contain a real line feed and carriage return. Written as the
  two-character sequences ``\\n`` and ``\\r`` they fall outside the alphabet, so
  every multi-line message is billed as Unicode — 70 characters per segment
  instead of 160.
* The escape-table characters (``^{}\\[]~|€``) belong in the alphabet. Without
  them any message containing a ``{placeholder}`` was treated as Unicode and
  over-quoted by half.
* Unicode segments are counted in UTF-16 code units, not characters. An emoji
  sits outside the Basic Multilingual Plane and takes two units; counting it as
  one under-quotes long emoji messages.
"""

import math

#: The GSM 03.38 alphabet as the gateway bills it.
#:
#: The escape-table characters are counted as one character each, matching the
#: gateway. Strict GSM-7 charges two septets for those.
GSM_7BIT_CHARSET = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ^{}\\[]~€|ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

GSM_SINGLE = 160
GSM_MULTIPART = 153
UNICODE_SINGLE = 70
UNICODE_MULTIPART = 67

_GSM_CHARS = frozenset(GSM_7BIT_CHARSET)


def is_gsm_7bit(message: str) -> bool:
    """Whether every character falls inside the GSM alphabet."""
    return all(char in _GSM_CHARS for char in message)


def count(message: str) -> int:
    """Segments a message body will be split into."""
    if message == "":
        return 1

    if is_gsm_7bit(message):
        length = len(message)

        return 1 if length <= GSM_SINGLE else math.ceil(length / GSM_MULTIPART)

    # UCS-2 counts UTF-16 code units, so anything outside the Basic Multilingual
    # Plane — emoji, mostly — takes two.
    units = sum(2 if ord(char) > 0xFFFF else 1 for char in message)

    return 1 if units <= UNICODE_SINGLE else math.ceil(units / UNICODE_MULTIPART)


def estimate_cost(message: str, segment_price: float) -> float:
    """Estimated cost of sending a message at the given per-segment rate."""
    return count(message) * segment_price
