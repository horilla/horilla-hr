"""
Home-dashboard role resolution and chart preference defaults.

Locked decisions (plans/horilla-hr-main-dashboard-redesign.md):
- Leadership = superuser/staff OR (employee + leave + recruitment view)
- HR = employee.view_employee ∧ leave.view_leaverequest
- Manager = reporting manager and not HR/Leadership
- Employee = everyone else → ESS home
"""

from __future__ import annotations

from typing import Literal

HomeRole = Literal["employee", "manager", "hr", "leadership"]

# Charts demoted from default home (still available via Customize).
DEMOTED_BY_DEFAULT = (
    "employee_status",
    "leave_by_department",
    "department_leave_days",
    "hiring_timeline",
    "recruitment_funnel",
)

# Charts shown by default for manager/HR/leadership when prefs are empty.
# Employee role does not use the analytics home.
_BASE_VISIBLE = (
    "department_headcount",
    "gender_distribution",
    "leave_breakdown",
    "leave_trends",
    "attendance_trend",
    "department_overtime",
    "attendance_overview",
    "leave_coverage",
)

ROLE_DEFAULT_VISIBLE: dict[str, tuple[str, ...]] = {
    "manager": _BASE_VISIBLE,
    "hr": _BASE_VISIBLE
    + (
        "recruitment_pipeline",
        "employee_turnover",
    ),
    "leadership": _BASE_VISIBLE
    + (
        "recruitment_pipeline",
        "employee_turnover",
        "payroll_summary",
    ),
    "employee": (),
}


def _is_reporting_manager(user) -> bool:
    try:
        emp = getattr(user, "employee_get", None)
        if not emp:
            return False
        from employee.models import EmployeeWorkInformation

        return EmployeeWorkInformation.objects.filter(reporting_manager_id=emp).exists()
    except Exception:
        return False


def resolve_home_role(request) -> HomeRole:
    """
    Return the home-dashboard persona for this request.

    Optional QA override: ``?home_role=`` for staff/superuser only.
    """
    user = request.user
    override = request.GET.get("home_role") or request.session.get("home_role_override")
    if override in ("employee", "manager", "hr", "leadership"):
        if user.is_superuser or user.is_staff:
            return override  # type: ignore[return-value]

    if user.is_superuser or user.is_staff:
        return "leadership"

    has_employee = user.has_perm("employee.view_employee")
    has_leave = user.has_perm("leave.view_leaverequest")
    has_recruitment = user.has_perm("recruitment.view_recruitment")

    if has_employee and has_leave and has_recruitment:
        return "leadership"

    if has_employee and has_leave:
        return "hr"

    if _is_reporting_manager(user):
        return "manager"

    return "employee"


def role_default_prefs(
    role: HomeRole, available_chart_ids: list[str] | None = None
) -> list[dict]:
    """
    Build ``[{id, visible}, ...]`` for a role.

    Charts not in the role's visible set default to hidden when present in DOM.
    """
    visible = set(ROLE_DEFAULT_VISIBLE.get(role, ()))
    # Never show demoted vanity charts by default
    visible -= set(DEMOTED_BY_DEFAULT)

    ids = available_chart_ids
    if ids is None:
        # Full known catalog — template will ignore unknown ids
        ids = list(
            dict.fromkeys(
                list(DEMOTED_BY_DEFAULT)
                + list(_BASE_VISIBLE)
                + [
                    "recruitment_pipeline",
                    "employee_turnover",
                    "payroll_summary",
                    "leave_coverage",
                ]
            )
        )

    prefs = []
    for chart_id in ids:
        prefs.append({"id": chart_id, "visible": chart_id in visible})
    return prefs


def can_see_analytics_home(role: HomeRole) -> bool:
    return role in ("manager", "hr", "leadership")
