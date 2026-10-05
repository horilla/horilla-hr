"""
methods.py

Payroll related module to write custom calculation methods
"""

import calendar
import json
import logging
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q

# from attendance.models import Attendance
from base.methods import (
    get_company_leave_dates,
    get_date_range,
    get_holiday_dates,
    get_pagination,
    get_working_days,
)
from base.models import CompanyLeaves, Holidays
from horilla.methods import get_horilla_model_class
from payroll.methods.component_formula import ComponentFormulaError
from payroll.methods.employer_cost import employer_amount
from payroll.models.models import Contract, Deduction, Payslip

logger = logging.getLogger(__name__)


def get_total_days(start_date, end_date):
    """
    Calculates the total number of days in a given period.

    Args:
        start_date (date): The start date of the period.

        end_date (date): The end date of the period.
    Returns:
        int: The total number of days in the period, including the end date.

    Example:
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 10)
        days_on_period = get_total_days(start_date, end_date)
    """
    delta = end_date - start_date
    total_days = delta.days + 1  # Add 1 to include the end date itself
    return total_days


def get_total_calendar_days(pay_head_data):
    """
    Every day in the pay period, week offs and holidays included.

    Every place that shows "paid days" alongside a total reads it from
    `pay_head_data["working_days"]`, which excludes week offs and holidays --
    so a 6-day paid count was shown against 23, not the 31 the period title
    already says. `start_date`/`end_date` are stored as ISO strings in
    `pay_head_data` (it is a JSON field), hence the parse rather than a
    straight `get_total_days` call.
    """
    start_date = datetime.strptime(pay_head_data["start_date"], "%Y-%m-%d").date()
    end_date = datetime.strptime(pay_head_data["end_date"], "%Y-%m-%d").date()
    return get_total_days(start_date, end_date)


def get_leaves(employee, start_date, end_date):
    """
    This method is used to return all the leaves taken by the employee
    between the period.

    Args:
        employee (obj): Employee model instance
        start_date (obj): the start date from the data needed
        end_date (obj): the end date till the date needed
    """
    if apps.is_installed("leave"):
        approved_leaves = employee.leaverequest_set.filter(status="approved")
    else:
        approved_leaves = None
    paid_leave = 0
    unpaid_leave = 0
    paid_half = 0
    unpaid_half = 0
    paid_leave_dates = []
    unpaid_leave_dates = []
    # list of (date, payment_percentage) for partial-pay leaves
    custom_leave_dates = []
    # (leave_type_name, payment_percentage) -> list of dates, for per-leave-type breakdown
    custom_leave_dates_by_type = {}
    company_leave_dates = get_working_days(start_date, end_date, employee)[
        "company_leave_dates"
    ]

    if approved_leaves and approved_leaves.exists():
        for instance in approved_leaves:
            leave_type = instance.leave_type_id
            # Resolve payment category: use payment_type (new) with fallback to payment (legacy)
            if leave_type.payment_type:
                ptype = leave_type.payment_type
            else:
                ptype = "paid" if leave_type.payment == "paid" else "unpaid"

            all_dates = instance.requested_dates()
            dates_in_range = [d for d in all_dates if start_date <= d <= end_date]

            if ptype == "paid":
                paid_leave_dates += dates_in_range
            elif ptype == "custom":
                pct = float(leave_type.payment_percentage or 0)
                custom_leave_dates += [(d, pct) for d in dates_in_range]
                type_key = (leave_type.name, pct)
                custom_leave_dates_by_type.setdefault(type_key, [])
                custom_leave_dates_by_type[type_key] += dates_in_range
            else:
                unpaid_leave_dates += dates_in_range

    half_day_data = find_half_day_leaves()

    unpaid_half = half_day_data["half_unpaid_leaves"]
    paid_half = half_day_data["half_paid_leaves"]

    paid_leave_dates = list(set(paid_leave_dates) - set(company_leave_dates))
    unpaid_leave_dates = list(set(unpaid_leave_dates) - set(company_leave_dates))
    custom_leave_dates = [
        (d, pct) for d, pct in custom_leave_dates if d not in company_leave_dates
    ]
    custom_dates_only = [d for d, _ in custom_leave_dates]
    paid_leave = len(paid_leave_dates) - paid_half
    unpaid_leave = len(unpaid_leave_dates) - unpaid_half

    # Per custom payment leave type breakdown for payslip display: leave type
    # name, number of days taken, and the configured payment percentage.
    custom_leave_breakdown = [
        {
            "leave_type": type_name,
            "days": len([d for d in dates if d not in company_leave_dates]),
            "percentage": pct,
        }
        for (type_name, pct), dates in custom_leave_dates_by_type.items()
        if [d for d in dates if d not in company_leave_dates]
    ]

    return {
        "paid_leave": paid_leave,
        "unpaid_leaves": unpaid_leave,
        "partial_pay_days": len(custom_dates_only),
        "total_leaves": paid_leave + unpaid_leave + len(custom_dates_only),
        # List of paid leave date between range
        "paid_leave_dates": paid_leave_dates,
        # List of unpaid leave date between range
        "unpaid_leave_dates": unpaid_leave_dates,
        # List of (date, payment_percentage) for custom partial-pay leaves
        "custom_leave_dates": custom_leave_dates,
        # Per leave type breakdown of custom partial-pay leaves for display
        "custom_leave_breakdown": custom_leave_breakdown,
        "leave_dates": unpaid_leave_dates + paid_leave_dates + custom_dates_only,
    }


