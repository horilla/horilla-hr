"""Leave requests judged by the balance of their end date; approving one brings the balance forward to that cycle."""

import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave import forecast
from leave.methods import (
    decide_leave_cancellation,
    reset_available_leave,
    run_missed_resets,
)
from leave.models import AvailableLeave, LeaveRequest, LeaverequestComment, LeaveType
from leave.services import charge_leave_request


def first_of_next_month(day):
    return (day.replace(day=1) + timedelta(days=32)).replace(day=1)


TODAY = date.today()
RESET = first_of_next_month(TODAY)
NEXT_RESET = first_of_next_month(RESET)
AFTER_NEXT_RESET = first_of_next_month(NEXT_RESET)


class ForecastBase(TestCase):
    carryforward_type = "no carryforward"
    carryforward_max = 0
    reset = True
    total_days = 10

    def setUp(self):
        company = make_company("Forecast Co")
        self.admin_user = make_user(
            "forecast_admin", password="secret123", is_superuser=True
        )
        self.admin = make_employee(
            company=company, email="forecast_admin@test.horilla", user=self.admin_user
        )
        self.employee = make_employee(
            company=company, email="forecast_emp@test.horilla"
        )
        self.leave_type = LeaveType.objects.create(
            name="Forecast Leave",
            total_days=self.total_days,
            reset=self.reset,
            reset_based="monthly",
            reset_day="1",
            carryforward_type=self.carryforward_type,
            carryforward_max=self.carryforward_max,
        )

    def balance(self, available=2, carryforward=0, employee=None):
        return AvailableLeave.objects.create(
            employee_id=employee or self.employee,
            leave_type_id=self.leave_type,
            available_days=available,
            carryforward_days=carryforward,
            total_leave_days=available + carryforward,
            reset_date=RESET,
        )

    def leave(self, start, end, status="requested", **extra):
        leave = LeaveRequest(
            employee_id=extra.pop("employee", self.employee),
            leave_type_id=self.leave_type,
            start_date=start,
            end_date=end,
            description="forecast",
            status=status,
            **extra,
        )
        leave.save()
        return LeaveRequest.objects.get(pk=leave.pk)

    def reasons(self, balance):
        return [h.history_change_reason for h in balance.history.order_by("history_id")]


class BalanceOnTests(ForecastBase):
    def test_before_the_reset_the_balance_is_what_is_held(self):
        avail = self.balance(available=2)
        result = forecast.balance_on(avail, RESET - timedelta(days=1))
        self.assertEqual(result.total, 2)
        self.assertEqual(result.resets, [])
        self.assertIsNone(result.cycle_start)

    def test_on_the_reset_day_the_new_cycle_counts(self):
        avail = self.balance(available=2)
        result = forecast.balance_on(avail, RESET)
        self.assertEqual(result.total, 10)
        self.assertEqual(result.cycle_start, RESET)

    def test_leftover_is_dropped_without_carryforward(self):
        avail = self.balance(available=7, carryforward=1)
        self.assertEqual(forecast.balance_on(avail, RESET).total, 10)

    def test_second_reset_is_counted(self):
        avail = self.balance(available=2)
        result = forecast.balance_on(avail, NEXT_RESET + timedelta(days=3))
        self.assertEqual(result.resets, [RESET, NEXT_RESET])
        self.assertEqual(result.total, 10)

    def test_a_leave_type_that_never_resets_ignores_the_date(self):
        self.leave_type.reset = False
        self.leave_type.save()
        avail = self.balance(available=2)
        self.assertEqual(forecast.balance_on(avail, NEXT_RESET).total, 2)

    def test_waiting_requests_of_the_same_cycle_are_held_back_when_asked(self):
        avail = self.balance(available=2)
        self.leave(
            RESET + timedelta(days=1), RESET + timedelta(days=4)
        )  # 4 days, next cycle
        self.leave(
            TODAY + timedelta(days=1), TODAY + timedelta(days=1)
        )  # current cycle
        end = RESET + timedelta(days=8)
        self.assertEqual(forecast.balance_on(avail, end).total, 10)
        self.assertEqual(forecast.balance_on(avail, end, include_pending=True).total, 6)
        self.assertEqual(
            forecast.balance_on(
                avail, TODAY + timedelta(days=2), include_pending=True
            ).total,
            1,
        )


class BalanceOnCarryforwardTests(ForecastBase):
    carryforward_type = "carryforward"
    carryforward_max = 3

    def test_carryforward_is_capped_at_the_maximum(self):
        avail = self.balance(available=8, carryforward=0)
        self.assertEqual(forecast.balance_on(avail, RESET).total, 13)

    def test_carryforward_is_what_is_left_when_below_the_maximum(self):
        avail = self.balance(available=1, carryforward=0)
        self.assertEqual(forecast.balance_on(avail, RESET).total, 11)


