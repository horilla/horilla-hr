"""Tests for AvailableLeave.build_ledger() and the leave-balance-ledger view."""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.test import TestCase, override_settings


class LeaveLedgerBuildTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Ledger Co")
        self.employee = make_employee(company=company, email="ledger@test.horilla")
        self.LeaveType = LeaveType
        self.AvailableLeave = AvailableLeave

    def test_manual_edit_via_update_form_is_tracked(self):
        from leave.forms import AvailableLeaveUpdateForm

        lt = self.LeaveType.objects.create(
            name="Manual Edit Verify Type",
            total_days=5,
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )

        form = AvailableLeaveUpdateForm(
            {"available_days": 8, "carryforward_days": 0}, instance=avail
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(avail.history.count(), 2)
        ledger = avail.build_ledger()
        self.assertEqual(len(ledger), 2)
        # Newest first -- the manual edit is the latest entry, at index 0.
        self.assertEqual(ledger[0]["label"], "Balance updated")
        self.assertEqual(ledger[0]["credit"], 3)
        self.assertEqual(ledger[0]["balance"], 8)

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_entry_is_dated_by_the_local_calendar_not_utc(self):
        """
        20:00 UTC on 10 Jan is 01:30 on 11 Jan in India. History timestamps
        are stored in UTC, so taking .date() directly dated this edit a day
        early -- and made two ledger tests fail whenever CI ran between
        18:30 and 24:00 UTC.
        """
        from leave.forms import AvailableLeaveUpdateForm

        lt = self.LeaveType.objects.create(
            name="Ledger TZ Type", total_days=5, carryforward_type="no carryforward"
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            assigned_date=date(2026, 1, 10),
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )
        form = AvailableLeaveUpdateForm(
            {"available_days": 8, "carryforward_days": 0}, instance=avail
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        created, edited = avail.history.order_by("history_date")
        # Same UTC day for both, keeping their real order: the edit lands
        # after local midnight, the creation before it.
        avail.history.filter(pk=created.pk).update(
            history_date=datetime(2026, 1, 10, 10, 0, tzinfo=dt_timezone.utc)
        )
        avail.history.filter(pk=edited.pk).update(
            history_date=datetime(2026, 1, 10, 20, 0, tzinfo=dt_timezone.utc)
        )

        ledger = avail.build_ledger()

        self.assertEqual(ledger[0]["label"], "Balance updated")
        self.assertEqual(ledger[0]["date"], date(2026, 1, 11))

    def test_opening_balance_from_first_history_row(self):
        lt = self.LeaveType.objects.create(
            name="Ledger Opening Type",
            total_days=5,
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )

        ledger = avail.build_ledger()

        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["label"], "Initial assignment")
        self.assertEqual(ledger[0]["credit"], 5)
        self.assertEqual(ledger[0]["debit"], 0)
        self.assertEqual(ledger[0]["balance"], 5)

    def test_initial_carryforward_is_its_own_row(self):
        """
        An AvailableLeave created with a non-zero starting carryforward
        (e.g. imported from an older system, or backdated data) must show
        that portion as its own labeled row -- not silently folded into
        "Initial assignment" -- so it's just as visible as every later
        change.
        """
        lt = self.LeaveType.objects.create(
            name="Ledger Carryforward Type",
            total_days=5,
            carryforward_type="carryforward",
            carryforward_max=10,
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            carryforward_days=3,
            total_leave_days=8,
        )

        ledger = avail.build_ledger()

        self.assertEqual(len(ledger), 2)
        labels = {row["label"] for row in ledger}
        self.assertEqual(labels, {"Initial assignment", "Initial carryforward"})
        carryforward_row = next(
            row for row in ledger if row["label"] == "Initial carryforward"
        )
        self.assertEqual(carryforward_row["credit"], 3)
        self.assertEqual(ledger[0]["balance"], 8)

    def test_reset_appears_as_labeled_credit_row(self):
        from leave.scheduler import leave_reset

        lt = self.LeaveType.objects.create(
            name="Ledger Reset Type",
            total_days=10,
            reset=True,
            reset_based="monthly",
            reset_day="1",
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=3,
            carryforward_days=0,
            total_leave_days=3,
            reset_date=date.today(),
        )

        leave_reset()
        avail.refresh_from_db()
        ledger = avail.build_ledger()

        self.assertEqual(len(ledger), 2)
        # Newest first: the reset is the latest entry, at index 0.
        self.assertEqual(ledger[0]["label"], "Leave reset")
        self.assertEqual(ledger[0]["credit"], 7)  # 10 - 3
        self.assertEqual(ledger[0]["balance"], 10)
        self.assertEqual(ledger[1]["label"], "Initial assignment")
        self.assertEqual(ledger[1]["balance"], 3)

    def test_approved_leave_is_a_debit_rejected_is_excluded(self):
        """
        Approval must go through the real code path (LeaveRequest.
        no_approval()), which already decrements available_days and
        saves() -- that save() is what creates the history row the ledger
        reads. A LeaveRequest created directly with status="approved"
        (bypassing no_approval()) never touches AvailableLeave at all, so
        it must NOT show up as a second, independent debit (see
        build_ledger()'s docstring for why that would double-count).
        """
        from leave.models import LeaveRequest

        lt = self.LeaveType.objects.create(
            name="Ledger Taken Type",
            total_days=10,
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=10,
            carryforward_days=0,
            total_leave_days=10,
            assigned_date=date.today() - timedelta(days=10),
        )
        approved = LeaveRequest(
            employee_id=self.employee,
            leave_type_id=lt,
            start_date=date.today() - timedelta(days=2),
            end_date=date.today() - timedelta(days=2),
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            requested_days=1,
            status="requested",
            approved_available_days=0,
            approved_carryforward_days=0,
        )
        approved.no_approval()
        approved.save()

        rejected = LeaveRequest.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            start_date=date.today() - timedelta(days=1),
            end_date=date.today() - timedelta(days=1),
            requested_days=1,
            status="rejected",
        )

        avail.refresh_from_db()
        ledger = avail.build_ledger()

        debit_rows = [row for row in ledger if row["debit"]]
        self.assertEqual(len(debit_rows), 1)
        self.assertEqual(debit_rows[0]["debit"], 1)
        # The ledger entry is dated when the balance actually changed
        # (the approval save(), i.e. today in this test) -- not the
        # leave's own start_date, which is commonly a different day.
        self.assertEqual(debit_rows[0]["date"], date.today())
        self.assertIn("Leave taken", debit_rows[0]["label"])
        # The ledger's own running total must reconcile with the real,
        # current stored balance -- not just "some plausible number".
        # Newest first, so the latest (final) balance is at index 0.
        self.assertEqual(
            ledger[0]["balance"], avail.available_days + avail.carryforward_days
        )
        self.assertEqual(avail.available_days, 9)

    def test_approved_leave_bypassing_no_approval_still_gets_its_own_row(self):
        """
        Some approved LeaveRequests never go through no_approval()/
        multiple_approvals() at all -- created directly with
        status="approved" (bulk import, admin edit, demo fixtures like
        create_leave_fixtures). Their deduction never touches
        AvailableLeave, so there's no history delta to derive a debit
        from -- but the request is still genuinely "taken" (it's exactly
        what the existing "Taken Leaves" column on the Assigned Leave list
        reports), so it must still show up as its own row rather than
        being silently invisible. The running balance legitimately will
        not reconcile with available_days + carryforward_days in this
        case -- that mismatch reflects the underlying data (approved
        leave that was never deducted), not a bug in build_ledger().
        """
        from leave.models import LeaveRequest

        lt = self.LeaveType.objects.create(
            name="Ledger Unclaimed Type",
            total_days=10,
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
            assigned_date=date.today() - timedelta(days=10),
        )
        # LeaveRequest.save() recomputes requested_days from the actual
        # date range regardless of what's passed in (leave/models.py:1607)
        # -- span 2 real days (not 1) so the recalculated value matches
        # what this test asserts, rather than fighting that recompute.
        taken = LeaveRequest.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            start_date=date.today() - timedelta(days=3),
            end_date=date.today() - timedelta(days=2),
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            requested_days=2,
            status="approved",
        )

        ledger = avail.build_ledger()

        debit_rows = [row for row in ledger if row["debit"]]
        self.assertEqual(len(debit_rows), 1)
        self.assertEqual(debit_rows[0]["debit"], 2)
        self.assertEqual(debit_rows[0]["date"], taken.start_date)
        self.assertIn("Leave taken", debit_rows[0]["label"])
        # available_days was never actually touched by this request, so
        # the ledger's own total (5 opening - 2 taken = 3) intentionally
        # differs from the live stored balance (still 5). Newest first,
        # so the latest (final) balance is at index 0.
        self.assertEqual(ledger[0]["balance"], 3)
        self.assertEqual(avail.available_days, 5)

    def test_running_balance_across_mixed_credits_and_debits(self):
        from leave.models import LeaveRequest
        from leave.scheduler import leave_reset

        lt = self.LeaveType.objects.create(
            name="Ledger Mixed Type",
            total_days=10,
            reset=True,
            reset_based="monthly",
            reset_day="1",
            carryforward_type="no carryforward",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=4,
            carryforward_days=0,
            total_leave_days=4,
            assigned_date=date.today() - timedelta(days=10),
            reset_date=date.today() - timedelta(days=1),
        )
        taken = LeaveRequest(
            employee_id=self.employee,
            leave_type_id=lt,
            start_date=date.today() - timedelta(days=5),
            end_date=date.today() - timedelta(days=5),
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            requested_days=1,
            status="requested",
            approved_available_days=0,
            approved_carryforward_days=0,
        )
        taken.no_approval()
        taken.save()

        leave_reset()
        avail.refresh_from_db()
        ledger = avail.build_ledger()

        # 4 (opening) - 1 (taken) + 7 (reset: 10 - 3 already-decremented total) = 10
        # Newest first, so the latest (final) balance is at index 0.
        self.assertEqual(ledger[0]["balance"], 10)
        self.assertEqual(
            ledger[0]["balance"], avail.available_days + avail.carryforward_days
        )
        self.assertEqual(avail.available_days, 10)


class ForecastNextResetTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Forecast Co")
        self.employee = make_employee(company=company, email="forecast@test.horilla")
        self.LeaveType = LeaveType
        self.AvailableLeave = AvailableLeave

    def test_no_forecast_when_reset_disabled(self):
        lt = self.LeaveType.objects.create(
            name="No Reset Type", total_days=5, reset=False
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            total_leave_days=5,
        )
        self.assertIsNone(avail.forecast_next_reset())

    def test_no_forecast_when_reset_date_unset(self):
        """
        AvailableLeave.save() auto-computes reset_date whenever
        leave_type.reset=True, so this can't happen through normal
        creation -- simulate legacy/corrupted data missing it instead
        (e.g. imported from an older system) to genuinely exercise the
        None-guard.
        """
        lt = self.LeaveType.objects.create(
            name="Reset No Date Type",
            total_days=5,
            reset=True,
            reset_based="monthly",
            reset_day="1",
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            total_leave_days=5,
        )
        avail.reset_date = None
        self.assertIsNone(avail.forecast_next_reset())

    def test_forecast_matches_what_a_real_reset_would_produce(self):
        from leave.scheduler import leave_reset

        lt = self.LeaveType.objects.create(
            name="Forecast Reset Type",
            total_days=10,
            reset=True,
            reset_based="monthly",
            reset_day="1",
            carryforward_type="carryforward",
            carryforward_max=3,
        )
        avail = self.AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=4,
            carryforward_days=0,
            total_leave_days=4,
            reset_date=date.today(),
        )

        forecast = avail.forecast_next_reset()
        self.assertIsNotNone(forecast)
        self.assertEqual(forecast["date"], date.today())
        # carryforward_max(3) < current total(4) -> capped at 3.
        # forecasted total = 10 + 3 = 13; delta from current total (4) = 9.
        self.assertEqual(forecast["credit"], 9)
        self.assertEqual(forecast["balance"], 13)

        # forecast must not mutate anything.
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 4)
        self.assertEqual(avail.carryforward_days, 0)

        # And it must match what actually happens once the reset runs for real.
        leave_reset()
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 10)
        self.assertEqual(avail.carryforward_days, 3)
        self.assertEqual(
            avail.available_days + avail.carryforward_days, forecast["balance"]
        )


class LeaveLedgerViewTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee, make_user
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Ledger View Co")
        user = make_user("ledger_view_user", is_superuser=True)
        self.employee = make_employee(
            company=company, email="ledgerview@test.horilla", user=user
        )
        lt = LeaveType.objects.create(
            name="Ledger View Type",
            total_days=5,
            carryforward_type="no carryforward",
        )
        self.avail = AvailableLeave.objects.create(
            employee_id=self.employee,
            leave_type_id=lt,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )

    def test_ledger_view_renders(self):
        from django.urls import reverse

        self.client.force_login(self.employee.employee_user_id)
        response = self.client.get(
            reverse("leave-balance-ledger", args=[self.avail.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initial assignment")
