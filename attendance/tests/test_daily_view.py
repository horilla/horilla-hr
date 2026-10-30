"""The Day-wise view of the monthly summary: a column per date in the filter, a status in each cell."""

import datetime
from datetime import time

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
from attendance.views.summary import DAILY_VIEW_MAX_DAYS, daily_cell
from horilla.testkit import make_company, make_employee, make_user

DAY = datetime.date(2026, 9, 2)  # a Wednesday


class DailyViewMixin:
    """Shared setUp and helpers; the test classes below mix it in so each test runs once."""

    def setUp(self):
        company = make_company("Daily View Co")
        self.employee = make_employee(company=company, email="daily@test.horilla")
        user = make_user("daily-admin", is_superuser=True)
        make_employee(company=company, email="daily-admin@test.horilla", user=user)
        self.client.force_login(user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def get(self, start, end, **extra):
        params = {
            "view": "daily",
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            **extra,
        }
        return self.client.get(
            reverse("attendance-monthly-summary-table"), params, HTTP_HX_REQUEST="true"
        )

    def punch(
        self, day=DAY, clock_in=time(9, 0), clock_out=time(18, 0), worked="09:00"
    ):
        return Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=day,
            attendance_clock_in_date=day,
            attendance_clock_in=clock_in,
            attendance_clock_out_date=day,
            attendance_clock_out=clock_out,
            attendance_worked_hour=worked,
            minimum_hour="08:00",
            attendance_validated=True,
        )


