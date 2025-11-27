# SignalBridge Django SDK

Official Django SDK for SignalBridge SMS Gateway - Send SMS through multiple vendors with a unified API.

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
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

## Installation

```bash
pip install signalbridge-django
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
```

Or use environment variables:

```bash
# .env
SIGNALBRIDGE_TOKEN=your-api-token-here
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

### Client Methods

#### `send_sms(recipient, message, metadata=None, is_test=False, scheduled_at=None)`

Send a single SMS message.

**Parameters:**
- `recipient` (str): Phone number in international format (e.g., '256700000000')
- `message` (str): Message content (max 1000 characters)
- `metadata` (dict, optional): Custom data to store with message
- `is_test` (bool): Flag as test message (won't be charged)
- `scheduled_at` (datetime, optional): Schedule for future sending

**Returns:** Dict with `success`, `message`, and `data` keys

#### `send_batch(messages, is_test=False)`

Send multiple SMS messages in one request.

**Parameters:**
- `messages` (list): List of message dicts with `recipient`, `message`, optional `metadata`
- `is_test` (bool): Mark all as test messages

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

```python
from django.test import TestCase
from unittest.mock import patch, MagicMock
from signalbridge.client import SignalBridgeClient

class SMSTestCase(TestCase):
    @patch('signalbridge.client.requests.Session')
    def test_send_sms(self, mock_session):
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'message': 'SMS queued successfully'
        }
        mock_session.return_value.request.return_value = mock_response

        client = SignalBridgeClient(token='test-token')
        result = client.send_sms('256700000000', 'Test message')

        self.assertTrue(result['success'])
```

## Requirements

- Python 3.8+
- Django 3.2+
- requests >= 2.25.0

## Support

For issues and questions:
- Documentation: https://signal-bridge.nugsoftstagging.com/docs

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Related SDKs

- **Laravel SDK**: [nugsoft/signalbridge-laravel-sdk](https://github.com/nugsoft/signalbridge-laravel-sdk)
- **PHP SDK**: [nugsoft/signalbridge-php-sdk](https://github.com/nugsoft/signalbridge-php-sdk)