class CheckTests(ForecastBase):
    def test_fits_now(self):
        result = forecast.check(self.balance(available=5), TODAY + timedelta(days=2), 3)
        self.assertEqual(result.kind, forecast.OK_NOW)
        self.assertFalse(result.ahead)

    def test_fits_the_cycle_the_end_date_falls_in(self):
        result = forecast.check(self.balance(available=0), RESET + timedelta(days=2), 3)
        self.assertEqual(result.kind, forecast.OK_FORECAST)
        self.assertTrue(result.ahead)
        self.assertEqual(result.balance.cycle_start, RESET)

    def test_a_future_leave_the_balance_covers_comes_straight_off_it(self):
        result = forecast.check(
            self.balance(available=5), RESET + timedelta(days=10), 3
        )
        self.assertEqual(result.kind, forecast.OK_NOW)
        self.assertFalse(result.ahead)
        self.assertIsNone(result.balance.cycle_start)

    def test_waiting_requests_count_against_what_is_held_now(self):
        avail = self.balance(available=5)
        self.leave(
            TODAY + timedelta(days=1), TODAY + timedelta(days=4)
        )  # 4 days waiting, current cycle
        result = forecast.check(
            avail, RESET + timedelta(days=10), 3, include_pending=True
        )
        self.assertEqual(
            result.kind, forecast.OK_FORECAST
        )  # 1 is left now, so the next cycle is used

    def test_a_leave_crossing_the_reset_is_judged_by_its_end_date(self):
        avail = self.balance(available=1)
        result = forecast.check(avail, RESET + timedelta(days=1), 6)
        self.assertEqual(result.kind, forecast.OK_FORECAST)

    def test_short_and_by_how_much(self):
        result = forecast.check(self.balance(available=1), TODAY + timedelta(days=2), 4)
        self.assertEqual(result.kind, forecast.SHORT)
        self.assertEqual(result.shortfall, 3)
        self.assertTrue(result.can_reset_now)

    def test_a_reset_cannot_cover_more_than_the_allowance(self):
        result = forecast.check(
            self.balance(available=1), TODAY + timedelta(days=2), 11
        )
        self.assertEqual(result.kind, forecast.SHORT)
        self.assertFalse(result.can_reset_now)

    def test_no_reset_now_for_a_leave_type_that_never_resets(self):
        self.leave_type.reset = False
        self.leave_type.save()
        result = forecast.check(self.balance(available=1), TODAY + timedelta(days=2), 4)
        self.assertFalse(result.can_reset_now)

    def test_no_limit_always_fits(self):
        self.leave_type.limit_leave = False
        self.leave_type.save()
        result = forecast.check(
            self.balance(available=0), RESET + timedelta(days=2), 50
        )
        self.assertEqual(result.kind, forecast.OK_NOW)


class CleanTests(ForecastBase):
    def _request(self, start, end):
        return LeaveRequest(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            start_date=start,
            end_date=end,
            description="clean",
        )

    def _clean(self, leave):
        from horilla import horilla_middlewares

        class Req:
            user = self.admin_user

        horilla_middlewares._thread_locals.request = Req()
        try:
            leave.clean()
        finally:
            horilla_middlewares._thread_locals.request = None

    def test_leave_after_the_reset_is_accepted_without_a_current_balance(self):
        self.balance(available=0)
        self._clean(self._request(RESET + timedelta(days=1), RESET + timedelta(days=3)))

    def test_leave_before_the_reset_needs_the_current_balance(self):
        from django.core.exceptions import ValidationError

        self.balance(available=0)
        with self.assertRaises(ValidationError):
            self._clean(
                self._request(TODAY + timedelta(days=1), TODAY + timedelta(days=1))
            )

    def test_waiting_requests_use_up_the_forecast(self):
        from django.core.exceptions import ValidationError

        self.balance(available=0)
        self.leave(RESET + timedelta(days=1), RESET + timedelta(days=8))  # 8 of 10 days
        with self.assertRaises(ValidationError):
            self._clean(
                self._request(RESET + timedelta(days=10), RESET + timedelta(days=12))
            )


