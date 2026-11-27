"""LDAP commands must never derive passwords from employee/directory data."""

import importlib
import sys
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase


def _load(module_path, fake_modules):
    with mock.patch.dict(sys.modules, fake_modules):
        sys.modules.pop(module_path, None)
        return importlib.import_module(module_path)


def _fake_ldap3():
    """A stand-in ldap3 package (the library is optional and may be missing)."""
    ldap3 = mock.MagicMock()
    ldap3.__path__ = []
    core = mock.MagicMock()
    core.__path__ = []
    exceptions = SimpleNamespace(LDAPException=type("LDAPException", (Exception,), {}))
    ldap3.core = core
    core.exceptions = exceptions
    return ldap3, {
        "ldap3": ldap3,
        "ldap3.core": core,
        "ldap3.core.exceptions": exceptions,
    }


class FakeEntry(dict):
    """Mimics an ldap3 entry: `name in entry` and `entry[name].value`."""

    def __getitem__(self, key):
        return SimpleNamespace(value=dict.__getitem__(self, key))


class ExportTests(SimpleTestCase):
    def test_exported_entry_has_no_user_password(self):
        ldap3 = mock.MagicMock()
        mod = _load(
            "horilla_ldap.management.commands.import_users_to_ldap",
            {"ldap3": ldap3},
        )
        employee = SimpleNamespace(
            employee_user_id=SimpleNamespace(username="alice@example.com"),
            employee_first_name="Alice",
            employee_last_name="A",
            email="alice.work@example.com",
            phone="07700900123",
        )
        conn = ldap3.Connection.return_value
        conn.entries = []
        settings = SimpleNamespace(
            ldap_server="ldap://x", bind_dn="cn=a", bind_password="p", base_dn="dc=x"
        )
        with mock.patch.object(
            mod.LDAPSettings.objects, "first", return_value=settings
        ), mock.patch.object(mod.Employee.objects, "all", return_value=[employee]):
            mod.Command().handle()
        attributes = conn.add.call_args.kwargs["attributes"]
        self.assertNotIn("userPassword", attributes)
        # uid is the stable account ID (the Horilla username), not the email
        self.assertEqual(attributes["uid"], "alice@example.com")
        self.assertEqual(attributes["mail"], "alice.work@example.com")


def _patch_models(mod, existing=None, email_taken=False):
    """Patch the DB layer of an import module. Returns (employee_cls, user)."""
    user = mock.MagicMock()
    employee_cls = mock.MagicMock()
    employee_cls.return_value.employee_user_id = user
    employee_cls.objects.filter.return_value.exclude.return_value.exists.return_value = (
        email_taken
    )
    if existing is not None:
        existing.employee_user_id = user
    patchers = [
        mock.patch.object(mod, "Employee", employee_cls),
        mock.patch.object(mod, "transaction", mock.MagicMock()),
        mock.patch.object(
            mod.Command, "find_employee", staticmethod(lambda *a: existing)
        ),
    ]
    for p in patchers:
        p.start()
    return employee_cls, user, patchers


def _stop(patchers):
    for p in patchers:
        p.stop()


LDAP_SETTINGS = SimpleNamespace(
    ldap_server="ldap://x",
    bind_dn="cn=a",
    bind_password="p",
    base_dn="ou=users,dc=x",
)


class ExportWithoutEmailTests(SimpleTestCase):
    def test_mail_attribute_is_omitted_when_employee_has_no_email(self):
        ldap3 = mock.MagicMock()
        mod = _load(
            "horilla_ldap.management.commands.import_users_to_ldap", {"ldap3": ldap3}
        )
        employee = SimpleNamespace(
            employee_user_id=SimpleNamespace(username="bob"),
            employee_first_name="Bob",
            employee_last_name="B",
            email=None,
            phone="",
        )
        conn = ldap3.Connection.return_value
        conn.entries = []
        settings = SimpleNamespace(
            ldap_server="ldap://x", bind_dn="cn=a", bind_password="p", base_dn="dc=x"
        )
        with mock.patch.object(
            mod.LDAPSettings.objects, "first", return_value=settings
        ), mock.patch.object(mod.Employee.objects, "all", return_value=[employee]):
            mod.Command().handle()
        attributes = conn.add.call_args.kwargs["attributes"]
        self.assertNotIn("mail", attributes)
        self.assertEqual(attributes["uid"], "bob")


