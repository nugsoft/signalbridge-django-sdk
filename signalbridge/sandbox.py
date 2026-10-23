"""
The sandbox's magic numbers: send to one to drive a message down that path.
Any number not listed is delivered. They do nothing special on live — where
every message is real — so keep them to tests and development.
"""


class MagicNumbers:
    #: Delivered within seconds.
    DELIVERED = '256700000001'

    #: Accepted, then failed. WhatsApp refunds it; an SMS is not refunded, as on live.
    FAILED = '256700000002'

    #: Accepted, and no outcome ever comes: it stays "sent".
    NO_REPORT = '256700000003'

    #: Refused by every provider: "permanently_failed" and refunded.
    REJECTED = '256700000004'

    #: Delivered after a minute.
    SLOW = '256700000005'

    #: WhatsApp: delivered, then read.
    READ = '256700000006'

    #: WhatsApp: outside the 24-hour window — anything but a template fails (Meta 131047).
    OUTSIDE_WINDOW = '256700000007'
