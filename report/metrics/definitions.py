"""
Register all Phase-1 (and compliance) standard reports with the registry.
"""

from django.utils.translation import gettext_lazy as _

from report.registry import ReportDefinition, register

# Shared filter packs keyed to the underlying model family.
_EMPLOYEE = (
    "employment_status",
    "department_id",
    "job_position_id",
    "job_role_id",
    "employee_type_id",
    "work_type_id",
    "shift_id",
    "company_id",
    "location",
    "gender",
    "reporting_manager_id",
)
_ATTENDANCE = (
    "employment_status",
    "department_id",
    "job_position_id",
    "work_type_id",
    "shift_id",
    "company_id",
    "gender",
)
_LEAVE = (
    "employment_status",
    "department_id",
    "job_position_id",
    "company_id",
    "gender",
    "leave_type_id",
    "leave_status",
)
_LEAVE_BALANCE = (
    "employment_status",
    "department_id",
    "job_position_id",
    "company_id",
    "gender",
    "leave_type_id",
)
_PAYROLL = (
    "employment_status",
    "department_id",
    "job_position_id",
    "employee_type_id",
    "company_id",
    "gender",
    "payslip_status",
)
_CANDIDATE = (
    "department_id",
    "job_position_id",
    "company_id",
    "gender",
    "recruitment_id",
    "source",
    "offer_letter_status",
)
_ONBOARDING = (
    "company_id",
    "recruitment_id",
)
_PMS = (
    "employment_status",
    "department_id",
    "company_id",
    "gender",
    "reporting_manager_id",
)
_COMPLIANCE = (
    "employment_status",
    "department_id",
    "company_id",
)


