"""
An earning paid outside the salary structure (a bonus, a one-time allowance) sits on top of a CTC Down
package: it does not shrink the balance component, and a full pay month pays its fixed amount in full.
"""

from datetime import date

from payroll.methods.earning_working import earning_workings
from payroll.methods.proration import MONTH_CALENDAR_DAYS, period_factor
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    Payslip,
    SalaryStructure,
)
from payroll.tests.test_contract_structure_types import StructureTypeFixture, day


def month(start, end, days):
    return {"start_date": start, "end_date": end, "days": days}


class FullPayMonthFactor(StructureTypeFixture):
    def test_a_pay_month_crossing_a_calendar_month_is_one_whole_month(self):
        slices = [
            month("2026-09-29", "2026-09-30", 30),
            month("2026-10-01", "2026-10-28", 31),
        ]
        self.assertEqual(period_factor(slices, MONTH_CALENDAR_DAYS), 1.0)

    def test_a_part_of_a_pay_month_is_still_shared_by_calendar_days(self):
        slices = [
            month("2026-09-29", "2026-09-30", 30),
            month("2026-10-01", "2026-10-13", 31),
        ]
        self.assertAlmostEqual(
            period_factor(slices, MONTH_CALENDAR_DAYS), 2 / 30 + 13 / 31
        )

    def test_a_calendar_month_is_unchanged(self):
        self.assertEqual(
            period_factor([month("2026-04-01", "2026-04-30", 30)], MONTH_CALENDAR_DAYS),
            1.0,
        )


class OutsideHelpers:
    """Shared helpers, deliberately not a TestCase so subclasses do not inherit (and re-run) each other's tests."""

    def pay(self, with_bonus):
        structure = self.ctc_structure("C1", 50.0, 400.0)
        kw = dict(
            employee_id=self.employee,
            wage_type="monthly",
            wage=60000.0,
            contract_status="active",
            deduct_leave_from_basic_pay=True,
            calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
            salary_structure_id=structure,
        )
        Contract.objects.create(contract_name="Main", contract_start_date=day(1), **kw)
        if with_bonus:
            bonus = Allowance.objects.create(
                title="Xmas", is_fixed=True, amount=5000.0, is_taxable=True
            )
            bonus.specific_employees.add(self.employee)
        (payslip,) = self.run_month()
        return payslip

    def rows(self, payslip):
        return {row["title"]: row for row in payslip.pay_head_data["allowances"]}

    def add_generated_earning(self, title, **kw):
        """An earning the way a loan, advance, reimbursement or encashment raises it: one date, one employee."""
        earning = Allowance.objects.create(
            title=title,
            is_fixed=True,
            include_active_employees=False,
            one_time_date=day(10),
            maximum_unit="full_period",
            **kw,
        )
        earning.specific_employees.add(self.employee)

    def add_generated_deduction(self, title, **kw):
        """A loan instalment, fine or attendance penalty: one date, one employee."""
        deduction = Deduction.objects.create(
            title=title,
            is_fixed=True,
            include_active_employees=False,
            one_time_date=day(10),
            maximum_unit="full_period",
            **kw,
        )
        deduction.specific_employees.add(self.employee)


