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

            # The gateway returns a paginated resource collection: the rows sit
            # under 'data' and the page counters under 'meta'. This command used
            # to read result['data']['data'] and crash on a list.
            transactions = result.get('data') or []
            meta = result.get('meta') or {}

            self.stdout.write(self.style.SUCCESS('\nTransaction History\n'))

            if not transactions:
                self.stdout.write('  No transactions found.\n')
                return

            for txn in transactions:
                type_emoji = '💸' if txn.get('type') == 'debit' else '💰'
                self.stdout.write(
                    "  {} {}: {} {} ({}) - {}".format(
                        type_emoji,
                        str(txn.get('type', '')).upper(),
                        txn.get('amount'),
                        txn.get('currency', ''),
                        txn.get('description'),
                        txn.get('created_at'),
                    )
                )

            current_page = meta.get('current_page', options['page'])
            last_page = meta.get('last_page', '?')

            self.stdout.write("\nPage {} of {}\n".format(current_page, last_page))

        except SignalBridgeException as e:
            raise CommandError("✗ {}".format(str(e)))
