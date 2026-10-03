"""
Running payroll for a group, as a reviewable operation.

The old bulk generate wrote payslips straight to the database from a modal
holding a batch name and two dates. Nothing said who was included, nothing
said why anyone was left out, and nothing was checked — so a wrong payslip was
the first sign of a problem.

The tests that matter here are the ones about what the review step REFUSES,
and about a run being resumable without paying anyone twice.
"""

import logging
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods import batch_run
from payroll.models.models import (
    Allowance,
    Contract,
    PayrollBatch,
    PayrollBatchLine,
    Payslip,
    SalaryStructure,
)
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 4, 1)
END = date(2026, 4, 30)

EMPTY_LEAVES = {
    "paid_leave": 0,
    "unpaid_leaves": 0,
    "partial_pay_days": 0,
    "total_leaves": 0,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}


def months(wage, *_a, **_kw):
    return [
        {
            "working_days_on_period": 22,
            "working_days_on_month": 22,
            "days": 30,
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "per_day_amount": float(wage or 0) / 22,
        }
    ]


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Batch Co")
        self.people = []
        for name in ("Ann", "Ben", "Cara"):
            employee = make_employee(
                company=self.company,
                email=f"{name.lower()}@test.horilla",
                first_name=name,
            )
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(employee, wage=30000.0)
            self.people.append(employee)

    def summary(self, **overrides):
        base = {
            "present": 22,
            "paid_leave": 0,
            "unpaid_leave": 0,
            "absent": 0,
            "week_off": 8,
            "holiday": 0,
            "total_working": 22,
            "unresolved_conflicts": 0,
            "overtime_label": "0h 00m",
            "paid_days": 30,
            "unpaid_days": 0,
        }
        base.update(overrides)
        return {employee.pk: dict(base) for employee in self.people}


class EligibilityTests(Fixture):
    def test_everyone_with_an_active_contract_is_eligible(self):
        ok, excluded = batch_run.eligible_employees(self.people, START, END)
        self.assertEqual(len(ok), 3)
        self.assertEqual(excluded, [])

    def test_no_active_contract_is_excluded_with_a_reason(self):
        Contract.objects.filter(employee_id=self.people[0]).delete()
        ok, excluded = batch_run.eligible_employees(self.people, START, END)

        self.assertEqual(len(ok), 2)
        self.assertEqual(excluded[0][0], self.people[0])
        self.assertIn("No active contract", str(excluded[0][1]))

    def test_a_contract_starting_after_the_period_is_excluded(self):
        contract = Contract.objects.get(employee_id=self.people[1])
        contract.contract_start_date = date(2026, 6, 1)
        contract.save()

        _ok, excluded = batch_run.eligible_employees(self.people, START, END)
        self.assertIn(self.people[1], [employee for employee, _r in excluded])

    def test_an_existing_payslip_excludes_rather_than_erroring(self):
        """
        The model refuses a second payslip for the same period, so catching it
        here is the difference between a listed exclusion and an exception
        halfway through a run.
        """
        Payslip.objects.create(
            employee_id=self.people[2],
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=1,
            contract_wage=1,
            gross_pay=1,
            deduction=0,
            net_pay=1,
            pay_head_data={},
        )
        ok, excluded = batch_run.eligible_employees(self.people, START, END)

        self.assertNotIn(self.people[2], ok)
        self.assertIn("Already has a payslip", str(dict(excluded)[self.people[2]]))


class ReviewTests(Fixture):
    def review(self, summaries):
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value=summaries,
        ):
            return batch_run.review(self.people, START, END)

    def test_a_clean_period_blocks_nobody(self):
        result = self.review(self.summary())
        self.assertEqual(result["blocked_count"], 0)
        self.assertEqual(result["ready_count"], 3)

    def test_an_unresolved_conflict_blocks_the_employee(self):
        """
        The rule it guards: in compute_salary_on_period a single unresolved
        conflict day makes the whole month unpaid. Blocking here does not
        change that rule — it makes it impossible to hit unknowingly.
        """
        summaries = self.summary()
        summaries[self.people[0].pk]["unresolved_conflicts"] = 1

        result = self.review(summaries)
        blocked = [row for row in result["rows"] if row["blocked"]]

        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["employee"], self.people[0])
        self.assertIn("whole month unpaid", str(blocked[0]["problems"][0][1]))

    def test_a_contract_with_no_pay_source_blocks(self):
        contract = Contract.objects.get(employee_id=self.people[1])
        contract.wage = 0
        contract.hourly_wage = 0
        contract.save()

        result = self.review(self.summary())
        blocked = [row for row in result["rows"] if row["blocked"]]
        self.assertEqual(blocked[0]["employee"], self.people[1])

    def test_a_flagged_earning_means_a_zero_wage_is_not_blocked(self):
        """The structure works basic out, so the contract does not have to."""
        structure = SalaryStructure.objects.create(title="CTC")
        structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay", is_basic_pay=True, is_fixed=True, amount=20000.0
            )
        )
        contract = Contract.objects.get(employee_id=self.people[1])
        contract.wage = 0
        contract.hourly_wage = 0
        contract.salary_structure_id = structure
        contract.save()

        result = self.review(self.summary())
        self.assertEqual(result["blocked_count"], 0)

    def test_no_structure_is_a_warning_not_a_block(self):
        result = self.review(self.summary())
        warnings = [
            message
            for row in result["rows"]
            for level, message in row["problems"]
            if level == batch_run.WARNING
        ]
        self.assertTrue(warnings)
        self.assertEqual(result["blocked_count"], 0)

    def test_blocked_rows_sort_first(self):
        """They are the reason the screen is being read."""
        summaries = self.summary()
        summaries[self.people[2].pk]["unresolved_conflicts"] = 2

        rows = self.review(summaries)["rows"]
        self.assertTrue(rows[0]["blocked"])

    def test_review_creates_nothing(self):
        self.review(self.summary())
        self.assertEqual(PayrollBatch.objects.count(), 0)
        self.assertEqual(Payslip.objects.count(), 0)


