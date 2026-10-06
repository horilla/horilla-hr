"""
Employee dashboard views — KPI summary + ApexCharts.

Request KPIs mirror the querysets of the Requests page tabs (shift, shift
allocation, work type and document) so each count equals what its click-through
list shows. Company scoping comes from the models' HorillaCompanyManager, which
already resolves the session's selected company (including "All Company").
"""

import calendar
from datetime import date

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
    return queryset | allocated


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

    "Pending" is the same condition as the list filter status=requested
    (not approved and not canceled). Only requests created inside the selected
    period are counted.
    """
    from_date, to_date = _period_bounds(request)
    pending = {
        "approved": False,
        "canceled": False,
        "created_at__date__gte": from_date,
        "created_at__date__lte": to_date,
    }
    show_documents = _can_view_documents(request)

    return JsonResponse(
        {
            "document_requests": (
                Document.objects.filter(
                    status="requested",
                    created_at__date__gte=from_date,
                    created_at__date__lte=to_date,
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


@login_required
@manager_can_enter(EMPLOYEE_PERM)
def employee_new_joiners(request):
    """Active employees who joined during the selected period, newest first."""
    from_date, to_date = _period_bounds(request)
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

    return JsonResponse({"employees": employees, "total": joined.count()})
