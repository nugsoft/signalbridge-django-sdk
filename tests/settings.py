"""Minimal Django settings for running the SDK's tests."""

SECRET_KEY = 'signalbridge-sdk-tests'

INSTALLED_APPS = [
    'signalbridge',
]

DATABASES = {}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

USE_TZ = True

SIGNALBRIDGE_TOKEN = 'test-token'
SIGNALBRIDGE_URL = 'https://gateway.test/api'