class BatchCreationTests(Fixture):
    def test_the_batch_exists_before_anything_is_generated(self):
        """
        So an interrupted run is listed and resumable rather than invisible.
        """
        batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        self.assertEqual(batch.employee_count, 3)
        self.assertEqual(batch.lines.count(), 3)
        self.assertEqual(batch.progress_state, PayrollBatch.PENDING)
        self.assertEqual(Payslip.objects.count(), 0)

    def test_every_employee_is_queued(self):
        batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        self.assertEqual(batch.lines.filter(status=PayrollBatchLine.QUEUED).count(), 3)


class GenerationTests(Fixture):
    def make_batch(self):
        return batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )

    def generate(self, batch, size=batch_run.SLICE_SIZE):
        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ), patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value={},
        ):
            return batch_run.generate_slice(batch, size=size)

    def test_a_slice_generates_only_its_share(self):
        batch = self.make_batch()
        self.assertEqual(self.generate(batch, size=2), 2)
        self.assertEqual(batch.payslips.count(), 2)
        self.assertEqual(batch.lines.filter(status=PayrollBatchLine.QUEUED).count(), 1)

    def test_running_to_completion_pays_everyone_once(self):
        batch = self.make_batch()
        while self.generate(batch, size=2):
            pass

        batch.refresh_from_db()
        self.assertEqual(batch.payslips.count(), 3)
        self.assertEqual(batch.progress_state, PayrollBatch.DONE)
        self.assertEqual(batch.percent_complete, 100)

    def test_resuming_does_not_pay_anyone_twice(self):
        """
        The whole reason lines carry a status. A resumed run that re-read its
        employee list instead would generate duplicates.
        """
        batch = self.make_batch()
        self.generate(batch, size=2)
        self.generate(batch, size=2)
        self.generate(batch, size=2)

        self.assertEqual(batch.payslips.count(), 3)
        for employee in self.people:
            self.assertEqual(
                Payslip.objects.filter(
                    employee_id=employee, start_date=START, end_date=END
                ).count(),
                1,
            )

    def test_the_payslips_are_attached_to_the_batch(self):
        batch = self.make_batch()
        while self.generate(batch):
            pass

        for payslip in Payslip.objects.all():
            self.assertEqual(payslip.payroll_batch, batch)
            self.assertEqual(payslip.group_name, "April")

    def test_totals_are_recorded_on_the_batch(self):
        batch = self.make_batch()
        while self.generate(batch):
            pass
        batch.refresh_from_db()

        self.assertEqual(batch.generated_count, 3)
        self.assertAlmostEqual(
            batch.total_net,
            sum(payslip.net_pay for payslip in Payslip.objects.all()),
            places=2,
        )

    def test_one_failure_does_not_stop_the_others(self):
        """
        A misconfigured contract is one person's problem. The run continues
        and the result says whose.
        """
        from payroll.methods.payroll_run import payroll_calculation as real_calc

        batch = self.make_batch()
        target = self.people[0]

        def explode(employee, *args, **kwargs):
            if employee.pk == target.pk:
                raise ValueError("boom")
            return real_calc(employee, *args, **kwargs)

        # The handler logs the traceback, which is the point of it; muted here
        # so a deliberate failure does not read like a broken test run.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        with patch(
            "payroll.methods.payroll_run.payroll_calculation", side_effect=explode
        ), patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ), patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value={},
        ):
            while batch_run.generate_slice(batch, size=1):
                pass

        batch.refresh_from_db()
        failed = batch.lines.filter(status=PayrollBatchLine.FAILED)
        self.assertEqual(failed.count(), 1)
        self.assertEqual(failed.first().employee_id, target)
        self.assertIn("boom", failed.first().message)
        self.assertEqual(batch.payslips.count(), 2)


class StatusTests(TestCase):
    def setUp(self):
        self.batch = PayrollBatch.objects.create(
            batch_name="April", period_start=START, period_end=END
        )

    def test_a_run_cannot_be_approved_before_it_has_finished(self):
        allowed, reason = self.batch.can_transition_to(PayrollBatch.APPROVED)
        self.assertFalse(allowed)
        self.assertIn("not finished generating", str(reason))

    def test_a_finished_run_can_be_approved(self):
        self.batch.progress_state = PayrollBatch.DONE
        self.batch.save()
        allowed, _reason = self.batch.can_transition_to(PayrollBatch.APPROVED)
        self.assertTrue(allowed)

    def test_paid_is_terminal(self):
        self.batch.status = PayrollBatch.PAID
        self.batch.progress_state = PayrollBatch.DONE
        self.batch.save()

        for target in (
            PayrollBatch.DRAFT,
            PayrollBatch.REVIEW,
            PayrollBatch.APPROVED,
        ):
            with self.subTest(target=target):
                allowed, reason = self.batch.can_transition_to(target)
                self.assertFalse(allowed)
                self.assertIn("cannot be changed", str(reason))
