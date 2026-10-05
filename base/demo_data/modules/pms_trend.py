"""Spread demo EmployeeObjective dates across a real trailing 6 months.

Only 8 EmployeeObjective rows exist across the base + scenarios fixtures,
clustered around a single month roughly 10-14 months before any reasonable
"today" -- well outside a 6-month trailing window regardless of the anchor
shift. The PMS progress trend groups by `updated_at`, which is `auto_now=True`
-- a plain `.save()` always resets it to today, so this must go through
`.filter().update()` (which bypasses `auto_now`, same as normalize_demo_payslips).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from django.apps import apps
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

TRAILING_DAYS = 180


@transaction.atomic
def backfill_pms_objectives(today: date | None = None) -> int:
    """Spread every EmployeeObjective's updated_at (and start/end_date, shifted
    by the same delta) across the trailing 6 months, then cascade that same
    per-objective delta to EmployeeKeyResult, Comment, and Feedback so they
    don't drift out of sync with the objective's own re-dated window (e.g. a
    comment landing 1.5 years before the objective it's attached to)."""
    if not apps.is_installed("pms"):
        return 0

    today = today or date.today()
    window_start = today - timedelta(days=TRAILING_DAYS)

    from pms.models import Comment, EmployeeKeyResult, EmployeeObjective, Feedback

    rows = list(
        EmployeeObjective._base_manager.order_by("id").values(
            "id", "start_date", "end_date", "updated_at"
        )
    )
    count = len(rows)
    updated = 0
    objective_deltas: dict[int, int] = {}
    for i, row in enumerate(rows):
        # count-1: the last objective lands at exactly today instead of one
        # step short of it, so the current month isn't left empty.
        offset = int(i * TRAILING_DAYS / max(count - 1, 1))
        new_updated_at = window_start + timedelta(days=offset)
        delta_days = (
            (new_updated_at - row["updated_at"]).days if row["updated_at"] else 0
        )
        objective_deltas[row["id"]] = delta_days
        new_start = (
            row["start_date"] + timedelta(days=delta_days)
            if row["start_date"]
            else None
        )
        new_end = (
            row["end_date"] + timedelta(days=delta_days) if row["end_date"] else None
        )
        EmployeeObjective._base_manager.filter(pk=row["id"]).update(
            updated_at=new_updated_at, start_date=new_start, end_date=new_end
        )
        updated += 1

    key_result_deltas: dict[int, int] = {}
    for kr in EmployeeKeyResult._base_manager.filter(
        employee_objective_id__in=objective_deltas
    ).values("id", "employee_objective_id", "start_date", "end_date"):
        delta_days = objective_deltas[kr["employee_objective_id"]]
        EmployeeKeyResult._base_manager.filter(pk=kr["id"]).update(
            start_date=(
                kr["start_date"] + timedelta(days=delta_days)
                if kr["start_date"]
                else None
            ),
            end_date=(
                kr["end_date"] + timedelta(days=delta_days) if kr["end_date"] else None
            ),
        )
        key_result_deltas[kr["id"]] = delta_days

    # created_at is auto_now_add and nullable, so rows created via
    # bulk_create() never get one. A NULL here makes the row invisible to
    # every period-filtered report (report/metrics/talent.py), not just the
    # current window -- and the undated rows happen to carry the only
    # non-"Not Started" statuses, so the Key Result Status chart renders a
    # flat single bar without them. Date them from their own objective.
    for kr in EmployeeKeyResult._base_manager.filter(created_at__isnull=True).values(
        "id", "employee_objective_id", "start_date"
    ):
        seed = kr["start_date"]
        if seed is None:
            seed = (
                EmployeeObjective._base_manager.filter(pk=kr["employee_objective_id"])
                .values_list("start_date", flat=True)
                .first()
            )
        if seed is None:
            continue
        EmployeeKeyResult._base_manager.filter(pk=kr["id"]).update(created_at=seed)

    for comment in Comment._base_manager.filter(
        employee_objective_id__in=objective_deltas
    ).values("id", "employee_objective_id", "created_at"):
        if not comment["created_at"]:
            continue
        delta_days = objective_deltas[comment["employee_objective_id"]]
        Comment._base_manager.filter(pk=comment["id"]).update(
            created_at=comment["created_at"] + timedelta(days=delta_days)
        )

    # Feedback links to an objective only indirectly, via its M2M set of
    # EmployeeKeyResult rows -- use whichever linked key result's delta is
    # found first (a Feedback spanning key results from more than one
    # objective isn't a scenario this small demo dataset produces).
    if key_result_deltas:
        for feedback in Feedback._base_manager.filter(
            employee_key_results_id__in=list(key_result_deltas)
        ).distinct():
            linked_kr_id = next(
                (
                    kr.id
                    for kr in feedback.employee_key_results_id.all()
                    if kr.id in key_result_deltas
                ),
                None,
            )
            if linked_kr_id is None:
                continue
            delta_days = key_result_deltas[linked_kr_id]
            Feedback._base_manager.filter(pk=feedback.pk).update(
                start_date=(
                    feedback.start_date + timedelta(days=delta_days)
                    if feedback.start_date
                    else None
                ),
                end_date=(
                    feedback.end_date + timedelta(days=delta_days)
                    if feedback.end_date
                    else None
                ),
            )

    _date_undated_key_results()
    _reconcile_objective_status(today)

    logger.info(
        "PMS backfill: spread %s objective(s) over the trailing %s days",
        updated,
        TRAILING_DAYS,
    )
    return updated


def _date_undated_key_results() -> int:
    """Give key results with no start/end date their objective's dates.

    Fixture key results are seeded undated, which makes them invisible to the
    period-overlap filters the PMS dashboard charts use.
    """
    from pms.models import EmployeeKeyResult, EmployeeObjective

    objective_dates = {
        row["id"]: (row["start_date"], row["end_date"])
        for row in EmployeeObjective._base_manager.values(
            "id", "start_date", "end_date"
        )
    }
    updated = 0
    for kr in EmployeeKeyResult._base_manager.filter(
        Q(start_date__isnull=True) | Q(end_date__isnull=True)
    ).values("id", "employee_objective_id", "start_date", "end_date"):
        start, end = objective_dates.get(kr["employee_objective_id"], (None, None))
        EmployeeKeyResult._base_manager.filter(pk=kr["id"]).update(
            start_date=kr["start_date"] or start, end_date=kr["end_date"] or end
        )
        updated += 1
    return updated


def _reconcile_objective_status(today: date) -> None:
    """Closed work ended in the past; not-started work isn't already overdue."""
    from pms.models import EmployeeObjective

    for row in EmployeeObjective._base_manager.values(
        "id", "status", "end_date", "progress_percentage"
    ):
        end = row["end_date"]
        status = row["status"]
        if not end:
            continue
        if status == "Closed" and end > today:
            EmployeeObjective._base_manager.filter(pk=row["id"]).update(
                end_date=today - timedelta(days=7),
                progress_percentage=100,
            )
        elif status == "Not Started" and end < today:
            EmployeeObjective._base_manager.filter(pk=row["id"]).update(
                status="At Risk",
                progress_percentage=max(row["progress_percentage"] or 0, 20),
            )


# Roughly one in seven employees per company gets an objective -- a
# performance program realistically covers a meaningful slice of staff, not
# literally everyone, but the *slice itself* should scale with headcount and
# reach every company instead of concentrating in just one.
NEW_COVERAGE_RATE = 0.15
STATUS_CYCLE = ("Not Started", "On Track", "At Risk", "Closed")


@transaction.atomic
def backfill_pms_coverage(today: date | None = None) -> int:
    """
    Give a headcount-proportional, every-company slice of employees an
    EmployeeObjective assignment, cycling through the existing Objective
    catalog. PMS previously touched only 8 of 276 employees total, all in a
    single company -- a second company had none at all.

    Dates here are placeholders only: backfill_pms_objectives (called right
    after this one in the seeder) re-spreads every EmployeeObjective's dates
    across the trailing 6 months regardless of how the row was created, so
    duplicating that date logic here isn't necessary.
    """
    if not apps.is_installed("pms"):
        return 0

    today = today or date.today()

    from employee.models import Employee, EmployeeWorkInformation
    from pms.models import EmployeeObjective, Objective

    objective_ids = list(
        Objective._base_manager.order_by("id").values_list("id", flat=True)
    )
    if not objective_ids:
        return 0

    covered_ids = set(
        EmployeeObjective._base_manager.values_list("employee_id", flat=True).distinct()
    )
    company_by_employee = dict(
        EmployeeWorkInformation._base_manager.values_list("employee_id", "company_id")
    )
    active_ids = (
        Employee._base_manager.filter(is_active=True)
        .order_by("id")
        .values_list("id", flat=True)
    )

    # Target is a fraction of each company's *total* headcount, not of
    # whatever's currently uncovered -- computing it from the shrinking
    # uncovered pool would make every additional non-flush reload add ~15%
    # of whatever's left, converging toward full coverage instead of
    # holding steady near the intended ratio.
    all_ids_by_company: dict[int, list[int]] = defaultdict(list)
    for employee_id in active_ids:
        company_id = company_by_employee.get(employee_id)
        if company_id:
            all_ids_by_company[company_id].append(employee_id)

    created = 0
    for company_id, all_ids in all_ids_by_company.items():
        target = max(1, int(len(all_ids) * NEW_COVERAGE_RATE))
        currently_covered = sum(1 for e in all_ids if e in covered_ids)
        need = target - currently_covered
        if need <= 0:
            continue
        candidate_ids = [e for e in all_ids if e not in covered_ids][:need]
        for employee_id in candidate_ids:
            objective_id = objective_ids[created % len(objective_ids)]
            EmployeeObjective._base_manager.get_or_create(
                employee_id_id=employee_id,
                objective_id_id=objective_id,
                defaults={
                    "start_date": today,
                    "end_date": today,
                    "status": STATUS_CYCLE[created % len(STATUS_CYCLE)],
                    "progress_percentage": 0,
                },
            )
            created += 1

    logger.info(
        "PMS backfill: created %s EmployeeObjective assignment(s) across %s compan(ies)",
        created,
        len(all_ids_by_company),
    )
    return created