class DailyViewTests(DailyViewMixin, TestCase):
    def test_one_column_per_date_in_the_range(self):
        response = self.get(DAY, DAY + datetime.timedelta(days=4))
        self.assertEqual(response.context["days"][0]["date"], DAY)
        self.assertEqual(len(response.context["days"]), 5)
        self.assertContains(response, 'class="dv-day', count=5)

    def test_the_range_follows_the_filter(self):
        short = self.get(DAY, DAY + datetime.timedelta(days=2))
        longer = self.get(DAY, DAY + datetime.timedelta(days=9))
        self.assertEqual(len(short.context["days"]), 3)
        self.assertEqual(len(longer.context["days"]), 10)

    def test_each_cell_shows_the_days_status(self):
        self.punch()
        response = self.get(DAY, DAY + datetime.timedelta(days=1))
        row = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]
        first, second = row["cells"]
        self.assertEqual((first["status"], first["code"]), ("present", "P"))
        self.assertContains(response, "dv-present")
        self.assertIn("Present", first["title"])

    def test_past_days_without_attendance_are_absent_and_future_days_are_upcoming(self):
        today = datetime.date.today()
        response = self.get(
            today - datetime.timedelta(days=30), today + datetime.timedelta(days=3)
        )
        row = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]
        statuses = [c["status"] for c in row["cells"]]
        self.assertIn("absent", statuses)
        self.assertEqual(statuses[-1], "future")
        self.assertEqual(row["cells"][-1]["code"], "")

    def test_a_leave_day_shows_its_code(self):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(name="Daily Paid", payment="paid")
        LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=DAY,
                    end_date=DAY,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=1,
                    description="Test",
                    status="approved",
                )
            ]
        )
        response = self.get(DAY, DAY)
        row = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]
        self.assertEqual(row["cells"][0]["code"], "PL")

    def test_a_conflict_is_marked_on_the_cell(self):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(name="Daily Clash", payment="paid")
        LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=DAY,
                    end_date=DAY,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=1,
                    description="Test",
                    status="approved",
                )
            ]
        )
        self.punch()
        response = self.get(DAY, DAY)
        row = [
            r for r in response.context["rows"] if r["employee"].pk == self.employee.pk
        ][0]
        self.assertTrue(row["cells"][0]["conflict"])
        self.assertContains(response, "dv-dot--conflict")

    def test_a_range_that_is_too_long_asks_for_a_shorter_one(self):
        response = self.get(DAY, DAY + datetime.timedelta(days=DAILY_VIEW_MAX_DAYS))
        self.assertTrue(response.context["too_long"])
        self.assertContains(response, str(DAILY_VIEW_MAX_DAYS))
        self.assertNotContains(response, 'id="dvTable"')

    def test_the_cells_open_the_calendar_for_that_employee(self):
        response = self.get(DAY, DAY)
        self.assertContains(response, "data-calendar-url")
        self.assertContains(response, f"employee_id={self.employee.pk}")

    def test_the_summary_is_still_the_default(self):
        response = self.client.get(
            reverse("attendance-monthly-summary-table"),
            {"from_date": DAY.isoformat(), "to_date": DAY.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, 'id="dvTable"')
        self.assertContains(response, "ms-summary-row")

    def test_a_submit_nothing_handled_is_sent_through_htmx_not_left_to_the_browser(
        self,
    ):
        """saveFilters.js clicks Apply on load; if htmx has not taken the form yet the browser would
        navigate and the page would reload in a loop."""
        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertIn("window.addEventListener('submit', function (e) {", html)
        self.assertIn(
            "e.target.id !== 'summary-filter-form' || e.defaultPrevented", html
        )
        self.assertIn("e.preventDefault();", html)
        self.assertIn("htmx.ajax('GET'", html)

    def test_clearing_a_filter_also_clears_what_is_remembered_for_the_next_load(self):
        """saveFilters.js restores the last applied filter on every load; clearing one (its chip, Clear
        All, the search box) must update that memory or the filter comes back after a reload.
        """
        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertIn("function msSyncSavedFilters()", html)
        self.assertIn("localStorage.removeItem('savedFilters')", html)
        # Hooked to the places a filter is cleared, not to every table load (the first load runs
        # before the saved filter is put back).
        self.assertEqual(html.count("msSyncSavedFilters();"), 2)
        self.assertIn("setTimeout(msSyncSavedFilters, 700)", html)
        self.assertNotIn("htmx:afterSwap', msSyncSavedFilters", html)

    def test_no_template_comment_leaks_into_the_page(self):
        """A {# #} comment must stay on one line; across lines Django prints it as text."""
        import re
        from pathlib import Path

        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)
        pattern = re.compile(r"\{#(?:(?!#\}).)*#\}", re.S)
        for name in (
            "monthly_summary",
            "table_daily",
            "table_dashboard",
            "table_partial",
            "calendar_modal",
        ):
            source = Path(
                f"attendance/templates/attendance/monthly_summary/{name}.html"
            ).read_text(encoding="utf-8")
            across_lines = [m for m in pattern.findall(source) if chr(10) in m]
            self.assertEqual(across_lines, [], name)

    def test_a_page_opened_inside_the_app_forgets_the_old_filter(self):
        html = self.client.get(reverse("attendance-monthly-summary")).content.decode()
        self.assertIn("if (document.readyState === 'complete') {", html)
        self.assertIn("localStorage.removeItem('savedFilters')", html)

    def test_the_page_opens_on_the_view_last_used(self):
        from attendance.views.summary import SUMMARY_VIEW_COOKIE

        for view in ("daily", "summary", "list"):
            with self.subTest(view=view):
                self.client.cookies[SUMMARY_VIEW_COOKIE] = view
                html = self.client.get(
                    reverse("attendance-monthly-summary")
                ).content.decode()
                self.assertIn(f'id="ms-view" value="{view}"', html)
                self.assertIn(f'data-view="{view}"', html)
                self.assertRegex(
                    html, rf'data-view="{view}"[^>]*ms-view-btn oh-view-btn--active'
                )
                # The table's first request asks for that view, so it does not flash the list.
                self.assertIn(f"table/?view={view}", html)

    def test_an_address_view_beats_the_remembered_one_and_a_bad_value_falls_back(self):
        from attendance.views.summary import SUMMARY_VIEW_COOKIE

        self.client.cookies[SUMMARY_VIEW_COOKIE] = "daily"
        self.assertIn(
            'id="ms-view" value="summary"',
            self.client.get(
                reverse("attendance-monthly-summary"), {"view": "summary"}
            ).content.decode(),
        )
        self.client.cookies[SUMMARY_VIEW_COOKIE] = "nonsense"
        self.assertIn(
            'id="ms-view" value="list"',
            self.client.get(reverse("attendance-monthly-summary")).content.decode(),
        )

    def test_the_list_is_the_default_view(self):
        response = self.client.get(reverse("attendance-monthly-summary"))
        self.assertContains(response, 'id="ms-view" value="list"')

    def test_an_unknown_view_falls_back_to_the_list(self):
        response = self.client.get(
            reverse("attendance-monthly-summary"), {"view": "nonsense"}
        )
        self.assertContains(response, 'id="ms-view" value="list"')


