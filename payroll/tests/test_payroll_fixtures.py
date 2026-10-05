"""
The demo dataset holding together.

A fixture command is only worth having if what it produces agrees with itself:
a payslip whose components exist, a run whose review flags the things it was
built to flag, a contributions page with employer shares on it. Data that looks
populated but contradicts itself is worse than none, because every screen built
on it then looks broken for reasons nobody can trace.

Small numbers here -- the point is the shape, not the scale.
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods import contributions
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    FilingStatus,
    PayrollBatch,
    Payslip,
    SalaryStructure,
)

START = datetime.date(2026, 8, 1)
END = datetime.date(2026, 8, 31)


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Fixture Co")
        for index in range(12):
            make_employee(
                company=self.company,
                email=f"person{index}@fixture.test",
                first_name=f"Person{index}",
            )

    def build(self, **options):
        out = StringIO()
        call_command(
            "create_payroll_fixtures",
            employees=12,
            stdout=out,
            **{"from": START.isoformat(), "to": END.isoformat(), **options},
        )
        return out.getvalue()


class ItBuildsEverySectionTests(Fixture):
    def test_the_components_exist(self):
        self.build()

        self.assertTrue(Allowance.objects.filter(code="HRA").exists())
        self.assertTrue(Deduction.objects.filter(code="PF").exists())

    def test_a_structure_holds_them(self):
        """Now two: a Gross Up and a CTC Down structure, not one."""
        self.build()
        self.assertEqual(SalaryStructure.objects.count(), 2)

        for structure in SalaryStructure.objects.all():
            self.assertGreaterEqual(structure.allowances.count(), 3)
            self.assertGreaterEqual(structure.deductions.count(), 4)

    def test_the_tax_packs_are_reloaded(self):
        """The wipe takes them, so the rebuild has to put them back."""
        self.build()
        self.assertTrue(FilingStatus.objects.exists())

    def test_every_employee_gets_an_active_contract(self):
        self.build()
        self.assertEqual(Contract.objects.filter(contract_status="active").count(), 12)

    def test_contracts_differ_from_one_another(self):
        """
        The engine branches on the wage, the filing status and the loss-of-pay
        basis, so a demo where every contract is identical exercises one path
        and hides the rest.
        """
        self.build()
        contracts = Contract.objects.all()

        self.assertGreater(len({c.wage for c in contracts}), 1)
        self.assertGreater(len({c.daily_leave_amount_base for c in contracts}), 1)

    def test_a_run_is_generated(self):
        self.build()
        batch = PayrollBatch.objects.get()

        self.assertGreater(batch.generated_count, 0)
        self.assertEqual(batch.failed_count, 0)

    def test_the_payslips_carry_their_components(self):
        self.build()
        payslip = Payslip.objects.first()
        titles = [a["title"] for a in payslip.pay_head_data["allowances"]]

        self.assertIn("House Rent Allowance", titles)

    def test_the_contributions_page_has_something_to_show(self):
        """
        Employer shares are the whole point of that screen, and they only exist
        if the components were configured with one.
        """
        self.build()
        rows, totals = contributions.summarise(Payslip.objects.all())

        self.assertTrue(rows)
        self.assertGreater(totals["employer_amount"], 0)

    def test_an_employer_formula_is_among_them(self):
        """A rate cannot express a capped split; the demo should prove it can."""
        self.build()
        rows, _totals = contributions.summarise(Payslip.objects.all())

        self.assertTrue(any(row["by_formula"] for row in rows))


class CtcDownTests(Fixture):
    """
    The CTC Down structure, and that its components stay on their own side.

    Structure assignment (Contract.salary_structure_id) does not by itself
    gate which components apply -- eligible_allowances() reads each
    component's own include_active_employees/specific_employees, never the
    contract's structure. A component meant for one structure and left
    include_active_employees=True reaches every contract regardless of which
    structure it is on.
    """

    def contracts_by_mode(self):
        contracts = Contract.objects.select_related("salary_structure_id")
        ctc_down = [
            c for c in contracts if c.salary_structure_id.structure_mode == "ctc_down"
        ]
        gross_up = [
            c for c in contracts if c.salary_structure_id.structure_mode == "gross_up"
        ]
        return gross_up, ctc_down

    def a_ctc_down_payslip_without_loss_of_pay(self):
        """
        The CTC Down payslip that lost the least pay. Loss of pay comes off the
        basic earning on a stated Monthly CTC, so for someone with most of the
        month unpaid basic is rightly nothing -- not what these checks are
        about, and the demo attendance gives most of them a lot of unpaid days.
        """
        _gross_up, ctc_down = self.contracts_by_mode()
        payslips = [
            Payslip.objects.get(employee_id=contract.employee_id)
            for contract in ctc_down
        ]
        return min(payslips, key=lambda p: p.pay_head_data.get("loss_of_pay") or 0)

    def test_both_structures_have_contracts_on_them(self):
        self.build()
        gross_up, ctc_down = self.contracts_by_mode()

        self.assertTrue(gross_up)
        self.assertTrue(ctc_down)

    def test_a_ctc_down_contract_states_the_package_not_a_wage(self):
        self.build()
        _gross_up, ctc_down = self.contracts_by_mode()

        for contract in ctc_down:
            self.assertFalse(contract.wage)
            self.assertTrue(contract.monthly_ctc)

    def test_the_ctc_down_payslip_has_a_real_basic_pay(self):
        """
        Basic pay comes from the flagged earning, not the (zero) wage -- and
        it has to be a real, nonzero figure or a filing status based on basic
        pay would tax nothing.
        """
        self.build()
        payslip = self.a_ctc_down_payslip_without_loss_of_pay()

        self.assertGreater(payslip.basic_pay, 0)

    def test_hra_is_a_real_percentage_of_basic_not_zero(self):
        """
        based_on="basic_pay" reads kwargs["basic_pay"] directly, which is
        correct under Gross Up (known before any earning runs) and is 0
        throughout a CTC Down pass -- basic there is not known until the
        flagged component computes it. The CTC Down twin of HRA has to use
        based_on="component"/percentage_of_code="BASIC" instead, or it prices
        at 0 while looking perfectly configured.
        """
        self.build()
        payslip = self.a_ctc_down_payslip_without_loss_of_pay()

        hra = next(
            a
            for a in payslip.pay_head_data["allowances"]
            if a["title"] == "House Rent Allowance"
        )
        self.assertGreater(hra["amount"], 0)

    def test_a_gross_up_payslip_does_not_carry_the_ctc_only_components(self):
        """
        The failure mode this guards: a Basic Pay / balance component left
        include_active_employees=True would reach every Gross Up contract too,
        double-counting basic and pricing "balance of a CTC of zero".
        """
        self.build()
        gross_up, _ctc_down = self.contracts_by_mode()
        payslip = Payslip.objects.get(employee_id=gross_up[0].employee_id)

        titles = [a["title"] for a in payslip.pay_head_data["allowances"]]
        self.assertNotIn("Flexible Benefits (Balance)", titles)
        self.assertNotIn("Basic Pay", titles)
        # Exactly one: the real Gross Up HRA. A duplicate, zero-valued one from
        # the CTC Down component reaching this contract too would still pass
        # a bare assertIn.
        self.assertEqual(titles.count("House Rent Allowance"), 1)

    def test_every_contract_gets_exactly_one_salary_structure(self):
        """Sanity: nobody ends up on both, or on neither."""
        self.build()
        gross_up, ctc_down = self.contracts_by_mode()
        self.assertEqual(len(gross_up) + len(ctc_down), Contract.objects.count())


class ItProducesAWorkingDemoTests(Fixture):
    def test_most_people_are_payable(self):
        """
        Leave is planned before attendance so the two do not contradict each
        other. Generating both blindly put an unresolved conflict on everyone
        who took a day off, which blocked 18 of 45 and made a working demo
        look broken.
        """
        self.build()
        batch = PayrollBatch.objects.get()

        self.assertGreater(batch.generated_count, batch.employee_count * 0.6)

    def test_but_some_are_blocked_on_purpose(self):
        """
        A demo where nothing is wrong cannot show the review step working, or
        the regularisation flow, or the blocked count.
        """
        from employee.models import Employee
        from payroll.methods import batch_run

        self.build(no_run=True)
        review = batch_run.review(list(Employee.objects.all()), START, END)

        self.assertGreater(review["blocked_count"], 0)
        self.assertGreater(review["ready_count"], review["blocked_count"])

    def test_nobody_ends_up_owing_money(self):
        """
        Net pay at or below zero is a real case and worth one, but a demo where
        it is common is one where the figures were not thought about.
        """
        self.build()
        batch = PayrollBatch.objects.get()

        self.assertLess(batch.flagged_count, batch.generated_count / 2)

    def test_the_deductions_never_exceed_the_gross(self):
        self.build()
        for payslip in Payslip.objects.all():
            self.assertLessEqual(payslip.deduction, payslip.gross_pay)


class ItClearsFirstTests(Fixture):
    def test_running_it_twice_does_not_double_anything(self):
        """
        It wipes before it builds, so a second run replaces the demo rather
        than stacking a second one on top of it.
        """
        self.build()
        first = (Contract.objects.count(), PayrollBatch.objects.count())

        self.build()
        self.assertEqual(
            (Contract.objects.count(), PayrollBatch.objects.count()), first
        )

    def test_keep_leaves_what_is_there(self):
        self.build()
        marker = Allowance.objects.create(title="Hand made", is_fixed=True, amount=1)

        self.build(keep=True, no_run=True)
        self.assertTrue(Allowance.objects.filter(pk=marker.pk).exists())