def _load():
    from report.metrics import compliance, payroll, talent, time_leave, workforce

    # --- Workforce ---
    register(
        ReportDefinition(
            slug="workforce-composition",
            name=_("Workforce Composition"),
            domain="workforce",
            description=_(
                "Headcount, FTE proxy, and distribution by dept/type/job/location."
            ),
            permission="employee.view_employee",
            query_fn=workforce.workforce_composition,
            drilldown_fn=workforce.workforce_composition_drilldown,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="diversity-snapshot",
            name=_("Diversity Snapshot"),
            domain="workforce",
            description=_(
                "DEI / representation — gender and age bands plus leadership mix. "
                "Authorized roles only; marital status excluded from default view."
            ),
            permission="employee.view_employee",
            query_fn=workforce.diversity_snapshot,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="tenure-longevity",
            name=_("Tenure & Longevity"),
            domain="workforce",
            description=_("Average tenure and tenure bands by department."),
            permission="employee.view_employee",
            query_fn=workforce.tenure_longevity,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="turnover-attrition",
            name=_("Turnover (All Exits)"),
            domain="workforce",
            description=_(
                "Hires vs all exits (offboarding / resignation / inactive fallback), "
                "period turnover rate, and first-year exit proxy — no voluntary split."
            ),
            permission="employee.view_employee",
            query_fn=workforce.turnover_attrition,
            drilldown_fn=workforce.turnover_attrition_drilldown,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="joiners-leavers",
            name=_("Joiners & Leavers"),
            domain="workforce",
            description=_(
                "Period joiners and leavers (with exit source), net change, and "
                "approximate month-end headcount trend."
            ),
            permission="employee.view_employee",
            query_fn=workforce.joiners_leavers,
            drilldown_fn=workforce.joiners_leavers_drilldown,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )

    # --- Time & Leave ---
    register(
        ReportDefinition(
            slug="attendance-summary",
            name=_("Attendance Summary"),
            domain="time_leave",
            description=_(
                "Present days, late comes, overtime, and department breakdown."
            ),
            permission="attendance.view_attendance",
            query_fn=time_leave.attendance_summary,
            explorer_url_name="attendance-report",
            export_model="attendance.Attendance",
            required_apps=("attendance", "employee"),
            filter_fields=_ATTENDANCE,
        )
    )
    register(
        ReportDefinition(
            slug="absenteeism-rate",
            name=_("Absenteeism Rate"),
            domain="time_leave",
            description=_(
                "Unscheduled absence vs calendar expected days (holidays/company "
                "leaves subtracted; approved leave excluded from absence)."
            ),
            permission="attendance.view_attendance",
            query_fn=time_leave.absenteeism_rate,
            explorer_url_name="attendance-report",
            export_model="attendance.Attendance",
            required_apps=("attendance", "employee"),
            filter_fields=_ATTENDANCE,
        )
    )
    register(
        ReportDefinition(
            slug="overtime-analysis",
            name=_("Overtime Analysis"),
            domain="time_leave",
            description=_(
                "OT hours by department (default). Named employee rows require "
                "?include_names=1 and attendance.change_attendance."
            ),
            permission="attendance.view_attendance",
            query_fn=time_leave.overtime_analysis,
            drilldown_fn=time_leave.overtime_analysis_drilldown,
            explorer_url_name="attendance-report",
            export_model="attendance.Attendance",
            required_apps=("attendance",),
            filter_fields=_ATTENDANCE,
        )
    )
    register(
        ReportDefinition(
            slug="leave-utilization",
            name=_("Leave Planning (Used vs Entitlement)"),
            domain="time_leave",
            description=_(
                "Planner ratio of period-approved leave days to the current "
                "entitlement snapshot — not an employee consumption nudge."
            ),
            permission="leave.view_leaverequest",
            query_fn=time_leave.leave_utilization,
            explorer_url_name="leave-report",
            export_model="leave.LeaveRequest",
            required_apps=("leave",),
            filter_fields=_LEAVE,
        )
    )
    register(
        ReportDefinition(
            slug="leave-liability",
            name=_("Open Leave Balance (Days)"),
            domain="time_leave",
            description=_(
                "Open leave balances in days (available + carry forward) by type/dept — "
                "not a currency liability."
            ),
            permission="leave.view_leaverequest",
            query_fn=time_leave.leave_liability,
            drilldown_fn=time_leave.leave_liability_drilldown,
            explorer_url_name="leave-report",
            export_model="leave.AvailableLeave",
            required_apps=("leave",),
            filter_fields=_LEAVE_BALANCE,
        )
    )

    # --- Payroll ---
    register(
        ReportDefinition(
            slug="labor-cost-summary",
            name=_("Labor Cost Summary"),
            domain="payroll",
            description=_(
                "Gross, net, deductions by department. Employer cost shown as gross proxy "
                "until contribution components exist."
            ),
            permission="payroll.view_payslip",
            query_fn=payroll.labor_cost_summary,
            explorer_url_name="payroll-report",
            export_model="payroll.Payslip",
            required_apps=("payroll",),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="cost-composition",
            name=_("Cost Composition"),
            domain="payroll",
            description=_(
                "Allowance and deduction component mix from payslip heads "
                "(falls back to unsplit gross with an explicit hint)."
            ),
            permission="payroll.view_payslip",
            query_fn=payroll.cost_composition,
            explorer_url_name="payroll-report",
            export_model="payroll.Payslip",
            required_apps=("payroll",),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="payroll-headcount-cost",
            name=_("Payroll Headcount Cost"),
            domain="payroll",
            description=_(
                "Gross cost per active headcount and average pay by department "
                "(not hours-based FTE)."
            ),
            permission="payroll.view_payslip",
            query_fn=payroll.payroll_headcount_cost,
            explorer_url_name="payroll-report",
            export_model="payroll.Payslip",
            required_apps=("payroll", "employee"),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="payslip-register",
            name=_("Payslip Register"),
            domain="payroll",
            description=_(
                "Confidential payslip register for the selected period. Export requires "
                "export permission (matrix can_export); treat named pay rows as ops-only."
            ),
            permission="payroll.view_payslip",
            query_fn=payroll.payslip_register,
            drilldown_fn=payroll.payslip_register_drilldown,
            explorer_url_name="payroll-report",
            export_model="payroll.Payslip",
            required_apps=("payroll",),
            filter_fields=_PAYROLL,
        )
    )

    # --- Talent ---
    register(
        ReportDefinition(
            slug="recruitment-funnel",
            name=_("Recruitment Funnel"),
            domain="talent",
            description=_(
                "Stage snapshot of candidates in period (not sequential conversion), "
                "plus mutually exclusive source mix."
            ),
            permission="recruitment.view_recruitment",
            query_fn=talent.recruitment_funnel,
            drilldown_fn=talent.recruitment_funnel_drilldown,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment",),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="time-to-hire",
            name=_("Time to Hire / Fill"),
            domain="talent",
            description=_(
                "Average and median days from application (created_at) to joining_date; "
                "open requisition aging."
            ),
            permission="recruitment.view_recruitment",
            query_fn=talent.time_to_hire,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment",),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="offer-acceptance",
            name=_("Offer & Acceptance"),
            domain="talent",
            description=_("Offer letter status mix and acceptance rate."),
            permission="recruitment.view_recruitment",
            query_fn=talent.offer_acceptance,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment",),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="onboarding-progress",
            name=_("Onboarding Progress"),
            domain="talent",
            description=_(
                "Onboarding stage and task completion for candidates who started "
                "onboarding in the selected period (tasks scoped to those candidates)."
            ),
            permission="recruitment.view_recruitment",
            query_fn=talent.onboarding_progress,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment", "onboarding"),
            filter_fields=_ONBOARDING,
        )
    )
    register(
        ReportDefinition(
            slug="performance-distribution",
            name=_("Objective & KR Health"),
            domain="talent",
            description=_(
                "Objective/KR status and progress bands — not a performance rating curve."
            ),
            permission="pms.view_objective",
            query_fn=talent.performance_distribution,
            explorer_url_name="pms-report",
            export_model="pms.EmployeeObjective",
            required_apps=("pms",),
            filter_fields=_PMS,
        )
    )

    # --- Compliance (Phase 2) ---
    register(
        ReportDefinition(
            slug="audit-activity",
            name=_("Audit Activity"),
            domain="compliance",
            description=_(
                "Global audit log volume by action and model (not company-scoped). "
                "Prefer ReportAccess matrix for production tenants."
            ),
            permission="employee.view_employee",
            alt_permissions=("horilla_audit.view_audittag",),
            query_fn=compliance.audit_activity,
            export_model=None,
            required_apps=(),
            filter_fields=("company_id",),
        )
    )

    # --- Phase 7 packs ---
    from report.metrics import packs

    register(
        ReportDefinition(
            slug="span-of-control",
            name=_("Span of Control"),
            domain="workforce",
            description=_(
                "Manager count, average span, and manager-to-headcount ratio."
            ),
            permission="employee.view_employee",
            query_fn=packs.span_of_control,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="pipeline-aging",
            name=_("Pipeline Aging"),
            domain="talent",
            description=_(
                "Age of open candidates since application (created_at) by stage — "
                "not stage-entry age unless audit history is wired later."
            ),
            permission="recruitment.view_recruitment",
            query_fn=packs.pipeline_aging,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment",),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="source-quality",
            name=_("Source Quality"),
            domain="talent",
            description=_(
                "Hire conversion by mutually exclusive source buckets "
                "(referral first; no double-count)."
            ),
            permission="recruitment.view_recruitment",
            query_fn=packs.source_quality,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment",),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="document-expiry-aging",
            name=_("Document Expiry Aging"),
            domain="compliance",
            description=_(
                "Overdue and upcoming horilla_documents expiry buckets (90-day horizon)."
            ),
            permission="employee.view_employee",
            alt_permissions=("horilla_documents.view_document",),
            query_fn=packs.document_expiry_aging,
            export_model="employee.Employee",
            required_apps=("employee", "horilla_documents"),
            filter_fields=_COMPLIANCE,
        )
    )

    # --- Phase 5 CHRO metrics ---
    register(
        ReportDefinition(
            slug="headcount-bridge",
            name=_("Headcount Bridge"),
            domain="workforce",
            description=_(
                "Opening headcount + joiners − leavers = closing bridge for the period."
            ),
            permission="employee.view_employee",
            query_fn=workforce.headcount_bridge,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="exit-analysis",
            name=_("Exit Analysis"),
            domain="workforce",
            description=_(
                "Exits by source, department, and tenure at exit — no voluntary/"
                "involuntary split until reason fields exist."
            ),
            permission="employee.view_employee",
            query_fn=workforce.exit_analysis,
            drilldown_fn=workforce.exit_analysis_drilldown,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="new-hire-90-day-attrition",
            name=_("New-Hire 90-Day Attrition"),
            domain="workforce",
            description=_(
                "Share of period joiners who exit within 90 days of joining."
            ),
            permission="employee.view_employee",
            query_fn=workforce.new_hire_90_day_attrition,
            drilldown_fn=workforce.new_hire_90_day_attrition_drilldown,
            explorer_url_name="employee-report",
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_EMPLOYEE,
        )
    )
    register(
        ReportDefinition(
            slug="unscheduled-absence",
            name=_("Unscheduled Absence"),
            domain="time_leave",
            description=_(
                "Calendar-aware unscheduled absence for the selected period "
                "(holidays/company leave subtracted; approved leave excluded)."
            ),
            permission="attendance.view_attendance",
            query_fn=time_leave.unscheduled_absence,
            explorer_url_name="attendance-report",
            export_model="attendance.Attendance",
            required_apps=("attendance", "employee"),
            filter_fields=_ATTENDANCE,
        )
    )
    register(
        ReportDefinition(
            slug="visa-contract-expiry",
            name=_("Contracts & Document Expiry"),
            domain="compliance",
            description=_(
                "Employment contracts ending and documents with expiry_date. "
                "Visa-like classification is title-based only — not a legal visa register."
            ),
            permission="employee.view_employee",
            alt_permissions=(
                "horilla_documents.view_document",
                "payroll.view_contract",
            ),
            query_fn=compliance.visa_contract_expiry,
            export_model="employee.Employee",
            required_apps=("employee",),
            filter_fields=_COMPLIANCE,
        )
    )
    register(
        ReportDefinition(
            slug="quality-of-hire",
            name=_("Quality of Hire (90-day retention)"),
            domain="talent",
            description=_(
                "90-day retention of hires with joining_date in period — not a "
                "performance quality score."
            ),
            permission="recruitment.view_recruitment",
            query_fn=talent.quality_of_hire,
            explorer_url_name="recruitment-report",
            export_model="recruitment.Candidate",
            required_apps=("recruitment", "employee"),
            filter_fields=_CANDIDATE,
        )
    )
    register(
        ReportDefinition(
            slug="payroll-readiness",
            name=_("Payroll Readiness"),
            domain="payroll",
            description=_(
                "Active employees who cannot be paid: missing bank details or "
                "no active contract. An exception report -- empty is good."
            ),
            permission="payroll.view_payslip",
            alt_permissions=("payroll.view_contract",),
            query_fn=payroll.payroll_readiness,
            explorer_url_name="payroll-report",
            export_model="employee.Employee",
            required_apps=("payroll", "employee"),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="loan-advance-ledger",
            name=_("Loan & Advance Ledger"),
            domain="payroll",
            description=_(
                "Outstanding employee loans and advances: principal, recovered "
                "installments and remaining balance."
            ),
            permission="payroll.view_payslip",
            alt_permissions=("payroll.view_loanaccount",),
            query_fn=payroll.loan_advance_ledger,
            explorer_url_name="payroll-report",
            export_model="payroll.LoanAccount",
            required_apps=("payroll",),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="reimbursement-register",
            name=_("Reimbursement Register"),
            domain="payroll",
            description=_(
                "Reimbursement and encashment claims by type and status, with "
                "pending exposure before a payroll run closes."
            ),
            permission="payroll.view_payslip",
            alt_permissions=("payroll.view_reimbursement",),
            query_fn=payroll.reimbursement_register,
            explorer_url_name="payroll-report",
            export_model="payroll.Reimbursement",
            required_apps=("payroll",),
            filter_fields=_PAYROLL,
        )
    )
    register(
        ReportDefinition(
            slug="asset-register",
            name=_("Asset Register"),
            domain="compliance",
            description=_(
                "Asset inventory by status, and how long each assigned asset "
                "has been held -- the offboarding recovery control."
            ),
            permission="asset.view_asset",
            alt_permissions=("employee.view_employee",),
            query_fn=compliance.asset_register,
            export_model="asset.Asset",
            required_apps=("asset",),
            filter_fields=_COMPLIANCE,
        )
    )


_load()
