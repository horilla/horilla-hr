"""
Modern helpdesk dashboard views — KPI summary + ApexCharts.

Accessible at /helpdesk/dashboard/modern/ alongside the existing pipeline view.
"""

import calendar
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from horilla.decorators import login_required, permission_required


def _parse_period(request):
    """Return the picker's (from_date, to_date), defaulting to the current month.

    `from_date` / `to_date` come from the GET params (ISO dates); either one
    that is missing or invalid falls back to the current calendar month's
    first / last day, so the range still rolls forward by itself.
    """
    today = timezone.now().date()
    default_from = today.replace(day=1)
    default_to = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    try:
        from_date = date.fromisoformat(request.GET.get("from_date", ""))
    except (ValueError, TypeError):
        from_date = default_from
    try:
        to_date = date.fromisoformat(request.GET.get("to_date", ""))
    except (ValueError, TypeError):
        to_date = default_to
    return from_date, to_date


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_dashboard_view(request):
    """Render the modern helpdesk dashboard page."""
    return render(request, "helpdesk/dashboard.html")


def _live_tickets():
    """Every active ticket regardless of the picker (current-state panels)."""
    from helpdesk.models import Ticket

    return Ticket.objects.filter(is_active=True, employee_id__is_active=True)


def _period_tickets(request):
    """Active tickets created within the picker's date range."""
    from_date, to_date = _parse_period(request)
    return _live_tickets().filter(
        created_date__gte=from_date, created_date__lte=to_date
    )


