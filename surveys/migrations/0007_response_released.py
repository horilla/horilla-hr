"""Add SurveyResponse.released and release the answers already shown.

Until now an anonymous survey showed all its answers once it was closed. Those
answers count as released, as long as there are enough of them (the same minimum
as the survey itself uses); answers of an open survey wait for its next close.
"""

from django.conf import settings
from django.db import migrations, models


def release_closed_anonymous(apps, schema_editor):
    Survey = apps.get_model("surveys", "Survey")
    SurveyResponse = apps.get_model("surveys", "SurveyResponse")
    minimum = max(1, int(getattr(settings, "SURVEYS_MIN_RESPONSES", 5)))
    closed = Survey._base_manager.filter(is_anonymous=True, status="closed")
    for survey in closed.iterator():
        submitted = SurveyResponse._base_manager.filter(survey=survey, is_draft=False)
        if submitted.count() >= minimum:
            submitted.update(released=True)


class Migration(migrations.Migration):
    dependencies = [("surveys", "0006_managers_help_text")]

    operations = [
        migrations.AddField(
            model_name="surveyresponse",
            name="released",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(release_closed_anonymous, migrations.RunPython.noop),
    ]
