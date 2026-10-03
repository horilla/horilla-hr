"""Final A/B date clamp after the enterprise demo seeder.

A-class (historical facts): never after today.
B-class (requests / planned): pending till/end in the past gets bumped;
completed rows stay in the past. Holidays re-anchor to the current year.

Attendance future rows are deleted in reconcile_attendance_with_leave;
this pass clamps leftover fields via update() so model validators never run.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from base.demo_data.dates import holiday_on_year

logger = logging.getLogger(__name__)

TRAILING_DAYS = 180

# Candidate.created_at drives the recruitment dashboard's default "this
# month" filter (recruitment/dashboard.py's _candidates_in_period). A
# shorter, recency-biased window (vs. TRAILING_DAYS) guarantees a handful
# of candidates always fall in the current calendar month, even on the
# 1st, so Hiring Pipeline / Hire Rate / Time to Hire never render empty.
CANDIDATE_TRAILING_DAYS = 45

# Same problem, same fix, for the Project dashboard: Project.created_at /
# Task.created_at drive project/dashboard.py's default "this month" filter
# for the Project Status and Task Status charts.
PROJECT_TRAILING_DAYS = 45

# Historical facts: never after today. Attendance.attendance_date is deleted
# (not clamped) so unique_together is not violated. WorkRecords.date is
# handled separately (_clamp_workrecords_date) since it carries a
# per-employee unique constraint that a blanket update() can collide with.
A_CLASS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "attendance",
        "Attendance",
        ("attendance_clock_in_date", "attendance_clock_out_date"),
    ),
    (
        "attendance",
        "AttendanceActivity",
        ("attendance_date", "clock_in_date", "clock_out_date"),
    ),
    ("payroll", "WorkRecord", ("date",)),
    ("project", "TimeSheet", ("date",)),
    ("helpdesk", "Ticket", ("created_date", "resolved_date")),
    ("asset", "AssetAssignment", ("assigned_date", "return_date")),
    ("onboarding", "CandidateStage", ("onboarding_end_date",)),
    ("payroll", "Contract", ("contract_start_date",)),
    ("payroll", "LoanAccount", ("provided_date", "installment_start_date")),
    ("base", "RotatingShiftAssign", ("start_date",)),
    ("base", "RotatingWorkTypeAssign", ("start_date",)),
)

A_CLASS_DATETIME: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("payroll", "LoanAccount", ("settled_date",)),
    ("payroll", "Contract", ("created_at",)),
    ("attendance", "AttendanceActivity", ("in_datetime", "out_datetime")),
)


@transaction.atomic
def clamp_demo_dates(today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    result = {
        "a_class": 0,
        "a_class_datetime": 0,
        "holidays": 0,
        "loans": 0,
        "assignments": 0,
        "rotating": 0,
        "candidates": 0,
        "projects": 0,
        "workrecords": 0,
        "b_class": 0,
        "payslips": 0,
        "interviews": 0,
        "exits": 0,
    }
    result["holidays"] = _reanchor_holidays(today)
    result["loans"] = _reanchor_loans(today)
    result["assignments"] = _reanchor_assignments(today)
    result["rotating"] = _reanchor_rotating(today)
    result["candidates"] = _reanchor_candidates(today)
    result["projects"] = _reanchor_projects_and_tasks(today)
    result["workrecords"] = _clamp_workrecords_date(today)
    result["a_class"] = _clamp_a_class(today)
    result["a_class_datetime"] = _clamp_a_class_datetime()
    result["b_class"] = _bump_stale_pending(today)
    result["payslips"] = _demote_future_paid_payslips(today)
    result["interviews"] = _clamp_completed_interviews(today)
    result["exits"] = _clamp_completed_exits(today)
    logger.info("Demo date clamp: %s", result)
    return result


def _clamp_workrecords_date(today: date) -> int:
    """Clamp attendance.WorkRecords.date to today, without violating the
    per-(employee_id, date) unique constraint.

    A blanket `.update(date=today)` (like the rest of A_CLASS) collides
    whenever an employee already has a WorkRecords row dated today and
    another future-dated row for the same employee gets clamped onto it.
    Excess future rows are deleted instead of clamped in that case.
    """
    if not apps.is_installed("attendance"):
        return 0
    from attendance.models import WorkRecords

    updated = 0
    future_qs = WorkRecords._base_manager.filter(date__gt=today).order_by(
        "employee_id", "id"
    )
    seen_today_employees = set(
        WorkRecords._base_manager.filter(date=today).values_list(
            "employee_id", flat=True
        )
    )
    for row in future_qs:
        if row.employee_id_id in seen_today_employees:
            row.delete()
        else:
            WorkRecords._base_manager.filter(pk=row.pk).update(date=today)
            seen_today_employees.add(row.employee_id_id)
        updated += 1
    return updated


def _clamp_a_class(today: date) -> int:
    updated = 0
    for app, model, fields in A_CLASS:
        if not apps.is_installed(app):
            continue
        Model = apps.get_model(app, model)
        for field in fields:
            updated += Model._base_manager.filter(**{f"{field}__gt": today}).update(
                **{field: today}
            )
    return updated


def _clamp_a_class_datetime() -> int:
    now = timezone.now()
    updated = 0
    for app, model, fields in A_CLASS_DATETIME:
        if not apps.is_installed(app):
            continue
        Model = apps.get_model(app, model)
        for field in fields:
            updated += Model._base_manager.filter(**{f"{field}__gt": now}).update(
                **{field: now}
            )
    return updated


def _reanchor_holidays(today: date) -> int:
    if not apps.is_installed("base"):
        return 0
    from base.models import Holidays

    updated = 0
    for holiday in Holidays._base_manager.all():
        if not holiday.start_date:
            continue
        span = 0
        if holiday.end_date:
            span = (holiday.end_date - holiday.start_date).days
        new_start = holiday_on_year(holiday.start_date, today.year)
        new_end = new_start + timedelta(days=span) if holiday.end_date else None
        if new_start == holiday.start_date and new_end == holiday.end_date:
            continue
        Holidays._base_manager.filter(pk=holiday.pk).update(
            start_date=new_start, end_date=new_end
        )
        updated += 1
    return updated


def _reanchor_loans(today: date) -> int:
    """
    Re-anchoring installment_start_date alone leaves LoanAccount.deduction_ids
    pointing at whatever Deduction rows the *previous* schedule created --
    get_installments() reads the field live and so recomputes a clean
    monthly-from-the-new-date schedule, but the actual attached Deduction
    rows never followed it. Across repeated demo reloads those went stale
    and duplicated (several installments landing on the same one_time_date,
    e.g. three separate "Emergency Loan" rows all dated the same day), which
    is exactly what a generated payslip then displayed. Deleting and
    recreating installment Deductions here, in the same pass that moves the
    date, is what keeps the two in agreement.
    """
    if not apps.is_installed("payroll"):
        return 0
    from payroll.methods.deductions import create_deductions
    from payroll.models.models import Deduction, LoanAccount

    window_start = today - timedelta(days=TRAILING_DAYS)
    rows = list(LoanAccount._base_manager.order_by("id"))
    if not rows:
        return 0
    step = TRAILING_DAYS / max(len(rows), 1)
    updated = 0
    for i, loan in enumerate(rows):
        provided = window_start + timedelta(days=int(i * step))
        if provided > today:
            provided = today
        start = min(provided + timedelta(days=7), today)
        fields = {"provided_date": provided, "installment_start_date": start}
        if loan.settled:
            when = datetime.combine(today - timedelta(days=1), time(12, 0))
            if timezone.is_naive(when):
                try:
                    when = timezone.make_aware(when)
                except Exception:
                    pass
            fields["settled_date"] = when
        LoanAccount._base_manager.filter(pk=loan.pk).update(**fields)

        if loan.allowance_id_id:
            # The one-time payout allowance (separate from the installment
            # Deductions below) carries its own one_time_date, matched to
            # provided_date the same way create_installments sets it up.
            from payroll.models.models import Allowance

            Allowance._base_manager.filter(pk=loan.allowance_id_id).update(
                one_time_date=provided
            )

        stale_ids = list(loan.deduction_ids.values_list("id", flat=True))
        if stale_ids:
            Deduction._base_manager.filter(pk__in=stale_ids).delete()
        loan.refresh_from_db(fields=["installment_start_date"])
        fresh = [
            create_deductions(loan, amount, installment_date)
            for installment_date, amount in loan.get_installments().items()
        ]
        loan.deduction_ids.set(fresh)

        updated += 1
    return updated


def _reanchor_assignments(today: date) -> int:
    if not apps.is_installed("asset"):
        return 0
    from asset.models import AssetAssignment

    updated = 0
    for i, row in enumerate(AssetAssignment._base_manager.order_by("id")):
        assigned = today - timedelta(days=14 + (i * 7) % TRAILING_DAYS)
        fields = {"assigned_date": assigned}
        if row.return_date:
            fields["return_date"] = min(assigned + timedelta(days=21), today)
        AssetAssignment._base_manager.filter(pk=row.pk).update(**fields)
        updated += 1
    return updated


def _reanchor_rotating(today: date) -> int:
    if not apps.is_installed("base"):
        return 0
    from base.models import RotatingShiftAssign, RotatingWorkTypeAssign

    updated = 0
    for Model in (RotatingShiftAssign, RotatingWorkTypeAssign):
        for i, row in enumerate(Model._base_manager.order_by("id")):
            start = today - timedelta(days=30 + i % 60)
            nxt = today + timedelta(days=3 + i % 18)
            Model._base_manager.filter(pk=row.pk).update(
                start_date=start, next_change_date=nxt
            )
            updated += 1
    return updated


def _reanchor_candidates(today: date) -> int:
    """Spread Candidate.created_at across a recent trailing window.

    Fixture/backfilled candidates carry frozen creation timestamps, so once
    those dates fall outside the current calendar month the recruitment
    dashboard's default period filter (created_at-based) shows nothing --
    Hiring Pipeline, Hire Rate by Recruitment, and Time to Hire all render
    empty even though the underlying recruitments/candidates exist.

    Every hired candidate (hired=True, OR currently sitting in a
    stage_type="hired" stage -- the two aren't kept in sync by the app, see
    recruitment/dashboard.py's Q(hired=True) | Q(stage_id__stage_type=...)
    everywhere it needs "is this candidate hired") gets a joining_date a
    plausible interval after their new created_at, filled in if missing --
    not just re-clamped if already set -- so Time to Hire's per-recruitment
    average never silently drops a recruitment that has a real hire but no
    recorded join date.
    """
    if not apps.is_installed("recruitment"):
        return 0
    from recruitment.models import Candidate

    rows = list(Candidate._base_manager.select_related("stage_id").order_by("id"))
    if not rows:
        return 0
    window_start = today - timedelta(days=CANDIDATE_TRAILING_DAYS)
    # Count backward from today so the newest row always lands on today
    # (guaranteeing the current month is never empty) regardless of how
    # many rows there are -- forward-spreading a single row from
    # window_start, by contrast, can place it entirely outside this month.
    cadence = max(1, CANDIDATE_TRAILING_DAYS // len(rows))
    updated = 0
    for offset, candidate in enumerate(reversed(rows)):
        created = max(today - timedelta(days=offset * cadence), window_start)
        created_dt = datetime.combine(created, time(9, 0))
        if timezone.is_naive(created_dt):
            try:
                created_dt = timezone.make_aware(created_dt)
            except Exception:
                pass
        fields = {"created_at": created_dt}
        is_hired = candidate.hired or (
            candidate.stage_id and candidate.stage_id.stage_type == "hired"
        )
        if is_hired:
            fields["joining_date"] = min(created + timedelta(days=14), today)
        Candidate._base_manager.filter(pk=candidate.pk).update(**fields)
        updated += 1
    return updated


def _reanchor_projects_and_tasks(today: date) -> int:
    """Spread Project.created_at and Task.created_at across a recent window.

    Same failure mode as _reanchor_candidates: project/dashboard.py's
    Project Status and Task Status charts filter by created_at within the
    default "this month" period. Demo Project/Task rows are created via
    fixtures/backfills without created_at ever being set relative to
    "today", so those charts silently render as blank boxes (ApexCharts
    draws nothing for an empty series, with no placeholder) once the seed
    timestamp falls outside the current calendar month.
    """
    if not apps.is_installed("project"):
        return 0
    from project.models import Project, Task

    updated = 0
    window_start = today - timedelta(days=PROJECT_TRAILING_DAYS)
    for Model in (Project, Task):
        rows = list(Model._base_manager.order_by("id"))
        if not rows:
            continue
        # Count backward from today (see _reanchor_candidates) so the
        # newest row always lands on today, guaranteeing at least one
        # project/task in the current month regardless of row count.
        cadence = max(1, PROJECT_TRAILING_DAYS // len(rows))
        for offset, row in enumerate(reversed(rows)):
            created = max(today - timedelta(days=offset * cadence), window_start)
            created_dt = datetime.combine(created, time(9, 0))
            if timezone.is_naive(created_dt):
                try:
                    created_dt = timezone.make_aware(created_dt)
                except Exception:
                    pass
            Model._base_manager.filter(pk=row.pk).update(created_at=created_dt)
            updated += 1
    return updated


def _bump_stale_pending(today: date) -> int:
    """B-class: pending requests whose till/end already lapsed."""
    updated = 0
    if apps.is_installed("base"):
        from base.models import ShiftRequest, WorkTypeRequest

        till = today + timedelta(days=14)
        updated += ShiftRequest._base_manager.filter(
            approved=False, canceled=False, requested_till__lt=today
        ).update(requested_till=till)
        updated += WorkTypeRequest._base_manager.filter(
            approved=False, canceled=False, requested_till__lt=today
        ).update(requested_till=till)
    if apps.is_installed("leave"):
        from leave.models import LeaveRequest

        # Leave pending may start up to 21 days ago; only bump the stale tail.
        stale = today - timedelta(days=21)
        pending = LeaveRequest._base_manager.filter(
            status="requested", end_date__lt=stale
        )
        for i, req in enumerate(pending):
            start = today + timedelta(days=7 + i)
            LeaveRequest._base_manager.filter(pk=req.pk).update(
                start_date=start,
                end_date=start + timedelta(days=1),
                requested_date=today - timedelta(days=1),
            )
            updated += 1
    return updated


def _demote_future_paid_payslips(today: date) -> int:
    if not apps.is_installed("payroll"):
        return 0
    from payroll.models.models import Payslip

    return Payslip._base_manager.filter(
        status__in=("paid", "confirmed"), start_date__gt=today
    ).update(status="draft")


def _clamp_completed_interviews(today: date) -> int:
    if not apps.is_installed("recruitment"):
        return 0
    from recruitment.models import InterviewSchedule

    return InterviewSchedule._base_manager.filter(
        completed=True, interview_date__gt=today
    ).update(interview_date=today)


def _clamp_completed_exits(today: date) -> int:
    if not apps.is_installed("offboarding"):
        return 0
    from offboarding.models import OffboardingEmployee, OffboardingStage

    archived = OffboardingStage._base_manager.filter(type="archived").values_list(
        "id", flat=True
    )
    return OffboardingEmployee._base_manager.filter(
        stage_id__in=archived, notice_period_ends__gt=today
    ).update(notice_period_ends=today)