if apps.is_installed("attendance"):

    def get_attendance(employee, start_date, end_date):
        """
        This method is used to render attendance details between the range

        Args:
            employee (obj): Employee user instance
            start_date (obj): start date of the period
            end_date (obj): end date of the period
        """
        Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
        attendances_on_period = Attendance.objects.filter(
            employee_id=employee,
            attendance_date__range=(start_date, end_date),
            attendance_validated=True,
        )
        present_on = [
            attendance.attendance_date for attendance in attendances_on_period
        ]
        working_days_between_range = get_working_days(start_date, end_date, employee)[
            "working_days_on"
        ]
        leave_dates = get_leaves(employee, start_date, end_date)["leave_dates"]
        conflict_dates = list(
            set(working_days_between_range)
            - set(attendances_on_period)
            - set(leave_dates)
        )
        conflict_dates = conflict_dates + [
            date
            for date in present_on
            if date in get_holiday_dates(start_date, end_date, employee)
            or date
            in list(
                set(
                    get_company_leave_dates(start_date.year)
                    + get_company_leave_dates(end_date.year)
                )
            )
        ]

        return {
            "attendances_on_period": attendances_on_period,
            "present_on": present_on,
            "conflict_dates": conflict_dates,
        }


def hourly_computation(employee, wage, start_date, end_date):
    """
    Hourly salary computation for period.

    Regular hours  = at_work_second - overtime_second on scheduled working days.
    Overtime is split into three sources for display purposes:
      - ot_regular:  worked beyond minimum_hour on a normal working day
      - ot_week_off: all hours worked on a week-off day (entirely overtime)
      - ot_holiday:  all hours worked on a holiday (entirely overtime)
    Actual overtime PAY is computed separately by the configurable
    "Regular Overtime" / "Week Off Overtime" / "Holiday Overtime" Allowance
    types (see payroll/methods/payslip_calc.py), not here — these seconds
    are worked hours regardless of approval, used to show the breakdown on
    the payslip and to surface pending-approval hours.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee (per hour)
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    if not apps.is_installed("attendance"):
        return {
            "basic_pay": 0,
            "loss_of_pay": 0,
            "regular_seconds": 0,
            "ot_seconds": 0,
            "ot_regular_seconds": 0,
            "ot_week_off_seconds": 0,
            "ot_holiday_seconds": 0,
        }
    from attendance.models import AttendanceConflictResolution

    attendance_data = get_attendance(employee, start_date, end_date)
    attendances_on_period = attendance_data["attendances_on_period"]

    working_day_dates = set(
        get_working_days(start_date, end_date, employee)["working_days_on"]
    )
    holiday_dates = set(get_holiday_dates(start_date, end_date, employee))
    # A holiday/week-off day HR has regularized away from that
    # classification (Full Present/Half Day) is treated as a normal
    # working day here too, matching build_monthly_summary's same rule.
    regularized_dates = set(
        AttendanceConflictResolution.objects.filter(
            employee_id=employee,
            date__range=(start_date, end_date),
            resolution__in=("full_present", "half_present"),
        ).values_list("date", flat=True)
    )

    regular_seconds = 0
    ot_regular_seconds = ot_week_off_seconds = ot_holiday_seconds = 0
    for attendance in attendances_on_period:
        att_date = attendance.attendance_date
        if att_date in working_day_dates or att_date in regularized_dates:
            regular_seconds += attendance.at_work_second - attendance.overtime_second
            ot_regular_seconds += attendance.overtime_second
        elif att_date in holiday_dates:
            ot_holiday_seconds += attendance.at_work_second
        else:
            ot_week_off_seconds += attendance.at_work_second

    ot_seconds = ot_regular_seconds + ot_week_off_seconds + ot_holiday_seconds
    basic_pay = float(f"{(wage / 3600 * regular_seconds):.2f}")

    return {
        "basic_pay": basic_pay,
        "loss_of_pay": 0,
        "paid_days": len(attendances_on_period),
        "unpaid_days": 0,
        "regular_seconds": regular_seconds,
        "ot_regular_seconds": ot_regular_seconds,
        "ot_week_off_seconds": ot_week_off_seconds,
        "ot_holiday_seconds": ot_holiday_seconds,
        "ot_seconds": ot_seconds,
    }


def find_half_day_leaves():
    """
    This method is used to return the half day leave details

    Args:
        employee (obj): Employee model instance
        start_date (obj): start date of the period
        end_date (obj): end date of the period
    """
    paid_queryset = []
    unpaid_queryset = []

    paid_leaves = list(filter(None, list(set(paid_queryset))))
    unpaid_leaves = list(filter(None, list(set(unpaid_queryset))))

    paid_half = len(paid_leaves) * 0.5
    unpaid_half = len(unpaid_leaves) * 0.5
    queryset = paid_leaves + unpaid_leaves
    total_leaves = len(queryset) * 0.50
    return {
        "half_day_query_set": queryset,
        "half_day_leaves": total_leaves,
        "half_paid_leaves": paid_half,
        "half_unpaid_leaves": unpaid_half,
    }


def daily_computation(employee, wage, start_date, end_date):
    """
    Hourly salary computation for period.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    working_day_data = get_working_days(start_date, end_date)
    total_working_days = working_day_data["total_working_days"]

    leave_data = get_leaves(employee, start_date, end_date)

    contract = employee.contract_set.filter(contract_status="active").first()
    basic_pay = wage * total_working_days
    loss_of_pay = 0

    date_range = get_date_range(start_date, end_date)
    # Half-day filter: only truly unpaid leaves (exclude custom payment_type)
    unpaid_only_q = (
        Q(leave_type_id__payment_type="unpaid")
        | Q(leave_type_id__payment_type__isnull=True, leave_type_id__payment="unpaid")
        | Q(leave_type_id__payment_type="", leave_type_id__payment="unpaid")
    )
    half_day_leaves_between_period_on_start_date = (
        employee.leaverequest_set.filter(
            unpaid_only_q,
            start_date__in=date_range,
            status="approved",
        )
        .exclude(start_date_breakdown="full_day")
        .count()
    )

    half_day_leaves_between_period_on_end_date = (
        employee.leaverequest_set.filter(
            unpaid_only_q, end_date__in=date_range, status="approved"
        )
        .exclude(end_date_breakdown="full_day")
        .exclude(start_date=F("end_date"))
        .count()
    )
    unpaid_half_leaves = (
        half_day_leaves_between_period_on_start_date
        + half_day_leaves_between_period_on_end_date
    ) * 0.5

    contract = employee.contract_set.filter(
        is_active=True, contract_status="active"
    ).first()

    unpaid_leaves = leave_data["unpaid_leaves"] - unpaid_half_leaves
    if contract.calculate_daily_leave_amount:
        loss_of_pay = unpaid_leaves * wage
    else:
        fixed_penalty = contract.deduction_for_one_leave_amount
        loss_of_pay = unpaid_leaves * fixed_penalty

    # Partial deduction for custom payment_type leaves (tracked separately for payslip display)
    custom_leave_dates = leave_data.get("custom_leave_dates", [])
    custom_leave_deduction = 0.0
    for _leave_date, pct in custom_leave_dates:
        deductible_fraction = 1.0 - (pct / 100.0)
        if contract.calculate_daily_leave_amount:
            custom_leave_deduction += wage * deductible_fraction
        else:
            custom_leave_deduction += (
                contract.deduction_for_one_leave_amount * deductible_fraction
            )
    loss_of_pay += custom_leave_deduction

    # Per leave type deduction amount, for payslip display
    custom_leave_breakdown = leave_data.get("custom_leave_breakdown", [])
    for entry in custom_leave_breakdown:
        deductible_fraction = 1.0 - (entry["percentage"] / 100.0)
        per_day_basis = (
            wage
            if contract.calculate_daily_leave_amount
            else contract.deduction_for_one_leave_amount
        )
        entry["deduction_amount"] = round(
            per_day_basis * deductible_fraction * entry["days"], 2
        )

    if contract.deduct_leave_from_basic_pay:
        basic_pay = basic_pay - loss_of_pay

    return {
        "basic_pay": basic_pay,
        "loss_of_pay": loss_of_pay,
        "custom_leave_deduction": custom_leave_deduction,
        "custom_leave_breakdown": custom_leave_breakdown,
        "paid_days": total_working_days,
        "unpaid_days": unpaid_leaves,
        "partial_pay_days": leave_data.get("partial_pay_days", 0),
    }


