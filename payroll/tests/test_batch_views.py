"""
The payroll run screens, end to end.

These check the things a template cannot be trusted to enforce: that a blocked
employee is actually dropped from the run rather than merely shown in red,
that a status the state machine forbids is refused by the view and not only
hidden from the dropdown, and that the set reviewed is the set generated.
"""

import logging
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user
from payroll.methods import batch_run
from payroll.models.models import (
    Contract,
    PayPeriodSettings,
    PayrollBatch,
    PayrollBatchLine,
    Payslip,
)
from payroll.tests.factories_payroll import make_active_contract
from payroll.views.batch_views import SESSION_KEY

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


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("runadmin", is_superuser=True)
        self.company = make_company("Run Co")
        make_employee(
            company=self.company, email="runadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.people = []
        for name in ("Ann", "Ben"):
            employee = make_employee(
                company=self.company,
                email=f"{name.lower()}@run.horilla",
                first_name=name,
            )
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(employee, wage=30000.0)
            self.people.append(employee)

    def summaries(self, per_employee=None):
        rows = {employee.pk: dict(CLEAN) for employee in self.people}
        for pk, overrides in (per_employee or {}).items():
            rows[pk].update(overrides)
        return rows

    def stash(self, employees=None):
        """Put the wizard where step two expects to find it."""
        session = self.client.session
        session[SESSION_KEY] = {
            "batch_name": "April",
            "period_start": START.isoformat(),
            "period_end": END.isoformat(),
            "employee_ids": [e.pk for e in (employees or self.people)],
        }
        session.save()


class ListTests(Fixture):
    def test_an_empty_list_offers_the_wizard(self):
        response = self.client.get(reverse("payroll-batch-home"))
        self.assertContains(response, reverse("payroll-batch-scope"))

    def test_the_figures_come_from_the_runs(self):
        PayrollBatch.objects.create(
            batch_name="March",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            generated_count=7,
            total_net=1234.0,
            flagged_count=2,
        )
        response = self.client.get(reverse("payroll-batch-home"))
        self.assertEqual(response.context["kpi"]["employees"], 7)
        self.assertEqual(response.context["kpi"]["flagged"], 2)
        self.assertEqual(response.context["kpi"]["unpaid"], 1)


class ScopeTests(Fixture):
    def test_the_dates_default_to_last_months_pay_period(self):
        """Payroll is run once the month is over, so the finished month is the default."""
        response = self.client.get(reverse("payroll-batch-scope"))
        form = response.context["form"]
        last_month_day = date.today().replace(day=1) - timedelta(days=1)
        start, end = PayPeriodSettings().period_for(last_month_day)
        self.assertEqual(form.initial["period_start"], start)
        self.assertEqual(form.initial["period_end"], end)
        self.assertEqual(form.initial["batch_name"], start.strftime("%B %Y"))
        self.assertLess(end, date.today())

    def test_choosing_everyone_records_everyone(self):
        self.client.post(
            reverse("payroll-batch-scope"),
            {
                "batch_name": "April",
                "period_start": START.isoformat(),
                "period_end": END.isoformat(),
                "scope": "all",
            },
        )
        stashed = self.client.session[SESSION_KEY]
        # Everyone with an active contract, which includes the admin -- an
        # Employee gets one on save. The point is that the set is derived
        # from contracts rather than from whoever was typed into the picker.
        expected = Employee.objects.filter(
            is_active=True,
            contract_set__isnull=False,
            contract_set__contract_status="active",
        ).values_list("pk", flat=True)
        self.assertCountEqual(stashed["employee_ids"], list(expected))
        for employee in self.people:
            self.assertIn(employee.pk, stashed["employee_ids"])

    def test_a_future_period_is_refused(self):
        response = self.client.post(
            reverse("payroll-batch-scope"),
            {
                "batch_name": "Next year",
                "period_start": "2099-01-01",
                "period_end": "2099-01-31",
                "scope": "all",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_review_without_a_scope_returns_to_the_start(self):
        response = self.client.get(reverse("payroll-batch-review"))
        self.assertRedirects(response, reverse("payroll-batch-scope"))


class ReviewTests(Fixture):
    def review(self, summaries):
        self.stash()
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value=summaries,
        ):
            return self.client.get(reverse("payroll-batch-review"))

    def test_the_attendance_each_person_will_be_paid_from_is_shown(self):
        response = self.review(self.summaries())
        self.assertEqual(response.context["ready_count"], 2)
        self.assertContains(response, "Ann")
        self.assertContains(response, "Ben")

    def test_a_conflict_blocks_and_the_count_drops(self):
        blocked = self.people[0].pk
        response = self.review(self.summaries({blocked: {"unresolved_conflicts": 3}}))
        self.assertEqual(response.context["blocked_count"], 1)
        self.assertEqual(response.context["ready_count"], 1)

    def test_nothing_is_created_by_looking(self):
        self.review(self.summaries())
        self.assertEqual(PayrollBatch.objects.count(), 0)
        self.assertEqual(Payslip.objects.count(), 0)


class StartTests(Fixture):
    def start(self, summaries):
        self.stash()
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value=summaries,
        ):
            return self.client.post(reverse("payroll-batch-start"))

    def test_the_run_is_created_and_the_browser_goes_to_the_progress_page(self):
        response = self.start(self.summaries())
        batch = PayrollBatch.objects.get()
        self.assertRedirects(
            response, reverse("payroll-batch-progress", args=[batch.pk])
        )
        self.assertEqual(batch.employee_count, 2)

    def test_a_blocked_employee_is_not_in_the_run(self):
        """
        The point of the review step. Red text on a row that gets generated
        anyway would be worse than no review at all.
        """
        blocked = self.people[0]
        self.start(self.summaries({blocked.pk: {"unresolved_conflicts": 1}}))

        batch = PayrollBatch.objects.get()
        self.assertEqual(batch.employee_count, 1)
        self.assertNotIn(
            blocked.pk, list(batch.lines.values_list("employee_id", flat=True))
        )

    def test_nothing_is_created_when_everyone_is_blocked(self):
        everyone = {
            employee.pk: {"unresolved_conflicts": 1} for employee in self.people
        }
        response = self.start(self.summaries(everyone))
        self.assertEqual(PayrollBatch.objects.count(), 0)
        self.assertRedirects(response, reverse("payroll-batch-review"))

    def test_the_scope_is_cleared_so_it_cannot_be_run_twice(self):
        self.start(self.summaries())
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_a_get_cannot_start_a_run(self):
        self.stash()
        self.client.get(reverse("payroll-batch-start"))
        self.assertEqual(PayrollBatch.objects.count(), 0)


class ProgressTests(Fixture):
    def setUp(self):
        super().setUp()
        self.batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        self.url = reverse("payroll-batch-generate", args=[self.batch.pk])

    def test_the_slice_endpoint_is_htmx_only(self):
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_an_unfinished_run_asks_for_the_next_slice(self):
        """
        The loop: each response that is not finished carries the hx-get that
        fetches the next one. Without it the bar renders once and stops.

        generate_slice is stubbed to do nothing, because two employees fit in
        one slice -- a real call would finish the run and the fragment would
        correctly stop asking, which is the opposite of what is under test.
        """
        with patch.object(batch_run, "generate_slice", return_value=1):
            response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.assertContains(response, 'hx-trigger="load')
        self.assertContains(response, self.url)

    def test_a_finished_run_stops_asking(self):
        self.batch.progress_state = PayrollBatch.DONE
        self.batch.save()
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertNotContains(response, "hx-trigger")

    def test_a_failure_inside_the_slice_is_reported_not_swallowed(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        with patch.object(
            batch_run, "generate_slice", side_effect=RuntimeError("database gone")
        ):
            response = self.client.get(self.url, HTTP_HX_REQUEST="true")

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.progress_state, PayrollBatch.FAILED)
        self.assertIn("database gone", self.batch.last_error)
        self.assertContains(response, "database gone")


class StatusTests(Fixture):
    def setUp(self):
        super().setUp()
        self.batch = PayrollBatch.objects.create(
            batch_name="April",
            period_start=START,
            period_end=END,
            progress_state=PayrollBatch.DONE,
            employee_count=1,
        )
        self.payslip = Payslip.objects.create(
            employee_id=self.people[0],
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=1,
            contract_wage=1,
            gross_pay=1,
            deduction=0,
            net_pay=1,
            pay_head_data={},
            payroll_batch=self.batch,
        )
        self.url = reverse("payroll-batch-set-status", args=[self.batch.pk])

    def test_an_allowed_move_sticks(self):
        self.client.post(self.url, {"status": PayrollBatch.APPROVED})
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, PayrollBatch.APPROVED)

    def test_the_payslips_follow_the_run(self):
        """
        A run marked paid whose payslips still read draft is the disagreement
        that makes both untrustworthy.
        """
        self.client.post(self.url, {"status": PayrollBatch.APPROVED})
        self.client.post(self.url, {"status": PayrollBatch.PAID})

        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.status, "paid")

    def test_the_payslips_follow_the_run_backwards_too(self):
        """
        A run sent back to draft whose payslips still read "confirmed" is the
        same disagreement as the forward case, and easier to miss.
        """
        self.client.post(self.url, {"status": PayrollBatch.APPROVED})
        self.client.post(self.url, {"status": PayrollBatch.REVIEW})

        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.status, "review_ongoing")

    def test_cancelling_takes_the_payslips_off_confirmed(self):
        self.client.post(self.url, {"status": PayrollBatch.APPROVED})
        self.client.post(self.url, {"status": PayrollBatch.CANCELLED})

        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.status, "draft")

    def test_a_forbidden_move_is_refused_by_the_view(self):
        """
        Not only hidden in the dropdown. A template only hides a button.
        """
        self.batch.status = PayrollBatch.PAID
        self.batch.save()

        self.client.post(self.url, {"status": PayrollBatch.DRAFT})
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, PayrollBatch.PAID)

    def test_approving_an_unfinished_run_is_refused(self):
        self.batch.progress_state = PayrollBatch.RUNNING
        self.batch.save()

        self.client.post(self.url, {"status": PayrollBatch.APPROVED})
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, PayrollBatch.DRAFT)


