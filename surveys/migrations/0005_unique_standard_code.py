from django.db import migrations, models


def blank_duplicate_codes(apps, schema_editor):
    """Keep the first questionnaire of each standard code; the copies become plain ones.

    Nothing is deleted: a duplicate keeps its questions and title, it just stops
    claiming to be the standard one, so the unique constraint can be added.
    """
    Questionnaire = apps.get_model("surveys", "Questionnaire")
    seen = set()
    for row in Questionnaire._base_manager.exclude(code="").order_by("pk"):
        if row.code in seen:
            Questionnaire._base_manager.filter(pk=row.pk).update(code="")
        else:
            seen.add(row.code)


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0004_survey_anonymous_help_text"),
    ]

    operations = [
        migrations.RunPython(blank_duplicate_codes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="questionnaire",
            constraint=models.UniqueConstraint(
                condition=models.Q(("code", ""), _negated=True),
                fields=("code",),
                name="surveys_questionnaire_unique_code",
            ),
        ),
    ]