def get_daily_salary(wage, wage_date, contract=None) -> dict:
    """
    What one day of unpaid leave costs.

    Two things decide it, and both used to be fixed in this function: which
    figure a day is a share of, and how many days it is shared between. The
    divisor in particular is not a detail — a 44,000 wage over 22 working days
    is 2,000 a day, and over 30 calendar days it is 1,467, so the same absence
    costs a third less.

    ``contract`` is optional so every existing caller keeps the old behaviour:
    the contract wage divided by working days.
    """
    last_day = calendar.monthrange(wage_date.year, wage_date.month)[1]
    end_date = date(wage_date.year, wage_date.month, last_day)
    start_date = date(wage_date.year, wage_date.month, 1)

    base = wage
    divisor_name = "working_days"
    if contract is not None:
        if getattr(contract, "daily_leave_amount_base", "wage") == "monthly_ctc":
            # Falls back to the wage rather than to zero: a contract with no
            # CTC set would otherwise make every unpaid day free.
            base = contract.monthly_ctc or wage
        divisor_name = getattr(contract, "daily_leave_amount_divisor", "working_days")

    if divisor_name == "calendar_days":
        days = last_day
    else:
        days = get_working_days(start_date, end_date)["total_working_days"]

    day_wage = base / days if days else 0.0

    return {
        "day_wage": day_wage,
        # The two numbers day_wage was divided out of -- exposed so a
        # payslip can show the actual equation (base ÷ days = day_wage)
        # rather than only naming which contract settings were used.
        "base": base,
        "days": days,
    }


