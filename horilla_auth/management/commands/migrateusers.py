from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from horilla_auth.models import (
    AuthUserGroups,
    AuthUserUserPermissions,
    HorillaUser,
    LegacyUser,
)


class Command(BaseCommand):
    help = "Migrate users from LegacyUser (auth_user) to HorillaUser, including groups and permissions."

    def handle(self, *args, **options):
        # LegacyUser and its two join models are unmanaged views onto v1's
        # auth_user tables. Django never creates or validates them, so their
        # absence is not noticed until the first query, which then raises
        # ProgrammingError: relation "auth_user" does not exist.
        #
        # They are absent in two ordinary situations:
        #
        #   - a fresh v2 install, which never had a v1 database
        #   - a database already upgraded from v1, where the users have been
        #     carried over and there is nothing left to copy
        #
        # Both are a no-op rather than an error, so report and exit cleanly
        # rather than surfacing a traceback.
        if not self._legacy_tables_present():
            self.stdout.write(
                self.style.SUCCESS(
                    "Nothing to migrate: no legacy auth_user table found. This is "
                    "expected on a fresh install, or where the users have already "
                    "been carried over."
                )
            )
            return

        created_count = 0
        skipped_count = 0

        with transaction.atomic():
            for old_user in LegacyUser.objects.all():
                if HorillaUser.objects.filter(username=old_user.username).exists():
                    skipped_count += 1
                    continue

                date_joined = old_user.date_joined
                if date_joined and timezone.is_naive(date_joined):
                    date_joined = timezone.make_aware(date_joined)
                last_login = old_user.last_login
                if last_login and timezone.is_naive(last_login):
                    last_login = timezone.make_aware(last_login)

                new_user = HorillaUser.objects.create(
                    id=old_user.id,
                    username=old_user.username,
                    password=old_user.password,
                    first_name=old_user.first_name,
                    last_name=old_user.last_name,
                    email=old_user.email,
                    is_staff=old_user.is_staff,
                    is_active=old_user.is_active,
                    is_superuser=old_user.is_superuser,
                    last_login=last_login,
                    date_joined=date_joined,
                    is_new_employee=False,
                )

                group_ids = AuthUserGroups.objects.filter(
                    user_id=old_user.id
                ).values_list("group_id", flat=True)
                new_user.groups.set(Group.objects.filter(id__in=group_ids))

                permission_ids = AuthUserUserPermissions.objects.filter(
                    user_id=old_user.id
                ).values_list("permission_id", flat=True)
                new_user.user_permissions.set(
                    Permission.objects.filter(id__in=permission_ids)
                )

                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Migration complete: {created_count} users migrated, {skipped_count} skipped (with groups & permissions)."
            )
        )

    @staticmethod
    def _legacy_tables_present():
        """True when v1's auth_user table is still there to read from.

        Checked against the database rather than caught as an exception: a
        failed query inside an atomic block aborts the transaction, so the
        command could not go on to do anything useful afterwards anyway.
        """
        return LegacyUser._meta.db_table in connection.introspection.table_names()
