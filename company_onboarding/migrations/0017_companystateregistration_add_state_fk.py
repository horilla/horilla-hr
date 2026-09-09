# Step 2 of 3 -- add the real FK field under the name "state". Pure
# schema change, no data touched (nullable, so this can't fail on
# existing rows).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0016_companystateregistration_rename_state_column'),
    ]

    operations = [
        migrations.AddField(
            model_name='companystateregistration',
            name='state',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'is_active': True},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='state_registrations',
                to='company_onboarding.gststateconfig',
                verbose_name='State',
            ),
        ),
    ]
