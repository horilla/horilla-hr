"""
Settle existing components onto an explicit proration basis.

``maximum_unit`` used to be a dead field. It offered one option, "For working
days on month", it defaulted to that on every row, and the arithmetic that
would have acted on it was commented out inside ``compute_limit`` — so the
stored value described scaling that never happened.

Now that the basis is live, and now that it governs a fixed amount as well as a
ceiling, every one of those rows would suddenly start prorating: a flat
professional tax of 200 would drop to 72.73 on a ten-day payroll, because of a
setting nobody chose and which never did anything.

This puts them on ``full_period`` — a flat amount, the same in every period —
which is exactly what they have been paying all along. New components default
to prorating by calendar days instead; the difference is deliberate, because a
component created today was configured knowing the field works, and one created
before it did was not.

Run once after upgrading. It is safe to run again: it only touches rows still
carrying the old default, so an admin's later choice is never undone.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from payroll.methods.proration import FULL_PERIOD
from payroll.models.models import Allowance, Deduction

OLD_DEFAULT = "month_working_days"


class Command(BaseCommand):
    help = "Put components that never really prorated onto a flat basis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change and write nothing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total = 0

        with transaction.atomic():
            for model in (Allowance, Deduction):
                stale = model.objects.entire().filter(maximum_unit=OLD_DEFAULT)
                count = stale.count()
                total += count

                if count and not dry_run:
                    # update() on purpose: save() would fire the component's
                    # own logic, and this is a data correction, not an edit.
                    stale.update(maximum_unit=FULL_PERIOD)

                self.stdout.write(
                    f"{model.__name__}: {count} carried the old default"
                    + (" (unchanged)" if dry_run else " -> flat")
                )

            if dry_run:
                transaction.set_rollback(True)

        if not total:
            self.stdout.write(
                self.style.SUCCESS("Nothing to do; no component is on the old default.")
            )
        elif dry_run:
            self.stdout.write(self.style.WARNING(f"{total} rows would change."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"{total} rows settled on a flat basis.")
            )