def compute_custom_leave_deduction(leave_data, contract, daily_computed_salary):
    """
    Compute custom-payment-type leave deduction amount and per-type breakdown.

    Args:
        leave_data            : dict returned by get_leaves()
        contract              : active Contract instance
        daily_computed_salary : wage / working_days_in_month

    Returns:
        (custom_leave_deduction, custom_leave_breakdown)
    """
    custom_leave_deduction = 0.0
    for _leave_date, pct in leave_data.get("custom_leave_dates", []):
        deductible_fraction = 1.0 - (pct / 100.0)
        if contract.calculate_daily_leave_amount:
            custom_leave_deduction += daily_computed_salary * deductible_fraction
        else:
            custom_leave_deduction += (
                contract.deduction_for_one_leave_amount * deductible_fraction
            )

    custom_leave_breakdown = leave_data.get("custom_leave_breakdown", [])
    for entry in custom_leave_breakdown:
        deductible_fraction = 1.0 - (entry["percentage"] / 100.0)
        per_day_basis = (
            daily_computed_salary
            if contract.calculate_daily_leave_amount
            else contract.deduction_for_one_leave_amount
        )
        entry["deduction_amount"] = round(
            per_day_basis * deductible_fraction * entry["days"], 2
        )

    return custom_leave_deduction, custom_leave_breakdown


def months_between_range(wage, start_date, end_date):
    """
    This method is used to find the months between range
    """
    months_data = []

    for current_date in (
        start_date + relativedelta(months=i)
        for i in range(
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
            + 1
        )
    ):
        month = current_date.month
        year = current_date.year

        days_in_month = (
            current_date + relativedelta(day=1, months=1) - relativedelta(days=1)
        ).day

        # Calculate the end date for the current month
        current_end_date = current_date + relativedelta(day=days_in_month)
        current_end_date = min(current_end_date, end_date)
        working_days_on_month = get_working_days(
            current_date.replace(day=1), current_date.replace(day=days_in_month)
        )["total_working_days"]

        month_start_date = (
            date(year=year, month=month, day=1)
            if start_date < date(year=year, month=month, day=1)
            else start_date
        )
        total_working_days_on_period = get_working_days(
            month_start_date, current_end_date
        )["total_working_days"]

        month_info = {
            "month": month,
            "year": year,
            "days": days_in_month,
            "start_date": month_start_date.strftime("%Y-%m-%d"),
            "end_date": current_end_date.strftime("%Y-%m-%d"),
            # month period
            "working_days_on_period": total_working_days_on_period,
            "working_days_on_month": working_days_on_month,
            "per_day_amount": (
                wage / working_days_on_month if working_days_on_month else 0.0
            ),
            # if working_days_on_month != 0 else 0 #769,
        }

        months_data.append(month_info)
        # Set the start date for the next month as the first day of the next month
        current_date = (current_date + relativedelta(day=1, months=1)).replace(day=1)

    return months_data


def compute_yearly_taxable_amount(
    monthly_taxable_amount=None,
    default_yearly_taxable_amount=None,
    *args,
    **kwargs,
):
    """
    Compute yearly taxable amount custom logic
    eg:
        default_yearly_taxable_amount = monthly_taxable_amount * 12
    """
    return default_yearly_taxable_amount


def convert_year_tax_to_period(
    federal_tax_for_period=None,
    yearly_tax=None,
    total_days=None,
    start_date=None,
    end_date=None,
    *args,
    **kwargs,
):
    """
    Method to convert yearly taxable to monthly
    """
    return federal_tax_for_period


