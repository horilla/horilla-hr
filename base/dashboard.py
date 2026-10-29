"""
Modern dashboard views — KPI summary + ApexCharts.

Accessible at /dashboard/modern/ alongside the existing dashboard.
"""

import calendar
import json
from datetime import date, timedelta

from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from horilla.decorators import login_required


def _safe_url(url_name, query=""):
    """Reverse a URL name with an optional query string; return '#' if the URL is not registered."""
    try:
        return reverse(url_name) + query
    except Exception:
        return "#"


# ---------------------------------------------------------------------------
# Setup checklist helpers
# ---------------------------------------------------------------------------


def _is_setup_admin(request):
    """
    True for superusers, staff, and any user who can manage HR setup entities.
    Regular employees (no management perms) are excluded — they can't complete
    setup steps and should not see setup prompts.
    """
    user = request.user
    if user.is_superuser or user.is_staff:
        return True
    return user.has_perm("base.add_department") or user.has_perm("base.add_company")


def _resolve_checklist_company(request):
    """
    Return the integer PK of the company currently active for this request.

    Priority:
      1. The company stored in the ContextVar by the middleware
      2. The first company in the DB (fresh install with no session yet)
      3. None  (no company exists — the "Company" step is the first to do)
    """
    from horilla.horilla_middlewares import get_selected_company

    company_id = get_selected_company()
    if company_id and company_id != "all":
        try:
            return int(company_id)
        except (TypeError, ValueError):
            pass

    # "all" or None → fall back to first company in the DB
    from base.models import Company

    first = Company.objects.first()
    return first.pk if first else None


def _exists_for_company(ModelClass, company_id):
    """
    Return True if at least one record of ModelClass is visible for the given
    company.  Mirrors HorillaCompanyManager: a record is visible when it is
    explicitly assigned to this company OR has no company assignment at all
    (meaning it is shared across all companies — common for lookup tables like
    WorkType, EmployeeType, EmployeeShift whose M2M company_id may be empty).
    """
    try:
        filter_path = ModelClass.objects.get_company_filter_path()
        if not filter_path:
            return False
        null_path = f"{filter_path}__isnull"
        return (
            ModelClass.objects.entire()
            .filter(Q(**{filter_path: company_id}) | Q(**{null_path: True}))
            .exists()
        )
    except Exception:
        return False


