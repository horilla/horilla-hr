"""Day-wise view: a week off is an empty square, as a day still to come is."""

import datetime

from django.test import TestCase
from django.utils.translation import gettext as _

from attendance.tests.test_daily_view import DailyViewMixin


class DailyWeekOffTests(DailyViewMixin, TestCase):
    SATURDAY = datetime.date(2026, 9, 5)

    def setUp(self):
        super().setUp()
        from base.models import CompanyLeaves

        CompanyLeaves.objects.create(based_on_week=None, based_on_week_day="5")

    def test_a_week_off_is_an_empty_square(self):
        response = self.get(self.SATURDAY, self.SATURDAY)
        cell = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]["cells"][0]
        self.assertEqual((cell["status"], cell["code"]), ("week_off", ""))
        self.assertIn(str(_("Week Off")), cell["title"])  # still named on hover
        self.assertContains(response, '<span class="dv-chip dv-week_off"')
