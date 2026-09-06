"""
Shared filter context and helpers for standard reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext as _

EMPLOYMENT_STATUS_ACTIVE = "active"
EMPLOYMENT_STATUS_INACTIVE = "inactive"
EMPLOYMENT_STATUS_ALL = "all"

PERIOD_PRESETS = {
    "this_month",
    "last_month",
    "last_30",
    "last_90",
    "quarter",
    "ytd",
    "last_year",
    "all_time",
    "custom",
}

# Wide sentinel window for ``all_time`` — metrics keep required date fields.
ALL_TIME_FROM = date(2010, 1, 1)


@dataclass
class ReportFilters:
    """Normalized filter set for metric queries."""

    from_date: date
    to_date: date
    department_id: Optional[int] = None
    job_position_id: Optional[int] = None
    job_role_id: Optional[int] = None
    employee_type_id: Optional[int] = None
    work_type_id: Optional[int] = None
    shift_id: Optional[int] = None
    company_id: Optional[int] = None
    reporting_manager_id: Optional[int] = None
    location: Optional[str] = None
    gender: Optional[str] = None
    employment_status: str = EMPLOYMENT_STATUS_ACTIVE
    leave_type_id: Optional[int] = None
    leave_status: Optional[str] = None
    recruitment_id: Optional[int] = None
    source: Optional[str] = None
    offer_letter_status: Optional[str] = None
    payslip_status: Optional[str] = None
    period_preset: str = "this_month"
    compare_preset: str = "none"
    request: Optional[HttpRequest] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def period_label(self) -> str:
        if self.period_preset == "all_time":
            return "All time"
        return f"{self.from_date.isoformat()} → {self.to_date.isoformat()}"

    # Marker for the period row. summary_labels() renders that row as a bare
    # value rather than "Label: value", and it used to detect it by comparing
    # the label against the literal "Period" -- which silently stopped
    # matching the moment the label became translatable.
    PERIOD_LABEL_KEY = "period"

    def summary_pairs(self) -> list[tuple[str, str]]:
        """Structured (label, value) pairs for the active filters, with FK ids
        resolved to their display names — the audit-ready form consumed by the
        export cover sheets / PDF header. Resolution is best-effort: a deleted
        or unresolvable row falls back to ``#<id>`` rather than erroring.

        Labels are translated: these appear on the cover sheet of every Excel
        and PDF export, and previously stayed English while the rest of the
        document rendered in the tenant's language.
        """
        pairs: list[tuple[str, str]] = [(str(_("Period")), self.period_label)]
        if self.period_preset and self.period_preset not in ("custom", "all_time"):
            pairs.append(
                (
                    str(_("Period preset")),
                    self.period_preset.replace("_", " ").capitalize(),
                )
            )
        if self.compare_preset and self.compare_preset not in ("none", "", None):
            pairs.append(
                (
                    str(_("Compared against")),
                    self.compare_preset.replace("_", " ").capitalize(),
                )
            )
        if self.employment_status and self.employment_status != EMPLOYMENT_STATUS_ALL:
            pairs.append(
                (str(_("Employment status")), self.employment_status.capitalize())
            )
        fk_specs = [
            (_("Department"), self.department_id, "base", "Department"),
            (_("Job position"), self.job_position_id, "base", "JobPosition"),
            (_("Job role"), self.job_role_id, "base", "JobRole"),
            (_("Employee type"), self.employee_type_id, "base", "EmployeeType"),
            (_("Work type"), self.work_type_id, "base", "WorkType"),
            (_("Shift"), self.shift_id, "base", "EmployeeShift"),
            (_("Company"), self.company_id, "base", "Company"),
            (
                _("Reporting manager"),
                self.reporting_manager_id,
                "employee",
                "Employee",
            ),
            (_("Leave type"), self.leave_type_id, "leave", "LeaveType"),
            (_("Recruitment"), self.recruitment_id, "recruitment", "Recruitment"),
        ]
        for label, pk, app_label, model_name in fk_specs:
            if pk:
                pairs.append((str(label), _resolve_display(app_label, model_name, pk)))
        if self.location:
            pairs.append((str(_("Location")), self.location))
        if self.gender:
            pairs.append((str(_("Gender")), self.gender.capitalize()))
        if self.leave_status:
            pairs.append((str(_("Leave status")), self.leave_status.capitalize()))
        if self.source:
            pairs.append((str(_("Source")), self.source))
        if self.offer_letter_status:
            pairs.append(
                (str(_("Offer letter status")), self.offer_letter_status.capitalize())
            )
        if self.payslip_status:
            pairs.append((str(_("Payslip status")), self.payslip_status.capitalize()))
        return pairs

    def summary_labels(self) -> list[str]:
        """Human-readable active filter chips for UI / export — derived from
        ``summary_pairs`` so chips carry resolved names, not raw FK ids."""
        chips = []
        period_label = str(_("Period"))
        for label, value in self.summary_pairs():
            # The period row reads as a bare value ("2026-01-01 → 2026-01-31"),
            # every other row as "Label: value".
            chips.append(value if label == period_label else f"{label}: {value}")
        return chips


def _resolve_display(app_label: str, model_name: str, pk: int) -> str:
    """FK id → the row's ``str()`` display, falling back to ``#<id>`` when the
    app isn't installed, the row was deleted, or anything else goes wrong.
    Never raises — export paths must keep working on partial data."""
    try:
        from django.apps import apps as django_apps

        model = django_apps.get_model(app_label, model_name)
        obj = model.objects.filter(pk=pk).first()
        if obj is not None:
            text = str(obj).strip()
            if text:
                return text
    except Exception:
        pass
    return f"#{pk}"


def _parse_int(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_period_preset(
    preset: str, today: Optional[date] = None
) -> tuple[date, date]:
    """Return (from_date, to_date) for a named preset."""
    today = today or date.today()
    preset = (preset or "this_month").lower()

    if preset == "last_30":
        return today - timedelta(days=29), today
    if preset == "last_90":
        return today - timedelta(days=89), today
    if preset == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if preset == "quarter":
        q = (today.month - 1) // 3
        start_month = q * 3 + 1
        return date(today.year, start_month, 1), today
    if preset == "ytd":
        return date(today.year, 1, 1), today
    if preset == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if preset == "all_time":
        return ALL_TIME_FROM, today
    # this_month / default
    return today.replace(day=1), today


def parse_period(
    request: Optional[HttpRequest] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    preset: Optional[str] = None,
) -> tuple[date, date, str]:
    """
    Parse period from request GET or explicit dates.
    Returns (from_date, to_date, effective_preset).
    """
    today = date.today()
    preset = (
        preset or (request.GET.get("period_preset") if request else None) or ""
    ).lower()
    if preset and preset in PERIOD_PRESETS and preset != "custom":
        start, end = resolve_period_preset(preset, today)
        return start, end, preset

    if request is not None:
        from_str = request.GET.get("from_date")
        to_str = request.GET.get("to_date")
        try:
            from_date = (
                date.fromisoformat(from_str)
                if from_str
                else (from_date or today.replace(day=1))
            )
        except (ValueError, TypeError):
            from_date = from_date or today.replace(day=1)
        try:
            to_date = date.fromisoformat(to_str) if to_str else (to_date or today)
        except (ValueError, TypeError):
            to_date = to_date or today
    else:
        from_date = from_date or today.replace(day=1)
        to_date = to_date or today

    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date, preset or "custom"


def filters_from_request(request: HttpRequest) -> ReportFilters:
    """Build ReportFilters from a request."""
    from_date, to_date, preset = parse_period(request)
    status = (request.GET.get("employment_status") or EMPLOYMENT_STATUS_ACTIVE).lower()
    if status not in (
        EMPLOYMENT_STATUS_ACTIVE,
        EMPLOYMENT_STATUS_INACTIVE,
        EMPLOYMENT_STATUS_ALL,
    ):
        status = EMPLOYMENT_STATUS_ACTIVE

    location = (request.GET.get("location") or "").strip() or None
    gender = (request.GET.get("gender") or "").strip().lower() or None
    if gender and gender not in ("male", "female", "other"):
        gender = None

    return ReportFilters(
        from_date=from_date,
        to_date=to_date,
        department_id=_parse_int(
            request.GET.get("department_id") or request.GET.get("department")
        ),
        job_position_id=_parse_int(request.GET.get("job_position_id")),
        job_role_id=_parse_int(request.GET.get("job_role_id")),
        employee_type_id=_parse_int(request.GET.get("employee_type_id")),
        work_type_id=_parse_int(request.GET.get("work_type_id")),
        shift_id=_parse_int(request.GET.get("shift_id")),
        company_id=_parse_int(request.GET.get("company_id")),
        reporting_manager_id=_parse_int(request.GET.get("reporting_manager_id")),
        location=location,
        gender=gender,
        employment_status=status,
        leave_type_id=_parse_int(request.GET.get("leave_type_id")),
        leave_status=(request.GET.get("leave_status") or "").strip() or None,
        recruitment_id=_parse_int(request.GET.get("recruitment_id")),
        source=(request.GET.get("source") or "").strip() or None,
        offer_letter_status=(request.GET.get("offer_letter_status") or "").strip()
        or None,
        payslip_status=(request.GET.get("payslip_status") or "").strip() or None,
        period_preset=preset or "custom",
        compare_preset=_normalize_compare(request.GET.get("compare_preset")),
        request=request,
    )


def _normalize_compare(value) -> str:
    from report.compare import normalize_compare_preset

    return normalize_compare_preset(value)


def filters_from_dict(
    raw: Optional[dict] = None,
    *,
    default_company_id: Optional[int] = None,
) -> ReportFilters:
    """
    Build ReportFilters from a saved subscription / preset dict.

    Accepts period_preset (preferred) or legacy ``period`` key.
    """
    raw = raw or {}
    today = date.today()
    preset = raw.get("period_preset") or raw.get("period") or "this_month"
    if preset == "month":
        preset = "this_month"

    from_date = None
    to_date = None
    if preset == "custom" or raw.get("from_date") or raw.get("to_date"):
        try:
            from_date = (
                date.fromisoformat(raw["from_date"]) if raw.get("from_date") else None
            )
        except (TypeError, ValueError):
            from_date = None
        try:
            to_date = date.fromisoformat(raw["to_date"]) if raw.get("to_date") else None
        except (TypeError, ValueError):
            to_date = None
        if from_date and to_date:
            preset = "custom"
        else:
            from_date, to_date = resolve_period_preset(
                preset if preset != "custom" else "this_month", today
            )
            preset = preset if preset != "custom" else "this_month"
    else:
        from_date, to_date = resolve_period_preset(preset, today)

    status = (raw.get("employment_status") or EMPLOYMENT_STATUS_ACTIVE).lower()
    if status not in (
        EMPLOYMENT_STATUS_ACTIVE,
        EMPLOYMENT_STATUS_INACTIVE,
        EMPLOYMENT_STATUS_ALL,
    ):
        status = EMPLOYMENT_STATUS_ACTIVE

    gender = (raw.get("gender") or "").strip().lower() or None
    if gender and gender not in ("male", "female", "other"):
        gender = None

    company_id = _parse_int(raw.get("company_id"))
    if company_id is None:
        company_id = default_company_id

    return ReportFilters(
        from_date=from_date,
        to_date=to_date,
        department_id=_parse_int(raw.get("department_id") or raw.get("department")),
        job_position_id=_parse_int(raw.get("job_position_id")),
        job_role_id=_parse_int(raw.get("job_role_id")),
        employee_type_id=_parse_int(raw.get("employee_type_id")),
        work_type_id=_parse_int(raw.get("work_type_id")),
        shift_id=_parse_int(raw.get("shift_id")),
        company_id=company_id,
        reporting_manager_id=_parse_int(raw.get("reporting_manager_id")),
        location=(raw.get("location") or "").strip() or None,
        gender=gender,
        employment_status=status,
        leave_type_id=_parse_int(raw.get("leave_type_id")),
        leave_status=(raw.get("leave_status") or "").strip() or None,
        recruitment_id=_parse_int(raw.get("recruitment_id")),
        source=(raw.get("source") or "").strip() or None,
        offer_letter_status=(raw.get("offer_letter_status") or "").strip() or None,
        payslip_status=(raw.get("payslip_status") or "").strip() or None,
        period_preset=preset or "custom",
        compare_preset=_normalize_compare(raw.get("compare_preset")),
    )


def month_offset(d: date, months_back: int) -> date:
    """First day of the month that is ``months_back`` months before ``d``."""
    year = d.year
    month = d.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def month_bounds(d: date) -> tuple[date, date]:
    """Return (month_start, month_end) for the month containing ``d``."""
    month_start = d.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return month_start, next_month - timedelta(days=1)


def iter_months(to_date: date, months_back: int = 6):
    """Yield (month_start, month_end, label) for the last ``months_back`` months."""
    for i in range(months_back - 1, -1, -1):
        start = month_offset(to_date, i)
        _, end = month_bounds(start)
        yield start, end, start.strftime("%b %Y")


def apply_department_filter(
    qs: QuerySet,
    department_id: Optional[int],
    path: str = "employee_work_info__department_id",
) -> QuerySet:
    """Filter a queryset by department when provided."""
    if department_id:
        return qs.filter(**{path: department_id})
    return qs


def apply_org_filters(
    qs: QuerySet,
    filters: ReportFilters,
    *,
    prefix: str = "employee_work_info",
    employee_prefix: str = "",
    apply_employment_status: bool = True,
) -> QuerySet:
    """
    Apply shared organizational filters.

    ``prefix`` is the relation path to EmployeeWorkInformation fields
    (e.g. ``employee_work_info``, ``employee_id__employee_work_info``).
    ``employee_prefix`` is the path to Employee fields for gender/is_active
    (e.g. ``""`` on Employee, ``employee_id`` on related models).
    """

    def p(field: str) -> str:
        return f"{prefix}__{field}" if prefix else field

    def e(field: str) -> str:
        return f"{employee_prefix}__{field}" if employee_prefix else field

    if filters.department_id:
        qs = qs.filter(**{p("department_id"): filters.department_id})
    if filters.job_position_id:
        qs = qs.filter(**{p("job_position_id"): filters.job_position_id})
    if filters.job_role_id:
        qs = qs.filter(**{p("job_role_id"): filters.job_role_id})
    if filters.employee_type_id:
        qs = qs.filter(**{p("employee_type_id"): filters.employee_type_id})
    if filters.work_type_id:
        qs = qs.filter(**{p("work_type_id"): filters.work_type_id})
    if filters.shift_id:
        qs = qs.filter(**{p("shift_id"): filters.shift_id})
    if filters.company_id:
        qs = qs.filter(**{p("company_id"): filters.company_id})
    if filters.reporting_manager_id:
        qs = qs.filter(**{p("reporting_manager_id"): filters.reporting_manager_id})
    if filters.location:
        qs = qs.filter(**{f"{p('location')}__icontains": filters.location})
    if filters.gender:
        qs = qs.filter(**{e("gender"): filters.gender})
    if apply_employment_status:
        if filters.employment_status == EMPLOYMENT_STATUS_ACTIVE:
            qs = qs.filter(**{e("is_active"): True})
        elif filters.employment_status == EMPLOYMENT_STATUS_INACTIVE:
            qs = qs.filter(**{e("is_active"): False})
    return qs


def selected_company_id(request: Optional[HttpRequest]) -> Optional[str]:
    """Return session selected_company when not 'all'."""
    if not request:
        return None
    company = request.session.get("selected_company")
    if company and company != "all":
        return str(company)
    return None


def empty_report(title: str, filters: ReportFilters, message: str = "") -> dict:
    """Standard empty payload shape."""
    return {
        "title": title,
        "kpis": [],
        "charts": [],
        "table": {"columns": [], "rows": []},
        "period": {
            "from_date": filters.from_date.isoformat(),
            "to_date": filters.to_date.isoformat(),
            "preset": filters.period_preset,
            "label": filters.period_label,
        },
        "filters": filters.summary_labels(),
        "message": message,
    }
