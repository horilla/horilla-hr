"""
Three related attendance-web findings, all from the same audit pass:

GHSA-r59f-4xh4-58cf: the office-IP restriction trusted the first
X-Forwarded-For value unconditionally, so an attacker who supplies an
allowed address in that (client-controlled) header bypasses the restriction
entirely. get_client_ip() now only trusts it as far as AXES_PROXY_COUNT
says a real reverse proxy sits in front of the app -- the same setting
django-axes itself already relies on for lockouts.

GHSA-j3hc-6v4r-j658: the web clock-in/out endpoints enforced the office-IP
restriction but not a configured geo-fence, even though the mobile/API path
enforces both. geofence_denial_web() closes that gap; it fails closed (no
coordinates submitted, or the browser refused location access, denies
rather than silently allowing the punch).

The third copy of the reporting-manager truthy-HttpResponse bug (the same
root cause behind PR #3412's fixes to base.views.is_reportingmanger and
horilla_api...base.views._is_reportingmanger) lived in
attendance.methods.utils.is_reportingmanger, reached via
attendance.views.views.revalidate_this_attendance: an employee with no
work-info record yet made every caller's `or` chain pass for anyone.
"""

from datetime import date
from unittest import mock
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse

from attendance.methods.utils import (
    geofence_denial_web,
    get_client_ip,
    is_reportingmanger,
)
from attendance.models import Attendance
from employee.models import EmployeeWorkInformation
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user


class GetClientIpTests(TestCase):
    def _request(self, remote_addr="10.0.0.5", xff=None):
        request = type("R", (), {"META": {"REMOTE_ADDR": remote_addr}})()
        if xff is not None:
            request.META["HTTP_X_FORWARDED_FOR"] = xff
        return request

    @mock.patch("django.conf.settings.AXES_IPWARE_PROXY_COUNT", None)
    @mock.patch(
        "django.conf.settings.AXES_IPWARE_META_PRECEDENCE_ORDER", ["REMOTE_ADDR"]
    )
    def test_x_forwarded_for_is_ignored_with_no_proxy_count_configured(self):
        # The reported bypass: an attacker-supplied header must not win when
        # this deployment has never declared a trusted reverse proxy.
        request = self._request(remote_addr="203.0.113.9", xff="10.20.30.7")
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    @mock.patch("django.conf.settings.AXES_IPWARE_PROXY_COUNT", 1)
    @mock.patch(
        "django.conf.settings.AXES_IPWARE_META_PRECEDENCE_ORDER",
        ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"],
    )
    def test_x_forwarded_for_is_honored_once_a_proxy_count_is_declared(self):
        # With proxy_count=1, ipware expects the chain to already include
        # that one hop's own observed address -- exactly what nginx's
        # $proxy_add_x_forwarded_for appends. A single-entry header (as if
        # nginx had overwritten rather than appended) is one hop short of
        # what was declared, so it's correctly treated as unverifiable and
        # falls back to REMOTE_ADDR instead of being trusted regardless.
        request = self._request(remote_addr="10.0.0.1", xff="10.20.30.7, 10.0.0.1")
        self.assertEqual(get_client_ip(request), "10.20.30.7")


class GeofenceDenialWebTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Fence Co")

    def tearDown(self):
        set_selected_company(None)

    def _request(self, latitude=None, longitude=None):
        params = {}
        if latitude is not None:
            params["latitude"] = str(latitude)
        if longitude is not None:
            params["longitude"] = str(longitude)
        return type("R", (), {"GET": params})()

    def _fence(self, **overrides):
        from geofencing.models import GeoFencing

        fields = {
            "company_id": self.company,
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radius_in_meters": 200,
            "start": True,
        }
        fields.update(overrides)
        # GeoFencing.save() geocodes the coordinates against a live service
        # (Nominatim) purely to validate them -- mocked here, same as
        # geofencing/tests/test_geofencing_smoke.py.
        with patch("geofencing.models.Nominatim") as nominatim_cls:
            nominatim_cls.return_value.reverse.return_value = MagicMock()
            return GeoFencing.objects.create(**fields)

    def test_no_geofence_row_never_blocks(self):
        self.assertIsNone(geofence_denial_web(self._request(), self.company))

    def test_disabled_fence_never_blocks(self):
        self._fence(start=False)
        self.assertIsNone(geofence_denial_web(self._request(), self.company))

    def test_enabled_fence_with_no_coordinates_submitted_fails_closed(self):
        # The web page previously never sent coordinates at all -- the whole
        # reported gap. An enabled fence with nothing to check against must
        # deny, not silently let the punch through.
        self._fence()
        self.assertIsNotNone(geofence_denial_web(self._request(), self.company))

    def test_outside_the_radius_is_denied(self):
        self._fence()
        far_away = self._request(latitude=13.0827, longitude=80.2707)  # Chennai
        self.assertIsNotNone(geofence_denial_web(far_away, self.company))

    def test_inside_the_radius_is_allowed(self):
        self._fence()
        nearby = self._request(latitude=12.9717, longitude=77.5947)
        self.assertIsNone(geofence_denial_web(nearby, self.company))


class ThirdReportingManagerCopyTests(TestCase):
    """attendance.methods.utils.is_reportingmanger -- same bug, third copy."""

    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme")
        boss_user = make_user("boss3", password="pw")
        self.boss = make_employee(
            company=self.company,
            email="boss3@acme.test",
            first_name="Boss",
            user=boss_user,
        )
        target_user = make_user("target3", password="pw")
        self.target = make_employee(
            company=self.company,
            email="target3@acme.test",
            first_name="Target",
            user=target_user,
        )

    def tearDown(self):
        set_selected_company(None)

    def _request_as(self, employee):
        request = type("R", (), {"user": employee.employee_user_id})()
        return request

    def test_returns_false_not_a_truthy_response_when_work_info_is_missing(self):
        EmployeeWorkInformation.objects.filter(employee_id=self.target).delete()
        attendance = Attendance.objects.create(
            employee_id=self.target,
            attendance_date=date(2026, 1, 5),
            attendance_clock_in="09:00",
            attendance_clock_in_date=date(2026, 1, 5),
        )
        result = is_reportingmanger(self._request_as(self.boss), attendance)
        self.assertIs(result, False)
        # The bug was specifically that this used to be truthy in an `or`
        # chain -- assert the falsy-ness directly, not just "not the manager".
        self.assertFalse(bool(result))


class RevalidateAttendanceRegressionTests(TestCase):
    """The one real call site of the fixed helper."""

    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Acme2")
        stranger_user = make_user("stranger", password="pw")
        self.stranger = make_employee(
            company=self.company,
            email="stranger@acme.test",
            first_name="Stranger",
            user=stranger_user,
        )
        target_user = make_user("orphan", password="pw")
        self.target = make_employee(
            company=self.company,
            email="orphan@acme.test",
            first_name="Orphan",
            user=target_user,
        )
        EmployeeWorkInformation.objects.filter(employee_id=self.target).delete()
        self.attendance = Attendance.objects.create(
            employee_id=self.target,
            attendance_date=date(2026, 1, 5),
            attendance_clock_in="09:00",
            attendance_clock_in_date=date(2026, 1, 5),
            attendance_validated=True,
        )

    def tearDown(self):
        set_selected_company(None)

    def test_a_stranger_cannot_revalidate_an_orphaned_employees_attendance(self):
        client = Client()
        client.force_login(self.stranger.employee_user_id)
        client.get(reverse("revalidate-this-attendance", args=[self.attendance.pk]))
        self.attendance.refresh_from_db()
        self.assertTrue(self.attendance.attendance_validated)
