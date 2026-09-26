from django.db import migrations


def backfill(apps, schema_editor):
    Tour = apps.get_model("horilla_tour", "Tour")
    TourStep = apps.get_model("horilla_tour", "TourStep")
    TourTranslation = apps.get_model("horilla_tour", "TourTranslation")
    TourStepTranslation = apps.get_model("horilla_tour", "TourStepTranslation")

    for tour in Tour.objects.all():
        TourTranslation.objects.update_or_create(
            tour=tour,
            language="en",
            defaults={"title": tour.title, "description": tour.description},
        )

    for tour_step in TourStep.objects.all():
        TourStepTranslation.objects.update_or_create(
            tour_step=tour_step,
            language="en",
            defaults={"title": tour_step.title, "description": tour_step.description},
        )


def unbackfill(apps, schema_editor):
    TourTranslation = apps.get_model("horilla_tour", "TourTranslation")
    TourStepTranslation = apps.get_model("horilla_tour", "TourStepTranslation")
    TourTranslation.objects.filter(language="en").delete()
    TourStepTranslation.objects.filter(language="en").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("horilla_tour", "0088_add_tour_translation_models"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
