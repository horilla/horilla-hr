"""Demo date-window helpers and date-policy clamp."""

from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase

from base.demo_data.dates import (
    FIXTURE_AS_OF,
    attendance_dates_for_employee,
    clamp_date,
    holiday_on_year,
    previous_weekday,
    scheduled_weekdays_for_shift,
    shift_fixture_dates_text,
    should_be_present_today,
    spaced_dates,
    weekdays_inclusive,
)
from base.models import EmployeeShift
from horilla.testkit import make_company, make_employee


class DemoDateWindowTests(SimpleTestCase):
    def test_weekdays_skip_saturday_sunday(self):
        days = weekdays_inclusive(date(2026, 8, 15), date(2026, 8, 23))
        self.assertTrue(all(d.weekday() < 5 for d in days))
        self.assertNotIn(date(2026, 8, 16), days)  # Sunday
        self.assertNotIn(date(2026, 8, 22), days)  # Saturday

    def test_scheduled_weekdays_for_shift_maps_day_names(self):
        mon_sat = scheduled_weekdays_for_shift(
            ["monday", "Tuesday", "wednesday", "THURSDAY", "friday", "saturday"]
        )
        self.assertEqual(mon_sat, {0, 1, 2, 3, 4, 5})

    def test_scheduled_weekdays_for_shift_falls_back_to_mon_fri(self):
        self.assertEqual(scheduled_weekdays_for_shift([]), {0, 1, 2, 3, 4})
        self.assertEqual(scheduled_weekdays_for_shift(None), {0, 1, 2, 3, 4})
        self.assertEqual(scheduled_weekdays_for_shift(["not-a-day"]), {0, 1, 2, 3, 4})

    def test_attendance_dates_respect_a_mon_sat_shift(self):
        # A Mon-Sat shift's demo attendance should be able to land on
        # Saturday -- the default Mon-Fri-only pool can never produce one.
        mon_sat = {0, 1, 2, 3, 4, 5}
        today = date(2026, 8, 20)  # Thursday
        start = today - timedelta(days=180)
        dates = attendance_dates_for_employee(1, start, today, 130, weekdays=mon_sat)
        self.assertTrue(any(d.weekday() == 5 for d in dates))
        self.assertTrue(all(d.weekday() != 6 for d in dates))  # never Sunday

    def test_attendance_dates_default_weekdays_never_include_saturday(self):
        today = date(2026, 8, 20)
        start = today - timedelta(days=180)
        dates = attendance_dates_for_employee(1, start, today, 26)
        self.assertTrue(all(d.weekday() < 5 for d in dates))

    def test_spaced_dates_are_unique_and_bounded(self):
        start, end = date(2026, 2, 20), date(2026, 8, 19)
        dates = spaced_dates(start, end, 26, weekdays_only=True)
        self.assertEqual(len(dates), 26)
        self.assertEqual(len(set(dates)), 26)
        self.assertEqual(dates[0], weekdays_inclusive(start, end)[0])
        self.assertEqual(dates[-1], weekdays_inclusive(start, end)[-1])
        self.assertTrue(all(start <= d <= end for d in dates))
        self.assertTrue(all(d.weekday() < 5 for d in dates))

    def test_nobody_present_on_weekend(self):
        saturday = date(2026, 8, 22)
        self.assertFalse(should_be_present_today(1, saturday))
        self.assertFalse(should_be_present_today(87, saturday))

    def test_present_today_is_not_everyone(self):
        today = date(2026, 8, 19)  # Wednesday
        present = [i for i in range(1, 201) if should_be_present_today(i, today)]
        self.assertGreater(len(present), 100)
        self.assertLess(len(present), 200)

    def test_absent_employees_do_not_get_today_as_last_date(self):
        today = date(2026, 8, 19)
        start = today - timedelta(days=180)
        absent_id = 90  # 90 % 100 = 90, not < 87
        self.assertFalse(should_be_present_today(absent_id, today))
        dates = attendance_dates_for_employee(absent_id, start, today, 26)
        self.assertNotIn(today, dates)
        self.assertLess(max(dates), today)
        self.assertIn(previous_weekday(today), dates)
        self.assertEqual(len(dates), 26)
        self.assertEqual(len(set(dates)), 26)

    def test_present_employees_include_today_on_weekdays(self):
        today = date(2026, 8, 20)  # Thursday
        start = today - timedelta(days=180)
        present_id = 1
        self.assertTrue(should_be_present_today(present_id, today))
        dates = attendance_dates_for_employee(present_id, start, today, 26)
        self.assertEqual(dates[-1], today)
        self.assertIn(previous_weekday(today), dates)

    def test_fixture_shift_maps_snapshot_day_to_load_day(self):
        today = date(2026, 8, 20)
        text = (
            '{"attendance_date": "2025-07-31", "clock": "2025-07-30T18:00:00Z",'
            ' "dob": "1968-04-12"}'
        )
        shifted = shift_fixture_dates_text(text, today)
        self.assertIsNotNone(shifted)
        self.assertIn('"2026-08-20"', shifted)
        self.assertIn("2026-08-19T18:00:00Z", shifted)
        self.assertIn("1968-04-12", shifted)
        self.assertIsNone(shift_fixture_dates_text(text, FIXTURE_AS_OF))

    def test_holiday_on_year_keeps_month_day(self):
        self.assertEqual(holiday_on_year(date(2025, 12, 25), 2026), date(2026, 12, 25))
        self.assertEqual(holiday_on_year(date(2024, 2, 29), 2025), date(2025, 2, 28))

    def test_clamp_date_never_after_today(self):
        today = date(2026, 8, 20)
        self.assertEqual(clamp_date(date(2026, 8, 19), today), date(2026, 8, 19))
        self.assertEqual(clamp_date(date(2026, 9, 1), today), today)
        self.assertIsNone(clamp_date(None, today))

    def test_attendance_window_spans_six_months(self):
        today = date(2026, 8, 20)
        start = today - timedelta(days=180)
        dates = attendance_dates_for_employee(1, start, today, 26)
        self.assertGreaterEqual((max(dates) - min(dates)).days, 150)
        self.assertLessEqual(max(dates), today)
        self.assertGreaterEqual(min(dates), start)

    def test_inventory_covers_every_sidebar_app(self):
        from django.conf import settings

        from base.demo_data.inventory import SIDEBAR_DEMO_MODELS

        listed = {app for app, _ in SIDEBAR_DEMO_MODELS}
        for app in settings.SIDEBARS:
            self.assertIn(app, listed)

    def test_side_fixtures_are_on_the_load_list(self):
        from base.demo_data.fixtures import demo_fixture_files

        files = demo_fixture_files()
        self.assertIn("tags.json", files)
        self.assertIn("mail_templates.json", files)
        self.assertIn("mail_automations.json", files)
        self.assertNotIn("faq.json", files)


