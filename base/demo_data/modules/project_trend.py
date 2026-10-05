"""Give the demo Project catalog real spread across a trailing 6 months.

Only one real historical Project row ships in the fixtures. The other five,
in project_scenarios_data.json, are re-anchored by
`reanchor_project_scenarios` below rather than left untouched: their static
dates were authored one calendar year off, so the generic whole-file date
shift (`_shift_fixture_dates`) landed their Timesheet entries in the future
roughly as often as not, which a logged timesheet -- a record of work
already performed -- must never be.

One point can't populate a 6-month started/completed trend, so this also
creates a small, fixed set of additional projects -- idempotent via `title`
(globally unique on the model) -- and re-dates all of them fresh on every
run.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

TRAILING_DAYS = 180

# (title, description, duration_days) -- duration decides completed vs
# ongoing once staggered across the window.
DEMO_PROJECTS = [
    (
        "Employee Self-Service Portal Revamp",
        "Modernize the self-service portal for leave, payslips, and profile updates.",
        60,
    ),
    (
        "Payroll Compliance Automation",
        "Automate statutory payroll compliance checks across supported regions.",
        75,
    ),
    (
        "Onboarding Experience Redesign",
        "Redesign the new-hire onboarding journey from offer to first 30 days.",
        45,
    ),
    (
        "Attendance Analytics Dashboard",
        "Build manager-facing attendance and overtime analytics dashboards.",
        90,
    ),
    (
        "Recruitment Pipeline Integration",
        "Integrate the candidate pipeline with external job board sources.",
        50,
    ),
    (
        "Internal Helpdesk Knowledge Base",
        "Stand up a searchable knowledge base to deflect repeat helpdesk tickets.",
        40,
    ),
    (
        "Leave Policy Harmonization",
        "Align leave policies and approval workflows across all companies.",
        55,
    ),
    (
        "Performance Review Cycle Tooling",
        "Build tooling to streamline quarterly performance review cycles.",
        65,
    ),
]


@transaction.atomic
def backfill_project_trend(today: date | None = None) -> int:
    """Ensure DEMO_PROJECTS exist, then spread their dates across the trailing 6 months."""
    if not apps.is_installed("project"):
        return 0

    today = today or date.today()
    window_start = today - timedelta(days=TRAILING_DAYS)

    from employee.models import Employee
    from project.models import Project

    manager_ids = list(
        Employee._base_manager.filter(is_active=True)
        .order_by("id")
        .values_list("id", flat=True)[:5]
    )

    count = len(DEMO_PROJECTS)
    updated = 0
    for i, (title, description, duration_days) in enumerate(DEMO_PROJECTS):
        project, created = Project._base_manager.get_or_create(
            title=title,
            defaults={
                "description": description,
                "start_date": today,
                "status": "new",
            },
        )

        # count-1: the last project lands at exactly today instead of one
        # step short of it, so the current month isn't left empty.
        offset = int(i * TRAILING_DAYS / max(count - 1, 1))
        start = window_start + timedelta(days=offset)
        end = start + timedelta(days=duration_days)
        status = "completed" if end < today else "in_progress"
        if end > today:
            end = min(end, today + timedelta(days=30))

        Project._base_manager.filter(pk=project.pk).update(
            start_date=start, end_date=end, status=status
        )
        if created and manager_ids:
            project.managers.add(manager_ids[i % len(manager_ids)])
        updated += 1

    logger.info(
        "Project backfill: %s demo project(s) spread over the trailing %s days",
        updated,
        TRAILING_DAYS,
    )
    return updated


SCENARIO_PK_FLOOR = 1001

# Due-date offsets (days from today) for the demo "Task Deadlines" panel:
# three coming up within its 14-day window and two already overdue.
DEADLINE_OFFSETS = (2, 5, 9, -3, -8)
FOLLOW_UP_TASK_TITLES = (
    "Review open items with stakeholders",
    "Hand over project documentation",
    "Confirm sign-off with the client",
    "Close out remaining action items",
    "Archive project files",
)


@transaction.atomic
def backfill_task_deadlines(today: date | None = None) -> int:
    """Give every company a handful of open tasks due around `today`.

    The dashboard's Task Deadlines panel lists open tasks due in the next 14
    days plus overdue ones. The shifted fixture dates rarely put any open task
    in that window (and only for the company that owns it), so the panel came
    up empty. For each company, re-date its first few open tasks relative to
    `today`; fresh on every run, so reloads stay consistent.
    """
    if not apps.is_installed("project"):
        return 0

    today = today or date.today()

    from project.models import Task

    open_tasks = Task._base_manager.filter(
        is_active=True,
        status__in=["to_do", "in_progress"],
        project__isnull=False,
    ).order_by("pk")

    # Projects with no company show up for every company's users, so count
    # them with the first company rather than as a group of their own (which
    # would double the rows a user sees). The named scenario tasks go first.
    tasks_all = list(open_tasks.select_related("project"))
    company_ids = sorted(
        {t.project.company_id_id for t in tasks_all if t.project.company_id_id}
    )
    default_company = company_ids[0] if company_ids else None
    tasks_all.sort(key=lambda t: (t.pk < SCENARIO_PK_FLOOR, t.pk))
    by_company: dict = {}
    for task in tasks_all:
        key = task.project.company_id_id or default_company
        by_company.setdefault(key, []).append(task)

    # A company whose projects are all finished/cancelled has no open task to
    # re-date (its users would see an empty panel), so top it up with a few
    # follow-up tasks on its first project -- idempotent via title.
    from project.models import Project, ProjectStage

    for company_id in sorted(
        {p for p in Project._base_manager.values_list("company_id_id", flat=True) if p}
    ):
        tasks = by_company.setdefault(company_id, [])
        missing = len(DEADLINE_OFFSETS) - len(tasks)
        if missing <= 0:
            continue
        project = (
            Project._base_manager.filter(company_id_id=company_id)
            .order_by("pk")
            .first()
        )
        stage = (
            ProjectStage._base_manager.filter(project=project)
            .order_by("sequence", "pk")
            .first()
        )
        seed_task = Task._base_manager.filter(project=project).order_by("pk").first()
        for title in FOLLOW_UP_TASK_TITLES[:missing]:
            task, created = Task._base_manager.get_or_create(
                project=project,
                title=title,
                defaults={
                    "stage": stage,
                    "status": "to_do",
                    "description": "Follow-up item after the main delivery.",
                },
            )
            if created and seed_task is not None:
                task.task_managers.set(seed_task.task_managers.all())
                task.task_members.set(seed_task.task_members.all())
            if task.status in ("to_do", "in_progress"):
                tasks.append(task)

    updated = 0
    for tasks in by_company.values():
        for task, offset in zip(tasks, DEADLINE_OFFSETS):
            end = today + timedelta(days=offset)
            start = task.start_date
            if start is None or start > end:
                start = end - timedelta(days=10)
            Task._base_manager.filter(pk=task.pk).update(start_date=start, end_date=end)
            updated += 1

    logger.info("Task deadlines backfill: re-dated %s open task(s)", updated)
    return updated


@transaction.atomic
def reanchor_project_scenarios(today: date | None = None) -> int:
    """Re-anchor project_scenarios_data.json's static rows to `today`.

    The generic whole-file shift only guarantees the fixture's authored
    center lands near `today` -- not that every date stays <= `today`,
    which a logged TimeSheet entry (work already performed) must.
    Translates the whole scenario cluster (projects + tasks + timesheets)
    by a single delta so every relative gap authored between them is
    preserved exactly -- a project/task date range that legitimately
    extends into the future (an "in_progress"/"new" project's end_date)
    shifts by the same delta and correctly keeps extending into the real
    future; only the latest TimeSheet entry is pinned to `today - 1`.
    """
    if not apps.is_installed("project"):
        return 0

    today = today or date.today()

    from project.models import Project, Task, TimeSheet

    timesheets = list(TimeSheet._base_manager.filter(pk__gte=SCENARIO_PK_FLOOR))
    if not timesheets:
        return 0

    shift = (today - timedelta(days=1)) - max(ts.date for ts in timesheets)
    if shift == timedelta(0):
        return 0

    for ts in timesheets:
        TimeSheet._base_manager.filter(pk=ts.pk).update(date=ts.date + shift)

    tasks = list(Task._base_manager.filter(pk__gte=SCENARIO_PK_FLOOR))
    for task in tasks:
        Task._base_manager.filter(pk=task.pk).update(
            start_date=task.start_date + shift if task.start_date else None,
            end_date=task.end_date + shift if task.end_date else None,
        )

    projects = list(Project._base_manager.filter(pk__gte=SCENARIO_PK_FLOOR))
    for project in projects:
        Project._base_manager.filter(pk=project.pk).update(
            start_date=project.start_date + shift if project.start_date else None,
            end_date=project.end_date + shift if project.end_date else None,
        )

    logger.info(
        "Project scenario re-anchor: shifted %s project(s), %s task(s), %s timesheet(s) by %s day(s)",
        len(projects),
        len(tasks),
        len(timesheets),
        shift.days,
    )
    return len(projects)
