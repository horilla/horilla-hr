"""A pay run checks the recoveries due in it before generating, and notes a payslip that could not take them all."""

from datetime import date
from unittest.mock import patch

from payroll.methods import batch_run
from payroll.models.models import PayAdjustment, PayrollBatchLine, Payslip
from payroll.tests.test_batch_run import END, START, Fixture


class RunChecksFixture(Fixture):
    def recovery(
        self,
        employee,
        amount,
        title="Excess Paid",
        pay_date=date(2026, 4, 15),
        confirmed=True,
    ):
        entry = PayAdjustment.objects.create(
            employee_id=employee,
            kind="recovery",
            title=title,
            amount=amount,
            pay_date=pay_date,
        )
        if confirmed:
            entry.approve()
        return entry

    def contract_of(self, employee):
        return batch_run.contracts_in_period(employee, START, END)[-1][0]

    def review(self):
        with patch(
            "attendance.methods.utils.get_employee_attendance_summary",
            return_value=self.summary(),
        ):
            return batch_run.review(self.people, START, END)

    def row_of(self, result, employee):
        return next(row for row in result["rows"] if row["employee"] == employee)


class RecoveryOverPayTests(RunChecksFixture):
    def check(self, employee):
        return batch_run.recovery_over_pay(
            employee, self.contract_of(employee), START, END
        )

    def test_a_recovery_within_the_monthly_pay_is_fine(self):
        self.recovery(self.people[0], 5000.0)
        self.assertIsNone(self.check(self.people[0]))

    def test_a_recovery_over_the_monthly_pay_is_found_with_its_figures(self):
        self.recovery(self.people[0], 500000.0, title="Big One")
        self.assertEqual(self.check(self.people[0]), (500000.0, 30000.0, ["Big One"]))

    def test_recoveries_in_the_period_are_added_together(self):
        self.recovery(self.people[0], 20000.0, title="First")
        self.recovery(
            self.people[0], 15000.0, title="Second", pay_date=date(2026, 4, 20)
        )
        due, pay, titles = self.check(self.people[0])
        self.assertEqual((due, pay, titles), (35000.0, 30000.0, ["First", "Second"]))

    def test_drafts_arrears_other_months_and_other_people_are_ignored(self):
        self.recovery(self.people[0], 500000.0, title="Draft", confirmed=False)
        self.recovery(
            self.people[0], 500000.0, title="Next Month", pay_date=date(2026, 5, 15)
        )
        self.recovery(self.people[1], 500000.0, title="Someone Else")
        arrears = PayAdjustment.objects.create(
            employee_id=self.people[0],
            kind="arrears",
            title="Arrears",
            amount=900000.0,
            pay_date=date(2026, 4, 15),
        )
        arrears.approve()
        self.assertIsNone(self.check(self.people[0]))

    def test_without_a_period_or_a_monthly_pay_there_is_nothing_to_compare(self):
        self.recovery(self.people[0], 500000.0)
        contract = self.contract_of(self.people[0])
        self.assertIsNone(
            batch_run.recovery_over_pay(self.people[0], contract, None, None)
        )
        contract.wage = 0
        self.assertIsNone(
            batch_run.recovery_over_pay(self.people[0], contract, START, END)
        )


class ReviewStepTests(RunChecksFixture):
    def test_the_review_blocks_an_employee_whose_recoveries_exceed_their_pay(self):
        self.recovery(self.people[0], 500000.0, title="Big One")
        result = self.review()
        blocked = self.row_of(result, self.people[0])
        self.assertTrue(blocked["blocked"])
        self.assertEqual(result["blocked_count"], 1)
        severity, message = blocked["problems"][0]
        self.assertEqual(severity, batch_run.BLOCKING)
        for text in ("500,000.00", "30,000.00", "Big One", "Send Them Back To Draft"):
            self.assertIn(text, str(message))

    def test_everyone_else_is_still_ready(self):
        self.recovery(self.people[0], 500000.0)
        result = self.review()
        self.assertEqual(result["ready_count"], 2)
        self.assertFalse(self.row_of(result, self.people[1])["blocked"])

    def test_a_recovery_within_pay_does_not_block(self):
        self.recovery(self.people[0], 6000.0)
        self.assertEqual(self.review()["blocked_count"], 0)

    def test_sending_the_entry_back_to_draft_clears_the_block(self):
        entry = self.recovery(self.people[0], 500000.0)
        self.assertEqual(self.review()["blocked_count"], 1)
        entry.revert()
        entry.amount = 6000.0
        entry.save()
        entry.approve()
        self.assertEqual(self.review()["blocked_count"], 0)


class GenerationNoteTests(RunChecksFixture):
    def generate_one(self, pay_head_data):
        employee = self.people[0]
        batch = batch_run.create_batch(
            name="Note Run", start_date=START, end_date=END, employees=[employee]
        )
        line = batch.lines.get()
        batch_run._generate_one(
            batch,
            line,
            employee,
            {},
            payslip_fields=lambda *a, **k: {},
            save_payslip=lambda **k: Payslip.objects.create(
                employee_id=employee,
                start_date=START,
                end_date=END,
                pay_head_data=pay_head_data,
            ),
            payroll_calculation=lambda *a, **k: {},
        )
        line.refresh_from_db()
        return line

    def test_a_payslip_that_could_not_take_everything_is_noted_on_its_line(self):
        line = self.generate_one({"uncovered_deduction": 495400.0})
        self.assertEqual(line.status, PayrollBatchLine.DONE)
        self.assertIn("495,400.00 Could Not Be Deducted", line.message)

    def test_a_payslip_that_took_everything_has_no_note(self):
        line = self.generate_one({"uncovered_deduction": 0.0})
        self.assertEqual((line.status, line.message), (PayrollBatchLine.DONE, ""))

    def test_a_payslip_that_says_nothing_about_it_has_no_note(self):
        line = self.generate_one({})
        self.assertEqual((line.status, line.message), (PayrollBatchLine.DONE, ""))
