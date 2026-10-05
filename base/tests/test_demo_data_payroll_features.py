"""backfill_payroll_feature_coverage's CTC Down half.

The Gross Up half (structures_created/contracts_with_structure) already had
implicit coverage through the enterprise seeder's own smoke tests; this adds
the same scrutiny to the CTC Down structure/contracts this module now also
creates, since that path is new here and has real money at the end of it
(payroll_trend.backfill_payroll_coverage runs the real calculation engine
against whatever this leaves behind).
"""

from datetime import date

from django.test import TestCase

from base.demo_data.modules.payroll_features import backfill_payroll_feature_coverage
from horilla.testkit import make_company, make_employee
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import make_active_contract


class BackfillPayrollFeatureCoverageCtcDownTests(TestCase):
    def setUp(self):
        # The two component titles the module looks up by name -- without
        # these, its own Gross Up half already fails the same way the real
        # bug this test exists to catch would (a component set with no
        # is_basic_pay earning and a wage of 0).
        Allowance.objects.create(
            title="House Rent Allowance (HRA)",
            based_on="basic_pay",
            rate=40.0,
            is_fixed=False,
        )
        Allowance.objects.create(
            title="Meal Allowance",
            is_fixed=True,
            amount=1200.0,
        )
        Deduction.objects.create(
            title="Provident Fund (PF)",
            based_on="basic_pay",
            rate=12.0,
            is_fixed=False,
        )
        Deduction.objects.create(
            title="Professional Tax",
            is_fixed=True,
            amount=200.0,
        )

        self.company = make_company("Coverage Co")
        self.employees = []
        for i in range(8):
            employee = make_employee(company=self.company, email=f"cov{i}@test.horilla")
            # Employee.save() auto-creates a starter contract; the factory's
            # own active-contract-per-employee guard refuses a second one.
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(
                employee,
                contract_name=f"Coverage {i}",
                wage=25000.0 + i * 1000,
            )
            self.employees.append(employee)

    def test_every_company_gets_a_ctc_down_structure(self):
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        structure = SalaryStructure.objects.get(
            title="CTC Down Compensation Package", company_id=self.company
        )
        self.assertEqual(structure.structure_mode, "ctc_down")

    def test_ctc_down_structure_has_exactly_one_basic_pay_earning(self):
        """
        validate_component_set's own invariant: exactly one, not zero (no
        basic pay to tax) and not two (which one wins is undefined).
        """
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        structure = SalaryStructure.objects.get(
            title="CTC Down Compensation Package", company_id=self.company
        )
        basic_pay_earnings = structure.allowances.filter(is_basic_pay=True)
        self.assertEqual(basic_pay_earnings.count(), 1)
        self.assertEqual(basic_pay_earnings.first().code, "BASIC")

    def test_ctc_down_contracts_state_ctc_not_wage(self):
        """
        resolve_basic_pay_source reads contract.pay_rate: a nonzero wage
        alongside the flagged component double-counts basic pay on top of
        the package, which is why this must land on wage=0.
        """
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        ctc_contracts = Contract.objects.filter(
            employee_id__in=self.employees,
            salary_structure_id__structure_mode="ctc_down",
        )
        self.assertGreater(ctc_contracts.count(), 0)
        for contract in ctc_contracts:
            self.assertEqual(contract.wage, 0)
            self.assertGreater(contract.monthly_ctc, 0)

    def test_gross_up_and_ctc_down_contracts_do_not_overlap(self):
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        gross_up_ids = set(
            Contract.objects.filter(
                employee_id__in=self.employees,
                salary_structure_id__structure_mode="gross_up",
            ).values_list("employee_id", flat=True)
        )
        ctc_down_ids = set(
            Contract.objects.filter(
                employee_id__in=self.employees,
                salary_structure_id__structure_mode="ctc_down",
            ).values_list("employee_id", flat=True)
        )
        self.assertEqual(gross_up_ids & ctc_down_ids, set())
        self.assertGreater(len(ctc_down_ids), 0)

    def test_contracts_default_to_calendar_day_lop(self):
        """
        Every make_active_contract() row here starts at the model's own
        default ("working_days"), same as every fixture contract does --
        this backfill is what moves the whole demo dataset onto calendar
        days, matching the "of <calendar days>" figure the payslip itself
        now shows.
        """
        for contract in Contract.objects.filter(employee_id__in=self.employees):
            self.assertEqual(contract.daily_leave_amount_divisor, "working_days")

        backfill_payroll_feature_coverage(today=date(2026, 9, 1))

        for contract in Contract.objects.filter(employee_id__in=self.employees):
            self.assertEqual(contract.daily_leave_amount_divisor, "calendar_days")

    def test_a_ctc_down_contract_actually_computes_a_payslip(self):
        """
        The real gap this whole change closes: not just that the structure
        and the contract exist, but that the engine can be pointed at one of
        these employees and get a real payslip back rather than
        StructureConfigurationError -- which is exactly the failure mode a
        wage of 0 with no basic-pay earning produces.
        """
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        ctc_contract = Contract.objects.filter(
            employee_id__in=self.employees,
            salary_structure_id__structure_mode="ctc_down",
        ).first()
        self.assertIsNotNone(ctc_contract)

        data = payroll_calculation(
            ctc_contract.employee_id, date(2026, 8, 1), date(2026, 8, 31)
        )
        self.assertIsNotNone(data)
        self.assertGreater(data["basic_pay"], 0)

    def test_rerunning_is_idempotent(self):
        """A reload calls this again; it must not duplicate structures or
        error on contracts it already moved last time."""
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        backfill_payroll_feature_coverage(today=date(2026, 9, 1))
        self.assertEqual(
            SalaryStructure.objects.filter(
                title="CTC Down Compensation Package", company_id=self.company
            ).count(),
            1,
        )
