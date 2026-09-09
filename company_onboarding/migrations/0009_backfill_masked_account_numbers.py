# Generated for the masked_account_number backfill.
"""
Backfills masked_account_number for rows that existed before the field
was added -- new rows get it automatically via CompanyBankDetails.save(),
but that never ran for rows already in the DB. Masking logic is inlined
here (not imported from company_onboarding.encryption) since migrations
should stay self-contained and not depend on app code that may change or
be removed later.
"""

from django.db import migrations


def _mask(value, visible=4):
    if not value:
        return ""
    if len(value) <= visible:
        return value
    return ("X" * (len(value) - visible)) + value[-visible:]


def backfill_masked_account_numbers(apps, schema_editor):
    CompanyBankDetails = apps.get_model("company_onboarding", "CompanyBankDetails")
    for row in CompanyBankDetails.objects.all():
        # row.account_number is already decrypted here -- EncryptedCharField's
        # from_db_value runs regardless of which model class reads it.
        row.masked_account_number = _mask(row.account_number)
        row.save(update_fields=["masked_account_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0008_companybankdetails_masked_account_number'),
    ]

    operations = [
        migrations.RunPython(backfill_masked_account_numbers, noop_reverse),
    ]
