"""
Modern offboarding dashboard views — KPI summary + ApexCharts.

Accessible at /offboarding/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import date, timedelta

from django.apps import apps
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from horilla.decorators import login_required, permission_required


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
@permission_required("offboarding.view_offboarding")
def offboarding_dashboard_view(request):
    """Render the modern offboarding dashboard page."""
    return render(request, "offboarding/dashboard.html")


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_kpi_data(request):
    """Return offboarding KPI summary data as JSON.

    Total offboardings and resignation counts reflect the picker range.
    Current-state KPIs (active offboardings, headcount, notice ending) ignore it.
    """
    from employee.models import Employee
    from offboarding.models import EmployeeTask, OffboardingEmployee, ResignationLetter

    from_date, to_date = _parse_period(request)
    period_offboardings = OffboardingEmployee.objects.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )
    period_resignations = ResignationLetter.objects.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )

    employees = Employee.objects.filter(is_active=True).count()
    total_offboarding = period_offboardings.count()
    # OffboardingEmployee has no timestamp for "when did this reach its
    # current stage" (stage moves happen either via drag-and-drop, which
    # bulk_updates and skips .save(), or via the stage dropdown, which
    # does call .save() -- an unreliable mix to hang a period filter on),
    # so this is a current-state count, not scoped to the picker range.
    archived = OffboardingEmployee.objects.filter(stage_id__type="archived").count()

    exit_ratio = round((archived / employees * 100), 1) if employees > 0 else 0

    # Pending resignations are a review queue -- a letter submitted before
    # the selected period but still awaiting review should still count, so
    # (unlike total_offboarding above) this ignores the period.
    pending_resignations = ResignationLetter.objects.filter(status="requested").count()
    approved_resignations = period_resignations.filter(status="approved").count()

    # Task completion (current state across all offboardings)
    total_tasks = EmployeeTask.objects.all().count()
    completed_tasks = EmployeeTask.objects.filter(status="completed").count()
    task_completion = (
        round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0
    )

    # Active offboarding (current state, not archived)
    active_offboarding = OffboardingEmployee.objects.exclude(
        stage_id__type="archived"
    ).count()

    # Notice periods ending soon (next 7 days)
    today = date.today()
    notice_ending_soon = (
        OffboardingEmployee.objects.filter(
            notice_period_ends__gte=today,
            notice_period_ends__lte=today + timedelta(days=7),
        )
        .exclude(stage_id__type="archived")
        .count()
    )

    return JsonResponse(
        {
            "total_employees": employees,
            "total_offboarding": total_offboarding,
            "active_offboarding": active_offboarding,
            "archived": archived,
            "exit_ratio": exit_ratio,
            "pending_resignations": pending_resignations,
            "approved_resignations": approved_resignations,
            "task_completion": task_completion,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "notice_ending_soon": notice_ending_soon,
        }
    )


#: (OffboardingStage.type, tile label) in pipeline order. OffboardingStage
#: rows are per-Offboarding-template -- every company/template gets its own
#: "Notice Period" / "Exit Interview" / etc. row -- so grouping by the stage
#: *row* (as this endpoint used to) renders one tile per template instead of
#: one tile per stage, e.g. 3 templates x 6 types = 18 tiles. Grouping by
#: `type` instead collapses that back to exactly one tile per pipeline step,
#: matching every other pipeline widget in the app (Payslip/Project Pipeline).
PIPELINE_STAGE_TYPES = (
    ("notice_period", _("Notice Period")),
    ("interview", _("Exit Interview")),
    ("handover", _("Work Handover")),
    ("fnf", _("FNF")),
    ("other", _("Farewell")),
    ("archived", _("Archived")),
)


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_pipeline(request):
    """Employees grouped by offboarding stage type -- one tile per stage.

    Live pipeline state, not scoped to the date picker: an employee doesn't
    stop being "in the pipeline" just because their offboarding record
    predates the selected period (same rationale as active_offboarding /
    archived in offboarding_kpi_data above, and as project_status_pipeline
    in project/dashboard.py).
    """
    from collections import Counter

    from offboarding.models import OffboardingEmployee

    # HorillaCompanyManager.get_queryset() applies .distinct() whenever the
    # company OR-filter is active, which silently corrupts any aggregation
    # built on top of it. This isn't limited to .values().annotate(Count())
    # -- a *plain* .values_list("stage_id__type", flat=True) is just as
    # broken: Django compiles it as `SELECT DISTINCT stage_type FROM ...`,
    # which deduplicates on the VALUE, not the row, so two different
    # employees who both happen to be "archived" collapse into one row and
    # get undercounted. (Project/Task's equivalent pipeline queries in
    # project/dashboard.py happen to dodge this only because those models
    # have a default `ordering`, which Django folds into the SELECT DISTINCT
    # list to satisfy ORDER BY -- an accident of unrelated Meta config, not
    # a real fix; OffboardingEmployee has no such ordering.) Pulling `pk`
    # alongside the field forces every row to stay distinct regardless of
    # ordering, so the Python-side Counter below sees every row once.
    counts = Counter(
        stage_type
        for _pk, stage_type in OffboardingEmployee.objects.filter(
            stage_id__isnull=False
        ).values_list("pk", "stage_id__type")
    )
    stages = [
        {"stage": str(label), "type": stage_type, "count": counts.get(stage_type, 0)}
        for stage_type, label in PIPELINE_STAGE_TYPES
    ]
    return JsonResponse({"stages": stages, "total": sum(counts.values())})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_resignation_status(request):
    """Resignation letter status breakdown for letters created within the selected period."""
    from offboarding.models import ResignationLetter

    from_date, to_date = _parse_period(request)
    base = ResignationLetter.objects.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )
    statuses = [
        {
            "status": "requested",
            "label": _("Requested"),
            "count": base.filter(status="requested").count(),
        },
        {
            "status": "approved",
            "label": _("Approved"),
            "count": base.filter(status="approved").count(),
        },
        {
            "status": "rejected",
            "label": _("Rejected"),
            "count": base.filter(status="rejected").count(),
        },
    ]

    return JsonResponse({"statuses": statuses})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_task_status(request):
    """Task completion status for tasks created within the selected period."""
    from offboarding.models import EmployeeTask

    from_date, to_date = _parse_period(request)
    base = EmployeeTask.objects.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )
    statuses = []
    for status, label in EmployeeTask.statuses:
        count = base.filter(status=status).count()
        statuses.append({"status": status, "label": str(label), "count": count})

    return JsonResponse({"statuses": statuses})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_department_attrition(request):
    """Offboarding count by department (offboardings opened within the selected period)."""
    from offboarding.models import OffboardingEmployee

    from_date, to_date = _parse_period(request)
    departments = []

    try:
        data = (
            OffboardingEmployee.objects.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
            )
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
                    {
                        "department": dept,
                        "dept_id": dept_id,
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_exit_reasons(request):
    """Exit reasons breakdown for reasons logged within the selected period."""
    from offboarding.models import ExitReason

    from_date, to_date = _parse_period(request)
    reasons = []

    try:
        data = (
            ExitReason.objects.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
            )
            .values("title")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            reasons.append(
                {
                    "reason": item["title"],
                    "count": item["count"],
                }
            )
    except Exception:
        pass

    return JsonResponse({"reasons": reasons})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_notice_period_tracker(request):
    """Employees with notice periods overlapping the selected period."""
    from offboarding.models import OffboardingEmployee

    from_date, to_date = _parse_period(request)
    today = date.today()
    employees = []

    try:
        qs = (
            OffboardingEmployee.objects.filter(
                notice_period_ends__isnull=False,
                notice_period_starts__lte=to_date,
                notice_period_ends__gte=from_date,
            )
            .exclude(stage_id__type="archived")
            .select_related("employee_id", "stage_id", "stage_id__offboarding_id")
            .order_by("notice_period_ends")[:15]
        )

        for oe in qs:
            emp = oe.employee_id
            days_left = (
                (oe.notice_period_ends - today).days if oe.notice_period_ends else None
            )
            employees.append(
                {
                    "id": emp.id if emp else None,
                    "name": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "offboarding_id": (
                        oe.stage_id.offboarding_id_id if oe.stage_id else None
                    ),
                    "stage": oe.stage_id.title if oe.stage_id else "—",
                    "notice_ends": (
                        oe.notice_period_ends.strftime("%b %d, %Y")
                        if oe.notice_period_ends
                        else "—"
                    ),
                    "days_left": days_left,
                    "status": (
                        "ended"
                        if days_left is not None and days_left < 0
                        else (
                            "ending"
                            if days_left is not None and days_left <= 7
                            else "active"
                        )
                    ),
                }
            )
    except Exception:
        pass

    return JsonResponse({"employees": employees})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_unreturned_assets(request):
    """Unreturned assets from employees offboarded within the selected period."""
    from_date, to_date = _parse_period(request)
    assets = []

    try:
        if apps.is_installed("asset"):
            from asset.models import AssetAssignment
            from offboarding.models import OffboardingEmployee

            offboarding_emp_ids = OffboardingEmployee.objects.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
            ).values_list("employee_id", flat=True)

            qs = AssetAssignment.objects.filter(
                assigned_to_employee_id__in=offboarding_emp_ids,
                return_status__isnull=True,
            ).select_related("assigned_to_employee_id", "asset_id")[:15]

            for aa in qs:
                emp = aa.assigned_to_employee_id
                assets.append(
                    {
                        "id": emp.id if emp else None,
                        "employee": emp.get_full_name() if emp else "—",
                        "asset": aa.asset_id.asset_name if aa.asset_id else "—",
                        "category": (
                            aa.asset_id.asset_category_id.asset_category_name
                            if aa.asset_id and aa.asset_id.asset_category_id
                            else "—"
                        ),
                    }
                )
    except Exception:
        pass

    return JsonResponse({"assets": assets})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_joining_vs_exiting(request):
    """Monthly joining vs exiting trend within the selected period."""
    from employee.models import EmployeeWorkInformation
    from offboarding.models import ResignationLetter

    from_date, to_date = _parse_period(request)
    months = []

    cursor = from_date.replace(day=1)
    end_marker = to_date.replace(day=1)
    while cursor <= end_marker:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_start = cursor
        month_end = next_month - timedelta(days=1)

        joining = EmployeeWorkInformation.objects.filter(
            date_joining__gte=month_start,
            date_joining__lte=month_end,
        ).count()

        exiting = ResignationLetter.objects.filter(
            planned_to_leave_on__gte=month_start,
            planned_to_leave_on__lte=month_end,
            status__in=["approved", "requested"],
        ).count()

        months.append(
            {
                "month": month_start.strftime("%b %Y"),
                "joining": joining,
                "exiting": exiting,
                "from_date": month_start.isoformat(),
                "to_date": month_end.isoformat(),
            }
        )
        cursor = next_month

    return JsonResponse({"months": months})


@login_required
@permission_required("offboarding.view_offboarding")
def offboarding_avg_duration(request):
    """Average offboarding duration for offboardings archived within the selected period."""
    from offboarding.models import OffboardingEmployee

    from_date, to_date = _parse_period(request)
    avg_days = None
    durations = []
    try:
        archived = OffboardingEmployee.objects.filter(
            stage_id__type="archived",
            notice_period_starts__isnull=False,
            notice_period_ends__gte=from_date,
            notice_period_ends__lte=to_date,
        )
        for oe in archived:
            if oe.notice_period_ends and oe.notice_period_starts:
                delta = (oe.notice_period_ends - oe.notice_period_starts).days
                if delta >= 0:
                    durations.append(delta)
        if durations:
            avg_days = round(sum(durations) / len(durations), 1)
    except Exception:
        pass
    return JsonResponse(
        {
            "avg_days": avg_days,
            "total_archived": len(durations),
        }
    )
