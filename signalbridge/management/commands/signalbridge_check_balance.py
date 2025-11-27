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
            data = result['data']

            self.stdout.write(self.style.SUCCESS('\nBalance Summary\n'))
            self.stdout.write(f"  Currency: {data['currency']}")
            self.stdout.write(f"  Balance: {data['balance']}")
            self.stdout.write(f"  Credit Limit: {data['credit_limit']}")
            self.stdout.write(f"  Segment Price: {data['segment_price']}\n")

        except SignalBridgeException as e:
            raise CommandError(f"✗ {str(e)}")
