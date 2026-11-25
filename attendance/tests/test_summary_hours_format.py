"""
Hours on the monthly summary read as HH:MM, like everywhere else in
attendance (format_time): 8 hours 30 minutes is "08:30", not "8:30".
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from attendance.models import AttendanceDailyHours
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)


class SummaryHoursFormatTests(TestCase):
    def setUp(self):
        company = make_company("Hours Format Co")
        self.employee = make_employee(company=company, email="worker@hours.test")
        user = make_user("hr-hours", is_superuser=True)
        make_employee(company=company, email="hr@hours.test", user=user)
        self.client.force_login(user)
        AttendanceDailyHours.objects.create(
            employee_id=self.employee,
            date=DAY,
            hours_second=8 * 3600 + 30 * 60,
            is_manually_edited=True,
        )

    def _get(self, url_name, **extra):
        return self.client.get(
            reverse(url_name),
            {
                "employee_id": self.employee.pk,
                "date": DAY.isoformat(),
                "from_date": DAY.isoformat(),
                "to_date": DAY.isoformat(),
                **extra,
            },
            HTTP_HX_REQUEST="true",
        )

    def test_the_calendar_hours_input_is_hh_mm(self):
        response = self._get("attendance-monthly-summary-daily-hours-edit")
        self.assertEqual(response.context["hours_input"], "08:30")

    def test_the_panel_hours_input_is_hh_mm(self):
        response = self._get("attendance-monthly-summary-daily-hours-edit", panel=1)
        self.assertEqual(response.context["hours_input"], "08:30")

    def test_the_day_panel_is_hh_mm(self):
        response = self._get("attendance-monthly-summary-conflict-resolve")
        self.assertEqual(response.context["panel_hours_input"], "08:30")
        # No shift: the 8 hour default.
        self.assertEqual(response.context["min_required_label"], "08:00")

    def test_hh_mm_is_read_back(self):
        response = self.client.post(
            reverse("attendance-monthly-summary-daily-hours-edit"),
            {
                "employee_id": self.employee.pk,
                "date": DAY.isoformat(),
                "from_date": DAY.isoformat(),
                "to_date": DAY.isoformat(),
                "hours": "07:45",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AttendanceDailyHours.objects.get(
                employee_id=self.employee, date=DAY
            ).hours_second,
            7 * 3600 + 45 * 60,
        )
