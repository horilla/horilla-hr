"""
Management command: seed_tax_packs

Loads ready-made income-tax configurations (India new/old regime, US federal,
UK PAYE, flat rate) as FilingStatus rows with their slabs and adjustments.

    python manage.py seed_tax_packs                 # load them all
    python manage.py seed_tax_packs --list          # show what is available
    python manage.py seed_tax_packs --pack in_new   # load specific ones

Idempotent: packs are keyed on name, so re-running never duplicates and never
overwrites an admin's edits to one they have already tuned.

The same packs are loadable from the Filing Status page, which is where most
people will reach for them; this exists for provisioning a new tenant without
clicking through the UI.
"""

from django.core.management.base import BaseCommand, CommandError

from payroll.tax_packs import TAX_PACKS, load_tax_packs


class Command(BaseCommand):
    help = "Load ready-made income-tax configurations for common jurisdictions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pack",
            action="append",
            dest="packs",
            help="Load only this pack (repeatable). Omit to load all.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List the available packs and exit.",
        )

    def handle(self, *args, **options):
        if options["list"]:
            for pack in TAX_PACKS:
                self.stdout.write(f"{pack['key']:<12} {pack['name']}")
            return

        keys = options["packs"]
        if keys:
            known = {pack["key"] for pack in TAX_PACKS}
            unknown = set(keys) - known
            if unknown:
                raise CommandError(
                    f"Unknown pack(s): {', '.join(sorted(unknown))}. "
                    f"Available: {', '.join(sorted(known))}"
                )

        created = load_tax_packs(keys)
        if not created:
            self.stdout.write(
                self.style.WARNING("Nothing loaded — those packs already exist.")
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(created)} pack(s):"))
        for name in created:
            self.stdout.write(f"  {name}")
        self.stdout.write(
            self.style.WARNING(
                "\nRates and thresholds change every year. Check each pack "
                "against the current finance act before anyone is paid by it."
            )
        )
