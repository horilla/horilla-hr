"""
Overtime slabs on a real payslip: paid by band on the contract's hourly wage, and zero, with the
reason on the payslip, when the contract states no hourly wage.
"""

import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from attendance.models import Attendance
from employee.models import Employee
from horilla.testkit import make_company, make_employee
from payroll.methods.component_summary import calculation_summary
from payroll.methods.earning_working import earning_workings, overtime_kind
from payroll.models.models import Allowance, AllowanceSlab, Contract, Payslip
from payroll.scheduler import generate_payslips

START, END = datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)
WEDNESDAY = datetime.date(2026, 9, 2)


class SlabSummaryTests(SimpleTestCase):
    def _component(self, based_on, slabs):
        manager = SimpleNamespace(all=lambda: slabs)
        return SimpleNamespace(
            is_fixed=False,
            based_on=based_on,
            overtime_calc="slab",
            slabs=manager,
            amount_per_one_hr=0,
        )

    def test_the_bands_are_written_out(self):
        slabs = [
            SimpleNamespace(from_hours=0, to_hours=2, multiplier=1.25),
            SimpleNamespace(from_hours=2, to_hours=None, multiplier=1.5),
        ]
        text = calculation_summary(self._component("overtime", slabs))
        self.assertIn("0\u20132h \u00d71.25", text)
        self.assertIn("2h+ \u00d71.5", text)
        self.assertIn("overtime hour", text)

    def test_no_bands_says_so(self):
        self.assertEqual(
            calculation_summary(self._component("overtime", [])), "Slabs not set"
        )

    def test_a_flat_overtime_allowance_reads_as_before(self):
        component = self._component("overtime", [])
        component.overtime_calc = "flat"
        component.amount_per_one_hr = 60
        self.assertIn("per overtime hour", calculation_summary(component))


class OvertimeKindTests(SimpleTestCase):
    """Each overtime line says which hours it pays for."""

    def test_each_kind_is_explained(self):
        regular = overtime_kind(SimpleNamespace(based_on="overtime"))
        week_off = overtime_kind(SimpleNamespace(based_on="week_off_overtime"))
        holiday = overtime_kind(SimpleNamespace(based_on="holiday_overtime"))
        self.assertIn("Normal Working Day", regular)
        self.assertIn("Week Off", week_off)
        self.assertIn("Every Hour Counts", week_off)
        self.assertIn("Holiday", holiday)
        self.assertIn("Every Hour Counts", holiday)

    def test_other_earnings_have_no_kind(self):
        self.assertEqual(overtime_kind(SimpleNamespace(based_on="basic_pay")), "")
        self.assertEqual(overtime_kind(None), "")


