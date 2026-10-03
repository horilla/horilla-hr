"""
Management command: create_precise_payroll_fixtures
-----------------------------------------------------
Replaces all data with a small, hand-curated, self-verified dataset: 10
employees, one company, active monthly contracts, and complete attendance
for the last two fully-closed calendar months -- built specifically so
paid_days + unpaid_days reconciles exactly against the period's own working
days for every employee, every month, no exceptions.

The broader ~275-contract demo dataset (create_payroll_fixtures.py,
base/demo_data/) covers many more scenarios but inherits attendance data
whose classification doesn't always reconcile cleanly (a genuine gap in some
employees' underlying attendance/leave records, not a payroll formula bug --
see the "Michael Brown" case this command exists to never reproduce). This
command trades that breadth for a dataset where every number is verifiable
by hand.

Nothing here is loaded from load_data/*.json. Loading base_data.json's
shared "Regular Shift" pulled in whatever week-off pattern that shift
happened to have configured -- not necessarily Mon-Fri -- so this command's
own day-by-day attendance (built assuming Mon-Fri) could disagree with the
real week_off/holiday count that shift produced, landing extra days in
"unpaid" that were never meant to be there. Building a company and a
dedicated Mon-Fri shift here instead means the only week-off calendar in
play is the one this command itself defines.

Even so, day-by-day Attendance/LeaveRequest rows are still an indirect way
to state "this employee had 3 unpaid days this month" -- correct only if
every downstream classification (week off, holiday, conflict) agrees with
what was intended. AttendanceSummaryOverride (see attendance/models.py) is
the direct form: it states a month's present/paid_leave/unpaid_leave/absent
counts outright, and build_monthly_summary applies it last, over whatever
was otherwise computed -- which is what get_employee_attendance_summary (and
so payroll_calculation) actually reads. Each period's override here is
computed to balance exactly against that period's real week_off/holiday, so
the payslip's own paid_days + unpaid_days is guaranteed correct by
construction rather than by hoping the day-by-day rows landed right.

Run:
    python manage.py create_precise_payroll_fixtures
"""

import calendar
import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

EMPLOYEES = 10
WAGE = 30000.0
# Per-employee count of leave days each month, alternating paid/unpaid --
# varied on purpose (0 through 4) so the dataset exercises "no leave at all"
# and "several leave days" without any employee being ambiguous.
LEAVE_DAYS_BY_INDEX = [0, 1, 2, 3, 4, 0, 1, 2, 3, 4]

# Real-looking names instead of "Precise EmployeeN" -- this dataset is meant
# to be read on a payslip, not just computed against.
EMPLOYEE_NAMES = [
    ("Olivia", "Bennett"),
    ("Ethan", "Brooks"),
    ("Sophia", "Ramirez"),
    ("Liam", "Foster"),
    ("Ava", "Whitfield"),
    ("Noah", "Griffin"),
    ("Isabella", "Park"),
    ("Mason", "Delgado"),
    ("Mia", "Sullivan"),
    ("Lucas", "Whitaker"),
]

# A minority on CTC Down -- the same "most employees are Gross Up, a few are
# CTC Down" split base/demo_data/modules/payroll_features.py uses, so both
# modes show up as themselves rather than one crowding out the other.
CTC_DOWN_INDEXES = {7, 8, 9}
CTC_DOWN_WAGE_TO_CTC_MULTIPLIER = 2.2

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def _closed_months(today):
    """
    The last two fully-closed calendar months relative to today -- never the
    current one, so there is no "is this month done yet" ambiguity to
    reconcile against. Mirrors base/demo_data/modules/payroll_trend.py's own
    _target_periods, minus the month-end special case: this fixture is meant
    to be reproducible on any day it is run, not dependent on today's date.
    """
    months = []
    year, month = today.year, today.month
    for _ in range(2):
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        last_day = calendar.monthrange(year, month)[1]
        months.append(
            (datetime.date(year, month, 1), datetime.date(year, month, last_day))
        )
    return months


def _weekdays(start, end):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += datetime.timedelta(days=1)


