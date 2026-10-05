"""
Modern onboarding dashboard views — KPI summary + ApexCharts.

Accessible at /onboarding/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from horilla.methods import handle_no_permission


def _has_onboarding_permission(request):
    """Return True if the user may access the onboarding dashboard."""
    user = request.user
    if user.is_superuser or user.has_perm("onboarding.view_onboardingstage"):
        return True
    try:
        employee = user.employee_get
        return (
            employee.onboardingstage_set.all().exists()
            or employee.onboarding_task.all().exists()
        )
    except Exception:
        return False


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


def _onboarding_candidates_in_period(request):
    """Return Candidate queryset (start_onboard=True) filtered to the requested period."""
    from recruitment.models import Candidate

    from_date, to_date = _parse_period(request)
    return Candidate.objects.filter(
        start_onboard=True,
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    )


@login_required
def onboarding_dashboard_view(request):
    """Render the modern onboarding dashboard page."""
    if not _has_onboarding_permission(request):
        return handle_no_permission(request)
    return render(request, "onboarding/dashboard.html")


@login_required
def onboarding_kpi_data(request):
    """Return onboarding KPI summary data as JSON."""
    if not _has_onboarding_permission(request):
        return JsonResponse({"no_permission": True})
    from onboarding.models import CandidateStage, CandidateTask, OnboardingPortal

    # "Onboarding" tile: every candidate actually sitting in a pipeline
    # stage (a CandidateStage row), not scoped to the selected period --
    # that's a standing state, not a one-time event tied to when the
    # candidate record was created, and the vast majority of them predate
    # this month. start_onboard=True is NOT a reliable proxy for this: a
    # candidate can be added to the pipeline (fixture data, or the "safe
    # onboarding stage insert" fallback in email_send) without that flag
    # ever getting set, which left this tile undercounting against what
    # the Pipeline board itself shows. Already-converted-to-employee
    # candidates are excluded -- they've left the candidate pipeline for
    # good, same exclusion email_send itself applies before sending a
    # portal link.
    onboard_stages = CandidateStage.objects.exclude(
        candidate_id__converted_employee_id__isnull=False
    )
    total_candidates = onboard_stages.count()
    completed_all_time = onboard_stages.filter(
        onboarding_stage_id__is_final_stage=True
    ).count()
    completion_rate = (
        round((completed_all_time / total_candidates * 100), 1)
        if total_candidates > 0
        else 0
    )

    # Portal link sent, but the candidate hasn't finished the onboarding
    # portal flow yet (used flips to True only once they reach the very
    # end -- see employee_bank_details_save in onboarding/views.py).
    portal_sent = OnboardingPortal.objects.count()
    portal_incomplete = OnboardingPortal.objects.filter(used=False).count()

    # Task stats — every pipeline candidate's checklist, all-time (same
    # population as the "Onboarding Candidates"/"Candidate Rate In Final
    # Stage" tiles above), not just whoever was created this month.
    pipeline_tasks = CandidateTask.objects.filter(
        candidate_id__in=onboard_stages.values("candidate_id")
    )
    total_tasks = pipeline_tasks.count()
    stuck_tasks = pipeline_tasks.filter(status="stuck").count()

    return JsonResponse(
        {
            "total_candidates": total_candidates,
            "portal_sent": portal_sent,
            "portal_incomplete": portal_incomplete,
            "completed_all_time": completed_all_time,
            "completion_rate": completion_rate,
            "total_tasks": total_tasks,
            "stuck_tasks": stuck_tasks,
        }
    )


@login_required
def onboarding_by_job_position(request):
    """Candidates onboarding per job position.

    Every candidate currently in the pipeline (a CandidateStage row),
    all-time -- same population as the "Onboarding Candidates"/"Task
    Completion"/"Final Stage By Position" cards on this same dashboard,
    not just whoever happened to be added this calendar month.
    """
    if not _has_onboarding_permission(request):
        return JsonResponse({"no_permission": True})
    from onboarding.models import CandidateStage

    positions = []

    try:
        data = (
            CandidateStage.objects.exclude(
                candidate_id__converted_employee_id__isnull=False
            )
            .values(
                "candidate_id__job_position_id",
                "candidate_id__job_position_id__job_position",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            pos = item["candidate_id__job_position_id__job_position"]
            pos_id = item["candidate_id__job_position_id"]
            if pos:
                positions.append(
                    {"position": pos, "position_id": pos_id, "count": item["count"]}
                )
    except Exception:
        pass

    return JsonResponse({"positions": positions})


@login_required
def onboarding_task_managers(request):
    """Task assignment by manager (logged-in user's tasks), scoped to the selected period."""
    if not _has_onboarding_permission(request):
        return JsonResponse({"no_permission": True})
    from onboarding.models import CandidateTask, OnboardingTask

    tasks = []

    try:
        user_emp = getattr(request.user, "employee_get", None)
        if user_emp:
            period_candidates = _onboarding_candidates_in_period(request)
            task_qs = OnboardingTask.objects.filter(
                employee_id=user_emp,
            ).order_by("stage_id__sequence")

            for task in task_qs[:10]:
                ct_base = CandidateTask.objects.filter(
                    onboarding_task_id=task,
                    candidate_id__in=period_candidates,
                )
                total = ct_base.count()
                if total == 0:
                    continue
                done = ct_base.filter(status="done").count()
                stuck = ct_base.filter(status="stuck").count()

                tasks.append(
                    {
                        "title": task.task_title,
                        "stage": task.stage_id.stage_title if task.stage_id else "—",
                        "total": total,
                        "done": done,
                        "stuck": stuck,
                        "progress": round((done / total * 100)) if total > 0 else 0,
                    }
                )
    except Exception:
        pass

    return JsonResponse({"tasks": tasks})


@login_required
def onboarding_completion_trend(request):
    """Candidates in the final onboarding stage, for active recruitments,
    broken down by job position -- not time-windowed, since this reads as
    a current snapshot ("who's finished, where") rather than a trend.

    Includes every job position open on an active recruitment, not just
    ones with a nonzero count -- a single-category result renders as a
    lone dot with nothing to draw a line to, which defeats the point of
    a line chart. Zero-filling the rest gives it an actual line to draw.
    """
    if not _has_onboarding_permission(request):
        return JsonResponse({"no_permission": True})
    from onboarding.models import CandidateStage
    from recruitment.models import JobPosition, Recruitment

    active_recruitment_ids = Recruitment.objects.filter(
        closed=False, is_active=True
    ).values("id")
    position_qs = (
        JobPosition.objects.filter(open_positions__in=active_recruitment_ids)
        .distinct()
        .order_by("job_position")
    )

    final_stage_counts = dict(
        CandidateStage.objects.filter(
            onboarding_stage_id__is_final_stage=True,
            candidate_id__recruitment_id__closed=False,
            candidate_id__recruitment_id__is_active=True,
        )
        .exclude(candidate_id__converted_employee_id__isnull=False)
        .values("candidate_id__job_position_id")
        .annotate(count=Count("id"))
        .values_list("candidate_id__job_position_id", "count")
    )

    positions = [
        {
            "position": jp.job_position,
            "position_id": jp.id,
            "count": final_stage_counts.get(jp.id, 0),
        }
        for jp in position_qs
    ]
    return JsonResponse({"positions": positions})
