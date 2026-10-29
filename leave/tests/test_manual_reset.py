"""Tests for manually running missed leave resets and telling them apart from
scheduler runs in the ledger."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse


class ManualResetTestBase(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee, make_user
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Manual Reset Co")
        self.user = make_user("manual_reset_user", is_superuser=True)
        self.employee = make_employee(
            company=company, email="manual-reset@test.horilla", user=self.user
        )
        self.other_employee = make_employee(
            company=company, email="manual-reset-2@test.horilla"
        )
        self.AvailableLeave = AvailableLeave
        self.leave_type = LeaveType.objects.create(
            name="Manual Reset Type",
            total_days=10,
            reset=True,
            reset_based="monthly",
            reset_day="1",
            carryforward_type="no carryforward",
        )

    def make_balance(self, employee=None, days_ago=5):
        return self.AvailableLeave.objects.create(
            employee_id=employee or self.employee,
            leave_type_id=self.leave_type,
            available_days=3,
            carryforward_days=0,
            total_leave_days=3,
            reset_date=date.today() - timedelta(days=days_ago),
        )


class ResetAvailableLeaveTests(ManualResetTestBase):
    def test_balance_not_due_is_left_alone(self):
        from leave.methods import reset_available_leave

        avail = self.make_balance(days_ago=-5)
        history_count = avail.history.count()

        applied = reset_available_leave(
            avail, date.today(), "Leave reset manually", "Carryforward expired manually"
        )

        avail.refresh_from_db()
        self.assertFalse(applied)
        self.assertEqual(avail.available_days, 3)
        self.assertEqual(avail.history.count(), history_count)

    def test_due_balance_is_reset_with_the_given_reason(self):
        from leave.methods import reset_available_leave

        avail = self.make_balance()

        applied = reset_available_leave(
            avail, date.today(), "Leave reset manually", "Carryforward expired manually"
        )

        avail.refresh_from_db()
        self.assertTrue(applied)
        self.assertEqual(avail.available_days, 10)
        self.assertGreater(avail.reset_date, date.today())
        latest = avail.history.order_by("-history_date").first()
        self.assertEqual(latest.history_change_reason, "Leave reset manually")

    def test_run_missed_resets_only_touches_due_balances(self):
        from leave.methods import run_missed_resets

        due = self.make_balance()
        not_due = self.make_balance(employee=self.other_employee, days_ago=-5)

        result = run_missed_resets(
            self.leave_type, "Leave reset manually", "Carryforward expired manually"
        )

        due.refresh_from_db()
        not_due.refresh_from_db()
        self.assertEqual(len(result["reset"]), 1)
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["reset"][0]["before"], 3)
        self.assertEqual(result["reset"][0]["after"], 10)
        self.assertEqual(due.available_days, 10)
        self.assertEqual(not_due.available_days, 3)

    def test_run_missed_resets_isolates_a_failing_balance(self):
        from unittest import mock

        from leave import methods

        first = self.make_balance()
        second = self.make_balance(employee=self.other_employee)
        real_reset = methods.reset_available_leave

        def fail_for_first(available_leave, *args, **kwargs):
            if available_leave.pk == first.pk:
                raise ValueError("boom")
            return real_reset(available_leave, *args, **kwargs)

        with mock.patch.object(methods, "reset_available_leave", fail_for_first):
            result = methods.run_missed_resets(
                self.leave_type, "Leave reset manually", "Carryforward expired manually"
            )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(len(result["reset"]), 1)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["error"], "boom")
        self.assertEqual(first.available_days, 3)
        self.assertEqual(second.available_days, 10)

    def test_is_reset_due_follows_the_reset_flag_and_dates(self):
        due = self.make_balance()
        future = self.make_balance(employee=self.other_employee, days_ago=-5)
        self.assertTrue(due.is_reset_due())
        self.assertFalse(future.is_reset_due())

        self.leave_type.reset = False
        self.leave_type.save()
        due.refresh_from_db()
        self.assertFalse(due.is_reset_due())

    def test_leave_type_has_due_resets_only_when_a_balance_is_overdue(self):
        self.assertFalse(self.leave_type.has_due_resets())

        self.make_balance(days_ago=-5)
        self.assertFalse(self.leave_type.has_due_resets())

        self.make_balance(employee=self.other_employee)
        self.assertTrue(self.leave_type.has_due_resets())

        self.leave_type.reset = False
        self.leave_type.save()
        self.assertFalse(self.leave_type.has_due_resets())

    def test_due_reset_count_counts_only_overdue_balances(self):
        self.assertEqual(self.leave_type.due_reset_count(), 0)

        self.make_balance(days_ago=-5)
        self.assertEqual(self.leave_type.due_reset_count(), 0)

        self.make_balance(employee=self.other_employee)
        self.assertEqual(self.leave_type.due_reset_count(), 1)

        self.leave_type.reset = False
        self.leave_type.save()
        self.assertEqual(self.leave_type.due_reset_count(), 0)


class LedgerSourceTests(ManualResetTestBase):
    def test_scheduler_reset_is_marked_scheduled(self):
        from leave.scheduler import leave_reset

        avail = self.make_balance()
        leave_reset()

        row = avail.build_ledger()[0]
        self.assertEqual(row["label"], "Leave reset")
        self.assertEqual(row["source"], "scheduler")
        self.assertIsNone(row["by"])

    def test_manual_reset_is_marked_manual_with_the_user(self):
        from leave.methods import reset_available_leave

        avail = self.make_balance()
        avail._history_user = self.user
        reset_available_leave(
            avail, date.today(), "Leave reset manually", "Carryforward expired manually"
        )

        row = avail.build_ledger()[0]
        self.assertEqual(row["label"], "Leave reset manually")
        self.assertEqual(row["source"], "manual")
        self.assertEqual(row["by"], self.employee.get_full_name())

    def test_rows_without_a_reason_have_no_source(self):
        avail = self.make_balance(days_ago=-5)
        row = avail.build_ledger()[0]
        self.assertIsNone(row.get("source"))


class ManualResetViewTests(ManualResetTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def post(self, url_name, pk):
        return self.client.post(reverse(url_name, args=[pk]), HTTP_HX_REQUEST="true")

    def test_ledger_reset_view_resets_a_due_balance(self):
        avail = self.make_balance()

        response = self.post("leave-balance-reset", avail.id)

        avail.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(avail.available_days, 10)
        self.assertContains(response, "Leave reset manually")
        self.assertContains(response, "Manual")

    def test_ledger_reset_view_refuses_a_balance_not_due(self):
        avail = self.make_balance(days_ago=-5)

        response = self.post("leave-balance-reset", avail.id)

        avail.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(avail.available_days, 3)

    def test_ledger_reset_view_refuses_a_non_resetting_leave_type(self):
        avail = self.make_balance()
        self.leave_type.reset = False
        self.leave_type.save()

        self.post("leave-balance-reset", avail.id)

        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 3)

    def test_ledger_reset_view_rejects_get(self):
        avail = self.make_balance()
        response = self.client.get(
            reverse("leave-balance-reset", args=[avail.id]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 405)

    def test_ledger_sidebar_offers_the_button_only_when_overdue(self):
        overdue = self.make_balance()
        future = self.make_balance(employee=self.other_employee, days_ago=-5)

        overdue_page = self.client.get(
            reverse("leave-balance-ledger", args=[overdue.id]), HTTP_HX_REQUEST="true"
        )
        future_page = self.client.get(
            reverse("leave-balance-ledger", args=[future.id]), HTTP_HX_REQUEST="true"
        )

        self.assertContains(overdue_page, "Run missed reset")
        self.assertNotContains(future_page, "Run missed reset")

    def test_leave_type_view_resets_only_overdue_balances(self):
        due = self.make_balance()
        not_due = self.make_balance(employee=self.other_employee, days_ago=-5)

        response = self.post("leave-type-run-missed-resets", self.leave_type.id)

        due.refresh_from_db()
        not_due.refresh_from_db()
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["reset"], 1)
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["not_due"], 1)
        self.assertEqual(
            data["reset_rows"],
            [{"name": str(self.employee), "before": 3, "after": 10}],
        )
        self.assertEqual(data["failed_rows"], [])
        self.assertEqual(due.available_days, 10)
        self.assertEqual(not_due.available_days, 3)

    def test_leave_type_view_ignores_a_non_resetting_type(self):
        avail = self.make_balance()
        self.leave_type.reset = False
        self.leave_type.save()

        response = self.post("leave-type-run-missed-resets", self.leave_type.id)

        avail.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        self.assertEqual(avail.available_days, 3)

    def test_leave_type_view_rejects_get(self):
        response = self.client.get(
            reverse("leave-type-run-missed-resets", args=[self.leave_type.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 405)


class CompanyScopeTests(ManualResetTestBase):
    def setUp(self):
        super().setUp()
        from horilla.horilla_middlewares import current_company_id
        from horilla.testkit import make_company, make_employee

        self.current_company_id = current_company_id
        other_company = make_company("Scope Other Co", hq=False)
        self.outsider = make_employee(
            company=other_company, email="scope-outsider@test.horilla"
        )
        self.inside = self.make_balance()
        self.outside = self.make_balance(employee=self.outsider)
        self.inside_company_id = self.employee.employee_work_info.company_id.pk

    def select_company(self):
        token = self.current_company_id.set(self.inside_company_id)
        self.addCleanup(self.current_company_id.reset, token)
        return token

    def test_count_and_run_stay_inside_the_selected_company(self):
        from leave.methods import run_missed_resets

        self.select_company()

        self.assertEqual(self.leave_type.due_reset_count(), 1)
        result = run_missed_resets(
            self.leave_type, "Leave reset manually", "Carryforward expired manually"
        )

        self.inside.refresh_from_db()
        self.outside.refresh_from_db()
        self.assertEqual(len(result["reset"]), 1)
        self.assertEqual(self.inside.available_days, 10)
        self.assertEqual(self.outside.available_days, 3)

    def test_without_a_selected_company_every_balance_is_handled(self):
        from leave.methods import run_missed_resets

        self.assertEqual(self.leave_type.due_reset_count(), 2)
        result = run_missed_resets(
            self.leave_type, "Leave reset", "Carryforward expired"
        )

        self.inside.refresh_from_db()
        self.outside.refresh_from_db()
        self.assertEqual(len(result["reset"]), 2)
        self.assertEqual(self.inside.available_days, 10)
        self.assertEqual(self.outside.available_days, 10)


class ManualResetUserAndNameTests(ManualResetTestBase):
    def test_user_without_an_employee_is_shown_by_username(self):
        from horilla.testkit import make_user
        from leave.methods import reset_available_leave

        bare_user = make_user("no_employee_user")
        avail = self.make_balance()
        avail._history_user = bare_user
        reset_available_leave(
            avail, date.today(), "Leave reset manually", "Carryforward expired manually"
        )

        row = avail.build_ledger()[0]
        self.assertEqual(row["source"], "manual")
        self.assertEqual(row["by"], "no_employee_user")

    def test_view_returns_unusual_employee_names_verbatim(self):
        from horilla.testkit import make_employee

        odd_employee = make_employee(
            company=self.employee.employee_work_info.company_id,
            email="odd-names@test.horilla",
            first_name='Zoë O\'Brien "Q"',
            last_name="مرحبا <b>",
        )
        self.make_balance(employee=odd_employee)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("leave-type-run-missed-resets", args=[self.leave_type.id]),
            HTTP_HX_REQUEST="true",
        )

        names = [row["name"] for row in response.json()["reset_rows"]]
        self.assertIn(str(odd_employee), names)

    def test_row_template_escapes_the_leave_type_name_for_javascript(self):
        from django.contrib.auth.context_processors import PermWrapper
        from django.template.loader import render_to_string

        self.leave_type.name = 'Sam\'s "Special" <Leave> مرحبا'
        self.leave_type.save()
        self.make_balance()

        html = render_to_string(
            "cbv/leave_types/leave_type_list_actions.html",
            {"instance": self.leave_type, "perms": PermWrapper(self.user)},
        )

        self.assertIn("runLeaveTypeReset(", html)
        self.assertIn("Sam\\u0027s", html)
        self.assertIn("\\u0022Special\\u0022", html)
        self.assertIn("مرحبا", html)
        self.assertNotIn("<Leave>", html)
        self.assertNotIn("Sam's", html)
