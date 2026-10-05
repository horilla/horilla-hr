"""
Modern employee dashboard views — KPI summary + ApexCharts.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _


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


@login_required
def employee_dashboard_view(request):
    return render(request, "employee/dashboard.html")


@login_required
def employee_kpi_data(request):
    from employee.models import Employee

    today = date.today()
    from_date, to_date = _parse_period(request)

    total = Employee.objects.count()
    active = Employee.objects.filter(is_active=True).count()
    inactive = total - active

    new_this_month = Employee.objects.filter(
        employee_work_info__date_joining__gte=from_date,
        employee_work_info__date_joining__lte=to_date,
    ).count()

    on_leave = 0
    try:
        from django.apps import apps

        if apps.is_installed("leave"):
            from leave.models import LeaveRequest

            on_leave = LeaveRequest.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                status="approved",
            ).count()
    except Exception:
        pass

    return JsonResponse(
        {
            "total": total,
            "active": active,
            "inactive": inactive,
            "new_this_month": new_this_month,
            "on_leave": on_leave,
            "active_pct": round(active / total * 100, 1) if total else 0,
        }
    )


@login_required
def employee_by_department(request):
    from employee.models import EmployeeWorkInformation

    data = (
        EmployeeWorkInformation.objects.filter(
            employee_id__is_active=True,
            department_id__isnull=False,
        )
        .values("department_id", "department_id__department")
        .annotate(count=Count("employee_id"))
        .order_by("-count")[:12]
    )

    departments = [
        {
            "id": item["department_id"],
            "department": item["department_id__department"],
            "count": item["count"],
        }
        for item in data
    ]
    return JsonResponse({"departments": departments})


@login_required
def employee_by_gender(request):
    from collections import Counter

    from employee.models import Employee

    gender_list = Employee.objects.filter(is_active=True).values_list(
        "gender", flat=True
    )
    counts = Counter(gender_list)
    gender_labels = {"male": _("Male"), "female": _("Female"), "other": _("Other")}
    genders = [
        {"gender": g, "label": gender_labels.get(g, g or _("Unknown")), "count": c}
        for g, c in counts.items()
        if c > 0 and g
    ]
    genders.sort(key=lambda x: -x["count"])
    return JsonResponse({"genders": genders})


@login_required
def employee_by_type(request):
    from employee.models import EmployeeWorkInformation

    data = (
        EmployeeWorkInformation.objects.filter(
            employee_id__is_active=True,
            employee_type_id__isnull=False,
        )
        .values("employee_type_id", "employee_type_id__employee_type")
        .annotate(count=Count("employee_id"))
        .order_by("-count")
    )

    types = [
        {
            "id": item["employee_type_id"],
            "type": item["employee_type_id__employee_type"],
            "count": item["count"],
        }
        for item in data
    ]
    return JsonResponse({"types": types})


@login_required
def employee_by_job_position(request):
    from employee.models import EmployeeWorkInformation

    data = (
        EmployeeWorkInformation.objects.filter(
            employee_id__is_active=True,
            job_position_id__isnull=False,
        )
        .values("job_position_id", "job_position_id__job_position")
        .annotate(count=Count("employee_id"))
        .order_by("-count")[:10]
    )

    positions = [
        {
            "id": item["job_position_id"],
            "position": item["job_position_id__job_position"],
            "count": item["count"],
        }
        for item in data
    ]
    return JsonResponse({"positions": positions})


@login_required
def employee_attendance_by_shift(request):
    from attendance.models import Attendance

    month_start = date.today().replace(day=1)
    rows = (
        Attendance.objects.filter(
            attendance_date__gte=month_start,
            attendance_date__lte=date.today(),
            employee_id__is_active=True,
            employee_id__employee_work_info__shift_id__isnull=False,
        )
        .order_by()
        .values(
            "employee_id__employee_work_info__shift_id",
            "employee_id__employee_work_info__shift_id__employee_shift",
        )
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    shifts = [
        {
            "id": r["employee_id__employee_work_info__shift_id"],
            "shift": r["employee_id__employee_work_info__shift_id__employee_shift"],
            "count": r["count"],
        }
        for r in rows
    ]
    return JsonResponse({"shifts": shifts, "month": month_start.strftime("%B %Y")})


@login_required
def employee_attendance_by_work_type(request):
    from attendance.models import Attendance

    month_start = date.today().replace(day=1)
    rows = (
        Attendance.objects.filter(
            attendance_date__gte=month_start,
            attendance_date__lte=date.today(),
            employee_id__is_active=True,
            employee_id__employee_work_info__work_type_id__isnull=False,
        )
        .order_by()
        .values(
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__work_type_id__work_type",
        )
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    work_types = [
        {
            "id": r["employee_id__employee_work_info__work_type_id"],
            "work_type": r["employee_id__employee_work_info__work_type_id__work_type"],
            "count": r["count"],
        }
        for r in rows
    ]
    return JsonResponse(
        {"work_types": work_types, "month": month_start.strftime("%B %Y")}
    )


def _month_offset(d, months_back):
    """Return the first day of the month that is `months_back` months before d."""
    year = d.year
    month = d.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


@login_required
def employee_joining_trend(request):
    from employee.models import EmployeeWorkInformation

    today = date.today()
    months = []
    for i in range(5, -1, -1):
        month_date = _month_offset(today, i)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1)
        month_end = next_month - timedelta(days=1)

        count = EmployeeWorkInformation.objects.filter(
            date_joining__gte=month_date,
            date_joining__lte=month_end,
        ).count()

        months.append({"month": month_date.strftime("%b %Y"), "count": count})

    return JsonResponse({"months": months})


@login_required
def employee_headcount_trend(request):
    from employee.models import EmployeeWorkInformation

    today = date.today()
    months = []
    for i in range(5, -1, -1):
        month_date = _month_offset(today, i)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1)
        month_end = next_month - timedelta(days=1)

        count = EmployeeWorkInformation.objects.filter(
            employee_id__is_active=True,
            date_joining__lte=month_end,
        ).count()

        months.append({"month": month_date.strftime("%b %Y"), "count": count})

    return JsonResponse({"months": months})


@login_required
def employee_recent_list(request):
    from employee.models import Employee

    qs = (
        Employee.objects.filter(is_active=True)
        .select_related(
            "employee_work_info__department_id", "employee_work_info__job_position_id"
        )
        .order_by("-id")[:12]
    )

    employees = []
    for emp in qs:
        wi = getattr(emp, "employee_work_info", None)
        employees.append(
            {
                "id": emp.id,
                "name": emp.get_full_name(),
                "avatar": emp.get_avatar(),
                "department": (
                    wi.department_id.department if wi and wi.department_id else "—"
                ),
                "position": (
                    wi.job_position_id.job_position
                    if wi and wi.job_position_id
                    else "—"
                ),
                "date_joining": (
                    wi.date_joining.strftime("%d %b %Y")
                    if wi and wi.date_joining
                    else "—"
                ),
            }
        )

    return JsonResponse({"employees": employees})


@login_required
def employee_upcoming_birthdays(request):
    from employee.models import Employee

    today = date.today()
    window_end = today + timedelta(days=30)

    birthdays = []
    try:
        qs = Employee.objects.filter(is_active=True, dob__isnull=False)
        for emp in qs:
            birthday_this_year = emp.dob.replace(year=today.year)
            if birthday_this_year < today:
                birthday_this_year = emp.dob.replace(year=today.year + 1)
            if today <= birthday_this_year <= window_end:
                birthdays.append(
                    {
                        "id": emp.id,
                        "name": emp.get_full_name(),
                        "avatar": emp.get_avatar(),
                        "date": birthday_this_year.strftime("%d %b"),
                        "days_left": (birthday_this_year - today).days,
                    }
                )
        birthdays.sort(key=lambda x: x["days_left"])
    except Exception:
        pass

    return JsonResponse({"birthdays": birthdays[:10]})