class OutsideTheStructure(OutsideHelpers, StructureTypeFixture):
    def test_the_balance_is_the_same_with_or_without_the_bonus(self):
        plain = self.pay(with_bonus=False)
        Payslip.objects.all().delete()
        Contract.objects.all().delete()
        with_bonus = self.pay(with_bonus=True)
        self.assertAlmostEqual(
            self.rows(with_bonus)["C1 Special"]["amount"],
            self.rows(plain)["C1 Special"]["amount"],
            places=2,
        )

    def test_the_bonus_is_paid_in_full_on_top_of_the_package(self):
        payslip = self.pay(with_bonus=True)
        self.assertAlmostEqual(self.rows(payslip)["Xmas"]["amount"], 5000.0, places=2)
        self.assertTrue(self.rows(payslip)["Xmas"]["outside_ctc"])
        self.assertAlmostEqual(payslip.gross_pay, 60000.0 + 5000.0, places=2)

    def test_structure_components_are_not_marked_outside(self):
        payslip = self.pay(with_bonus=True)
        self.assertFalse(self.rows(payslip)["C1 HRA"].get("outside_ctc"))

    def test_loan_advance_reimbursement_and_encashment_payouts_are_all_on_top(self):
        baseline = self.rows(self.pay(with_bonus=False))["C1 Special"]["amount"]
        Payslip.objects.all().delete()
        Contract.objects.all().delete()
        for title, amount in (
            ("Loan", 20000.0),
            ("Salary Advance", 3000.0),
            ("Reimbursement", 1200.0),
            ("Leave Encashment", 4000.0),
            ("Bonus Point Encashment", 500.0),
        ):
            self.add_generated_earning(title, amount=amount, is_taxable=True)
        payslip = self.pay(with_bonus=False)
        rows = self.rows(payslip)
        self.assertAlmostEqual(rows["C1 Special"]["amount"], baseline, places=2)
        for title, amount in (
            ("Loan", 20000.0),
            ("Salary Advance", 3000.0),
            ("Reimbursement", 1200.0),
            ("Leave Encashment", 4000.0),
            ("Bonus Point Encashment", 500.0),
        ):
            self.assertAlmostEqual(rows[title]["amount"], amount, places=2)
            self.assertTrue(rows[title]["outside_ctc"], title)
        self.assertAlmostEqual(payslip.gross_pay, 60000.0 + 28700.0, places=2)

    def test_loan_instalments_fines_and_penalties_come_off_without_touching_the_package(
        self,
    ):
        baseline = self.pay(with_bonus=False)
        base_special = self.rows(baseline)["C1 Special"]["amount"]
        Payslip.objects.all().delete()
        Contract.objects.all().delete()
        self.add_generated_deduction("Loan - 10 Apr", amount=1000.0, is_pretax=True)
        self.add_generated_deduction("Fine - 10 Apr", amount=250.0, is_pretax=True)
        self.add_generated_deduction(
            "Late Penalty - 10 Apr", amount=100.0, is_pretax=True
        )
        payslip = self.pay(with_bonus=False)
        self.assertAlmostEqual(
            self.rows(payslip)["C1 Special"]["amount"], base_special, places=2
        )
        self.assertAlmostEqual(payslip.gross_pay, baseline.gross_pay, places=2)
        self.assertAlmostEqual(payslip.net_pay, baseline.net_pay - 1350.0, places=2)

    def test_a_structure_that_lists_no_components_keeps_every_earning_in_the_package(
        self,
    ):
        structure = SalaryStructure.objects.create(
            title="Bare", structure_mode="ctc_down"
        )
        Contract.objects.create(
            contract_name="Bare",
            contract_start_date=day(1),
            employee_id=self.employee,
            wage_type="monthly",
            wage=60000.0,
            contract_status="active",
            salary_structure_id=structure,
            deduct_leave_from_basic_pay=True,
            calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
        )
        for title, code, seq, kw in (
            (
                "Basic",
                "BASIC",
                10,
                dict(
                    is_basic_pay=True,
                    based_on="component",
                    percentage_of_code="CTC",
                    rate=50.0,
                ),
            ),
            ("Rest", "REST", 900, dict(based_on="balance")),
        ):
            part = Allowance.objects.create(
                title=title,
                code=code,
                sequence=seq,
                is_taxable=True,
                is_fixed=False,
                **kw,
            )
            part.specific_employees.add(self.employee)
        (payslip,) = self.run_month()
        self.assertFalse(
            [
                row
                for row in payslip.pay_head_data["allowances"]
                if row.get("outside_ctc")
            ]
        )
        self.assertAlmostEqual(payslip.gross_pay, 60000.0, places=2)

    def test_the_payslip_says_so(self):
        payslip = self.pay(with_bonus=True)
        working = earning_workings(payslip)[
            f"a:{self.rows(payslip)['Xmas']['allowance_id']}"
        ]
        self.assertIn("Outside The Salary Structure", " ".join(working["notes"]))


class CtcBreakDown(OutsideHelpers, StructureTypeFixture):
    """The block under the tax working that shows how a CTC Down payslip adds up to its CTC."""

    def test_the_parts_add_up_to_the_package_with_the_bonus_listed_outside(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        payslip = self.pay(with_bonus=True)
        figures = ctc_breakdown(payslip)
        self.assertAlmostEqual(figures["ctc"], 60000.0, places=2)
        self.assertAlmostEqual(figures["total"], 60000.0, places=2)
        self.assertAlmostEqual(figures["difference"], 0.0, places=2)
        self.assertEqual([row["title"] for row in figures["outside"]], ["Xmas"])
        self.assertAlmostEqual(figures["outside_total"], 5000.0, places=2)
        self.assertNotIn("Xmas", [row["title"] for row in figures["inside"]])

    def test_an_employer_contribution_is_part_of_the_cost_and_a_deduction_is_not(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        payslip = self.pay(with_bonus=False)
        data = payslip.pay_head_data
        data["pretax_deductions"][0]["employer_contribution_amount"] = 1440.0
        figures = ctc_breakdown(payslip)
        self.assertEqual(figures["employer_total"], 1440.0)
        self.assertAlmostEqual(
            figures["total"], figures["inside_total"] + 1440.0, places=2
        )
        self.assertEqual([row["title"] for row in figures["taken"]], ["C1 PF"])

    def test_a_deduction_tooltip_says_it_is_not_added_to_the_ctc(self):
        from payroll.methods.earning_working import deduction_workings

        payslip = self.pay(with_bonus=False)
        notes = " ".join(
            " ".join(w["notes"]) for w in deduction_workings(payslip).values()
        )
        self.assertIn("Not Part Of The CTC", notes)

    def test_a_deduction_tooltip_shows_the_employer_contribution(self):
        from payroll.methods.earning_working import deduction_workings

        payslip = self.pay(with_bonus=False)
        payslip.pay_head_data["pretax_deductions"][0][
            "employer_contribution_amount"
        ] = 1440.0
        notes = " ".join(
            " ".join(w["notes"]) for w in deduction_workings(payslip).values()
        )
        self.assertIn("Employer Contribution: 1,440.00", notes)

    def test_a_gross_up_payslip_has_no_breakdown(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        self.two_contracts(
            self.gross_up_structure("G1", 200.0),
            30000.0,
            self.gross_up_structure("G2", 400.0),
            60000.0,
        )
        first, _second = self.run_month()
        self.assertIsNone(ctc_breakdown(first))

    def test_the_block_draws_only_for_ctc_down(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "payroll/payslip/_ctc_breakdown.html",
            {"payslip": self.pay(with_bonus=True)},
        )
        self.assertIn("CTC Break Down", html)
        self.assertIn("Outside The CTC", html)
