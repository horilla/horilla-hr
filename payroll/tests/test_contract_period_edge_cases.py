"""
Pay-period edge cases around contracts: starts, ends, change-overs and notice periods.

Each contract is paid for the days it was in force, at its own wage. March 2024 has 31 days and no
holidays here, so a day is wage / 31; April 2024 has 30, so a day is wage / 30. The notice-period
test is an ``expectedFailure``: payroll does not read the notice end yet, and the test states the
pay that is due once it does.
"""

from datetime import date, timedelta
from unittest import expectedFailure
from unittest.mock import patch

from django.test import TestCase

from employee.models import Employee
from horilla.testkit import make_company, make_employee
from offboarding.models import OffboardingEmployee
from payroll.methods import batch_run
from payroll.methods.contract_periods import contracts_in_period
from payroll.models.models import Contract, Payslip
from payroll.scheduler import generate_payslips
from payroll.tests.factories_payroll import make_allowance, make_deduction

START, END = date(2024, 3, 1), date(2024, 3, 31)
DAYS = 31


def day(n, month=3):
    return date(2024, month, n)


class ContractFixture(TestCase):
    def setUp(self):
        self.employee = make_employee(company=make_company("Edge Co"), email="edge@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def contract(self, name, start, end, wage, status="active"):
        """A monthly contract. A past end date makes it expired, as saving it does anywhere."""
        return Contract.objects.create(
            contract_name=name, employee_id=self.employee, contract_start_date=start,
            contract_end_date=end, wage_type="monthly", wage=wage, contract_status=status,
            deduct_leave_from_basic_pay=True, calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
        )

    def run_period(self, start=START, end=END):
        generate_payslips(Employee.objects.filter(pk=self.employee.pk), start, end)
        return list(Payslip.objects.filter(employee_id=self.employee).order_by("start_date"))

    def paid(self, slips):
        return sum(p.basic_pay for p in slips)

    def due(self, wage, first, last, days=DAYS):
        """What a contract at ``wage`` earns from ``first`` to ``last`` of a month of ``days`` days."""
        return round(wage / days * ((last - first).days + 1), 2)


class ContractPeriodEdgeCases(ContractFixture):
    # --- a contract that starts inside the period -------------------------------------------

    def test_a_contract_starting_mid_period_is_paid_from_its_start_date(self):
        self.contract("Joiner", day(16), None, 31000.0)
        slips = self.run_period()
        self.assertEqual(len(slips), 1)
        self.assertEqual((slips[0].start_date, slips[0].end_date), (day(16), END))
        self.assertAlmostEqual(self.paid(slips), self.due(31000.0, day(16), END), places=2)

    def test_a_contract_starting_on_the_first_day_is_paid_the_whole_period(self):
        self.contract("Day One", START, None, 31000.0)
        slips = self.run_period()
        self.assertEqual((slips[0].start_date, slips[0].end_date), (START, END))
        self.assertAlmostEqual(self.paid(slips), 31000.0, places=2)

    def test_a_contract_starting_on_the_last_day_is_paid_one_day(self):
        self.contract("Last Day", END, None, 31000.0)
        slips = self.run_period()
        self.assertEqual((slips[0].start_date, slips[0].end_date), (END, END))
        self.assertAlmostEqual(self.paid(slips), 1000.0, places=2)

    def test_a_contract_starting_after_the_period_gets_no_payslip(self):
        self.contract("Next Month", date(2024, 4, 1), None, 31000.0)
        self.assertEqual(self.run_period(), [])

    def test_running_the_period_twice_does_not_duplicate_a_mid_period_payslip(self):
        self.contract("Joiner", day(16), None, 31000.0)
        self.run_period()
        self.assertEqual(len(self.run_period()), 1)

    # --- a contract that ends inside the period ---------------------------------------------

    def test_a_contract_ending_mid_period_is_paid_to_its_end_date(self):
        self.contract("Leaver", START, day(20), 31000.0)
        slips = self.run_period()
        self.assertEqual((slips[0].start_date, slips[0].end_date), (START, day(20)))
        self.assertAlmostEqual(self.paid(slips), self.due(31000.0, START, day(20)), places=2)

    def test_a_contract_ending_on_the_last_day_of_the_period_is_paid_in_full(self):
        self.contract("Month End", START, END, 31000.0)
        slips = self.run_period()
        self.assertAlmostEqual(self.paid(slips), 31000.0, places=2)

    def test_a_contract_that_ended_before_the_period_gets_no_payslip(self):
        self.contract("Long Gone", date(2024, 1, 1), date(2024, 2, 29), 31000.0)
        self.assertEqual(self.run_period(), [])

    def test_an_expired_contract_with_no_end_date_is_not_paid(self):
        """It is not known when it stopped, so there are no days to pay."""
        self.contract("No End", date(2024, 1, 1), None, 31000.0, status="expired")
        self.assertEqual(self.run_period(), [])

    def test_a_terminated_or_draft_contract_is_not_paid(self):
        self.contract("Dropped", START, None, 31000.0, status="terminated")
        self.assertEqual(self.run_period(), [])

    # --- one contract replaced by another ----------------------------------------------------

    def test_a_new_contract_the_day_after_the_old_one_ends_pays_each_its_own_days(self):
        self.contract("Old", START, day(15), 30000.0)
        self.contract("New", day(16), None, 45000.0)
        slips = self.run_period()
        self.assertEqual([(p.start_date, p.end_date) for p in slips], [(START, day(15)), (day(16), END)])
        self.assertEqual([p.contract_wage for p in slips], [30000.0, 45000.0])
        expected = self.due(30000.0, START, day(15)) + self.due(45000.0, day(16), END)
        self.assertAlmostEqual(self.paid(slips), expected, places=2)

    def test_a_gap_between_two_contracts_is_not_paid(self):
        self.contract("Old", START, day(15), 30000.0)
        self.contract("New", day(20), None, 45000.0)
        slips = self.run_period()
        self.assertEqual([(p.start_date, p.end_date) for p in slips], [(START, day(15)), (day(20), END)])
        expected = self.due(30000.0, START, day(15)) + self.due(45000.0, day(20), END)
        self.assertAlmostEqual(self.paid(slips), expected, places=2)

    def test_overlapping_contracts_pay_each_day_once(self):
        """The later contract takes over on its start date; the overlap is paid at its wage."""
        self.contract("Old", START, day(20), 30000.0)
        self.contract("New", day(16), None, 45000.0)
        slips = self.run_period()
        self.assertEqual([(p.start_date, p.end_date) for p in slips], [(START, day(15)), (day(16), END)])
        expected = self.due(30000.0, START, day(15)) + self.due(45000.0, day(16), END)
        self.assertAlmostEqual(self.paid(slips), expected, places=2)

    def test_three_contracts_in_one_period_each_get_their_own_slice(self):
        self.contract("One", START, day(10), 31000.0)
        self.contract("Two", day(11), day(20), 62000.0)
        self.contract("Three", day(21), None, 31000.0)
        slips = self.run_period()
        self.assertEqual(len(slips), 3)
        expected = self.due(31000.0, START, day(10)) + self.due(62000.0, day(11), day(20)) + self.due(31000.0, day(21), END)
        self.assertAlmostEqual(self.paid(slips), expected, places=2)

    def test_running_a_changeover_period_twice_does_not_duplicate_payslips(self):
        self.contract("Old", START, day(15), 30000.0)
        self.contract("New", day(16), None, 45000.0)
        self.run_period()
        self.assertEqual(len(self.run_period()), 2)

    def test_the_slices_are_the_contracts_days_in_date_order(self):
        self.contract("Old", START, day(15), 30000.0)
        self.contract("New", day(16), None, 45000.0)
        slices = contracts_in_period(self.employee, START, END)
        self.assertEqual([(c.contract_name, a, b) for c, a, b in slices], [("Old", START, day(15)), ("New", day(16), END)])

    # --- a notice period that ends inside the period ----------------------------------------

    @expectedFailure
    def test_pay_stops_when_the_notice_period_ends_mid_period(self):
        """Gap: the contract has no end date and payroll never reads the notice end, so the full period is paid."""
        self.contract("Resigning", START, None, 31000.0)
        OffboardingEmployee.objects.create(
            employee_id=self.employee, notice_period_starts=day(1), notice_period_ends=day(20),
        )
        slips = self.run_period()
        self.assertEqual(slips[-1].end_date, day(20))
        self.assertAlmostEqual(self.paid(slips), self.due(31000.0, START, day(20)), places=2)

    def test_a_notice_period_ending_after_the_period_does_not_shorten_it(self):
        self.contract("Resigning", START, None, 31000.0)
        OffboardingEmployee.objects.create(
            employee_id=self.employee, notice_period_starts=day(1), notice_period_ends=END + timedelta(days=10),
        )
        slips = self.run_period()
        self.assertEqual((slips[0].start_date, slips[0].end_date), (START, END))
        self.assertAlmostEqual(self.paid(slips), 31000.0, places=2)


class WholePayslipOnEachContract(ContractFixture):
    """April 2024, 30 days: 3,000 for the 1st to 15th, then 6,000 for the 16th to 30th, with components."""

    def setUp(self):
        super().setUp()
        self.contract("First Half", day(1, 4), day(15, 4), 3000.0)
        self.contract("Second Half", day(16, 4), None, 6000.0)
        make_allowance(self.employee, "HRA Fixed", is_fixed=True, amount=600.0)
        make_allowance(self.employee, "Bonus 10 Percent", is_fixed=False, based_on="basic_pay", rate=10.0)
        make_deduction(self.employee, "PF Pretax", is_fixed=True, amount=100.0, is_pretax=True)
        make_deduction(self.employee, "Lunch Posttax", is_fixed=True, amount=50.0)
        self.slips = self.run_period(day(1, 4), day(30, 4))

    def test_there_is_a_payslip_for_each_half(self):
        self.assertEqual([(p.start_date, p.end_date) for p in self.slips], [(day(1, 4), day(15, 4)), (day(16, 4), day(30, 4))])

    def test_the_first_half_is_worked_out_on_the_first_contract(self):
        first = self.slips[0]
        self.assertEqual(first.contract_wage, 3000.0)
        self.assertAlmostEqual(first.basic_pay, 1500.0, places=2)
        self.assertAlmostEqual(first.gross_pay, 1950.0, places=2)   # 1,500 + HRA 300 + bonus 150
        self.assertAlmostEqual(first.net_pay, 1875.0, places=2)     # less 50 pre-tax and 25 post-tax

    def test_the_second_half_is_worked_out_on_the_second_contract(self):
        second = self.slips[1]
        self.assertEqual(second.contract_wage, 6000.0)
        self.assertAlmostEqual(second.basic_pay, 3000.0, places=2)
        self.assertAlmostEqual(second.gross_pay, 3600.0, places=2)  # 3,000 + HRA 300 + bonus 300
        self.assertAlmostEqual(second.net_pay, 3525.0, places=2)

    def test_the_month_adds_up_to_both_halves(self):
        self.assertAlmostEqual(sum(p.net_pay for p in self.slips), 5400.0, places=2)


def _slice_summary(days):
    return {
        "present": days, "paid_leave": 0, "unpaid_leave": 0, "absent": 0, "week_off": 0, "holiday": 0,
        "total_working": days, "unresolved_conflicts": 0, "paid_days": days, "unpaid_days": 0,
    }


class BatchRunOnEachContract(ContractFixture):
    """The reviewed batch run pays each contract its own days too."""

    def run_batch(self, start, end, summary_for):
        batch = batch_run.create_batch(name="Batch", start_date=start, end_date=end, employees=[self.employee])
        with patch.object(batch_run, "_summaries_for", return_value={}), patch.object(
            batch_run, "_slice_summary", side_effect=lambda employee, first, last: summary_for(first, last)
        ):
            while batch_run.generate_slice(batch):
                pass
        return list(Payslip.objects.filter(payroll_batch=batch).order_by("start_date")), batch

    def test_a_changeover_gives_one_payslip_per_contract_in_the_batch(self):
        self.contract("First Half", day(1, 4), day(15, 4), 3000.0)
        self.contract("Second Half", day(16, 4), None, 6000.0)
        slips, batch = self.run_batch(day(1, 4), day(30, 4), lambda a, b: _slice_summary((b - a).days + 1))
        self.assertEqual([(p.start_date, p.end_date, p.contract_wage) for p in slips],
                         [(day(1, 4), day(15, 4), 3000.0), (day(16, 4), day(30, 4), 6000.0)])
        self.assertAlmostEqual(slips[0].basic_pay, 1500.0, places=2)
        self.assertAlmostEqual(slips[1].basic_pay, 3000.0, places=2)
        self.assertEqual(batch.lines.get().payslip.pk, slips[-1].pk)

    def test_an_unpaid_day_in_one_contract_only_costs_that_contracts_rate(self):
        self.contract("First Half", day(1, 4), day(15, 4), 3000.0)
        self.contract("Second Half", day(16, 4), None, 6000.0)

        def summary(first, last):
            days = (last - first).days + 1
            return {**_slice_summary(days - 1), "absent": 1, "paid_days": days - 1, "unpaid_days": 1}

        slips, _batch = self.run_batch(day(1, 4), day(30, 4), summary)
        self.assertAlmostEqual(slips[0].basic_pay, 1500.0 - 100.0, places=2)   # 3,000 / 30 a day
        self.assertAlmostEqual(slips[1].basic_pay, 3000.0 - 200.0, places=2)   # 6,000 / 30 a day

    def test_a_contract_that_ended_mid_period_is_eligible_and_paid_to_its_end(self):
        self.contract("Leaver", day(1, 4), day(20, 4), 3000.0)
        ok, excluded = batch_run.eligible_employees([self.employee], day(1, 4), day(30, 4))
        self.assertEqual((ok, excluded), ([self.employee], []))
        slips, _batch = self.run_batch(day(1, 4), day(30, 4), lambda a, b: _slice_summary((b - a).days + 1))
        self.assertEqual([(p.start_date, p.end_date) for p in slips], [(day(1, 4), day(20, 4))])

    def test_no_contract_in_the_period_is_excluded_with_a_reason(self):
        self.contract("Long Gone", date(2024, 1, 1), date(2024, 2, 29), 3000.0)
        ok, excluded = batch_run.eligible_employees([self.employee], day(1, 4), day(30, 4))
        self.assertEqual(ok, [])
        self.assertIn("No contract in force", str(excluded[0][1]))
