"""
audit_tour_translations — classify every Tour/TourStep as ready/not ready
for translation (i.e. whether an English TourTranslation/TourStepTranslation
already exists), with summary counts.

Usage:
    python manage.py audit_tour_translations                    # human output
    python manage.py audit_tour_translations --output audit.json
    python manage.py audit_tour_translations --only-not-ready
"""

import json

from django.core.management.base import BaseCommand

from horilla_tour.models import Tour, TourStep


class Command(BaseCommand):
    help = (
        "Audit every Tour/TourStep and classify it as ready/not ready for "
        "translation (has/doesn't have an English translation row). Read-only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", help="Write the structured JSON result to this file"
        )
        parser.add_argument(
            "--only-not-ready",
            action="store_true",
            help="Limit the printed listing to 'not ready' items",
        )

    def handle(self, *args, **options):
        tours = list(Tour.objects.all().order_by("id"))
        tour_steps = list(TourStep.objects.all().order_by("id"))

        tour_rows = [
            {
                "id": tour.id,
                "slug": tour.slug,
                "ready": tour.translations.filter(language="en").exists(),
            }
            for tour in tours
        ]
        step_rows = [
            {
                "id": step.id,
                "tour_slug": step.tour.slug,
                "sequence": step.sequence,
                "ready": step.translations.filter(language="en").exists(),
            }
            for step in tour_steps
        ]

        tours_ready = [row for row in tour_rows if row["ready"]]
        tours_not_ready = [row for row in tour_rows if not row["ready"]]
        steps_ready = [row for row in step_rows if row["ready"]]
        steps_not_ready = [row for row in step_rows if not row["ready"]]

        result = {
            "tours": {
                "ready": len(tours_ready),
                "not_ready": len(tours_not_ready),
                "total": len(tour_rows),
                "not_ready_items": [
                    {"id": row["id"], "slug": row["slug"]} for row in tours_not_ready
                ],
            },
            "tour_steps": {
                "ready": len(steps_ready),
                "not_ready": len(steps_not_ready),
                "total": len(step_rows),
                "not_ready_items": [
                    {
                        "id": row["id"],
                        "tour_slug": row["tour_slug"],
                        "sequence": row["sequence"],
                    }
                    for row in steps_not_ready
                ],
            },
        }

        self._print_human(tour_rows, step_rows, result, options["only_not_ready"])

        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=2, sort_keys=True)

    def _print_human(self, tour_rows, step_rows, result, only_not_ready):
        self.stdout.write("Tours:")
        for row in tour_rows:
            if only_not_ready and row["ready"]:
                continue
            label = "[PRONTO]     " if row["ready"] else "[NAO PRONTO]"
            self.stdout.write(f"  {label} {row['slug']} (id={row['id']})")

        self.stdout.write("Passos de tour:")
        for row in step_rows:
            if only_not_ready and row["ready"]:
                continue
            label = "[PRONTO]     " if row["ready"] else "[NAO PRONTO]"
            self.stdout.write(
                f"  {label} {row['tour_slug']} / passo {row['sequence']} (id={row['id']})"
            )

        self.stdout.write("")
        self.stdout.write("Resumo:")
        t = result["tours"]
        s = result["tour_steps"]
        self.stdout.write(
            f"  Tours:  {t['ready']} prontos / {t['not_ready']} não pronto / {t['total']} total"
        )
        self.stdout.write(
            f"  Passos: {s['ready']} prontos / {s['not_ready']} não prontos / {s['total']} total"
        )