class ChargeTests(ForecastBase):
    def test_a_leave_in_the_current_cycle_comes_out_now(self):
        avail = self.balance(available=5)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        charge_leave_request(leave, avail)
        self.assertEqual(avail.available_days, 3)
        self.assertEqual(leave.approved_available_days, 2)
        self.assertIsNone(leave.provided_cycle)
        self.assertEqual(avail.reset_date, RESET)

    def test_a_future_leave_the_balance_covers_brings_nothing_forward(self):
        avail = self.balance(available=5)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=2))
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 3)
        self.assertEqual(avail.reset_date, RESET)
        self.assertIsNone(leave.provided_cycle)
        self.assertFalse([r for r in self.reasons(avail) if r and "provided" in r])

    def test_a_leave_after_the_reset_brings_the_balance_forward_to_its_cycle(self):
        avail = self.balance(available=1)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=2))
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 8)  # the reset's 10, less the 2 days
        self.assertEqual(
            avail.reset_date, NEXT_RESET
        )  # the next reset is the one after that cycle
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual(leave.approved_available_days, 2)
        self.assertEqual(
            self.reasons(avail)[-2:],
            [
                f"Leave reset provided: {RESET.isoformat()}",
                f"Forecasted leave taken: {RESET.isoformat()}",
            ],
        )

    def test_only_the_resets_up_to_the_first_one_that_covers_the_leave_are_provided(
        self,
    ):
        avail = self.balance(available=1)
        # Ends in the second cycle, but the first reset already leaves 10, enough for the 3 days.
        leave = self.leave(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=3)
        )
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual(avail.available_days, 7)
        self.assertEqual(
            avail.reset_date, NEXT_RESET
        )  # the second reset is left to happen on its own
        self.assertEqual(
            self.reasons(avail)[-2:],
            [
                f"Leave reset provided: {RESET.isoformat()}",
                f"Forecasted leave taken: {RESET.isoformat()}",
            ],
        )

    def test_nothing_is_written_until_the_balance_is_saved(self):
        avail = self.balance(available=1)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=2))
        charge_leave_request(leave, avail)
        stored = AvailableLeave.objects.get(pk=avail.pk)
        self.assertEqual((stored.available_days, stored.reset_date), (1, RESET))

    def test_the_scheduler_does_not_run_the_provided_reset_again(self):
        avail = self.balance(available=1)
        # Ends in the second cycle, but only the first reset is needed and so only that one is provided.
        leave = self.leave(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=3)
        )
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        # The first reset's day has come and gone for this balance: nothing is due, nothing is reset again.
        self.assertFalse(avail.is_reset_due(RESET + timedelta(days=5)))
        self.assertFalse(
            reset_available_leave(avail, RESET, "Leave reset", "Carryforward expired")
        )
        result = run_missed_resets(
            self.leave_type, "Leave reset", "Carryforward expired", today_date=RESET
        )
        self.assertEqual(result["reset"], [])
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 7)
        # The second reset was not brought forward, so it still happens on its own day.
        self.assertTrue(avail.is_reset_due(NEXT_RESET))
        self.assertTrue(
            reset_available_leave(
                avail, NEXT_RESET, "Leave reset", "Carryforward expired"
            )
        )

    def test_no_approval_brings_the_balance_forward_too(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        leave.no_approval()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual(avail.available_days, 7)

    def cancel_requested(self, leave):
        LeaveRequest.objects.filter(pk=leave.pk).update(
            status="cancel_requested",
            provided_cycle=leave.provided_cycle,
            approved_available_days=leave.approved_available_days,
            approved_carryforward_days=leave.approved_carryforward_days,
        )

    def test_cancelling_takes_the_resets_brought_forward_back(self):
        avail = self.balance(available=1)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        charge_leave_request(leave, avail)
        avail.save()
        self.cancel_requested(leave)
        _, error = decide_leave_cancellation(leave.pk, True, self.admin)
        self.assertIsNone(error)
        avail.refresh_from_db()
        # Back to what it was before the approval, not a balance that holds days not yet earned.
        self.assertEqual((avail.available_days, avail.reset_date), (1, RESET))
        self.assertIn(
            "Leave approval undone: resets brought forward were taken back",
            self.reasons(avail),
        )

    def test_rewinding_restores_the_reset_date_the_balance_had_not_the_one_in_old_history(
        self,
    ):
        avail = self.balance(available=1)
        # The schedule moved without a save of the balance (a leave type rule change does that).
        AvailableLeave.objects.filter(pk=avail.pk).update(reset_date=NEXT_RESET)
        avail.refresh_from_db()
        leave = self.leave(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=3)
        )
        charge_leave_request(leave, avail)
        avail.save()
        self.assertEqual(leave.provided_cycle, NEXT_RESET)
        self.cancel_requested(leave)
        decide_leave_cancellation(leave.pk, True, self.admin)
        avail.refresh_from_db()
        self.assertEqual((avail.available_days, avail.reset_date), (1, NEXT_RESET))

    def test_cancelling_after_something_else_changed_the_balance_only_gives_the_days_back(
        self,
    ):
        avail = self.balance(available=1)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        avail.available_days += 4  # someone adjusts the balance afterwards
        avail._change_reason = "Manual adjustment"
        avail.save()
        self.cancel_requested(leave)
        _, error = decide_leave_cancellation(leave.pk, True, self.admin)
        self.assertIsNone(error)
        avail.refresh_from_db()
        self.assertEqual(
            avail.available_days, 7 + 4 + 3
        )  # 10 less 3, plus the adjustment, plus the 3 back
        self.assertEqual(avail.reset_date, NEXT_RESET)

    def test_cancelling_a_leave_in_the_current_cycle_just_gives_the_days_back(self):
        avail = self.balance(available=5)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        charge_leave_request(leave, avail)
        avail.save()
        self.cancel_requested(leave)
        decide_leave_cancellation(leave.pk, True, self.admin)
        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 5)


