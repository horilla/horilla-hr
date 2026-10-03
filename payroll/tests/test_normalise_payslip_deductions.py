"""
Repairing payslips written before the deduction cap existed.

The cap stops new payslips being stored with more deducted than earned. It does
nothing for the ones already on the table, and that one field is read by the
payslip, the run totals, the dashboard and every export -- so a single stale row
makes all of them disagree.
"""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods import batch_run
from payroll.models.models import Contract, PayrollBatch, Payslip
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 8, 1)
END = date(2026, 8, 31)


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Repair Co")
        self.employee = make_employee(
            company=self.company, email="repair@test.horilla", first_name="Repair"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=32000.0)

    def payslip(self, gross, deduction, net=0.0):
        return Payslip.objects.create(
            employee_id=self.employee,
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=gross,
            contract_wage=gross,
            gross_pay=gross,
            deduction=deduction,
            net_pay=net,
            pay_head_data={},
        )

    def normalise(self, *args):
        out = StringIO()
        call_command("normalise_payslip_deductions", *args, stdout=out)
        return out.getvalue()


class ReportTests(Fixture):
    def test_a_clean_table_says_so(self):
        self.payslip(gross=33440.0, deduction=3000.0, net=30440.0)
        self.assertIn("No payslip deducts more than it pays", self.normalise())

    def test_a_bad_row_is_listed_with_the_overage(self):
        self.payslip(gross=33440.0, deduction=37920.0)
        output = self.normalise()

        self.assertIn("1 payslip(s) deduct more than they pay", output)
        self.assertIn("4,480.00", output)  # 37,920 - 33,440

    def test_reporting_changes_nothing(self):
        payslip = self.payslip(gross=33440.0, deduction=37920.0)
        self.normalise()

        payslip.refresh_from_db()
        self.assertEqual(payslip.deduction, 37920.0)


class FixTests(Fixture):
    def test_the_deduction_is_capped_at_gross(self):
        payslip = self.payslip(gross=33440.0, deduction=37920.0)
        self.normalise("--fix")

        payslip.refresh_from_db()
        self.assertEqual(payslip.deduction, 33440.0)
        self.assertEqual(payslip.net_pay, 0.0)

    def test_a_correct_payslip_is_left_alone(self):
        good = self.payslip(gross=33440.0, deduction=3000.0, net=30440.0)
        self.normalise("--fix")

        good.refresh_from_db()
        self.assertEqual(good.deduction, 3000.0)
        self.assertEqual(good.net_pay, 30440.0)

    def test_the_run_totals_are_recomputed(self):
        """
        A run carries its own denormalised totals, so correcting the payslips
        does not by itself correct the run list -- which is where the figure
        was seen.
        """
        batch = batch_run.create_batch(
            name="Aug", start_date=START, end_date=END, employees=[self.employee]
        )
        payslip = self.payslip(gross=33440.0, deduction=37920.0)
        payslip.payroll_batch = batch
        payslip.save()
        batch.refresh_totals()

        self.assertGreater(batch.total_deductions, batch.total_gross)

        self.normalise("--fix")
        batch.refresh_from_db()

        self.assertLessEqual(batch.total_deductions, batch.total_gross)
        self.assertEqual(batch.total_deductions, 33440.0)


class StorageBackstopTests(Fixture):
    def test_save_payslip_will_not_store_more_than_gross(self):
        """
        The engine caps it, but save_payslip is the one door every generation
        path goes through -- the wizard, the scheduler, the single payslip
        form -- so the guarantee belongs there too.
        """
        from payroll.methods.methods import save_payslip

        instance = save_payslip(
            employee=self.employee,
            start_date=START,
            end_date=END,
            status="draft",
            basic_pay=32000.0,
            contract_wage=32000.0,
            gross_pay=33440.0,
            deduction=37920.0,
            net_pay=-4480.0,
            pay_data={},
            installments=[],
        )

        self.assertEqual(instance.deduction, 33440.0)
        self.assertEqual(instance.net_pay, 0.0)
