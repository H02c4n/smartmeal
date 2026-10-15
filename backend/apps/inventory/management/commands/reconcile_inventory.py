from django.core.management.base import BaseCommand, CommandError

from apps.inventory import selectors


class Command(BaseCommand):
    help = (
        "Check that lot balances match the stock ledger and active reservations. "
        "Exits with an error if any lot is inconsistent."
    )

    def handle(self, *args, **options):
        problems = selectors.reconcile()
        if not problems:
            self.stdout.write(self.style.SUCCESS("Inventory is consistent."))
            return
        for problem in problems:
            self.stderr.write(
                f"{problem['lot']}: on_hand={problem['on_hand']} "
                f"vs ledger={problem['ledger_total']}; reserved={problem['reserved']} "
                f"vs reservations={problem['active_reservations_total']}"
            )
        raise CommandError(f"{len(problems)} inconsistent lot(s).")
