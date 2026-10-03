"""
Management command: payroll_snapshot

Dumps what ``payroll_calculation()`` currently produces for every employee with
an active contract, without creating a single Payslip row.

This is the second half of the payroll engine safety net. The golden suite
(payroll/tests/test_payroll_calculation_golden.py) proves the engine is stable
for the configurations it models; this proves it for the configurations a real
tenant actually has — condition-based components, unusual wage types, overlapping
structures, whatever is out there that no fixture thought to build.

Usage, either side of an engine change:

    python manage.py payroll_snapshot --start 2026-08-01 --end 2026-08-31 --out before.json
    ...make the change...
    python manage.py payroll_snapshot --start 2026-08-01 --end 2026-08-31 --out after.json
    python manage.py payroll_snapshot --diff before.json after.json

Read-only by construction: it calls the engine and serialises the result. The
engine itself never persists — ``save_payslip()`` is a separate step the
generation views call, and this command does not call it.
"""

import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Contract, Payslip


def _parse_date(text, label):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise CommandError(f"--{label} must be YYYY-MM-DD, got {text!r}") from exc


class Command(BaseCommand):
    help = "Snapshot payroll_calculation() output for every active contract (creates nothing)"

    def add_arguments(self, parser):
        parser.add_argument("--start", help="Period start, YYYY-MM-DD")
        parser.add_argument("--end", help="Period end, YYYY-MM-DD")
        parser.add_argument("--out", help="Write the snapshot to this path")
        parser.add_argument(
            "--diff",
            nargs=2,
            metavar=("BEFORE", "AFTER"),
            help="Compare two snapshots instead of taking one",
        )

    def handle(self, *args, **options):
        if options["diff"]:
            return self._diff(*options["diff"])

        for required in ("start", "end", "out"):
            if not options[required]:
                raise CommandError(f"--{required} is required (or use --diff)")

        start = _parse_date(options["start"], "start")
        end = _parse_date(options["end"], "end")
        if end < start:
            raise CommandError("--end is before --start")

        payslips_before = Payslip.objects.count()
        contracts = Contract.objects.filter(contract_status="active").select_related(
            "employee_id"
        )

        snapshot, skipped = {}, []
        for contract in contracts:
            employee = contract.employee_id
            key = f"{employee.pk}:{employee.get_full_name()}"
            try:
                data = payroll_calculation(employee, start, end)
            except (
                Exception
            ) as exc:  # noqa: BLE001 - a snapshot must survive one bad row
                skipped.append((key, f"{type(exc).__name__}: {exc}"))
                continue
            if not data:
                skipped.append((key, "no basic pay details"))
                continue
            snapshot[key] = json.loads(data["json_data"])

        payslips_after = Payslip.objects.count()
        if payslips_after != payslips_before:
            raise CommandError(
                "payroll_snapshot created Payslip rows "
                f"({payslips_before} -> {payslips_after}); this command must be read-only"
            )

        with open(options["out"], "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True, default=str)

        self.stdout.write(
            self.style.SUCCESS(
                f"Snapshotted {len(snapshot)} employee(s) to {options['out']}"
            )
        )
        for key, reason in skipped:
            self.stdout.write(self.style.WARNING(f"  skipped {key}: {reason}"))

    def _diff(self, before_path, after_path):
        with open(before_path, encoding="utf-8") as handle:
            before = json.load(handle)
        with open(after_path, encoding="utf-8") as handle:
            after = json.load(handle)

        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])

        for key in removed:
            self.stdout.write(self.style.ERROR(f"- {key} (no longer computes)"))
        for key in added:
            self.stdout.write(self.style.WARNING(f"+ {key} (newly computes)"))
        for key in changed:
            self.stdout.write(self.style.ERROR(f"~ {key}"))
            for field in sorted(set(before[key]) | set(after[key])):
                old, new = before[key].get(field), after[key].get(field)
                if old != new:
                    self.stdout.write(f"    {field}: {old!r} -> {new!r}")

        if not (added or removed or changed):
            self.stdout.write(
                self.style.SUCCESS(f"No change across {len(before)} employee(s)")
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(changed)} changed, {len(added)} added, {len(removed)} removed"
                )
            )
