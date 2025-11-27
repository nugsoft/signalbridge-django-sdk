# Changelog

All notable changes to the SignalBridge Django SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-XX

### Added
- Initial release of SignalBridge Django SDK
- Single and batch SMS sending functionality
- Balance management and transaction history
- Segment calculation for GSM 7-bit and Unicode messages
- Cost estimation before sending
- Django management commands (send_sms, check_balance, transactions)
- Django AppConfig integration
- Native Django settings support
- Comprehensive exception handling with typed exceptions
- Example Django views for real-world use cases
- Full API documentation and examples
- HTTP session pooling for performance
- Support for Django 3.2, 4.0, 4.1, 4.2, and 5.0
- Support for Python 3.8, 3.9, 3.10, 3.11, and 3.12

### Features
- OTP verification system example
- Batch student notifications example
- Appointment reminders with balance checking
- Cost estimator before sending campaigns
- Transaction history and reporting
- Scheduled message support
- Custom metadata tracking
- Test message flagging

### Developer Tools
- Management commands for CLI operations
- Singleton client pattern with get_client()
- Django logging integration
- Comprehensive test examples
- Type hints throughout codebase
