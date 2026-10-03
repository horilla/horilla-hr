"""
Management command: backfill_component_sequence

Gives existing allowances and deductions the evaluation order they already had
implicitly, so adding `sequence` does not reshuffle anyone's payslip.

Why a command and not a data migration: this repo gitignores migrations
(.gitignore, "# migration files"), so every environment regenerates the schema
from the models with makemigrations — which reproduces a column, but never a
RunPython backfill. A migration here would exist only on the machine that wrote
it. This runs once per environment after migrating, and is idempotent.

What order is being preserved: payroll's old gatherer collected taxable
allowances into one list and non-taxable into another, then concatenated them.
That put every taxable allowance ahead of every non-taxable one in
pay_head_data["allowances"] — an artifact of the two-list implementation rather
than a decision, but a visible one, since payslip templates iterate that list.
Spacing the two groups at 100 and 200 reproduces it exactly while leaving room
to slot components between them.

Deductions keep a flat 100: they are already partitioned into their phases by
is_pretax / is_tax, so sequence plus pk reproduces the existing per-phase order.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from payroll.models.models import Allowance, Deduction, derive_component_code


class Command(BaseCommand):
    help = "Set evaluation sequence on existing allowances/deductions to preserve today's order"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        taxable = Allowance.objects.filter(is_taxable=True).exclude(sequence=100)
        untaxed = Allowance.objects.filter(is_taxable=False).exclude(sequence=200)
        deductions = Deduction.objects.exclude(sequence=100)

        self.stdout.write(f"taxable allowances to set to 100 : {taxable.count()}")
        self.stdout.write(f"non-taxable allowances to set 200: {untaxed.count()}")
        self.stdout.write(f"deductions to set to 100         : {deductions.count()}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
            return

        # Codes are derived from titles so nobody has to invent one, but that
        # only happens on save — existing rows predate it.
        missing_codes = 0
        for model in (Allowance, Deduction):
            for component in model.objects.filter(code=""):
                component.code = derive_component_code(
                    model, component.title, exclude_pk=component.pk
                )
                component.save(update_fields=["code"])
                missing_codes += 1
        self.stdout.write(f"components given a derived code   : {missing_codes}")

        with transaction.atomic():
            # .update() deliberately: this must not fire save(), which would
            # stamp modified_by and rewrite history rows for every component in
            # the database on what is purely a data-shape migration.
            changed = (
                taxable.update(sequence=100)
                + untaxed.update(sequence=200)
                + deductions.update(sequence=100)
            )

        self.stdout.write(self.style.SUCCESS(f"Updated {changed} component(s)."))
