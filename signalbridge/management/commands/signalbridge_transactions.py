"""Management command to view transaction history"""
from django.core.management.base import BaseCommand, CommandError
from signalbridge.client import get_client
from signalbridge.exceptions import SignalBridgeException


class Command(BaseCommand):
    help = 'View SignalBridge transaction history'

    def add_arguments(self, parser):
        parser.add_argument('--page', type=int, default=1, help='Page number')
        parser.add_argument('--per-page', type=int, default=15, help='Results per page')
        parser.add_argument('--type', type=str, help='Transaction type filter')

    def handle(self, *args, **options):
        client = get_client()

        try:
            result = client.get_transactions(
                page=options['page'],
                per_page=options['per_page'],
                transaction_type=options.get('type')
            )

            data = result['data']
            transactions = data['data']

            self.stdout.write(self.style.SUCCESS('\nTransaction History\n'))

            for txn in transactions:
                type_emoji = '💸' if txn['type'] == 'debit' else '💰'
                self.stdout.write(
                    f"  {type_emoji} {txn['type'].upper()}: {txn['amount']} "
                    f"({txn['description']}) - {txn['created_at']}"
                )

            self.stdout.write(f"\nPage {data['current_page']} of {data['last_page']}\n")

        except SignalBridgeException as e:
            raise CommandError(f"✗ {str(e)}")