class DemoDatePolicyDBTests(TestCase):
    """Clamp / request-window behaviour with injected `today`."""

    @classmethod
    def setUpTestData(cls):
        cls.today = date.today()
        cls.company = make_company("Demo Clamp Co")
        cls.employee = make_employee(company=cls.company, email="clamp@test.horilla")
        cls.shift = EmployeeShift.objects.create(employee_shift="Clamp Day")

    def test_a_class_activity_dates_not_after_today(self):
        from datetime import time

        from attendance.models import AttendanceActivity
        from base.demo_data.modules.date_clamp import clamp_demo_dates

        future = self.today + timedelta(days=12)
        act = AttendanceActivity._base_manager.create(
            employee_id=self.employee,
            attendance_date=self.today,
            clock_in_date=self.today,
            clock_in=time(9, 0),
        )
        AttendanceActivity._base_manager.filter(pk=act.pk).update(
            attendance_date=future, clock_in_date=future
        )
        clamp_demo_dates(self.today)
        act.refresh_from_db()
        self.assertLessEqual(act.attendance_date, self.today)
        self.assertLessEqual(act.clock_in_date, self.today)

    def test_pending_shift_request_till_is_in_the_future(self):
        from base.demo_data.modules.request_windows import backfill_request_windows
        from base.models import ShiftRequest

        req = ShiftRequest._base_manager.create(
            employee_id=self.employee,
            shift_id=self.shift,
            requested_date=self.today - timedelta(days=40),
            requested_till=self.today - timedelta(days=10),
            approved=False,
            canceled=False,
        )
        backfill_request_windows(self.today)
        req.refresh_from_db()
        self.assertGreater(req.requested_till, self.today)

    def test_holidays_reanchor_to_current_year(self):
        from base.demo_data.modules.date_clamp import clamp_demo_dates
        from base.models import Holidays

        holiday = Holidays._base_manager.create(
            name="Clamp Christmas",
            start_date=date(2025, 12, 25),
            end_date=date(2025, 12, 26),
        )
        clamp_demo_dates(self.today)
        holiday.refresh_from_db()
        self.assertEqual(holiday.start_date.year, self.today.year)
        self.assertEqual(holiday.start_date.month, 12)
        self.assertEqual(holiday.start_date.day, 25)
        self.assertEqual((holiday.end_date - holiday.start_date).days, 1)
        self.assertTrue(
            Holidays._base_manager.filter(start_date__year=self.today.year).exists()
        )
