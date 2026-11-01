"""
The home screen in one request.

Rendering it from the resource endpoints took eight or more round trips on a
cold start (the previous Flutter app made fourteen). These pin the shape the
client binds to, and the one derived value -- break time -- that has no
stored field behind it.
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from attendance.models import AttendanceActivity
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

HOME_URL = "/api/v1/mobile/home/"

# A fixed "today". The view reads date.today() and the fixtures build rows for
# the same day, so a run that straddled midnight would look for the rows on the
# wrong date. Pinning it makes the day a constant, not a race.
FIXED_TODAY = date(2026, 3, 10)


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return FIXED_TODAY


class MobileHomeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Home Co")
        self.user = make_user("home_user")
        self.employee = make_employee(
            company=self.company,
            email="home@test.horilla",
            first_name="Hana",
            user=self.user,
        )
        self.client.force_authenticate(user=self.user)
        clock = patch("horilla_api.api_views.mobile.views.date", _FrozenDate)
        clock.start()
        self.addCleanup(clock.stop)

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(HOME_URL).status_code, 401)

    def test_returns_every_block_the_screen_draws(self):
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        for key in (
            "employee",
            "capabilities",
            "punch",
            "geofence",
            "today",
            "on_leave_today",
            "announcement",
            "unread_notifications",
        ):
            self.assertIn(key, response.data)
        # Embedded so the tab bar needs no extra call.
        self.assertIn("role", response.data["capabilities"])
        self.assertIn("features", response.data["capabilities"])

    def test_clean_slate_is_not_clocked_in(self):
        punch = self.client.get(HOME_URL).data["punch"]
        self.assertFalse(punch["is_clocked_in"])
        self.assertIsNone(punch["clock_in_time"])

    def test_geofence_reports_disabled_when_unconfigured(self):
        self.assertEqual(self.client.get(HOME_URL).data["geofence"], {"enabled": False})

    def test_break_is_derived_from_the_gap_between_activity_pairs(self):
        """
        Attendance stores at_work_second and overtime_second but no break
        total, so this is computed. A 30-minute gap between clocking out and
        back in must surface as 00:30:00.
        """
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))

        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
            clock_out_date=today,
            clock_out=(base + timedelta(hours=12)).time(),
            out_datetime=base + timedelta(hours=12),
        )
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=12, minutes=30)).time(),
            in_datetime=base + timedelta(hours=12, minutes=30),
        )

        data = self.client.get(HOME_URL).data
        self.assertEqual(data["today"]["break"], "00:30:00")
        self.assertTrue(
            data["punch"]["is_clocked_in"],
            "the second activity has no clock_out, so the employee is still in",
        )

    def test_a_clock_out_without_an_out_datetime_does_not_500(self):
        """
        clock_out is a TimeField; out_datetime is a separate nullable
        DateTimeField written by a different code path, so a row can carry one
        without the other. Every other test here sets both, which is why this
        went unnoticed until a real server returned 500 on the home screen.
        """
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
            clock_out_date=today,
            clock_out=(base + timedelta(hours=12)).time(),
            out_datetime=None,
        )
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=12, minutes=30)).time(),
            in_datetime=base + timedelta(hours=12, minutes=30),
        )

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)
        # The break is still correct: it is rebuilt from clock_out_date +
        # clock_out, which are written even when out_datetime is not. Reading
        # the nullable column instead would report a real 30-minute break as
        # zero, which is worse than the 500 it replaced -- it looks like data.
        self.assertEqual(response.data["today"]["break"], "00:30:00")

    def test_an_open_activity_without_an_in_datetime_does_not_500(self):
        """in_datetime is nullable too, and last_activity_at dereferenced it."""
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=None,
        )

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["punch"]["is_clocked_in"])
        # Rebuilt from the date+time pair rather than reported as absent.
        self.assertTrue(
            response.data["punch"]["last_activity_at"].startswith(today.isoformat())
        )

    def test_single_open_activity_means_no_break(self):
        today = FIXED_TODAY
        base = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        AttendanceActivity.objects.create(
            employee_id=self.employee,
            attendance_date=today,
            clock_in_date=today,
            clock_in=(base + timedelta(hours=9)).time(),
            in_datetime=base + timedelta(hours=9),
        )
        self.assertEqual(self.client.get(HOME_URL).data["today"]["break"], "00:00:00")


class HomeAnnouncementAudienceTests(TestCase):
    """
    The home screen may only surface an announcement this employee is for.

    ``Announcement`` carries targeting (``employees``, ``department``,
    ``job_position``, and the denormalised ``filtered_employees``) and an
    ``expire_date``; the web self-service dashboard filters on all of them.
    The aggregate took ``objects.order_by("-created_at").first()``, which
    honoured none -- so an announcement written for one department, or expired
    a month ago, was handed to everyone in the company.
    """

    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Audience Co")
        self.user = make_user("audience_user")
        self.employee = make_employee(
            company=self.company,
            email="audience@test.horilla",
            first_name="Ada",
            user=self.user,
        )
        self.client.force_authenticate(user=self.user)

    def _announcement(self, title, **fields):
        from base.models import Announcement

        announcement = Announcement.objects.create(title=title, **fields)
        announcement.company_id.set([self.company])
        return announcement

    def test_untargeted_announcement_is_returned(self):
        """A broadcast -- no targeting at all -- is addressed to everyone."""
        self._announcement("All hands Friday")
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNotNone(response.data["announcement"])
        self.assertEqual(response.data["announcement"]["title"], "All hands Friday")

    def test_announcement_for_another_department_is_withheld(self):
        from base.models import Department

        other = Department.objects.create(department="Executive")
        announcement = self._announcement("Exec-only restructure")
        announcement.department.set([other])

        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(
            response.data["announcement"],
            "an announcement targeted at a department this employee is not in "
            "must not appear on their home screen",
        )

    def test_expired_announcement_is_withheld(self):
        self._announcement(
            "Last year's office move", expire_date=date.today() - timedelta(days=30)
        )
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(
            response.data["announcement"],
            "an announcement past its expire_date must not be surfaced",
        )
