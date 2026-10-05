"""
Modern PMS (Performance Management) dashboard views — KPI summary + ApexCharts.

Accessible at /pms/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render

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


def _period_overlap(qs, request, start_field="start_date", end_field="end_date"):
    """Restrict a queryset to rows whose [start, end] overlaps the requested period."""
    from_date, to_date = _parse_period(request)
    return qs.filter(**{f"{start_field}__lte": to_date, f"{end_field}__gte": from_date})


@login_required
@permission_required("pms.view_employeeobjective")
def pms_dashboard_view(request):
    """Render the modern PMS dashboard page."""
    return render(request, "pms/dashboard.html")


@login_required
@permission_required("pms.view_employeeobjective")
def pms_kpi_data(request):
    """Return PMS KPI summary data as JSON (tile counts match the lists they link to)."""
    from pms.models import EmployeeKeyResult, EmployeeObjective, Feedback, Objective

    # Every tile links to an unfiltered list page, so the counts are not
    # scoped to the picker range: key results can have no start/end date at
    # all, and assignments/feedback are often dated outside the current
    # month, which made these tiles read 0 while the lists were populated.
    objectives = EmployeeObjective.objects.filter(archive=False)
    key_results = EmployeeKeyResult.objects.all()
    feedbacks = Feedback.objects.filter(archive=False)

    total_objectives = (
        Objective.objects.exclude(is_template=True)
        .filter(Q(archive=False) | Q(archive__isnull=True))
        .count()
    )
    assigned_objectives = objectives.count()
    total_key_results = key_results.count()
    total_feedbacks = feedbacks.count()

    # Average progress -- of key results, matching this card's sub-label
    # ("N key results") and its click-through to the Key Results list, not
    # objectives' own progress_percentage (each objective's own average of
    # its key results, a different aggregation).
    avg_progress = key_results.aggregate(
        avg=Coalesce(Avg("progress_percentage"), 0.0, output_field=FloatField())
    )["avg"]

    # At-risk count
    at_risk = objectives.filter(status="At Risk").count()

    # Closed objectives
    closed = objectives.filter(status="Closed").count()

    completion_rate = (
        round((closed / assigned_objectives * 100), 1) if assigned_objectives > 0 else 0
    )

    # Pending feedback (not started + on track)
    pending_feedback = feedbacks.filter(status__in=["Not Started", "On Track"]).count()

    return JsonResponse(
        {
            "total_objectives": total_objectives,
            "total_key_results": total_key_results,
            "total_feedbacks": total_feedbacks,
            "avg_progress": round(float(avg_progress), 1),
            "at_risk": at_risk,
            "closed": closed,
            "completion_rate": completion_rate,
            "pending_feedback": pending_feedback,
        }
    )


@login_required
@permission_required("pms.view_employeeobjective")
def pms_objective_status(request):
    """Objective status distribution for objectives active in the picker range."""
    from pms.models import EmployeeObjective

    objectives = _period_overlap(
        EmployeeObjective.objects.filter(archive=False), request
    )
    statuses = []

    for status, label in EmployeeObjective.STATUS_CHOICES:
        count = objectives.filter(status=status).count()
        statuses.append({"status": status, "label": str(label), "count": count})

    return JsonResponse({"statuses": statuses})


@login_required
@permission_required("pms.view_employeekeyresult")
def pms_key_result_status(request):
    """Key result status distribution for KRs active in the picker range."""
    from pms.models import EmployeeKeyResult

    key_results = _period_overlap(EmployeeKeyResult.objects.all(), request)
    statuses = []

    for status, label in EmployeeKeyResult.STATUS_CHOICES:
        count = key_results.filter(status=status).count()
        statuses.append({"status": status, "label": str(label), "count": count})

    return JsonResponse({"statuses": statuses})


@login_required
@permission_required("pms.view_feedback")
def pms_feedback_status(request):
    """Feedback status distribution for feedback active in the picker range."""
    from pms.models import Feedback

    feedbacks = _period_overlap(Feedback.objects.filter(archive=False), request)
    statuses = []

    # Same status order as the objective / key result charts (the model's
    # own STATUS_CHOICES order differs), so the three legends line up.
    labels = dict(Feedback.STATUS_CHOICES)
    for status in ("Not Started", "On Track", "Behind", "At Risk", "Closed"):
        count = feedbacks.filter(status=status).count()
        statuses.append(
            {"status": status, "label": str(labels.get(status, status)), "count": count}
        )

    return JsonResponse({"statuses": statuses})


@login_required
@permission_required("pms.view_employeeobjective")
def pms_department_performance(request):
    """Average objective progress by department for objectives active in the picker range."""
    from pms.models import EmployeeObjective

    departments = []

    try:
        data = (
            _period_overlap(EmployeeObjective.objects.filter(archive=False), request)
            .values(
                "employee_id__employee_work_info__department_id",
                "employee_id__employee_work_info__department_id__department",
            )
            .annotate(
                avg_progress=Avg("progress_percentage"),
                total=Count("id"),
                closed=Count("id", filter=Q(status="Closed")),
                at_risk=Count("id", filter=Q(status="At Risk")),
            )
            .order_by("-avg_progress")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            dept_id = item["employee_id__employee_work_info__department_id"]
            if dept:
                departments.append(
                    {
                        "department": dept,
                        "dept_id": dept_id,
                        "avg_progress": round(float(item["avg_progress"] or 0), 1),
                        "total": item["total"],
                        "closed": item["closed"],
                        "at_risk": item["at_risk"],
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments})


@login_required
@permission_required("pms.view_employeeobjective")
def pms_top_performers(request):
    """Top performers by objective completion and bonus points, for the picker range."""
    from employee.models import Employee
    from pms.models import EmployeeBonusPoint, EmployeeObjective

    performers = []

    try:
        # By objective progress
        data = (
            _period_overlap(EmployeeObjective.objects.filter(archive=False), request)
            .values(
                "employee_id",
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            )
            .annotate(
                avg_progress=Avg("progress_percentage"),
                total_objectives=Count("id"),
                completed=Count("id", filter=Q(status="Closed")),
            )
            .order_by("-avg_progress")[:10]
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

            # Get bonus points
            bonus = 0
            try:
                bonus = EmployeeBonusPoint.objects.filter(
                    employee_id=item["employee_id"]
                ).aggregate(total=Coalesce(Sum("bonus_point"), 0))["total"]
            except Exception:
                pass

            performers.append(
                {
                    "id": item["employee_id"],
                    "name": f"{first} {last}".strip(),
                    "avatar": avatar_by_employee_id.get(item["employee_id"]),
                    "avg_progress": round(float(item["avg_progress"] or 0), 1),
                    "objectives": item["total_objectives"],
                    "completed": item["completed"],
                    "bonus_points": bonus,
                }
            )
    except Exception:
        pass

    return JsonResponse({"performers": performers})


@login_required
@permission_required("pms.view_employeekeyresult")
def pms_kr_progress_overview(request):
    """Key result progress grouped by objective, for open (not Closed) objectives active in the picker range."""
    from pms.models import EmployeeKeyResult, EmployeeObjective

    overview = []

    try:
        objectives = (
            _period_overlap(
                EmployeeObjective.objects.filter(archive=False).exclude(
                    status="Closed"
                ),
                request,
            )
            .select_related("objective_id")
            .order_by("-progress_percentage")[:10]
        )

        for obj in objectives:
            krs = EmployeeKeyResult.objects.filter(employee_objective_id=obj).values(
                "key_result",
                "progress_percentage",
                "status",
                "current_value",
                "target_value",
            )

            kr_list = []
            for kr in krs:
                kr_list.append(
                    {
                        "title": kr["key_result"],
                        "progress": kr["progress_percentage"],
                        "status": kr["status"],
                        "current": kr["current_value"],
                        "target": kr["target_value"],
                    }
                )

            emp = obj.employee_id
            overview.append(
                {
                    "objective": (
                        obj.objective_id.title
                        if obj.objective_id
                        else obj.objective or "—"
                    ),
                    "employee": emp.get_full_name() if emp else "—",
                    "progress": obj.progress_percentage,
                    "status": obj.status,
                    "key_results": kr_list,
                }
            )
    except Exception:
        pass

    return JsonResponse({"overview": overview})


@login_required
@permission_required("pms.view_meetings")
def pms_upcoming_meetings(request):
    """PMS meetings in the next 14 days (the card's "Next 14 days" label)."""
    from pms.models import Meetings

    today = date.today()
    from_date, to_date = today, today + timedelta(days=14)
    meetings = []

    try:
        qs = Meetings.objects.filter(
            date__date__gte=from_date,
            date__date__lte=to_date,
        ).order_by("date")[:10]

        for m in qs:
            meetings.append(
                {
                    "id": m.id,
                    "title": m.title,
                    "date": m.date.strftime("%b %d"),
                    "time": m.date.strftime("%I:%M %p"),
                    "days_away": (m.date.date() - today).days,
                    "attendees": m.employee_id.count() + m.manager.count(),
                }
            )
    except Exception:
        pass

    return JsonResponse({"meetings": meetings})
