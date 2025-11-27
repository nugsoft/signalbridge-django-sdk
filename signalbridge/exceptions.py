"""
SignalBridge custom exceptions
"""


class SignalBridgeException(Exception):
    """Base exception for SignalBridge errors"""

    def __init__(self, message='', code=0, data=None):
        super().__init__(message)
        self.code = code
        self.data = data or {}

    def get_data(self):
        return self.data

    def get_message(self):
        return str(self)

    def is_retryable(self):
        return self.code in (500, 502, 503, 504)


class InsufficientBalanceException(SignalBridgeException):
    """Raised when account has insufficient balance"""

    def __init__(self, message='Insufficient balance', data=None):
        super().__init__(message, 402, data or {})

    @property
    def required_balance(self):
        return self.data.get('required_balance')

    @property
    def current_balance(self):
        return self.data.get('current_balance')

    @property
    def segments(self):
        return self.data.get('segments')


class NoClientException(SignalBridgeException):
    """Raised when no client is associated with account"""

    def __init__(self, message='No client associated with your account'):
        super().__init__(message, 403)


class ValidationException(SignalBridgeException):
    """Raised when validation fails"""

    def __init__(self, message='Validation error', errors=None, data=None):
        super().__init__(message, 422, data or {})
        self.errors = errors or {}

    def get_errors(self):
        return self.errors

    def get_first_error(self):
        if not self.errors:
            return None

        field = next(iter(self.errors))
        value = self.errors.get(field)

        if isinstance(value, list) and value:
            return value[0]

        return value


class ServiceUnavailableException(SignalBridgeException):
    """Raised when SMS service is unavailable"""

    def __init__(self, message='SMS service is currently unavailable'):
        super().__init__(message, 503)
