"""
Modern leave dashboard views — KPI summary + ApexCharts.

Accessible at /leave/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from horilla.decorators import permission_required


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
@permission_required("leave.view_leaverequest")
def leave_dashboard_view(request):
    """Render the modern leave dashboard page."""
    return render(request, "leave/dashboard.html")


@login_required
@permission_required("leave.view_leaverequest")
def leave_kpi_data(request):
    """Return leave KPI summary data as JSON."""
    from leave.models import AvailableLeave, LeaveAllocationRequest, LeaveRequest

    from_date, to_date = _parse_period(request)
    first_of_month = from_date
    real_today = date.today()  # always current date for point-in-time metrics

    pending_approval = LeaveRequest.objects.filter(
        status="requested", employee_id__is_active=True
    ).count()

    approved_this_month = LeaveRequest.objects.filter(
        status="approved",
        start_date__gte=first_of_month,
        start_date__lte=to_date,
        employee_id__is_active=True,
    ).count()

    rejected_this_month = LeaveRequest.objects.filter(
        status="rejected",
        start_date__gte=first_of_month,
        start_date__lte=to_date,
        employee_id__is_active=True,
    ).count()

    # Always reflects who is on leave right now, independent of the date filter
    on_leave_today = (
        LeaveRequest.objects.filter(
            start_date__lte=real_today,
            status="approved",
            employee_id__is_active=True,
        )
        .filter(
            Q(end_date__gte=real_today)
            | Q(end_date__isnull=True, start_date=real_today)
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    # Total leave days approved within the selected period
    total_days_used = LeaveRequest.objects.filter(
        status="approved",
        start_date__gte=first_of_month,
        start_date__lte=to_date,
        employee_id__is_active=True,
    ).aggregate(total=Coalesce(Sum("requested_days"), 0.0, output_field=FloatField()))[
        "total"
    ]

    # Pending allocation requests
    pending_allocations = 0
    try:
        pending_allocations = LeaveAllocationRequest.objects.filter(
            status="requested", employee_id__is_active=True
        ).count()
    except Exception:
        pass

    # Pending comp leave requests
    pending_comp = 0
    try:
        from leave.models import CompensatoryLeaveRequest

        pending_comp = CompensatoryLeaveRequest.objects.filter(
            status="requested", employee_id__is_active=True
        ).count()
    except Exception:
        pass
    return JsonResponse(
        {
            "pending_approval": pending_approval,
            "approved_this_month": approved_this_month,
            "rejected_this_month": rejected_this_month,
            "on_leave_today": on_leave_today,
            "total_days_used": round(float(total_days_used), 1),
            "pending_allocations": pending_allocations,
            "pending_comp": pending_comp,
            "month": to_date.strftime("%B %Y"),
            "from_date": first_of_month.isoformat(),
            "to_date": to_date.isoformat(),
            "today": real_today.isoformat(),
        }
    )


@login_required
@permission_required("leave.view_leaverequest")
def leave_department_trend(request):
    """Leave request counts per department, split by status, for the selected period."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    dept_field = "employee_id__employee_work_info__department_id__department"
    rows = (
        LeaveRequest.objects.filter(
            status__in=["approved", "rejected", "requested"],
            start_date__gte=from_date,
            start_date__lte=to_date,
            employee_id__is_active=True,
        )
        .values(dept_field, "status")
        .annotate(count=Count("id"))
    )

    by_dept = {}
    for row in rows:
        dept = row[dept_field] or _("No Department")
        entry = by_dept.setdefault(
            dept, {"department": dept, "approved": 0, "rejected": 0, "pending": 0}
        )
        key = "pending" if row["status"] == "requested" else row["status"]
        entry[key] += row["count"]

    departments = sorted(
        by_dept.values(),
        key=lambda d: (
            -d["approved"],
            -(d["rejected"] + d["pending"]),
            d["department"],
        ),
    )
    return JsonResponse(
        {
            "departments": departments,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
    )


@login_required
@permission_required("leave.view_leaverequest")
def leave_type_distribution(request):
    """Leave days by type for the current month."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    types = []

    try:
        data = (
            LeaveRequest.objects.filter(
                status="approved",
                start_date__gte=first_of_month,
                start_date__lte=today,
                employee_id__is_active=True,
            )
            .values(
                "leave_type_id",
                "leave_type_id__name",
                "leave_type_id__payment",
            )
            .annotate(count=Count("id"), total_days=Sum("requested_days"))
            .order_by("-total_days")
        )

        for item in data:
            types.append(
                {
                    "id": item["leave_type_id"],
                    "type": item["leave_type_id__name"] or _("Unknown"),
                    "payment": item["leave_type_id__payment"] or "unpaid",
                    "count": item["count"],
                    "days": round(float(item["total_days"] or 0), 1),
                }
            )
    except Exception:
        pass

    return JsonResponse({"types": types, "month": today.strftime("%B %Y")})


@login_required
@permission_required("leave.view_leaverequest")
def leave_department_breakdown(request):
    """Leave days by department for the current month."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    departments = []

    try:
        data = (
            LeaveRequest.objects.filter(
                status="approved",
                start_date__gte=first_of_month,
                start_date__lte=today,
                employee_id__is_active=True,
            )
            .values("employee_id__employee_work_info__department_id__department")
            .annotate(count=Count("id"), total_days=Sum("requested_days"))
            .order_by("-total_days")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            if dept:
                departments.append(
                    {
                        "department": dept,
                        "count": item["count"],
                        "days": round(float(item["total_days"] or 0), 1),
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments, "month": today.strftime("%B %Y")})


@login_required
@permission_required("leave.view_leaverequest")
def leave_utilization_rate(request):
    """Leave utilization per leave type: days used in the selected period vs total allocated."""
    from leave.models import AvailableLeave, LeaveRequest

    from_date, to_date = _parse_period(request)
    utilization = []

    try:
        allocations = (
            AvailableLeave.objects.filter(employee_id__is_active=True)
            .values("leave_type_id", "leave_type_id__name")
            .annotate(
                total_available=Sum("available_days"),
                total_carryforward=Sum("carryforward_days"),
                total_allocated=Sum("total_leave_days"),
            )
            .order_by("-total_allocated")
        )

        used_by_type = {
            row["leave_type_id"]: float(row["total"] or 0)
            for row in (
                LeaveRequest.objects.filter(
                    status="approved",
                    start_date__lte=to_date,
                    end_date__gte=from_date,
                    employee_id__is_active=True,
                )
                .values("leave_type_id")
                .annotate(total=Sum("requested_days"))
            )
        }

        for item in allocations:
            lt_id = item["leave_type_id"]
            allocated = float(item["total_allocated"] or 0)
            available = float(item["total_available"] or 0) + float(
                item["total_carryforward"] or 0
            )
            used = used_by_type.get(lt_id, 0.0)
            rate = round((used / allocated * 100), 1) if allocated > 0 else 0

            utilization.append(
                {
                    "type": item["leave_type_id__name"] or _("Unknown"),
                    "allocated": round(allocated, 1),
                    "used": round(used, 1),
                    "remaining": round(available, 1),
                    "rate": rate,
                }
            )
    except Exception:
        pass

    return JsonResponse({"utilization": utilization})


@login_required
@permission_required("leave.view_leaverequest")
def leave_paid_unpaid_split(request):
    """Paid vs unpaid leave days for the current month."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date

    paid = 0
    unpaid = 0
    paid_requests = 0
    unpaid_requests = 0

    try:
        data = (
            LeaveRequest.objects.filter(
                status="approved",
                start_date__gte=first_of_month,
                start_date__lte=today,
                employee_id__is_active=True,
            )
            .values("leave_type_id__payment")
            .annotate(total_days=Sum("requested_days"), requests=Count("id"))
        )

        for item in data:
            days = float(item["total_days"] or 0)
            if item["leave_type_id__payment"] == "paid":
                paid += days
                paid_requests += item["requests"]
            else:
                unpaid += days
                unpaid_requests += item["requests"]
    except Exception:
        pass

    return JsonResponse(
        {
            "paid": round(paid, 1),
            "unpaid": round(unpaid, 1),
            "paid_requests": paid_requests,
            "unpaid_requests": unpaid_requests,
            "month": today.strftime("%B %Y"),
        }
    )


@login_required
@permission_required("leave.view_leaverequest")
def leave_top_takers(request):
    """Top 10 employees by leave days taken this month."""
    from employee.models import Employee
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    takers = []

    try:
        data = (
            LeaveRequest.objects.filter(
                status="approved",
                start_date__gte=first_of_month,
                start_date__lte=today,
                employee_id__is_active=True,
            )
            .values(
                "employee_id",
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            )
            .annotate(total_days=Sum("requested_days"), request_count=Count("id"))
            .order_by("-total_days")[:10]
        )

        avatar_by_employee_id = {
            emp.id: emp.get_avatar()
            for emp in Employee.objects.filter(
                id__in=[item["employee_id"] for item in data]
            )
        }

        for item in data:
            first = item["employee_id__employee_first_name"] or ""
            last = item["employee_id__employee_last_name"] or ""
            name = f"{first} {last}".strip()

            takers.append(
                {
                    "id": item["employee_id"],
                    "name": name,
                    "avatar": avatar_by_employee_id.get(item["employee_id"]),
                    "days": round(float(item["total_days"] or 0), 1),
                    "requests": item["request_count"],
                }
            )
    except Exception:
        pass

    return JsonResponse(
        {
            "takers": takers,
            "month": today.strftime("%B %Y"),
        }
    )


@login_required
@permission_required("leave.view_leaverequest")
def leave_on_leave_today(request):
    """Employees with approved leave on actual today."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = date.today()
    employees = []

    try:
        qs = (
            LeaveRequest.objects.filter(
                start_date__lte=today,
                end_date__gte=today,
                status="approved",
                employee_id__is_active=True,
            )
            .select_related("employee_id", "leave_type_id")
            .order_by("employee_id__employee_first_name")[:20]
        )

        for lr in qs:
            emp = lr.employee_id
            employees.append(
                {
                    "id": emp.id if emp else None,
                    "name": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "leave_type": lr.leave_type_id.name if lr.leave_type_id else "—",
                    "start": lr.start_date.strftime("%b %d"),
                    "end": (
                        lr.end_date.strftime("%b %d")
                        if lr.end_date
                        else lr.start_date.strftime("%b %d")
                    ),
                    "days": float(lr.requested_days) if lr.requested_days else 1,
                }
            )
    except Exception:
        pass

    return JsonResponse({"employees": employees, "date": today.isoformat()})


@login_required
@permission_required("leave.view_leaverequest")
def leave_upcoming_holidays(request):
    """Holidays falling within the selected period."""
    from base.models import Holidays

    from_date, to_date = _parse_period(request)
    today = date.today()
    holidays = []

    try:
        qs = Holidays.objects.filter(
            is_specific=False,
            start_date__gte=from_date,
            start_date__lte=to_date,
        ).order_by("start_date")[:10]

        for h in qs:
            holidays.append(
                {
                    "name": h.name,
                    "start": h.start_date.strftime("%b %d"),
                    "end": (
                        h.end_date.strftime("%b %d")
                        if h.end_date and h.end_date != h.start_date
                        else None
                    ),
                    "days_away": (h.start_date - today).days,
                }
            )
    except Exception:
        pass

    return JsonResponse({"holidays": holidays})


@login_required
@permission_required("leave.view_leaverequest")
def leave_weekly_pattern(request):
    """Leave requests by day of week for the selected period (pattern analysis)."""
    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    counts = [0] * 7

    try:
        leaves = LeaveRequest.objects.filter(
            status="approved",
            start_date__lte=to_date,
            end_date__gte=from_date,
            employee_id__is_active=True,
        )

        for lr in leaves:
            d = max(lr.start_date, from_date)
            end = min(lr.end_date or lr.start_date, to_date)
            while d <= end:
                counts[d.weekday()] += 1
                d += timedelta(days=1)
    except Exception:
        pass

    return JsonResponse(
        {
            "days": days,
            "counts": counts,
        }
    )


@login_required
@permission_required("leave.view_leaverequest")
def leave_upcoming(request):
    """Approved leaves starting within the next 7 days, excluding today."""
    from datetime import timedelta

    from leave.models import LeaveRequest

    from_date, to_date = _parse_period(request)
    today = date.today()
    upcoming = []

    try:
        next_week = today + timedelta(days=7)
        qs = (
            LeaveRequest.objects.filter(
                status="approved",
                start_date__gt=today,
                start_date__lte=next_week,
                employee_id__is_active=True,
            )
            .select_related("employee_id", "leave_type_id")
            .order_by("start_date")[:15]
        )

        for lr in qs:
            emp = lr.employee_id
            days_away = (lr.start_date - today).days
            upcoming.append(
                {
                    "id": emp.id if emp else None,
                    "name": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "leave_type": lr.leave_type_id.name if lr.leave_type_id else "—",
                    "start": lr.start_date.strftime("%b %d"),
                    "end": (
                        lr.end_date.strftime("%b %d")
                        if lr.end_date
                        else lr.start_date.strftime("%b %d")
                    ),
                    "days": float(lr.requested_days) if lr.requested_days else 1,
                    "days_away": days_away,
                }
            )
    except Exception:
        pass

    return JsonResponse({"upcoming": upcoming})


# ---------------------------------------------------------------------------
# Employee-specific dashboard API views
# ---------------------------------------------------------------------------


def _get_employee_for_user(request):
    """Return the Employee instance for the current user, or None.

    Uses the reverse OneToOne (``employee_get``) so company filtering on
    ``Employee.objects`` cannot hide the logged-in user when they have
    switched to a company that is not their work-info company.
    """
    return getattr(request.user, "employee_get", None)


@login_required
def employee_dashboard_view(request):
    """Render the employee leave dashboard page (JS fetches all data via API)."""
    return render(request, "leave/employee_dashboard.html")


@login_required
def employee_kpi_data(request):
    """Return KPI summary for the logged-in employee as JSON."""
    from leave.models import AvailableLeave, LeaveRequest

    today = date.today()
    first_of_month = today.replace(day=1)

    employee = _get_employee_for_user(request)
    if employee is None:
        return JsonResponse({"error": "Employee not found"}, status=404)

    # Basic employee info
    try:
        avatar_url = employee.get_avatar()
    except Exception:
        avatar_url = None

    try:
        pending_count = LeaveRequest.objects.filter(
            employee_id=employee, status="requested"
        ).count()
    except Exception:
        pending_count = 0

    try:
        approved_count = LeaveRequest.objects.filter(
            employee_id=employee,
            status="approved",
            start_date__gte=first_of_month,
            start_date__lte=today,
        ).count()
    except Exception:
        approved_count = 0

    try:
        rejected_count = LeaveRequest.objects.filter(
            employee_id=employee,
            status="rejected",
            start_date__gte=first_of_month,
            start_date__lte=today,
        ).count()
    except Exception:
        rejected_count = 0

    try:
        balance_agg = AvailableLeave.objects.filter(employee_id=employee).aggregate(
            total=Coalesce(
                Sum(F("available_days") + F("carryforward_days")),
                0.0,
                output_field=FloatField(),
            )
        )
        total_available_days = round(float(balance_agg["total"] or 0), 1)
    except Exception:
        total_available_days = 0.0

    try:
        upcoming_count = LeaveRequest.objects.filter(
            employee_id=employee,
            status="approved",
            start_date__gte=today,
        ).count()
    except Exception:
        upcoming_count = 0

    return JsonResponse(
        {
            "employee_id": employee.id,
            "employee_name": (
                employee.get_full_name()
                if hasattr(employee, "get_full_name")
                else str(employee)
            ),
            "employee_avatar": avatar_url,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "total_available_days": total_available_days,
            "upcoming_count": upcoming_count,
            "month": today.strftime("%B %Y"),
            "today": today.isoformat(),
        }
    )


@login_required
def employee_leave_balance(request):
    """Return leave balance details for the logged-in employee as JSON."""
    from leave.models import AvailableLeave, LeaveRequest

    employee = _get_employee_for_user(request)
    if employee is None:
        return JsonResponse({"error": "Employee not found"}, status=404)

    balances = []
    try:
        available_leaves = AvailableLeave.objects.filter(
            employee_id=employee
        ).select_related("leave_type_id")

        # Pre-fetch used days per leave type for this employee
        used_by_type = {
            row["leave_type_id"]: float(row["used"] or 0)
            for row in LeaveRequest.objects.filter(
                employee_id=employee,
                status="approved",
            )
            .values("leave_type_id")
            .annotate(used=Sum("requested_days"))
        }

        for al in available_leaves:
            lt = al.leave_type_id
            if lt is None:
                continue
            used_days = used_by_type.get(lt.id, 0.0)
            balances.append(
                {
                    "type_id": lt.id,
                    "name": lt.name,
                    "available_days": round(float(al.available_days or 0), 1),
                    "carryforward_days": round(float(al.carryforward_days or 0), 1),
                    "total_days": round(float(al.total_leave_days or 0), 1),
                    "used_days": round(used_days, 1),
                }
            )
    except Exception:
        pass

    return JsonResponse({"balances": balances})


@login_required
def employee_monthly_trend(request):
    """Monthly leave request counts for the last 6 months for the logged-in employee."""
    from leave.models import LeaveRequest

    employee = _get_employee_for_user(request)
    if employee is None:
        return JsonResponse({"error": "Employee not found"}, status=404)

    today = date.today()
    months = []

    base = today.replace(day=1)
    for i in range(5, -1, -1):
        year = base.year
        month = base.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_start = date(year, month, 1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(
                days=1
            )

        try:
            approved = LeaveRequest.objects.filter(
                employee_id=employee,
                status="approved",
                start_date__gte=month_start,
                start_date__lte=month_end,
            ).count()
        except Exception:
            approved = 0

        try:
            rejected = LeaveRequest.objects.filter(
                employee_id=employee,
                status="rejected",
                start_date__gte=month_start,
                start_date__lte=month_end,
            ).count()
        except Exception:
            rejected = 0

        try:
            pending = LeaveRequest.objects.filter(
                employee_id=employee,
                status="requested",
                start_date__gte=month_start,
                start_date__lte=month_end,
            ).count()
        except Exception:
            pending = 0

        months.append(
            {
                "month": month_start.strftime("%b %Y"),
                "approved": approved,
                "rejected": rejected,
                "pending": pending,
                "from_date": month_start.isoformat(),
                "to_date": month_end.isoformat(),
            }
        )

    return JsonResponse({"months": months})


@login_required
def employee_upcoming_leaves(request):
    """Upcoming approved leaves for the logged-in employee."""
    from leave.models import LeaveRequest

    employee = _get_employee_for_user(request)
    if employee is None:
        return JsonResponse({"error": "Employee not found"}, status=404)

    today = date.today()
    leaves = []

    try:
        qs = (
            LeaveRequest.objects.filter(
                employee_id=employee,
                status="approved",
                start_date__gte=today,
            )
            .select_related("leave_type_id")
            .order_by("start_date")[:10]
        )

        for lr in qs:
            days_away = (lr.start_date - today).days
            leaves.append(
                {
                    "id": lr.id,
                    "leave_type": lr.leave_type_id.name if lr.leave_type_id else "—",
                    "start_date": lr.start_date.isoformat(),
                    "end_date": (
                        lr.end_date.isoformat()
                        if lr.end_date
                        else lr.start_date.isoformat()
                    ),
                    "days": float(lr.requested_days) if lr.requested_days else 1,
                    "days_away": days_away,
                }
            )
    except Exception:
        pass

    return JsonResponse({"leaves": leaves})


@login_required
def employee_leave_history(request):
    """Recent leave request history for the logged-in employee (last 10)."""
    from leave.models import LeaveRequest

    employee = _get_employee_for_user(request)
    if employee is None:
        return JsonResponse({"error": "Employee not found"}, status=404)

    requests = []

    try:
        qs = (
            LeaveRequest.objects.filter(employee_id=employee)
            .select_related("leave_type_id")
            .order_by("-id")[:10]
        )

        for lr in qs:
            applied_on = (
                lr.requested_date.isoformat()
                if lr.requested_date
                else lr.start_date.isoformat()
            )
            requests.append(
                {
                    "id": lr.id,
                    "leave_type": lr.leave_type_id.name if lr.leave_type_id else "—",
                    "status": lr.status,
                    "start_date": lr.start_date.isoformat(),
                    "end_date": (
                        lr.end_date.isoformat()
                        if lr.end_date
                        else lr.start_date.isoformat()
                    ),
                    "days": float(lr.requested_days) if lr.requested_days else 1,
                    "applied_on": applied_on,
                }
            )
    except Exception:
        pass

    return JsonResponse({"requests": requests})