class Command(BaseCommand):
    help = (
        "Replace all data with 10 employees and two months of minute-accurate payroll."
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Flushing the database..."))
        call_command("flush", "--no-input", verbosity=0)

        self.stdout.write("Building company and a dedicated Mon-Fri shift...")
        company, shift = self._scaffolding()
        self.stdout.write(f"  Using company: {company}, shift: {shift.employee_shift}")

        self.stdout.write("Loading tax packs and standard components...")
        call_command("seed_tax_packs", verbosity=0)
        call_command("sync_system_components", verbosity=0)

        gross_up, ctc_down = self._structure(company)
        employees = self._employees(company, shift, gross_up, ctc_down)
        paid_type, unpaid_type = self._leave_types()

        today = datetime.date.today()
        periods = _closed_months(today)

        payslips_created = 0
        for period_start, period_end in periods:
            self.stdout.write(f"\nPeriod {period_start} to {period_end}:")
            for index, employee in enumerate(employees):
                self._attendance_for(
                    employee, period_start, period_end, index, paid_type, unpaid_type
                )
                summary = self._verified_summary(employee, period_start, period_end)
                self._save_payslip(employee, period_start, period_end, summary)
                payslips_created += 1
                self.stdout.write(
                    f"  {employee.get_full_name():20s}  "
                    f"present={summary['present']:>4}  "
                    f"paid_leave={summary['paid_leave']:>3}  "
                    f"unpaid_leave={summary['unpaid_leave']:>3}  "
                    f"absent={summary['absent']:>3}  "
                    f"week_off={summary['week_off']:>4}  "
                    f"paid_days={summary['paid_days']:>5}  "
                    f"unpaid_days={summary['unpaid_days']:>4}  "
                    f"sum={summary['paid_days'] + summary['unpaid_days']:>5} "
                    f"of {(period_end - period_start).days + 1}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {len(employees)} employees, {payslips_created} payslips, "
                f"every one verified paid_days + unpaid_days == calendar days in its period."
            )
        )

    # -- scaffolding -------------------------------------------------------

    def _scaffolding(self):
        """
        A company and a shift this command fully controls, rather than
        loaddata's shared "Regular Shift" -- see the module docstring for
        why that indirection was the actual source of the day-count
        mismatches this command exists to rule out.

        EmployeeShiftSchedule alone is *not* what makes Saturday/Sunday a
        week off -- that only feeds the per-day worked-hour target
        (build_monthly_summary's shift_day_secs). What actually decides
        "total_working_days" / week-off classification is the entirely
        separate, company-wide CompanyLeaves model (get_company_leave_days
        -> get_working_days), and after `flush` there are zero rows in it,
        so every day in the period was landing as neither present, week
        off, nor absent -- just missing from the row's own arithmetic
        entirely. Both mechanisms have to agree, so both are built here.
        """
        from base.models import (
            CompanyLeaves,
            EmployeeShift,
            EmployeeShiftDay,
            EmployeeShiftSchedule,
        )
        from horilla.testkit import make_company

        company = make_company("Precise Fixture Co")

        shift = EmployeeShift.objects.create(employee_shift="Fixture Shift (Mon-Fri)")
        shift.company_id.add(company)
        for day_name in WEEKDAY_NAMES:
            day, _created = EmployeeShiftDay.objects.get_or_create(day=day_name)
            EmployeeShiftSchedule.objects.create(day=day, shift_id=shift)

        # "5"/"6" = Saturday/Sunday (base.models.WEEK_DAYS). based_on_week
        # left blank: every week, not one specific week of the month.
        for week_day in ("5", "6"):
            weekly_off, _created = CompanyLeaves.objects.get_or_create(
                based_on_week=None,
                based_on_week_day=week_day,
            )
            weekly_off.company_id.add(company)

        return company, shift

    # -- components/structure ---------------------------------------------

    def _structure(self, company):
        """
        Two structures, sharing the same PF/PT deductions: a Gross Up one
        (wage IS basic pay, allowances stack on top) for most employees, and
        a CTC Down one (wage IS the package; a BASIC-flagged component works
        basic out of it) for CTC_DOWN_INDEXES -- the same shape
        base/demo_data/modules/payroll_features.py builds for the broader
        demo dataset, reused here rather than invented a second time.
        """
        from payroll.models.models import Allowance, Deduction, SalaryStructure

        hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="HRA",
            sequence=10,
            is_fixed=False,
            based_on="basic_pay",
            rate=40.0,
            is_taxable=True,
        )
        special = Allowance.objects.create(
            title="Special Allowance",
            code="SPL",
            sequence=20,
            is_fixed=True,
            amount=2000.0,
            is_taxable=True,
        )
        pf = Deduction.objects.create(
            title="Provident Fund (PF)",
            code="PF",
            sequence=10,
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            employer_rate=12.0,
            is_pretax=True,
        )
        pt = Deduction.objects.create(
            title="Professional Tax",
            code="PT",
            sequence=20,
            is_fixed=True,
            amount=200.0,
            is_pretax=False,
        )
        gross_up = SalaryStructure.objects.create(
            title="Precise Fixture — Standard",
            company_id=company,
            structure_mode="gross_up",
        )
        gross_up.allowances.set([hra, special])
        gross_up.deductions.set([pf, pt])

        basic = Allowance.objects.create(
            title="Basic Pay",
            code="BASIC",
            sequence=5,
            is_basic_pay=True,
            is_fixed=False,
            based_on="formula",
            formula="CTC * 0.4",
            is_taxable=True,
        )
        ctc_hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="CHRA",
            sequence=10,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
            is_taxable=True,
        )
        flex = Allowance.objects.create(
            title="Flexible Benefits (Balance)",
            code="FLEX",
            sequence=90,
            is_fixed=False,
            based_on="balance",
            is_taxable=True,
        )
        ctc_down = SalaryStructure.objects.create(
            title="Precise Fixture — CTC Down",
            company_id=company,
            structure_mode="ctc_down",
        )
        ctc_down.allowances.set([basic, ctc_hra, flex])
        ctc_down.deductions.set([pf, pt])

        self.stdout.write(
            f"  Structure: {gross_up.title} (2 earnings, 2 deductions, Gross Up)"
        )
        self.stdout.write(
            f"  Structure: {ctc_down.title} (3 earnings, 2 deductions, CTC Down)"
        )
        return gross_up, ctc_down

    # -- people --------------------------------------------------------

    def _employees(self, company, shift, gross_up, ctc_down):
        """
        Contract.salary_structure_id is never set directly on ``create()``:
        that only points the FK at the structure without the side effect
        that makes it real -- ``set_salary_structure()`` is what adds the
        employee to each of the structure's Allowance/Deduction rows'
        ``specific_employees``, which is what calculate_pre_tax_deduction /
        calculate_post_tax_deduction actually filter on. Skipping it is
        exactly why PF and Professional Tax were silently absent from every
        payslip this command produced before.
        """
        from horilla.testkit import make_employee
        from payroll.models.models import Contract

        employees = []
        for i in range(EMPLOYEES):
            first, last = EMPLOYEE_NAMES[i % len(EMPLOYEE_NAMES)]
            is_ctc_down = i in CTC_DOWN_INDEXES
            employee = make_employee(
                company=company,
                email=f"{first.lower()}.{last.lower()}@fixture.payroll.test",
                first_name=first,
                last_name=last,
                shift=shift,
            )
            Contract.objects.filter(employee_id=employee).delete()
            contract = Contract.objects.create(
                contract_name=f"{employee.get_full_name()} — Standard",
                employee_id=employee,
                contract_start_date=datetime.date(2024, 1, 1),
                contract_status="active",
                wage_type="monthly",
                wage=WAGE,
                calculate_daily_leave_amount=True,
                daily_leave_amount_divisor="calendar_days",
                deduct_leave_from_basic_pay=True,
            )
            if is_ctc_down:
                contract.set_salary_structure(ctc_down)
                Contract.objects.filter(pk=contract.pk).update(
                    monthly_ctc=round(WAGE * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2),
                    wage=0,
                    daily_leave_amount_base="monthly_ctc",
                )
            else:
                contract.set_salary_structure(gross_up)
                Contract.objects.filter(pk=contract.pk).update(
                    daily_leave_amount_base="wage",
                )
            employees.append(employee)
        gross_up_count = len(employees) - len(CTC_DOWN_INDEXES)
        self.stdout.write(
            f"  {len(employees)} employees: {gross_up_count} on Gross Up "
            f"({WAGE} monthly wage), {len(CTC_DOWN_INDEXES)} on CTC Down "
            f"({round(WAGE * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2)} monthly CTC)"
        )
        return employees

    def _leave_types(self):
        """
        Not seeded by any migration -- the old loaddata calls this command
        no longer makes were the only reason LeaveType rows ever existed
        here. Querying for "a paid/unpaid LeaveType" afterward silently
        found nothing and skipped creating every single leave request, which
        is why paid_leave/unpaid_leave kept coming back 0 regardless of what
        the override stated it should be.
        """
        from leave.models import LeaveType

        paid_type, _created = LeaveType.objects.get_or_create(
            name="Fixture Paid Leave",
            defaults={"payment": "paid", "limit_leave": False},
        )
        unpaid_type, _created = LeaveType.objects.get_or_create(
            name="Fixture Unpaid Leave",
            defaults={"payment": "unpaid", "limit_leave": False},
        )
        return paid_type, unpaid_type

    # -- attendance ------------------------------------------------------

    def _attendance_for(self, employee, start, end, index, paid_type, unpaid_type):
        """
        Two layers, not one:

        1. Real Attendance/LeaveRequest rows, for a calendar that looks like
           a real month rather than an empty one -- built against this
           command's own Mon-Fri shift, so week_off here always means
           exactly Saturday/Sunday.
        2. An AttendanceSummaryOverride stating the same counts outright.
           build_monthly_summary applies it last, over whatever the rows
           above computed, so the payslip's numbers come from what was
           *stated* -- guaranteed to balance against the period's real
           week_off/holiday -- rather than from hoping every classification
           the rows pass through (conflicts, half days, edge-of-period
           leave) landed exactly as intended.
        """
        from attendance.models import Attendance, AttendanceSummaryOverride
        from leave.models import LeaveRequest

        Attendance.objects.filter(
            employee_id=employee, attendance_date__range=(start, end)
        ).delete()
        LeaveRequest.objects.filter(
            employee_id=employee, start_date__range=(start, end)
        ).delete()

        weekdays = list(_weekdays(start, end))
        leave_count = min(
            LEAVE_DAYS_BY_INDEX[index % len(LEAVE_DAYS_BY_INDEX)], len(weekdays) - 1
        )
        leave_days = weekdays[-leave_count:] if leave_count else []
        present_days = [d for d in weekdays if d not in leave_days]

        for day in present_days:
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=day,
                attendance_clock_in=datetime.time(9, 0),
                attendance_clock_out=datetime.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )

        paid_leave_count = 0
        unpaid_leave_count = 0
        if leave_days:
            for position, day in enumerate(leave_days):
                is_paid = position % 2 == 0
                leave_type = paid_type if is_paid else unpaid_type
                if is_paid:
                    paid_leave_count += 1
                else:
                    unpaid_leave_count += 1
                LeaveRequest.objects.create(
                    employee_id=employee,
                    leave_type_id=leave_type,
                    start_date=day,
                    end_date=day,
                    status="approved",
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    description="Precise fixture — planned leave",
                )

        # Balanced by construction: present + paid_leave + unpaid_leave +
        # absent(0) is exactly len(weekdays), and week_off/holiday are
        # whatever this command's own shift/calendar say for the period --
        # so overriding present/paid_leave/unpaid_leave/absent to these
        # counts, on top of that real week_off/holiday, always reconciles.
        AttendanceSummaryOverride.objects.update_or_create(
            employee_id=employee,
            from_date=start,
            to_date=end,
            defaults={
                "present": float(len(present_days)),
                "paid_leave": float(paid_leave_count),
                "unpaid_leave": float(unpaid_leave_count),
                "absent": 0.0,
                "note": "Precise fixture — stated totals",
            },
        )

    def _verified_summary(self, employee, start, end):
        """
        The real attendance summary, fetched the same way the payroll
        engine does -- and checked, here, before anything is saved.
        Reconciliation failing is not logged and moved past: it stops the
        whole command, because a payslip built on a summary that already
        doesn't add up is the exact failure mode this command exists to
        rule out.
        """
        from attendance.methods.utils import get_employee_attendance_summary

        summaries = get_employee_attendance_summary([employee], start, end)
        summary = summaries.get(employee.pk)
        if not summary:
            raise CommandError(
                f"No attendance summary returned for {employee} ({start}..{end})."
            )

        total_days = (end - start).days + 1
        paid_days = summary["paid_days"]
        unpaid_days = summary["unpaid_days"]
        if abs((paid_days + unpaid_days) - total_days) > 0.01:
            raise CommandError(
                f"{employee}: paid_days({paid_days}) + unpaid_days({unpaid_days}) "
                f"= {paid_days + unpaid_days}, not {total_days} (the period's own "
                f"calendar days). Raw summary: {summary}"
            )
        return summary

    # -- payslip ---------------------------------------------------------

    def _save_payslip(self, employee, start, end, summary):
        from payroll.methods.methods import payslip_fields, save_payslip
        from payroll.methods.payroll_run import payroll_calculation

        result = payroll_calculation(employee, start, end, month_summary=summary)
        if not result:
            raise CommandError(f"payroll_calculation refused a payslip for {employee}.")
        fields = payslip_fields(
            result,
            employee,
            status="paid",
            group_name=f"Precise Fixture — {start.strftime('%b %Y')}",
        )
        save_payslip(**fields)
