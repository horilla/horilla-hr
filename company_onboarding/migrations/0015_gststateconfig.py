# GSTStateConfig: DB-backed config table for India's GST state codes,
# replacing the hardcoded list that used to live in gst_states.py.
# Seeded here from the same CBIC GST state code list.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_STATES = [
    ("01", "Jammu and Kashmir"),
    ("02", "Himachal Pradesh"),
    ("03", "Punjab"),
    ("04", "Chandigarh"),
    ("05", "Uttarakhand"),
    ("06", "Haryana"),
    ("07", "Delhi"),
    ("08", "Rajasthan"),
    ("09", "Uttar Pradesh"),
    ("10", "Bihar"),
    ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"),
    ("13", "Nagaland"),
    ("14", "Manipur"),
    ("15", "Mizoram"),
    ("16", "Tripura"),
    ("17", "Meghalaya"),
    ("18", "Assam"),
    ("19", "West Bengal"),
    ("20", "Jharkhand"),
    ("21", "Odisha"),
    ("22", "Chhattisgarh"),
    ("23", "Madhya Pradesh"),
    ("24", "Gujarat"),
    ("26", "Dadra and Nagar Haveli and Daman and Diu"),
    ("27", "Maharashtra"),
    ("29", "Karnataka"),
    ("30", "Goa"),
    ("31", "Lakshadweep"),
    ("32", "Kerala"),
    ("33", "Tamil Nadu"),
    ("34", "Puducherry"),
    ("35", "Andaman and Nicobar Islands"),
    ("36", "Telangana"),
    ("37", "Andhra Pradesh"),
    ("38", "Ladakh"),
]


def seed_gst_states(apps, schema_editor):
    GSTStateConfig = apps.get_model("company_onboarding", "GSTStateConfig")
    GSTStateConfig.objects.bulk_create(
        [GSTStateConfig(code=code, name=name) for code, name in _STATES]
    )


def unseed_gst_states(apps, schema_editor):
    GSTStateConfig = apps.get_model("company_onboarding", "GSTStateConfig")
    GSTStateConfig.objects.filter(code__in=[code for code, _ in _STATES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0014_alter_companybankdetails_verification_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GSTStateConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True, verbose_name='Created At')),
                ('code', models.CharField(max_length=2, unique=True, verbose_name='GST State Code')),
                ('name', models.CharField(max_length=100, verbose_name='State / UT Name')),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('modified_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Modified By')),
            ],
            options={
                'verbose_name': 'GST State',
                'verbose_name_plural': 'GST States',
                'ordering': ['code'],
            },
        ),
        migrations.RunPython(seed_gst_states, unseed_gst_states),
    ]