class DailyCellTests(TestCase):
    def test_no_cell_is_blank(self):
        self.assertEqual(daily_cell(None)["status"], "none")

    def test_a_split_day_shows_both_halves(self):
        cell = {
            "date": DAY,
            "status": "split",
            "halves": ("P", "PL"),
            "split_style": "--h1:#86efac;--h2:#93c5fd",
            "split_label": "Half Present + Half Paid Leave",
            "detail": "",
            "is_conflict": False,
        }
        out = daily_cell(cell)
        self.assertEqual(out["code"], "P/PL")
        self.assertEqual(
            out["style"], "--h1:#86efac;--h2:#93c5fd"
        )  # the colours the calendar uses

    def test_a_half_leave_ahead_shows_leave_and_upcoming(self):
        cell = {
            "date": DAY,
            "status": "paid_leave",
            "future_part": (0.5, 0.0, "first", "Casual"),
            "split_style": "--h1:#93c5fd;--h2:#f1f5f9",
            "detail": "Casual",
            "is_conflict": False,
        }
        out = daily_cell(cell)
        self.assertEqual(out["code"], "PL/–")
        self.assertTrue(out["ahead"])


class DailyClickTests(DailyViewMixin, TestCase):
    """A day cell opens only the regularise popover for that employee; the name opens the calendar."""

    def test_a_day_cell_carries_what_the_popover_needs_and_the_name_opens_the_calendar(
        self,
    ):
        import re

        response = self.get(DAY, DAY + datetime.timedelta(days=1))
        html = response.content.decode()
        self.assertEqual(
            html.count("data-day-popover="), 2 * len(response.context["rows"])
        )
        cell = re.search(r'<td class="dv-cell[^>]*data-day-popover[^>]*>', html).group(
            0
        )
        self.assertIn(f'data-employee="{self.employee.pk}"', cell)
        self.assertIn(f'data-date="{DAY.isoformat()}"', cell)
        self.assertIn(f'data-from="{DAY.isoformat()}"', cell)
        # No calendar link on a day cell: the popover is all it opens.
        self.assertNotIn("data-calendar-url", cell)
        name_cell = re.search(r'<td class="dv-emp"[^>]*>', html).group(0)
        self.assertIn("data-calendar-url", name_cell)
        self.assertNotIn("data-day-popover", name_cell)

    def test_the_table_carries_the_popover_urls(self):
        html = self.get(DAY, DAY).content.decode()
        self.assertIn("data-resolve-url=", html)
        self.assertIn("data-bulk-resolve-url=", html)

    def test_a_conflict_cell_names_its_conflict_for_the_popover_theme(self):
        from leave.models import LeaveRequest, LeaveType

        leave_type = LeaveType.objects.create(name="Pop Clash", payment="paid")
        LeaveRequest.objects.bulk_create(
            [
                LeaveRequest(
                    employee_id=self.employee,
                    leave_type_id=leave_type,
                    start_date=DAY,
                    end_date=DAY,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=1,
                    description="Test",
                    status="approved",
                )
            ]
        )
        self.punch()
        html = self.get(DAY, DAY).content.decode()
        self.assertIn('data-conflict-type="paid_leave"', html)

    def test_the_host_opens_the_popover_alone_and_refreshes_the_page_after_saving(self):
        from django.template.loader import render_to_string

        host = render_to_string("attendance/monthly_summary/_calendar_modal_host.html")
        self.assertIn("window.msOpenDayPopover = function (cell)", host)
        self.assertIn("[data-day-popover]", host)
        self.assertEqual(host.count("_standaloneDone();"), 3)
        self.assertIn("attendance-calendar-saved", host)

    def test_the_grid_reloads_after_a_day_is_regularised(self):
        response = self.get(DAY, DAY)
        self.assertContains(response, "attendance-calendar-saved")
        self.assertContains(response, 'data-page="1"')


