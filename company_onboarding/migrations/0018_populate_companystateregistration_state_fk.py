# Step 3 of 3 (data) -- populate the new state FK from the old
# state_old_code values, matching against GSTStateConfig.code. Pure
# data migration, no schema touched.

from django.db import migrations


def populate_state_fk(apps, schema_editor):
    CompanyStateRegistration = apps.get_model("company_onboarding", "CompanyStateRegistration")
    GSTStateConfig = apps.get_model("company_onboarding", "GSTStateConfig")
    codes = {s.code: s for s in GSTStateConfig.objects.all()}
    for row in CompanyStateRegistration.objects.exclude(
        state_old_code__isnull=True
    ).exclude(state_old_code=""):
        state = codes.get(row.state_old_code)
        if state is not None:
            row.state = state
            row.save(update_fields=["state"])


def reverse_populate_state_fk(apps, schema_editor):
    CompanyStateRegistration = apps.get_model("company_onboarding", "CompanyStateRegistration")
    for row in CompanyStateRegistration.objects.exclude(state__isnull=True):
        row.state_old_code = row.state.code
        row.save(update_fields=["state_old_code"])


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0017_companystateregistration_add_state_fk'),
    ]

    operations = [
        migrations.RunPython(populate_state_fk, reverse_populate_state_fk),
    ]
