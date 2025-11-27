from django.apps import AppConfig


class SignalBridgeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'signalbridge'
    verbose_name = 'SignalBridge SMS Gateway'

    def ready(self):
        """
        Import signal handlers or perform startup tasks here.
        """
        pass
