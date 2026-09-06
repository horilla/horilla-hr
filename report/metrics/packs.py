"""
Phase 7 pack expansion — org design, talent quality, compliance aging, OT concentration.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.apps import apps
from django.db.models import Count, Sum
from django.utils.translation import gettext as _

from report.engine import ReportFilters, apply_org_filters, empty_report

logger = logging.getLogger(__name__)


def span_of_control(filters: ReportFilters) -> dict:
    """Managers and average direct reports (org design)."""
    from employee.models import Employee, EmployeeWorkInformation

    managers = apply_org_filters(
        EmployeeWorkInformation.objects.filter(reporting_manager_id__isnull=False),
        filters,
        prefix="",
        employee_prefix="employee_id",
    )
    # Count reports per manager among filtered employees
    report_counts = list(
        managers.values(
            "reporting_manager_id",
            "reporting_manager_id__employee_first_name",
            "reporting_manager_id__employee_last_name",
        )
        .annotate(direct_reports=Count("employee_id", distinct=True))
        .order_by("-direct_reports")
    )
    manager_count = len(report_counts)
    total_reports = sum(r["direct_reports"] for r in report_counts)
    avg_span = round(total_reports / manager_count, 1) if manager_count else 0

    active = apply_org_filters(
        Employee.objects.filter(is_active=True),
        filters,
        prefix="employee_work_info",
        employee_prefix="",
    ).count()
    manager_ratio = round(manager_count / active * 100, 1) if active else 0

    rows = []
    for r in report_counts[:50]:
        first = r.get("reporting_manager_id__employee_first_name") or ""
        last = r.get("reporting_manager_id__employee_last_name") or ""
        rows.append(
            {
                "manager": f"{first} {last}".strip() or str(r["reporting_manager_id"]),
                "direct_reports": r["direct_reports"],
            }
        )

    return {
        "title": _("Span of Control"),
        "kpis": [
            {
                "label": _("Managers"),
                "value": manager_count,
                "hint": _("With ≥1 report"),
            },
            {
                "label": _("Avg span"),
                "value": avg_span,
                "hint": _("Direct reports / manager"),
            },
            {
                "label": _("Manager ratio"),
                "value": f"{manager_ratio}%",
                "hint": _("Managers / active headcount"),
            },
            {"label": _("Active headcount"), "value": active, "hint": ""},
        ],
        "charts": [
            {
                "id": "span_managers",
                "type": "bar",
                "title": _("Direct reports by manager"),
                "categories": [r["manager"] for r in rows[:12]],
                "series": [
                    {
                        "name": _("Direct reports"),
                        "data": [r["direct_reports"] for r in rows[:12]],
                    }
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "manager", "label": _("Manager")},
                {"key": "direct_reports", "label": _("Direct reports")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "employee-report",
    }


def pipeline_aging(filters: ReportFilters) -> dict:
    """How long candidates sit in each stage (talent)."""
    from django.utils import timezone

    from recruitment.models import Candidate

    qs = Candidate.objects.filter(is_active=True, hired=False)
    if filters.recruitment_id:
        qs = qs.filter(recruitment_id=filters.recruitment_id)
    if filters.company_id:
        qs = qs.filter(recruitment_id__company_id=filters.company_id)
    if filters.department_id:
        qs = qs.filter(job_position_id__department_id=filters.department_id)

    today = timezone.now().date()
    buckets = Counter()
    by_stage = defaultdict(list)
    rows = []
    for cand in qs.select_related("stage_id", "recruitment_id")[:500]:
        created = cand.created_at.date() if cand.created_at else today
        age = max((today - created).days, 0)
        if age <= 7:
            buckets["0–7"] += 1
        elif age <= 14:
            buckets["8–14"] += 1
        elif age <= 30:
            buckets["15–30"] += 1
        else:
            buckets["31+"] += 1
        stage = getattr(getattr(cand, "stage_id", None), "stage", None) or _("Unknown")
        by_stage[stage].append(age)
        if len(rows) < 100:
            rows.append(
                {
                    "candidate": str(cand),
                    "stage": stage,
                    "age_days": age,
                    "recruitment": str(getattr(cand, "recruitment_id", "") or ""),
                }
            )

    stage_avg = [
        {
            "stage": stage,
            "avg_days": round(sum(ages) / len(ages), 1),
            "count": len(ages),
        }
        for stage, ages in sorted(by_stage.items(), key=lambda x: -len(x[1]))
    ]
    total = sum(buckets.values())
    stale = buckets.get("31+", 0)

    if not total:
        return empty_report(
            _("Pipeline Aging"),
            filters,
            _("No open candidates in pipeline."),
        )

    return {
        "title": _("Pipeline Aging"),
        "kpis": [
            {"label": _("Open candidates"), "value": total, "hint": _("Not hired")},
            {"label": _("Stale 31+ days"), "value": stale, "hint": _("Aging risk")},
            {
                "label": _("Avg age (days)"),
                "value": (
                    round(sum(r["age_days"] for r in rows) / len(rows), 1)
                    if rows
                    else 0
                ),
                "hint": _("Sample listed"),
            },
            {"label": _("Stages"), "value": len(stage_avg), "hint": ""},
        ],
        "charts": [
            {
                "id": "age_buckets",
                "type": "donut",
                "title": _("Age since application"),
                "categories": list(buckets.keys()),
                "series": [{"name": _("Candidates"), "data": list(buckets.values())}],
            },
            {
                "id": "stage_avg",
                "type": "bar",
                "title": _("Avg age since application by stage"),
                "categories": [r["stage"] for r in stage_avg[:12]],
                "series": [
                    {
                        "name": _("Avg days"),
                        "data": [r["avg_days"] for r in stage_avg[:12]],
                    }
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "candidate", "label": _("Candidate")},
                {"key": "stage", "label": _("Stage")},
                {"key": "age_days", "label": _("Age (days)")},
                {"key": "recruitment", "label": _("Recruitment")},
            ],
            "rows": sorted(rows, key=lambda r: -r["age_days"]),
        },
        "explorer_url_name": "recruitment-report",
    }


def source_quality(filters: ReportFilters) -> dict:
    """Hire conversion by candidate source (talent) — mutually exclusive buckets."""
    from recruitment.models import Candidate

    qs = Candidate.objects.filter(
        is_active=True,
        created_at__date__gte=filters.from_date,
        created_at__date__lte=filters.to_date,
    )
    if filters.recruitment_id:
        qs = qs.filter(recruitment_id=filters.recruitment_id)
    if filters.company_id:
        qs = qs.filter(recruitment_id__company_id=filters.company_id)

    source_labels = {
        "application": _("Application Form"),
        "software": _("Inside Software"),
        "other": _("Other"),
    }

    def _hired_count(subset):
        hired_ids = set(subset.filter(hired=True).values_list("id", flat=True)) | set(
            subset.filter(stage_id__stage_type="hired").values_list("id", flat=True)
        )
        return len(hired_ids)

    rows = []
    # Referral first (exclusive); remaining candidates bucketed by source CharField
    referral_qs = qs.filter(referral__isnull=False)
    referral_total = referral_qs.count()
    if referral_total:
        hired = _hired_count(referral_qs)
        rate = round(hired / referral_total * 100, 1)
        rows.append(
            {
                "source": str(_("Referral")),
                "candidates": referral_total,
                "hired": hired,
                "accept_rate": f"{rate}%",
                "rate_num": rate,
            }
        )

    non_referral = qs.filter(referral__isnull=True)
    for key, label in source_labels.items():
        subset = non_referral.filter(source=key)
        total = subset.count()
        if not total:
            continue
        hired = _hired_count(subset)
        rate = round(hired / total * 100, 1)
        rows.append(
            {
                "source": str(label),
                "candidates": total,
                "hired": hired,
                "accept_rate": f"{rate}%",
                "rate_num": rate,
            }
        )
    other_qs = non_referral.exclude(source__in=source_labels.keys())
    other_total = other_qs.count()
    if other_total:
        hired = _hired_count(other_qs)
        rate = round(hired / other_total * 100, 1)
        rows.append(
            {
                "source": str(_("Unspecified / other")),
                "candidates": other_total,
                "hired": hired,
                "accept_rate": f"{rate}%",
                "rate_num": rate,
            }
        )

    if not rows:
        return empty_report(
            _("Source Quality"),
            filters,
            _("No candidates in period."),
        )

    best = max(rows, key=lambda r: r["rate_num"])
    return {
        "title": _("Source Quality"),
        "kpis": [
            {
                "label": _("Sources"),
                "value": len(rows),
                "hint": _("Mutually exclusive"),
            },
            {
                "label": _("Best source"),
                "value": best["source"],
                "hint": best["accept_rate"],
            },
            {
                "label": _("Candidates"),
                "value": sum(r["candidates"] for r in rows),
                "hint": _("In period (no double-count)"),
            },
            {
                "label": _("Hired"),
                "value": sum(r["hired"] for r in rows),
                "hint": "",
            },
        ],
        "charts": [
            {
                "id": "source_rate",
                "type": "bar",
                "title": _("Hire rate by source"),
                "categories": [r["source"] for r in rows],
                "series": [
                    {"name": _("% hired"), "data": [r["rate_num"] for r in rows]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "source", "label": _("Source")},
                {"key": "candidates", "label": _("Candidates")},
                {"key": "hired", "label": _("Hired")},
                {"key": "accept_rate", "label": _("Hire rate")},
            ],
            "rows": [{k: v for k, v in r.items() if k != "rate_num"} for r in rows],
        },
        "explorer_url_name": "recruitment-report",
    }


def document_expiry_aging(filters: ReportFilters) -> dict:
    """Documents aging toward expiry (compliance) — buckets relative to today."""
    today = date.today()
    horizon = today + timedelta(days=90)
    buckets = {"overdue": 0, "0–30": 0, "31–60": 0, "61–90": 0}
    rows = []
    # Row list cap. The aging buckets and KPIs are computed over the whole
    # queryset, so this limits only what the table shows.
    ROW_CAP = 200
    matched = 0

    def _bucket(exp: date):
        if exp < today:
            return "overdue"
        days = (exp - today).days
        if days <= 30:
            return "0–30"
        if days <= 60:
            return "31–60"
        return "61–90"

    if apps.is_installed("horilla_documents"):
        try:
            Document = apps.get_model("horilla_documents", "Document")
            qs = Document.objects.filter(
                expiry_date__lte=horizon,
                expiry_date__isnull=False,
            )
            qs = apply_org_filters(
                qs,
                filters,
                prefix="employee_id__employee_work_info",
                employee_prefix="employee_id",
            )
            # Bucket every match, but only list the first ROW_CAP of them.
            # These loops used to be one: the aging buckets were built inside
            # the row slice, so past the cap the KPI totals themselves were
            # wrong -- not merely the table under them.
            for exp in qs.values_list("expiry_date", flat=True):
                if exp:
                    b = _bucket(exp)
                    buckets[b] = buckets.get(b, 0) + 1
            matched += qs.count()

            for obj in qs.select_related("employee_id")[:ROW_CAP]:
                exp = obj.expiry_date
                if not exp:
                    continue
                emp = getattr(obj, "employee_id", None)
                rows.append(
                    {
                        "source": "horilla_documents.Document",
                        "title": str(obj),
                        "employee": emp.get_full_name() if emp else "",
                        "expiry": exp.isoformat(),
                        "bucket": _bucket(exp),
                    }
                )
        except Exception:
            # A source that fails silently shrinks the report into a
            # smaller, apparently valid number. Log it.
            logger.exception("Report metric source unavailable")

    total = sum(buckets.values())
    if not total:
        return empty_report(
            _("Document Expiry Aging"),
            filters,
            _("No documents expiring in the next 90 days."),
        )

    labels = {
        "overdue": _("Overdue"),
        "0–30": _("0–30 days"),
        "31–60": _("31–60 days"),
        "61–90": _("61–90 days"),
    }
    return {
        "title": _("Document Expiry Aging"),
        "kpis": [
            {
                "label": _("Items tracked"),
                "value": total,
                "hint": _("≤90 days / overdue"),
            },
            {"label": _("Overdue"), "value": buckets["overdue"], "hint": ""},
            {"label": _("Due ≤30 days"), "value": buckets["0–30"], "hint": ""},
            {
                "label": _("Listed below"),
                "value": len(rows),
                "hint": (
                    _("Sample — %(shown)s of %(total)s")
                    % {"shown": len(rows), "total": matched}
                    if matched > len(rows)
                    else _("Complete list")
                ),
            },
        ],
        "charts": [
            {
                "id": "expiry_buckets",
                "type": "donut",
                "title": _("Expiry buckets"),
                "categories": [str(labels[k]) for k in buckets],
                "series": [{"name": _("Items"), "data": list(buckets.values())}],
            }
        ],
        "table": {
            "columns": [
                {"key": "source", "label": _("Source")},
                {"key": "title", "label": _("Item")},
                {"key": "employee", "label": _("Employee")},
                {"key": "expiry", "label": _("Expiry")},
                {"key": "bucket", "label": _("Bucket")},
            ],
            "rows": rows,
            # KPIs count every match; the list is capped. Say so, or the
            # export inherits the cap with no indication.
            "truncated": matched > len(rows),
            "total_rows": matched,
        },
    }


def ot_concentration(filters: ReportFilters) -> dict:
    """Share of OT concentrated in top employees / departments (time)."""
    from attendance.models import Attendance
    from report.formulas import ot_concentration_share
    from report.metrics._privacy import allow_named_ot_rows

    att_qs = Attendance.objects.filter(
        attendance_date__gte=filters.from_date,
        attendance_date__lte=filters.to_date,
        overtime_second__gt=0,
    )
    att_qs = apply_org_filters(
        att_qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    by_emp = list(
        att_qs.values(
            "employee_id",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__employee_work_info__department_id__department",
        )
        .annotate(total_seconds=Sum("overtime_second"))
        .order_by("-total_seconds")
    )
    total = sum(r["total_seconds"] or 0 for r in by_emp)
    if not total:
        return empty_report(
            _("OT Concentration"),
            filters,
            _("No overtime recorded in period."),
        )

    top5 = by_emp[:5]
    top10 = by_emp[:10]
    concentration = ot_concentration_share(
        sum(r["total_seconds"] or 0 for r in top5), total
    )
    concentration10 = ot_concentration_share(
        sum(r["total_seconds"] or 0 for r in top10), total
    )

    include_names = allow_named_ot_rows(filters)

    # Default: department aggregates (culture-safe)
    by_dept = list(
        att_qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values("employee_id__employee_work_info__department_id__department")
        .annotate(total_seconds=Sum("overtime_second"))
        .order_by("-total_seconds")[:20]
    )
    dept_rows = [
        {
            "department": r[
                "employee_id__employee_work_info__department_id__department"
            ]
            or "",
            "ot_hours": round((r["total_seconds"] or 0) / 3600, 1),
            "share": f"{ot_concentration_share(r['total_seconds'] or 0, total)}%",
        }
        for r in by_dept
    ]

    charts = [
        {
            "id": "ot_dept",
            "type": "bar",
            "title": _("OT Hours by Department"),
            "categories": [r["department"] for r in dept_rows[:12]],
            "series": [
                {"name": _("OT Hours"), "data": [r["ot_hours"] for r in dept_rows[:12]]}
            ],
        }
    ]
    table = {
        "columns": [
            {"key": "department", "label": _("Department")},
            {"key": "ot_hours", "label": _("OT Hours")},
            {"key": "share", "label": _("Share")},
        ],
        "rows": dept_rows,
    }

    if include_names:
        named_rows = []
        for r in by_emp[:25]:
            share = ot_concentration_share(r["total_seconds"] or 0, total)
            first = r.get("employee_id__employee_first_name") or ""
            last = r.get("employee_id__employee_last_name") or ""
            named_rows.append(
                {
                    "employee": f"{first} {last}".strip(),
                    "department": r.get(
                        "employee_id__employee_work_info__department_id__department"
                    )
                    or "",
                    "ot_hours": round((r["total_seconds"] or 0) / 3600, 1),
                    "share": f"{share}%",
                }
            )
        charts.append(
            {
                "id": "ot_top",
                "type": "bar",
                "title": _("Top OT hours (named — confidential)"),
                "categories": [r["employee"] for r in named_rows[:10]],
                "series": [
                    {
                        "name": _("OT Hours"),
                        "data": [r["ot_hours"] for r in named_rows[:10]],
                    }
                ],
            }
        )
        table = {
            "columns": [
                {"key": "employee", "label": _("Employee")},
                {"key": "department", "label": _("Department")},
                {"key": "ot_hours", "label": _("OT Hours")},
                {"key": "share", "label": _("Share")},
            ],
            "rows": named_rows,
        }

    return {
        "title": _("OT Concentration"),
        "kpis": [
            {
                "label": _("Total OT hours"),
                "value": round(total / 3600, 1),
                "hint": _("In period"),
            },
            {
                "label": _("Top 5 share"),
                "value": f"{concentration}%",
                "hint": _("Concentration risk"),
            },
            {
                "label": _("Top 10 share"),
                "value": f"{concentration10}%",
                "hint": "",
            },
            {
                "label": _("Employees with OT"),
                "value": len(by_emp),
                "hint": _("Names hidden unless include_names + change_attendance"),
            },
        ],
        "charts": charts,
        "table": table,
        "explorer_url_name": "attendance-report",
    }
