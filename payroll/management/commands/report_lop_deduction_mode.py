"""
Which contracts still take loss of pay as a separate deduction.

"Take Loss Of Pay Off Basic Pay" is no longer on the contract form — where
loss of pay comes off now follows from "Daily Leave Amount From", since a day
is a share of basic pay and therefore comes off basic pay.

The field was not deleted, because a contract set to False behaves genuinely
differently: basic pay is left whole and loss of pay is deducted afterwards,
which also means it does NOT reduce taxable gross. Dropping the field would
have switched those contracts silently, moving their tax.

So they keep their behaviour and this reports them. Run it to see whether any
are left, and pass --normalise to bring them in line with the rest.
"""

from django.core.management.base import BaseCommand

from payroll.models.models import Contract


class Command(BaseCommand):
    help = "Report contracts that deduct loss of pay separately from basic pay."

    def add_arguments(self, parser):
        parser.add_argument(
            "--normalise",
            action="store_true",
            help="Switch them to taking loss of pay off basic pay.",
        )

    def handle(self, *args, **options):
        odd = Contract.objects.entire().filter(deduct_leave_from_basic_pay=False)

        if not odd.exists():
            self.stdout.write(
                self.style.SUCCESS("Every contract takes loss of pay off basic pay.")
            )
            return

        self.stdout.write(
            f"{odd.count()} contract(s) deduct loss of pay separately, so it "
            "does not reduce their taxable gross:"
        )
        for contract in odd:
            self.stdout.write(f"  {contract.employee_id} — {contract.contract_name}")

        if not options["normalise"]:
            self.stdout.write("")
            self.stdout.write(
                "Re-run with --normalise to switch them. That lowers their "
                "taxable gross, so it changes tax on future payslips."
            )
            return

        count = odd.update(deduct_leave_from_basic_pay=True)
        self.stdout.write(self.style.SUCCESS(f"Switched {count} contract(s)."))
