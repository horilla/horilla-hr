# Generated for the account-number-at-rest-encryption change.
"""
Re-saves every existing CompanyBankDetails row so its account_number is
actually encrypted at rest. Before this runs, rows written prior to the
0006 AlterField still hold plaintext in the DB column -- EncryptedCharField
tolerates that on read (falls back to the raw value when it isn't valid
Fernet ciphertext, see company_onboarding/encryption.py), but the value
isn't genuinely encrypted until it's written back through the new field.

Uses the historical (apps.get_model) model deliberately, not the real
CompanyBankDetails class -- its custom save() override resets
verification_status to Pending whenever account_number "changes", which
would incorrectly fire here since every row's Python value differs from
its still-plaintext DB value at read time. The historical model has no
such override, so this is a silent re-encryption with no side effects.
"""

from django.db import migrations


def encrypt_existing_account_numbers(apps, schema_editor):
    CompanyBankDetails = apps.get_model("company_onboarding", "CompanyBankDetails")
    for row in CompanyBankDetails.objects.exclude(account_number__isnull=True).exclude(
        account_number=""
    ):
        row.save(update_fields=["account_number"])


def noop_reverse(apps, schema_editor):
    # Not reversible in a meaningful way (the "backwards" direction would
    # be to store plaintext again, which we don't want to automate).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0006_alter_companybankdetails_account_number'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_account_numbers, noop_reverse),
    ]
