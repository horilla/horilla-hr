"""
Fixing attendance from the payroll run review.

An unresolved conflict is the one thing that blocks a run, and the fix for it
lived on another screen. Going there, resolving it, coming back and running the
review again is a round trip that gets skipped -- so the calendar and its
conflict resolution are hosted on the review itself.

The modal and its JavaScript were lifted out of the attendance summary table
into a shared partial. These check both ends of that: the review can open it,
and the page it came from still can. There were no tests over that template
before, so this is the only thing standing between the extraction and a
silently dead click handler.
"""

from datetime import date
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract
from payroll.views.batch_views import SESSION_KEY

HOST = "attendance/monthly_summary/_calendar_modal_host.html"

START = date(2026, 4, 1)
END = date(2026, 4, 30)

CLEAN = {
    "present": 22,
    "paid_leave": 0,
    "unpaid_leave": 0,
    "absent": 0,
    "week_off": 8,
    "holiday": 0,
    "total_working": 22,
    "unresolved_conflicts": 0,
    "overtime_label": "0h 00m",
}


class HostPartialTests(TestCase):
    """The extracted partial, on its own."""

    def setUp(self):
        self.body = render_to_string(HOST)

    def test_it_carries_the_modal_the_calendar_is_loaded_into(self):
        self.assertIn('id="cal-modal-overlay"', self.body)
        self.assertIn('id="cal-modal-content"', self.body)

    def test_it_exposes_the_opener_by_name(self):
        """
        A closure-local function would be unreachable from a second page.
        """
        self.assertIn("window.openAttendanceCalendar", self.body)

    def test_the_resolve_helpers_come_with_it(self):
        """
        The calendar's cells call these by name. Scripts inserted through
        innerHTML do not execute, so they cannot live in the modal template --
        if they did not come across, every conflict cell would be dead.
        """
        self.assertIn("window.msCalLoadResolve", self.body)
        self.assertIn("window.msCalResolvePost", self.body)

    def test_any_element_with_a_calendar_url_opens_it(self):
        """
        Delegated rather than bound to .ms-summary-row, so the review's own
        button works without the partial knowing anything about it.
        """
        self.assertIn("[data-calendar-url]", self.body)


class SummaryTableStillWorksTests(TestCase):
    """The page the partial was taken out of."""

    def test_the_table_includes_the_host_rather_than_its_own_copy(self):
        source = "attendance/templates/attendance/monthly_summary/table_partial.html"
        with open(source, encoding="utf-8") as handle:
            body = handle.read()

        self.assertIn(HOST, body)
        self.assertIn("data-calendar-url", body)
        # The old copy is gone -- two modals with the same element ids on one
        # page would have the second one's JavaScript driving the first one's
        # markup.
        self.assertNotIn('id="cal-modal-overlay"', body)
        self.assertNotIn("window.msCalResolvePost", body)