class SlabPayslipTests(TestCase):
    def setUp(self):
        self.employee = make_employee(
            company=make_company("Slab Pay Co"), email="slab@test.horilla"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        allowance = Allowance.objects.create(
            title="Slab Overtime",
            is_fixed=False,
            based_on="overtime",
            overtime_calc="slab",
            is_taxable=True,
            include_active_employees=True,
        )
        AllowanceSlab.objects.create(
            allowance_id=allowance, from_hours=0, to_hours=2, multiplier=1.25
        )
        AllowanceSlab.objects.create(
            allowance_id=allowance, from_hours=2, to_hours=None, multiplier=1.5
        )
        self.allowance = allowance

    def _contract(self, hourly_wage):
        Contract.objects.create(
            contract_name="Main",
            contract_start_date=START,
            employee_id=self.employee,
            wage_type="monthly",
            wage=60000.0,
            hourly_wage=hourly_wage,
            contract_status="active",
            deduct_leave_from_basic_pay=True,
            calculate_daily_leave_amount=True,
            deduction_for_one_leave_amount=0,
        )

    def _approved_overtime(self, hours):
        Attendance.objects.create(
            employee_id=self.employee,
            attendance_date=WEDNESDAY,
            attendance_clock_in_date=WEDNESDAY,
            attendance_clock_in=datetime.time(9, 0),
            attendance_clock_out_date=WEDNESDAY,
            attendance_clock_out=datetime.time(20, 0),
            attendance_worked_hour="11:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )
        Attendance.objects.filter(employee_id=self.employee).update(
            at_work_second=(8 + hours) * 3600,
            overtime_second=hours * 3600,
            attendance_overtime_approve=True,
        )

    def _payslip(self):
        generate_payslips(Employee.objects.filter(pk=self.employee.pk), START, END)
        return Payslip.objects.get(employee_id=self.employee)

    def _row(self, payslip):
        return {r["title"]: r for r in payslip.pay_head_data["allowances"]}[
            "Slab Overtime"
        ]

    def test_three_hours_are_paid_by_band_on_the_hourly_wage(self):
        self._contract(hourly_wage=100.0)
        self._approved_overtime(3)
        row = self._row(self._payslip())
        # 2h at 1.25 and 1h at 1.5 of 100 an hour.
        self.assertAlmostEqual(row["amount"], 400.0, places=2)
        self.assertNotIn("note", row)

    def test_the_payslip_line_keeps_the_overtime_day_by_day(self):
        self._contract(hourly_wage=100.0)
        self._approved_overtime(3)
        payslip = self._payslip()
        row = self._row(payslip)
        self.assertEqual(len(row["days"]), 1)
        day = row["days"][0]
        self.assertEqual(day["date"], WEDNESDAY.isoformat())
        self.assertEqual(day["bands"], [[2.0, 1.25], [1.0, 1.5]])
        self.assertAlmostEqual(day["amount"], 400.0, places=2)

        working = earning_workings(payslip)[f"a:{self.allowance.pk}"]
        (shown,) = working["days"]
        self.assertEqual(shown["date"], WEDNESDAY)
        self.assertEqual(shown["hours"], "3h 00m")
        self.assertEqual(shown["detail"], "2h × 1.25 + 1h × 1.5 × 100.00")
        self.assertAlmostEqual(shown["amount"], 400.0, places=2)

    def test_the_popover_says_which_overtime_it_is(self):
        from django.template.loader import render_to_string

        self._contract(hourly_wage=100.0)
        self._approved_overtime(3)
        working = earning_workings(self._payslip())[f"a:{self.allowance.pk}"]
        self.assertIn("Normal Working Day", working["kind"])
        html = render_to_string("payroll/payslip/_earning_popover.html", {"w": working})
        self.assertIn("Regular Overtime:", html)

    def test_a_flat_rate_overtime_line_lists_each_day_too(self):
        flat = Allowance.objects.create(
            title="Flat Overtime",
            is_fixed=False,
            based_on="overtime",
            overtime_calc="flat",
            amount_per_one_hr=60.0,
            is_taxable=True,
            include_active_employees=True,
        )
        self.allowance.delete()
        self._contract(hourly_wage=None)
        self._approved_overtime(3)
        payslip = self._payslip()
        working = earning_workings(payslip)[f"a:{flat.pk}"]
        (shown,) = working["days"]
        self.assertEqual(shown["hours"], "3h 00m")
        self.assertAlmostEqual(shown["amount"], 180.0, places=2)
        self.assertIn("60.00", shown["detail"])

    def test_the_popover_lists_the_days(self):
        from django.template.loader import render_to_string

        self._contract(hourly_wage=100.0)
        self._approved_overtime(3)
        payslip = self._payslip()
        working = earning_workings(payslip)[f"a:{self.allowance.pk}"]
        html = render_to_string("payroll/payslip/_earning_popover.html", {"w": working})
        self.assertIn("Day by day", html)
        self.assertIn("Wed, 02 Sep", html)
        self.assertIn("3h 00m", html)

    def test_no_hourly_wage_pays_zero_and_says_why(self):
        self._contract(hourly_wage=None)
        self._approved_overtime(3)
        payslip = self._payslip()
        row = self._row(payslip)
        self.assertEqual(row["amount"], 0)
        self.assertIn("no hourly wage", row["note"])
        working = earning_workings(payslip)[f"a:{self.allowance.pk}"]
        self.assertTrue(any("no hourly wage" in note for note in working["notes"]))
