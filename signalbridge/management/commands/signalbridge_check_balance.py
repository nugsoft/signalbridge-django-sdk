"""Management command to check SignalBridge balance"""
from django.core.management.base import BaseCommand, CommandError

from signalbridge.client import get_client
from signalbridge.exceptions import SignalBridgeException


class Command(BaseCommand):
    help = 'Check SignalBridge balance'

    def add_arguments(self, parser):
        parser.add_argument('--currency', type=str, default='UGX', help='Currency code')

    def handle(self, *args, **options):
        client = get_client()

        try:
            result = client.get_balance(currency=options['currency'])
            data = result.get('data') or {}

            self.stdout.write(self.style.SUCCESS('\nBalance Summary\n'))
            self.stdout.write("  Currency: {}".format(data.get('currency')))
            self.stdout.write("  Balance: {}".format(data.get('balance')))
            self.stdout.write("  Available: {}".format(data.get('available_balance')))
            self.stdout.write("  Credit Limit: {}".format(data.get('credit_limit')))
            self.stdout.write("  Segment Price: {}\n".format(data.get('segment_price')))

        except SignalBridgeException as e:
            raise CommandError("✗ {}".format(str(e)))
