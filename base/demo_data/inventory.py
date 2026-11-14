"""Zero-row inventory of SIDEBAR list models after demo seed.

Source of truth for "visible" is `SIDEBARS` plus Base request / holiday /
mail / tag screens. Hardware (biometric, geofence, face) is omitted on
purpose. Run `python manage.py demo_data_inventory` after load_demo_data.
"""

from __future__ import annotations

from django.apps import apps

# (app_label, ModelName) — one row per list the demo walkthrough opens.
SIDEBAR_DEMO_MODELS: tuple[tuple[str, str], ...] = (
    ("employee", "Employee"),
    ("attendance", "Attendance"),
    ("attendance", "AttendanceActivity"),
    ("attendance", "AttendanceOverTime"),
    ("leave", "LeaveRequest"),
    ("leave", "AvailableLeave"),
    ("leave", "LeaveType"),
    ("payroll", "Payslip"),
    ("payroll", "Contract"),
    ("payroll", "LoanAccount"),
    ("recruitment", "Recruitment"),
    ("recruitment", "Candidate"),
    ("recruitment", "InterviewSchedule"),
    ("onboarding", "OnboardingStage"),
    ("offboarding", "Offboarding"),
    ("surveys", "Survey"),
    ("pms", "EmployeeObjective"),
    ("project", "Project"),
    ("project", "TimeSheet"),
    ("asset", "Asset"),
    ("asset", "AssetRequest"),
    ("asset", "AssetAssignment"),
    ("helpdesk", "Ticket"),
    ("report", "ReportTemplate"),
    ("base", "ShiftRequest"),
    ("base", "WorkTypeRequest"),
    ("base", "Holidays"),
    ("base", "Announcement"),
    ("base", "RotatingShiftAssign"),
    ("base", "RotatingWorkTypeAssign"),
    ("base", "Tags"),
    ("base", "HorillaMailTemplate"),
    ("horilla_automations", "MailAutomation"),
)


def count_sidebar_models() -> list[tuple[str, int]]:
    """Return `(app.Model, count)` for installed inventory models."""
    out: list[tuple[str, int]] = []
    for app, model in SIDEBAR_DEMO_MODELS:
        if not apps.is_installed(app):
            continue
        Model = apps.get_model(app, model)
        out.append((f"{app}.{model}", Model._base_manager.count()))
    return out


def zero_row_models() -> list[str]:
    return [label for label, n in count_sidebar_models() if n == 0]
