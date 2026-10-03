"""Hourly salary computation against Main's payroll.methods.hourly_computation."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.methods import compute_salary_on_period, hourly_computation
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract


class HourlyComputationTests(TestCase):
    def setUp(self):
        company = make_company("Hourly Co")
        self.employee = make_employee(company=company, email="hourly@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.workday = date(2024, 1, 8)  # Monday
        self.start = date(2024, 1, 1)
        self.end = date(2024, 1, 31)

    def _att(self, day, at_work, overtime=0):
        return SimpleNamespace(
            attendance_date=day,
            at_work_second=at_work,
            overtime_second=overtime,
        )

    @patch("payroll.methods.methods.get_attendance")
    def test_hourly_basic_pay_excludes_overtime_seconds(self, mock_att):
        # Main: paid seconds = at_work_second - overtime_second
        mock_att.return_value = {
            "attendances_on_period": [
                self._att(self.workday, at_work=28800, overtime=3600)
            ],
        }
        data = hourly_computation(self.employee, 100.0, self.start, self.end)
        # 25200s * (100/3600) = 700
        self.assertEqual(data["basic_pay"], 700.0)
        self.assertEqual(data["loss_of_pay"], 0)
        self.assertEqual(data["paid_days"], 1)
        self.assertEqual(data["unpaid_days"], 0)

    @patch("payroll.methods.methods.get_attendance")
    def test_hourly_sums_multiple_attendances(self, mock_att):
        mock_att.return_value = {
            "attendances_on_period": [
                self._att(date(2024, 1, 8), at_work=14400, overtime=0),
                self._att(date(2024, 1, 9), at_work=7200, overtime=0),
            ],
        }
        data = hourly_computation(self.employee, 50.0, self.start, self.end)
        # 21600s * (50/3600) = 300
        self.assertEqual(data["basic_pay"], 300.0)
        self.assertEqual(data["paid_days"], 2)

    @patch("payroll.methods.methods.months_between_range", return_value=[])
    @patch("payroll.methods.methods.get_attendance")
    def test_compute_salary_on_period_hourly(self, mock_att, _months):
        Contract.objects.create(
            contract_name="Hourly Active",
            employee_id=self.employee,
            contract_start_date=date(2024, 1, 1),
            wage_type="hourly",
            wage=100.0,
            contract_status="active",
        )
        mock_att.return_value = {
            "attendances_on_period": [
                self._att(self.workday, at_work=28800, overtime=3600)
            ],
        }
        data = compute_salary_on_period(self.employee, self.start, self.end)
        self.assertIsNotNone(data)
        self.assertEqual(data["basic_pay"], 700.0)
        self.assertEqual(data["contract_wage"], 100.0)
        self.assertEqual(data["paid_days"], 1)
        self.assertIn("month_data", data)


class HourlyWageFieldTests(TestCase):
    """
    The hourly rate has its own field.

    One column held a monthly salary for one contract and an hourly rate for
    the next, which is why every list showing it is ambiguous: 100 could be a
    month's pay or an hour's. The engine now reads `pay_rate`, which picks the
    box the wage type actually pays from.
    """

    def setUp(self):
        company = make_company("Hourly Co")
        self.employee = make_employee(company=company, email="hw@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def test_an_hourly_contract_pays_from_the_hourly_box(self):
        contract = make_active_contract(
            self.employee, wage_type="hourly", wage=0.0, hourly_wage=250.0
        )
        self.assertEqual(contract.pay_rate, 250.0)

    def test_an_hourly_contract_falls_back_to_the_wage(self):
        """
        Hourly contracts entered before the field existed keep their rate in
        `wage`, and have to keep paying exactly what they paid.
        """
        contract = make_active_contract(self.employee, wage_type="hourly", wage=100.0)
        self.assertEqual(contract.pay_rate, 100.0)

    def test_a_monthly_contract_ignores_the_hourly_box(self):
        """
        Filled in by mistake, or left behind by a change of wage type, it must
        not become the monthly salary.
        """
        contract = make_active_contract(
            self.employee, wage_type="monthly", wage=30000.0, hourly_wage=250.0
        )
        self.assertEqual(contract.pay_rate, 30000.0)

    def test_the_form_states_the_unit_and_stops_demanding_the_monthly_figure(self):
        from payroll.forms.forms import ContractForm

        form = ContractForm(instance=Contract(wage_type="hourly"))
        self.assertIn("per hour", form.fields["wage"].label)
        self.assertFalse(form.fields["wage"].required)

        monthly = ContractForm(instance=Contract(wage_type="monthly"))
        self.assertIn("per month", monthly.fields["wage"].label)
        self.assertTrue(monthly.fields["wage"].required)


class HourlyWithNoAttendanceTests(TestCase):
    """
    An hourly employee who logged no hours this period.

    Their contract is correctly configured — it states a rate — so they get a
    payslip of zero, which is the truthful answer. Resolving the basic-pay
    source from the period's computed amount instead of from the contract read
    this as "nothing states basic pay" and refused to produce a payslip at all.
    """

    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from payroll.models.models import Contract

        company = make_company("Hourly Zero Co")
        self.employee = make_employee(company=company, email="hourlyzero@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def _contract(self, **kwargs):
        from payroll.tests.factories_payroll import make_active_contract

        return make_active_contract(self.employee, **kwargs)

    def test_an_hourly_contract_with_a_rate_states_basic_pay(self):
        from payroll.methods.basic_pay_source import CONTRACT, resolve_basic_pay_source

        contract = self._contract(wage_type="hourly", wage=0, hourly_wage=10.0)
        source, _component = resolve_basic_pay_source(contract.pay_rate, [])
        self.assertEqual(source, CONTRACT)

    def test_a_contract_with_no_rate_at_all_still_states_nothing(self):
        """The refusal is still there for what it was written for."""
        from payroll.methods.basic_pay_source import NEITHER, resolve_basic_pay_source

        contract = self._contract(wage_type="hourly", wage=0, hourly_wage=0)
        source, _component = resolve_basic_pay_source(contract.pay_rate, [])
        self.assertEqual(source, NEITHER)

    def test_a_monthly_contract_on_full_loss_of_pay_still_states_basic_pay(self):
        """
        Same shape as the hourly case: the period computes to zero and the
        contract is fine.
        """
        from payroll.methods.basic_pay_source import CONTRACT, resolve_basic_pay_source

        contract = self._contract(wage=30000.0)
        source, _component = resolve_basic_pay_source(contract.pay_rate, [])
        self.assertEqual(source, CONTRACT)
