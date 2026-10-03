"""
Payslips stored with more deducted than was earned.

The engine now caps total deductions at gross, and ``save_payslip`` refuses to
store more than that. Neither helps a payslip written before those existed: the
figure is already on the row, and because it is one field with many readers, it
shows up everywhere at once —

  * the payslip itself, where the column does not sum to its own total;
  * the run list and run detail, whose totals are a Sum over those rows;
  * the payroll dashboard, same Sum;
  * every export and report that names Deduction.

Which is why this is a command and not a patch in one of those views. Clamping
at the point of display would leave the stored figure wrong and make each
reader disagree with the next depending on whether it remembered to clamp.

    manage.py normalise_payslip_deductions            # report only
    manage.py normalise_payslip_deductions --fix      # write the corrections

The shortfall is not recorded against the old payslip: nothing was stored to
say which part of the deduction went uncollected, and inventing a split now
would be a guess. Regenerate the payslip if the breakdown matters.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from payroll.models.models import Payslip


class Command(BaseCommand):
    help = "Find (and optionally fix) payslips whose deductions exceed gross pay."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Write the corrections. Without it, nothing is changed.",
        )

    def handle(self, *args, **options):
        # entire(): this is a data repair, not a company-scoped report -- a
        # bad row in another company is still a wrong dashboard for someone.
        broken = Payslip.objects.entire().filter(deduction__gt=F("gross_pay"))
        total = broken.count()

        if not total:
            self.stdout.write(
                self.style.SUCCESS("No payslip deducts more than it pays.")
            )
            self._report_batches(fix=False)
            return

        self.stdout.write(f"{total} payslip(s) deduct more than they pay:\n")
        for payslip in broken.select_related("employee_id")[:50]:
            self.stdout.write(
                f"  {payslip.employee_id}  {payslip.start_date} to {payslip.end_date}  "
                f"gross {payslip.gross_pay:,.2f}  deduction {payslip.deduction:,.2f}  "
                f"(over by {payslip.deduction - payslip.gross_pay:,.2f})"
            )
        if total > 50:
            self.stdout.write(f"  ... and {total - 50} more")

        if not options["fix"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nNothing changed. Re-run with --fix to correct them."
                )
            )
            return

        with transaction.atomic():
            changed = broken.update(deduction=F("gross_pay"), net_pay=0.0)
        self.stdout.write(self.style.SUCCESS(f"\nCorrected {changed} payslip(s)."))

        self._report_batches(fix=True)

    def _report_batches(self, fix):
        """
        The runs those payslips belong to carry their own denormalised totals,
        so correcting the payslips does not by itself correct the run list.
        """
        from payroll.models.models import PayrollBatch

        batches = PayrollBatch.objects.entire()
        if not batches.exists():
            return

        if not fix:
            stale = [
                batch
                for batch in batches
                if round(batch.total_deductions, 2) > round(batch.total_gross, 2)
            ]
            if stale:
                self.stdout.write(
                    f"\n{len(stale)} payroll run(s) also show more deducted than paid; "
                    "--fix recomputes their totals."
                )
            return

        for batch in batches:
            batch.refresh_totals()
        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed totals on {batches.count()} payroll run(s)."
            )
        )
