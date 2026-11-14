"""
The component catalog must pick exactly the components the original queries pick.

It is an accelerator for batch runs, so every membership rule is exercised both ways -- the original
querysets outside ``use_catalog()`` and the catalog inside it -- and the answers must be identical,
down to the order and to every figure of a payslip calculation.
"""

import datetime
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import TestCase

from base.models import Department, JobPosition, JobRole
from horilla.testkit import make_company, make_employee
from payroll.methods.batch_run import use_contract
from payroll.methods.component_catalog import use_catalog
from payroll.methods.component_engine import eligible_allowances
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure
from payroll.tests.factories_payroll import make_active_contract
from payroll.tests.test_batch_run import EMPTY_LEAVES, months

START = date(2026, 4, 1)
END = date(2026, 4, 30)


def norm(value):
    if isinstance(value, QuerySet):
        return sorted(item.pk for item in value)
    if isinstance(value, dict):
        return {
            str(k): norm(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [norm(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "pk") and hasattr(value, "_meta"):
        return "%s:%s" % (value._meta.label, value.pk)
    if isinstance(value, float):
        return round(value, 6)
    return value if isinstance(value, (str, int, bool, type(None))) else repr(value)


class CatalogMatchesQueriesTests(TestCase):
    def setUp(self):
        self.company = make_company("Catalog Co")
        self.dept = Department.objects.create(department="Ops")
        self.other_dept = Department.objects.create(department="Sales")
        self.position = JobPosition.objects.create(
            job_position="Clerk", department_id=self.dept
        )
        self.role = JobRole.objects.create(
            job_role="Lead", job_position_id=self.position
        )

        def person(name, **work):
            employee = make_employee(
                company=self.company, email=f"{name}@cat.horilla", first_name=name
            )
            if work:
                from employee.models import EmployeeWorkInformation

                EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                    **work
                )
            Contract.objects.filter(employee_id=employee).delete()
            return employee

        self.ann = person(
            "Ann",
            department_id=self.dept,
            job_position_id=self.position,
            job_role_id=self.role,
        )
        self.ben = person("Ben", department_id=self.other_dept)
        self.cara = person("Cara")
        self.people = [self.ann, self.ben, self.cara]

        self.structure = SalaryStructure.objects.create(title="Std")
        self.other_structure = SalaryStructure.objects.create(title="Old")
        for employee in self.people:
            make_active_contract(
                employee, wage=30000.0, salary_structure_id=self.structure
            )

        # Allowances: every way of reaching (or missing) an employee.
        def allowance(title, **fields):
            defaults = dict(
                title=title,
                is_taxable=True,
                is_fixed=True,
                amount=100.0,
                is_condition_based=False,
                has_max_limit=False,
                include_active_employees=False,
            )
            defaults.update(fields)
            return Allowance.objects.create(**defaults)

        self.a_specific = allowance("Specific", sequence=2)
        self.a_specific.specific_employees.add(self.ann)
        self.a_active = allowance("Everyone", include_active_employees=True, sequence=1)
        self.a_active_not_ben = allowance(
            "Not Ben", include_active_employees=True, sequence=1
        )
        self.a_active_not_ben.exclude_employees.add(self.ben)
        self.a_dept = allowance("Ops Dept", apply_by="department", sequence=3)
        self.a_dept.apply_departments.add(self.dept)
        self.a_position = allowance("Clerks", apply_by="job_position", sequence=3)
        self.a_position.apply_job_positions.add(self.position)
        self.a_role = allowance("Leads", apply_by="job_role", sequence=3)
        self.a_role.apply_job_roles.add(self.role)
        self.a_dated_out = allowance(
            "Last Year", include_active_employees=True, one_time_date=date(2025, 1, 1)
        )
        self.a_dated_in = allowance(
            "This Month", include_active_employees=True, one_time_date=date(2026, 4, 10)
        )
        self.a_in_structure = allowance("In Structure")
        self.a_in_structure.salary_structures.add(self.structure)
        self.a_in_structure.exclude_employees.add(self.cara)  # the structure still wins
        self.a_old_structure = allowance("Old Structure")
        self.a_old_structure.salary_structures.add(self.other_structure)
        self.a_old_structure.specific_employees.add(
            self.ann
        )  # mirrored from a structure she left

        # Deductions in each pass, plus one that adjusts gross pay.
        def deduction(title, **fields):
            defaults = dict(
                title=title,
                is_fixed=True,
                amount=50.0,
                is_pretax=False,
                is_tax=False,
                is_condition_based=False,
                has_max_limit=False,
                include_active_employees=False,
            )
            defaults.update(fields)
            return Deduction.objects.create(**defaults)

        self.d_pre = deduction(
            "Pre", is_pretax=True, include_active_employees=True, sequence=2
        )
        self.d_post = deduction("Post", include_active_employees=True, sequence=1)
        self.d_tax = deduction("Tax", is_tax=True, include_active_employees=True)
        self.d_specific = deduction("Mine", is_pretax=True)
        self.d_specific.specific_employees.add(self.ben)
        self.d_dept = deduction("Dept", apply_by="department")
        self.d_dept.apply_departments.add(self.dept)
        self.d_excluded = deduction("Not Cara", include_active_employees=True)
        self.d_excluded.exclude_employees.add(self.cara)
        self.d_gross = deduction(
            "Gross Adjust", update_compensation="gross_pay", amount=10.0
        )
        self.d_gross.specific_employees.add(self.ann)
        self.d_old = deduction("Old Structure Ded")
        self.d_old.salary_structures.add(self.other_structure)
        self.d_old.specific_employees.add(self.ann)

    def test_the_allowances_picked_are_the_same_and_in_the_same_order(self):
        for employee in self.people:
            for forced in (False, True):
                contract = Contract.objects.get(employee_id=employee)
                with self.subTest(employee=employee.employee_first_name, forced=forced):
                    outer = use_contract(contract) if forced else _nothing()
                    with outer:
                        legacy = [
                            a.pk for a in eligible_allowances(employee, START, END)
                        ]
                        with use_catalog():
                            fresh = type(employee).objects.get(pk=employee.pk)
                            got = [a.pk for a in eligible_allowances(fresh, START, END)]
                    self.assertEqual(got, legacy)
                    self.assertTrue(legacy)  # the scenario really selects something

    def test_a_whole_payslip_calculation_is_identical(self):
        patches = (
            patch("payroll.methods.methods.months_between_range", side_effect=months),
            patch(
                "payroll.methods.methods.get_daily_salary",
                return_value={"day_wage": 1000.0},
            ),
            patch("payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        summary = {
            "present": 22,
            "paid_leave": 0,
            "unpaid_leave": 0,
            "absent": 0,
            "week_off": 8,
            "holiday": 0,
            "total_working": 22,
            "unresolved_conflicts": 0,
            "overtime_label": "0h 00m",
            "paid_days": 30,
            "unpaid_days": 0,
        }

        def run(employee, catalog):
            contract = Contract.objects.get(employee_id=employee)
            fresh = type(employee).objects.get(pk=employee.pk)
            with use_contract(contract):
                if catalog:
                    with use_catalog():
                        return norm(
                            payroll_calculation(
                                fresh,
                                START,
                                END,
                                month_summary=dict(summary),
                                prorate_slice=False,
                            )
                        )
                return norm(
                    payroll_calculation(
                        fresh,
                        START,
                        END,
                        month_summary=dict(summary),
                        prorate_slice=False,
                    )
                )

        for employee in self.people:
            with self.subTest(employee=employee.employee_first_name):
                self.assertEqual(run(employee, True), run(employee, False))

    def test_nothing_changes_outside_a_catalog(self):
        """Without use_catalog() the original queries answer, so everything else is untouched."""
        from payroll.methods.component_catalog import active

        self.assertIsNone(active())
        with use_catalog():
            self.assertIsNotNone(active())
        self.assertIsNone(active())


class _nothing:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False
