"""
A period split across two contracts whose salary structures are the same type or different types.

April 2024 has 30 days: the first contract covers the 1st to the 15th, the second the 16th to the
30th, each half a month. A CTC Down structure divides the contract wage (half of it here) into
components that add up to exactly that; a Gross Up structure takes half the wage as basic and adds
its allowances on top. Each contract is paid on its own structure only.

The contracts are made the way they are in practice: the first is active when created, which
mirrors its structure's components onto the employee, and is then expired by the job that expires
contracts. The second is created active on another structure. Nothing clears the first
structure's mirror, which is what these tests guard against.
"""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from employee.models import Employee
from horilla.testkit import make_company, make_employee
from payroll.methods import batch_run
from payroll.models.models import Allowance, Contract, Deduction, Payslip, SalaryStructure
from payroll.scheduler import generate_payslips


def day(n):
    return date(2024, 4, n)


class StructureTypeFixture(TestCase):
    def setUp(self):
        self.employee = make_employee(company=make_company("Structure Co"), email="structure@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()

    def component(self, structure, title, code, sequence, **kw):
        allowance = Allowance.objects.create(title=title, code=code, sequence=sequence, is_taxable=True, **kw)
        structure.allowances.add(allowance)
        return allowance

    def deduction(self, structure, title, amount):
        deduction = Deduction.objects.create(title=title, is_fixed=True, amount=amount, is_pretax=True)
        structure.deductions.add(deduction)
        return deduction

    def ctc_structure(self, name, basic_rate, pretax):
        """Basic is ``basic_rate`` % of CTC, HRA 40% of basic, a balance absorbs the rest."""
        structure = SalaryStructure.objects.create(title=name, structure_mode="ctc_down")
        self.component(structure, f"{name} Basic", "BASIC", 10, is_fixed=False, is_basic_pay=True,
                       based_on="component", percentage_of_code="CTC", rate=basic_rate)
        self.component(structure, f"{name} HRA", "HRA", 20, is_fixed=False, based_on="component",
                       percentage_of_code="BASIC", rate=40.0)
        self.component(structure, f"{name} Special", "SPECIAL", 900, is_fixed=False, based_on="balance")
        self.deduction(structure, f"{name} PF", pretax)
        return structure

    def gross_up_structure(self, name, pretax):
        """The wage is basic; HRA is 40% of basic and a fixed 600 a month is added."""
        structure = SalaryStructure.objects.create(title=name, structure_mode="gross_up")
        self.component(structure, f"{name} HRA", "GHRA", 20, is_fixed=False, based_on="basic_pay", rate=40.0)
        self.component(structure, f"{name} Fixed", "GFIX", 30, is_fixed=True, amount=600.0)
        self.deduction(structure, f"{name} PF", pretax)
        return structure

    def two_contracts(self, first, first_wage, second, second_wage):
        """The first contract, then the job that expires it, then the second on its own structure."""
        kw = dict(employee_id=self.employee, wage_type="monthly", deduct_leave_from_basic_pay=True,
                  calculate_daily_leave_amount=True, deduction_for_one_leave_amount=0)
        old = Contract.objects.create(contract_name="First", contract_start_date=day(1), wage=first_wage,
                                      contract_status="active", salary_structure_id=first, **kw)
        Contract.objects.filter(pk=old.pk).update(contract_status="expired", contract_end_date=day(15))
        Contract.objects.create(contract_name="Second", contract_start_date=day(16), wage=second_wage,
                                contract_status="active", salary_structure_id=second, **kw)

    def run_month(self):
        generate_payslips(Employee.objects.filter(pk=self.employee.pk), day(1), day(30))
        return list(Payslip.objects.filter(employee_id=self.employee).order_by("start_date"))

    def titles(self, payslip):
        data = payslip.pay_head_data
        return [row["title"] for row in data["allowances"]] + [
            row["title"] for key in ("pretax_deductions", "post_tax_deductions") for row in data.get(key, [])
        ]

    def check_slice(self, payslip, wage, gross, own_prefix, other_prefix):
        self.assertEqual(payslip.contract_wage, wage)
        self.assertAlmostEqual(payslip.gross_pay, gross, places=2)
        titles = self.titles(payslip)
        self.assertTrue(all(t.startswith(own_prefix) for t in titles), titles)
        self.assertFalse([t for t in titles if t.startswith(other_prefix)], titles)


class SameStructureType(StructureTypeFixture):
    def test_ctc_down_then_ctc_down_divides_each_halfs_own_package(self):
        self.two_contracts(self.ctc_structure("C1", 50.0, 400.0), 60000.0, self.ctc_structure("C2", 40.0, 800.0), 90000.0)
        first, second = self.run_month()
        # CTC is half the wage; the components add up to it exactly.
        self.check_slice(first, 60000.0, 30000.0, "C1", "C2")
        self.check_slice(second, 90000.0, 45000.0, "C2", "C1")
        self.assertAlmostEqual(first.basic_pay, 15000.0, places=2)      # 50% of 30,000
        self.assertAlmostEqual(second.basic_pay, 18000.0, places=2)     # 40% of 45,000
        self.assertAlmostEqual(first.net_pay, 30000.0 - 200.0, places=2)    # PF 400 a month, half a month
        self.assertAlmostEqual(second.net_pay, 45000.0 - 400.0, places=2)   # PF 800 a month, half a month

    def test_gross_up_then_gross_up_adds_each_halfs_own_allowances(self):
        self.two_contracts(self.gross_up_structure("G1", 200.0), 30000.0, self.gross_up_structure("G2", 400.0), 60000.0)
        first, second = self.run_month()
        self.check_slice(first, 30000.0, 15000.0 + 6000.0 + 300.0, "G1", "G2")    # basic + 40% + half of 600
        self.check_slice(second, 60000.0, 30000.0 + 12000.0 + 300.0, "G2", "G1")
        self.assertAlmostEqual(first.net_pay, 21300.0 - 100.0, places=2)
        self.assertAlmostEqual(second.net_pay, 42300.0 - 200.0, places=2)


class CrossStructureType(StructureTypeFixture):
    def test_ctc_down_then_gross_up(self):
        self.two_contracts(self.ctc_structure("C1", 50.0, 400.0), 60000.0, self.gross_up_structure("G1", 200.0), 60000.0)
        first, second = self.run_month()
        self.check_slice(first, 60000.0, 30000.0, "C1", "G1")
        self.assertAlmostEqual(first.basic_pay, 15000.0, places=2)
        self.check_slice(second, 60000.0, 30000.0 + 12000.0 + 300.0, "G1", "C1")
        self.assertAlmostEqual(second.basic_pay, 30000.0, places=2)             # the wage is basic, half of it
        self.assertAlmostEqual(first.net_pay, 30000.0 - 200.0, places=2)
        self.assertAlmostEqual(second.net_pay, 42300.0 - 100.0, places=2)

    def test_gross_up_then_ctc_down(self):
        self.two_contracts(self.gross_up_structure("G1", 200.0), 30000.0, self.ctc_structure("C1", 50.0, 400.0), 90000.0)
        first, second = self.run_month()
        self.check_slice(first, 30000.0, 21300.0, "G1", "C1")
        self.assertAlmostEqual(first.basic_pay, 15000.0, places=2)
        self.check_slice(second, 90000.0, 45000.0, "C1", "G1")
        self.assertAlmostEqual(second.basic_pay, 22500.0, places=2)             # 50% of 45,000
        self.assertAlmostEqual(first.net_pay, 21300.0 - 100.0, places=2)
        self.assertAlmostEqual(second.net_pay, 45000.0 - 200.0, places=2)

    def test_the_old_structures_mirror_is_still_on_the_employee_so_the_filter_is_what_keeps_it_out(self):
        first = self.ctc_structure("C1", 50.0, 400.0)
        self.two_contracts(first, 60000.0, self.gross_up_structure("G1", 200.0), 60000.0)
        self.assertTrue(first.allowances.filter(specific_employees=self.employee).exists())

    def test_a_component_in_both_structures_applies_to_both_halves(self):
        first = self.gross_up_structure("G1", 200.0)
        second = self.gross_up_structure("G2", 400.0)
        shared = first.allowances.get(code="GFIX")
        second.allowances.add(shared)
        self.two_contracts(first, 30000.0, second, 60000.0)
        slices = self.run_month()
        self.assertIn(shared.title, self.titles(slices[0]))
        self.assertIn(shared.title, self.titles(slices[1]))

    def test_a_contract_with_no_structure_keeps_its_directly_targeted_components(self):
        direct = Allowance.objects.create(title="Direct Bonus", is_fixed=True, amount=300.0, is_taxable=True)
        direct.specific_employees.add(self.employee)
        kw = dict(employee_id=self.employee, wage_type="monthly", wage=30000.0, contract_status="active",
                  deduct_leave_from_basic_pay=True, calculate_daily_leave_amount=True, deduction_for_one_leave_amount=0)
        Contract.objects.create(contract_name="Plain", contract_start_date=day(1), **kw)
        (payslip,) = self.run_month()
        self.assertIn("Direct Bonus", self.titles(payslip))
        self.assertAlmostEqual(payslip.gross_pay, 30000.0 + 300.0, places=2)


class StructureTypesInTheBatchRun(StructureTypeFixture):
    def test_ctc_down_then_gross_up_in_a_reviewed_batch(self):
        self.two_contracts(self.ctc_structure("C1", 50.0, 400.0), 60000.0, self.gross_up_structure("G1", 200.0), 60000.0)
        batch = batch_run.create_batch(name="Batch", start_date=day(1), end_date=day(30), employees=[self.employee])

        def summary(_employee, first, last):
            days = (last - first).days + 1
            return {"present": days, "paid_leave": 0, "unpaid_leave": 0, "absent": 0, "week_off": 0, "holiday": 0,
                    "total_working": days, "unresolved_conflicts": 0, "paid_days": days, "unpaid_days": 0}

        with patch.object(batch_run, "_summaries_for", return_value={}), patch.object(
            batch_run, "_slice_summary", side_effect=summary
        ):
            while batch_run.generate_slice(batch):
                pass
        first, second = Payslip.objects.filter(payroll_batch=batch).order_by("start_date")
        self.check_slice(first, 60000.0, 30000.0, "C1", "G1")
        self.check_slice(second, 60000.0, 30000.0 + 12000.0 + 300.0, "G1", "C1")
