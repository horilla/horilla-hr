"""Remove from anonymous responses what could point at the person who wrote them.

The first version of the module stamped the logged-in respondent on the response
(created_by, modified_by) and gave the response and its invitation the same exact
submission time. Both are removed for every submitted response of an anonymous
survey: the people are forgotten, the times are cut back to the day.

There is no way back: the data is destroyed on purpose.
"""

from django.db import migrations
from django.utils import timezone


def _midnight(moment):
    return timezone.localtime(moment).replace(hour=0, minute=0, second=0, microsecond=0)


def scrub_anonymous_responses(apps, schema_editor):
    SurveyResponse = apps.get_model("surveys", "SurveyResponse")
    SurveyInvitation = apps.get_model("surveys", "SurveyInvitation")

    submitted = SurveyResponse._base_manager.filter(
        survey__is_anonymous=True, is_draft=False
    )
    for response in submitted.iterator():
        moment = response.submitted_at or response.created_at or response.started_at
        fields = {"created_by": None, "modified_by": None}
        if moment is not None:
            day = _midnight(moment)
            fields.update(created_at=day, started_at=day, submitted_at=day)
        SurveyResponse._base_manager.filter(pk=response.pk).update(**fields)

    answered = SurveyInvitation._base_manager.filter(
        survey__is_anonymous=True, submitted_at__isnull=False
    )
    for invitation in answered.iterator():
        SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
            submitted_at=_midnight(invitation.submitted_at)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0002_survey_library"),
    ]

    operations = [
        migrations.RunPython(scrub_anonymous_responses, migrations.RunPython.noop),
    ]
