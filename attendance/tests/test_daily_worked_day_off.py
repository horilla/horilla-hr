"""Day-wise view: a week off or holiday someone worked on shows that they worked (OT)."""

import datetime
from datetime import time

from django.test import TestCase
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from attendance.tests.test_daily_view import DAY, DailyViewMixin
from attendance.views.summary import daily_cell

OT = pgettext("summary code", "OT")


class DailyWorkedDayOffTests(DailyViewMixin, TestCase):
    SATURDAY = datetime.date(2026, 9, 5)

    def setUp(self):
        super().setUp()
        from base.models import CompanyLeaves

        CompanyLeaves.objects.create(based_on_week=None, based_on_week_day="5")

    def cell(self, day):
        response = self.get(day, day)
        row = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]
        return response, row["cells"][0]

    def test_a_week_off_nobody_worked_is_not_marked_worked(self):
        _response, cell = self.cell(self.SATURDAY)
        self.assertEqual(cell["status"], "week_off")
        self.assertNotEqual(cell["code"], OT)
        self.assertFalse(cell["worked_off"])

    def test_a_week_off_worked_on_shows_overtime(self):
        self.punch(day=self.SATURDAY, clock_in=time(7, 0), clock_out=time(11, 0))
        response, cell = self.cell(self.SATURDAY)
        self.assertEqual((cell["status"], cell["code"]), ("week_off", OT))
        self.assertTrue(cell["worked_off"])
        self.assertIn(str(_("Week Off Overtime")), cell["title"])
        self.assertIn("07:00", cell["title"])
        self.assertContains(response, "dv-week_off dv-worked-off")

    def test_a_holiday_keeps_its_code_until_someone_works_on_it(self):
        from base.models import Holidays

        Holidays.objects.create(name="Bank Holiday", start_date=DAY, end_date=DAY)
        _response, cell = self.cell(DAY)
        self.assertEqual((cell["status"], cell["code"]), ("holiday", "H"))
        self.punch()
        _response, cell = self.cell(DAY)
        self.assertEqual((cell["status"], cell["code"]), ("holiday", OT))
        self.assertIn(str(_("Holiday Overtime")), cell["title"])

    def test_overtime_still_to_approve_says_so(self):
        out = daily_cell(
            {
                "date": self.SATURDAY,
                "status": "week_off",
                "conflict_with": "week_off_ot",
                "ot_pending": True,
                "detail": "",
                "is_conflict": False,
            }
        )
        self.assertEqual(out["code"], OT)
        self.assertIn(str(_("Week Off Overtime, Pending Approval")), out["title"])