class EarliestResetTests(ForecastBase):
    """The leave is charged to the first reset (by its end date) that leaves enough, not to its end date's cycle."""

    carryforward_type = "carryforward"
    carryforward_max = 12
    total_days = 1

    def far_leave(self, days):
        """``days`` days ending three cycles out."""
        end = AFTER_NEXT_RESET + timedelta(days=5)
        return self.leave(end - timedelta(days=days - 1), end)

    def test_the_first_reset_is_enough_when_it_leaves_enough(self):
        avail = self.balance(available=5)  # 5 now, 6 after the first reset
        result = forecast.check(avail, AFTER_NEXT_RESET + timedelta(days=5), 6)
        self.assertEqual(result.kind, forecast.OK_FORECAST)
        self.assertEqual(result.balance.cycle_start, RESET)
        self.assertEqual([step["date"] for step in result.balance.steps], [RESET])

    def test_a_bigger_leave_waits_for_the_reset_that_leaves_enough(self):
        avail = self.balance(
            available=5
        )  # 6, 7, 8 after the first, second, third reset
        result = forecast.check(avail, AFTER_NEXT_RESET + timedelta(days=5), 8)
        self.assertEqual(result.balance.cycle_start, AFTER_NEXT_RESET)
        self.assertEqual(len(result.balance.steps), 3)

    def test_a_reset_after_the_end_date_is_never_used(self):
        avail = self.balance(available=5)
        result = forecast.check(
            avail, NEXT_RESET + timedelta(days=5), 8
        )  # only two resets by then: 7 at most
        self.assertEqual(result.kind, forecast.SHORT)
        self.assertEqual(result.shortfall, 1)

    def test_approving_leaves_the_later_resets_to_happen_on_their_own(self):
        avail = self.balance(available=5)
        leave = self.far_leave(6)
        charge_leave_request(leave, avail)
        avail.save()
        avail.refresh_from_db()
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual((avail.available_days, avail.carryforward_days), (0, 0))
        self.assertEqual(avail.reset_date, NEXT_RESET)
        self.assertEqual(
            self.reasons(avail)[-2:][0], f"Leave reset provided: {RESET.isoformat()}"
        )

    def test_waiting_requests_are_spoken_for_at_every_reset(self):
        avail = self.balance(available=5)
        self.far_leave(2)  # waiting: 2 of the days
        end = AFTER_NEXT_RESET + timedelta(days=5)
        # Alone, 6 days are covered after the first reset; with 2 days spoken for, it takes the third (8 - 2).
        self.assertEqual(forecast.check(avail, end, 6).balance.cycle_start, RESET)
        self.assertEqual(
            forecast.check(avail, end, 6, include_pending=True).balance.cycle_start,
            AFTER_NEXT_RESET,
        )

    def test_the_form_shows_only_the_resets_it_will_bring_forward(self):
        avail = self.balance(available=5)
        self.client.force_login(self.admin_user)
        end = AFTER_NEXT_RESET + timedelta(days=5)
        response = self.client.get(
            reverse("employee-available-leave-count"),
            {
                "leave_type_id": self.leave_type.pk,
                "employee_id": avail.employee_id_id,
                "start_date": (end - timedelta(days=5)).isoformat(),
                "end_date": end.isoformat(),
                "start_date_breakdown": "full_day",
                "end_date_breakdown": "full_day",
            },
            HTTP_HX_REQUEST="true",
        )
        report = response.context["report"]
        self.assertEqual(report["kind"], forecast.OK_FORECAST)
        self.assertEqual(
            [step["event"] for step in report["steps"]],
            ["Balance Now", "Monthly Reset"],
        )
        self.assertEqual(report["left"], "0")


