"""
Modern attendance dashboard views — KPI summary + ApexCharts.

Accessible at /attendance/dashboard/modern/ alongside the existing dashboard.
"""

import calendar
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from base.decorators import manager_can_enter


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to current month."""
    today = date.today()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = date.fromisoformat(from_str) if from_str else today.replace(day=1)
    except (ValueError, TypeError):
        from_date = today.replace(day=1)
    try:
        to_date = date.fromisoformat(to_str) if to_str else today
    except (ValueError, TypeError):
        to_date = today
    return from_date, to_date


def _current_month_bounds():
    """First and last calendar day of the current month (server "today").

    Used by the charts that must always reflect the present month
    regardless of the dashboard's own from/to period picker - see
    attendance_weekly_trend, attendance_overview, attendance_late_early_data
    and attendance_hours_distribution. (The KPI cards in attendance_kpi_data
    are day-scoped instead - see that function's own docstring.)
    """
    today = date.today()
    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end


def _missing_punches_employees(today=None):
    """
    Active employees who should already be at work today but haven't
    clocked in: their shift's scheduled start time for today has already
    passed, they're not on approved leave, and no AttendanceActivity
    (punch-in) row exists for them today.

    Employees with no shift assigned are skipped entirely -- there's no
    schedule to compare "has it started" against.
    """
    from attendance.models import AttendanceActivity
    from base.models import EmployeeShiftSchedule
    from employee.models import Employee
    from leave.models import LeaveRequest

    today = today or date.today()
    now_time = datetime.now().time()
    weekday = today.strftime("%A").lower()

    on_leave_ids = LeaveRequest.employees_on_leave_today(
        today=today, status="approved"
    ).values_list("employee_id", flat=True)
    checked_in_ids = AttendanceActivity.objects.filter(
        attendance_date=today
    ).values_list("employee_id", flat=True)

    candidates = (
        Employee.objects.filter(is_active=True)
        .exclude(id__in=on_leave_ids)
        .exclude(id__in=checked_in_ids)
        .select_related("employee_work_info__shift_id")
    )

    shift_ids = {
        emp.employee_work_info.shift_id_id
        for emp in candidates
        if getattr(emp, "employee_work_info", None)
        and emp.employee_work_info.shift_id_id
    }
    # One lookup for every shift's schedule on today's weekday, instead of a
    # query per candidate employee.
    schedules = {
        schedule.shift_id_id: schedule
        for schedule in EmployeeShiftSchedule.objects.filter(
            shift_id_id__in=shift_ids, day__day=weekday
        )
    }

    missing_ids = []
    for emp in candidates:
        work_info = getattr(emp, "employee_work_info", None)
        if not work_info or not work_info.shift_id_id:
            continue
        schedule = schedules.get(work_info.shift_id_id)
        if schedule and schedule.start_time and schedule.start_time <= now_time:
            missing_ids.append(emp.id)

    return Employee.objects.filter(id__in=missing_ids)


def _latest_attendance_date(reference_date=None):
    """Return the latest attendance_date that actually has records.

    Falls back to the given reference_date (or today) if no attendance exists at all,
    so callers can still execute their queries with a safe default.
    """
    from attendance.models import Attendance

    ref = reference_date or date.today()
    latest = (
        Attendance.objects.filter(attendance_date__lte=ref)
        .order_by("-attendance_date")
        .values_list("attendance_date", flat=True)
        .first()
    )
    return latest or ref


@login_required
@manager_can_enter("attendance.view_attendance")
def attendance_dashboard_view(request):
    """Render the modern attendance dashboard page."""
    return render(request, "attendance/dashboard.html")


@login_required
def attendance_kpi_data(request):
    """Return attendance KPI summary data as JSON.

    Every card here (Present Today, On Time, Late Arrival, Pending, OT
    Pending) is a real-time, current-day snapshot (attendance_date =
    today) - unlike the charts elsewhere in this file (Attendance Trend,
    Attendance Overview, Late Arrival & Early Departure, Hours
    Distribution), which are scoped to the whole current month via
    _current_month_bounds().
    """
    from attendance.filters import get_expected_to_check_in
    from attendance.models import Attendance, AttendanceLateComeEarlyOut
    from employee.models import Employee

    employees = Employee.objects.filter(is_active=True)
    total_employees = employees.count()

    # Deliberately NOT routed through _latest_attendance_date(): that
    # fallback would silently substitute an older date with data, so the
    # card's own label ("Present Today") and the date actually being
    # filtered/linked to would disagree - a 0 for today is a more honest
    # result than a non-zero count for some other day.
    today = date.today()

    # Everyone with an attendance row today, validated or not - matches the
    # main HR dashboard's definition (base/dashboard.py's dashboard_kpi_data)
    # and the card's own link, which has no attendance_validated filter.
    present_today = (
        Attendance.objects.filter(
            attendance_date=today,
            employee_id__is_active=True,
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    attendance_rate = (
        round((present_today / total_employees * 100), 1) if total_employees > 0 else 0
    )

    # Not scoped to attendance_validated=False: "On Time" below is
    # present_today minus late_come, so both sides need the same
    # validated+unvalidated scope or the subtraction undercounts lateness
    # and inflates "On Time".
    late_come = (
        AttendanceLateComeEarlyOut.objects.filter(
            type="late_come",
            attendance_id__attendance_date=today,
            employee_id__is_active=True,
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    early_out = (
        AttendanceLateComeEarlyOut.objects.filter(
            type="early_out",
            attendance_id__attendance_date=today,
            employee_id__is_active=True,
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    on_time = max(0, present_today - late_come)

    # Pending - employees still expected to check in today: reuses the
    # exact "expected to check in" rule the main HR dashboard's KPI and the
    # employee list filter already share (attendance/filters.py::
    # get_expected_to_check_in - active, not already present today, not on
    # approved leave today), so this card's count and its destination list
    # agree.
    expected_to_check_in = get_expected_to_check_in(
        employees, "expected_to_check_in", today
    ).count()

    # Pending overtime approval, for today's attendance only - same
    # reasoning as "On Time" above, matches the "OT Attendances" tab's own
    # active-employee scoping.
    pending_overtime = 0
    try:
        pending_overtime = Attendance.objects.filter(
            attendance_date=today,
            attendance_overtime_approve=False,
            attendance_validated=True,
            overtime_second__gt=0,
            employee_id__is_active=True,
        ).count()
    except Exception:
        pass

    # ids (not just the count) so the dashboard tile can link straight to
    # the Employee list pre-filtered to exactly these people via repeated
    # ?employee_id=<id> params (EmployeeFilter.employee_id, a
    # ModelMultipleChoiceFilter on id) instead of a dedicated page.
    missing_punches_ids = list(
        _missing_punches_employees(today).values_list("id", flat=True)
    )

    return JsonResponse(
        {
            "total_employees": total_employees,
            "present_today": present_today,
            "attendance_rate": attendance_rate,
            "on_time": on_time,
            "late_come": late_come,
            "early_out": early_out,
            "expected_to_check_in": expected_to_check_in,
            "pending_overtime": pending_overtime,
            "missing_punches": len(missing_punches_ids),
            "missing_punches_ids": missing_punches_ids,
            "date": today.isoformat(),
        }
    )


@login_required
def attendance_weekly_trend(request):
    """Attendance headcount for the current calendar month.

    Daily bars when span ≤ 14 days; otherwise aggregates by ISO week so the
    chart stays readable. Always scoped to the current month (first day to
    last day, via _current_month_bounds()) regardless of any from_date/
    to_date GET params, so it stays in step with the KPI cards above.
    """
    from attendance.models import Attendance

    from_date, to_date = _current_month_bounds()
    today = date.today()
    span = (to_date - from_date).days

    counts = {
        row["attendance_date"]: row["c"]
        for row in (
            Attendance.objects.filter(
                attendance_date__gte=from_date,
                attendance_date__lte=to_date,
                employee_id__is_active=True,
            )
            # Attendance's default ordering (-attendance_date, employee name,
            # clock_in) otherwise leaks into the GROUP BY below, splintering
            # each date into one group per employee instead of one total.
            .order_by()
            .values("attendance_date")
            .annotate(c=Count("employee_id", distinct=True))
        )
    }

    period_label = (
        f"{from_date.strftime('%b %d')} – {to_date.strftime('%b %d, %Y')}"
        if from_date.year == to_date.year
        else f"{from_date.strftime('%b %d, %Y')} – {to_date.strftime('%b %d, %Y')}"
    )

    if span <= 14:
        days = []
        d = from_date
        while d <= to_date:
            days.append(
                {
                    "day": d.strftime("%a"),
                    "date": d.isoformat(),
                    "count": counts.get(d, 0),
                    "is_today": d == today,
                }
            )
            d += timedelta(days=1)
        return JsonResponse(
            {
                "days": days,
                "aggregate": "daily",
                "week_start": from_date.isoformat(),
                "period_label": period_label,
            }
        )

    # Weekly aggregation
    days = []
    week_start = from_date - timedelta(days=from_date.weekday())  # Monday
    while week_start <= to_date:
        week_end = week_start + timedelta(days=6)
        bucket_total = 0
        d = max(week_start, from_date)
        last = min(week_end, to_date)
        contains_today = d <= today <= last
        while d <= last:
            bucket_total += counts.get(d, 0)
            d += timedelta(days=1)
        # Use the average daily headcount across the week to keep the y-axis
        # comparable to daily mode.
        bucket_days = (last - max(week_start, from_date)).days + 1
        avg = round(bucket_total / bucket_days) if bucket_days > 0 else 0
        label_start = max(week_start, from_date).strftime("%b %d")
        days.append(
            {
                "day": label_start,
                "date": max(week_start, from_date).isoformat(),
                "count": avg,
                "is_today": contains_today,
            }
        )
        week_start += timedelta(days=7)

    return JsonResponse(
        {
            "days": days,
            "aggregate": "weekly",
            "week_start": from_date.isoformat(),
            "period_label": period_label,
        }
    )


@login_required
def attendance_department_breakdown(request):
    """Attendance broken down by department for the selected date (to_date)."""
    from attendance.models import Attendance
    from employee.models import Employee

    _, to_date = _parse_period(request)
    today = _latest_attendance_date(to_date)
    departments = []

    try:
        dept_data = (
            Attendance.objects.filter(
                attendance_date=today,
                employee_id__is_active=True,
            )
            # Clear Attendance's default ordering before grouping -- see
            # attendance_weekly_trend for why it otherwise pollutes GROUP BY.
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(present=Count("employee_id", distinct=True))
            .order_by("-present")
        )

        for item in dept_data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if dept:
                total_in_dept = Employee.objects.filter(
                    is_active=True,
                    employee_work_info__department_id__department=dept,
                ).count()
                departments.append(
                    {
                        "department": dept,
                        "present": item["present"],
                        "total": total_in_dept,
                        "rate": (
                            round((item["present"] / total_in_dept * 100), 1)
                            if total_in_dept > 0
                            else 0
                        ),
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments, "date": today.isoformat()})


@login_required
def attendance_late_early_data(request):
    """Late come and early out breakdown by department for the current month."""
    from attendance.models import AttendanceLateComeEarlyOut

    month_start, month_end = _current_month_bounds()
    late_data = []
    early_data = []

    try:
        # Plain row count, not distinct-employee: AttendanceLateComeEarlyOut
        # is unique per (attendance, type) - see Attendance's own
        # unique_together - so over a month range this is total late-arrival
        # incidents in the department (per-department counts here sum to
        # the department total, unlike a distinct-employee dedup, which
        # would collapse an employee's multiple late days into one).
        late = (
            AttendanceLateComeEarlyOut.objects.filter(
                type="late_come",
                attendance_id__attendance_date__gte=month_start,
                attendance_id__attendance_date__lte=month_end,
            )
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        for item in late:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if dept:
                late_data.append({"department": dept, "count": item["count"]})

        early = (
            AttendanceLateComeEarlyOut.objects.filter(
                type="early_out",
                attendance_id__attendance_date__gte=month_start,
                attendance_id__attendance_date__lte=month_end,
            )
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        for item in early:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if dept:
                early_data.append({"department": dept, "count": item["count"]})
    except Exception:
        pass

    return JsonResponse(
        {
            "late_come": late_data,
            "early_out": early_data,
            "date": month_end.isoformat(),
            "from_date": month_start.isoformat(),
            "to_date": month_end.isoformat(),
            "month": month_end.strftime("%B %Y"),
        }
    )


@login_required
def attendance_overtime_summary(request):
    """Overtime summary by department for the current month."""
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    departments = []

    try:
        data = (
            Attendance.objects.filter(
                attendance_date__gte=first_of_month,
                attendance_date__lte=today,
                attendance_validated=True,
                overtime_second__gt=0,
            )
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(
                total_ot=Sum("overtime_second"),
                total_approved=Sum("approved_overtime_second"),
                count=Count("employee_id", distinct=True),
            )
            .order_by("-total_ot")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if dept:
                departments.append(
                    {
                        "department": dept,
                        "total_hours": round((item["total_ot"] or 0) / 3600, 1),
                        "approved_hours": round(
                            (item["total_approved"] or 0) / 3600, 1
                        ),
                        "employees": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse(
        {
            "departments": departments,
            "month": today.strftime("%B %Y"),
            "from_date": first_of_month.isoformat(),
            "to_date": today.isoformat(),
        }
    )


@login_required
def attendance_hours_distribution(request):
    """Worked hours vs pending hours by department for the current month."""
    from attendance.models import Attendance, AttendanceOverTime

    month_start, month_end = _current_month_bounds()
    departments = []

    try:
        # Worked hours: Attendance has an attendance_date, so bound directly
        # to the current month. One grouped query for every department
        # instead of one query per department.
        worked_by_dept = {
            row["employee_id__employee_work_info__department_id__department"]: (
                row["total"] or 0
            )
            for row in (
                Attendance.objects.filter(
                    employee_id__is_active=True,
                    attendance_date__gte=month_start,
                    attendance_date__lte=month_end,
                )
                .order_by()
                .values("employee_id__employee_work_info__department_id__department")
                .annotate(total=Sum("at_work_second"))
            )
        }

        # Pending hours: AttendanceOverTime (the "hour account") has no
        # attendance_date - it's keyed by its own month/year accounting
        # period instead, so that's the field to bound to the current
        # month rather than attendance_date. filter=Q(...) on the Sum
        # ignores negative hour_pending_second rows, same as the previous
        # per-row max(value, 0) clamp before summing.
        pending_by_dept = {
            row["employee_id__employee_work_info__department_id__department"]: (
                row["total"] or 0
            )
            for row in (
                AttendanceOverTime.objects.filter(
                    employee_id__is_active=True,
                    month=month_start.strftime("%B").lower(),
                    year=str(month_start.year),
                )
                .order_by()
                .values("employee_id__employee_work_info__department_id__department")
                .annotate(
                    total=Sum(
                        "hour_pending_second",
                        filter=Q(hour_pending_second__gt=0),
                    )
                )
            )
        }

        for dept in set(worked_by_dept) | set(pending_by_dept):
            if not dept:
                continue
            worked_seconds = max(worked_by_dept.get(dept, 0), 0)
            pending_seconds = max(pending_by_dept.get(dept, 0), 0)
            if worked_seconds == 0 and pending_seconds == 0:
                continue
            departments.append(
                {
                    "department": dept,
                    "worked_hours": round(worked_seconds / 3600, 1),
                    "pending_hours": round(pending_seconds / 3600, 1),
                }
            )

        departments.sort(key=lambda x: x["worked_hours"], reverse=True)
    except Exception:
        pass

    return JsonResponse({"departments": departments[:10]})


@login_required
def attendance_shift_distribution(request):
    """Employee distribution by shift type."""
    from employee.models import Employee

    shifts = []

    try:
        data = (
            Employee.objects.filter(is_active=True)
            .exclude(employee_work_info__shift_id__isnull=True)
            .values(
                "employee_work_info__shift_id",
                "employee_work_info__shift_id__employee_shift",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            shift = item["employee_work_info__shift_id__employee_shift"]
            shift_id = item["employee_work_info__shift_id"]
            if shift:
                shifts.append(
                    {"shift": shift, "shift_id": shift_id, "count": item["count"]}
                )
    except Exception:
        pass

    return JsonResponse({"shifts": shifts})


@login_required
def attendance_absenteeism_trend(request):
    """Monthly absenteeism rate for the last 6 months.

    "Expected" days excludes weekends, days before an employee's joining
    date, approved leave, and company-wide holidays -- otherwise every
    approved leave/holiday gets miscounted as an absence and the rate is
    structurally overstated regardless of how complete attendance data is.
    """
    from attendance.models import Attendance
    from base.models import Holidays
    from employee.models import Employee
    from leave.methods import holiday_dates_list
    from leave.models import LeaveRequest

    _, to_date = _parse_period(request)
    today = to_date
    months = []

    try:
        current_month_start = today.replace(day=1)

        # Trailing-6-month window bounds, so holidays/leaves/employees are
        # each fetched once instead of once per month.
        year = current_month_start.year
        month = current_month_start.month - 5
        while month <= 0:
            month += 12
            year -= 1
        window_start = date(year, month, 1)

        employees = list(
            Employee.objects.filter(is_active=True).values(
                "id", "employee_work_info__date_joining"
            )
        )

        holiday_dates = set(
            holiday_dates_list(
                Holidays.objects.filter(
                    start_date__lte=today,
                    end_date__gte=window_start,
                    is_specific=False,
                )
            )
        )

        leaves_by_employee = {}
        for leave in LeaveRequest.objects.filter(
            status="approved",
            start_date__lte=today,
            end_date__gte=window_start,
        ).values("employee_id", "start_date", "end_date"):
            leaves_by_employee.setdefault(leave["employee_id"], []).append(
                (leave["start_date"], leave["end_date"] or leave["start_date"])
            )

        for i in range(5, -1, -1):
            # Step back i full months using year/month arithmetic (no day drift)
            year = current_month_start.year
            month = current_month_start.month - i
            while month <= 0:
                month += 12
                year -= 1
            month_start = date(year, month, 1)
            if month == 12:
                month_end = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(year, month + 1, 1) - timedelta(days=1)
            month_end = min(month_end, today)

            # Working days (Mon-Fri, non-holiday) in the month
            working_dates = []
            d = month_start
            while d <= month_end:
                if d.weekday() < 5 and d not in holiday_dates:
                    working_dates.append(d)
                d += timedelta(days=1)

            if not working_dates or not employees:
                months.append({"month": month_start.strftime("%b %Y"), "rate": 0})
                continue

            # Expected days: each employee's working days in the month,
            # minus days before they joined and days covered by approved leave.
            expected_days = 0
            for emp in employees:
                join_date = emp["employee_work_info__date_joining"]
                emp_leaves = leaves_by_employee.get(emp["id"], [])
                for d in working_dates:
                    if join_date and d < join_date:
                        continue
                    if any(start <= d <= end for start, end in emp_leaves):
                        continue
                    expected_days += 1

            # Count unique employee-days with attendance
            present_days = (
                Attendance.objects.filter(
                    attendance_date__gte=month_start,
                    attendance_date__lte=month_end,
                    employee_id__is_active=True,
                )
                .values("employee_id", "attendance_date")
                .distinct()
                .count()
            )

            absent_days = max(0, expected_days - present_days)
            absenteeism_rate = (
                round((absent_days / expected_days * 100), 1) if expected_days else 0
            )

            months.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "rate": absenteeism_rate,
                    "absent_days": absent_days,
                    "expected_days": expected_days,
                }
            )
    except Exception:
        months = [{"month": f"M{i+1}", "rate": 0} for i in range(6)]

    return JsonResponse({"months": months})


@login_required
def attendance_work_type_distribution(request):
    """Employee distribution by work type (remote, on-site, hybrid, etc.)."""
    from employee.models import Employee

    work_types = []

    try:
        data = (
            Employee.objects.filter(is_active=True)
            .exclude(employee_work_info__work_type_id__isnull=True)
            .values(
                "employee_work_info__work_type_id",
                "employee_work_info__work_type_id__work_type",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            wt = item["employee_work_info__work_type_id__work_type"]
            wt_id = item["employee_work_info__work_type_id"]
            if wt:
                work_types.append(
                    {"work_type": wt, "work_type_id": wt_id, "count": item["count"]}
                )

        # Count employees with no work type assigned
        no_wt = Employee.objects.filter(
            is_active=True,
            employee_work_info__work_type_id__isnull=True,
        ).count()
        if no_wt > 0:
            work_types.append(
                {"work_type": _("Not Assigned"), "work_type_id": None, "count": no_wt}
            )
    except Exception:
        pass

    return JsonResponse({"work_types": work_types})


@login_required
def attendance_avg_working_hours(request):
    """Average working hours per department for the current month."""
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    departments = []

    try:
        data = (
            Attendance.objects.filter(
                attendance_date__gte=first_of_month,
                attendance_date__lte=today,
                at_work_second__gt=0,
            )
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(
                total_seconds=Sum("at_work_second"),
                att_count=Count("id"),
                emp_count=Count("employee_id", distinct=True),
            )
            .order_by("-total_seconds")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if not dept:
                continue
            total_hrs = (item["total_seconds"] or 0) / 3600
            avg_per_day = (
                round(total_hrs / item["att_count"], 1) if item["att_count"] > 0 else 0
            )
            departments.append(
                {
                    "department": dept,
                    "avg_hours_per_day": avg_per_day,
                    "total_hours": round(total_hrs, 1),
                    "employees": item["emp_count"],
                }
            )

        departments.sort(key=lambda x: x["avg_hours_per_day"], reverse=True)
    except Exception:
        pass

    return JsonResponse(
        {
            "departments": departments[:10],
            "month": today.strftime("%B %Y"),
            "from_date": first_of_month.isoformat(),
            "to_date": today.isoformat(),
        }
    )


@login_required
def attendance_top_absentees(request):
    """Top 10 employees with most absences in the current month."""
    from attendance.models import Attendance
    from employee.models import Employee

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    absentees = []

    try:
        # Count working days so far this month
        working_days = 0
        d = first_of_month
        while d <= today:
            if d.weekday() < 5:
                working_days += 1
            d += timedelta(days=1)

        if working_days == 0:
            return JsonResponse({"absentees": []})

        employees = Employee.objects.filter(is_active=True)

        for emp in employees:
            present_days = (
                Attendance.objects.filter(
                    employee_id=emp,
                    attendance_date__gte=first_of_month,
                    attendance_date__lte=today,
                )
                .values("attendance_date")
                .distinct()
                .count()
            )

            absent_days = max(0, working_days - present_days)
            if absent_days > 0:
                absentees.append(
                    {
                        "id": emp.id,
                        "name": emp.get_full_name(),
                        "avatar": emp.get_avatar(),
                        "absent_days": absent_days,
                        "present_days": present_days,
                        "total_days": working_days,
                        "rate": round((absent_days / working_days * 100), 1),
                    }
                )

        absentees.sort(key=lambda x: x["absent_days"], reverse=True)
    except Exception:
        pass

    return JsonResponse(
        {
            "absentees": absentees[:10],
            "month": today.strftime("%B %Y"),
        }
    )


@login_required
def attendance_clockin_distribution(request):
    """Distribution of clock-in times for today (or latest day with records)."""
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    target_date = _latest_attendance_date(to_date)
    buckets = {}
    try:
        qs = Attendance.objects.filter(
            attendance_date=target_date, attendance_clock_in__isnull=False
        )
        for att in qs:
            hour = att.attendance_clock_in.hour
            label = f"{hour:02d}:00"
            buckets[label] = buckets.get(label, 0) + 1
    except Exception:
        pass
    sorted_buckets = sorted(buckets.items())
    return JsonResponse(
        {
            "hours": [b[0] for b in sorted_buckets],
            "counts": [b[1] for b in sorted_buckets],
            "date": target_date.isoformat(),
        }
    )


@login_required
def attendance_calendar_heatmap(request):
    """Attendance rate per day (or per ISO week for longer ranges).

    For ≤ 31 days the chart shows one bar per day. Beyond that, daily bars
    cram together — so we aggregate to one bar per ISO week and use the
    week's average rate.
    """
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    span = (to_date - from_date).days
    days = []
    aggregate = "daily"
    try:
        from employee.models import Employee

        total = Employee.objects.filter(is_active=True).count()
        counts = {
            row["attendance_date"]: row["c"]
            for row in (
                Attendance.objects.filter(
                    attendance_date__gte=from_date,
                    attendance_date__lte=to_date,
                    employee_id__is_active=True,
                )
                .order_by()
                .values("attendance_date")
                .annotate(c=Count("employee_id", distinct=True))
            )
        }

        if span <= 31:
            d = from_date
            while d <= to_date:
                c = counts.get(d, 0)
                rate = round((c / total * 100), 1) if total > 0 else 0
                days.append(
                    {
                        "date": d.isoformat(),
                        "day": d.strftime("%a"),
                        "dom": d.day,
                        "label": (
                            d.strftime("%b %d")
                            if from_date.month != to_date.month
                            else d.day
                        ),
                        "count": c,
                        "rate": rate,
                    }
                )
                d += timedelta(days=1)
        else:
            aggregate = "weekly"
            week_start = from_date - timedelta(days=from_date.weekday())  # Monday
            while week_start <= to_date:
                week_end = week_start + timedelta(days=6)
                actual_start = max(week_start, from_date)
                actual_end = min(week_end, to_date)
                rates = []
                bucket_total = 0
                d = actual_start
                while d <= actual_end:
                    c = counts.get(d, 0)
                    bucket_total += c
                    if total > 0:
                        rates.append((c / total) * 100)
                    d += timedelta(days=1)
                avg_rate = round(sum(rates) / len(rates), 1) if rates else 0
                bucket_days = (actual_end - actual_start).days + 1
                avg_count = round(bucket_total / bucket_days) if bucket_days > 0 else 0
                days.append(
                    {
                        "date": actual_start.isoformat(),
                        "day": actual_start.strftime("%b %d"),
                        "dom": actual_start.day,
                        "label": actual_start.strftime("%b %d"),
                        "count": avg_count,
                        "rate": avg_rate,
                    }
                )
                week_start += timedelta(days=7)
    except Exception:
        pass

    if from_date.year == to_date.year and from_date.month == to_date.month:
        period_label = from_date.strftime("%B %Y")
    elif from_date.year == to_date.year:
        period_label = (
            f"{from_date.strftime('%b %d')} – {to_date.strftime('%b %d, %Y')}"
        )
    else:
        period_label = (
            f"{from_date.strftime('%b %d, %Y')} – {to_date.strftime('%b %d, %Y')}"
        )

    return JsonResponse(
        {
            "days": days,
            "month": period_label,
            "aggregate": aggregate,
            "period_label": period_label,
        }
    )


@login_required
def attendance_overview(request):
    """Department-wise on-time / late / early counts for the current month.

    One grouped query per metric (present/late/early) instead of the
    original per-department loop, so the query count stays constant no
    matter how many departments exist.
    """
    from attendance.models import Attendance, AttendanceLateComeEarlyOut

    month_start, month_end = _current_month_bounds()

    labels = []
    on_time_series = []
    late_series = []
    early_series = []

    try:
        dept_field = "employee_id__employee_work_info__department_id__department"

        present_by_dept = {
            row[dept_field]: row["c"]
            for row in (
                Attendance.objects.filter(
                    attendance_date__gte=month_start,
                    attendance_date__lte=month_end,
                    employee_id__is_active=True,
                )
                .order_by()
                .values(dept_field)
                .annotate(c=Count("id"))
            )
        }
        late_by_dept = {
            row[dept_field]: row["c"]
            for row in (
                AttendanceLateComeEarlyOut.objects.filter(
                    type="late_come",
                    attendance_id__attendance_date__gte=month_start,
                    attendance_id__attendance_date__lte=month_end,
                    employee_id__is_active=True,
                )
                .order_by()
                .values(dept_field)
                .annotate(c=Count("id"))
            )
        }
        early_by_dept = {
            row[dept_field]: row["c"]
            for row in (
                AttendanceLateComeEarlyOut.objects.filter(
                    type="early_out",
                    attendance_id__attendance_date__gte=month_start,
                    attendance_id__attendance_date__lte=month_end,
                    employee_id__is_active=True,
                )
                .order_by()
                .values(dept_field)
                .annotate(c=Count("id"))
            )
        }

        for dept, present_count in sorted(
            present_by_dept.items(), key=lambda kv: kv[1], reverse=True
        ):
            if not dept or not present_count:
                continue
            late_count = late_by_dept.get(dept, 0)
            early_count = early_by_dept.get(dept, 0)
            labels.append(dept)
            on_time_series.append(max(0, present_count - late_count))
            late_series.append(late_count)
            early_series.append(early_count)
    except Exception:
        pass

    data_set = [
        {"label": _("On Time"), "data": on_time_series},
        {"label": _("Late Arrival"), "data": late_series},
        {"label": _("Early Departure"), "data": early_series},
    ]
    return JsonResponse(
        {
            "dataSet": data_set,
            "labels": labels,
            "date": month_end.isoformat(),
            "from_date": month_start.isoformat(),
            "to_date": month_end.isoformat(),
            "month": month_end.strftime("%B %Y"),
        }
    )
