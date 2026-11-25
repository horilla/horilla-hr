"""The calendar's overtime codes (HO, WO, OT) are translatable, like the rest of its labels."""

import datetime
from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from attendance.models import Attendance
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)  # a Wednesday


def _marked(context, message):
    """A translation that marks the summary codes, so the test can see they went through it."""
    if context == "summary code":
        return f"[{message}]"
    return pgettext_lazy(context, message)


class CalendarCodesTests(TestCase):
    def setUp(self):
        company = make_company("Codes Co")
        self.employee = make_employee(company=company, email="codes@test.horilla")
        user = make_user("codes-admin", is_superuser=True)
        make_employee(company=company, email="codes-admin@test.horilla", user=user)
        self.client.force_login(user)
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=time(8, 0),
            attendance_clock_out_date=DAY,
            attendance_clock_out=time(20, 0),
            attendance_worked_hour="12:00",
            minimum_hour="08:00",
            overtime_second=4 * 3600,
            attendance_overtime_approve=True,
            attendance_validated=True,
        )

    def calendar(self):
        return self.client.get(
            reverse("attendance-monthly-summary-calendar"),
            {
                "employee_id": self.employee.pk,
                "from_date": DAY.isoformat(),
                "to_date": DAY.isoformat(),
            },
            HTTP_HX_REQUEST="true",
        )

    def test_the_codes_go_through_translation(self):
        with patch("django.template.base.pgettext_lazy", _marked):
            response = self.calendar()
        # The day's badge and its tooltip, and the legend's codes.
        self.assertContains(response, ">[OT]</div>")
        self.assertContains(response, "[OT] — ")
        self.assertContains(response, "[HO]</span>")
        self.assertContains(response, "[WO]</span>")

    def test_untouched_they_read_as_translated(self):
        response = self.calendar()
        self.assertContains(response, f">{pgettext('summary code', 'OT')}</div>")
        self.assertContains(response, f"{pgettext('summary code', 'HO')}</span>")