def _resolved_this_month(request):
    """Active tickets resolved within the picker's date range."""
    from_date, to_date = _parse_period(request)
    return _live_tickets().filter(
        status="resolved", resolved_date__gte=from_date, resolved_date__lte=to_date
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_kpi_data(request):
    """Return helpdesk KPI summary data as JSON, for the picker's date range."""
    from helpdesk.models import ClaimRequest

    period_tickets = _period_tickets(request)
    resolved_this_month = _resolved_this_month(request)

    total_tickets = period_tickets.count()
    new_tickets = period_tickets.filter(status="new").count()
    in_progress = period_tickets.filter(status="in_progress").count()
    on_hold = period_tickets.filter(status="on_hold").count()
    canceled = period_tickets.filter(status="canceled").count()
    open_tickets = period_tickets.filter(
        status__in=["new", "in_progress", "on_hold"]
    ).count()

    period_resolved = resolved_this_month.count()

    month_created = total_tickets
    month_resolved = period_resolved
    resolution_rate = (
        min(round((month_resolved / month_created * 100), 1), 100)
        if month_created > 0
        else 0
    )

    overdue = _overdue_count()

    pending_claims = ClaimRequest.objects.filter(
        is_approved=False,
        is_rejected=False,
    ).count()

    unassigned = period_tickets.filter(
        status__in=["new", "in_progress"], assigned_to__isnull=True
    ).count()

    return JsonResponse(
        {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "new_tickets": new_tickets,
            "in_progress": in_progress,
            "on_hold": on_hold,
            "resolved": period_resolved,
            "canceled": canceled,
            "resolution_rate": resolution_rate,
            "period_resolved": period_resolved,
            "month_created": month_created,
            "month_resolved": month_resolved,
            "overdue": overdue,
            "pending_claims": pending_claims,
            "unassigned": unassigned,
        }
    )


def _overdue_count():
    """Tickets currently past their deadline and still open -- a live count."""
    from helpdesk.models import Ticket

    today = date.today()
    return Ticket.objects.filter(
        is_active=True,
        employee_id__is_active=True,
        deadline__lt=today,
        status__in=["new", "in_progress", "on_hold"],
    ).count()


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_status_distribution(request):
    """Ticket count by current status, for tickets created in the picker's range."""
    statuses = []
    status_choices = [
        ("new", _("New")),
        ("in_progress", _("In Progress")),
        ("on_hold", _("On Hold")),
        ("resolved", _("Resolved")),
        ("canceled", _("Canceled")),
    ]
    qs = _period_tickets(request)

    for status, label in status_choices:
        count = qs.filter(status=status).count()
        statuses.append({"status": status, "label": label, "count": count})

    return JsonResponse(
        {
            "statuses": statuses,
        }
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_priority_distribution(request):
    """Open ticket count by priority, for tickets created in the picker's range."""
    priorities = []
    priority_choices = [
        ("high", _("High")),
        ("medium", _("Medium")),
        ("low", _("Low")),
    ]
    qs = _period_tickets(request).filter(status__in=["new", "in_progress", "on_hold"])

    for priority, label in priority_choices:
        count = qs.filter(priority=priority).count()
        priorities.append({"priority": priority, "label": label, "count": count})

    return JsonResponse(
        {
            "priorities": priorities,
        }
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_type_distribution(request):
    """Ticket count by type, for tickets created in the picker's range."""
    types = []

    try:
        data = (
            _period_tickets(request)
            .values("ticket_type__id", "ticket_type__title", "ticket_type__type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            title = item["ticket_type__title"]
            if title:
                types.append(
                    {
                        "id": item["ticket_type__id"],
                        "type": title,
                        "category": item["ticket_type__type"] or "",
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse(
        {
            "types": types,
        }
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_monthly_trend(request):
    """Created-vs-resolved ticket counts for the 6 months ending at the picker's end date."""
    from helpdesk.models import Ticket

    today = _parse_period(request)[1]
    months = []
    created = []
    resolved = []

    cursor = (today - relativedelta(months=5)).replace(day=1)
    while cursor <= today:
        month_end = cursor.replace(
            day=calendar.monthrange(cursor.year, cursor.month)[1]
        )

        created.append(
            Ticket.objects.filter(
                is_active=True,
                created_date__gte=cursor,
                created_date__lte=month_end,
            ).count()
        )
        resolved.append(
            Ticket.objects.filter(
                is_active=True,
                status="resolved",
                resolved_date__gte=cursor,
                resolved_date__lte=month_end,
            ).count()
        )

        months.append(
            {
                "month": cursor.strftime("%b %Y"),
                "from_date": cursor.isoformat(),
                "to_date": month_end.isoformat(),
            }
        )
        cursor = month_end + timedelta(days=1)

    series = [
        {"key": "created", "label": _("Created"), "data": created},
        {"key": "resolved", "label": _("Resolved"), "data": resolved},
    ]
    return JsonResponse({"months": months, "series": series})


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_department_breakdown(request):
    """Open tickets by department (via employee owner), created in the picker's range."""
    departments = []

    try:
        data = (
            _period_tickets(request)
            .filter(status__in=["new", "in_progress", "on_hold"])
            .values(
                "employee_id__employee_work_info__department_id",
                "employee_id__employee_work_info__department_id__department",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            dept_id = item["employee_id__employee_work_info__department_id"]
            if dept:
                departments.append(
                    {"id": dept_id, "department": dept, "count": item["count"]}
                )
    except Exception:
        pass

    return JsonResponse(
        {
            "departments": departments,
        }
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_overdue_tickets(request):
    """Open tickets whose deadline has already passed (live, not scoped to the picker)."""
    today = date.today()
    cutoff = today
    tickets = []

    try:
        qs = (
            _live_tickets()
            .filter(
                deadline__lt=cutoff,
                status__in=["new", "in_progress", "on_hold"],
            )
            .select_related("employee_id", "ticket_type")
            .order_by("deadline")[:15]
        )

        for t in qs:
            emp = t.employee_id
            days_overdue = (today - t.deadline).days if t.deadline else 0
            tickets.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "ticket_id": (
                        f"{t.ticket_type.prefix}-{t.id}" if t.ticket_type else str(t.id)
                    ),
                    "employee_id": emp.id if emp else None,
                    "employee": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "priority": t.priority,
                    "status": t.status,
                    "days_overdue": days_overdue,
                    "deadline": t.deadline.strftime("%b %d") if t.deadline else "—",
                }
            )
    except Exception:
        pass

    return JsonResponse({"tickets": tickets})


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_recent_tickets(request):
    """Most recently created tickets within the picker's range, resolved ones left out."""
    tickets = []
    total = 0

    try:
        period_qs = _period_tickets(request).exclude(status="resolved")
        total = period_qs.count()
        qs = period_qs.select_related("employee_id", "ticket_type").order_by(
            "-created_date", "-id"
        )[:10]

        for t in qs:
            emp = t.employee_id
            tickets.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "ticket_id": (
                        f"{t.ticket_type.prefix}-{t.id}" if t.ticket_type else str(t.id)
                    ),
                    "employee_id": emp.id if emp else None,
                    "employee": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "priority": t.priority,
                    "status": t.status,
                    "type": t.ticket_type.title if t.ticket_type else "—",
                    "date": t.created_date.strftime("%b %d") if t.created_date else "—",
                }
            )
    except Exception:
        pass

    return JsonResponse({"tickets": tickets, "total": total})


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_sla_compliance(request):
    """SLA compliance -- tickets resolved in the picker's range, on time vs late."""
    resolved_on_time = 0
    resolved_late = 0

    try:
        resolved_with_deadline = _resolved_this_month(request).filter(
            deadline__isnull=False,
        )

        for t in resolved_with_deadline:
            if t.resolved_date <= t.deadline:
                resolved_on_time += 1
            else:
                resolved_late += 1
    except Exception:
        pass

    open_overdue = _overdue_count()

    total_with_deadline = resolved_on_time + resolved_late
    compliance_rate = (
        round((resolved_on_time / total_with_deadline * 100), 1)
        if total_with_deadline > 0
        else 0
    )

    return JsonResponse(
        {
            "compliance_rate": compliance_rate,
            "resolved_on_time": resolved_on_time,
            "resolved_late": resolved_late,
            "open_overdue": open_overdue,
            "total_with_deadline": total_with_deadline,
        }
    )


@login_required
@permission_required("helpdesk.view_ticket")
def helpdesk_assignee_workload(request):
    """Current open ticket count per assignee (live, not scoped to the picker)."""
    assignees = []

    try:
        open_tickets = _live_tickets().filter(
            status__in=["new", "in_progress", "on_hold"],
        )

        workload = {}
        for t in open_tickets:
            for emp in t.assigned_to.all():
                if emp.id not in workload:
                    workload[emp.id] = {
                        "id": emp.id,
                        "name": emp.get_full_name(),
                        "avatar": emp.get_avatar(),
                        "count": 0,
                        "high": 0,
                    }
                workload[emp.id]["count"] += 1
                if t.priority == "high":
                    workload[emp.id]["high"] += 1

        assignees = sorted(workload.values(), key=lambda x: x["count"], reverse=True)[
            :10
        ]
    except Exception:
        pass

    return JsonResponse(
        {
            "assignees": assignees,
        }
    )
