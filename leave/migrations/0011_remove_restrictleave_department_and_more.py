"""RestrictLeave.department: ForeignKey -> ManyToManyField, keeping every restriction's department.

The first version of this migration was RemoveField + AddField, which dropped the department of every existing restriction (a freeze window with
no department restricts nobody). This version renames the old column, adds the many-to-many, copies each row's department across, and only then
drops the old column. The name and the final schema are unchanged, so a database that already applied the first version stays valid (its
restrictions had already lost their department and must be re-entered; nothing here can recover that).
"""
import django.db.models.deletion
from django.db import migrations, models


def copy_department_to_m2m(apps, schema_editor):
    RestrictLeave = apps.get_model("leave", "RestrictLeave")
    Through = RestrictLeave.department.through
    db = schema_editor.connection.alias
    rows = (
        RestrictLeave.objects.using(db)
        .exclude(department_old__isnull=True)
        .values_list("pk", "department_old_id")
    )
    Through.objects.using(db).bulk_create(
        [
            Through(restrictleave_id=pk, department_id=department_id)
            for pk, department_id in rows
        ],
        ignore_conflicts=True,
    )


def copy_m2m_back_to_department(apps, schema_editor):
    """Reverse: the old column holds one department, so a restriction with several keeps the first one (lowest id)."""
    RestrictLeave = apps.get_model("leave", "RestrictLeave")
    Through = RestrictLeave.department.through
    db = schema_editor.connection.alias
    first = {}
    for restrictleave_id, department_id in (
        Through.objects.using(db)
        .order_by("department_id")
        .values_list("restrictleave_id", "department_id")
    ):
        first.setdefault(restrictleave_id, department_id)
    for pk, department_id in first.items():
        RestrictLeave.objects.using(db).filter(pk=pk).update(
            department_old_id=department_id
        )


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0021_penaltyaccounts_additional_info_and_more"),
        ("leave", "0010_historicalleaverequest_cancellation_requested_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="restrictleave", old_name="department", new_name="department_old"
        ),
        # nullable while both exist, so the reverse (which re-adds this column) also works on a table that has rows
        migrations.AlterField(
            model_name="restrictleave",
            name="department_old",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="base.department",
                verbose_name="Department",
            ),
        ),
        migrations.AddField(
            model_name="restrictleave",
            name="department",
            field=models.ManyToManyField(
                related_name="restrict_leaves",
                to="base.department",
                verbose_name="Department",
            ),
        ),
        migrations.RunPython(copy_department_to_m2m, copy_m2m_back_to_department),
        migrations.RemoveField(model_name="restrictleave", name="department_old"),
    ]
