"""
An earning paid outside the salary structure (a bonus, a one-time allowance) sits on top of a CTC Down
package: it does not shrink the balance component, and a full pay month pays its fixed amount in full.
"""

from datetime import date

from django.test import SimpleTestCase

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


class CtcBreakDownLossOfPay(SimpleTestCase):
    """A payslip whose context lost the basic cut still reconciles, from its stored loss of pay."""

    @staticmethod
    def _payslip(context, **extra):
        from types import SimpleNamespace

        data = {
            "component_context": {"CTC": 30000.0, **context},
            "allowances": [{"title": "House Rent Allowance", "amount": 17000.0}],
            "pretax_deductions": [
                {
                    "title": "Pension",
                    "amount": 100.0,
                    "employer_contribution_amount": 1393.55,
                }
            ],
            **extra,
        }
        return SimpleNamespace(pay_head_data=data, basic_pay=11219.35)

    def test_the_stored_loss_of_pay_closes_the_gap_when_the_context_has_no_cut(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        figures = ctc_breakdown(
            self._payslip({}, loss_of_pay=387.10, lop_reflected_in_basic=True)
        )
        self.assertAlmostEqual(figures["lop"], 387.10)
        self.assertAlmostEqual(figures["package"], 29612.90)
        self.assertAlmostEqual(figures["difference"], 0.0, places=2)

    def test_the_cut_in_the_context_is_used_when_there_is_one(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        figures = ctc_breakdown(
            self._payslip(
                {"_basic_lop": 100.0}, loss_of_pay=387.10, lop_reflected_in_basic=True
            )
        )
        self.assertAlmostEqual(figures["lop"], 100.0)

    def test_a_loss_of_pay_not_taken_off_basic_is_not_counted_against_the_package(self):
        from payroll.methods.ctc_breakdown import ctc_breakdown

        figures = ctc_breakdown(
            self._payslip({}, loss_of_pay=387.10, lop_reflected_in_basic=False)
        )
        self.assertEqual(figures["lop"], 0)


class CtcDifferenceReason(SimpleTestCase):
    """A gap to the package is explained by what the payslip records, not by a catch-all."""

    @staticmethod
    def _reason(difference, **data):
        from payroll.methods.ctc_breakdown import difference_reason

        return str(difference_reason(data, difference))

    def test_basic_changed_by_hand_is_named(self):
        self.assertIn(
            "Basic Pay Was Changed By Hand", self._reason(500.0, basic_edited=True)
        )

    def test_a_line_added_by_hand_is_named(self):
        reason = self._reason(
            -200.0, allowances=[{"title": "Extra", "amount": 200, "custom_id": "ab12"}]
        )
        self.assertIn("Added To This Payslip By Hand", reason)

    def test_a_structure_without_a_balance_component_leaves_the_rest_unpaid(self):
        reason = self._reason(1200.0, allowances=[{"title": "Basic", "amount": 100}])
        self.assertIn("No Balance Component", reason)
        self.assertIn("1,200.00", reason)

    def test_a_short_balance_says_a_line_was_changed(self):
        from unittest import mock

        rows = [{"title": "Balance", "amount": 50.0, "allowance_id": 7}]
        with mock.patch("payroll.methods.ctc_breakdown._balance_ids", return_value={7}):
            self.assertIn(
                "Balance Component Is Short By 300.00",
                self._reason(300.0, allowances=rows),
            )

    def test_a_zero_balance_over_the_package_says_the_rest_already_exceeds_it(self):
        from unittest import mock

        rows = [{"title": "Balance", "amount": 0.0, "allowance_id": 7}]
        with mock.patch("payroll.methods.ctc_breakdown._balance_ids", return_value={7}):
            reason = self._reason(-80.0, allowances=rows)
        self.assertIn("Nothing Left To Fill", reason)
        self.assertIn("80.00", reason)

    def test_the_breakdown_carries_the_reason(self):
        from types import SimpleNamespace

        from payroll.methods.ctc_breakdown import ctc_breakdown

        data = {
            "component_context": {"CTC": 30000.0},
            "allowances": [{"title": "HRA", "amount": 1000.0}],
        }
        figures = ctc_breakdown(SimpleNamespace(pay_head_data=data, basic_pay=2000.0))
        self.assertIn("No Balance Component", str(figures["difference_reason"]))


class CtcLossOfPayNote(SimpleTestCase):
    """The total sits below the monthly CTC by the loss of pay, and the panel says so."""

    def test_the_note_names_the_loss_of_pay_the_days_and_the_package(self):
        from payroll.methods.ctc_breakdown import lop_note

        note = str(lop_note(30000.0, 387.10, {"UNPAID_DAYS": 1.0}))
        self.assertIn("387.10 Less Than The Monthly CTC Of 30,000.00", note)
        self.assertIn("For 1 Unpaid Day Was Taken Off Basic Pay", note)
        self.assertIn("29,612.90", note)

    def test_several_days_are_plural_and_unknown_days_are_left_out(self):
        from payroll.methods.ctc_breakdown import lop_note

        self.assertIn(
            "For 3 Unpaid Days", str(lop_note(30000.0, 900.0, {"UNPAID_DAYS": 3.0}))
        )
        self.assertNotIn("Unpaid Day", str(lop_note(30000.0, 900.0, {})))

    def test_no_loss_of_pay_no_note(self):
        from payroll.methods.ctc_breakdown import lop_note

        self.assertIsNone(lop_note(30000.0, 0.0, {}))

    def test_the_breakdown_carries_it_for_a_payslip_with_loss_of_pay(self):
        from types import SimpleNamespace

        from payroll.methods.ctc_breakdown import ctc_breakdown

        data = {
            "component_context": {"CTC": 30000.0, "UNPAID_DAYS": 1.0},
            "allowances": [{"title": "HRA", "amount": 28219.35 - 11612.90}],
            "pretax_deductions": [
                {
                    "title": "Pension",
                    "amount": 100.0,
                    "employer_contribution_amount": 1393.55,
                }
            ],
            "lop_reflected_in_basic": True,
            "loss_of_pay": 387.10,
        }
        figures = ctc_breakdown(SimpleNamespace(pay_head_data=data, basic_pay=11612.90))
        self.assertIn("387.10 Less Than The Monthly CTC", str(figures["lop_note"]))
        self.assertAlmostEqual(figures["difference"], 0.0, places=2)