class DeleteTests(Fixture):
    def setUp(self):
        super().setUp()
        self.batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        self.payslip = Payslip.objects.create(
            employee_id=self.people[0],
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=1,
            contract_wage=1,
            gross_pay=1,
            deduction=0,
            net_pay=1,
            pay_head_data={},
            payroll_batch=self.batch,
        )
        self.url = reverse("payroll-batch-delete", args=[self.batch.pk])

    def test_a_draft_run_and_its_payslips_go(self):
        self.client.post(self.url)

        self.assertFalse(PayrollBatch.objects.filter(pk=self.batch.pk).exists())
        self.assertFalse(Payslip.objects.filter(pk=self.payslip.pk).exists())

    def test_a_paid_run_is_refused(self):
        """
        It is the record of money that left the business. Correcting it means
        another run, not deleting the evidence.
        """
        self.batch.progress_state = PayrollBatch.DONE
        self.batch.status = PayrollBatch.PAID
        self.batch.save()

        self.client.post(self.url)
        self.assertTrue(PayrollBatch.objects.filter(pk=self.batch.pk).exists())

    def test_a_get_does_not_delete(self):
        self.client.get(self.url)
        self.assertTrue(PayrollBatch.objects.filter(pk=self.batch.pk).exists())

    def test_the_payslips_are_not_left_orphaned(self):
        """
        They exist only because this run made them. Left behind they would sit
        in the payslip list with nothing saying where they came from.
        """
        self.client.post(self.url)
        self.assertEqual(Payslip.objects.count(), 0)


