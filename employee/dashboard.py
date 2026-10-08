"""
Employee dashboard views — KPI summary + ApexCharts.

Request KPIs mirror the querysets of the Requests page tabs (shift, shift
allocation, work type and document) so each count equals what its click-through
list shows. Company scoping comes from the models' HorillaCompanyManager, which
already resolves the session's selected company (including "All Company").
"""

import calendar
from datetime import date, timedelta

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from base.methods import filtersubordinates
from base.models import ShiftRequest, WorkTypeRequest
from employee.models import Employee
from horilla.decorators import login_required, manager_can_enter
from horilla_documents.models import Document

EMPLOYEE_PERM = "employee.view_employee"
NEW_EMPLOYEES_LIMIT = 10
NEW_EMPLOYEES_DAYS = 30
EXPIRED_DOCUMENTS_LIMIT = 10
EXPIRING_DOCUMENTS_DAYS = 60


def _current_month_bounds():
    """Return the current calendar month's first and last day."""
    today = timezone.now().date()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last_day)


def _period_bounds(request):
    """Selected dashboard period (from_date/to_date GET params, ISO dates).

    Falls back to the current month when a bound is missing or invalid, and
    swaps the bounds if they were given in reverse order.
    """
    try:
        from_date = date.fromisoformat(request.GET.get("from_date", ""))
        to_date = date.fromisoformat(request.GET.get("to_date", ""))
    except ValueError:
        return _current_month_bounds()
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def _active_employees():
    """Active employees in the selected company, as the employee list shows."""
    return Employee.objects.filter(is_active=True)


def _can_view_documents(request):
    """Same visibility rule as the Documents menu in employee/sidebar.py."""
    from base.templatetags.basefilters import is_reportingmanager

    return request.user.has_perm(
        "horilla_documents.view_documentrequest"
    ) or is_reportingmanager(request.user)


def _shift_requests(request):
    """Queryset behind the Requests > Shift Requests tab (ShiftRequestList)."""
    all_requests = ShiftRequest.objects.all()
    employee = request.user.employee_get
    queryset = filtersubordinates(
        request,
        all_requests.filter(reallocate_to__isnull=True),
        "base.view_shiftrequest",
    )
    queryset = queryset | all_requests.filter(employee_id=employee)
    return queryset.filter(employee_id__is_active=True)


def _shift_allocations(request):
    """Queryset behind the Requests > Shift Allocations tab (AllocatedShift)."""
    allocated = ShiftRequest.objects.filter(reallocate_to__isnull=False)
    employee = request.user.employee_get
    queryset = filtersubordinates(request, allocated, "base.view_shiftrequest")
    if not request.user.has_perm("base.view_shiftrequest"):
        allocated = allocated.filter(
            Q(reallocate_to=employee) | Q(employee_id=employee)
        )
    return (queryset | allocated).filter(employee_id__is_active=True)


def _work_type_requests(request):
    """Queryset behind the Requests > Work Type Requests tab (WorkRequestListView)."""
    all_requests = WorkTypeRequest.objects.all()
    employee = request.user.employee_get
    queryset = filtersubordinates(request, all_requests, "base.view_worktyperequest")
    queryset = queryset | all_requests.filter(employee_id=employee)
    return queryset.filter(employee_id__is_active=True)


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_dashboard_view(request):
    """Render the employee dashboard page."""
    return render(request, "employee/dashboard.html")


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_kpi_data(request):
    """Pending request counts shown in the KPI cards.

    "Pending" is the same condition as the list filter status=requested (not
    approved and not canceled) -- a live snapshot, not scoped to any date
    window, so each tile's count always matches what its own click-through
    link shows (those links carry no date filter either).
    """
    pending = {"approved": False, "canceled": False}
    show_documents = _can_view_documents(request)

    return JsonResponse(
        {
            "document_requests": (
                Document.objects.filter(
                    status="requested",
                    employee_id__is_active=True,
                    document_request_id__isnull=False,
                ).count()
                if show_documents
                else None
            ),
            "work_type_requests": _work_type_requests(request)
            .filter(**pending)
            .count(),
            "shift_requests": _shift_requests(request).filter(**pending).count(),
            "shift_allocation_requests": _shift_allocations(request)
            .filter(**pending)
            .count(),
        }
    )


# Work-information relation -> name field shown as the chart label
DISTRIBUTION_LABELS = {
    "work_type": "work_type",
    "shift": "employee_shift",
    "department": "department",
}


