"""Tests for leave reset scheduling: weekly reset dates, missed scheduler
ticks, and reset-history labeling."""

from datetime import date, timedelta

from django.test import TestCase


class WeeklyResetDateTests(TestCase):
    """LeaveType.leave_type_next_reset_date() for reset_based='weekly'."""

    def setUp(self):
        from leave.models import LeaveType

        self.LeaveType = LeaveType

    def test_weekly_reset_lands_on_target_weekday(self):
        lt = self.LeaveType.objects.create(
            name="Weekly Reset Wednesday",
            total_days=2,
            reset=True,
            reset_based="weekly",
            reset_weekend="2",  # Wednesday
        )
        # Previously raised TypeError: list indices must be integers or
        # slices, not str (WEEK_DAYS[self.reset_day] on the wrong field).
        next_date = lt.leave_type_next_reset_date()
        self.assertEqual(next_date.weekday(), 2)


class ResetSchedulerTests(TestCase):
    """leave.scheduler.leave_reset()."""

    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Reset Scheduler Co")
        self.employee = make_employee(company=company, email="reset-sched@test.horilla")
        self.LeaveType = LeaveType
        self.AvailableLeave = AvailableLeave

    def test_missed_tick_reset_date_still_processed(self):
        """
        A reset_date already in the past (e.g. the scheduler process was
        down on the exact day it was due) must still be picked up --
        previously used `==` instead of `<=`, so a missed tick meant that
        employee's leave never reset again.
        """
        from leave.scheduler import leave_reset

        lt = self.LeaveType.objects.create(
            name="Missed Tick Type",
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
            reset_date=date.today() - timedelta(days=5),
        )

        leave_reset()

        avail.refresh_from_db()
        self.assertEqual(avail.available_days, 10)
        self.assertGreater(avail.reset_date, date.today() - timedelta(days=5))

    def test_reset_labels_history_with_a_change_reason(self):
        from leave.scheduler import leave_reset

        lt = self.LeaveType.objects.create(
            name="History Label Type",
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

        latest_history = avail.history.order_by("-history_date").first()
        self.assertEqual(latest_history.history_change_reason, "Leave reset")
