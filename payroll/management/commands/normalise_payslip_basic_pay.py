"""
Payslips that store their basic pay twice.

Under a CTC Down structure basic pay is one of the components dividing up the
package, and the engine used to store it in two places at once: as the
payslip's own ``basic_pay``, and again as that component's row inside
``pay_head_data["allowances"]``. It is one figure, so nothing was wrong with
the money -- gross was computed from the rows and basic was deliberately held
out of that sum -- but every reader of the stored rows saw it twice:

  * the payslip page and the PDF, which print basic pay and then the rows
    under it, so "Basic Pay" appeared on two lines;
  * the payslip component editor, which treats every earning as a line and so
    added basic into gross a second time -- its preview read 96,600 against a
    payslip whose gross was 69,000.

The engine now leaves the row out, so allowances mean the same thing in both
structure modes: the earnings on top of basic pay. This repairs the payslips
written before that.

    manage.py normalise_payslip_basic_pay            # report only
    manage.py normalise_payslip_basic_pay --fix      # write the corrections

No figure moves. The row is removed and nothing else is touched, because gross,
basic, deductions and net were all already right -- the duplication was in what
was stored beside them, not in the arithmetic.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from payroll.models.models import Allowance, Payslip

TOLERANCE = 0.01


def duplicate_row_index(payslip, basic_pay_ids):
    """
    Which row of ``allowances`` is this payslip's basic pay, if any.

    Decided from the record itself rather than from the contract, which may
    have been moved to another structure since. Gross is the rows alone only
    when basic pay is one of them -- in every other payslip gross is basic
    plus the rows -- so that sum is what says whether a duplicate is even
    possible, before any row is looked at.
    """
    data = payslip.pay_head_data or {}
    rows = data.get("allowances") or []
    basic = round(float(payslip.basic_pay or 0), 2)
    if not rows or basic <= 0:
        return None

    total = round(sum(float(row.get("amount") or 0) for row in rows), 2)
    if abs(total - round(float(payslip.gross_pay or 0), 2)) > TOLERANCE:
        return None

    for index, row in enumerate(rows):
        if row.get("allowance_id") in basic_pay_ids and (
            abs(float(row.get("amount") or 0) - basic) <= TOLERANCE
        ):
            return index

    # The flag can be turned off a component after the payslips it made. The
    # amount then has to identify the row, which is only safe while exactly
    # one of them matches -- two rows at the same figure and there is no way
    # to tell which was the basic one.
    matches = [
        index
        for index, row in enumerate(rows)
        if abs(float(row.get("amount") or 0) - basic) <= TOLERANCE
    ]
    return matches[0] if len(matches) == 1 else None


class Command(BaseCommand):
    help = "Find (and optionally fix) payslips that list basic pay twice."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Write the corrections. Without it, nothing is changed.",
        )

    def handle(self, *args, **options):
        # entire(): a data repair, not a company-scoped report. A payslip
        # reading wrong in another company is still a payslip reading wrong.
        basic_pay_ids = set(
            Allowance.objects.entire()
            .filter(is_basic_pay=True)
            .values_list("pk", flat=True)
        )

        affected = []
        for payslip in Payslip.objects.entire().select_related("employee_id"):
            index = duplicate_row_index(payslip, basic_pay_ids)
            if index is not None:
                affected.append((payslip, index))

        if not affected:
            self.stdout.write(
                self.style.SUCCESS("No payslip lists its basic pay twice.")
            )
            return

        self.stdout.write(f"{len(affected)} payslip(s) list basic pay twice:\n")
        for payslip, index in affected[:50]:
            row = payslip.pay_head_data["allowances"][index]
            self.stdout.write(
                f"  {payslip.employee_id}  {payslip.start_date} to {payslip.end_date}  "
                f"basic {payslip.basic_pay:,.2f}  also listed as "
                f"{row.get('title') or '(untitled)'}"
            )
        if len(affected) > 50:
            self.stdout.write(f"  ... and {len(affected) - 50} more")

        if not options["fix"]:
            self.stdout.write(
                "\nNothing changed. Re-run with --fix to remove the duplicate rows."
            )
            return

        with transaction.atomic():
            for payslip, index in affected:
                data = dict(payslip.pay_head_data)
                rows = list(data.get("allowances") or [])
                removed = rows.pop(index)
                data["allowances"] = rows
                # Which component worked basic pay out, now that its row is
                # gone. The engine records this on every payslip it writes,
                # and it is what lets the payslip editor say "50% of CTC"
                # beside the figure instead of presenting it as a flat number.
                data["basic_pay_component_id"] = removed.get("allowance_id")
                payslip.pay_head_data = data
                payslip.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nRemoved the duplicate row from {len(affected)} payslip(s)."
            )
        )
