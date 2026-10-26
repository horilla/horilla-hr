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

from django.test import TestCase

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
