"""Archiving an employee must revoke their ability to log in.

Archiving is the obvious, reversible way to offboard someone, and it is what
an HR user reaches for instead of deleting. It did not touch login at all.

Two independent faults, which masked each other:

    employee.is_active = not employee.is_active                    # True -> False
    employee.employee_user_id.is_active = not employee.is_active   # -> not False = True
    ...
    employee.save()        # the user object is never saved

The assignment negated the *already flipped* value, so it set the user's flag
to the employee's previous state -- backwards. It never mattered, because only
the employee was saved. Fixing the save alone would have turned a no-op into
archiving *enabling* logins, which is why both halves are pinned here.

The gate that matters is ``HorillaUser.is_active``: ``CompanyScopedBackend``
subclasses ``ModelBackend`` without overriding ``user_can_authenticate``, which
is ``return getattr(user, "is_active", True)`` and knows nothing about
``Employee.is_active``. So these tests assert against ``authenticate()`` rather
than against the flag alone -- the flag is the mechanism, authentication is the
property that was broken.

Reported as https://github.com/horilla/horilla-hr/issues/1239 by @Safeer1877.
"""

from django.contrib.auth import authenticate
from django.test import RequestFactory, TestCase

from horilla.testkit import make_company, make_employee


class ArchiveRevokesLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Archive Co")

    def setUp(self):
        # AxesStandaloneBackend is first in AUTHENTICATION_BACKENDS and raises
        # AxesBackendRequestParameterRequired unless authenticate() is given a
        # request, so every call below passes one.
        self.request = RequestFactory().post("/login/")

    def _employee_with_password(self, email="leaver@test.horilla"):
        emp = make_employee(
            company=self.company,
            email=email,
            first_name="Departing",
            last_name="Staff",
        )
        user = emp.employee_user_id
        user.set_password("correct-horse-battery")
        user.save()
        return emp

    def test_archiving_revokes_authentication(self):
        emp = self._employee_with_password()
        self.assertIsNotNone(
            authenticate(
                self.request,
                username=emp.employee_user_id.username,
                password="correct-horse-battery",
            ),
            "precondition: an active employee can authenticate",
        )

        emp.is_active = False
        emp.save()
        emp.sync_login_access()

        emp.employee_user_id.refresh_from_db()
        self.assertFalse(emp.employee_user_id.is_active)
        self.assertIsNone(
            authenticate(
                self.request,
                username=emp.employee_user_id.username,
                password="correct-horse-battery",
            ),
            "an archived employee must not be able to log in",
        )

    def test_unarchiving_restores_authentication(self):
        emp = self._employee_with_password("returner@test.horilla")
        emp.is_active = False
        emp.save()
        emp.sync_login_access()

        emp.is_active = True
        emp.save()
        emp.sync_login_access()

        emp.employee_user_id.refresh_from_db()
        self.assertTrue(emp.employee_user_id.is_active)
        self.assertIsNotNone(
            authenticate(
                self.request,
                username=emp.employee_user_id.username,
                password="correct-horse-battery",
            ),
            "un-archiving must restore access",
        )

    def test_employee_without_a_user_does_not_raise(self):
        """employee_user_id is nullable, so the sync must tolerate None.

        Not routed through save(): Employee.save() auto-creates a HorillaUser
        whenever the FK is empty, which would both defeat the point and collide
        with the account already holding that username. The guard is what is
        under test, so it is called directly.
        """
        emp = make_employee(
            company=self.company,
            email="nouser@test.horilla",
            first_name="No",
            last_name="Account",
        )
        emp.employee_user_id = None
        emp.is_active = False

        emp.sync_login_access()  # must be a no-op, not an AttributeError

    def test_sync_does_not_clobber_an_independently_revoked_login(self):
        """Why this is not wired into Employee.save().

        ToggleDashboardAccess revokes a login while leaving the employee
        active. Syncing on every save would silently hand that access back, so
        the sync is an explicit call at the archive sites only -- and a plain
        employee save must leave the user's flag alone.
        """
        emp = self._employee_with_password("dashboard@test.horilla")
        user = emp.employee_user_id
        user.is_active = False  # access revoked, employee still active
        user.save(update_fields=["is_active"])

        emp.employee_first_name = "Renamed"
        emp.save()  # an ordinary save, no archive involved

        user.refresh_from_db()
        self.assertFalse(
            user.is_active,
            "an ordinary Employee.save() must not re-enable a revoked login",
        )
