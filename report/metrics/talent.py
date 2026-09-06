"""Talent metrics: recruitment, onboarding, performance."""

from __future__ import annotations

import logging

from django.db.models import Count, Q
from django.utils.translation import gettext as _

from report.engine import ReportFilters, apply_org_filters, empty_report

logger = logging.getLogger(__name__)


def _candidates_in_period(filters: ReportFilters):
    from recruitment.models import Candidate

    qs = Candidate.objects.filter(
        is_active=True,
        created_at__date__gte=filters.from_date,
        created_at__date__lte=filters.to_date,
    )
    if filters.recruitment_id:
        qs = qs.filter(recruitment_id=filters.recruitment_id)
    if filters.gender:
        qs = qs.filter(gender=filters.gender)
    if filters.source:
        qs = qs.filter(source=filters.source)
    if filters.offer_letter_status:
        qs = qs.filter(offer_letter_status=filters.offer_letter_status)
    if filters.job_position_id:
        qs = qs.filter(job_position_id=filters.job_position_id)
    if filters.department_id:
        qs = qs.filter(job_position_id__department_id=filters.department_id)
    if filters.company_id:
        qs = qs.filter(recruitment_id__company_id=filters.company_id)
    return qs


def recruitment_funnel(filters: ReportFilters) -> dict:
    from recruitment.models import Candidate, Recruitment, Stage

    period_cands = _candidates_in_period(filters)
    total = period_cands.count()
    hired = (
        period_cands.filter(Q(hired=True) | Q(stage_id__stage_type="hired"))
        .distinct()
        .count()
    )

    by_stage = list(
        period_cands.filter(stage_id__isnull=False)
        .values("stage_id__stage", "stage_id__stage_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Mutually exclusive source buckets: referral first, then source CharField
    sources = []
    referral_qs = period_cands.filter(referral__isnull=False)
    referral = referral_qs.count()
    if referral:
        sources.append({"source": _("Referral"), "count": referral})
    non_referral = period_cands.filter(referral__isnull=True)
    source_labels = {
        "application": _("Application Form"),
        "software": _("Inside Software"),
        "other": _("Other"),
    }
    for key, label in source_labels.items():
        count = non_referral.filter(source=key).count()
        if count:
            sources.append({"source": label, "count": count})
    other_count = non_referral.exclude(source__in=source_labels.keys()).count()
    if other_count:
        sources.append({"source": _("Unspecified / other"), "count": other_count})

    open_reqs = Recruitment.objects.filter(closed=False)
    if filters.company_id:
        open_reqs = open_reqs.filter(company_id=filters.company_id)
    if filters.recruitment_id:
        open_reqs = open_reqs.filter(id=filters.recruitment_id)
    open_req_count = open_reqs.count()
    conversion = round(hired / total * 100, 1) if total else 0

    return {
        "title": _("Recruitment Funnel"),
        "kpis": [
            {"label": _("Candidates"), "value": total, "hint": _("In period")},
            {"label": _("Hired"), "value": hired, "hint": _("In period")},
            {
                "label": _("Hired / candidates"),
                "value": f"{conversion}%",
                "hint": _("Stage snapshot — not sequential conversion"),
            },
            {"label": _("Open requisitions"), "value": open_req_count, "hint": ""},
        ],
        "charts": [
            {
                "id": "funnel_stages",
                "type": "bar",
                "title": _("Candidates by Stage (snapshot)"),
                "categories": [r["stage_id__stage"] for r in by_stage],
                "series": [
                    {"name": _("Candidates"), "data": [r["count"] for r in by_stage]}
                ],
            },
            {
                "id": "sources",
                "type": "donut",
                "title": _("Source Mix"),
                "categories": [s["source"] for s in sources],
                "series": [
                    {"name": _("Candidates"), "data": [s["count"] for s in sources]}
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "stage", "label": _("Stage")},
                {"key": "type", "label": _("Type")},
                {"key": "count", "label": _("Count")},
            ],
            "rows": [
                {
                    "stage": r["stage_id__stage"],
                    "type": r["stage_id__stage_type"] or "",
                    "count": r["count"],
                }
                for r in by_stage
            ]
            + [
                {
                    "stage": _("Source: %(s)s") % {"s": s["source"]},
                    "type": "",
                    "count": s["count"],
                }
                for s in sources
            ],
        },
        "explorer_url_name": "recruitment-report",
    }


def _median(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2)


def time_to_hire(filters: ReportFilters) -> dict:
    from recruitment.models import Recruitment

    period_candidates = _candidates_in_period(filters)
    recruitments = Recruitment.objects.filter(closed=False)
    if filters.recruitment_id:
        recruitments = recruitments.filter(id=filters.recruitment_id)
    if filters.company_id:
        recruitments = recruitments.filter(company_id=filters.company_id)
    data = []
    all_days: list[int] = []

    for rec in recruitments:
        hired = (
            period_candidates.filter(recruitment_id=rec)
            .filter(Q(hired=True) | Q(stage_id__stage_type="hired"))
            .distinct()
        )
        if not hired.exists():
            continue
        days_list = []
        for c in hired:
            if c.joining_date and c.created_at:
                try:
                    delta = (c.joining_date - c.created_at.date()).days
                    if delta >= 0:
                        days_list.append(delta)
                        all_days.append(delta)
                except Exception:
                    logger.exception("Report metric source unavailable")
        if not days_list:
            continue
        data.append(
            {
                "recruitment": rec.title or str(rec),
                "avg_days": round(sum(days_list) / len(days_list)),
                "hired_count": len(days_list),
                "min_days": min(days_list),
                "max_days": max(days_list),
            }
        )

    # Candidate-weighted overall (not unweighted avg of req avgs)
    overall_avg = round(sum(all_days) / len(all_days)) if all_days else 0
    overall_median = _median(all_days)

    # Open req aging (company-scoped)
    aging = []
    open_qs = Recruitment.objects.filter(closed=False)
    if filters.company_id:
        open_qs = open_qs.filter(company_id=filters.company_id)
    if filters.recruitment_id:
        open_qs = open_qs.filter(id=filters.recruitment_id)
    for rec in open_qs:
        created = getattr(rec, "created_at", None)
        if not created:
            continue
        age = (filters.to_date - created.date()).days
        aging.append(
            {
                "recruitment": rec.title or str(rec),
                "vacancy": rec.vacancy or 0,
                "age_days": age,
            }
        )
    aging.sort(key=lambda x: -x["age_days"])

    return {
        "title": _("Time to Hire / Fill"),
        "kpis": [
            {
                "label": _("Avg days to hire"),
                "value": overall_avg,
                "hint": _("Application → joining (candidate-weighted)"),
            },
            {
                "label": _("Median days to hire"),
                "value": overall_median,
                "hint": _("Application → joining"),
            },
            {
                "label": _("Hires measured"),
                "value": len(all_days),
                "hint": _("With joining_date + created_at"),
            },
            {
                "label": _("Oldest open (days)"),
                "value": aging[0]["age_days"] if aging else 0,
                "hint": _("Open requisitions"),
            },
        ],
        "charts": [
            {
                "id": "tth",
                "type": "bar",
                "title": _("Avg Days to Hire"),
                "categories": [d["recruitment"] for d in data[:12]],
                "series": [
                    {"name": _("Days"), "data": [d["avg_days"] for d in data[:12]]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "recruitment", "label": _("Recruitment")},
                {"key": "avg_days", "label": _("Avg Days")},
                {"key": "hired_count", "label": _("Hired")},
                {"key": "age_days", "label": _("Open Age (days)")},
                {"key": "vacancy", "label": _("Vacancy")},
            ],
            "rows": [
                {
                    "recruitment": d["recruitment"],
                    "avg_days": d["avg_days"],
                    "hired_count": d["hired_count"],
                    "age_days": "",
                    "vacancy": "",
                }
                for d in data
            ]
            + [
                {
                    "recruitment": a["recruitment"],
                    "avg_days": "",
                    "hired_count": "",
                    "age_days": a["age_days"],
                    "vacancy": a["vacancy"],
                }
                for a in aging[:30]
            ],
        },
        "explorer_url_name": "recruitment-report",
    }


def offer_acceptance(filters: ReportFilters) -> dict:
    candidates = _candidates_in_period(filters)
    status_counts = list(
        candidates.values("offer_letter_status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    labels = dict(
        [
            ("not_sent", _("Not Sent")),
            ("sent", _("Sent")),
            ("accepted", _("Accepted")),
            ("rejected", _("Rejected")),
            ("joined", _("Joined")),
        ]
    )
    sent = candidates.filter(
        offer_letter_status__in=["sent", "accepted", "rejected", "joined"]
    ).count()
    accepted = candidates.filter(offer_letter_status__in=["accepted", "joined"]).count()
    rejected = candidates.filter(offer_letter_status="rejected").count()
    rate = round(accepted / sent * 100, 1) if sent else 0

    rows = [
        {
            "status": labels.get(
                r["offer_letter_status"], r["offer_letter_status"] or _("Unknown")
            ),
            "count": r["count"],
        }
        for r in status_counts
    ]

    return {
        "title": _("Offer & Acceptance"),
        "kpis": [
            {"label": _("Offers touched"), "value": sent, "hint": _("Sent or decided")},
            {"label": _("Accepted / joined"), "value": accepted, "hint": ""},
            {"label": _("Rejected"), "value": rejected, "hint": ""},
            {
                "label": _("Acceptance rate"),
                "value": f"{rate}%",
                "hint": _("Accepted÷sent"),
            },
        ],
        "charts": [
            {
                "id": "offer_status",
                "type": "donut",
                "title": _("Offer Letter Status"),
                "categories": [r["status"] for r in rows],
                "series": [
                    {"name": _("Candidates"), "data": [r["count"] for r in rows]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "status", "label": _("Status")},
                {"key": "count", "label": _("Count")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "recruitment-report",
    }


def onboarding_progress(filters: ReportFilters) -> dict:
    from django.apps import apps

    if not apps.is_installed("onboarding"):
        return {
            "title": _("Onboarding Progress"),
            "kpis": [],
            "charts": [],
            "table": {"columns": [], "rows": []},
            "message": _("Onboarding app is not installed."),
        }

    from onboarding.models import CandidateStage, CandidateTask
    from recruitment.models import Candidate

    candidates = Candidate.objects.filter(
        start_onboard=True,
        created_at__date__gte=filters.from_date,
        created_at__date__lte=filters.to_date,
    )
    if filters.company_id:
        candidates = candidates.filter(recruitment_id__company_id=filters.company_id)
    if filters.recruitment_id:
        candidates = candidates.filter(recruitment_id=filters.recruitment_id)
    total = candidates.count()
    cand_ids = list(candidates.values_list("id", flat=True))

    stage_rows = list(
        CandidateStage.objects.filter(candidate_id__in=cand_ids)
        .values("onboarding_stage_id__stage_title")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    task_status = list(
        CandidateTask.objects.filter(candidate_id__in=cand_ids)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    completed_tasks = sum(
        t["count"] for t in task_status if str(t.get("status", "")).lower() == "done"
    )
    total_tasks = sum(t["count"] for t in task_status)
    completion = round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0

    return {
        "title": _("Onboarding Progress"),
        "kpis": [
            {
                "label": _("Onboardees (period)"),
                "value": total,
                "hint": _("start_onboard candidates in period"),
            },
            {
                "label": _("Task completion"),
                "value": f"{completion}%",
                "hint": _("Tasks for period onboardees only"),
            },
            {
                "label": _("Total tasks"),
                "value": total_tasks,
                "hint": _("Scoped to period"),
            },
            {
                "label": _("Stages tracked"),
                "value": len(stage_rows),
                "hint": "",
            },
        ],
        "charts": [
            {
                "id": "onboard_stages",
                "type": "bar",
                "title": _("Candidates by Onboarding Stage"),
                "categories": [
                    r["onboarding_stage_id__stage_title"] or _("Unknown")
                    for r in stage_rows
                ],
                "series": [
                    {"name": _("Candidates"), "data": [r["count"] for r in stage_rows]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "item", "label": _("Item")},
                {"key": "status", "label": _("Status / Stage")},
                {"key": "count", "label": _("Count")},
            ],
            "rows": [
                {
                    "item": _("Stage"),
                    "status": r["onboarding_stage_id__stage_title"] or _("Unknown"),
                    "count": r["count"],
                }
                for r in stage_rows
            ]
            + [
                {
                    "item": _("Task"),
                    "status": t.get("status") or _("Unknown"),
                    "count": t["count"],
                }
                for t in task_status
            ],
        },
        "explorer_url_name": "recruitment-report",
    }


def performance_distribution(filters: ReportFilters) -> dict:
    """Objective & KR health — not a performance rating curve."""
    from django.db.models import DateField, DateTimeField

    from pms.models import EmployeeKeyResult, EmployeeObjective
    from report.engine import apply_org_filters

    def _period_filter(qs, model):
        # created_at is nullable and auto_now_add, so bulk_create()d rows have
        # no date at all. A plain range filter drops those from EVERY window,
        # not just this one -- they become permanently invisible. Keep them:
        # an undated record is better shown than silently discarded, and here
        # the undated rows carry the only non-"Not Started" statuses, so
        # excluding them turned the chart into a flat, misleading single bar.
        from django.db.models import Q

        field = model._meta.get_field("created_at")
        undated = Q(created_at__isnull=True)
        if isinstance(field, DateTimeField):
            return qs.filter(
                undated
                | Q(
                    created_at__date__gte=filters.from_date,
                    created_at__date__lte=filters.to_date,
                )
            )
        if isinstance(field, DateField):
            return qs.filter(
                undated
                | Q(
                    created_at__gte=filters.from_date,
                    created_at__lte=filters.to_date,
                )
            )
        return qs

    objectives = _period_filter(
        EmployeeObjective.objects.filter(archive=False), EmployeeObjective
    )
    objectives = apply_org_filters(
        objectives,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    obj_status = list(
        objectives.values("status").annotate(count=Count("id")).order_by("-count")
    )

    # Progress bands on objectives
    bands = {"0–25": 0, "26–50": 0, "51–75": 0, "76–100": 0}
    for pct in objectives.values_list("progress_percentage", flat=True):
        p = int(pct or 0)
        if p <= 25:
            bands["0–25"] += 1
        elif p <= 50:
            bands["26–50"] += 1
        elif p <= 75:
            bands["51–75"] += 1
        else:
            bands["76–100"] += 1

    kr_qs = _period_filter(EmployeeKeyResult.objects.all(), EmployeeKeyResult)
    kr_qs = apply_org_filters(
        kr_qs,
        filters,
        prefix="employee_objective_id__employee_id__employee_work_info",
        employee_prefix="employee_objective_id__employee_id",
    )
    kr_status = list(
        kr_qs.values("status").annotate(count=Count("id")).order_by("-count")
    )

    def labelize(rows, prefix):
        return [
            {
                "category": prefix,
                "status": r["status"] or _("Unknown"),
                "count": r["count"],
            }
            for r in rows
        ]

    band_rows = [
        {"category": _("Progress"), "status": k, "count": v} for k, v in bands.items()
    ]

    return {
        "title": _("Objective & KR Health"),
        "kpis": [
            {
                "label": _("Objectives"),
                "value": sum(r["count"] for r in obj_status),
                "hint": _("In period (org-scoped)"),
            },
            {
                "label": _("Key results"),
                "value": sum(r["count"] for r in kr_status),
                "hint": "",
            },
            {
                "label": _("On track"),
                "value": next(
                    (r["count"] for r in obj_status if r["status"] == "On Track"), 0
                ),
                "hint": _("Objective status"),
            },
            {
                "label": _("Behind / at risk"),
                "value": sum(
                    r["count"]
                    for r in obj_status
                    if r["status"] in ("Behind", "At Risk")
                ),
                "hint": _("Needs attention"),
            },
        ],
        "charts": [
            {
                "id": "obj_progress",
                "type": "bar",
                "title": _("Objective progress bands"),
                "categories": list(bands.keys()),
                "series": [{"name": _("Objectives"), "data": list(bands.values())}],
            },
            {
                "id": "obj_status",
                "type": "donut",
                "title": _("Objective Status"),
                "categories": [r["status"] or _("Unknown") for r in obj_status],
                "series": [
                    {"name": _("Count"), "data": [r["count"] for r in obj_status]}
                ],
            },
            {
                "id": "kr_status",
                "type": "bar",
                "title": _("Key Result Status"),
                "categories": [r["status"] or _("Unknown") for r in kr_status],
                "series": [
                    {"name": _("Count"), "data": [r["count"] for r in kr_status]}
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "category", "label": _("Category")},
                {"key": "status", "label": _("Status / Band")},
                {"key": "count", "label": _("Count")},
            ],
            "rows": (
                band_rows
                + labelize(obj_status, _("Objective"))
                + labelize(kr_status, _("Key Result"))
            ),
        },
        "explorer_url_name": "pms-report",
    }


def quality_of_hire(filters: ReportFilters) -> dict:
    """
    90-day retention of hired candidates who joined in the period.

    Uses Candidate.joining_date + hired flag; retention = no exit within 90 days
    (or employee still active). Does not invent quality scores.
    """
    from datetime import timedelta

    from report.formulas import retention_rate
    from report.metrics._exits import iter_exits

    period_candidates = _candidates_in_period(filters)
    hired = (
        period_candidates.filter(Q(hired=True) | Q(stage_id__stage_type="hired"))
        .filter(joining_date__gte=filters.from_date, joining_date__lte=filters.to_date)
        .distinct()
    )
    hired_list = list(
        hired.values(
            "id",
            "name",
            "joining_date",
            "source",
            "converted_employee_id",
            "recruitment_id__title",
        )[:500]
    )
    total = len(hired_list)
    if not total:
        # Fallback: employees joined in period (no candidate link required)
        from employee.models import EmployeeWorkInformation

        wi = EmployeeWorkInformation.objects.filter(
            date_joining__gte=filters.from_date,
            date_joining__lte=filters.to_date,
        )
        # Retention is measured against the whole joiner cohort, leavers
        # included. apply_org_filters defaults to active-only, which dropped
        # exactly the people who did not stay and biased the rate upward.
        wi = apply_org_filters(
            wi,
            filters,
            prefix="",
            employee_prefix="employee_id",
            apply_employment_status=False,
        )
        hired_list = [
            {
                "id": None,
                "name": (
                    f"{r.employee_id.employee_first_name} {r.employee_id.employee_last_name or ''}".strip()
                    if r.employee_id
                    else ""
                ),
                "joining_date": r.date_joining,
                "source": "employee_joining",
                "converted_employee_id": r.employee_id_id,
                "recruitment_id__title": "",
            }
            for r in wi.select_related("employee_id")[:500]
        ]
        total = len(hired_list)

    if not total:
        return empty_report(
            _("Quality of Hire (90-day retention)"),
            filters,
            _("No hires with joining dates in the selected period."),
        )

    exit_horizon = filters.to_date + timedelta(days=90)
    exits = iter_exits(filters, from_date=filters.from_date, to_date=exit_horizon)
    exit_by_emp = {r["employee_id"]: r for r in exits}

    retained_rows = []
    early_exit_rows = []
    for h in hired_list:
        joining = h.get("joining_date")
        emp_id = h.get("converted_employee_id")
        if not joining:
            continue
        exited_early = False
        exit_info = ""
        if emp_id and emp_id in exit_by_emp:
            er = exit_by_emp[emp_id]
            if (er["exit_date"] - joining).days <= 90:
                exited_early = True
                exit_info = f"{er['exit_date'].isoformat()} ({er['source']})"
        row = {
            "name": h.get("name") or "",
            "joined": joining.isoformat(),
            "recruitment": h.get("recruitment_id__title") or "",
            "source": h.get("source") or "",
            "outcome": _("Early exit") if exited_early else _("Retained 90d+"),
            "exit": exit_info,
        }
        if exited_early:
            early_exit_rows.append(row)
        else:
            retained_rows.append(row)

    retained = len(retained_rows)
    rate = retention_rate(retained, total)
    return {
        "title": _("Quality of Hire (90-day retention)"),
        "kpis": [
            {
                "label": _("90-day retention"),
                "value": f"{rate}%",
                "hint": _("No exit within 90 days of joining"),
            },
            {
                "label": _("Hires measured"),
                "value": total,
                "hint": _("With joining_date"),
            },
            {"label": _("Retained"), "value": retained, "hint": ""},
            {
                "label": _("Early exits"),
                "value": len(early_exit_rows),
                "hint": _("≤ 90 days"),
            },
        ],
        "charts": [
            {
                "id": "qoh",
                "type": "donut",
                "title": _("90-day outcomes"),
                "categories": [_("Retained"), _("Early exit")],
                "series": [
                    {
                        "name": _("Hires"),
                        "data": [retained, len(early_exit_rows)],
                    }
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "name", "label": _("Name")},
                {"key": "joined", "label": _("Joined")},
                {"key": "recruitment", "label": _("Recruitment")},
                {"key": "source", "label": _("Source")},
                {"key": "outcome", "label": _("Outcome")},
                {"key": "exit", "label": _("Exit")},
            ],
            "rows": (early_exit_rows + retained_rows)[:100],
        },
        "explorer_url_name": "recruitment-report",
    }


def recruitment_funnel_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Drill recruitment funnel by stage name or source label."""
    from report.drilldown import candidate_link, drilldown_payload, empty_drilldown

    dimension = (params.get("dimension") or "stage").strip().lower()
    value = (params.get("value") or "").strip()
    if not value:
        return empty_drilldown(
            _("Recruitment Funnel"), dimension, value, _("Missing dimension value.")
        )

    qs = _candidates_in_period(filters)
    # Candidates are not employee-subordinate scoped the same way; keep org filters only.
    title = _("Recruitment Funnel")
    if dimension in ("stage", "funnel_stages"):
        qs = qs.filter(stage_id__stage=value)
        dimension = "stage"
        title = _("Candidates · stage %(s)s") % {"s": value}
    elif dimension in ("source", "sources"):
        # Reverse display labels used in recruitment_funnel
        source_map = {
            str(_("Application Form")): "application",
            str(_("Inside Software")): "software",
            str(_("Other")): "other",
            "Application Form": "application",
            "Inside Software": "software",
            "Other": "other",
            "application": "application",
            "software": "software",
            "other": "other",
        }
        if value in (str(_("Referral")), "Referral"):
            qs = qs.filter(referral__isnull=False)
        else:
            key = source_map.get(value, value)
            qs = qs.filter(source=key)
        dimension = "source"
        title = _("Candidates · source %(s)s") % {"s": value}
    else:
        return empty_drilldown(title, dimension, value, _("Unsupported dimension."))

    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    total = qs.count()
    rows = []
    for cand in qs.select_related("stage_id", "recruitment_id").order_by("-created_at")[
        :limit
    ]:
        rows.append(
            {
                "candidate": str(cand),
                "stage": getattr(getattr(cand, "stage_id", None), "stage", "") or "",
                "source": cand.source or "",
                "hired": _("Yes") if getattr(cand, "hired", False) else _("No"),
                "link": candidate_link(cand.id),
            }
        )
    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "candidate", "label": _("Candidate")},
            {"key": "stage", "label": _("Stage")},
            {"key": "source", "label": _("Source")},
            {"key": "hired", "label": _("Hired")},
            {"key": "link", "label": _("Open"), "type": "link"},
        ],
        rows=rows,
        truncated=total > len(rows),
    )
