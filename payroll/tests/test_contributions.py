"""
Tracking what has to be remitted.

Payroll has always computed the employer's share of a contribution component and
never shown it, so the figure paid to a provident fund or an insurer lived only
inside a JSON column and a month could only be totalled by opening payslips one
at a time.

These go through the real engine rather than hand-built dicts. The whole point
of reading from the payslips is that the report agrees with what was issued, and
a test that invents its own payload would not notice if it stopped doing so.
"""

import json
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.methods import contributions
from payroll.methods.methods import payslip_fields, save_payslip
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Contract, Deduction, Payslip
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 4, 1)
END = date(2026, 4, 30)

NO_LEAVE = {
    "paid_leave": 0,
    "unpaid_leaves": 0,
    "partial_pay_days": 0,
    "total_leaves": 0,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("contribadmin", is_superuser=True)
        self.company = make_company("Contrib Co")
        make_employee(
            company=self.company, email="contribadmin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.people = []
        for name in ("Ann", "Ben"):
            employee = make_employee(
                company=self.company,
                email=f"{name.lower()}@contrib.horilla",
                first_name=name,
            )
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(employee, wage=30000.0)
            self.people.append(employee)

    def component(self, title="Provident Fund", **overrides):
        defaults = dict(
            title=title,
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            employer_rate=12.0,
            include_active_employees=True,
            is_condition_based=False,
            is_pretax=True,
        )
        defaults.update(overrides)
        return Deduction.objects.create(**defaults)

    def generate(self):
        """Real payslips, through the real engine and the real save path."""
        with patch("payroll.methods.methods.get_leaves", return_value=NO_LEAVE):
            for employee in self.people:
                result = payroll_calculation(employee, START, END)
                save_payslip(**payslip_fields(result, employee, status="draft"))
        return Payslip.objects.all()


class SummariseTests(Fixture):
    def test_a_component_with_an_employer_share_is_reported(self):
        self.component()
        rows, totals = contributions.summarise(self.generate())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Provident Fund")
        self.assertEqual(rows[0]["employees"], 2)

    def test_both_shares_are_totalled(self):
        self.component()
        rows, totals = contributions.summarise(self.generate())
        row = rows[0]

        # 12% of 30,000 basic, each side, two people.
        self.assertAlmostEqual(row["employee_amount"], 30000 * 0.12 * 2, places=2)
        self.assertAlmostEqual(row["employer_amount"], 30000 * 0.12 * 2, places=2)
        self.assertAlmostEqual(
            row["total"], row["employee_amount"] + row["employer_amount"], places=2
        )

    def test_the_headline_is_what_gets_remitted(self):
        """Both shares together -- that is the payment, not either half."""
        self.component()
        rows, totals = contributions.summarise(self.generate())

        self.assertAlmostEqual(
            totals["total"],
            totals["employee_amount"] + totals["employer_amount"],
            places=2,
        )
        self.assertEqual(totals["employees"], 2)

    def test_an_ordinary_deduction_is_not_a_contribution(self):
        """Nobody remits a loan instalment."""
        self.component(
            title="Loan",
            employer_rate=0,
            is_fixed=True,
            amount=500.0,
            based_on=None,
            rate=None,
        )
        rows, _totals = contributions.summarise(self.generate())
        self.assertEqual(rows, [])

    def test_a_formula_employer_share_counts(self):
        self.component(
            title="PF Pension",
            employer_rate=0,
            employer_basis=Deduction.EMPLOYER_BASIS_FORMULA,
            employer_formula="BASIC * 0.0833",
        )
        rows, _totals = contributions.summarise(self.generate())

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["by_formula"])
        self.assertAlmostEqual(rows[0]["employer_amount"], 30000 * 0.0833 * 2, places=2)

    def test_a_quiet_period_still_lists_the_component(self):
        """
        Configured to contribute but nothing came of it. Dropping the row would
        read as the component having been removed.
        """
        self.component(employer_rate=12.0)
        payslips = self.generate()
        # Blank the employer figures, as a month where the basis was zero would.
        for payslip in payslips:
            data = payslip.pay_head_data
            for key in contributions.DEDUCTION_KEYS:
                for row in data.get(key) or []:
                    row.pop("employer_contribution_amount", None)
            payslip.pay_head_data = data
            payslip.save()

        rows, _totals = contributions.summarise(Payslip.objects.all())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["dormant"])
        self.assertEqual(rows[0]["employer_amount"], 0)

    def test_the_biggest_liability_is_listed_first(self):
        self.component(title="Small", rate=1.0, employer_rate=1.0)
        self.component(title="Large", rate=12.0, employer_rate=12.0)
        rows, _totals = contributions.summarise(self.generate())

        self.assertEqual([row["title"] for row in rows], ["Large", "Small"])

    def test_nothing_generated_means_nothing_owed(self):
        self.component()
        rows, totals = contributions.summarise(Payslip.objects.none())

        self.assertEqual(rows, [])
        self.assertEqual(totals["total"], 0)


