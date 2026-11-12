from django.db import migrations

# The pivot fields as they were spelled, in the layouts people have saved.
RENAMED = {
    f"{role}Badge Id": f"{role}Badge ID"
    for role in (
        "",
        "Asset User ",
        "Assignee ",
        "Employee ",
        "Manager ",
        "Stage Manager ",
        "Task Manager ",
    )
}


def renamed(value, names):
    """The layout with each field renamed, wherever it names one."""
    if isinstance(value, dict):
        return {names.get(k, k): renamed(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [renamed(item, names) for item in value]
    if isinstance(value, str):
        return names.get(value, value)
    return value


def _rename_fields(apps, names):
    template_model = apps.get_model("report", "ReportTemplate")
    for template in template_model.objects.all():
        config = renamed(template.config, names)
        if config != template.config:
            template_model.objects.filter(pk=template.pk).update(config=config)


def forwards(apps, schema_editor):
    _rename_fields(apps, RENAMED)


def backwards(apps, schema_editor):
    _rename_fields(apps, {new: old for old, new in RENAMED.items()})


class Migration(migrations.Migration):

    dependencies = [
        ("report", "0004_alter_reportaccess_is_active_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
