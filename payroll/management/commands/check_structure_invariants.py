"""
Report salary structures that cannot produce a coherent payslip.

The structure form now refuses a bad component set, and the engine refuses a bad
run, but neither helps with what is already stored: validation only fires on the
next edit, and a structure nobody touches keeps paying whatever it pays.

Read-only. It changes nothing, because there is no single right repair — a Gross
Up structure carrying a BASIC component might want that component removed or the
mode switched to CTC Down, and only whoever configured it knows which.

Migrations are gitignored project-wide, so a command is the vehicle for this kind
of one-off sweep, as with normalise_component_basis.
"""

from django.core.management.base import BaseCommand

from payroll.methods.structure_rules import structure_problems
from payroll.models.models import SalaryStructure


class Command(BaseCommand):
    help = "List salary structures whose components disagree with their mode."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet-ok",
            action="store_true",
            help="Only print the structures that have a problem.",
        )

    def handle(self, *args, **options):
        structures = (
            SalaryStructure.objects.entire()
            .prefetch_related("allowances", "deductions")
            .order_by("title")
        )

        affected = 0
        for structure in structures:
            allowances = list(structure.allowances.all())
            deductions = list(structure.deductions.all())
            problems = structure_problems(
                structure.structure_mode, allowances, deductions
            )

            if not problems:
                if not options["quiet_ok"]:
                    self.stdout.write(
                        f"  ok      {structure.title} "
                        f"({structure.structure_mode or 'gross_up'})"
                    )
                continue

            affected += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  PROBLEM {structure.title} "
                    f"({structure.structure_mode or 'gross_up'})"
                )
            )
            for problem in problems:
                self.stdout.write(f"            - {problem}")

            # Who is actually being paid by it, because that is what decides
            # how urgent the repair is.
            employees = structure.get_employees_col() if structure.pk else ""
            if employees:
                self.stdout.write(f"            employees: {employees}")

        total = structures.count()
        if affected:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{affected} of {total} structures need attention. "
                    "Nothing was changed."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nAll {total} structures are coherent.")
            )
