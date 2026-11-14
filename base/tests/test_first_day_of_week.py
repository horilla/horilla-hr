"""
HORILLA_FIRST_DAY_OF_WEEK must reach every "This Week" calculation, not just
the generic Quick Date menu: the dashboards' presets, the reports, and the
PMS / leave / roster filters.
"""

import re
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings

from base.context_processors import first_day_of_week
from horilla.week import week_start

# Sunday 2026-11-08, the day from the bug report.
SUNDAY = date(2026, 11, 8)

# Dashboards whose "This Week" / "Last Week" presets are computed in the browser.
DASHBOARD_TEMPLATES = [
    "templates/dashboard.html",
    "helpdesk/templates/helpdesk/dashboard.html",
    "asset/templates/asset/dashboard.html",
    "attendance/templates/attendance/dashboard.html",
    "leave/templates/leave/dashboard.html",
    "base/templates/base/ess_dashboard.html",
    "pms/templates/pms/dashboard.html",
    "project/templates/project/dashboard.html",
    "offboarding/templates/offboarding/dashboard.html",
    "onboarding/templates/onboarding/dashboard.html",
    "payroll/templates/payroll/dashboard.html",
]


class FirstDayOfWeekContextTests(SimpleTestCase):
    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="6")
    def test_context_processor_exposes_the_setting(self):
        context = first_day_of_week(RequestFactory().get("/"))
        self.assertEqual(context, {"first_day_of_week": 6})

    @override_settings(HORILLA_FIRST_DAY_OF_WEEK="")
    def test_context_processor_falls_back_to_monday(self):
        context = first_day_of_week(RequestFactory().get("/"))
        self.assertEqual(context, {"first_day_of_week": 1})

    def test_context_processor_is_registered(self):
        processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
        self.assertIn("base.context_processors.first_day_of_week", processors)

    def test_week_start_for_the_reported_case(self):
        with override_settings(HORILLA_FIRST_DAY_OF_WEEK="6"):
            self.assertEqual(week_start(SUNDAY), date(2026, 11, 7))
            # Datetimes (some filters use datetime.today()) work too.
            self.assertEqual(
                week_start(datetime(2026, 11, 8, 15, 30)), datetime(2026, 11, 7, 15, 30)
            )
        with override_settings(HORILLA_FIRST_DAY_OF_WEEK="1"):
            self.assertEqual(week_start(SUNDAY), date(2026, 11, 2))


class DashboardPresetsAreNotHardcodedTests(SimpleTestCase):
    def test_no_dashboard_assumes_monday(self):
        root = Path(settings.BASE_DIR)
        for relative in DASHBOARD_TEMPLATES:
            with self.subTest(template=relative):
                source = (root / relative).read_text(encoding="utf-8")
                self.assertIsNone(
                    re.search(r"getDay\(\)\s*\+\s*6\)\s*%\s*7", source),
                    "week start must come from first_day_of_week, not Monday",
                )
                self.assertIn("first_day_of_week", source)