class DetailTests(Fixture):
    def test_the_failures_are_listed_with_their_reason(self):
        batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        line = batch.lines.first()
        line.status = PayrollBatchLine.FAILED
        line.message = "No basic pay could be worked out"
        line.save()

        response = self.client.get(reverse("payroll-batch-detail", args=[batch.pk]))
        self.assertContains(response, "No basic pay could be worked out")


class PayPeriodTests(Fixture):
    def test_saving_creates_the_row_for_this_company(self):
        self.client.post(
            reverse("pay-period-settings"),
            {"boundary": "calendar_month", "pay_day_offset": 3, "input_cutoff_days": 2},
        )
        settings = PayPeriodSettings.objects.entire().get()
        self.assertEqual(settings.pay_day_offset, 3)

    def test_the_pay_date_shown_follows_the_offset(self):
        PayPeriodSettings.objects.create(pay_day_offset=5)
        response = self.client.get(reverse("pay-period-settings"))
        self.assertEqual(
            (
                response.context["example_pay_date"] - response.context["example_end"]
            ).days,
            5,
        )

    def test_opening_the_page_does_not_write_a_row(self):
        """``for_company`` returns an unsaved default deliberately."""
        self.client.get(reverse("pay-period-settings"))
        self.assertEqual(PayPeriodSettings.objects.entire().count(), 0)


class ReopenTests(DeleteTests):
    """Back to "Check the inputs" from a draft run (inherits its draft run and payslip)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("payroll-batch-reopen", args=[self.batch.pk])

    def test_a_draft_run_goes_back_to_the_review_step_with_the_same_people(self):
        response = self.client.post(self.url)

        self.assertRedirects(
            response, reverse("payroll-batch-review"), fetch_redirect_response=False
        )
        self.assertFalse(PayrollBatch.objects.filter(pk=self.batch.pk).exists())
        self.assertFalse(Payslip.objects.filter(pk=self.payslip.pk).exists())
        state = self.client.session[SESSION_KEY]
        self.assertEqual(state["batch_name"], "April")
        self.assertEqual(state["period_start"], START.isoformat())
        self.assertEqual(state["period_end"], END.isoformat())
        self.assertCountEqual(state["employee_ids"], [e.pk for e in self.people])

    def test_a_run_whose_payslips_moved_on_is_refused(self):
        Payslip.objects.filter(pk=self.payslip.pk).update(status="confirmed")
        self.client.post(self.url)
        self.assertTrue(PayrollBatch.objects.filter(pk=self.batch.pk).exists())
        self.assertTrue(Payslip.objects.filter(pk=self.payslip.pk).exists())

    def test_a_run_that_is_not_draft_is_refused(self):
        self.batch.status = PayrollBatch.REVIEW
        self.batch.save()
        self.client.post(self.url)
        self.assertTrue(PayrollBatch.objects.filter(pk=self.batch.pk).exists())

    def test_a_get_changes_nothing(self):
        self.client.get(self.url)
        self.assertTrue(PayrollBatch.objects.filter(pk=self.batch.pk).exists())
