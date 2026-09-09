# Step 1 of 3 for converting CompanyStateRegistration.state from a plain
# CharField (GST code string) to a ForeignKey(GSTStateConfig). Split into
# separate migrations (schema-only / data-only / schema-only) because
# mixing DDL and DML on the same table in one migration's transaction
# has previously hit "cannot ALTER TABLE because it has pending trigger
# events" on Postgres for this project -- see base/migrations/0014 for
# the same pattern applied earlier.
#
# This step: drop the old unique_together (it references the field name
# "state", which is about to stop meaning "the CharField code") and
# rename the column out of the way so the real FK can take the "state"
# name in the next migration. Pure schema changes, no data touched.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('company_onboarding', '0015_gststateconfig'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='companystateregistration',
            unique_together=set(),
        ),
        migrations.RenameField(
            model_name='companystateregistration',
            old_name='state',
            new_name='state_old_code',
        ),
    ]