class BreakdownTests(Fixture):
    def test_it_is_the_working_behind_the_total(self):
        component = self.component()
        payslips = self.generate()

        rows, _totals = contributions.summarise(payslips)
        lines = contributions.breakdown(payslips, component.pk)

        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(
            sum(line["employer_amount"] for line in lines),
            rows[0]["employer_amount"],
            places=2,
        )

    def test_another_component_is_not_included(self):
        wanted = self.component(title="PF")
        self.component(title="ESI", rate=0.75, employer_rate=3.25)
        payslips = self.generate()

        lines = contributions.breakdown(payslips, wanted.pk)
        self.assertEqual(len(lines), 2)


class PageTests(Fixture):
    def test_the_list_shows_the_period_and_the_figures(self):
        self.component()
        self.generate()

        response = self.client.get(
            reverse("payroll-contribution-list"),
            {"from_date": START, "to_date": END},
        )
        self.assertContains(response, "Provident Fund")
        self.assertEqual(response.context["totals"]["employees"], 2)

    def test_a_payslip_outside_the_period_is_not_counted(self):
        """
        A total spanning two pay periods is not a figure anybody can remit.
        """
        self.component()
        self.generate()

        response = self.client.get(
            reverse("payroll-contribution-list"),
            {"from_date": "2026-05-01", "to_date": "2026-05-31"},
        )
        self.assertEqual(response.context["totals"]["total"], 0)

    def test_it_can_be_narrowed_to_a_payslip_status(self):
        self.component()
        self.generate()

        response = self.client.get(
            reverse("payroll-contribution-list"),
            {"from_date": START, "to_date": END, "status": "paid"},
        )
        self.assertEqual(response.context["totals"]["total"], 0)

    def test_the_detail_page_lists_the_employees(self):
        component = self.component()
        self.generate()

        response = self.client.get(
            reverse("payroll-contribution-detail", args=[component.pk]),
            {"from_date": START, "to_date": END},
        )
        self.assertContains(response, "Ann")
        self.assertContains(response, "Ben")
        self.assertEqual(len(response.context["lines"]), 2)

    def test_the_export_is_per_employee_per_component(self):
        """A remittance return is filed per member, not as a total."""
        self.component()
        self.generate()

        response = self.client.get(
            reverse("payroll-contribution-export"),
            {"from_date": START, "to_date": END},
        )
        body = response.content.decode()

        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("Employer share", body)
        self.assertIn("Ann", body)
        self.assertIn("Ben", body)
        self.assertEqual(len(body.strip().splitlines()), 3)  # header + two

    def test_it_needs_permission(self):
        stranger = make_user("nosy")
        make_employee(company=self.company, email="nosy@test.horilla", user=stranger)
        self.client.force_login(stranger)

        response = self.client.get(reverse("payroll-contribution-list"))
        self.assertNotEqual(response.status_code, 200)
