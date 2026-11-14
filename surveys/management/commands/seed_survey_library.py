"""manage.py seed_survey_library - the standard questionnaires into the library."""

from django.core.management.base import BaseCommand

from surveys.library import load_standard


class Command(BaseCommand):
    help = "Add the standard questionnaires (eNPS, engagement, new hire) the survey library lacks."

    def handle(self, *args, **options):
        added = load_standard()
        for questionnaire in added:
            self.stdout.write(f"added: {questionnaire.title}")
        self.stdout.write(self.style.SUCCESS(f"{len(added)} questionnaire(s) added."))
