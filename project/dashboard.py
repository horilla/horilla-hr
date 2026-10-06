"""
Modern Project dashboard views — KPI summary + ApexCharts.

Accessible at /project/dashboard/
"""

from collections import Counter
from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from horilla.decorators import login_required
from project.cbv.cbv_decorators import is_projectmanager_or_member_or_perms

PIPELINE_STAGES = (
    ("new", _("New")),
    ("in_progress", _("In Progress")),
    ("on_hold", _("On Hold")),
    ("completed", _("Completed")),
)

TASK_STATUS_LABELS = {
    "to_do": _("To Do"),
    "in_progress": _("In Progress"),
    "completed": _("Completed"),
    "expired": _("Expired"),
}


def _parse_period(request):
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


def _month_bounds(today, months_ago):
    """First/last day of the month `months_ago` months before `today`."""
    year = today.year
    month = today.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    first = date(year, month, 1)
    if first.month == 12:
        last = date(first.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(first.year, first.month + 1, 1) - timedelta(days=1)
    return first, last


def _period_overlap(qs, request):
    """Rows whose [start_date, end_date] overlaps the picker range.

    A missing end date counts as still open, and a missing start date as
    already started, so undated rows aren't silently dropped.
    """
    from_date, to_date = _parse_period(request)
    return qs.filter(
        Q(start_date__lte=to_date) | Q(start_date__isnull=True),
        Q(end_date__gte=from_date) | Q(end_date__isnull=True),
    )


@login_required
def project_dashboard_view(request):
    from project.sidebar import dashboard_accessibility

    if not dashboard_accessibility(request, None, None):
        messages.info(request, _("You don't have permission."))
        return redirect("/")
    return render(request, "project/dashboard.html")


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_kpi_data(request):
    """Total/Active/On Hold/Overdue counts, each with a small trend delta."""
    from project.models import Project

    today = date.today()
    this_month_start, this_month_end = _month_bounds(today, 0)

    active_qs = Project.objects.filter(is_active=True)
    total = active_qs.count()
    active = active_qs.filter(status="in_progress").count()
    on_hold_qs = active_qs.filter(status="on_hold")
    on_hold = on_hold_qs.count()
    on_hold_overdue = on_hold_qs.filter(end_date__lt=today).count()
    overdue = (
        active_qs.filter(end_date__lt=today)
        .exclude(status__in=["completed", "cancelled", "expired"])
        .count()
    )

    total_new_this_month = active_qs.filter(
        start_date__gte=this_month_start, start_date__lte=this_month_end
    ).count()
    active_started_this_month = active_qs.filter(
        status="in_progress",
        start_date__gte=this_month_start,
        start_date__lte=this_month_end,
    ).count()
    overdue_new_this_month = (
        active_qs.filter(
            end_date__gte=this_month_start,
            end_date__lte=min(this_month_end, today),
        )
        .exclude(status__in=["completed", "cancelled", "expired"])
        .count()
    )

    return JsonResponse(
        {
            "total_projects": total,
            "active_projects": active,
            "on_hold_projects": on_hold,
            "on_hold_overdue": on_hold_overdue,
            "overdue_projects": overdue,
            "total_new_this_month": total_new_this_month,
            "active_started_this_month": active_started_this_month,
            "overdue_new_this_month": overdue_new_this_month,
        }
    )


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_status_pipeline(request):
    """New -> In Progress -> On Hold -> Completed stage tracker for active
    projects whose dates overlap the picker range.
    """
    from project.models import Project

    qs = _period_overlap(Project.objects.filter(is_active=True), request)
    # HorillaCompanyManager's get_queryset() applies .distinct() whenever the
    # company OR-filter is active; chaining .values("status").annotate(Count())
    # on top of that collapses to one row per Project instead of one row per
    # status (Django groups by the queryset's already-selected columns, not
    # just "status"), so every status count comes back as 1. Counting in
    # Python over a plain column pull sidesteps that entirely -- but only if
    # "pk" is pulled alongside the field: pk uniqueness is what actually
    # forces SELECT DISTINCT to keep every row. (Pulling "status" alone
    # happens to work today only because Project has Meta.ordering, which
    # Django folds into the DISTINCT column list to satisfy ORDER BY --
    # remove that ordering and this would silently start undercounting.)
    counts = Counter(status for _pk, status in qs.values_list("pk", "status"))
    stages = [
        {"status": key, "label": str(label), "count": counts.get(key, 0)}
        for key, label in PIPELINE_STAGES
    ]
    return JsonResponse({"stages": stages, "total": qs.count()})


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_task_status(request):
    """Task status breakdown for active tasks whose dates overlap the picker range."""
    from project.models import Task

    qs = _period_overlap(Task.objects.filter(is_active=True), request)
    # See project_status_pipeline for why this counts in Python (rather than
    # via .values("status").annotate(Count())) and pulls "pk" alongside
    # "status" rather than relying on Task's incidental Meta.ordering.
    counts = Counter(status for _pk, status in qs.values_list("pk", "status"))
    labels, counts_list, keys = [], [], []
    for key, label in TASK_STATUS_LABELS.items():
        count = counts.get(key, 0)
        if count:
            labels.append(str(label))
            counts_list.append(count)
            keys.append(key)
    return JsonResponse(
        {"labels": labels, "counts": counts_list, "keys": keys, "total": qs.count()}
    )


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_timesheet_trend(request):
    """Hours logged per project over the selected period, for a stacked chart.

    One bucket per day for ranges up to ~2 months, one per month for longer
    ones. Each project is its own series; beyond the top few by hours the rest
    are folded into "Other" so the stack stays readable.
    """
    from project.models import TimeSheet

    max_projects = 6
    from_date, to_date = _parse_period(request)
    entries = TimeSheet.objects.filter(date__gte=from_date, date__lte=to_date)

    def _hours(value):
        try:
            hours, minutes = str(value or "0:0").split(":")[:2]
            return int(hours) + int(minutes) / 60
        except (ValueError, TypeError):
            return 0.0

    # Buckets, in order: (label, first day, day after last).
    buckets = []
    if (to_date - from_date).days <= 62:
        day = from_date
        while day <= to_date:
            buckets.append((day.strftime("%b %d"), day, day + timedelta(days=1)))
            day += timedelta(days=1)
    else:
        month = from_date.replace(day=1)
        while month <= to_date:
            next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            buckets.append((month.strftime("%b %Y"), month, next_month))
            month = next_month

    totals = Counter()
    per_project = {}
    titles = {}
    for entry_date, spent, project_id, title in entries.values_list(
        "date", "time_spent", "project_id", "project_id__title"
    ):
        hours = _hours(spent)
        key = project_id or 0
        titles[key] = title or _("No project")
        totals[key] += hours
        for index, (_label, start, end) in enumerate(buckets):
            if start <= entry_date < end:
                per_project.setdefault(key, [0.0] * len(buckets))[index] += hours
                break

    ranked = [key for key, _total in totals.most_common()]
    series = [
        {
            "name": str(titles[key]),
            "data": [round(v, 2) for v in per_project.get(key, [0.0] * len(buckets))],
            "project_id": key or None,
        }
        for key in ranked[:max_projects]
    ]
    rest = ranked[max_projects:]
    if rest:
        other = [0.0] * len(buckets)
        for key in rest:
            for index, value in enumerate(per_project.get(key, [])):
                other[index] += value
        series.append(
            {
                "name": str(_("Other")),
                "data": [round(v, 2) for v in other],
                "project_id": None,
            }
        )

    return JsonResponse(
        {
            "labels": [label for label, _start, _end in buckets],
            "series": series,
            "total_hours": round(sum(totals.values()), 2),
            "entries": entries.count(),
        }
    )


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_top_active(request):
    """Top in-progress projects (dates overlapping the picker range) by task count."""
    from project.models import Project

    projects = (
        _period_overlap(Project.objects.filter(status="in_progress"), request)
        .annotate(task_count=Count("task"))
        .order_by("-task_count")[:8]
    )
    data = [
        {
            "id": p.id,
            "title": p.title,
            "task_count": p.task_count,
            "end_date": str(p.end_date) if p.end_date else "—",
        }
        for p in projects
    ]
    return JsonResponse({"projects": data})


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_top_contributors(request):
    """Top employees by tasks completed this period."""
    from employee.models import Employee

    from_date, to_date = _parse_period(request)
    contributors = []
    try:
        data = (
            Employee.objects.filter(
                tasks__status="completed",
                tasks__end_date__gte=from_date,
                tasks__end_date__lte=to_date,
            )
            .annotate(completed_count=Count("tasks", distinct=True))
            .filter(completed_count__gt=0)
            .order_by("-completed_count")[:10]
        )
        for emp in data:
            contributors.append(
                {
                    "id": emp.id,
                    "name": emp.get_full_name(),
                    "avatar": emp.get_avatar(),
                    "completed_count": emp.completed_count,
                }
            )
    except Exception:
        pass
    return JsonResponse(
        {"contributors": contributors, "month": to_date.strftime("%B %Y")}
    )


@login_required
@is_projectmanager_or_member_or_perms(perm="project.view_project")
def project_task_deadlines(request):
    """Tasks due within the next 14 days, plus tasks already overdue."""
    from project.models import Task

    today = date.today()
    open_tasks = Task.objects.filter(is_active=True).exclude(status__in=["completed"])

    upcoming = open_tasks.filter(
        end_date__gte=today, end_date__lte=today + timedelta(days=14)
    ).order_by("end_date")[:8]
    overdue = open_tasks.filter(end_date__lt=today).order_by("end_date")[:8]

    def _serialize(task, days_left):
        return {
            "id": task.id,
            "title": task.title,
            "project": task.project.title if task.project_id else "—",
            "project_id": task.project_id,
            "end_date": str(task.end_date) if task.end_date else "—",
            "days_left": days_left,
        }

    upcoming_data = [_serialize(t, (t.end_date - today).days) for t in upcoming]
    overdue_data = [_serialize(t, (t.end_date - today).days) for t in overdue]

    return JsonResponse({"upcoming": upcoming_data, "overdue": overdue_data})
