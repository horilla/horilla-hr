# Final step -- drop the old state_old_code CharField (its data is
# already copied into the new state FK by 0018) and re-add
# unique_together, now referring to the FK. Pure schema changes.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0018_populate_companystateregistration_state_fk'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='companystateregistration',
            name='state_old_code',
        ),
        migrations.AlterUniqueTogether(
            name='companystateregistration',
            unique_together={('company', 'state')},
        ),
    ]
