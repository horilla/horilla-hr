"""Orchestrate the enterprise demo seeder after fixtures load."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from django.apps import apps
from django.conf import settings

from base.demo_data.companies import ensure_companies
from base.demo_data.media import copy_demo_media
from base.demo_data.modules.announcements import refresh_announcements
from base.demo_data.modules.asset_expansion import backfill_company_asset_pools
from base.demo_data.modules.asset_features import backfill_asset_reports
from base.demo_data.modules.attendance_trend import (
    backfill_attendance_activities,
    backfill_attendance_density,
    backfill_attendance_overtime,
    backfill_attendance_spread,
    backfill_pending_validation_today,
    backfill_zero_coverage_attendance,
    reconcile_attendance_with_leave,
)
from base.demo_data.modules.date_clamp import clamp_demo_dates
from base.demo_data.modules.employee_features import backfill_employee_feature_coverage
from base.demo_data.modules.employee_lifecycle import backfill_employee_lifecycle
from base.demo_data.modules.employee_work_history import (
    backfill_employee_work_info_history,
)
from base.demo_data.modules.helpdesk_expansion import backfill_company_helpdesk_lookups
from base.demo_data.modules.helpdesk_trend import (
    backfill_helpdesk_tickets,
    reanchor_helpdesk_scenarios,
)
from base.demo_data.modules.leave_trend import (
    backfill_leave_spread,
    backfill_zero_coverage_available_leave,
)
from base.demo_data.modules.offboarding_expansion import (
    backfill_company_offboarding_pipelines,
)
from base.demo_data.modules.offboarding_trend import backfill_offboarding_letters
from base.demo_data.modules.onboarding_trend import backfill_onboarding_pipeline
from base.demo_data.modules.payroll_precise import backfill_precise_payroll
from base.demo_data.modules.pms_trend import (
    backfill_pms_coverage,
    backfill_pms_objectives,
)
from base.demo_data.modules.project_trend import (
    backfill_project_trend,
    backfill_task_deadlines,
    reanchor_project_scenarios,
)
from base.demo_data.modules.recruitment import seed_recruitment_catalog
from base.demo_data.modules.recruitment_expansion import (
    backfill_company_recruitment_pipelines,
)
from base.demo_data.modules.recruitment_features import (
    backfill_candidate_offer_status,
    backfill_candidate_source,
    backfill_recruitment_job_position,
    backfill_rejected_candidates,
)
from base.demo_data.modules.request_windows import backfill_request_windows
from base.demo_data.org import (
    differentiate_org_taxonomy_by_company,
    standardize_org_taxonomy,
)
from base.demo_data.sanitize import sanitize_loaded_records, scrub_side_fixture_files

logger = logging.getLogger(__name__)


def run_enterprise_demo_seeder(
    *,
    load_dir: Path | None = None,
    today: date | None = None,
    copy_media: bool = True,
    scrub_side_files: bool = True,
) -> dict:
    """
    Standardize demo data after JSON fixtures are loaded.

    Safe to call repeatedly (idempotent renames / upserts). Does not create
    or delete employees — only activates companies, renames org taxonomy,
    refreshes announcements, and sanitizes vendor-specific labels.
    """
    today = today or date.today()
    root = Path(load_dir) if load_dir else Path(settings.BASE_DIR) / "load_data"
    result: dict = {"ok": True}

    if copy_media:
        result["media"] = copy_demo_media(root)

    if scrub_side_files:
        result["side_fixtures"] = scrub_side_fixture_files(root)

    result["companies"] = ensure_companies()
    result["org"] = standardize_org_taxonomy()
    result["org_differentiation"] = differentiate_org_taxonomy_by_company()
    result["announcements"] = refresh_announcements(today)
    result["recruitment"] = seed_recruitment_catalog()
    result["sanitized"] = sanitize_loaded_records()

    # Trailing-6-month dashboard backfill -- every function below computes
    # dates purely from `today`, so charts stay populated on every load
    # regardless of when it runs. Employee lifecycle runs before offboarding
    # since the latter reuses its chosen exit-employee ids.
    result["attendance_backfill"] = backfill_attendance_spread(today)
    result["attendance_overtime_backfill"] = backfill_attendance_overtime(today)
    # Fills genuine zero-coverage gaps left by the redistribution above (an
    # employee with no rows at all has nothing to redistribute).
    result["attendance_zero_coverage_backfill"] = backfill_zero_coverage_attendance(
        today
    )
    # Tops up everyone (including the just-covered employees above) to a
    # realistic shift-aware density -- must run after zero-coverage fill and
    # before leave spread finalizes leave dates below.
    result["attendance_density_backfill"] = backfill_attendance_density(today)
    result["leave_backfill"] = backfill_leave_spread(today)
    result["leave_zero_coverage_backfill"] = backfill_zero_coverage_available_leave(
        today
    )
    employee_lifecycle = backfill_employee_lifecycle(today, root)
    result["employee_lifecycle"] = employee_lifecycle
    result["project_backfill"] = backfill_project_trend(today)
    result["project_scenarios_reanchor"] = reanchor_project_scenarios(today)
    result["project_task_deadlines"] = backfill_task_deadlines(today)
    result["onboarding_backfill"] = backfill_onboarding_pipeline(today)
    result["offboarding_backfill"] = backfill_offboarding_letters(
        today, employee_lifecycle.get("exit_employee_ids")
    )
    result["offboarding_company_pipelines"] = backfill_company_offboarding_pipelines(
        today
    )
    # Coverage expansion first, so the newly-created EmployeeObjective rows
    # get spread across the trailing window by the date-redistribution pass
    # right after, the same as every other objective.
    result["pms_coverage_backfill"] = backfill_pms_coverage(today)
    result["pms_backfill"] = backfill_pms_objectives(today)
    result["helpdesk_company_lookups"] = backfill_company_helpdesk_lookups(today)
    result["helpdesk_backfill"] = backfill_helpdesk_tickets(today)
    result["helpdesk_scenarios_reanchor"] = reanchor_helpdesk_scenarios(today)

    # A small, dedicated set of employees per company with attendance stated
    # outright and payslips verified to reconcile against it -- replaces the
    # broad roster's own contracts/payslips (backfill_payroll_feature_coverage /
    # backfill_payroll_coverage), which depended on attendance_trend.py's
    # backfill reconciling cleanly for every employee it touched, and for some
    # it didn't (see payroll_precise.py's module docstring).
    result["precise_payroll"] = backfill_precise_payroll(today)

    result["recruitment_company_pipelines"] = backfill_company_recruitment_pipelines(
        today
    )
    result["recruitment_rejected_candidates"] = backfill_rejected_candidates(today)
    result["recruitment_candidate_source"] = backfill_candidate_source(today)
    result["recruitment_job_position"] = backfill_recruitment_job_position(today)
    result["recruitment_offer_status"] = backfill_candidate_offer_status(today)
    result["asset_company_pools"] = backfill_company_asset_pools(today)
    result["asset_reports"] = backfill_asset_reports(today)

    # Fully-built features (bank details, notes, roster, announcement
    # read-receipts, multi-level approval managers) that ship with zero
    # demo rows connecting them to anything.
    result["employee_feature_coverage"] = backfill_employee_feature_coverage(today)
    result["employee_work_info_history"] = backfill_employee_work_info_history(today)
    result["request_windows"] = backfill_request_windows(today)
    result["attendance_leave_reconcile"] = reconcile_attendance_with_leave(today)
    result["attendance_activities"] = backfill_attendance_activities(today)
    result["attendance_pending_validation"] = backfill_pending_validation_today(today)

    # System ReportTemplate rows (Explorer's pre-built pivot layouts) aren't
    # part of any load_data/*.json fixture, so a --flush reload wipes them
    # silently unless they're re-seeded here too.
    if apps.is_installed("report"):
        from report.management.commands.seed_standard_report_templates import (
            seed_standard_report_templates,
        )

        created, updated = seed_standard_report_templates()
        result["report_templates"] = {"created": created, "updated": updated}

    result["date_clamp"] = clamp_demo_dates(today)

    logger.info("Enterprise demo seeder finished: %s", result)
    return result
