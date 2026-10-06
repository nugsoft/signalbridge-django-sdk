"""Management command to send SMS from CLI"""
from django.core.management.base import BaseCommand, CommandError

from signalbridge.client import get_client
from signalbridge.exceptions import SignalBridgeException


class Command(BaseCommand):
    help = 'Send SMS via SignalBridge'

    def add_arguments(self, parser):
        parser.add_argument('recipient', type=str, help='Phone number')
        parser.add_argument('message', type=str, help='Message content')
        parser.add_argument('--sender-id', type=str, help='Deprecated, ignored: the gateway always sends as NUGSOFT')
        parser.add_argument('--test', action='store_true', help='Label as a test message (it is still sent and charged)')

    def handle(self, *args, **options):
        client = get_client()

        try:
            result = client.send_sms(
                recipient=options['recipient'],
                message=options['message'],
                sender_id=options.get('sender_id'),
                is_test=options.get('test', False)
            )

            data = result.get('data', {})

            self.stdout.write(self.style.SUCCESS(result.get('message', 'SMS queued')))

            if data:
                self.stdout.write("  Message ID: {}".format(data.get('message_id')))
                self.stdout.write("  Status: {}".format(data.get('status')))
                self.stdout.write("  Segments: {}".format(data.get('segments')))
                self.stdout.write("  Cost: {}".format(data.get('cost')))
                self.stdout.write("  Balance after: {}".format(data.get('balance_after')))

        except SignalBridgeException as e:
            raise CommandError(str(e))
