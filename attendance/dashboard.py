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
from base.models import Department, EmployeeShift, WorkType


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to current month."""
    today = date.today()
    month_start, month_end = _current_month_bounds()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = date.fromisoformat(from_str) if from_str else month_start
    except (ValueError, TypeError):
        from_date = month_start
    try:
        to_date = date.fromisoformat(to_str) if to_str else month_end
    except (ValueError, TypeError):
        to_date = month_end
    if to_date < from_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _period_label(from_date, to_date):
    """Human label for a period: "October 2026" for a single month, else a range."""
    if from_date.year == to_date.year and from_date.month == to_date.month:
        return from_date.strftime("%B %Y")
    if from_date == to_date:
        return from_date.strftime("%b %d, %Y")
    return f"{from_date.strftime('%b %d, %Y')} – {to_date.strftime('%b %d, %Y')}"


def _current_month_bounds():
    """First and last calendar day of the current month (server "today").

    Default period for the charts when the dashboard's from/to period
    picker sends no dates. (The KPI cards in attendance_kpi_data are
    day-scoped instead - see that function's own docstring.)
    """
    today = date.today()
    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end


def _missing_punches_employees(today=None, employee_ids=None):
    """
    Active employees who should already be at work today but haven't
    clocked in: their shift's scheduled start time for today has already
    passed, they're not on approved leave, and no AttendanceActivity
    (punch-in) row exists for them today.

    Employees with no shift assigned are skipped entirely -- there's no
    schedule to compare "has it started" against.

    `employee_ids`, when given (e.g. a manager's team-scoped id list from
    base.dashboard._scoped_active_employee_ids), restricts the candidates
    to that set -- shared with the main HR dashboard's own Offline KPI so
    both cards agree on both definition and scope.
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
    if employee_ids is not None:
        candidates = candidates.filter(id__in=employee_ids)

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


def _scoped_employees(request):
    """Active employees, restricted to a reporting manager's subordinates
    when they lack attendance.view_attendance; unrestricted otherwise."""
    from base.methods import filtersubordinatesemployeemodel
    from employee.models import Employee

    employees = Employee.objects.filter(is_active=True)
    return filtersubordinatesemployeemodel(
        request, employees, perm="attendance.view_attendance"
    )


@login_required
@manager_can_enter("attendance.view_attendance")
def attendance_dashboard_view(request):
    """Render the modern attendance dashboard page."""
    return render(request, "attendance/dashboard.html")


@login_required
def attendance_kpi_data(request):
    """Return attendance KPI summary data as JSON.

    Every card here (Checked In Today, On Time, Late Arrival, Not Checked
    In Today, OT Pending) is a real-time, current-day snapshot
    (attendance_date = today) - unlike the charts elsewhere in this file,
    which follow the dashboard's from/to period picker via _parse_period().
    """
    from attendance.filters import get_expected_to_check_in
    from attendance.models import Attendance, AttendanceLateComeEarlyOut

    employees = _scoped_employees(request)
    total_employees = employees.count()

    # Strictly today's date, with no fallback to an older day that has data:
    # the card's own label ("Checked In Today") and the date actually being
    # filtered/linked to must agree - a 0 for today is a more honest result
    # than a non-zero count for some other day.
    today = date.today()

    # Everyone with an attendance row today, validated or not - matches the
    # main HR dashboard's definition (base/dashboard.py's dashboard_kpi_data)
    # and the card's own link, which has no attendance_validated filter.
    present_today = (
        Attendance.objects.filter(
            attendance_date=today,
            employee_id__is_active=True,
            employee_id__in=employees,
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
            employee_id__in=employees,
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
            employee_id__in=employees,
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    on_time = max(0, present_today - late_come)

    # Not Checked In Today - employees still expected to check in today: reuses the
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
            employee_id__in=employees,
        ).count()
    except Exception:
        pass

    # ids (not just the count) so the dashboard tile can link straight to
    # the Employee list pre-filtered to exactly these people via repeated
    # ?employee_id=<id> params (EmployeeFilter.employee_id, a
    # ModelMultipleChoiceFilter on id) instead of a dedicated page.
    missing_punches_ids = list(
        _missing_punches_employees(today, employee_ids=employees).values_list(
            "id", flat=True
        )
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
def attendance_late_early_data(request):
    """Late come and early out breakdown by department for the current month."""
    from attendance.models import AttendanceLateComeEarlyOut

    month_start, month_end = _parse_period(request)
    late_data = []
    early_data = []
    employees = _scoped_employees(request)

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
                employee_id__in=employees,
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
                employee_id__in=employees,
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
            "month": _period_label(month_start, month_end),
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
    employees = _scoped_employees(request)

    try:
        data = (
            Attendance.objects.filter(
                attendance_date__gte=first_of_month,
                attendance_date__lte=today,
                attendance_validated=True,
                overtime_second__gt=0,
                employee_id__in=employees,
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
                        "pending_hours": round(
                            max(
                                (item["total_ot"] or 0) - (item["total_approved"] or 0),
                                0,
                            )
                            / 3600,
                            1,
                        ),
                        "employees": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse(
        {
            "departments": departments,
            "month": _period_label(first_of_month, today),
            "from_date": first_of_month.isoformat(),
            "to_date": today.isoformat(),
        }
    )


@login_required
def attendance_hours_distribution(request):
    """Pending hours and employees with pending hours, by department, for the selected period.

    Pending hours come from AttendanceOverTime (the "hour account"), which has
    no attendance_date - it's keyed by its own month/year accounting period,
    so the months overlapping the period bound it. Counts distinct employees
    whose pending balance is positive.
    """
    from attendance.models import AttendanceOverTime

    month_start, month_end = _parse_period(request)
    periods = []
    y, m = month_start.year, month_start.month
    while (y, m) <= (month_end.year, month_end.month):
        periods.append((calendar.month_name[m].lower(), str(y)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    period_q = Q()
    for month_name, year in periods:
        period_q |= Q(month=month_name, year=year)
    departments = []
    employees = _scoped_employees(request)

    try:
        rows = (
            AttendanceOverTime.objects.filter(
                employee_id__is_active=True,
                employee_id__in=employees,
                hour_pending_second__gt=0,
            )
            .filter(period_q)
            .order_by()
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(
                pending_employees=Count("employee_id", distinct=True),
                pending_total=Sum("hour_pending_second"),
            )
            .order_by("-pending_total")
        )
        for row in rows:
            dept = row["employee_id__employee_work_info__department_id__department"]
            if dept:
                departments.append(
                    {
                        "department": dept,
                        "pending_employees": row["pending_employees"],
                        "pending_hours": round((row["pending_total"] or 0) / 3600, 1),
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments[:10]})


def _group_attendance_stats(request, group_field):
    """Expected vs. attended employee-days per group, current month so far.

    `group_field` is an Employee lookup (department / shift / work type name).
    "Expected" days exclude weekends, days before an employee's joining date,
    approved leave, and company-wide holidays -- otherwise every approved
    leave/holiday gets miscounted as an absence. Absence is clamped at zero
    per employee (attendance recorded on a non-working day can't offset
    someone else's absence). Returns {group: {"expected": int, "absent": int}}
    for groups with at least one expected day.
    """
    from attendance.models import Attendance
    from base.models import Holidays
    from leave.methods import holiday_dates_list
    from leave.models import LeaveRequest

    month_start, month_end = _parse_period(request)
    month_end = min(month_end, date.today())

    employees = _scoped_employees(request)
    rows = list(employees.values("id", "employee_work_info__date_joining", group_field))
    if not rows:
        return {}

    holiday_dates = set(
        holiday_dates_list(
            Holidays.objects.filter(
                start_date__lte=month_end,
                end_date__gte=month_start,
                is_specific=False,
            )
        )
    )
    working_dates = []
    d = month_start
    while d <= month_end:
        if d.weekday() < 5 and d not in holiday_dates:
            working_dates.append(d)
        d += timedelta(days=1)
    if not working_dates:
        return {}

    leave_days = {}
    for leave in LeaveRequest.objects.filter(
        status="approved",
        employee_id__in=employees,
        start_date__lte=month_end,
        end_date__gte=month_start,
    ).values("employee_id", "start_date", "end_date"):
        start, end = leave["start_date"], leave["end_date"] or leave["start_date"]
        leave_days.setdefault(leave["employee_id"], set()).update(
            d for d in working_dates if start <= d <= end
        )

    present_by_employee = {
        row["employee_id"]: row["days"]
        for row in (
            Attendance.objects.filter(
                attendance_date__gte=month_start,
                attendance_date__lte=month_end,
                employee_id__is_active=True,
                employee_id__in=employees,
            )
            .order_by()
            .values("employee_id")
            .annotate(days=Count("attendance_date", distinct=True))
        )
    }

    stats = {}
    for emp in rows:
        group = emp[group_field]
        if not group:
            continue
        join_date = emp["employee_work_info__date_joining"]
        on_leave = leave_days.get(emp["id"], set())
        expected = sum(
            1
            for d in working_dates
            if (not join_date or d >= join_date) and d not in on_leave
        )
        absent = max(0, expected - present_by_employee.get(emp["id"], 0))
        bucket = stats.setdefault(group, {"expected": 0, "absent": 0})
        bucket["expected"] += expected
        bucket["absent"] += absent

    return {g: v for g, v in stats.items() if v["expected"] > 0}


def _group_rate_payload(request, stats, label_key, rate_of):
    month_start, month_end = _parse_period(request)
    items = []
    for group, v in stats.items():
        absent_pct = round(v["absent"] / v["expected"] * 100, 1)
        items.append(
            {
                label_key: group,
                "rate": rate_of(absent_pct),
                "absent_days": v["absent"],
                "present_days": v["expected"] - v["absent"],
                "expected_days": v["expected"],
            }
        )
    return items, {
        "month": _period_label(month_start, month_end),
        "from_date": month_start.isoformat(),
        "to_date": month_end.isoformat(),
    }


ATTENDANCE_DIMENSIONS = {
    "shift": "employee_work_info__shift_id__employee_shift",
    "department": "employee_work_info__department_id__department",
    "work_type": "employee_work_info__work_type_id__work_type",
}


ATTENDANCE_DIMENSION_MODELS = {
    "shift": (EmployeeShift, "employee_shift"),
    "department": (Department, "department"),
    "work_type": (WorkType, "work_type"),
}


def _rate_by_dimension(request, rate_of):
    """Shared body of the Attendance % / Absence % endpoints.

    Both use _group_attendance_stats, so date scope, leave / holiday
    handling and employee scoping are identical. `rate_of` maps the absence
    percentage to the rate being charted; groups are returned highest first.
    """
    dimension = request.GET.get("dimension", "shift")
    group_field = ATTENDANCE_DIMENSIONS.get(dimension)
    if group_field is None:
        return JsonResponse({"error": "invalid dimension"}, status=400)

    items = []
    meta = {}
    try:
        stats = _group_attendance_stats(request, group_field)
        items, meta = _group_rate_payload(request, stats, "label", rate_of)
        items.sort(key=lambda x: x["rate"], reverse=True)
        # Ids let the chart redirect to the attendance list filtered on the group.
        model, name_field = ATTENDANCE_DIMENSION_MODELS[dimension]
        ids = dict(
            model.objects.filter(
                **{f"{name_field}__in": [i["label"] for i in items]}
            ).values_list(name_field, "id")
        )
        for item in items:
            item["id"] = ids.get(item["label"])
    except Exception:
        pass
    return JsonResponse({"dimension": dimension, "items": items, **meta})


@login_required
def attendance_percentage_by_dimension(request):
    """Attendance rate (%) for the current month, grouped by ?dimension=
    (shift | department | work_type; default shift)."""
    return _rate_by_dimension(request, lambda pct: round(100 - pct, 1))


@login_required
def absence_percentage_by_dimension(request):
    """Absence rate (%) for the current month, grouped by ?dimension=
    (shift | department | work_type; default shift)."""
    return _rate_by_dimension(request, lambda pct: pct)


@login_required
def attendance_avg_working_hours(request):
    """Average working hours per department for the current month."""
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    departments = []
    employees = _scoped_employees(request)

    try:
        data = (
            Attendance.objects.filter(
                attendance_date__gte=first_of_month,
                attendance_date__lte=today,
                at_work_second__gt=0,
                employee_id__in=employees,
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
            "month": _period_label(first_of_month, today),
            "from_date": first_of_month.isoformat(),
            "to_date": today.isoformat(),
        }
    )


@login_required
def attendance_top_absentees(request):
    """Top 10 employees with most absences in the current month."""
    from attendance.models import Attendance

    from_date, to_date = _parse_period(request)
    today = min(to_date, date.today())
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

        employees = _scoped_employees(request)

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
            "month": _period_label(first_of_month, today),
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
        employees = _scoped_employees(request)
        total = employees.count()
        counts = {
            row["attendance_date"]: row["c"]
            for row in (
                Attendance.objects.filter(
                    attendance_date__gte=from_date,
                    attendance_date__lte=to_date,
                    attendance_validated=True,
                    employee_id__is_active=True,
                    employee_id__in=employees,
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
                        "from_date": d.isoformat(),
                        "to_date": d.isoformat(),
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
                        "from_date": actual_start.isoformat(),
                        "to_date": actual_end.isoformat(),
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

    month_start, month_end = _parse_period(request)

    labels = []
    on_time_series = []
    late_series = []
    early_series = []

    try:
        dept_field = "employee_id__employee_work_info__department_id__department"
        employees = _scoped_employees(request)

        present_by_dept = {
            row[dept_field]: row["c"]
            for row in (
                Attendance.objects.filter(
                    attendance_date__gte=month_start,
                    attendance_date__lte=month_end,
                    employee_id__is_active=True,
                    employee_id__in=employees,
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
                    employee_id__in=employees,
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
                    employee_id__in=employees,
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
            "month": _period_label(month_start, month_end),
        }
    )
