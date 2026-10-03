"""
Bring already-generated rows into line with their standard component.

Every loan instalment, reimbursement, encashment and penalty created before
this existed took its tax treatment and proration basis from the model
defaults — is_taxable=True, is_pretax=True, calendar-day proration — because
the code that made them set neither. Those rows do not change when the
standard component is edited; only new ones read it.

This finds the disagreements and, with --apply, fixes them.

Rows already referenced by a payslip are never touched. A paid payslip is a
record of what someone was actually paid, and rewriting the component behind
it would make the stored figure unexplainable by its own inputs. So this only
moves rows that have not been paid yet — which does mean a future payslip can
differ from what it would have been, and is exactly why the default is to
report rather than to write.

    manage.py sync_system_components            # report only
    manage.py sync_system_components --apply    # write the changes
"""

from django.core.management.base import BaseCommand

from payroll.methods.deductions import LOAN_PAYOUT_KEYS, LOAN_REPAYMENT_KEYS
from payroll.models.models import (
    Allowance,
    Deduction,
    LoanAccount,
    Payslip,
    Reimbursement,
)
from payroll.system_components import editable_fields, policy_fields


def _paid_deduction_ids():
    """Deductions already carried on a payslip, by id."""
    return set(
        Payslip.objects.values_list("installment_ids__id", flat=True).exclude(
            installment_ids__id=None
        )
    )


def _rows_to_check():
    """
    Every generated row, paired with the key that should govern it.

    Walked from the owning records rather than from the components, because a
    component carries no mark saying which kind produced it — `is_loan` is set
    for both loans and advances and read by nothing, and a penalty's Deduction
    carries no marker at all. The owner is the only place the kind is known.
    """
    pairs = []

    for loan in LoanAccount.objects.entire().select_related("allowance_id"):
        payout_key = LOAN_PAYOUT_KEYS.get(loan.type)
        if payout_key and loan.allowance_id_id:
            pairs.append((loan.allowance_id, payout_key))

        repayment_key = LOAN_REPAYMENT_KEYS.get(loan.type)
        if repayment_key:
            for deduction in loan.deduction_ids.all():
                pairs.append((deduction, repayment_key))

    for claim in Reimbursement.objects.entire().select_related("allowance_id"):
        if claim.allowance_id_id:
            key = (
                claim.type
                if claim.type
                in {"reimbursement", "leave_encashment", "bonus_encashment"}
                else "reimbursement"
            )
            pairs.append((claim.allowance_id, key))

    return pairs


class Command(BaseCommand):
    help = "Align generated pay rows with their standard component."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the changes. Without it, only report them.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        paid = _paid_deduction_ids()

        changed = 0
        frozen = 0
        for row, key in _rows_to_check():
            if row is None or getattr(row, "is_system", False):
                continue

            wanted = policy_fields(key)
            differs = {
                field: value
                for field, value in wanted.items()
                if getattr(row, field) != value
            }
            if not differs:
                continue

            if isinstance(row, Deduction) and row.pk in paid:
                frozen += 1
                self.stdout.write(f"  frozen  {row.title}: on a payslip, left as it is")
                continue

            changed += 1
            detail = ", ".join(
                f"{field} {getattr(row, field)!r} -> {value!r}"
                for field, value in differs.items()
            )
            self.stdout.write(
                f"  {'set    ' if apply else 'would  '}{row.title}: {detail}"
            )

            if apply:
                for field, value in differs.items():
                    setattr(row, field, value)
                row.save(update_fields=list(differs))

        self.stdout.write("")
        if frozen:
            self.stdout.write(
                f"{frozen} row(s) left alone because a payslip already used them."
            )
        if not changed:
            self.stdout.write(self.style.SUCCESS("Everything already matches."))
        elif apply:
            self.stdout.write(self.style.SUCCESS(f"Updated {changed} row(s)."))
        else:
            self.stdout.write(
                f"{changed} row(s) differ. Re-run with --apply to write them."
            )

        # Stated every time, because the fields this moves decide whether a
        # deduction comes off before tax.
        self.stdout.write(
            "Fields governed: "
            + ", ".join(
                sorted(
                    {
                        f
                        for k in LOAN_REPAYMENT_KEYS.values()
                        for f in editable_fields(k)
                    }
                )
            )
        )
