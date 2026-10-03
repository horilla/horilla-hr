"""
Repairing payslips that store their basic pay twice.

The engine no longer writes the basic pay component as an allowance row (see
payroll_run), but payslips written before that still carry it. These tests
build both shapes and check the repair only touches the one that is wrong --
a command that "fixes" a correct Gross Up payslip would take a real allowance
off it.
"""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.management.commands.normalise_payslip_basic_pay import duplicate_row_index
from payroll.models.models import Allowance, Contract, Payslip

START = date(2026, 4, 1)
END = date(2026, 4, 30)


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Repair Co")
        self.employee = make_employee(
            company=self.company, email="repair@test.horilla", first_name="Repair"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        self.basic_component = Allowance.objects.create(
            title="Basic Pay",
            code="BASIC",
            is_basic_pay=True,
            is_fixed=True,
            amount=11000.0,
        )
        self.hra = Allowance.objects.create(
            title="HRA", code="HRA", is_fixed=True, amount=4400.0
        )

    def make_payslip(self, allowance_rows, basic_pay, gross_pay):
        return Payslip.objects.create(
            employee_id=self.employee,
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=basic_pay,
            gross_pay=gross_pay,
            deduction=0.0,
            net_pay=gross_pay,
            pay_head_data={"allowances": allowance_rows},
        )

    def old_shape(self):
        """Basic pay stored twice: as the figure, and as its own row."""
        return self.make_payslip(
            [
                {
                    "allowance_id": self.basic_component.pk,
                    "title": "Basic Pay",
                    "amount": 11000.0,
                },
                {"allowance_id": self.hra.pk, "title": "HRA", "amount": 4400.0},
            ],
            basic_pay=11000.0,
            gross_pay=15400.0,
        )

    def gross_up_shape(self):
        """Basic pay is the contract wage, and is not among the rows."""
        return self.make_payslip(
            [{"allowance_id": self.hra.pk, "title": "HRA", "amount": 4400.0}],
            basic_pay=11000.0,
            gross_pay=15400.0,
        )


class WhatCountsAsADuplicateTests(Fixture):
    def test_the_old_shape_is_found(self):
        payslip = self.old_shape()
        self.assertEqual(duplicate_row_index(payslip, {self.basic_component.pk}), 0)

    def test_a_gross_up_payslip_is_left_alone(self):
        """
        Gross is basic plus the rows here, so no row can be the basic pay --
        and removing the one allowance it does have would be a real loss.
        """
        payslip = self.gross_up_shape()
        self.assertIsNone(duplicate_row_index(payslip, {self.basic_component.pk}))

    def test_a_payslip_with_no_rows_is_left_alone(self):
        payslip = self.make_payslip([], basic_pay=11000.0, gross_pay=11000.0)
        self.assertIsNone(duplicate_row_index(payslip, {self.basic_component.pk}))

    def test_a_zero_basic_is_left_alone(self):
        """
        With basic at zero, "gross equals the rows" is true of every payslip,
        so the sum proves nothing and any row at zero would match on amount.
        """
        payslip = self.make_payslip(
            [{"allowance_id": self.hra.pk, "title": "HRA", "amount": 4400.0}],
            basic_pay=0.0,
            gross_pay=4400.0,
        )
        self.assertIsNone(duplicate_row_index(payslip, {self.basic_component.pk}))

    def test_an_unflagged_component_is_still_found_by_its_amount(self):
        """
        The flag can be turned off a component after the payslips it made, so
        the amount has to be able to identify the row on its own.
        """
        payslip = self.old_shape()
        self.assertEqual(duplicate_row_index(payslip, set()), 0)

    def test_but_not_when_two_rows_share_that_amount(self):
        """There is then no way to say which was the basic one."""
        payslip = self.make_payslip(
            [
                {"allowance_id": self.hra.pk, "title": "HRA", "amount": 11000.0},
                {"allowance_id": None, "title": "Other", "amount": 11000.0},
            ],
            basic_pay=11000.0,
            gross_pay=22000.0,
        )
        self.assertIsNone(duplicate_row_index(payslip, set()))


class TheCommandTests(Fixture):
    def run_command(self, *args):
        out = StringIO()
        call_command("normalise_payslip_basic_pay", *args, stdout=out)
        return out.getvalue()

    def test_it_reports_without_changing_anything(self):
        payslip = self.old_shape()
        output = self.run_command()

        self.assertIn("1 payslip(s) list basic pay twice", output)
        payslip.refresh_from_db()
        self.assertEqual(len(payslip.pay_head_data["allowances"]), 2)

    def test_fix_removes_the_duplicate_row(self):
        payslip = self.old_shape()
        self.run_command("--fix")

        payslip.refresh_from_db()
        titles = [row["title"] for row in payslip.pay_head_data["allowances"]]
        self.assertEqual(titles, ["HRA"])

    def test_fix_moves_no_figure(self):
        """
        The money was never wrong -- gross was worked out from the rows with
        basic held out of the sum on purpose. Only what was stored beside the
        figures was wrong.
        """
        payslip = self.old_shape()
        self.run_command("--fix")

        payslip.refresh_from_db()
        self.assertEqual(payslip.basic_pay, 11000.0)
        self.assertEqual(payslip.gross_pay, 15400.0)
        self.assertEqual(payslip.net_pay, 15400.0)

    def test_afterwards_basic_plus_the_rows_is_gross(self):
        """
        The shape the repair exists to produce, and the one a Gross Up payslip
        always had: allowances are the earnings on top of basic pay.
        """
        payslip = self.old_shape()
        self.run_command("--fix")

        payslip.refresh_from_db()
        rows = sum(row["amount"] for row in payslip.pay_head_data["allowances"])
        self.assertAlmostEqual(payslip.basic_pay + rows, payslip.gross_pay, places=2)

    def test_fix_records_which_component_worked_basic_out(self):
        """
        The row is what said so. Once it is gone, nothing else on the payslip
        could tell the editor that basic pay was 50% of CTC rather than a
        figure somebody typed.
        """
        payslip = self.old_shape()
        self.run_command("--fix")

        payslip.refresh_from_db()
        self.assertEqual(
            payslip.pay_head_data["basic_pay_component_id"], self.basic_component.pk
        )

    def test_it_says_so_when_there_is_nothing_to_do(self):
        self.gross_up_shape()
        self.assertIn("No payslip lists its basic pay twice", self.run_command())

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.old_shape()
        self.run_command("--fix")
        self.assertIn("No payslip lists its basic pay twice", self.run_command("--fix"))
