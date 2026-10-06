# SignalBridge Django SDK — notes for AI coding agents

Sends SMS and WhatsApp, and collects mobile money, through the SignalBridge
gateway. Messages cost real money and reach real handsets — the rules below exist
because each one has gone wrong in practice.

## Setup

`settings.py`:

```python
INSTALLED_APPS = [..., 'signalbridge']

SIGNALBRIDGE_TOKEN = os.environ['SIGNALBRIDGE_TOKEN']
# Optional; defaults to the production gateway. Must include the /api suffix.
SIGNALBRIDGE_URL = 'https://signal-bridge.nugsoftapps.net/api'
```

```python
from signalbridge.client import get_client

client = get_client()          # process-wide singleton, pooled HTTP session
client.send_sms('256700000000', 'Your code is 1234')
```

Recipients are international format without a `+` (`256700000000`). Do not set a sender ID:
the gateway sends everything as `NUGSOFT` and ignores `sender_id`. SMS bodies are
capped at 1000 characters, WhatsApp at 4096. `scheduled_at` must be in the future.

## Never retry a send

The gateway charges a message the moment it accepts one, and there is no
idempotency key. A retried send bills and delivers twice. A timeout is the
dangerous case: it says nothing about whether the gateway processed the request.

This SDK retries reads only — see `SAFE_RETRY_METHODS` in `signalbridge/client.py`.
Do not add `POST` to it, and do not wrap a send in Celery's `autoretry_for`,
`task.retry()` or a `tenacity` decorator. If a send times out, find out what
happened before sending again:

```python
client.get_messages(recipient=to, start_date=date.today().isoformat())
```

## Never send real messages from tests

Patch the session in every test that touches the SDK. A test that reaches the real
gateway sends a real SMS and bills the account — including from CI.

```python
from unittest.mock import MagicMock, patch

response = MagicMock(status_code=200)
response.json.return_value = {'success': True, 'data': {'message_id': 1}}

with patch.object(client.session, 'request', return_value=response):
    client.send_sms('256700000000', 'Test')
```

There is no test mode. `is_test=True` only labels a message — it is still
delivered and charged. For a manual check against the real gateway, use a number
you control.

## Never calculate cost yourself

Segment counting is not "len(message) / 160". Unicode, emoji and the GSM escape
table all change it, and the gateway's rules are mirrored exactly by the SDK:

```python
segments = client.calculate_segments(message)
cost = client.estimate_cost(message, float(segment_price))
```

Hand-rolling this produces quotes that do not match the invoice.

## Catch the typed exceptions

A bare `except Exception` hides a billing problem as a delivery problem.

```python
from signalbridge.exceptions import (
    InsufficientBalanceException,      # 402, .required_balance / .current_balance
    InsufficientPermissionsException,  # 403, .required_ability
    NoClientException,                 # 403, no client on the account
    RateLimitedException,              # 429
    ServiceUnavailableException,       # 503
    UnauthorizedException,             # 401
    ValidationException,               # 422, .get_errors() / .get_first_error()
)
```

`SignalBridgeException.is_retryable()` is true only for 500/502/503/504 — and even
then, re-sending a message is a decision for your code, not an automatic retry.

## Token abilities

The gateway enforces what a token may do. A token created without a selection gets
`*` and reaches everything; a narrower one raises
`InsufficientPermissionsException`, whose `required_ability` names what was
missing.

| Ability | Needed by |
|---------|-----------|
| `sms:send` | `send_sms()`, `send_batch()` |
| `sms:read` | `get_message_status()`, `get_messages()` |
| `balance:read` | `get_balance()`, `get_balance_summary()`, `get_transactions()` |
| `balance:request-credit` | `request_credit()` |
| `webhooks:read` / `webhooks:write` | reading / changing webhooks |
| `export:read` | `export_messages()`, `export_transactions()` |

WhatsApp and mobile money abilities cannot be granted yet, so those two channels
need a full-access (`*`) token.

## Delivery is asynchronous

A send returns `queued`, not `delivered`. To learn the outcome, either register a
webhook, or poll:

```python
client.get_message_status(message_id)        # stored status
client.get_messages(ids=[11, 12, 13])        # whole batch at once
```

`permanently_failed` means every retry was exhausted **and the charge was
refunded** — treat it as not-sent, not as a silent cost.

Do not call `get_message_status(id, refresh=True)` in a loop. It asks the vendor
live and is rate limited; the plain call is normally current within minutes.

## Verify every webhook

Webhooks are signed over the raw body, so verify `request.body` — never
`json.dumps(parsed)`, which only matches while your key order happens to match the
sender's. The helper also compares in constant time:

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from signalbridge import webhooks

@csrf_exempt
def sms_webhook(request):
    if not webhooks.verify_request(request, settings.SIGNALBRIDGE_WEBHOOK_SECRET):
        return HttpResponse(status=403)
    ...
    return HttpResponse(status=200)
```

Valid events are `message.sent`, `message.delivered`, `message.failed`,
`message.permanently_failed` and `*`. The signing secret is returned once, when
the webhook is created.

## Bulk sending

`send_batch()` takes up to 100 messages per call and returns a `message_id` per
recipient — keep them to reconcile later with `get_messages(ids=[...])`. Do not
loop `send_sms()` for bulk.

A batch stops at the first insufficient balance, so a partial batch is normal:
read `successful`, `failed` and the per-message results rather than assuming all
or nothing.

## Balances

`get_balance()` returns the resource under `data`, and reading one never creates
one — a currency with nothing stored reads as zero. Currency must be a
three-letter code. The result is cached for 60 seconds per token and currency, so
it is cheap to call but can be up to a minute stale.

```python
balance = client.get_balance('UGX')['data']
balance['available_balance']   # balance + credit limit
balance['segment_price']       # pass to estimate_cost()
```

Clients cannot credit themselves: `request_credit()` only notifies the
administrators.

## Channels

```python
client.sms            # send, send_batch, status, messages
client.whatsapp       # send, send_template
client.mobile_money   # initiate, verify
client.ussd           # unreleased on the gateway
```

Mobile money reads `reference` and `note` (the text shown to the payer) only:

```python
client.mobile_money.initiate('256700000000', 15000, 'UGX', reference='INV-1', note='Invoice')
client.mobile_money.verify(transaction_id)
```

Avoid `client.whatsapp.send_template()` for now: the gateway does not yet deliver
template sends as templates, so the message goes out empty and ends up
permanently failed. Use `client.whatsapp.send()` within the 24-hour window.

`client.mobile_money.disburse()` raises `ServiceUnavailableException`; the gateway
exposes no payout endpoint.

## Management commands

```bash
python manage.py signalbridge_send_sms 256700000000 "Hello" --test
python manage.py signalbridge_check_balance --currency UGX
python manage.py signalbridge_transactions --type debit --per-page 50
```

`signalbridge_send_sms` sends a real message unless you pass `--test`.

## Do not log message bodies or recipient numbers

The SDK deliberately logs only the status, message and error code. Keep it that
way in application code.
