"""
Seed the "Default Export Access" rows, and collapse any duplicates.

Migration 0015 added the uniqueness constraints but the two data steps that
belong with them were lost when this change was ported: the per-company seed
and the dedupe that has to run *before* a uniqueness constraint can be
applied to a table that may already contain duplicates.

Without the seed, `has_export_access` falls back to "no row means enabled",
which is the permissive-by-absence behaviour 0015 set out to remove -- the
setting is invisible in the UI until an admin happens to toggle it. The
`base.tests.test_export_permission_seeding` suite asserts the seeded rows and
has been failing on this branch since 0015 landed.

Dedupe runs first here for installs that predate 0015 and could not have had
the constraints enforced yet. Where 0015 already applied cleanly it is a no-op.
"""

from django.db import migrations


def dedupe(apps, schema_editor):
    """
    Collapse duplicate rows, keeping the most restrictive per company.

    Every reader does .filter(company_id=...).first(), so a duplicate row
    silently decided the setting by insertion order. If an admin ever
    disabled export access, honour that rather than letting a stray enabled
    row re-open it.
    """
    DefaultExportPermission = apps.get_model("base", "DefaultExportPermission")
    seen = {}
    for row in DefaultExportPermission.objects.order_by("id"):
        key = row.company_id_id
        if key not in seen:
            seen[key] = row
            continue
        keeper = seen[key]
        if not row.is_enabled and keeper.is_enabled:
            keeper.is_enabled = False
            keeper.save(update_fields=["is_enabled"])
        row.delete()


def seed_rows(apps, schema_editor):
    """
    Give every company an explicit row, preserving today's behaviour.

    Flipping the default to deny would silently remove export access from
    installs relying on it, with no UI hint why. The point is to make the
    value visible and deliberate, not to change it.
    """
    Company = apps.get_model("base", "Company")
    DefaultExportPermission = apps.get_model("base", "DefaultExportPermission")

    existing = set(DefaultExportPermission.objects.values_list("company_id", flat=True))
    missing = [
        cid
        for cid in Company.objects.values_list("id", flat=True)
        if cid not in existing
    ]
    DefaultExportPermission.objects.bulk_create(
        [
            DefaultExportPermission(company_id_id=cid, is_enabled=True)
            for cid in missing
        ],
        batch_size=500,
    )

    # company_id=None is what has_export_access() looks up when the session
    # scope is "All companies", so it needs a row of its own.
    if None not in existing:
        DefaultExportPermission.objects.create(company_id=None, is_enabled=True)


def noop(apps, schema_editor):
    """
    Deliberately a no-op.

    Removing the rows would restore the implicit default rather than any
    prior explicit state, and nothing records which rows this migration
    created versus which an admin had already set.
    """


class Migration(migrations.Migration):

    dependencies = [
        (
            "base",
            "0015_defaultexportpermission_unique_default_export_permission_per_company_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(dedupe, noop),
        migrations.RunPython(seed_rows, noop),
    ]
