"""`migrateusers` must be a no-op when there is no legacy table to read.

LegacyUser and its two join models are unmanaged views onto v1's auth_user
tables. Django never creates or validates them, so their absence goes unnoticed
until the first query, which raises:

    ProgrammingError: relation "auth_user" does not exist

That is what the command did on any ordinary v2 database -- including a plain
fresh install, which has never had a v1 table and never will.
"""

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from horilla_auth.models import LegacyUser


class MigrateUsersWithoutLegacyTablesTests(TestCase):
    """The test database is built from migrations, so the unmanaged legacy
    tables are never created -- exactly the state of a fresh install."""

    def test_legacy_table_really_is_absent(self):
        """Guards the premise: if a future change starts creating auth_user,
        the no-op test below would pass for the wrong reason."""
        self.assertNotIn(
            LegacyUser._meta.db_table, connection.introspection.table_names()
        )

    def test_command_succeeds_instead_of_raising(self):
        out = StringIO()
        call_command("migrateusers", stdout=out)
        self.assertIn("Nothing to migrate", out.getvalue())

    def test_command_does_not_touch_existing_users(self):
        from horilla.testkit import make_user

        make_user("already_here", password="secret123")
        before = self.user_model().objects.count()

        call_command("migrateusers", stdout=StringIO())

        self.assertEqual(self.user_model().objects.count(), before)
        preserved = self.user_model().objects.get(username="already_here")
        self.assertTrue(preserved.check_password("secret123"))

    @staticmethod
    def user_model():
        from django.contrib.auth import get_user_model

        return get_user_model()