def compute_net_pay(
    net_pay=None,
    gross_pay=None,
    total_pretax_deduction=None,
    total_post_tax_deduction=None,
    total_tax_deductions=None,
    federal_tax=None,
    loss_of_pay_amount=None,
    *args,
    **kwargs,
):
    """
    Compute net pay | Additional logic
    """

    return net_pay


def monthly_computation(employee, wage, start_date, end_date, *args, **kwargs):
    """
    Hourly salary computation for period.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    basic_pay = 0
    month_data = months_between_range(wage, start_date, end_date)

    leave_data = get_leaves(employee, start_date, end_date)

    for data in month_data:
        basic_pay = basic_pay + (
            data["working_days_on_period"] * data["per_day_amount"]
        )

    contract = employee.contract_set.filter(contract_status="active").first()
    loss_of_pay = 0
    date_range = get_date_range(start_date, end_date)
    # Half-day filter: only truly unpaid leaves (exclude custom payment_type)
    unpaid_only_q = (
        Q(leave_type_id__payment_type="unpaid")
        | Q(leave_type_id__payment_type__isnull=True, leave_type_id__payment="unpaid")
        | Q(leave_type_id__payment_type="", leave_type_id__payment="unpaid")
    )
    if apps.is_installed("leave"):
        start_date_leaves = (
            employee.leaverequest_set.filter(
                unpaid_only_q,
                start_date__in=date_range,
                status="approved",
            )
            .exclude(start_date_breakdown="full_day")
            .count()
        )
        end_date_leaves = (
            employee.leaverequest_set.filter(
                unpaid_only_q,
                end_date__in=date_range,
                status="approved",
            )
            .exclude(end_date_breakdown="full_day")
            .exclude(start_date=F("end_date"))
            .count()
        )
    else:
        start_date_leaves = 0
        end_date_leaves = 0

    half_day_leaves_between_period_on_start_date = start_date_leaves

    half_day_leaves_between_period_on_end_date = end_date_leaves

    unpaid_half_leaves = (
        half_day_leaves_between_period_on_start_date
        + half_day_leaves_between_period_on_end_date
    ) * 0.5

    contract = employee.contract_set.filter(
        is_active=True, contract_status="active"
    ).first()
    unpaid_leaves = abs(leave_data["unpaid_leaves"] - unpaid_half_leaves)
    total_working_days = sum(d["working_days_on_period"] for d in month_data)
    paid_days = total_working_days - unpaid_leaves
    daily_salary = get_daily_salary(wage=wage, wage_date=start_date, contract=contract)
    daily_computed_salary = daily_salary["day_wage"]
    if contract.calculate_daily_leave_amount:
        loss_of_pay = unpaid_leaves * daily_computed_salary
    else:
        fixed_penalty = contract.deduction_for_one_leave_amount
        loss_of_pay = unpaid_leaves * fixed_penalty

    custom_leave_deduction, custom_leave_breakdown = compute_custom_leave_deduction(
        leave_data, contract, daily_computed_salary
    )
    loss_of_pay += custom_leave_deduction

    # A day as a share of GROSS cannot be priced here -- gross is basic plus
    # the earnings, and the earnings have not run. Deferred to payroll_run,
    # and basic is left whole so the gross it will be computed from is not
    # already carrying the deduction.
    lop_from_gross = getattr(contract, "daily_leave_amount_base", "wage") == "gross_pay"
    if lop_from_gross:
        loss_of_pay = custom_leave_deduction

    if contract.deduct_leave_from_basic_pay and not lop_from_gross:
        basic_pay = basic_pay - loss_of_pay
    return {
        "basic_pay": basic_pay,
        "loss_of_pay": loss_of_pay,
        "lop_from_gross": lop_from_gross,
        "lop_unpaid_days": unpaid_leaves,
        # .get(), not [] -- get_daily_salary is mocked with the older
        # {"day_wage": ...}-only shape across a number of existing tests, and
        # these three keys exist only to power a payslip popover, so a mock
        # that predates them should degrade to None rather than crash the
        # whole computation.
        "lop_base_amount": daily_salary.get("base"),
        "lop_divisor_days": daily_salary.get("days"),
        "lop_daily_rate": daily_computed_salary,
        "custom_leave_deduction": custom_leave_deduction,
        "custom_leave_breakdown": custom_leave_breakdown,
        "month_data": month_data,
        "unpaid_days": unpaid_leaves,
        "paid_days": paid_days,
        "partial_pay_days": leave_data.get("partial_pay_days", 0),
        "contract": contract,
    }


def compute_salary_on_period(
    employee, start_date, end_date, wage=None, month_summary=None
):
    """
    This method is used to compute salary on the start to end date period

    Args:
        employee (obj): Employee instance
        start_date (obj): start date of the period
        end_date (obj): end date of the period
        month_summary (dict): per-employee attendance summary row from
            build_monthly_summary(). When not supplied, day counts fall
            back to the classic months_between_range/get_working_days/
            get_leaves-based computation.
    """
    contract = Contract.objects.filter(
        employee_id=employee, contract_status="active"
    ).first()
    if contract is None:
        return contract

    month_summary = month_summary or {}
    # contract.pay_rate, not contract.wage: an hourly contract has its rate in
    # its own field now, and reading `wage` there would pay a monthly figure
    # per hour.
    wage = contract.pay_rate if wage is None else wage
    wage_type = contract.wage_type
    data = None
    if wage_type == "hourly":
        data = hourly_computation(employee, wage, start_date, end_date)
        regular_seconds = data["regular_seconds"]
        ot_seconds = data["ot_seconds"]
        ot_regular_seconds = data["ot_regular_seconds"]
        ot_week_off_seconds = data["ot_week_off_seconds"]
        ot_holiday_seconds = data["ot_holiday_seconds"]
        data["month_data"] = months_between_range(wage, start_date, end_date)
        data.setdefault("custom_leave_deduction", 0.0)
        data.setdefault("custom_leave_breakdown", [])
        data.update(month_summary)
        # restore after update so month_summary can't overwrite them
        data["regular_seconds"] = regular_seconds
        data["ot_seconds"] = ot_seconds
        data["ot_regular_seconds"] = ot_regular_seconds
        data["ot_week_off_seconds"] = ot_week_off_seconds
        data["ot_holiday_seconds"] = ot_holiday_seconds
        if month_summary:
            # attendance summary supplied — day counts come from it
            data["paid_days"] = (
                month_summary.get("present", 0)
                + month_summary.get("paid_leave", 0)
                + month_summary.get("week_off", 0)
                + month_summary.get("holiday", 0)
            )
            data["unpaid_days"] = month_summary.get(
                "unpaid_leave", 0
            ) + month_summary.get("absent", 0)
        # else: keep hourly_computation's own paid_days/unpaid_days (based on attendance count)
        # basic_pay uses only regular shift hours; week-off/holiday hours go to OT
        data["basic_pay"] = float(f"{(wage / 3600 * regular_seconds):.2f}")
    elif wage_type == "daily":
        if month_summary:
            # For daily wage, `wage` is the per-day rate; use attendance summary for day counts
            total_days = (
                month_summary.get("present", 0)
                + month_summary.get("paid_leave", 0)
                + month_summary.get("unpaid_leave", 0)
                + month_summary.get("absent", 0)
                + month_summary.get("week_off", 0)
                + month_summary.get("holiday", 0)
            )
            unpaid_days = month_summary.get("unpaid_leave", 0) + month_summary.get(
                "absent", 0
            )
            if month_summary.get("unresolved_conflicts", 0):
                unpaid_days = total_days
            paid_days = float(total_days - unpaid_days)
            loss_of_pay = unpaid_days * wage

            leave_data = get_leaves(employee, start_date, end_date)
            custom_leave_deduction, custom_leave_breakdown = (
                compute_custom_leave_deduction(leave_data, contract, wage)
            )
            loss_of_pay += custom_leave_deduction

            basic_pay = paid_days * wage
            if contract.deduct_leave_from_basic_pay:
                basic_pay = basic_pay - loss_of_pay

            data = {
                "basic_pay": basic_pay,
                "loss_of_pay": loss_of_pay,
                "custom_leave_deduction": custom_leave_deduction,
                "custom_leave_breakdown": custom_leave_breakdown,
                "month_data": months_between_range(wage, start_date, end_date),
                "unpaid_days": unpaid_days,
                "paid_days": paid_days,
                "partial_pay_days": leave_data.get("partial_pay_days", 0),
                "present": month_summary.get("present", 0),
                "paid_leave": month_summary.get("paid_leave", 0),
                "unpaid_leave": month_summary.get("unpaid_leave", 0),
                "absent": month_summary.get("absent", 0),
                "week_off": month_summary.get("week_off", 0),
                "holiday": month_summary.get("holiday", 0),
                "total_working": month_summary.get("total_working", 0),
                "contract": contract,
            }
        else:
            # No attendance summary supplied — fall back to working-days-based computation
            data = daily_computation(employee, wage, start_date, end_date)
            data["month_data"] = months_between_range(wage, start_date, end_date)
            data.setdefault("present", 0)
            data.setdefault("paid_leave", 0)
            data.setdefault("unpaid_leave", 0)
            data.setdefault("absent", 0)
            data.setdefault("week_off", 0)
            data.setdefault("holiday", 0)
            data.setdefault("total_working", 0)
            data["contract"] = contract
    else:
        if month_summary:
            total_days = (
                month_summary.get("week_off", 0)
                + month_summary.get("holiday", 0)
                + month_summary.get("absent", 0)
                + month_summary.get("present", 0)
                + month_summary.get("paid_leave", 0)
                + month_summary.get("unpaid_leave", 0)
            )
            unpaid_days = month_summary.get("unpaid_leave", 0) + month_summary.get(
                "absent", 0
            )
            if month_summary.get("unresolved_conflicts", 0):
                unpaid_days = total_days
            # What one unpaid day costs, from the contract: which figure it
            # is a share of, and how many days it is shared between.
            #
            # This branch used to work it out itself, as `wage / total_days`,
            # where total_days is every day in the month -- week offs and
            # holidays included. So a 25,000 wage over a 31 day August priced
            # a day at 806.45 no matter what the contract said, and a contract
            # set to divide by working days (23, giving 1,086.96) was ignored
            # entirely on this path while being honoured on the monthly one.
            # The same employee could be charged two different amounts for the
            # same absence depending on which branch ran.
            daily_salary = get_daily_salary(
                wage=wage, wage_date=start_date, contract=contract
            )
            daily_computed_salary = daily_salary["day_wage"]

            # And the flat per-leave figure was ignored here too: a contract
            # with "calculate daily leave amount" off still had its loss of
            # pay computed per day. Same switch the monthly branch applies.
            if contract.calculate_daily_leave_amount:
                loss_of_pay = unpaid_days * daily_computed_salary
            else:
                loss_of_pay = unpaid_days * (
                    contract.deduction_for_one_leave_amount or 0
                )

            leave_data = get_leaves(employee, start_date, end_date)
            custom_leave_deduction, custom_leave_breakdown = (
                compute_custom_leave_deduction(
                    leave_data, contract, daily_computed_salary
                )
            )
            loss_of_pay += custom_leave_deduction

            # Deferred when the day is a share of GROSS: gross is not known
            # until the earnings have run, and reducing basic here would make
            # the gross it is computed from already carry the deduction. See
            # payroll_run, which finishes it.
            # A local, not `data`: that dict is built a few lines below, so
            # writing into it here reached a None.
            lop_from_gross = (
                getattr(contract, "daily_leave_amount_base", "wage") == "gross_pay"
            )
            if lop_from_gross:
                loss_of_pay = custom_leave_deduction

            basic_pay = wage
            if contract.deduct_leave_from_basic_pay and not lop_from_gross:
                basic_pay = wage - loss_of_pay

            data = {
                "lop_from_gross": lop_from_gross,
                "lop_unpaid_days": unpaid_days,
                # .get(): see the identical note in monthly_computation.
                "lop_base_amount": daily_salary.get("base"),
                "lop_divisor_days": daily_salary.get("days"),
                "lop_daily_rate": daily_computed_salary,
                "basic_pay": basic_pay,
                "loss_of_pay": loss_of_pay,
                "custom_leave_deduction": custom_leave_deduction,
                "custom_leave_breakdown": custom_leave_breakdown,
                "month_data": months_between_range(wage, start_date, end_date),
                "unpaid_days": unpaid_days,
                # Present + paid leave + week off + holiday -- only absent and
                # unpaid leave are excluded. Same formula the attendance
                # summary and the batch-run review list already use for this
                # figure (attendance/methods/utils.py's own "paid_days"), so
                # a monthly payslip's count agrees with the one on those
                # pages instead of running on a different, working-days-only
                # basis that read as though the month itself were shorter.
                #
                # Report-only here -- basic_pay is the wage above, not a
                # multiple of this, so widening what counts as "paid" changes
                # nothing about what is actually paid. The daily-wage branch
                # keeps its own calendar-basis paid_days on purpose: there it
                # sets the pay.
                "paid_days": (
                    0.0
                    if month_summary.get("unresolved_conflicts", 0)
                    else float(
                        month_summary.get("present", 0)
                        + month_summary.get("paid_leave", 0)
                        + month_summary.get("week_off", 0)
                        + month_summary.get("holiday", 0)
                    )
                ),
                "partial_pay_days": leave_data.get("partial_pay_days", 0),
                "present": month_summary.get("present", 0),
                "paid_leave": month_summary.get("paid_leave", 0),
                "unpaid_leave": month_summary.get("unpaid_leave", 0),
                "absent": month_summary.get("absent", 0),
                "week_off": month_summary.get("week_off", 0),
                "holiday": month_summary.get("holiday", 0),
                "total_working": month_summary.get("total_working", 0),
                "contract": contract,
            }
        else:
            # No attendance summary supplied — fall back to months_between_range-based computation
            data = monthly_computation(employee, wage, start_date, end_date)
            data.setdefault("present", 0)
            data.setdefault("paid_leave", 0)
            data.setdefault("unpaid_leave", 0)
            data.setdefault("absent", 0)
            data.setdefault("week_off", 0)
            data.setdefault("holiday", 0)
            data.setdefault("total_working", 0)
    data["contract_wage"] = wage
    data["contract"] = contract
    return data


def paginator_qry(qryset, page_number):
    """
    This method is used to paginate queryset
    """
    paginator = Paginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


def calculate_employer_contribution(data):
    """
    This method is used to calculate the employer contribution
    """
    pay_head_data = data["pay_data"]
    deductions_to_process = [
        pay_head_data.get("pretax_deductions"),
        pay_head_data.get("post_tax_deductions"),
        pay_head_data.get("tax_deductions"),
        pay_head_data.get("net_deductions"),
    ]

    rows = [
        deduction
        for deductions in deductions_to_process
        if deductions
        for deduction in deductions
        if deduction.get("deduction_id")
    ]
    if not rows:
        return data

    # One query for the whole payslip. This used to run a query per deduction
    # row inside the loop, which on a run of any size is the difference
    # between one query and several thousand.
    components = Deduction.objects.entire().in_bulk(
        {row["deduction_id"] for row in rows}
    )

    # The codes and amounts every component on this payslip resolved to, which
    # is what an employer formula is written against -- the same names the
    # employee-side formulas use, so "(BASIC + DA) * 0.0367" means the same
    # thing on both sides of the component.
    context = pay_head_data.get("component_context") or {}

    for deduction in rows:
        component = components.get(deduction["deduction_id"])
        if component is None:
            continue

        try:
            result = employer_amount(component, pay_head_data, context)
        except ComponentFormulaError as exc:
            # Reported against the component and skipped, not raised: a
            # mistyped employer formula is the employer's own share, and
            # it must not stop the employee being paid.
            logger.error(
                "Employer formula on %s could not be worked out: %s",
                component,
                exc,
            )
            continue
        if result is None:
            continue
        employer_contribution_amount, formula = result
        if formula is not None:
            deduction["employer_contribution_formula"] = formula

        deduction["based_on"] = component.based_on
        deduction["employer_contribution_amount"] = employer_contribution_amount

    return data


def payslip_fields(payslip_data, employee, **extra):
    """
    Turn what ``payroll_calculation`` returns into what ``save_payslip`` takes.

    The two dicts use different key names for the same figures — ``deduction``
    against ``total_deductions``, ``pay_data`` against a JSON string in
    ``json_data`` — so every caller was translating between them by hand. The
    same fourteen lines existed in the single payslip view, the bulk view, the
    scheduler and the create form, which is how one of them came to be the only
    place that passed ``group_name``.

    ``extra`` carries whatever the caller adds on top: ``status``,
    ``group_name``, ``payroll_batch``.
    """
    data = {
        "employee": employee,
        "start_date": payslip_data["start_date"],
        "end_date": payslip_data["end_date"],
        "status": "draft",
        "contract_wage": payslip_data["contract_wage"],
        "basic_pay": payslip_data["basic_pay"],
        "gross_pay": payslip_data["gross_pay"],
        "deduction": payslip_data["total_deductions"],
        "net_pay": payslip_data["net_pay"],
        "pay_data": json.loads(payslip_data["json_data"]),
        "installments": payslip_data["installments"],
    }
    data.update(extra)
    calculate_employer_contribution(data)
    return data


@transaction.atomic
def save_payslip(**kwargs):
    """
    This method is used to save the generated payslip
    """
    filtered_instance = Payslip.objects.filter(
        employee_id=kwargs["employee"],
        start_date=kwargs["start_date"],
        end_date=kwargs["end_date"],
    ).first()
    instance = filtered_instance if filtered_instance is not None else Payslip()
    instance.employee_id = kwargs["employee"]
    # Only when one was given. Assigning kwargs.get() unconditionally meant
    # that regenerating an existing payslip through any path that does not
    # pass a name -- the single-payslip view, the scheduler -- erased the
    # batch it belonged to.
    if kwargs.get("group_name") is not None:
        instance.group_name = kwargs["group_name"]
    if kwargs.get("payroll_batch") is not None:
        instance.payroll_batch = kwargs["payroll_batch"]
    instance.start_date = kwargs["start_date"]
    instance.end_date = kwargs["end_date"]
    instance.status = kwargs["status"]
    instance.basic_pay = round(kwargs["basic_pay"], 2)
    instance.contract_wage = round(kwargs["contract_wage"], 2)
    instance.gross_pay = round(kwargs["gross_pay"], 2)
    # A backstop behind the engine's own cap, because this one field is read
    # by everything -- the payslip, the run totals, the dashboard, every
    # export -- and a single stored row where deductions exceed gross makes
    # all of them disagree with each other at once.
    instance.deduction = min(
        round(kwargs["deduction"], 2), round(kwargs["gross_pay"], 2)
    )
    instance.net_pay = max(0.0, round(kwargs["net_pay"], 2))
    instance.pay_head_data = kwargs["pay_data"]
    instance.save()
    instance.installment_ids.set(kwargs["installments"])
    return instance
