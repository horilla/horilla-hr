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

from payroll.methods.deductions import LOAN_REPAYMENT_KEYS
from payroll.methods.system_sync import align
from payroll.system_components import editable_fields


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
        # Reported before the write, so the old values can still be read off each row.
        changes, frozen_rows = align(apply=False)
        for row, differs in changes:
            detail = ", ".join(
                f"{field} {getattr(row, field)!r} -> {value!r}"
                for field, value in differs.items()
            )
            self.stdout.write(
                f"  {'set    ' if apply else 'would  '}{row.title}: {detail}"
            )
        for row in frozen_rows:
            self.stdout.write(f"  frozen  {row.title}: on a payslip, left as it is")
        if apply:
            align(apply=True)
        changed, frozen = len(changes), len(frozen_rows)

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
