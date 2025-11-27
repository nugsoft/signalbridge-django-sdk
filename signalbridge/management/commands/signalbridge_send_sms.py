"""Management command to send SMS from CLI"""
from django.core.management.base import BaseCommand, CommandError
from signalbridge.client import get_client
from signalbridge.exceptions import SignalBridgeException


class Command(BaseCommand):
    help = 'Send SMS via SignalBridge'

    def add_arguments(self, parser):
        parser.add_argument('recipient', type=str, help='Phone number')
        parser.add_argument('message', type=str, help='Message content')
        parser.add_argument('--sender-id', type=str, help='Custom sender ID')
        parser.add_argument('--test', action='store_true', help='Mark as test message')

    def handle(self, *args, **options):
        client = get_client()

        try:
            result = client.send_sms(
                recipient=options['recipient'],
                message=options['message'],
                sender_id=options.get('sender_id'),
                is_test=options.get('test', False)
            )

            self.stdout.write(
                self.style.SUCCESS(f"{result['message']}")
            )

        except SignalBridgeException as e:
            raise CommandError(str(e))