class DashboardTests(DailyViewMixin, TestCase):
    """The Summary view: attendance mix, findings and the period's figures; the list no longer carries the cards."""

    def get_summary(self, start=DAY, end=DAY + datetime.timedelta(days=6), **extra):
        params = {
            "view": "summary",
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            **extra,
        }
        return self.client.get(
            reverse("attendance-monthly-summary-table"), params, HTTP_HX_REQUEST="true"
        )

    def test_the_summary_view_renders_the_dashboard(self):
        response = self.get_summary()
        self.assertContains(response, "Attendance Mix")
        self.assertContains(response, '<div class="dbx-kpi">', count=7)
        self.assertContains(
            response, '<div class="dbx-kpi dbx-kpi--tip"', count=1
        )  # Absent: its breakdown is a tooltip
        self.assertContains(response, '<div class="dbx-kpi dbx-kpi--alert">', count=1)
        for label in (
            "Employees",
            "Working Days",
            "Present",
            "Absent / Short Hours",
            "Paid Leave",
            "Unpaid Leave",
            "Week Off",
            "Holidays",
            "Conflicts",
        ):
            self.assertContains(response, label)
        self.assertNotContains(response, 'id="dvTable"')
        self.assertNotContains(response, "ms-summary-row")

    def test_the_list_no_longer_carries_the_kpi_cards(self):
        response = self.client.get(
            reverse("attendance-monthly-summary-table"),
            {"from_date": DAY.isoformat(), "to_date": DAY.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(response, '<div class="ms-stat-row">')
        self.assertNotContains(response, 'class="ms-stat-card"')
        self.assertContains(response, "ms-summary-row")

    def test_the_mix_adds_up_and_the_donut_has_a_slice_for_each_part(self):
        self.punch()
        context = self.get_summary().context
        mix = {item["key"]: item for item in context["mix"]}
        totals = context["totals"]
        self.assertEqual(mix["present"]["value"], totals["total_present"])
        self.assertEqual(mix["absent"]["value"], totals["total_absent"])
        self.assertEqual(
            context["scheduled"], sum(item["value"] for item in context["mix"])
        )
        self.assertLessEqual(sum(item["percent"] for item in context["mix"]), 101)
        self.assertEqual(context["worked_percent"], mix["present"]["percent"])
        self.assertEqual(context["period"], "02 Sep 2026 \u2013 08 Sep 2026")

    def test_a_holiday_made_by_regularisation_is_not_called_company_wide(self):
        from attendance.models import AttendanceConflictResolution

        AttendanceConflictResolution.objects.create(
            employee_id=self.employee,
            date=DAY,
            resolution="holiday",
        )
        response = self.get_summary(DAY, DAY, search=self.employee.get_full_name())
        self.assertEqual(response.context["totals"]["regularised_holiday"], 1)
        self.assertContains(response, "1 Set By Regularisation")
        self.assertNotContains(response, "Company-Wide")

    def test_a_period_across_months_is_named_by_its_dates(self):
        context = self.get_summary(
            datetime.date(2026, 9, 20), datetime.date(2026, 10, 10)
        ).context
        self.assertIn("–", context["period"])
        self.assertIn("20 Sep 2026", context["period"])

    def test_with_nothing_scheduled_the_donut_shows_a_dash_not_a_percentage(self):
        response = self.get_summary(employee_id=0)
        self.assertEqual(response.context["scheduled"], 0)
        self.assertContains(response, "&ndash;")

    def test_the_absent_figure_says_how_much_is_short_hours_and_how_much_is_upcoming(
        self,
    ):
        today = datetime.date.today()
        context = self.get_summary(
            today + datetime.timedelta(days=1), today + datetime.timedelta(days=14)
        ).context
        self.assertGreater(context["upcoming_days"], 0)
        absent = context["totals"]["total_absent"]
        self.assertAlmostEqual(
            context["plain_absent"]
            + context["short_hours"]
            + context["missing_punches"]
            + context["upcoming_days"],
            absent,
        )

    def test_hours_that_fell_short_of_the_shift_are_counted_as_short_hours(self):
        self.punch(DAY, time(9, 0), time(11, 0), worked="02:00")
        context = self.get_summary(DAY, DAY).context
        self.assertGreaterEqual(context["short_hours"], 1)
        self.assertLessEqual(context["short_hours"], context["totals"]["total_absent"])

    def test_a_day_with_no_clock_out_is_a_missing_punch_not_short_hours(self):
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=DAY,
            attendance_clock_in_date=DAY,
            attendance_clock_in=time(9, 0),
            attendance_worked_hour="00:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )
        context = self.get_summary(DAY, DAY).context
        self.assertGreaterEqual(context["missing_punches"], 1)
        # The same day with a clock-out is short hours, not a missing punch.
        Attendance.objects.filter(employee_id=self.employee).delete()
        self.punch(DAY, time(9, 0), time(9, 30), worked="00:30")
        again = self.get_summary(DAY, DAY).context
        self.assertEqual(again["missing_punches"], 0)
        self.assertGreaterEqual(again["short_hours"], 1)

    def test_the_view_switch_reaches_every_view_through_the_same_request(self):
        for view, marker in (
            ("list", "ms-summary-row"),
            ("daily", 'id="dvTable"'),
            ("summary", "Attendance Mix"),
        ):
            with self.subTest(view=view):
                response = self.client.get(
                    reverse("attendance-monthly-summary-table"),
                    {
                        "view": view,
                        "from_date": DAY.isoformat(),
                        "to_date": DAY.isoformat(),
                    },
                    HTTP_HX_REQUEST="true",
                )
                self.assertContains(response, marker)


class DailyChipTests(DailyViewMixin, TestCase):
    """A day is a white square with a rounded status chip in it."""

    def test_each_day_is_a_chip_in_a_plain_cell(self):
        self.punch()
        html = self.get(DAY, DAY).content.decode()
        self.assertIn('<td class="dv-cell"', html)
        self.assertIn('<span class="dv-chip dv-present"', html)
        self.assertNotIn('<td class="dv-cell dv-', html)


class WeekOffRuleTests(TestCase):
    """The roster rules the period it is assigned for; the company's week-off days apply outside it."""

    D = datetime.date
    COMPANY = {
        D(2026, 9, 5),
        D(2026, 9, 12),
        D(2026, 9, 19),
        D(2026, 9, 26),
    }  # four Saturdays
    START, END = D(2026, 9, 1), D(2026, 9, 30)

    def off(self, rows):
        from attendance.views.summary import employee_week_off_dates

        return employee_week_off_dates(rows, self.COMPANY, self.START, self.END)

    def test_with_no_roster_the_companys_days_apply(self):
        self.assertEqual(self.off([]), self.COMPANY)

    def test_inside_the_rostered_period_only_the_roster_decides(self):
        D = self.D
        rows = [
            (D(2026, 9, d), d == 14) for d in range(10, 21)
        ]  # 10th to 20th, only the 14th off
        off = self.off(rows)
        self.assertIn(D(2026, 9, 14), off)
        self.assertNotIn(
            D(2026, 9, 12), off
        )  # a company Saturday, inside the period: worked
        self.assertNotIn(D(2026, 9, 19), off)

    def test_outside_the_rostered_period_the_companys_days_apply(self):
        D = self.D
        rows = [(D(2026, 9, d), d == 14) for d in range(10, 21)]
        off = self.off(rows)
        self.assertIn(D(2026, 9, 5), off)  # before the roster starts
        self.assertIn(D(2026, 9, 26), off)  # after it ends
        self.assertEqual(off, {D(2026, 9, 5), D(2026, 9, 14), D(2026, 9, 26)})

    def test_a_single_entry_is_a_period_of_one_day(self):
        D = self.D
        off = self.off([(D(2026, 9, 12), False)])
        self.assertNotIn(D(2026, 9, 12), off)
        self.assertEqual(off, self.COMPANY - {D(2026, 9, 12)})

    def test_roster_entries_outside_the_viewed_range_are_ignored(self):
        D = self.D
        self.assertEqual(
            self.off([(D(2026, 8, 12), True), (D(2026, 10, 3), False)]), self.COMPANY
        )


class WeekOffAgreementTests(DailyViewMixin, TestCase):
    """The grid, the calendar, the table and the regularise popover decide a week off the same way."""

    FROM, TO = datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)

    def setUp(self):
        super().setUp()
        from base.models import Department

        self.department = Department.objects.create(department="Roster Agreement")

    def roster(self, day, is_off):
        from base.models import Roster

        Roster.objects.create(
            employee=self.employee, date=day, department=self.department, is_off=is_off
        )

    def assign_roster(self):
        # Rostered 10th to 20th, with only the 14th off.
        for d in range(10, 21):
            self.roster(datetime.date(2026, 9, d), is_off=(d == 14))

    def patched(self):
        """The company's week-off days patched where the table and the shared rule both read them."""
        from contextlib import ExitStack
        from unittest.mock import patch

        saturdays = [datetime.date(2026, 9, d) for d in (5, 12, 19, 26)]
        stack = ExitStack()
        stack.enter_context(
            patch(
                "attendance.views.summary.get_company_leave_dates",
                return_value=saturdays,
            )
        )
        stack.enter_context(
            patch(
                "attendance.methods.leave_days.get_company_leave_dates",
                return_value=saturdays,
            )
        )
        return stack

    def panel(self, day):
        with self.patched():
            return self.client.get(
                reverse("attendance-monthly-summary-conflict-resolve"),
                {
                    "employee_id": self.employee.pk,
                    "date": day.isoformat(),
                    "from_date": self.FROM.isoformat(),
                    "to_date": self.TO.isoformat(),
                },
                HTTP_HX_REQUEST="true",
            )

    def cell(self, day):
        from attendance.views.summary import _build_calendar_context

        with self.patched():
            context = _build_calendar_context(self.employee, self.FROM, self.TO)
        return [
            c
            for m in context["months"]
            for w in m["weeks"]
            for c in w
            if c and c.get("date") == day
        ][0]

    def week_offs_in_table(self):
        from attendance.views.summary import build_monthly_summary
        from employee.models import Employee

        with self.patched():
            rows, _t, _x = build_monthly_summary(
                self.FROM, self.TO, Employee.objects.filter(pk=self.employee.pk)
            )
        return rows[0]["week_off"]

    def test_without_a_roster_the_company_days_are_week_offs_everywhere(self):
        self.assertEqual(
            self.panel(datetime.date(2026, 9, 12)).context["conflict_type"], "week_off"
        )
        self.assertEqual(self.cell(datetime.date(2026, 9, 12))["status"], "week_off")
        self.assertEqual(self.week_offs_in_table(), 4)

    def test_inside_the_roster_a_company_saturday_is_a_working_day_in_every_view(self):
        self.assign_roster()
        day = datetime.date(2026, 9, 12)
        self.assertNotEqual(self.cell(day)["status"], "week_off")
        self.assertEqual(self.panel(day).context["conflict_type"], "")

    def test_the_roster_day_off_is_a_week_off_in_every_view(self):
        self.assign_roster()
        day = datetime.date(2026, 9, 14)
        self.assertEqual(self.cell(day)["status"], "week_off")
        self.assertEqual(self.panel(day).context["conflict_type"], "week_off")

    def test_before_and_after_the_roster_the_company_days_apply_in_every_view(self):
        self.assign_roster()
        for day in (datetime.date(2026, 9, 5), datetime.date(2026, 9, 26)):
            with self.subTest(day=day):
                self.assertEqual(self.cell(day)["status"], "week_off")
                self.assertEqual(self.panel(day).context["conflict_type"], "week_off")

    def test_the_table_counts_the_same_week_offs(self):
        self.assign_roster()
        # The 5th (before), the 14th (the roster's), the 26th (after).
        self.assertEqual(self.week_offs_in_table(), 3)


class DailyWorkStatusDeprecationTests(DailyViewMixin, TestCase):
    """The old Daily Work Status page is off the menu and sends people to the Day-wise view."""

    def test_the_menu_no_longer_lists_daily_work_status(self):
        from attendance.sidebar import SUBMENUS

        labels = [str(item["menu"]) for item in SUBMENUS]
        self.assertNotIn("Daily Work Status", labels)
        self.assertIn("Monthly Summary", labels)
        self.assertFalse(
            any("work-status" in str(item.get("redirect", "")) for item in SUBMENUS)
        )

    def test_the_old_address_opens_the_day_wise_view(self):
        response = self.client.get(reverse("work-records"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"], reverse("attendance-monthly-summary") + "?view=daily"
        )

    def test_following_the_redirect_lands_on_the_day_wise_view(self):
        response = self.client.get(reverse("work-records"), follow=True)
        self.assertContains(response, 'id="ms-view" value="daily"')


class LabelCaseTests(DailyViewMixin, TestCase):
    """Labels and legends are in Title Case."""

    def test_the_subtitle_shows_the_filtered_range_not_the_month(self):
        context = self.client.get(
            reverse("attendance-monthly-summary-table"),
            {"view": "summary", "from_date": "2026-09-05", "to_date": "2026-09-12"},
            HTTP_HX_REQUEST="true",
        ).context
        self.assertEqual(context["period"], "05 Sep 2026 \u2013 12 Sep 2026")


class DefaultRangeTests(DailyViewMixin, TestCase):
    """Actions > Default Date Range: the range the summary opens on."""

    def test_modes_give_the_month_the_previous_month_and_the_pay_period(self):
        from attendance.methods.default_range import range_for
        from payroll.models.payroll_batch import PayPeriodSettings

        today = datetime.date(2026, 10, 28)
        company = self.employee.employee_work_info.company_id
        self.assertEqual(
            range_for("month", today),
            (datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)),
        )
        self.assertEqual(
            range_for("previous_month", today),
            (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)),
        )
        self.assertEqual(
            range_for("previous_month", datetime.date(2026, 1, 15)),
            (datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)),
        )
        PayPeriodSettings.objects.create(company_id=company, cycle_start_day=26)
        self.assertEqual(
            range_for("pay_period", today, company),
            (datetime.date(2026, 10, 26), datetime.date(2026, 11, 25)),
        )
        self.assertEqual(
            range_for("pay_period", datetime.date(2026, 10, 10), company),
            (datetime.date(2026, 9, 26), datetime.date(2026, 10, 25)),
        )

    def test_saving_a_mode_sets_the_cookie_and_the_page_opens_on_it(self):
        response = self.client.post(
            reverse("attendance-monthly-summary-default-range"),
            {"mode": "previous_month"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.cookies["ms_range"].value, "previous_month")
        page = self.client.get(reverse("attendance-monthly-summary"))
        last = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        self.assertEqual(page.context["from_date"], last.replace(day=1).isoformat())
        self.assertEqual(page.context["to_date"], last.isoformat())
        self.assertContains(page, "Default Date Range")

    def test_an_unknown_mode_is_refused(self):
        response = self.client.post(
            reverse("attendance-monthly-summary-default-range"), {"mode": "nope"}
        )
        self.assertEqual(response.status_code, 400)

    def test_the_table_falls_back_to_the_chosen_range(self):
        self.client.cookies["ms_range"] = "previous_month"
        response = self.client.get(
            reverse("attendance-monthly-summary-table"),
            {"view": "summary"},
            HTTP_HX_REQUEST="true",
        )
        last = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        self.assertContains(response, f"{last.replace(day=1):%d %b %Y}")

    def test_a_month_cycle_runs_a_full_month_from_the_chosen_day(self):
        from attendance.methods.default_range import range_for

        day = datetime.date
        self.assertEqual(
            range_for("custom", day(2026, 10, 28), start_day=15),
            (day(2026, 10, 15), day(2026, 11, 14)),
        )
        self.assertEqual(
            range_for("custom", day(2026, 10, 10), start_day=15),
            (day(2026, 9, 15), day(2026, 10, 14)),
        )
        self.assertEqual(
            range_for("custom", day(2026, 2, 10), start_day=31),
            (day(2026, 1, 31), day(2026, 2, 27)),
        )

    def test_a_start_day_is_saved_and_used(self):
        response = self.client.post(
            reverse("attendance-monthly-summary-default-range"),
            {"mode": "custom", "start_day": "15"},
        )
        start, end = response.json()["from_date"], response.json()["to_date"]
        self.assertEqual(start[-2:], "15")
        self.assertEqual(
            (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days
            + 1
            in range(28, 32),
            True,
        )
        page = self.client.get(reverse("attendance-monthly-summary"))
        self.assertEqual(
            (page.context["from_date"], page.context["to_date"]), (start, end)
        )
        self.assertEqual(page.context["start_day"], 15)

    def test_a_start_day_must_be_a_day_of_the_month(self):
        url = reverse("attendance-monthly-summary-default-range")
        self.assertEqual(
            self.client.post(url, {"mode": "custom", "start_day": "0"}).status_code, 400
        )
        self.assertEqual(
            self.client.post(url, {"mode": "custom", "start_day": "32"}).status_code,
            400,
        )
        self.assertEqual(self.client.post(url, {"mode": "custom"}).status_code, 400)

    def test_late_start_days_explain_what_short_months_do(self):
        from attendance.methods.default_range import start_day_choices

        notes = {day: note for day, _label, _rule, note in start_day_choices()}
        self.assertEqual(notes[28], "")
        self.assertIn("February", notes[30])
        self.assertIn("Fewer Than 30 Days", notes[30])
        self.assertIn("28th To The 31st", notes[31])

    def test_the_rule_line_is_filled_when_the_page_renders(self):
        page = self.client.get(reverse("attendance-monthly-summary"))
        html = page.content.decode()
        start = html.index('id="ms-range-preview-text">') + len(
            'id="ms-range-preview-text">'
        )
        self.assertEqual(
            html[start : html.index("</b>", start)].strip(),
            "Calendar Month (1st To Last Day)",
        )

    def test_the_chooser_names_rules_not_dates(self):
        page = self.client.get(reverse("attendance-monthly-summary"))
        for choice in page.context["range_choices"]:
            self.assertNotRegex(choice["text"], r"\d{4}")
        self.assertContains(page, "Calendar Month (1st To Last Day)")
        self.assertContains(page, "Month Cycle")
