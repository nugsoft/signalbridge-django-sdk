# SignalBridge Django SDK

Official Django SDK for SignalBridge SMS Gateway - Send SMS through multiple vendors with a unified API.

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Django Version](https://img.shields.io/badge/django-3.2%2B-green)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/pypi/v/signalbridge-django-sdk)](https://pypi.org/project/signalbridge-django-sdk/)
[![Downloads](https://img.shields.io/pypi/dm/signalbridge-django-sdk)](https://pypi.org/project/signalbridge-django-sdk/)

## Features

- **Unified SMS API** - Single interface for multiple SMS vendors (SpeedaMobile, Africa's Talking, etc)
- **Batch Sending** - Send bulk SMS efficiently with detailed results
- **Balance Management** - Real-time balance tracking and transaction history
- **Segment Calculation** - Automatic GSM 7-bit vs Unicode detection and cost estimation
- **Django Integration** - Native Django settings, logging, and session support
- **Management Commands** - CLI tools for common SMS operations
- **Session Pooling** - HTTP session reuse for optimal performance
- **Typed Exceptions** - Specific exceptions for different error scenarios
- **Every Channel** - SMS, WhatsApp and Mobile Money, with USSD stubbed for when it ships
- **Delivery Status** - Read a message's status, or follow up a whole batch
- **Webhooks** - Manage endpoints and verify inbound signatures safely

## Installation

```bash
pip install signalbridge-django-sdk
```

Add to your Django `INSTALLED_APPS`:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'signalbridge',
]

# SignalBridge Configuration
SIGNALBRIDGE_TOKEN = 'your-api-token-here'

# Optional. Defaults to the production gateway. Must include the /api suffix.
SIGNALBRIDGE_URL = 'https://signal-bridge.nugsoftapps.net/api'
```

Or use environment variables:

```bash
# .env
SIGNALBRIDGE_TOKEN=your-api-token-here
```

## Using this SDK with an AI coding agent

The package ships agent guidance at `signalbridge/AGENTS.md`, covering the things
that are easy to get expensively wrong — retrying a send that was already
charged, sending real messages from a test suite, hand-rolling segment costs,
verifying webhooks against a re-encoded body instead of the raw one.

It is installed with the package, so it is present in any environment that has
the SDK. Nothing discovers it automatically; wire it up once.

Find the installed path:

```bash
python -c "import signalbridge, pathlib; print(pathlib.Path(signalbridge.__file__).parent / 'AGENTS.md')"
```

**Claude Code** — add one line to your project's `CLAUDE.md` (or your own
`AGENTS.md`, which Claude Code reads when there is no `CLAUDE.md`). A path inside
the working directory needs no approval:

```md
@.venv/lib/python3.12/site-packages/signalbridge/AGENTS.md
```

**Other agents, or an environment outside the project** — copy it in, and
re-copy on upgrade:

```bash
cat "$(python -c 'import signalbridge, pathlib; print(pathlib.Path(signalbridge.__file__).parent / "AGENTS.md")')" >> AGENTS.md
```

## Quick Start

### Basic SMS Sending

```python
from signalbridge.client import get_client

client = get_client()

# Send single SMS
result = client.send_sms(
    recipient='256700000000',
    message='Hello from SignalBridge!'
)

print(result['message'])  # "SMS queued successfully"
```

### In Django Views

```python
from django.http import JsonResponse
from django.views import View
from signalbridge.client import get_client
from signalbridge.exceptions import SignalBridgeException

class SendSMSView(View):
    def post(self, request):
        try:
            client = get_client()
            result = client.send_sms(
                recipient=request.POST.get('phone'),
                message=request.POST.get('message')
            )

            return JsonResponse({
                'success': True,
                'message': result['message']
            })

        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)
```

## Real-World Use Cases

### 1. OTP Verification System

```python
from django.views import View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import random
from signalbridge.client import get_client

class SendOTPView(View):
    @method_decorator(csrf_exempt)
    def post(self, request):
        phone = request.POST.get('phone')
        otp = random.randint(100000, 999999)

        # Store in session
        request.session['otp'] = str(otp)
        request.session['otp_phone'] = phone

        client = get_client()
        result = client.send_sms(
            recipient=phone,
            message=f'Your verification code is {otp}. Valid for 5 minutes.',
            metadata={'purpose': 'otp'}
        )

        return JsonResponse({
            'success': True,
            'message': 'OTP sent successfully'
        })

class VerifyOTPView(View):
    @method_decorator(csrf_exempt)
    def post(self, request):
        submitted = request.POST.get('otp')
        stored = request.session.get('otp')

        if submitted == stored:
            del request.session['otp']
            return JsonResponse({'success': True, 'message': 'Verified'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid OTP'}, status=400)
```

### 2. Batch Student Notifications

```python
from signalbridge.client import get_client
from signalbridge.exceptions import InsufficientBalanceException

def send_exam_results(students):
    """Send exam results to multiple students"""
    messages = []
    for student in students:
        messages.append({
            'recipient': student.phone,
            'message': f"Dear {student.name}, your exam result: {student.marks}/100",
            'metadata': {'student_id': student.id}
        })

    try:
        client = get_client()
        result = client.send_batch(messages)

        print(f"Sent {result['data']['successful']} of {result['data']['total']} messages")
        return result

    except InsufficientBalanceException as e:
        print(f"Need {e.get_required_balance()} UGX, have {e.get_current_balance()} UGX")
        raise
```

### 3. Appointment Reminders with Balance Check

```python
from signalbridge.client import get_client

def send_appointment_reminder(appointment):
    client = get_client()

    # Check balance first
    balance = client.get_balance()
    if balance['data']['balance'] < 100:  # Minimum threshold
        raise ValueError("Balance too low. Please top up.")

    message = (
        f"Reminder: Dear {appointment.patient_name}, "
        f"you have an appointment with Dr. {appointment.doctor} "
        f"on {appointment.date} at {appointment.time}."
    )

    result = client.send_sms(
        recipient=appointment.phone,
        message=message,
        metadata={'appointment_id': appointment.id}
    )

    return result
```

### 4. Cost Estimator Before Sending

```python
from signalbridge.client import get_client

def estimate_campaign_cost(message, recipient_count):
    """Calculate cost before sending bulk SMS"""
    client = get_client()

    # Get current pricing
    balance = client.get_balance()
    segment_price = balance['data']['segment_price']

    # Calculate segments
    segments = client.calculate_segments(message)
    cost_per_message = client.estimate_cost(message, segment_price)
    total_cost = cost_per_message * recipient_count

    return {
        'segments': segments,
        'cost_per_message': cost_per_message,
        'recipient_count': recipient_count,
        'total_cost': total_cost,
        'current_balance': balance['data']['balance'],
        'sufficient': balance['data']['balance'] >= total_cost
    }

# Usage
estimate = estimate_campaign_cost("Your message here", recipient_count=500)
print(f"Campaign will cost {estimate['total_cost']} for {estimate['recipient_count']} recipients")
```

### 5. Transaction History and Reporting

```python
from signalbridge.client import get_client
from datetime import datetime, timedelta

def generate_monthly_report():
    """Generate SMS usage report for the past month"""
    client = get_client()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    transactions = client.get_transactions(
        per_page=100,
        transaction_type='debit',  # Only SMS sends
        start_date=start_date,
        end_date=end_date
    )

    total_spent = sum(t['amount'] for t in transactions['data']['data'])
    total_messages = len(transactions['data']['data'])

    return {
        'period': f"{start_date} to {end_date}",
        'total_messages': total_messages,
        'total_spent': total_spent,
        'average_cost': total_spent / total_messages if total_messages > 0 else 0
    }
```

## Management Commands

The SDK includes Django management commands for CLI operations:

### Send SMS from Command Line

```bash
python manage.py signalbridge_send_sms 256700000000 "Your message"
```

### Check Balance

```bash
python manage.py signalbridge_check_balance --currency=UGX
```

Output:
```
Balance Summary

  Currency: UGX
  Balance: 50000.0
  Credit Limit: 0.0
  Segment Price: 50.0
```

### View Transaction History

```bash
python manage.py signalbridge_transactions --page=1 --per-page=20 --type=debit
```

## API Reference

### Channels

Mirrors the PHP and Laravel SDKs:

```python
client.sms            # send, send_batch, status, messages
client.whatsapp       # templates, free text, Flows, received messages
client.mobile_money   # initiate, verify
client.ussd           # planned, not live on the gateway yet
```

The flat methods (`send_sms()`, `send_batch()`, …) are kept and proxy to the
channels, so existing code keeps working.

### WhatsApp

WhatsApp only lets a business **start** a conversation with a **template** it has
approved: submit one, wait for approval, then send it as often as you like. Free text
and Flows are delivered only within **24 hours of the person's last message to you**.
SignalBridge holds every WhatsApp credential and does all of WhatsApp's encryption.

```python
whatsapp = client.whatsapp

# Once: submit a template. A template.approved webhook arrives when WhatsApp approves it.
whatsapp.create_template({
    'name': 'fee_reminder',
    'category': 'utility',   # utility | marketing | authentication
    'body': 'Hello {{1}}, your fee balance is {{2}}. Please pay by Friday.',
    'examples': ['John', 'UGX 50,000'],
})

# Then send it — the variables as a plain list
whatsapp.send_template('256700000000', 'fee_reminder', ['John', 'UGX 50,000'])

# A template that starts with a document or image takes the file as a link
whatsapp.send_template('256700000000', 'weekly_report', ['Kampala branch'],
                       header={'type': 'document', 'url': 'https://files.example.com/report.pdf', 'filename': 'report.pdf'})

# Within 24 hours of their last message: free text, or a Flow
whatsapp.send('256700000000', 'Thanks — we have received your payment.')
whatsapp.send_flow('256700000000', 'spa_booking', 'Book your next session', 'Book now')

# What customers sent you, and their files
whatsapp.received(since='2026-10-07T00:00:00+03:00')
data = whatsapp.download_media(received_message_id)   # bytes
```

**Flows** are forms customers fill in inside WhatsApp. Create one from the JSON
WhatsApp's Flow Builder exports with `create_flow({'name': …, 'categories': […],
'flow_json': …, 'endpoint_url': …})`, then `publish_flow(flow_id)`. Answers arrive as a
`flow.completed` webhook. If the Flow fetches live data, SignalBridge decrypts
WhatsApp's calls and posts them to your `endpoint_url` as plain JSON, signed with the
`endpoint_secret` returned when you created it:

```python
from django.http import JsonResponse, HttpResponseForbidden
from signalbridge.webhooks import verify_request

def flow_endpoint(request):
    if not verify_request(request, settings.SIGNALBRIDGE_FLOW_SECRET):
        return HttpResponseForbidden()

    call = json.loads(request.body)   # event, flow, action, screen, data, flow_token, message_id, recipient
    return JsonResponse({'screen': 'SLOTS', 'data': {'slots': ['10:00', '11:00']}})
```

Reply within a few seconds — WhatsApp waits about ten.

WhatsApp webhook events: `message.sent`, `message.delivered`, `message.read`,
`message.failed`, `message.received`, `flow.completed`, `template.approved`,
`template.rejected`, `template.paused`, `template.disabled`. Template and Flow events
are not in the default subscription.

### Token abilities

A token carries abilities and the gateway enforces them on every route. A token
created without a selection gets `*` and can do everything. A narrower token is
refused elsewhere with a 403 naming the missing ability, raised here as
`InsufficientPermissionsException` with a `required_ability` attribute:

```python
from signalbridge.exceptions import InsufficientPermissionsException

try:
    client.get_balance()
except InsufficientPermissionsException as e:
    print(e.required_ability)   # 'balance:read'
```

| Ability | Allows |
|---------|--------|
| `sms:send` | `send_sms()`, `send_batch()` |
| `sms:read` | `get_message_status()`, `get_messages()` |
| `balance:read` | `get_balance()`, `get_balance_summary()`, `get_transactions()` |
| `balance:request-credit` | `request_credit()` |
| `webhooks:read` / `webhooks:write` | reading / changing webhooks |
| `export:read` | `export_messages()`, `export_transactions()` |

> `mobile-money:send` and `mobile-money:read` are not issuable at the moment: the mobile money channel is unreleased, so reaching it needs a full-access (`*`) token.
The WhatsApp abilities are `whatsapp:send`, `whatsapp:templates`, `whatsapp:flows` and `whatsapp:read`.

### Delivery status

```python
# One message. refresh=True asks the vendor live — rate limited, and rarely
# needed, because the gateway polls vendors in the background.
status = client.get_message_status(message_id)
print(status['data']['status'])      # queued, sent, delivered, failed …

# A whole batch, by the ids send_batch() returned. 'summary' counts the entire
# filtered set rather than the current page.
messages = client.get_messages(ids=[11, 12, 13])
print(messages['summary']['by_status'])
```

### Webhooks

```python
created = client.create_webhook('https://your-app.example/webhooks/sms', ['message.delivered'])
secret = created['secret']          # shown once, at creation
```

Verifying one in a Django view — always against `request.body`, the raw bytes,
never a re-encoded copy of the parsed payload:

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

### Exports

```python
csv = client.export_messages(start_date='2026-01-01')
```

### Retries

Reads (GET/HEAD/OPTIONS) are retried three times on 500/502/503/504 with a
backoff. **Sends are never retried automatically.** The gateway charges a message
the moment it accepts one, so retrying a POST — including after a read timeout,
which says nothing about whether the gateway processed it — risks delivering and
billing the same SMS twice. Retry a send yourself only after checking
`get_messages()` for what actually went out.

### Client Methods

#### `send_sms(recipient, message, metadata=None, is_test=False, sender_id=None, scheduled_at=None)`

Send a single SMS message.

**Parameters:**
- `recipient` (str): Phone number in international format (e.g., '256700000000')
- `message` (str): Message content (max 1000 characters)
- `metadata` (dict, optional): Custom data to store with message
- `is_test` (bool): A label only — the message is still sent and charged
- `sender_id` (str, optional): **Deprecated, ignored.** The gateway sends every message as `NUGSOFT`
- `scheduled_at` (datetime, optional): Schedule for future sending

**Returns:** Dict with `success`, `message`, and `data` keys

#### `send_batch(messages, is_test=False, sender_id=None)`

Send multiple SMS messages in one request.

**Parameters:**
- `messages` (list): List of message dicts with `recipient`, `message`, optional `metadata`
- `is_test` (bool): A label only — the messages are still sent and charged
- `sender_id` (str, optional): **Deprecated, ignored.** The gateway sends every message as `NUGSOFT`

**Returns:** Dict with total, successful, failed counts

#### `get_balance(currency='UGX')`

Get current balance for a currency.

**Returns:** Dict with balance, credit_limit, segment_price

#### `get_balance_summary()`

Get comprehensive balance summary with recent activity.

#### `get_transactions(per_page=15, page=1, transaction_type=None, start_date=None, end_date=None)`

Retrieve transaction history.

**Parameters:**
- `per_page` (int): Results per page (1-100)
- `page` (int): Page number
- `transaction_type` (str): Filter by 'credit' or 'debit'
- `start_date` (str): Start date (YYYY-MM-DD)
- `end_date` (str): End date (YYYY-MM-DD)

#### `calculate_segments(message)`

Calculate number of SMS segments for a message.

**Returns:** int - Number of segments

#### `estimate_cost(message, segment_price)`

Estimate cost for sending a message.

**Returns:** float - Estimated cost

## Exception Handling

The SDK provides specific exceptions for different scenarios:

```python
from signalbridge.exceptions import (
    InsufficientBalanceException,
    ValidationException,
    NoClientException,
    ServiceUnavailableException,
    SignalBridgeException
)

try:
    client.send_sms(recipient='256700000000', message='Test')

except InsufficientBalanceException as e:
    print(f"Balance: {e.get_current_balance()}")
    print(f"Required: {e.get_required_balance()}")
    print(f"Segments: {e.get_segments()}")

except ValidationException as e:
    print(f"Errors: {e.get_errors()}")
    print(f"First error: {e.get_first_error()}")

except NoClientException as e:
    print("Client not found or unauthorized")

except ServiceUnavailableException as e:
    print("Service temporarily unavailable")

except SignalBridgeException as e:
    print(f"Error: {e.message}")
    print(f"Status: {e.status_code}")
```

## Configuration

### Django Settings

```python
# settings.py

# Required
SIGNALBRIDGE_TOKEN = 'your-api-token-here'


# Logging
LOGGING = {
    'loggers': {
        'signalbridge': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    },
}
```

### Environment Variables

```bash
SIGNALBRIDGE_TOKEN=your-api-token-here
```

## Testing

### Testing your own code

Patch the client's session so nothing leaves your machine. A test that reached
the real gateway would send a real SMS and bill the account.

```python
from django.test import TestCase
from unittest.mock import MagicMock, patch
from signalbridge.client import SignalBridgeClient

class SMSTestCase(TestCase):
    def test_send_sms(self):
        client = SignalBridgeClient(token='test-token')

        response = MagicMock(status_code=200)
        response.json.return_value = {'success': True, 'message': 'SMS queued successfully'}

        with patch.object(client.session, 'request', return_value=response):
            result = client.send_sms('256700000000', 'Test message')

        self.assertTrue(result['success'])
```

### Testing this SDK

```bash
pip install django requests
django-admin test tests --settings=tests.settings --pythonpath=.
```

`tests/test_segments.py` pins the segment maths against the gateway's own cases,
including the GSM alphabet itself. If the gateway's
`BalanceService::calculateSegments()` changes, that test should fail here before
a client is quoted a price that does not match their invoice.

## Requirements

- Python 3.9+
- Django 3.2+
- requests >= 2.25.0

## Support

For issues and questions:
- Documentation: https://signal-bridge.nugsoftapps.net/docs

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Related SDKs

- **Laravel SDK**: [nugsoft/signalbridge-laravel-sdk](https://github.com/nugsoft/signalbridge-laravel-sdk)
- **PHP SDK**: [nugsoft/signalbridge-php-sdk](https://github.com/nugsoft/signalbridge-php-sdk)