def _distribution(field):
    """Active employee headcount grouped by a work-information relation.

    Employees with no value land in an "unassigned" bucket (id None) so the
    chart total always equals the active employee count.
    """
    key_id = f"employee_work_info__{field}_id"
    key_label = f"{key_id}__{DISTRIBUTION_LABELS[field]}"
    rows = (
        _active_employees()
        .values(key_id, key_label)
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    return [
        {
            "id": row[key_id],
            "label": row[key_label] or _("Unassigned"),
            "count": row["count"],
        }
        for row in rows
    ]


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_by_work_type(request):
    """Active employees by work type."""
    return JsonResponse({"items": _distribution("work_type")})


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_by_shift(request):
    """Active employees by assigned shift."""
    return JsonResponse({"items": _distribution("shift")})


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_by_department(request):
    """Active employees by department."""
    return JsonResponse({"items": _distribution("department")})


REPORTING_MANAGER_LIMIT = 10


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_department_positions(request):
    """Active headcount per department, split by job position.

    Every job position with active employees gets its own series, most populated
    first. Employees with no position at all are a "Not Assigned" series.
    """
    key_dept = "employee_work_info__department_id"
    key_pos = "employee_work_info__job_position_id"
    rows = list(
        _active_employees()
        .filter(**{f"{key_pos}__isnull": False})
        .values(
            key_dept,
            f"{key_dept}__department",
            key_pos,
            f"{key_pos}__job_position",
        )
        .annotate(count=Count("id"))
    )
    # Employees with no position still count toward their department total
    no_position = {
        row[key_dept]: row["count"]
        for row in _active_employees()
        .filter(**{f"{key_pos}__isnull": True})
        .values(key_dept)
        .annotate(count=Count("id"))
    }

    position_totals = {}
    for row in rows:
        entry = position_totals.setdefault(
            row[key_pos],
            {"key": row[key_pos], "label": row[f"{key_pos}__job_position"], "count": 0},
        )
        entry["count"] += row["count"]
    top = sorted(position_totals.values(), key=lambda p: -p["count"])
    positions = [{"key": p["key"], "label": p["label"]} for p in top]

    departments = {}

    def department(dept_id, label):
        return departments.setdefault(
            dept_id,
            {
                "id": dept_id,
                "label": label or _("Unassigned"),
                "total": 0,
                "by_position": {},
            },
        )

    for row in rows:
        dept = department(row[key_dept], row[f"{key_dept}__department"])
        pos_key = row[key_pos]
        dept["by_position"][pos_key] = (
            dept["by_position"].get(pos_key, 0) + row["count"]
        )
        dept["total"] += row["count"]
    if no_position:
        names = dict(
            _active_employees()
            .filter(**{f"{key_dept}__in": [k for k in no_position if k]})
            .values_list(key_dept, f"{key_dept}__department")
            .distinct()
        )
        for dept_id, count in no_position.items():
            dept = department(dept_id, names.get(dept_id))
            dept["by_position"]["unassigned"] = count
            dept["total"] += count
    if any("unassigned" in d["by_position"] for d in departments.values()):
        positions.append({"key": "unassigned", "label": _("Not Assigned")})

    return JsonResponse(
        {
            "positions": positions,
            "departments": sorted(departments.values(), key=lambda d: -d["total"]),
        }
    )


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_by_reporting_manager(request):
    """Active employees per reporting manager (direct reports), top 10."""
    key = "employee_work_info__reporting_manager_id"
    rows = list(
        _active_employees()
        .filter(**{f"{key}__isnull": False})
        .values(key)
        .annotate(count=Count("id"))
        .order_by("-count")[:REPORTING_MANAGER_LIMIT]
    )
    managers = {m.id: m for m in Employee.objects.filter(id__in=[r[key] for r in rows])}
    return JsonResponse(
        {
            "items": [
                {
                    "id": row[key],
                    "label": (
                        managers[row[key]].get_full_name()
                        if row[key] in managers
                        else _("Unknown")
                    ),
                    "count": row["count"],
                }
                for row in rows
            ]
        }
    )


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_new_joiners(request):
    """Active employees who joined in the last 30 days, newest first.

    Independent of the dashboard period filter.
    """
    to_date = timezone.localdate()
    from_date = to_date - timedelta(days=NEW_EMPLOYEES_DAYS)
    joined = _active_employees().filter(
        employee_work_info__date_joining__gte=from_date,
        employee_work_info__date_joining__lte=to_date,
    )
    rows = joined.select_related(
        "employee_work_info__department_id", "employee_work_info__job_position_id"
    ).order_by("-employee_work_info__date_joining", "-id")[:NEW_EMPLOYEES_LIMIT]

    employees = []
    for emp in rows:
        work_info = emp.employee_work_info
        employees.append(
            {
                "id": emp.id,
                "name": emp.get_full_name(),
                "avatar": emp.get_avatar(),
                "url": reverse("employee-view-individual", kwargs={"obj_id": emp.id}),
                "department": (
                    work_info.department_id.department
                    if work_info.department_id
                    else None
                ),
                "position": (
                    work_info.job_position_id.job_position
                    if work_info.job_position_id
                    else None
                ),
                "date_joining": work_info.date_joining.strftime("%d %b %Y"),
            }
        )

    return JsonResponse(
        {
            "employees": employees,
            "total": joined.count(),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "from_label": from_date.strftime("%d %b %Y"),
            "to_label": to_date.strftime("%d %b %Y"),
        }
    )


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_expired_documents(request):
    """Approved documents expiring within the next 60 days, soonest first."""
    if not _can_view_documents(request):
        return JsonResponse({"documents": [], "total": 0})
    today = timezone.now().date()
    expired = Document.objects.filter(
        status="approved",
        employee_id__is_active=True,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=EXPIRING_DOCUMENTS_DAYS),
    )
    rows = expired.select_related("employee_id").order_by("expiry_date", "id")[
        :EXPIRED_DOCUMENTS_LIMIT
    ]
    documents = [
        {
            "id": doc.id,
            "title": doc.title,
            "employee": doc.employee_id.get_full_name(),
            "avatar": doc.employee_id.get_avatar(),
            "expiry_date": doc.expiry_date.strftime("%d %b %Y"),
            "days_left": (doc.expiry_date - today).days,
        }
        for doc in rows
    ]
    return JsonResponse(
        {
            "documents": documents,
            "total": expired.count(),
            "from_date": today.isoformat(),
            "to_date": (today + timedelta(days=EXPIRING_DOCUMENTS_DAYS)).isoformat(),
        }
    )