def _get_setup_checklist_context(request):
    """
    Builds the context for the onboarding setup checklist banner.

    Returns ``{"show_setup_checklist": False}`` when:
      • the user is not an admin/manager (regular employees skip it)
      • the user has already dismissed the banner for the active company
      • all 8 steps are complete for the active company

    In DEBUG mode only, ``?preview_checklist=1`` forces the banner visible
    with every step shown as incomplete — useful for testing on populated DBs
    without deleting any data.
    """
    from django.conf import settings

    from base.models import (
        Company,
        Department,
        DynamicEmailConfiguration,
        EmployeeShift,
        EmployeeShiftSchedule,
        JobPosition,
        SetupChecklistDismissal,
        WorkType,
    )

    # 1. Permission gate — only show to admins / managers
    if not _is_setup_admin(request):
        return {"show_setup_checklist": False}

    preview_mode = settings.DEBUG and request.GET.get("preview_checklist") == "1"

    # 2. Resolve the company we're scoping the checklist to
    company_pk = _resolve_checklist_company(request)

    # 3. Check per-user, per-company dismissal
    if not preview_mode:
        dismissed = SetupChecklistDismissal.objects.filter(
            user=request.user, company_id=company_pk
        ).exists()
        if dismissed:
            return {"show_setup_checklist": False}

    # 4. Build steps — each checks live DB scoped to the active company
    def _has_company():
        # Company itself is the root tenant object; any company existing is enough.
        try:
            return Company.objects.exists()
        except Exception:
            return False

    def _has_employees():
        try:
            from employee.models import Employee

            return _exists_for_company(Employee, company_pk)
        except Exception:
            return False

    def _has_imported():
        # Optional step: a finished Master Data Import counts, whoever ran it.
        try:
            from master_import.models import ImportJob

            return ImportJob.objects.filter(status=ImportJob.DONE).exists()
        except Exception:
            return False

    def _has_mail_server():
        try:
            return DynamicEmailConfiguration.objects.filter(
                is_primary=True, host__isnull=False
            ).exists()
        except Exception:
            return False

    steps = [
        {
            "key": "company",
            "title": _("Company"),
            "description": _("Add your company profile — name, logo and timezone."),
            "url": _safe_url("company-view"),
            "done": _has_company(),
        },
        {
            "key": "department",
            "title": _("Departments"),
            "description": _("Create the departments your employees will belong to."),
            "url": _safe_url("department-view"),
            "done": (
                _exists_for_company(Department, company_pk) if company_pk else False
            ),
        },
        {
            "key": "job_position",
            "title": _("Job Positions"),
            "description": _("Define named roles within each department."),
            "url": _safe_url("job-position-view"),
            "done": (
                _exists_for_company(JobPosition, company_pk) if company_pk else False
            ),
        },
        {
            "key": "shift",
            "title": _("Shift"),
            "description": _("Define working schedules — Morning, Evening, Night."),
            "url": _safe_url("employee-settings-view", "?tab=shift"),
            "done": (
                _exists_for_company(EmployeeShift, company_pk) if company_pk else False
            ),
        },
        {
            "key": "shift_schedule",
            "title": _("Shift Schedule"),
            "description": _("Set day-wise timings for each shift."),
            "url": _safe_url("employee-settings-view", "?tab=shift-schedule"),
            "done": (
                _exists_for_company(EmployeeShiftSchedule, company_pk)
                if company_pk
                else False
            ),
        },
        {
            "key": "work_type",
            "title": _("Work Type"),
            "description": _("Set engagement types — Full Time, Part Time, Contract."),
            "url": _safe_url("employee-settings-view", "?tab=work-type"),
            "done": _exists_for_company(WorkType, company_pk) if company_pk else False,
        },
        {
            "key": "mail_server",
            "title": _("Mail Server"),
            "description": _(
                "Configure an outgoing mail server so Horilla can send emails."
            ),
            "url": _safe_url("mail-server-conf"),
            "done": _has_mail_server(),
        },
        {
            "key": "master_import",
            "title": _("Import Data"),
            "description": _(
                "Bring in employees, leave balances and assets from a spreadsheet."
            ),
            "url": _safe_url("master-import"),
            "done": _has_imported(),
            # Not needed to finish setup: the checklist can hide without it.
            "optional": True,
        },
        {
            "key": "first_employee",
            "title": _("First Employee"),
            "description": _("Add your first employee to bring everything together."),
            "url": _safe_url("employee-view-new"),
            "done": _has_employees() if company_pk else False,
        },
    ]

    # Only installed apps get a step; an import is a convenience, not a requirement.
    from django.apps import apps

    if not apps.is_installed("master_import"):
        steps = [s for s in steps if s["key"] != "master_import"]

    # 5. Preview mode overrides all done flags to False
    if preview_mode:
        for s in steps:
            s["done"] = False

    completed = sum(1 for s in steps if s["done"])
    total = len(steps)

    # Auto-hide once every required step is complete (no dismiss record needed)
    required = [s for s in steps if not s.get("optional")]
    if not preview_mode and all(s["done"] for s in required):
        return {"show_setup_checklist": False}

    # 6. Precompute connector-line state for the template.
    for i, step in enumerate(steps):
        step["left_line_active"] = (i > 0) and steps[i - 1]["done"]
        step["right_line_active"] = step["done"] and (i < total - 1)

    next_step = next((s for s in steps if not s["done"]), None)
    progress_pct = int(completed / total * 100)

    return {
        "show_setup_checklist": True,
        "setup_steps": steps,
        "setup_completed": completed,
        "setup_total": total,
        "setup_next_step": next_step,
        "setup_progress_pct": progress_pct,
        "setup_dismiss_url": _safe_url("dashboard-dismiss-setup-checklist"),
        "setup_company_pk": company_pk,
    }


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to current month."""
    today = date.today()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = date.fromisoformat(from_str) if from_str else today.replace(day=1)
    except (ValueError, TypeError):
        from_date = today.replace(day=1)
    try:
        to_date = date.fromisoformat(to_str) if to_str else today
    except (ValueError, TypeError):
        to_date = today
    return from_date, to_date


def _current_month_bounds():
    """Return (first_day, last_day) of the current calendar month.

    Always derived from ``date.today()`` -- never cached -- so every chart
    that calls this rolls over to the new month on its own, with no stored
    "current period" to go stale.
    """
    today = date.today()
    _, last_day_num = calendar.monthrange(today.year, today.month)
    return today.replace(day=1), today.replace(day=last_day_num)


def _is_manager(user):
    """Return True if user is a reporting manager for at least one active employee."""
    try:
        from employee.models import EmployeeWorkInformation

        emp = getattr(user, "employee_get", None)
        if not emp:
            return False
        return EmployeeWorkInformation.objects.filter(reporting_manager_id=emp).exists()
    except Exception:
        return False


def _leave_request_list_qs(request):
    """Same rows request-view lists: subordinates ∪ multi-level approval queue."""
    from base.methods import filtersubordinates
    from leave.methods import filter_conditional_leave_request
    from leave.models import LeaveRequest

    data = LeaveRequest.objects.all()
    conditional_ids = filter_conditional_leave_request(request).values_list(
        "id", flat=True
    )
    return (
        filtersubordinates(request, data, "leave.view_leaverequest")
        | data.filter(id__in=conditional_ids)
    ).distinct()


def _today_leave_qs(request, today, status="approved"):
    statuses = [status] if isinstance(status, str) else status
    return (
        _leave_request_list_qs(request)
        .filter(status__in=statuses, start_date__lte=today)
        .filter(Q(end_date__gte=today) | Q(end_date__isnull=True, start_date=today))
    )


def _scoped_active_employee_ids(request):
    """
    Return subordinate employee PKs when the user lacks org-wide employee view.

    ``None`` means company-scoped (HorillaCompanyManager) — no extra filter.
    """
    user = request.user
    if user.is_superuser or user.has_perm("employee.view_employee"):
        return None
    try:
        from base.methods import filtersubordinatesemployeemodel
        from employee.models import Employee

        qs = filtersubordinatesemployeemodel(
            request,
            Employee.objects.filter(is_active=True),
            perm="employee.view_employee",
        )
        return list(qs.values_list("id", flat=True))
    except Exception:
        return []


def _company_scope_context(request) -> dict:
    """Active company label for KPI / header chrome."""
    selected = request.session.get("selected_company")
    if not selected or selected == "all":
        return {
            "dashboard_company_label": str(_("All companies")),
            "dashboard_company_is_all": True,
        }
    try:
        from base.models import Company

        company = Company.objects.filter(id=int(selected)).only("company").first()
        label = company.company if company else str(_("Company"))
    except Exception:
        label = str(_("Company"))
    return {
        "dashboard_company_label": label,
        "dashboard_company_is_all": False,
    }


@login_required
def main_dashboard_view(request):
    """Render the modern analytics dashboard (manager/HR/leadership).

    Pure employees are redirected to ESS unless ``?view=analytics`` is set
    (explicit switch from ESS).
    """
    from django.apps import apps
    from django.shortcuts import redirect

    from base.dashboard_roles import (
        can_see_analytics_home,
        resolve_home_role,
        role_default_prefs,
    )

    home_role = resolve_home_role(request)
    if not can_see_analytics_home(home_role) and request.GET.get("view") != "analytics":
        return redirect("ess-dashboard")

    enabled_timerunner = True
    get_forecasted_at_work = None

    if apps.is_installed("attendance"):
        try:
            from base.context_processors import timerunner_enabled

            enabled_timerunner = timerunner_enabled(request)["enabled_timerunner"]
        except Exception:
            pass

        try:
            get_forecasted_at_work = request.user.employee_get.get_forecasted_at_work()
        except Exception:
            pass

    # Load saved chart preferences from DB for the current employee
    employee_chart_prefs = "[]"
    try:
        from base.models import DashboardEmployeeCharts

        emp = request.user.employee_get
        obj = DashboardEmployeeCharts.objects.filter(employee=emp).first()
        if obj and obj.charts is not None:
            normalized = _normalize_dashboard_chart_prefs(obj.charts)
            # Persist migration when legacy string-list prefs are detected
            if obj.charts and isinstance(obj.charts, list) and obj.charts != normalized:
                if obj.charts and isinstance(obj.charts[0], str):
                    obj.charts = normalized
                    obj.save(update_fields=["charts"])
            employee_chart_prefs = json.dumps(normalized)
    except Exception:
        pass

    context = {
        "enabled_timerunner": enabled_timerunner,
        "get_forecasted_at_work": get_forecasted_at_work,
        "employee_chart_prefs": employee_chart_prefs,
        "home_role": home_role,
        "role_default_prefs": json.dumps(role_default_prefs(home_role)),
    }
    context.update(_company_scope_context(request))
    context.update(_get_setup_checklist_context(request))
    return render(request, "dashboard.html", context)


def _normalize_dashboard_chart_prefs(charts):
    """
    Modern prefs are ``[{id, visible}, ...]``.
    Legacy FAB prefs stored excluded chart id strings — incompatible with the
    modern dashboard; treat those as empty (all charts visible by default).
    """
    if not charts or not isinstance(charts, list):
        return []
    if isinstance(charts[0], str):
        return []
    clean = []
    for item in charts:
        if isinstance(item, dict) and item.get("id"):
            clean.append({"id": item["id"], "visible": item.get("visible", True)})
    return clean


@login_required
@require_http_methods(["POST"])
def dismiss_setup_checklist(request):
    """
    HTMX endpoint — records per-user, per-company dismissal and returns empty
    HTML so the banner is removed via outerHTML swap.
    Only admins can dismiss (non-admins never see the banner anyway).
    """
    from base.models import SetupChecklistDismissal

    if _is_setup_admin(request):
        company_pk = _resolve_checklist_company(request)
        SetupChecklistDismissal.objects.get_or_create(
            user=request.user,
            company_id=company_pk,
        )
    return HttpResponse("")


@login_required
def dashboard_kpi_data(request):
    """Return KPI summary data as JSON."""
    from employee.models import Employee

    # KPI tiles are live "today" figures; the dashboard's date filter never applies.
    real_today = date.today()
    scoped_ids = _scoped_active_employee_ids(request)

    emp_qs = Employee.objects.filter(is_active=True)
    if scoped_ids is not None:
        emp_qs = emp_qs.filter(id__in=scoped_ids)
    total_employees = emp_qs.count()

    # The tile reads "+N This Month", so this is always the current calendar
    # month (not the picker's range) and only counts active employees.
    new_joiners = 0
    try:
        from employee.models import EmployeeWorkInformation

        new_joiners = EmployeeWorkInformation.objects.filter(
            date_joining__gte=real_today.replace(day=1),
            date_joining__lte=real_today,
            employee_id__in=emp_qs,
        ).count()
    except Exception:
        pass

    # Distinct employees, not leave requests — an employee with two
    # overlapping approved leave records must still count once.
    on_leave_employee_ids = set()
    full_day_leave_ids = set()
    half_day_today = 0
    try:
        leave_qs = _today_leave_qs(
            request, real_today, status=["approved", "cancel_requested"]
        )
        from attendance.dashboard import half_day_leave_q, leave_employee_ids

        on_leave_employee_ids, full_day_leave_ids = leave_employee_ids(
            leave_qs, real_today
        )
        half_day_today = (
            leave_qs.filter(half_day_leave_q(real_today))
            .values("employee_id")
            .distinct()
            .count()
        )
    except Exception:
        pass
    on_leave = len(on_leave_employee_ids)

    present_today = 0
    present_ids = set()
    try:
        from attendance.models import Attendance

        present_qs = Attendance.objects.filter(
            attendance_date=real_today, employee_id__in=emp_qs
        )
        # Someone on a full-day approved leave counts as on leave, not as
        # checked in. A half-day leave with an attendance record still counts
        # as checked in (and as on leave).
        present_ids = (
            set(present_qs.values_list("employee_id", flat=True)) - full_day_leave_ids
        )
        present_today = len(present_ids)
    except Exception:
        pass

    # Expected = active employees not on approved leave (excludes leave from
    # the denominator so "absent" is not inflated by people who should be out).
    # Only employees with a shift are expected in, plus anyone without one
    # who checked in anyway, and anyone on leave who is present anyway
    # (attendance.dashboard.expected_today_ids, the same rule as the
    # Attendance dashboard). The headcount counts everyone.
    expected_ids = set()
    try:
        from attendance.dashboard import expected_today_ids

        expected_ids = expected_today_ids(
            emp_qs, real_today, present_ids, on_leave_employee_ids
        )
    except Exception:
        expected_ids = (
            set(emp_qs.values_list("id", flat=True)) - on_leave_employee_ids
        ) | present_ids
    expected_today = len(expected_ids)
    # Counted as a set difference, not total - present - on_leave: someone on
    # a half-day leave who also clocked in is in both of those sets, and
    # subtracting both would count them out twice. This is the same
    # definition as the employee list's "expected_to_check_in" filter
    # (attendance/filters.py), which the card drills into, so the tile and
    # the list always agree. The Attendance dashboard's own Offline card is
    # a different, shift-aware metric.
    not_checked_in = (
        emp_qs.filter(id__in=expected_ids)
        .exclude(id__in=present_ids)
        .exclude(id__in=on_leave_employee_ids)
        .count()
    )
    # On a weekly off or holiday nobody is expected in, so whoever hasn't
    # checked in is on week off rather than absent.
    week_off_today = False
    try:
        from base.methods import get_holiday_dates, is_company_leave

        week_off_today = bool(is_company_leave(real_today)) or real_today in set(
            get_holiday_dates(real_today, real_today)
        )
    except Exception:
        pass
    week_off_count = not_checked_in if week_off_today else 0
    if week_off_today:
        not_checked_in = 0
    expected_to_check_in = not_checked_in
    # Keep absent_today as an alias for not_checked_in for API compatibility.
    absent_today = not_checked_in
    attendance_rate = (
        round((present_today / expected_today * 100), 1) if expected_today > 0 else 0
    )

    pending_leaves = 0
    try:
        pending_leaves = _today_leave_qs(
            request, real_today, status="requested"
        ).count()
    except Exception:
        pass

    return JsonResponse(
        {
            "total_employees": total_employees,
            "present_today": present_today,
            "absent_today": absent_today,
            "expected_today": expected_today,
            "not_checked_in": not_checked_in,
            "expected_to_check_in": expected_to_check_in,
            "attendance_rate": attendance_rate,
            "on_leave": on_leave,
            "half_day_today": half_day_today,
            "week_off_today": week_off_today,
            "week_off_count": week_off_count,
            "pending_leaves": pending_leaves,
            "new_joiners": new_joiners,
            "date": real_today.isoformat(),
            "is_team_scoped": scoped_ids is not None,
        }
    )


@login_required
def dashboard_leave_breakdown(request):
    """Leave type breakdown (approved vs pending) for the dashboard date range.

    Requires leave.view_leaverequest permission or superuser.
    """
    user = request.user
    if not (user.is_superuser or user.has_perm("leave.view_leaverequest")):
        return JsonResponse({"no_permission": True})

    first_of_month, last_of_month = _parse_period(request)
    today = date.today()
    breakdown = []

    try:
        from django.db.models import Count, Sum

        from leave.models import LeaveType

        # Any request that overlaps the month counts, not only those that
        # start in it -- a leave begun on the 28th still belongs to this month.
        # Same rows the Leave Requests page lists, so a click-through matches.
        rows = (
            _leave_request_list_qs(request)
            .filter(
                status__in=["approved", "cancel_requested", "requested"],
                start_date__lte=last_of_month,
            )
            .filter(
                Q(end_date__gte=first_of_month)
                | Q(end_date__isnull=True, start_date__gte=first_of_month)
            )
            .order_by()  # LeaveRequest's default ordering would split the GROUP BY per row
            .values("leave_type_id", "status")
            .annotate(count=Count("id"), total_days=Sum("requested_days"))
        )
        by_type = {}
        for row in rows:
            entry = by_type.setdefault(
                row["leave_type_id"], {"approved": 0, "requested": 0, "days": 0.0}
            )
            key = "approved" if row["status"] == "cancel_requested" else row["status"]
            entry[key] += row["count"]
            entry["days"] += float(row["total_days"] or 0)

        for lt in LeaveType.objects.all().order_by("name"):
            entry = by_type.get(lt.pk, {"approved": 0, "requested": 0, "days": 0.0})
            breakdown.append(
                {
                    "id": lt.pk,
                    "type": lt.name,
                    "approved": entry["approved"],
                    "requested": entry["requested"],
                    "count": entry["approved"] + entry["requested"],
                    "days": entry["days"],
                }
            )
        breakdown.sort(key=lambda b: (-b["count"], b["type"]))
    except Exception:
        pass

    return JsonResponse(
        {
            "breakdown": breakdown,
            "month": today.strftime("%B %Y"),
            "from_date": first_of_month.isoformat(),
            "to_date": last_of_month.isoformat(),
        }
    )


@login_required
def dashboard_department_headcount(request):
    """Department-wise headcount for every department, largest first."""
    departments = []

    try:
        from django.db.models import Count

        from base.models import Department
        from employee.models import Employee

        data = (
            Employee.objects.filter(is_active=True)
            .values("employee_work_info__department_id__department")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        seen = set()
        for item in data:
            dept = item["employee_work_info__department_id__department"]
            if dept:
                departments.append({"department": dept, "count": item["count"]})
                seen.add(dept)
        for name in (
            Department.objects.exclude(department__in=seen)
            .order_by("department")
            .values_list("department", flat=True)
        ):
            departments.append({"department": name, "count": 0})
    except Exception:
        pass

    return JsonResponse({"departments": departments})


@login_required
def dashboard_gender_split(request):
    """Gender distribution -- overall (default), or ?view=department for a
    per-department breakdown.
    """
    view = (
        request.GET.get("view")
        if request.GET.get("view") in ("overall", "department")
        else "overall"
    )
    gender_map = {
        "male": _("Male"),
        "female": _("Female"),
        "other": _("Other"),
        "": _("Not Specified"),
    }
    genders = []
    departments = []

    try:
        from django.db.models import Count

        from employee.models import Employee

        if view == "department":
            # .order_by() clears the default ordering Django would otherwise
            # inherit here -- combined with the company-scoping manager's own
            # .distinct() (see HorillaCompanyManager.get_queryset), an
            # implicit ordering field gets dragged into the GROUP BY,
            # splitting every matching employee into their own one-row
            # "group" (count always 1) instead of aggregating by
            # department+gender.
            rows = (
                Employee.objects.filter(is_active=True)
                .values(
                    "employee_work_info__department_id",
                    "employee_work_info__department_id__department",
                    "gender",
                )
                .annotate(count=Count("id"))
                .order_by()
            )
            # Stable series order regardless of which genders happen to
            # appear first in the data, so a bar's segment colors/order
            # don't shuffle between departments.
            gender_order = ["male", "female", "other", ""]
            seen_keys = set()
            by_dept = {}
            for row in rows:
                dept_id = row["employee_work_info__department_id"]
                dept_name = row["employee_work_info__department_id__department"] or _(
                    "No department"
                )
                gkey = row["gender"] or ""
                seen_keys.add(gkey)
                entry = by_dept.setdefault(
                    dept_id, {"department": dept_name, "id": dept_id, "by_gender": {}}
                )
                entry["by_gender"][gkey] = row["count"]

            ordered_keys = [k for k in gender_order if k in seen_keys] + sorted(
                seen_keys - set(gender_order)
            )
            genders = [
                {"gender": gender_map.get(k, k or _("Not Specified")), "key": k}
                for k in ordered_keys
            ]
            departments = sorted(
                by_dept.values(),
                key=lambda d: -sum(d["by_gender"].values()),
            )
        else:
            # .order_by("-count") already clears the default ordering here
            # (same fix as above) -- without it this would hit the same
            # one-row-per-employee GROUP BY bug.
            data = (
                Employee.objects.filter(is_active=True)
                .values("gender")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            for item in data:
                genders.append(
                    {
                        "gender": gender_map.get(
                            item["gender"], item["gender"] or _("Not Specified")
                        ),
                        # The name above is translated, so it cannot be used
                        # to look up a colour or build a filter. Ship the raw
                        # field value too.
                        "key": item["gender"] or "",
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse({"view": view, "genders": genders, "departments": departments})


@login_required
def dashboard_announcements(request):
    """Active announcements for the current user."""
    from base.models import Announcement

    today = date.today()
    announcements = []

    try:
        from django.db.models import Q

        qs = Announcement.objects.filter(
            Q(expire_date__gte=today) | Q(expire_date__isnull=True),
        ).order_by("-created_at")[:20]

        for ann in qs:
            announcements.append(
                {
                    "id": ann.id,
                    "title": ann.title,
                    "description": (ann.description or "")[:160],
                    "date": (
                        ann.created_at.strftime("%b %d, %Y") if ann.created_at else ""
                    ),
                    "expire_date": (
                        ann.expire_date.strftime("%b %d") if ann.expire_date else None
                    ),
                }
            )
    except Exception:
        pass

    return JsonResponse({"announcements": announcements})


@login_required
def dashboard_birthdays_anniversaries(request):
    """Birthdays and work anniversaries occurring in the current calendar month."""
    today = date.today()
    birthdays = []
    anniversaries = []

    def _this_month_date(month_day_source):
        """Recreate a month/day in the current year, dodging Feb 29 on non-leap years."""
        try:
            return month_day_source.replace(year=today.year)
        except ValueError:
            return date(today.year, month_day_source.month, 28)

    birthdays_restricted = True

    try:
        from accessibility.methods import check_is_accessible
        from employee.models import Employee, EmployeeWorkInformation

        birthdays_restricted = not check_is_accessible(
            "birthday_view",
            f"{request.session.session_key}accessibility_filter",
            request.user.employee_get,
        )

        # Birthdays — compare month only, so already-celebrated days this
        # month still show alongside ones still to come.
        birthday_employees = Employee.objects.filter(
            is_active=True, dob__month=today.month
        ).exclude(dob__isnull=True)
        if birthdays_restricted:
            birthday_employees = birthday_employees.none()
        for emp in birthday_employees:
            this_year_bday = _this_month_date(emp.dob)
            birthdays.append(
                {
                    "id": emp.id,
                    "name": emp.get_full_name(),
                    "avatar": emp.get_avatar(),
                    "date": this_year_bday.strftime("%b %d"),
                    "days_away": (this_year_bday - today).days,
                }
            )

        # Closest to today first (whether already past or still upcoming this
        # month), so the 10-item cap below keeps the most relevant entries.
        birthdays.sort(key=lambda x: abs(x["days_away"]))

        # Work anniversaries — same current-month rule as birthdays.
        for wi in (
            EmployeeWorkInformation.objects.filter(
                employee_id__is_active=True,
                date_joining__month=today.month,
            )
            .exclude(date_joining__isnull=True)
            .select_related("employee_id")
        ):
            join = wi.date_joining
            this_year_ann = _this_month_date(join)
            years = today.year - join.year
            emp = wi.employee_id
            anniversaries.append(
                {
                    "id": emp.id,
                    "name": emp.get_full_name(),
                    "avatar": emp.get_avatar(),
                    "date": this_year_ann.strftime("%b %d"),
                    "years": years,
                    "days_away": (this_year_ann - today).days,
                }
            )

        anniversaries.sort(key=lambda x: abs(x["days_away"]))
    except Exception:
        pass

    return JsonResponse(
        {
            "birthdays": birthdays[:10],
            "birthdays_restricted": birthdays_restricted,
            "anniversaries": anniversaries[:10],
        }
    )


@login_required
def dashboard_pending_approvals(request):
    """Pending items awaiting the logged-in user's approval.

    For users without any approval permission, shows their own pending requests
    (items they submitted that are waiting for approval).
    """
    user = request.user
    pending = {}

    has_leave_perm = user.has_perm("leave.change_leaverequest")
    has_attendance_perm = user.has_perm("attendance.change_validateattendance")
    has_asset_perm = user.has_perm("asset.change_assetrequest")
    has_shift_perm = user.has_perm("base.change_shiftrequest")
    has_wt_perm = user.has_perm("base.change_worktyperequest")
    has_reimb_perm = user.has_perm("payroll.change_reimbursement")
    is_mgr = _is_manager(user)

    can_approve = any(
        [
            has_leave_perm,
            has_attendance_perm,
            has_asset_perm,
            has_shift_perm,
            has_wt_perm,
            has_reimb_perm,
            is_mgr,
        ]
    )
    is_restricted = not can_approve
    employee = getattr(user, "employee_get", None)

    # Leave requests
    try:
        from leave.models import LeaveRequest

        if can_approve:
            leave_count = (
                _leave_request_list_qs(request).filter(status="requested").count()
            )
        else:
            leave_count = (
                LeaveRequest.objects.filter(
                    employee_id=employee, status="requested"
                ).count()
                if employee
                else 0
            )
        pending["leave_requests"] = leave_count
    except Exception:
        pending["leave_requests"] = 0

    # Attendance requests — same queryset as the Requested Attendances tab badge
    try:
        from attendance.cbv.attendance_request import (
            AttendanceRequestListTab,
            _request_tab_badge_count,
        )
        from attendance.models import Attendance

        if can_approve:
            att_count = _request_tab_badge_count(request, AttendanceRequestListTab)
        else:
            att_count = (
                Attendance.objects.filter(
                    employee_id=employee,
                    is_validate_request=True,
                    is_validate_request_approved=False,
                ).count()
                if employee
                else 0
            )
        pending["attendance_requests"] = att_count
    except Exception:
        pending["attendance_requests"] = 0

    # Asset requests
    try:
        from asset.models import AssetRequest
        from base.methods import filtersubordinates

        if can_approve:
            qs = AssetRequest.objects.filter(
                asset_request_status="Requested",
                requested_employee_id__is_active=True,
            )
            asset_count = (
                (
                    filtersubordinates(
                        request,
                        qs,
                        "asset.view_assetrequest",
                        field="requested_employee_id",
                    )
                    | (
                        qs.filter(requested_employee_id=employee)
                        if employee
                        else qs.none()
                    )
                )
                .distinct()
                .count()
            )
        else:
            asset_count = (
                AssetRequest.objects.filter(
                    requested_employee_id=employee,
                    asset_request_status="Requested",
                ).count()
                if employee
                else 0
            )
        pending["asset_requests"] = asset_count
    except Exception:
        pending["asset_requests"] = 0

    # Shift requests
    try:
        from base.methods import filtersubordinates
        from base.models import ShiftRequest

        if can_approve:
            data = ShiftRequest.objects.filter(employee_id__is_active=True)
            shift_count = (
                (
                    filtersubordinates(
                        request,
                        data.filter(reallocate_to__isnull=True),
                        "base.view_shiftrequest",
                    )
                    | (data.filter(employee_id=employee) if employee else data.none())
                )
                .filter(approved=False, canceled=False)
                .distinct()
                .count()
            )
        else:
            shift_count = (
                ShiftRequest.objects.filter(
                    employee_id=employee,
                    approved=False,
                    canceled=False,
                ).count()
                if employee
                else 0
            )
        pending["shift_requests"] = shift_count
    except Exception:
        pending["shift_requests"] = 0

    # Work type requests
    try:
        from base.methods import filtersubordinates
        from base.models import WorkTypeRequest

        if can_approve:
            # WorkRequestListView does not drop inactive employees.
            data = WorkTypeRequest.objects.all()
            wt_count = (
                (
                    filtersubordinates(request, data, "base.view_worktyperequest")
                    | (data.filter(employee_id=employee) if employee else data.none())
                )
                .filter(approved=False, canceled=False)
                .distinct()
                .count()
            )
        else:
            wt_count = (
                WorkTypeRequest.objects.filter(
                    employee_id=employee,
                    approved=False,
                    canceled=False,
                ).count()
                if employee
                else 0
            )
        pending["work_type_requests"] = wt_count
    except Exception:
        pending["work_type_requests"] = 0

    # Reimbursement requests
    try:
        from base.methods import filter_own_records
        from payroll.models.models import Reimbursement

        if can_approve:
            # Match ReimbursementsListView's own scoping
            # (payroll.view_reimbursement) so this count agrees with the
            # destination list.
            qs = Reimbursement.objects.filter(
                status="requested",
                type="reimbursement",
                employee_id__is_active=True,
            )
            reimb_count = filter_own_records(
                request, qs, "payroll.view_reimbursement"
            ).count()
        else:
            reimb_count = (
                Reimbursement.objects.filter(
                    employee_id=employee, status="requested"
                ).count()
                if employee
                else 0
            )
        pending["reimbursements"] = reimb_count
    except Exception:
        pending["reimbursements"] = 0

    pending["total"] = sum(pending.values())

    return JsonResponse({"pending": pending, "is_restricted": is_restricted})


@login_required
@require_http_methods(["POST"])
def save_dashboard_prefs(request):
    """Persist dashboard customisation to DashboardEmployeeCharts model."""
    try:
        from base.models import DashboardEmployeeCharts

        data = json.loads(request.body)
        prefs = data.get("prefs", [])
        clean_prefs = _normalize_dashboard_chart_prefs(prefs)
        emp = request.user.employee_get
        DashboardEmployeeCharts.objects.update_or_create(
            employee=emp, defaults={"charts": clean_prefs}
        )
    except Exception:
        pass
    return JsonResponse({"status": "ok"})


@login_required
def dashboard_turnover(request):
    """Employee turnover — new hires vs exits over the last 6 months ending at selected period.

    Org-wide metric: requires employee view permission (not manager-only).
    Exit counts prefer shared report exit helper when available.

    ``?group=department`` additionally returns ``departments``: per-department
    hires/exits for the same six months (index-aligned with ``months``).
    """
    user = request.user
    if not (user.has_perm("employee.view_employee") or user.is_superuser):
        return JsonResponse({"no_permission": True})

    _from_date, to_date = _parse_period(request)
    today = to_date
    months = []
    by_dept = request.GET.get("group") == "department"
    # {(id, name): {"hires": [0] * 6, "exits": [0] * 6}}
    dept_rows = {}

    def _dept_row(dept_id, name):
        return dept_rows.setdefault(
            (dept_id, name), {"hires": [0] * 6, "exits": [0] * 6}
        )

    report_url = ""
    total_employees = 0
    total_exits_6m = 0
    try:
        report_url = reverse("standard-report-detail", args=["turnover-attrition"])
    except Exception:
        report_url = ""

    try:
        from employee.models import Employee, EmployeeWorkInformation
        from report.engine import ReportFilters
        from report.metrics._exits import iter_exits

        filters = ReportFilters(from_date=today.replace(day=1), to_date=today)

        for idx, i in enumerate(range(5, -1, -1)):
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            month_start = today.replace(year=year, month=month, day=1)
            if month_start.month == 12:
                month_end = month_start.replace(
                    year=month_start.year + 1, month=1
                ) - timedelta(days=1)
            else:
                month_end = month_start.replace(
                    month=month_start.month + 1
                ) - timedelta(days=1)

            hires_qs = EmployeeWorkInformation.objects.filter(
                date_joining__gte=month_start,
                date_joining__lte=month_end,
            )
            hires = hires_qs.count()
            exit_rows = iter_exits(filters, from_date=month_start, to_date=month_end)
            exits = len(exit_rows)

            if by_dept:
                for r in hires_qs.values(
                    "department_id", "department_id__department"
                ).annotate(n=Count("id")):
                    _dept_row(r["department_id"], r["department_id__department"])[
                        "hires"
                    ][idx] = r["n"]
                for row in exit_rows:
                    wi = getattr(row.get("employee"), "employee_work_info", None)
                    dept = getattr(wi, "department_id", None)
                    _dept_row(
                        getattr(dept, "id", None), getattr(dept, "department", None)
                    )["exits"][idx] += 1

            months.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "from": month_start.isoformat(),
                    "to": month_end.isoformat(),
                    "hires": hires,
                    "exits": exits,
                    "net": hires - exits,
                }
            )

        total_employees = Employee.objects.filter(is_active=True).count()
        total_exits_6m = sum(m["exits"] for m in months)
        turnover_rate = (
            round((total_exits_6m / total_employees * 100), 1)
            if total_employees > 0
            else 0
        )
    except Exception:
        months = [
            {"month": f"M{i+1}", "hires": 0, "exits": 0, "net": 0} for i in range(6)
        ]
        turnover_rate = 0
        total_exits_6m = 0
        total_employees = 0

    payload = {
        "months": months,
        "turnover_rate_6m": turnover_rate,
        "turnover_exits_6m": total_exits_6m,
        "turnover_headcount": total_employees,
        "turnover_formula": str(_("Exits in last 6 months ÷ Active employees × 100")),
        "report_url": report_url,
        "subtitle": str(_("All exits — see Standard Report for detail")),
    }
    if by_dept:
        # Busiest departments first; people without a department are
        # grouped under one label rather than dropped.
        payload["departments"] = sorted(
            (
                {
                    "id": dept_id,
                    "name": name or str(_("No Department")),
                    "hires": row["hires"],
                    "exits": row["exits"],
                }
                for (dept_id, name), row in dept_rows.items()
            ),
            key=lambda d: -(sum(d["hires"]) + sum(d["exits"])),
        )
    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# Phase 5 — thin dashboard/api/* proxies for module chart JSON still used by
# templates/dashboard.html (keeps modern home off raw module URL names).
# ---------------------------------------------------------------------------


def _call_module_json(view_callable, request):
    """Invoke a module chart view; always return JsonResponse-compatible output."""
    try:
        return view_callable(request)
    except Exception as exc:
        return JsonResponse({"error": str(exc), "no_permission": True}, status=500)


def _force_get_params(request, **params):
    """Shallow-copy ``request`` with the given GET params forced in.

    These module chart views (attendance/leave) are shared with their own
    module dashboards, which rely on the view's own default period. Forcing
    params on a copy lets the main dashboard pin them to the current month
    without changing the view's default for those other callers.
    """
    import copy

    forced = copy.copy(request)
    get = request.GET.copy()
    for key, value in params.items():
        get[key] = value
    forced.GET = get
    return forced


_OPEN_TICKET_STATUSES = ["new", "in_progress", "on_hold"]


def _open_tickets_in_range(request):
    """Open (not resolved/canceled) active tickets created in the dashboard range."""
    from helpdesk.models import Ticket

    from_date, to_date = _parse_period(request)
    return (
        from_date,
        to_date,
        Ticket.objects.filter(
            is_active=True,
            status__in=_OPEN_TICKET_STATUSES,
            created_date__gte=from_date,
            created_date__lte=to_date,
        ),
    )


@login_required
def dashboard_ticket_priority(request):
    """Open tickets by priority (high first), split by status, with overdue counts."""
    user = request.user
    if not (user.is_superuser or user.has_perm("helpdesk.view_ticket")):
        return JsonResponse({"no_permission": True})

    from helpdesk.models import PRIORITY, TICKET_STATUS

    today = date.today()
    status_labels = [
        (k, str(v)) for k, v in TICKET_STATUS if k in _OPEN_TICKET_STATUSES
    ]
    priorities = []
    from_date, to_date = _parse_period(request)
    try:
        from_date, to_date, qs = _open_tickets_in_range(request)
        counts = {}
        for row in qs.order_by().values("priority", "status").annotate(n=Count("id")):
            counts[(row["priority"], row["status"])] = row["n"]
        overdue = {
            row["priority"]: row["n"]
            for row in qs.filter(deadline__lt=today)
            .order_by()
            .values("priority")
            .annotate(n=Count("id"))
        }
        for key, label in reversed(list(PRIORITY)):  # high, medium, low
            by_status = {s: counts.get((key, s), 0) for s, _l in status_labels}
            priorities.append(
                {
                    "priority": key,
                    "label": str(label),
                    "by_status": by_status,
                    "total": sum(by_status.values()),
                    "overdue": overdue.get(key, 0),
                }
            )
    except Exception:
        priorities = []

    return JsonResponse(
        {
            "priorities": priorities,
            "statuses": [{"key": k, "label": label} for k, label in status_labels],
            "total": sum(p["total"] for p in priorities),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
    )


@login_required
def dashboard_overdue_tickets(request):
    """Open tickets past their deadline, most overdue first (top 10 plus the full count)."""
    user = request.user
    if not (user.is_superuser or user.has_perm("helpdesk.view_ticket")):
        return JsonResponse({"no_permission": True})

    today = date.today()
    tickets = []
    count = 0
    from_date, to_date = _parse_period(request)
    try:
        from_date, to_date, qs = _open_tickets_in_range(request)
        qs = qs.filter(deadline__lt=today)
        count = qs.count()
        for t in (
            qs.select_related("employee_id", "ticket_type")
            .prefetch_related("assigned_to")
            .order_by("deadline", "id")[:10]
        ):
            emp = t.employee_id
            assignee = next(iter(t.assigned_to.all()), None)
            tickets.append(
                {
                    "id": t.id,
                    "ticket_id": (
                        f"{t.ticket_type.prefix}-{t.pk:03d}"
                        if t.ticket_type
                        else str(t.pk)
                    ),
                    "title": t.title,
                    "owner": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "assignee": assignee.get_full_name() if assignee else "",
                    "priority": t.priority,
                    "priority_label": t.get_priority_display(),
                    "status_label": t.get_status_display(),
                    "deadline": t.deadline.strftime("%b %d, %Y"),
                    "days_overdue": (today - t.deadline).days,
                }
            )
    except Exception:
        tickets = []

    return JsonResponse(
        {
            "tickets": tickets,
            "count": count,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        }
    )


@login_required
def dashboard_attendance_overview(request):
    from attendance.views.dashboard import dashboard_attendance

    # Daily overview: always today, never the dashboard's date filter.
    today = date.today().isoformat()
    scoped_request = _force_get_params(
        request,
        type="date_range",
        date=today,
        end_date=today,
        unit="employees",
    )
    return _call_module_json(dashboard_attendance, scoped_request)


@login_required
def dashboard_leave_trends(request):
    from leave.views import leave_over_period

    from_date, to_date = _parse_period(request)
    scoped_request = _force_get_params(
        request, from_date=from_date.isoformat(), to_date=to_date.isoformat()
    )
    return _call_module_json(leave_over_period, scoped_request)


@login_required
def dashboard_hiring_timeline(request):
    from recruitment.views.dashboard import dashboard_hiring

    _, to_date = _parse_period(request)
    scoped_request = _force_get_params(request, id=str(to_date.year))
    return _call_module_json(dashboard_hiring, scoped_request)


@login_required
def dashboard_recruitment_by_stage(request):
    """Stacked-by-recruitment pipeline chart (legacy recruitment-pipeline JSON)."""
    from recruitment.views.dashboard import dashboard_pipeline

    return _call_module_json(dashboard_pipeline, request)