class ApproveViewTests(ForecastBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def approve(self, leave, **post):
        url = reverse("request-approve", args=[leave.pk])
        if post:
            return self.client.post(url, post, HTTP_HX_REQUEST="true")
        return self.client.get(url, {"confirm": 1}, HTTP_HX_REQUEST="true")

    def trigger(self, response):
        return json.loads(response["HX-Trigger"])

    def test_a_leave_after_the_reset_is_approved_from_the_brought_forward_balance(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        response = self.approve(leave)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(leave.provided_cycle, RESET)
        self.assertEqual(avail.available_days, 7)
        self.assertEqual(avail.reset_date, NEXT_RESET)
        self.assertNotIn("leaveBalanceShort", self.trigger(response))

    def test_a_forecasted_leave_shows_its_summary_before_anything_is_approved(self):
        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        url = reverse("request-approve", args=[leave.pk])
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        leave.refresh_from_db()
        avail.refresh_from_db()
        summary = self.trigger(response)["leaveForecastSummary"]
        self.assertEqual(summary["url"], url + "?summary=1")
        self.assertEqual(
            (leave.status, avail.available_days, avail.reset_date),
            ("requested", 0, RESET),
        )
        page = self.client.get(summary["url"], HTTP_HX_REQUEST="true")
        self.assertContains(page, "Monthly Reset")
        self.assertContains(page, url + "?confirm=1")
        leave.refresh_from_db()
        self.assertEqual(leave.status, "requested")

    def test_the_summary_is_only_for_forecasted_requests(self):
        url_for = lambda leave: reverse("request-approve", args=[leave.pk])
        # Covered by the balance now, even though it is dated after the reset.
        self.balance(available=5)
        covered = self.leave(RESET + timedelta(days=5), RESET + timedelta(days=6))
        trigger = self.trigger(
            self.client.get(url_for(covered), HTTP_HX_REQUEST="true")
        )
        self.assertNotIn("leaveForecastSummary", trigger)
        self.assertEqual(LeaveRequest.objects.get(pk=covered.pk).status, "approved")
        # Not covered by the balance or any reset before it: the alert, never the summary.
        short = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=9))
        trigger = self.trigger(self.client.get(url_for(short), HTTP_HX_REQUEST="true"))
        self.assertIn("leaveBalanceShort", trigger)
        self.assertNotIn("leaveForecastSummary", trigger)
        # A leave type without a limit always fits the balance now.
        self.leave_type.limit_leave = False
        self.leave_type.save()
        unlimited = self.leave(RESET + timedelta(days=10), RESET + timedelta(days=12))
        trigger = self.trigger(
            self.client.get(url_for(unlimited), HTTP_HX_REQUEST="true")
        )
        self.assertNotIn("leaveForecastSummary", trigger)
        self.assertFalse(LeaveRequest.objects.get(pk=unlimited.pk).approves_ahead)

    def test_only_a_forecasted_request_approves_ahead(self):
        self.balance(available=0)
        forecasted = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        covered = self.leave(
            TODAY + timedelta(days=1), TODAY + timedelta(days=1), employee=self.admin
        )
        AvailableLeave.objects.filter(employee_id=self.admin).delete()
        self.balance(available=5, employee=self.admin)
        self.assertTrue(forecasted.approves_ahead)
        self.assertFalse(LeaveRequest.objects.get(pk=covered.pk).approves_ahead)

    def test_a_leave_in_the_current_cycle_is_approved_without_a_summary(self):
        self.balance(available=5)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        response = self.client.get(
            reverse("request-approve", args=[leave.pk]), HTTP_HX_REQUEST="true"
        )
        leave.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertNotIn("leaveForecastSummary", self.trigger(response))

    def test_a_leave_in_the_current_cycle_is_still_taken_now(self):
        avail = self.balance(available=5)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=2))
        self.approve(leave)
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(avail.available_days, 3)
        self.assertIsNone(leave.provided_cycle)
        self.assertEqual(avail.reset_date, RESET)

    def test_no_balance_raises_the_alert_and_changes_nothing(self):
        avail = self.balance(available=1)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=3))
        response = self.approve(leave)
        leave.refresh_from_db()
        avail.refresh_from_db()
        alert = self.trigger(response)["leaveBalanceShort"]
        self.assertEqual(leave.status, "requested")
        self.assertEqual(avail.available_days, 1)
        self.assertTrue(alert["can_reset"])
        self.assertEqual(alert["title"], "No Available Leave")
        self.assertIn("Short By", [line[0] for line in alert["lines"]])
        self.assertEqual(dict(alert["lines"])["Short By"], "2")

    def test_reset_now_and_approve(self):
        avail = self.balance(available=1)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=3))
        response = self.approve(leave, reset_now="1")
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(avail.available_days, 7)  # a fresh 10, less the 3 days
        self.assertEqual(
            avail.reset_date, RESET
        )  # a monthly reset still falls on the 1st
        self.assertNotIn("leaveBalanceShort", self.trigger(response))
        self.assertIn("Leave reset early to approve a request", self.reasons(avail))
        # Only the reset carries that reason: the leave's own row after it does not.
        self.assertEqual(
            self.reasons(avail).count("Leave reset early to approve a request"), 1
        )
        self.assertTrue(
            LeaverequestComment.objects.filter(
                request_id=leave, comment__contains="reset early"
            ).exists()
        )

    def test_reset_now_is_not_done_when_it_would_not_help(self):
        avail = self.balance(available=1)
        leave = self.leave(
            TODAY + timedelta(days=1), TODAY + timedelta(days=12)
        )  # 12 days > 10
        response = self.approve(leave, reset_now="1")
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertEqual(avail.available_days, 1)
        self.assertFalse(self.trigger(response)["leaveBalanceShort"]["can_reset"])

    def test_reset_now_needs_a_post(self):
        avail = self.balance(available=1)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=3))
        url = reverse("request-approve", args=[leave.pk]) + "?reset_now=1"
        self.client.get(url, HTTP_HX_REQUEST="true")
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertEqual(avail.available_days, 1)

    def test_reset_now_needs_the_permission_to_change_balances(self):
        from django.contrib.auth.models import Permission

        manager_user = make_user("forecast_manager", password="secret123")
        manager = make_employee(
            company=self.employee.employee_work_info.company_id,
            email="forecast_manager@test.horilla",
            user=manager_user,
        )
        work_info = self.employee.employee_work_info
        work_info.reporting_manager_id = manager
        work_info.save()
        manager_user.user_permissions.add(
            Permission.objects.get(codename="change_leaverequest")
        )
        avail = self.balance(available=1)
        leave = self.leave(TODAY + timedelta(days=1), TODAY + timedelta(days=3))
        self.client.force_login(manager_user)
        response = self.approve(leave, reset_now="1")
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "requested")
        self.assertEqual(avail.available_days, 1)
        self.assertFalse(self.trigger(response)["leaveBalanceShort"]["can_reset"])

    def test_rejecting_a_leave_approved_ahead_puts_the_balance_back(self):
        from unittest import mock

        from django.test import RequestFactory

        from leave.views import _reject_leave_request

        avail = self.balance(available=0)
        leave = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        self.approve(leave)
        leave.refresh_from_db()
        request = RequestFactory().post("/")
        request.user = self.admin_user
        with mock.patch("leave.views.LeaveMailSendThread"):
            _reject_leave_request(request, leave, "no longer needed")
        leave.refresh_from_db()
        avail.refresh_from_db()
        self.assertEqual(leave.status, "rejected")
        self.assertEqual((avail.available_days, avail.reset_date), (0, RESET))