class HorillaLdapImportCommandTests(SimpleTestCase):
    """The horilla_ldap import uses ldap3 only, on every platform."""

    MODULE = "horilla_ldap.management.commands.import_ldap_users"

    def _run(self, entries, existing=None, email_taken=False):
        ldap3, fakes = _fake_ldap3()
        mod = _load(self.MODULE, fakes)
        conn = ldap3.Connection.return_value
        conn.bind.return_value = True
        conn.bound = True
        conn.search.return_value = True
        conn.entries = entries
        employee_cls, user, patchers = _patch_models(mod, existing, email_taken)
        try:
            with mock.patch.object(
                mod.LDAPSettings.objects, "first", return_value=LDAP_SETTINGS
            ):
                mod.Command().handle()
        finally:
            _stop(patchers)
        return conn, user, employee_cls

    def test_new_employee_uses_cn_and_never_sets_password(self):
        entry = FakeEntry(uid="anu1", mail="a@x.com", cn="anuttan", sn="v")
        conn, user, employee_cls = self._run([entry])
        employee = employee_cls.return_value
        self.assertEqual(employee.employee_first_name, "anuttan")
        self.assertEqual(user.username, "anu1")
        self.assertEqual(user.email, "a@x.com")
        user.set_password.assert_not_called()
        conn.unbind.assert_called_once()

    def test_changed_mail_updates_the_same_employee(self):
        existing = mock.MagicMock(email="old@x.com")
        entry = FakeEntry(uid="cat1", mail="new@x.com", cn="cat", sn="m")
        _, user, employee_cls = self._run([entry], existing=existing)
        employee_cls.assert_not_called()  # no duplicate employee is created
        self.assertEqual(existing.email, "new@x.com")
        existing.save.assert_called_once()
        user.set_password.assert_not_called()

    def test_mail_already_used_by_another_employee_is_not_merged(self):
        existing = mock.MagicMock(email="old@x.com")
        entry = FakeEntry(uid="cat1", mail="taken@x.com", cn="cat", sn="m")
        _, user, _ = self._run([entry], existing=existing, email_taken=True)
        existing.save.assert_not_called()
        user.save.assert_not_called()

    def test_entry_without_mail_and_uid_is_skipped(self):
        entry = FakeEntry(cn="anuttan", sn="v")
        _, user, employee_cls = self._run([entry])
        employee_cls.assert_not_called()
        user.save.assert_not_called()

    def test_entry_without_mail_is_imported_through_its_uid(self):
        existing = mock.MagicMock(email=None)
        entry = FakeEntry(uid="anu1", cn="anuttan", sn="v")
        _, user, employee_cls = self._run([entry], existing=existing)
        employee_cls.assert_not_called()
        existing.save.assert_called_once()
        self.assertEqual(user.username, "anu1")
        user.set_password.assert_not_called()


class LegacyEmployeeImportTests(SimpleTestCase):
    MODULE = "employee.management.commands.import_ldap_users_legacy"

    def _run(self, attrs, existing=None):
        ldap = mock.MagicMock()
        ldap.LDAPError = Exception
        conn = ldap.initialize.return_value
        conn.search_s.return_value = [("uid=x", attrs)]
        mod = _load(self.MODULE, {"ldap": ldap})
        employee_cls, user, patchers = _patch_models(mod, existing)
        try:
            with mock.patch.object(
                mod.LDAPSettings.objects, "first", return_value=LDAP_SETTINGS
            ):
                mod.Command().handle()
        finally:
            _stop(patchers)
        return conn, user, employee_cls

    def test_keeps_password_and_uses_saved_search_base(self):
        conn, user, employee_cls = self._run(
            {
                "uid": [b"alice"],
                "mail": [b"alice@example.com"],
                "cn": [b"alice"],
                "userPassword": [b"{SHA}abc"],
            }
        )
        user.set_password.assert_not_called()
        self.assertEqual(user.username, "alice")
        self.assertEqual(
            employee_cls.return_value.employee_first_name, "alice"
        )  # cn fallback
        self.assertEqual(conn.search_s.call_args.args[0], "ou=users,dc=x")

    def test_changed_mail_updates_the_same_employee(self):
        existing = mock.MagicMock(email="old@x.com")
        _, _, employee_cls = self._run(
            {"uid": [b"cat1"], "mail": [b"new@x.com"], "cn": [b"cat"]},
            existing=existing,
        )
        employee_cls.assert_not_called()
        self.assertEqual(existing.email, "new@x.com")
