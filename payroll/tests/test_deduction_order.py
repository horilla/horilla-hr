"""
Deductions run in (sequence, pk) order, as allowances do.

The tax, pre-tax and post-tax gatherers built their candidates as a
``.distinct()`` union with no order_by, so the evaluation order was whatever
the database returned, and it changed between runs. That moved lines around
on the payslip and, for a deduction worked out from another one, changed the
amount: it read 0 when it happened to run first.

Each test creates its deductions in the opposite order to their sequence, so
an unordered query matches the expected order only by chance.
"""

from datetime import date

from django.test import TestCase

from payroll.methods.deductions import update_compensation_deduction
from payroll.tests import test_payroll_calculation_golden as golden
from payroll.tests.factories_payroll import make_active_contract, make_deduction

SEQUENCES = (60, 50, 40, 30, 20, 10)  # creation order: highest first


class DeductionOrderTests(TestCase):
    maxDiff = None

    setUp = golden.PayrollCalculationGoldenTests.setUp
    _run = golden.PayrollCalculationGoldenTests._run

    def _titles(self, key, **flags):
        make_active_contract(self.employee)
        for sequence in SEQUENCES:
            make_deduction(
                self.employee,
                f"Seq {sequence}",
                amount=100.0,
                sequence=sequence,
                **flags,
            )
        return [line["title"] for line in self._run()[key]]

    def test_post_tax_deductions_run_in_sequence_order(self):
        self.assertEqual(
            self._titles("post_tax_deductions"),
            [f"Seq {s}" for s in sorted(SEQUENCES)],
        )

    def test_pretax_deductions_run_in_sequence_order(self):
        self.assertEqual(
            self._titles("pretax_deductions", is_pretax=True),
            [f"Seq {s}" for s in sorted(SEQUENCES)],
        )

    def test_tax_deductions_run_in_sequence_order(self):
        self.assertEqual(
            self._titles("tax_deductions", is_tax=True),
            [f"Seq {s}" for s in sorted(SEQUENCES)],
        )

    def test_a_deduction_can_use_one_that_runs_before_it(self):
        """
        "Half of UNION" runs after UNION (higher sequence) though it was
        created first, so it sees UNION's 400 rather than nothing.
        """
        make_active_contract(self.employee)
        make_deduction(
            self.employee,
            "Half of union fee",
            is_fixed=False,
            based_on="component",
            percentage_of_code="UNION",
            rate=50.0,
            sequence=20,
        )
        make_deduction(
            self.employee, "Union fee", code="UNION", amount=400.0, sequence=10
        )
        lines = {
            line["title"]: line["amount"] for line in self._run()["post_tax_deductions"]
        }
        self.assertEqual(lines, {"Union fee": 400.0, "Half of union fee": 200.0})


class SameSequenceTests(TestCase):
    """Deductions on the same sequence keep their creation order (pk)."""

    setUp = golden.PayrollCalculationGoldenTests.setUp
    _run = golden.PayrollCalculationGoldenTests._run

    def test_creation_order_breaks_a_tie(self):
        make_active_contract(self.employee)
        titles = [f"Same {n}" for n in range(5)]
        for title in titles:
            make_deduction(self.employee, title, amount=100.0, sequence=100)
        lines = [line["title"] for line in self._run()["post_tax_deductions"]]
        self.assertEqual(lines, titles)


class CompensationDeductionOrderTests(TestCase):
    """
    update_compensation_deduction takes each rate from the running total, so
    the order changes the result. A fixed 500 at sequence 10 runs before a
    10% at sequence 20, whatever order they were created in.
    """

    setUp = golden.PayrollCalculationGoldenTests.setUp

    def test_deductions_reduce_gross_pay_in_sequence_order(self):
        make_deduction(
            self.employee,
            "Ten percent",
            is_fixed=False,
            amount=0,
            rate=10,
            sequence=20,
            update_compensation="gross_pay",
        )
        make_deduction(
            self.employee,
            "Fixed 500",
            amount=500.0,
            sequence=10,
            update_compensation="gross_pay",
        )
        result = update_compensation_deduction(
            self.employee, 27000.0, "gross_pay", date(2026, 8, 1), date(2026, 8, 31)
        )
        # 27,000 - 500 = 26,500; 10% of that is 2,650 -> 23,850
        # (creation order gave 27,000 - 2,700 - 500 = 23,800).
        self.assertEqual(result["compensation_amount"], 23850.0)
        self.assertEqual(
            [line["title"] for line in result["deductions"]],
            ["Fixed 500", "Ten percent"],
        )
