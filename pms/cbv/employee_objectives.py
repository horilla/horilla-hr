"""
Standalone list pages for employee objectives and employee key results
"""

from typing import Any

from django.db.models import Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from pms.filters import EmployeeKeyResultListFilter, EmployeeObjectiveFilter
from pms.models import EmployeeKeyResult, EmployeeObjective


def visible_employee_objectives(request):
    """
    Employee objectives the requesting user is allowed to see
    """
    queryset = EmployeeObjective.objects.all()
    if request.user.has_perm("pms.view_employeeobjective"):
        return queryset
    employee = request.user.employee_get
    return queryset.filter(
        Q(employee_id=employee) | Q(objective_id__managers=employee)
    ).distinct()


@method_decorator(login_required, name="dispatch")
class EmployeeObjectivesPage(TemplateView):
    """
    Page shell for the employee objective list
    """

    template_name = "cbv/employee_objectives/employee_objectives.html"


@method_decorator(login_required, name="dispatch")
class EmployeeObjectivesNav(HorillaNavView):
    """
    Search and status filter bar of the employee objective list
    """

    nav_title = _("Employee Objectives")
    filter_instance = EmployeeObjectiveFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/employee_objectives/employee_objective_filter.html"
    search_swap_target = "#listContainer"
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employee-objectives-list")


@method_decorator(login_required, name="dispatch")
class EmployeeObjectivesList(HorillaListView):
    """
    List of employee objectives
    """

    model = EmployeeObjective
    filter_class = EmployeeObjectiveFilter
    view_id = "employeeObjectivesContainer"
    filter_selected = False
    bulk_update = False
    quick_export = False

    columns = [
        (_("Employee"), "employee_id"),
        (_("Objective"), "objective_id__title"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Progress"), "progress_percentage"),
        (_("Status"), "get_status_display"),
    ]

    row_attrs = """
                hx-get='{employee_objective_detail_view}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employee-objectives-list")

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        qs = super().get_queryset(queryset, filtered, *args, **kwargs)
        qs = qs.filter(pk__in=visible_employee_objectives(self.request).values("pk"))
        if self.request.GET.get("archive") is None:
            qs = qs.filter(archive=False)
        return qs


@method_decorator(login_required, name="dispatch")
class EmployeeKeyResultsPage(TemplateView):
    """
    Page shell for the employee key result list
    """

    template_name = "cbv/employee_objectives/employee_key_results.html"


@method_decorator(login_required, name="dispatch")
class EmployeeKeyResultsNav(HorillaNavView):
    """
    Search and status filter bar of the employee key result list
    """

    nav_title = _("Employee Key Results")
    filter_instance = EmployeeKeyResultListFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/employee_objectives/employee_key_result_filter.html"
    search_swap_target = "#listContainer"
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employee-key-results-list")


@method_decorator(login_required, name="dispatch")
class EmployeeKeyResultsList(HorillaListView):
    """
    List of employee key results
    """

    model = EmployeeKeyResult
    filter_class = EmployeeKeyResultListFilter
    view_id = "employeeKeyResultsContainer"
    filter_selected = False
    bulk_update = False
    quick_export = False

    columns = [
        (_("Employee"), "employee_objective_id__employee_id"),
        (_("Objective"), "employee_objective_id__objective_id__title"),
        (_("Key Result"), "key_result"),
        (_("Start Value"), "start_value"),
        (_("Current Value"), "current_value"),
        (_("Target Value"), "target_value"),
        (_("Progress"), "get_progress_col"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Status"), "get_status_display"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employee-key-results-list")

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        qs = super().get_queryset(queryset, filtered, *args, **kwargs)
        visible = visible_employee_objectives(self.request).filter(archive=False)
        return qs.filter(employee_objective_id__in=visible.values("pk"))