class ReviewPageTests(TestCase):
    def setUp(self):
        self.user = make_user("regadmin", is_superuser=True)
        self.company = make_company("Reg Co")
        make_employee(
            company=self.company, email="regadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.employee = make_employee(
            company=self.company, email="reg@test.horilla", first_name="Reg"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

        session = self.client.session
        session[SESSION_KEY] = {
            "batch_name": "April",
            "period_start": START.isoformat(),
            "period_end": END.isoformat(),
            "employee_ids": [self.employee.pk],
        }
        session.save()

    def review(self, **overrides):
        summary = dict(CLEAN)
        summary.update(overrides)
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value={self.employee.pk: summary},
        ):
            return self.client.get(reverse("payroll-batch-review"))

    def test_the_review_hosts_the_calendar(self):
        response = self.review()
        self.assertContains(response, "cal-modal-overlay")
        self.assertContains(response, "window.openAttendanceCalendar")

    def test_each_row_can_open_that_employees_period(self):
        """
        The employee and the exact period being paid -- not today's month.
        Regularising the wrong month would leave the run blocked and look like
        the fix did nothing.
        """
        response = self.review()
        body = response.content.decode()

        self.assertIn(f"employee_id={self.employee.pk}", body)
        self.assertIn("from_date=2026-04-01", body)
        self.assertIn("to_date=2026-04-30", body)

    def test_a_blocked_row_offers_to_regularise(self):
        response = self.review(unresolved_conflicts=2)
        self.assertContains(response, "Regularise attendance")

    def test_an_unblocked_row_still_offers_the_calendar(self):
        """Worth reaching even when nothing is wrong -- to check, not to fix."""
        response = self.review()
        self.assertContains(response, "Open attendance")
        self.assertNotContains(response, "Regularise attendance")

    def test_every_row_carries_the_keys_search_and_sort_read(self):
        """
        Both are done in the browser -- review() recomputes every employee's
        attendance, so ordering a column server-side would re-run all of it to
        move rows around. The keys therefore have to be on the rows.
        """
        response = self.review(present=11, absent=4)
        body = response.content.decode()

        # No closing quote: str(Employee) appends the badge id, which is
        # empty here and leaves a trailing space. In the real app this reads
        # "Alice Fixture (FX01)" -- which is why the search covers both.
        self.assertIn('data-pbname="Reg Employee', body)
        self.assertIn('data-present="11"', body)
        self.assertIn('data-absent="4"', body)
        self.assertIn('data-blocked="0"', body)

    def test_overtime_sorts_by_seconds_not_by_its_label(self):
        """
        The column reads "44h 30m", which as text sorts before "5h 00m".
        """
        response = self.review(overtime_seconds=160200, overtime_label="44h 30m")
        body = response.content.decode()

        self.assertIn('data-overtime="160200"', body)
        self.assertIn("44h 30m", body)

    def test_a_blocked_row_is_marked_so_the_default_order_can_be_restored(self):
        response = self.review(unresolved_conflicts=1)
        self.assertContains(response, 'data-blocked="1"')
        self.assertContains(response, "data-sort-reset")

    def test_every_column_is_sortable(self):
        response = self.review()
        body = response.content.decode()

        for key in (
            "pbname",
            "present",
            "paidleave",
            "unpaidleave",
            "absent",
            "weekoff",
            "holiday",
            "working",
            "paiddays",
            "overtime",
        ):
            with self.subTest(column=key):
                self.assertIn(f'data-sort-key="{key}"', body)

    def test_every_sortable_column_shows_its_sort_indicator(self):
        """
        One arrow element per sortable header, present from the start -- a
        control that only appears once you are already pointing at the column
        does not tell you the column is sortable.
        """
        response = self.review()
        body = response.content.decode()

        sortable = body.count('class="pb__sortable"') + body.count(
            'class="pb__num pb__sortable"'
        )
        self.assertEqual(sortable, 10)
        self.assertEqual(body.count('<span class="pb__arrow"></span>'), 10)

    def test_the_contract_can_be_edited_from_the_row(self):
        """
        The other blocking problem -- no wage, no hourly rate, no earning
        marked as basic pay -- is fixed on the contract. Same reasoning as the
        attendance calendar: the fix belongs beside the line reporting it.
        """
        response = self.review()
        contract = self.employee.contract_set.filter(contract_status="active").first()

        self.assertContains(
            response, reverse("update-contract", args=[contract.pk]) + "?modal=1"
        )

    def test_the_modal_the_contract_form_lands_in_is_on_the_page(self):
        """
        #relatedObjectModal is included per page, not in the base template, so
        a page that opens one has to bring it -- otherwise the form is fetched
        into an element that does not exist and nothing appears.
        """
        response = self.review()
        self.assertContains(response, 'id="relatedObjectModalBody"')

    def test_the_blocked_banner_is_actually_visible(self):
        """
        .oh-alert is opacity:0 in the app stylesheet -- only .oh-alert--animated
        reveals it, with a keyframe that ends hidden again. A persistent banner
        using it renders as an invisible block holding open a gap, which is
        exactly how it looked.
        """
        response = self.review(unresolved_conflicts=1)
        body = response.content.decode()

        self.assertIn("pb__alert--danger", body)
        self.assertNotIn("oh-alert--danger", body)

    def test_the_figures_size_to_their_content(self):
        """
        Without this the label column took most of the width and every
        two-word header wrapped, which is what pushed the sort arrows onto a
        line of their own.
        """
        response = self.review()
        body = response.content.decode()

        # Overtime is a duration: right-aligned with the counts, not left.
        self.assertIn('data-sort-key="overtime"', body)
        self.assertEqual(body.count('class="pb__num pb__sortable"'), 9)

    def test_few_paid_days_is_counted_and_marked(self):
        """
        Not a blocker -- a mid-month joiner or a long sickness legitimately has
        few paid days -- but on a list of two hundred it is the handful worth
        checking before the payslips exist rather than after.
        """
        response = self.review(paid_days=4)

        self.assertEqual(response.context["low_paid_count"], 1)
        self.assertContains(response, "pb__low")

    def test_a_full_month_is_not_flagged(self):
        response = self.review(paid_days=30)
        self.assertEqual(response.context["low_paid_count"], 0)

    def test_a_blocked_row_is_not_double_counted(self):
        """
        It is already reported as blocked; counting it twice would make the
        two figures overlap and neither of them mean anything on its own.
        """
        response = self.review(paid_days=0, unresolved_conflicts=1)

        self.assertEqual(response.context["blocked_count"], 1)
        self.assertEqual(response.context["low_paid_count"], 0)

    def test_the_search_box_is_there(self):
        response = self.review()
        self.assertContains(response, "data-row-search")
        self.assertContains(response, "data-no-match")

    def test_the_review_can_be_re_run_after_fixing(self):
        """
        Resolving a conflict changes nothing on the page that is already open.
        Without a way back to a fresh review, the blocked count stays stale and
        the run stays blocked.
        """
        response = self.review(unresolved_conflicts=1)
        self.assertContains(response, "Re-check")

        # And the second look is genuinely recomputed, not cached: the same
        # request with the conflict gone reports nobody blocked.
        self.assertEqual(self.review().context["blocked_count"], 0)
