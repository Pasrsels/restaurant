from django.core.management.base import BaseCommand
from finance.models import Change
from collections import defaultdict
from django.utils import timezone
from datetime import datetime

def remove_duplicate_change_transactions(dry_run=False):
    today = timezone.localdate() if hasattr(timezone, 'localdate') else datetime.now().date()
    transactions = Change.objects.filter(timestamp__date=datetime.today()) 

    grouped = defaultdict(list)
    for tx in transactions:
        key = (tx.name.strip().lower(), float(tx.amount))
        grouped[key].append(tx)

    removed_count = 0
    would_remove = []
    kept_transactions = [] 

    for key, tx_list in grouped.items():
        collected_txs = [tx for tx in tx_list if tx.collected]
        not_collected_txs = [tx for tx in tx_list if not tx.collected]

        if collected_txs:
            to_keep = collected_txs[0]
        else:
            to_keep = not_collected_txs[0]

        kept_transactions.append(to_keep)  

        for tx in tx_list:
            if tx.id != to_keep.id:
                if dry_run:
                    would_remove.append(tx)
                else:
                    tx.delete()
                    removed_count += 1

    print("\n--- Transactions Kept After Removing Duplicates ---\n")
    for tx in kept_transactions:
        print(f"id={tx.id}, name='{tx.name}', amount={tx.amount}, collected={tx.collected}")

    # if dry_run:
    #     print(f"\n[DRY RUN] Would remove {len(would_remove)} duplicates:")
    #     for tx in would_remove:
    #         print(f"  id={tx.id}, name='{tx.name}', amount={tx.amount}, collected={tx.collected}")
    # else:
    #     print(f"\nRemoved {removed_count} duplicate transactions.")

class Command(BaseCommand):
    help = "Remove duplicate Change transactions for today, keeping one (prioritize collected=True)."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Simulate deletions without applying them.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        remove_duplicate_change_transactions(dry_run=dry_run)
