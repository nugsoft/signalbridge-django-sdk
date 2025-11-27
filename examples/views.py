"""
Django View Examples for SignalBridge SDK

Real-world examples showing integration patterns
"""
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import random

from signalbridge.client import get_client
from signalbridge.exceptions import (
    InsufficientBalanceException,
    ValidationException,
    SignalBridgeException
)


# Example 1: OTP Verification System
class SendOTPView(View):
    """Send OTP via SMS for two-factor authentication"""
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        phone = request.POST.get('phone')
        
        # Generate 6-digit OTP
        otp = random.randint(100000, 999999)
        
        # Store in session
        request.session['otp'] = str(otp)
        request.session['otp_phone'] = phone
        
        try:
            client = get_client()
            result = client.send_sms(
                recipient=phone,
                message=f'Your verification code is {otp}. Valid for 5 minutes.',
                metadata={'purpose': 'otp', 'user_id': request.user.id if request.user.is_authenticated else None}
            )
            
            return JsonResponse({
                'success': True,
                'message': 'OTP sent successfully',
                'expires_in': 300  # 5 minutes
            })
            
        except ValidationException as e:
            return JsonResponse({
                'success': False,
                'errors': e.get_errors()
            }, status=422)
            
        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


class VerifyOTPView(View):
    """Verify OTP submitted by user"""
    
    @method_decorator(csrf_exempt)
    def post(self, request):
        submitted_otp = request.POST.get('otp')
        stored_otp = request.session.get('otp')
        
        if submitted_otp == stored_otp:
            # Clear OTP from session
            del request.session['otp']
            del request.session['otp_phone']
            
            return JsonResponse({
                'success': True,
                'message': 'OTP verified successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Invalid OTP'
            }, status=400)


# Example 2: Batch Student Notifications
@method_decorator(login_required, name='dispatch')
class SendExamResultsView(View):
    """Send exam results to multiple students"""
    
    def post(self, request):
        # In real app, fetch from database
        students = [
            {'name': 'Alice', 'phone': '256700000001', 'marks': 85},
            {'name': 'Bob', 'phone': '256700000002', 'marks': 92},
            {'name': 'Charlie', 'phone': '256700000003', 'marks': 78},
        ]
        
        messages = []
        for student in students:
            messages.append({
                'recipient': student['phone'],
                'message': f"Dear {student['name']}, your exam result: {student['marks']}/100. "
                          f"{'Excellent!' if student['marks'] >= 90 else 'Good work!' if student['marks'] >= 75 else 'Keep trying!'}",
                'metadata': {'student_id': student['name'], 'marks': student['marks']}
            })
        
        try:
            client = get_client()
            result = client.send_batch(messages)
            
            return JsonResponse({
                'success': True,
                'message': f"Sent {result['data']['successful']} of {result['data']['total']} messages",
                'details': result['data']
            })
            
        except InsufficientBalanceException as e:
            return JsonResponse({
                'success': False,
                'message': f'Insufficient balance. Need {e.get_required_balance()}, have {e.get_current_balance()}',
                'segments': e.get_segments()
            }, status=402)
            
        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


# Example 3: Appointment Reminders with Balance Check
@method_decorator(login_required, name='dispatch')
class SendAppointmentReminderView(View):
    """Send scheduled appointment reminder"""
    
    def post(self, request):
        appointment_data = {
            'patient_name': request.POST.get('patient_name'),
            'phone': request.POST.get('phone'),
            'date': request.POST.get('date'),
            'time': request.POST.get('time'),
            'doctor': request.POST.get('doctor')
        }
        
        message = (
            f"Reminder: Dear {appointment_data['patient_name']}, "
            f"you have an appointment with Dr. {appointment_data['doctor']} "
            f"on {appointment_data['date']} at {appointment_data['time']}. "
            f"Please arrive 15 minutes early."
        )
        
        try:
            client = get_client()
            
            # Check balance first
            balance = client.get_balance()
            if balance['data']['balance'] < 100:  # Threshold
                return JsonResponse({
                    'success': False,
                    'message': 'Balance too low. Please top up.',
                    'current_balance': balance['data']['balance']
                }, status=402)
            
            # Send SMS
            result = client.send_sms(
                recipient=appointment_data['phone'],
                message=message,
                metadata={'type': 'appointment', 'patient': appointment_data['patient_name']}
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Reminder sent successfully',
                'segments': result['data'].get('segments', 1)
            })
            
        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


# Example 4: Transaction History Dashboard
@method_decorator(login_required, name='dispatch')
class TransactionHistoryView(View):
    """View SMS transaction history with filtering"""
    
    def get(self, request):
        page = int(request.GET.get('page', 1))
        transaction_type = request.GET.get('type')  # 'debit' or 'credit'
        
        try:
            client = get_client()
            result = client.get_transactions(
                page=page,
                per_page=20,
                transaction_type=transaction_type
            )
            
            return JsonResponse({
                'success': True,
                'data': result['data']
            })
            
        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


# Example 5: Cost Estimator
class EstimateSMSCostView(View):
    """Estimate SMS cost before sending"""
    
    def post(self, request):
        message = request.POST.get('message')
        
        try:
            client = get_client()
            
            # Get segment price from balance
            balance = client.get_balance()
            segment_price = balance['data']['segment_price']
            
            # Calculate segments and cost
            segments = client.calculate_segments(message)
            estimated_cost = client.estimate_cost(message, segment_price)
            
            return JsonResponse({
                'success': True,
                'message_length': len(message),
                'segments': segments,
                'segment_price': segment_price,
                'estimated_cost': estimated_cost,
                'encoding': 'Unicode' if segments == 1 and len(message) <= 70 or len(message) > 160 else 'GSM 7-bit'
            })
            
        except SignalBridgeException as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=500)


# URL patterns example (add to your urls.py)
"""
from django.urls import path
from examples import views

urlpatterns = [
    # OTP System
    path('sms/otp/send/', views.SendOTPView.as_view(), name='send-otp'),
    path('sms/otp/verify/', views.VerifyOTPView.as_view(), name='verify-otp'),
    
    # Batch Notifications
    path('sms/results/send/', views.SendExamResultsView.as_view(), name='send-results'),
    
    # Appointment Reminders
    path('sms/reminder/send/', views.SendAppointmentReminderView.as_view(), name='send-reminder'),
    
    # Transaction History
    path('sms/transactions/', views.TransactionHistoryView.as_view(), name='transactions'),
    
    # Cost Estimator
    path('sms/estimate/', views.EstimateSMSCostView.as_view(), name='estimate-cost'),
]
"""