class LedgerTests(ForecastBase):
    """The ledger lists what approving a leave ahead of its cycle brought forward, in date order."""

    def approved_ahead(self, avail, start, end):
        leave = self.leave(start, end, status="approved")
        charge_leave_request(leave, avail)
        avail.save()
        LeaveRequest.objects.filter(pk=leave.pk).update(
            provided_cycle=leave.provided_cycle,
            approved_available_days=leave.approved_available_days,
            approved_carryforward_days=leave.approved_carryforward_days,
        )
        return LeaveRequest.objects.get(pk=leave.pk)

    def test_the_provided_reset_and_the_leave_are_dated_by_their_cycle(self):
        avail = self.balance(available=1)
        self.approved_ahead(avail, RESET + timedelta(days=1), RESET + timedelta(days=2))
        ledger = avail.build_ledger()  # newest first
        provided = [row for row in ledger if row.get("provided")]
        self.assertEqual([row["kind"] for row in provided], ["taken", "reset"])
        taken, reset = provided
        self.assertEqual(
            (reset["date"], reset["credit"], reset["label"]), (RESET, 9, "Leave Reset")
        )
        self.assertEqual(
            (taken["date"], taken["debit"], taken["balance"]), (RESET, 2, 8)
        )
        self.assertIn("Leave taken", str(taken["label"]))

    def test_the_balances_tally_with_the_live_balance(self):
        avail = self.balance(available=1)
        self.approved_ahead(
            avail, NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=3)
        )
        avail.refresh_from_db()
        ledger = avail.build_ledger()
        self.assertEqual(
            ledger[0]["balance"], avail.available_days + avail.carryforward_days
        )
        # Only the first reset was needed, so only that one is provided (and dated by it).
        self.assertEqual(
            [row["date"] for row in ledger if row.get("provided")], [RESET, RESET]
        )
        self.assertEqual(
            len([row for row in ledger if "Leave taken" in str(row["label"])]), 1
        )

    def test_the_next_reset_is_the_one_after_the_leave(self):
        avail = self.balance(available=1)
        self.approved_ahead(
            avail, NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=3)
        )
        avail.refresh_from_db()
        info = avail.forecast_next_reset()
        self.assertEqual(info["date"], NEXT_RESET)
        self.assertEqual(avail.provided_ahead_days(), 3)

    def test_the_ledger_view_renders_provided_rows(self):
        avail = self.balance(available=1)
        self.approved_ahead(avail, RESET + timedelta(days=1), RESET + timedelta(days=2))
        self.client.force_login(self.admin_user)
        response = self.client.get(
            reverse("leave-balance-ledger", args=[avail.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Provided")
        self.assertContains(response, "Next Reset")

    def cancel(self, leave):
        LeaveRequest.objects.filter(pk=leave.pk).update(status="cancel_requested")
        _, error = decide_leave_cancellation(leave.pk, True, self.admin)
        self.assertIsNone(error)

    def test_an_undone_approval_leaves_no_trace_in_the_ledger(self):
        avail = self.balance(available=1)
        leave = self.approved_ahead(
            avail, RESET + timedelta(days=1), RESET + timedelta(days=3)
        )
        self.cancel(leave)
        avail.refresh_from_db()
        ledger = avail.build_ledger()
        self.assertEqual([str(row["label"]) for row in ledger], ["Initial assignment"])
        self.assertEqual(
            ledger[0]["balance"], avail.available_days + avail.carryforward_days
        )

    def test_a_refund_after_other_changes_is_dated_by_the_cycle_and_tallies(self):
        avail = self.balance(available=1)
        leave = self.approved_ahead(
            avail, RESET + timedelta(days=1), RESET + timedelta(days=3)
        )
        avail.refresh_from_db()
        avail.available_days += (
            4  # someone adjusts the balance afterwards, so it can't simply be rewound
        )
        avail._change_reason = "Manual adjustment"
        avail.save()
        self.cancel(leave)
        avail.refresh_from_db()
        ledger = avail.build_ledger()
        refunded = [row for row in ledger if str(row["label"]) == "Leave Refunded"]
        self.assertEqual(len(refunded), 1)
        self.assertEqual((refunded[0]["date"], refunded[0]["credit"]), (RESET, 3))
        taken = [row for row in ledger if "Leave taken" in str(row["label"])]
        self.assertEqual(len(taken), 1)
        self.assertIn(
            str(leave.start_date), str(taken[0]["label"])
        )  # named by its dates even after cancelling
        self.assertEqual(
            ledger[0]["balance"], avail.available_days + avail.carryforward_days
        )


class BalanceWidgetTests(ForecastBase):
    """The balance and forecast shown on the leave request form."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def widget(self, start, end, **extra):
        params = {
            "leave_type_id": self.leave_type.pk,
            "employee_id": self.employee.pk,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "start_date_breakdown": "full_day",
            "end_date_breakdown": "full_day",
            **extra,
        }
        return self.client.get(
            reverse("employee-available-leave-count"), params, HTTP_HX_REQUEST="true"
        )

    def test_a_leave_after_the_reset_lists_the_reset_in_the_table(self):
        self.balance(available=1)
        report = self.widget(
            RESET + timedelta(days=1), RESET + timedelta(days=3)
        ).context["report"]
        self.assertEqual(report["kind"], forecast.OK_FORECAST)
        self.assertEqual(report["reset_on"], RESET)
        self.assertEqual(
            [step["event"] for step in report["steps"]],
            ["Balance Now", "Monthly Reset"],
        )
        reset = report["steps"][1]
        self.assertEqual(reset["date"], RESET.strftime("%d %b %Y"))
        self.assertEqual(
            (reset["allowance"], reset["carryforward"], reset["balance"]),
            ("10", "0", "10"),
        )
        self.assertEqual(report["deductions"][-1], ("This Request", "-3"))
        self.assertEqual(report["left"], "7")
        self.assertIn("Resets Monthly On Day 1", report["policy"])

    def test_a_future_leave_the_balance_covers_shows_no_forecast(self):
        self.balance(available=5)
        response = self.widget(RESET + timedelta(days=5), RESET + timedelta(days=6))
        report = response.context["report"]
        self.assertEqual(report["kind"], forecast.OK_NOW)
        self.assertEqual(len(report["steps"]), 1)  # just "Balance Now"
        self.assertEqual(report["left"], "3")
        self.assertEqual(response.context["forcasted_days"], 0)

    def test_only_the_resets_up_to_the_first_that_covers_the_leave_are_rows(self):
        self.balance(available=1)
        report = self.widget(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=2)
        ).context["report"]
        self.assertEqual(
            len(report["steps"]), 2
        )  # now, and the first reset: 10 days is enough for 2
        self.assertEqual(report["reset_on"], RESET)

    def test_a_short_leave_says_by_how_much(self):
        self.balance(available=1)
        response = self.widget(TODAY + timedelta(days=1), TODAY + timedelta(days=3))
        report = response.context["report"]
        self.assertEqual(report["kind"], forecast.SHORT)
        self.assertEqual(report["short_by"], "2")
        self.assertContains(response, "Short By")

    def test_a_leave_in_the_current_cycle_has_no_reset_row(self):
        self.balance(available=5)
        report = self.widget(
            TODAY + timedelta(days=1), TODAY + timedelta(days=2)
        ).context["report"]
        self.assertEqual(report["kind"], forecast.OK_NOW)
        self.assertEqual(len(report["steps"]), 1)

    def test_a_request_is_not_counted_against_itself(self):
        self.balance(available=0)
        waiting = self.leave(
            RESET + timedelta(days=1), RESET + timedelta(days=8)
        )  # 8 of 10 days
        start, end = RESET + timedelta(days=1), RESET + timedelta(days=8)
        other = self.widget(start, end).context["report"]
        own = self.widget(start, end, leave_request=waiting.pk).context["report"]
        self.assertEqual(other["kind"], forecast.SHORT)
        self.assertEqual(own["kind"], forecast.OK_FORECAST)

    def test_hr_gets_the_forecast_behind_the_balance_pill(self):
        self.balance(available=1)
        response = self.widget(RESET + timedelta(days=1), RESET + timedelta(days=3))
        self.assertTrue(response.context["can_see_forecast"])
        self.assertContains(response, 'id="forecastReport"')
        self.assertContains(response, "Leave Count")
        self.assertNotContains(response, "Allowance")

    def test_the_pill_shows_the_balance_the_forecast_ends_on(self):
        self.balance(available=1)
        response = self.widget(
            NEXT_RESET + timedelta(days=1), NEXT_RESET + timedelta(days=2)
        )
        report = response.context["report"]
        # Judged against the first reset (10 days), not the most any later reset could hold.
        self.assertEqual(response.context["total_leave_days"], 10)
        self.assertEqual(report["steps"][-1]["balance"], "10")

    def test_the_forecast_lists_the_dates_already_booked(self):
        avail = self.balance(available=0)
        booked = self.leave(RESET + timedelta(days=1), RESET + timedelta(days=3))
        charge_leave_request(
            booked,
            avail,
            result=forecast.check(avail, booked.end_date, booked.requested_days),
        )
        avail.save()
        LeaveRequest.objects.filter(pk=booked.pk).update(
            status="approved", provided_cycle=booked.provided_cycle
        )
        other = self.leave(RESET + timedelta(days=6), RESET + timedelta(days=6))
        report = self.widget(
            RESET + timedelta(days=8), RESET + timedelta(days=9)
        ).context["report"]
        self.assertEqual(len(report["booked"]), 2)
        forecasted = [row for row in report["booked"] if "Forecasted" in row["status"]]
        waiting = [row for row in report["booked"] if row["status"] == "Waiting"]
        self.assertEqual(forecasted[0]["days"], "3")
        self.assertTrue(forecasted[0]["status"].startswith("Approved"))
        self.assertEqual(waiting[0]["dates"], other.start_date.strftime("%d %b %Y"))

    def test_an_employee_only_sees_the_balance(self):
        user = make_user("forecast_plain", password="secret123")
        make_employee(
            company=self.employee.employee_work_info.company_id,
            email="forecast_plain@test.horilla",
            user=user,
        )
        self.balance(available=1)
        self.client.force_login(user)
        response = self.widget(RESET + timedelta(days=1), RESET + timedelta(days=3))
        self.assertFalse(response.context["can_see_forecast"])
        self.assertNotContains(response, 'id="forecastReport"')
        self.assertNotContains(response, "Click To View The Forecast")
        self.assertContains(response, "Available Leaves")

    def test_no_limit_has_no_report(self):
        self.leave_type.limit_leave = False
        self.leave_type.save()
        self.balance(available=0)
        self.assertIsNone(
            self.widget(TODAY + timedelta(days=1), TODAY + timedelta(days=2)).context[
                "report"
            ]
        )


class ResetRuleSyncTests(ForecastBase):
    """Changing a leave type's reset schedule moves the next reset of its balances."""

    def make(self, reset_date):
        balance = self.balance(available=3)
        AvailableLeave.objects.filter(pk=balance.pk).update(reset_date=reset_date)
        return balance

    def test_a_changed_schedule_moves_a_stale_reset_date(self):
        stale = TODAY + timedelta(days=200)
        balance = self.make(stale)
        self.leave_type.reset_day = "15"
        self.leave_type.save()
        balance.refresh_from_db()
        self.assertEqual(balance.reset_date.day, 15)
        self.assertGreater(balance.reset_date, TODAY)
        self.assertLess(balance.reset_date, stale)

    def test_an_unrelated_change_leaves_the_dates_alone(self):
        stale = TODAY + timedelta(days=200)
        balance = self.make(stale)
        self.leave_type.name = "Renamed"
        self.leave_type.save()
        balance.refresh_from_db()
        self.assertEqual(balance.reset_date, stale)

    def test_a_reset_that_is_already_due_is_left_for_the_scheduler(self):
        due = TODAY - timedelta(days=1)
        balance = self.make(due)
        self.leave_type.reset_day = "15"
        self.leave_type.save()
        balance.refresh_from_db()
        self.assertEqual(balance.reset_date, due)

    def test_a_balance_brought_forward_keeps_its_reset_date(self):
        avail = self.balance(available=1)
        leave = self.leave(
            NEXT_RESET + timedelta(days=1),
            NEXT_RESET + timedelta(days=2),
            status="approved",
        )
        charge_leave_request(leave, avail)
        avail.save()
        LeaveRequest.objects.filter(pk=leave.pk).update(
            provided_cycle=leave.provided_cycle
        )
        avail.refresh_from_db()
        moved_to = avail.reset_date
        self.leave_type.reset_day = "15"
        self.leave_type.save()
        avail.refresh_from_db()
        self.assertEqual(avail.reset_date, moved_to)

    def test_the_forecast_follows_the_new_schedule(self):
        balance = self.make(TODAY + timedelta(days=200))
        self.leave_type.reset_based = "weekly"
        self.leave_type.reset_weekend = str(TODAY.weekday())
        self.leave_type.save()
        balance.refresh_from_db()
        end = TODAY + timedelta(days=15)
        self.assertEqual(len(forecast.reset_dates(balance, end)), 2)


class LeaveTypeTotalDaysTests(TestCase):
    """The leave type form asks for Total Days only, so saving it stores that many days."""

    def save_with_count(self, leave_type, count):
        from django.forms.models import model_to_dict

        from leave.forms import LeaveTypeForm

        data = {
            k: ("" if v is None else v)
            for k, v in model_to_dict(
                leave_type, exclude=["icon", "conditions"]
            ).items()
        }
        data["count"] = count
        form = LeaveTypeForm(data, instance=leave_type)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        leave_type.refresh_from_db()
        return leave_type

    def test_an_older_unit_does_not_multiply_the_days(self):
        leave_type = LeaveType.objects.create(
            name="Unit Leave", count=1, period_in="year", total_days=365, reset=False
        )
        leave_type = self.save_with_count(leave_type, 3)
        self.assertEqual(leave_type.period_in, "day")
        self.assertEqual(leave_type.total_days, 3)
