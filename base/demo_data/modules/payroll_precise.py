"""
Precise, self-verified payroll demo data.

backfill_payroll_feature_coverage / backfill_payroll_coverage (payroll_features.py,
payroll_trend.py) picked contracts and payslips out of the broad ~275-employee
demo roster and its independently-backfilled attendance (attendance_trend.py).
That backfill is good enough for dashboards and coverage counts, but was never
built to guarantee ``paid_days + unpaid_days == calendar days`` for every
employee it touches -- for some (an employee whose week_off/holiday coverage
for a given period doesn't reconcile) it doesn't, and a payslip computed on
top of an inconsistent summary is itself inconsistent.

Rather than trying to backfill the broad roster's attendance into
correctness, this seeds a small, dedicated set of employees per company with
attendance stated outright (AttendanceSummaryOverride) against a shift/
CompanyLeaves calendar this module also controls -- the same approach proven
out in payroll/management/commands/create_precise_payroll_fixtures.py,
adapted to run inside the shared seeder: no flush, idempotent, alongside
whatever else that company already has.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, time, timedelta

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

EMPLOYEES_PER_COMPANY = 4
CTC_DOWN_PER_COMPANY = 1
WAGE = 30000.0
CTC_DOWN_WAGE_TO_CTC_MULTIPLIER = 2.2
# Varied on purpose (0 through 3): "no leave at all" alongside "several leave
# days", without any employee's own numbers being ambiguous.
LEAVE_DAYS_BY_INDEX = [0, 1, 2, 3]
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday"]

# Sized well past any realistic company count x EMPLOYEES_PER_COMPANY, so no
# two precise employees anywhere in the demo ever share a name.
PRECISE_NAMES = [
    ("Grace", "Coleman"),
    ("Henry", "Ibrahim"),
    ("Zoe", "Nakamura"),
    ("Owen", "Kowalski"),
    ("Priya", "Nair"),
    ("Marcus", "Ondiek"),
    ("Elena", "Petrov"),
    ("Samuel", "Osei"),
    ("Nadia", "Haddad"),
    ("Felix", "Bergman"),
    ("Amara", "Okafor"),
    ("Leo", "Fontaine"),
    ("Ingrid", "Solberg"),
    ("Tariq", "Rahman"),
    ("Chloe", "Dubois"),
    ("Kenji", "Tanaka"),
]


def _closed_months(today):
    """
    The last two fully-closed calendar months relative to today -- never the
    current one. See create_precise_payroll_fixtures.py's identical helper.
    """
    months = []
    year, month = today.year, today.month
    for _ in range(2):
        month -= 1
        if month < 1:
            month = 12
            year -= 1
        last_day = calendar.monthrange(year, month)[1]
        months.append((date(year, month, 1), date(year, month, last_day)))
    return months


def _weekdays(start, end, holiday_dates=()):
    """
    Monday-Friday, minus any date a real (non-specific) Holiday already
    covers. Holidays are not company-scoped (get_holiday_dates(start, end)
    with no employee returns every one, system-wide) and build_monthly_summary
    counts them into its own "holiday" bucket regardless of which company an
    employee belongs to -- so a holiday landing on a weekday that this
    function did not also exclude was counted twice: once inside the
    override's own "present" total, and again as that row's untouched
    "holiday" count, which is exactly the paid_days-over-by-one this was
    written to rule out.
    """
    holiday_dates = set(holiday_dates)
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in holiday_dates:
            yield day
        day += timedelta(days=1)


def _ensure_calendar(company):
    """
    EmployeeShiftSchedule alone does not make Saturday/Sunday a week off --
    that only feeds the per-day worked-hour target. What actually decides
    week-off classification (get_working_days -> get_company_leave_dates) is
    the separate, company-wide CompanyLeaves model, so both are ensured here.
    """
    from base.models import (
        CompanyLeaves,
        EmployeeShift,
        EmployeeShiftDay,
        EmployeeShiftSchedule,
    )

    shift, _created = EmployeeShift._base_manager.get_or_create(
        employee_shift="Precise Payroll Demo Shift (Mon-Fri)"
    )
    shift.company_id.add(company)
    for day_name in WEEKDAY_NAMES:
        day, _c = EmployeeShiftDay._base_manager.get_or_create(day=day_name)
        EmployeeShiftSchedule._base_manager.get_or_create(day=day, shift_id=shift)

    # "5"/"6" = Saturday/Sunday (base.models.WEEK_DAYS). based_on_week left
    # blank: every week, not one specific week of the month.
    for week_day in ("5", "6"):
        weekly_off, _c = CompanyLeaves._base_manager.get_or_create(
            based_on_week=None,
            based_on_week_day=week_day,
        )
        weekly_off.company_id.add(company)

    return shift


def _ensure_leave_types():
    from leave.models import LeaveType

    paid_type, _c = LeaveType._base_manager.get_or_create(
        name="Precise Payroll Demo — Paid Leave",
        defaults={"payment": "paid", "limit_leave": False},
    )
    unpaid_type, _c = LeaveType._base_manager.get_or_create(
        name="Precise Payroll Demo — Unpaid Leave",
        defaults={"payment": "unpaid", "limit_leave": False},
    )
    return paid_type, unpaid_type


def _ensure_structures(company):
    """
    Reuses the existing Allowance/Deduction catalog and the CTC Down
    component recipe from payroll_features.py, rather than inventing a
    second one -- see that module's own note on why CTC Down needs its own
    BASIC/CHRA/CDA/FLEX set instead of the Gross Up allowances as-is.
    """
    from base.demo_data.modules.payroll_features import (
        SALARY_STRUCTURE_ALLOWANCE_TITLES,
        SALARY_STRUCTURE_DEDUCTION_TITLES,
        _get_or_create_ctc_down_components,
    )
    from payroll.models.models import Allowance, Deduction, SalaryStructure

    allowances = list(
        Allowance._base_manager.filter(title__in=SALARY_STRUCTURE_ALLOWANCE_TITLES)
    )
    deductions = list(
        Deduction._base_manager.filter(title__in=SALARY_STRUCTURE_DEDUCTION_TITLES)
    )
    flat_earnings = [a for a in allowances if a.is_fixed]
    ctc_down_components = _get_or_create_ctc_down_components(flat_earnings)

    gross_up, _c = SalaryStructure._base_manager.get_or_create(
        title="Precise Payroll Demo — Gross Up",
        company_id_id=company.pk,
        defaults={"structure_mode": "gross_up"},
    )
    if allowances:
        gross_up.allowances.add(*allowances)
    if deductions:
        gross_up.deductions.add(*deductions)

    ctc_down, _c = SalaryStructure._base_manager.get_or_create(
        title="Precise Payroll Demo — CTC Down",
        company_id_id=company.pk,
        defaults={"structure_mode": "ctc_down"},
    )
    ctc_down.allowances.add(*ctc_down_components)
    if deductions:
        ctc_down.deductions.add(*deductions)

    return gross_up, ctc_down


def _ensure_employees(company, shift, gross_up, ctc_down, name_offset):
    """
    Idempotent by email: a repeat load_demo_data run finds the same
    employees again instead of piling up duplicates each time.
    """
    from employee.models import Employee, EmployeeWorkInformation
    from horilla.testkit import make_employee
    from payroll.models.models import Contract

    employees = []
    for i in range(EMPLOYEES_PER_COMPANY):
        first, last = PRECISE_NAMES[(name_offset + i) % len(PRECISE_NAMES)]
        email = f"{first.lower()}.{last.lower()}@precise-payroll-demo.horilla"
        employee = Employee._base_manager.filter(email=email).first()
        if employee is None:
            employee = make_employee(
                company=company,
                email=email,
                first_name=first,
                last_name=last,
                shift=shift,
            )
            # Employee.save()'s own post-create signal seeds a starter
            # Contract with no salary structure and a default wage -- left
            # in place, it is exactly what "no wage or hourly rate, and no
            # earning marked as basic pay" downstream is describing, since
            # the properly-configured contract below never gets built once
            # an active one already exists for this employee.
            Contract._base_manager.filter(employee_id=employee).delete()
        else:
            EmployeeWorkInformation._base_manager.filter(employee_id=employee).update(
                shift_id=shift, company_id=company
            )

        is_ctc_down = i < CTC_DOWN_PER_COMPANY
        structure = ctc_down if is_ctc_down else gross_up
        contract = Contract._base_manager.filter(
            employee_id=employee, contract_status="active"
        ).first()
        if contract is None:
            contract = Contract._base_manager.create(
                contract_name=f"{employee.get_full_name()} — Precise Demo",
                employee_id=employee,
                contract_start_date=date(2024, 1, 1),
                contract_status="active",
                wage_type="monthly",
                wage=WAGE,
                calculate_daily_leave_amount=True,
                daily_leave_amount_divisor="calendar_days",
                deduct_leave_from_basic_pay=True,
            )
        # Re-applied every run, not just on first creation -- a repeat
        # load_demo_data finds the same employee/contract row again, and this
        # is what makes that row self-healing rather than merely idempotent.
        if contract.salary_structure_id_id != structure.pk:
            contract.set_salary_structure(structure)
        if is_ctc_down:
            Contract._base_manager.filter(pk=contract.pk).update(
                monthly_ctc=round(WAGE * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2),
                wage=0,
                daily_leave_amount_base="monthly_ctc",
            )
        else:
            Contract._base_manager.filter(pk=contract.pk).update(
                wage=WAGE,
                daily_leave_amount_base="wage",
            )
        employees.append((employee, i))
    return employees


def _state_attendance(employee, start, end, index, paid_type, unpaid_type):
    """
    Two layers: real Attendance/LeaveRequest rows for a calendar that looks
    like a real month, and an AttendanceSummaryOverride stating the same
    counts outright -- build_monthly_summary applies it last, over whatever
    the rows computed, so the payslip's numbers come from what was *stated*
    rather than from hoping every classification landed as intended. See
    create_precise_payroll_fixtures.py's identical, already-proven approach.
    """
    from attendance.models import Attendance, AttendanceSummaryOverride
    from base.methods import get_holiday_dates
    from leave.models import LeaveRequest

    Attendance._base_manager.filter(
        employee_id=employee, attendance_date__range=(start, end)
    ).delete()
    LeaveRequest._base_manager.filter(
        employee_id=employee, start_date__range=(start, end)
    ).delete()

    holiday_dates = get_holiday_dates(start, end)
    weekdays = list(_weekdays(start, end, holiday_dates))
    leave_count = min(
        LEAVE_DAYS_BY_INDEX[index % len(LEAVE_DAYS_BY_INDEX)], len(weekdays) - 1
    )
    leave_days = weekdays[-leave_count:] if leave_count else []
    present_days = [d for d in weekdays if d not in leave_days]

    for day in present_days:
        Attendance._base_manager.create(
            employee_id=employee,
            attendance_date=day,
            attendance_clock_in=time(9, 0),
            attendance_clock_out=time(18, 0),
            attendance_worked_hour="09:00",
            minimum_hour="08:00",
            attendance_validated=True,
        )

    paid_leave_count = 0
    unpaid_leave_count = 0
    for position, day in enumerate(leave_days):
        is_paid = position % 2 == 0
        leave_type = paid_type if is_paid else unpaid_type
        if is_paid:
            paid_leave_count += 1
        else:
            unpaid_leave_count += 1
        LeaveRequest._base_manager.create(
            employee_id=employee,
            leave_type_id=leave_type,
            start_date=day,
            end_date=day,
            status="approved",
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            description="Precise payroll demo — planned leave",
        )

    AttendanceSummaryOverride._base_manager.update_or_create(
        employee_id=employee,
        from_date=start,
        to_date=end,
        defaults={
            "present": float(len(present_days)),
            "paid_leave": float(paid_leave_count),
            "unpaid_leave": float(unpaid_leave_count),
            "absent": 0.0,
            "note": "Precise payroll demo — stated totals",
        },
    )


def _save_payslip(employee, start, end):
    """
    Verified, not assumed: logs and skips rather than raising, since this
    runs inside the shared seeder and one bad employee must not crash
    everything after it (the same warn-and-continue stance
    run_enterprise_demo_seeder already takes around its own steps).
    """
    from attendance.methods.utils import get_employee_attendance_summary
    from payroll.methods.methods import payslip_fields, save_payslip
    from payroll.methods.payroll_run import payroll_calculation

    summaries = get_employee_attendance_summary([employee], start, end)
    summary = summaries.get(employee.pk)
    if not summary:
        logger.warning("Precise payroll demo: no attendance summary for %s", employee)
        return False

    total_days = (end - start).days + 1
    if abs((summary["paid_days"] + summary["unpaid_days"]) - total_days) > 0.01:
        logger.warning(
            "Precise payroll demo: %s paid_days(%s) + unpaid_days(%s) != %s calendar "
            "days -- skipped",
            employee,
            summary["paid_days"],
            summary["unpaid_days"],
            total_days,
        )
        return False

    result = payroll_calculation(employee, start, end, month_summary=summary)
    if not result:
        logger.warning("Precise payroll demo: payroll_calculation refused %s", employee)
        return False

    fields = payslip_fields(
        result,
        employee,
        status="paid",
        group_name=f"Precise Payroll Demo — {start.strftime('%b %Y')}",
    )
    save_payslip(**fields)
    return True


@transaction.atomic
def backfill_precise_payroll(today: date | None = None) -> dict[str, int]:
    """
    Replaces backfill_payroll_feature_coverage/backfill_payroll_coverage in
    the seeder: a small, dedicated set of employees per company, each with
    attendance guaranteed to reconcile and payslips guaranteed to compute
    against it, rather than payslips assigned onto the broad roster's own
    (not always reconciling) attendance backfill.
    """
    if not apps.is_installed("payroll"):
        return {"precise_employees": 0, "precise_payslips": 0}

    from base.models import Company

    today = today or date.today()
    paid_type, unpaid_type = _ensure_leave_types()
    periods = _closed_months(today)

    total_employees = 0
    total_payslips = 0
    for company_index, company in enumerate(Company._base_manager.order_by("id")):
        shift = _ensure_calendar(company)
        gross_up, ctc_down = _ensure_structures(company)
        employees = _ensure_employees(
            company,
            shift,
            gross_up,
            ctc_down,
            name_offset=company_index * EMPLOYEES_PER_COMPANY,
        )
        total_employees += len(employees)
        for employee, index in employees:
            for period_start, period_end in periods:
                _state_attendance(
                    employee, period_start, period_end, index, paid_type, unpaid_type
                )
                if _save_payslip(employee, period_start, period_end):
                    total_payslips += 1

    logger.info(
        "Precise payroll demo: %s employee(s), %s payslip(s)",
        total_employees,
        total_payslips,
    )
    return {"precise_employees": total_employees, "precise_payslips": total_payslips}
