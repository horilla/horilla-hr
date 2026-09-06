"""
Leave allocation request page
"""

import contextlib
from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from base.methods import choosesubordinates, filtersubordinates, is_reportingmanager
from employee.cbv.employee_profile import EmployeeProfileView
from employee.models import Employee
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from leave.cbv.leave_tab import IndividualLeaveTab
from leave.filters import LeaveAllocationRequestFilter
from leave.forms import LeaveAllocationBulkForm, LeaveAllocationRequestForm
from leave.models import LeaveAllocationRequest
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestView(TemplateView):
    """
    for leave allocation  request page view
    """

    template_name = "cbv/leave_allocation_request/leave_allocation_request.html"


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestList(HorillaListView):
    """
    List view of the page
    """

    model = LeaveAllocationRequest
    filter_class = LeaveAllocationRequestFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("leave-allocation-request-filter")
        self.view_id = "view-container"

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Leave Type"), "leave_type_id"),
        (_("Requested Days"), "requested_days"),
        (_("Created By"), "created_by__employee_get"),
        (_("Status"), "get_status"),
        (_("Description"), "description"),
        (_("Comment"), "comment"),
    ]

    header_attrs = {
        "action": """ style="width:180px !important;" """,
        "description": """ style="width:180px !important;" """,
    }

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name"),
        (_("Leave Type"), "leave_type_id__name"),
        (_("Requested Days"), "requested_days"),
        (_("Created By"), "created_by__get_full_name"),
        (_("Status"), "get_status"),
    ]

    option_method = "action_col"

    row_status_indications = [
        (
            "rejected--dot",
            _("Rejected"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('rejected');
            $('[name=approved]').val('unknown').change();
            $('[name=requested]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "requested--dot",
            _("Requested"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('requested');
            $('[name=rejected]').val('unknown').change();
            $('[name=approved]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "approved--dot",
            _("Approved"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('approved');
            $('[name=rejected]').val('unknown').change();
            $('[name=requested]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
    ]

    row_status_class = "status-{status}"
    # Mirrors _LeaveAllocationTabNavBase.nested_group_by_fields -- needed
    # here too since this (List) and Nav are separate classes; see the
    # same split in employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("status", _("Status")),
        ("requested_days", _("Requested Days")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employment Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


def _leave_allocation_tab_badge_count(request, view_cls):
    """Same queryset rules as the tab's HorillaListView (filters, subordinates)."""
    view = view_cls()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.queryset = None
    return view.get_queryset().count()


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestTab(HorillaTabView):
    """
    Tab View
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "leave-allocation"
        self.tabs = [
            {
                "title": _("My Leave allocation request"),
                "url": f"{reverse('my-leave-allocation-tab-shell')}",
            },
        ]
        if self.request.user.has_perm(
            "leave.view_leaveallocationrequest"
        ) or is_reportingmanager(self.request):

            self.tabs.append(
                {
                    "title": _("Leave allocation requests"),
                    "url": f"{reverse('leave-allocation-requests-tab-shell')}",
                },
            )

    def get_context_data(self, **kwargs):
        """
        Populate tab badges with list counts so they show before each tab loads.
        """
        context = super().get_context_data(**kwargs)
        view_classes = [MyLeaveAllocationRequest, LeaveAllocationRequests]
        for idx, tab in enumerate(self.tabs):
            if idx < len(view_classes):
                tab["badge"] = _leave_allocation_tab_badge_count(
                    self.request, view_classes[idx]
                )
        return context


@method_decorator(login_required, name="dispatch")
class MyLeaveAllocationRequest(LeaveAllocationRequestList):
    """
    My leave allocations
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-leave-allocation-request-tab")
        self.view_id = "my-leave-container"

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        queryset = queryset.filter(employee_id=employee).order_by("-id")
        return queryset

    row_attrs = """
                {diff_cell}
                hx-get='{leave_request_allocation_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    option_method = None
    action_method = "action_col"


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequests(LeaveAllocationRequestList):
    """
    Leave allocation request
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("leave-allocation-requests-tab-view")
        self.view_id = "all-leave-container"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = filtersubordinates(
            self.request, queryset, "leave.view_leaveallocationrequest"
        )
        return queryset

    option_method = None
    action_method = "allocation_tab_actions"

    row_attrs = """
                {diff_cell}
                hx-get='{detail_view_leave_request_allocation}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


class _LeaveAllocationTabNavBase(HorillaNavView):
    """
    Shared Search/Filter/Create/Actions wiring for each Leave Allocation
    Request tab's own, independent Nav - only search_url/search_swap_target
    differ per tab.
    """

    nav_title = _("Leave Allocation Requests")
    filter_instance = LeaveAllocationRequestFilter()
    filter_body_template = "cbv/leave_allocation_request/filter.html"
    filter_form_context_name = "form"
    # Modern slide-over filter panel (horilla_nav.html's .oh-filter-modern
    # styles) -- same treatment as every other panel this session.
    # LeaveAllocationRequestFilter.ajax_fields carries the AJAX-loaded
    # Employee combobox this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("status", _("Status")),
        ("requested_days", _("Requested Days")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employment Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors LeaveAllocationRequestList.nested_group_by_fields below --
    # List and Nav are separate classes/templates (see
    # employee/cbv/employees.py's EmployeesList/EmployeeNav for the same
    # split), so the inline "add/change field" dropdowns in the "Grouped
    # by" breadcrumb (nested_group_by_table.html, rendered by the List
    # view) need this here too, not just the currently-active fields it
    # already had access to via nested_fields_active.
    nested_group_by_fields = group_by_fields

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.create_attrs = f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#objectCreateModal"
                            hx-target="#objectCreateModalTarget"
                            hx-get="{reverse_lazy('leave-allocation-request-create')}"
                            """

        if self.request.user.has_perm("leave.add_leaveallocationrequest"):
            self.actions = [
                {
                    "action": _("Bulk Allocate Leave"),
                    "attrs": f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            hx-get="{reverse_lazy('leave-allocation-request-bulk-create')}"
                            style="cursor: pointer;"
                        """,
                },
            ]


@method_decorator(login_required, name="dispatch")
class MyLeaveAllocationNav(_LeaveAllocationTabNavBase):
    """
    Independent Nav for the My Leave Allocation Request tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-leave-allocation-request-tab")
        self.search_swap_target = "#myLeaveAllocationListContainer"


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestsNav(_LeaveAllocationTabNavBase):
    """
    Independent Nav for the Leave Allocation Requests tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("leave-allocation-requests-tab-view")
        self.search_swap_target = "#allLeaveAllocationListContainer"


class MyLeaveAllocationTabShell(AttendanceTabContentShell):
    nav_url_name = "my-leave-allocation-nav"
    container_id = "myLeaveAllocationListContainer"
    tabs_root_id = "leave-allocation"


class LeaveAllocationRequestsTabShell(AttendanceTabContentShell):
    nav_url_name = "leave-allocation-requests-nav"
    container_id = "allLeaveAllocationListContainer"
    tabs_root_id = "leave-allocation"


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Requested Days"), "requested_days"),
            (_("Leave Type"), "leave_type_id"),
            (_("Created Date"), "requested_date"),
            (_("Created By"), "created_by__employee_get"),
            (_("History"), "history_col", True),
            (_("Attachment"), "attachment_col", True),
            (_("Description"), "description"),
            (_("Rejection Reason"), "reject_col", True),
        ]

    cols = {
        "description": 12,
        "reject_col": 12,
    }

    action_method = "detail_action"

    model = LeaveAllocationRequest
    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "leave_request_allocation_detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }


@method_decorator(login_required, name="dispatch")
class LeaveAllocationsRequestsTabDetailView(LeaveAllocationRequestDetailView):
    """
    Detail view
    """

    action_method = "leave_detail_action"


@method_decorator(login_required, name="dispatch")
class LeaveAllocationRequestFormView(HorillaFormView):
    """
    Form View
    """

    model = LeaveAllocationRequest
    form_class = LeaveAllocationRequestForm
    new_display_title = _("Create Leave Allocation Request")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_get
        self.form_class(initial={"employee_id": employee})
        if self.form.instance.pk:
            self.form_class.verbose_name = "Update Request"
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request, self.form, "leave.add_leaveallocationrequest"
        )
        self.form.fields["employee_id"].queryset = (
            self.form.fields["employee_id"].queryset
        ).distinct() | (
            Employee.objects.filter(employee_user_id=self.request.user)
        ).distinct()
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: LeaveAllocationRequestForm) -> HttpResponse:
        if form.is_valid():
            self.form_class(self.request.FILES)
            instance = form.save()
            instance.skip_history = False
            if form.instance.pk:
                message = _("Leave allocation request updated")
                with contextlib.suppress(Exception):
                    notify.send(
                        self.request.user.employee_get,
                        recipient=instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        verb=f"Leave allocation request updated for {instance.employee_id}.",
                        verb_ar=f"تم تحديث طلب تخصيص الإجازة لـ {instance.employee_id}.",
                        verb_de=f"Urlaubszuteilungsanforderung aktualisiert für {instance.employee_id}.",
                        verb_es=f"Solicitud de asignación de licencia actualizada para {instance.employee_id}.",
                        verb_fr=f"Demande d'allocation de congé mise à jour pour {instance.employee_id}.",
                        icon="people-cicle",
                        redirect=reverse("leave-allocation-request-view")
                        + f"?id={instance.id}",
                    )
            else:
                message = _("New leave allocation request created")
                with contextlib.suppress(Exception):
                    notify.send(
                        self.request.user.employee_get,
                        recipient=instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        verb=f"New leave allocation request created for {instance.employee_id}.",
                        verb_ar=f"تم إنشاء طلب تخصيص إجازة جديد لـ {instance.employee_id}.",
                        verb_de=f"Neue Anfrage zur Urlaubszuweisung erstellt für {instance.employee_id}.",
                        verb_es=f"Nueva solicitud de asignación de permisos creada para {instance.employee_id}.",
                        verb_fr=f"Nouvelle demande d'allocation de congé créée pour {instance.employee_id}.",
                        icon="people-cicle",
                        redirect=reverse("leave-allocation-request-view")
                        + f"?id={instance.id}",
                    )
            instance.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class LeaveAllocationBulkFormView(HorillaFormView):
    """
    Form view to bulk allocate (and optionally approve) leave for multiple
    employees at once.
    """

    model = LeaveAllocationRequest
    form_class = LeaveAllocationBulkForm
    new_display_title = _("Bulk Allocate Leave")

    def form_valid(self, form: LeaveAllocationBulkForm) -> HttpResponse:
        if form.is_valid():
            created_requests = form.save()
            messages.success(
                self.request,
                _("Leave allocated for %(count)s employee(s)")
                % {"count": len(created_requests)},
            )
            return self.HttpResponse()
        return super().form_valid(form)


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Leave"),
            # "view": views.employee_view_individual_leave_tab,
            "view": IndividualLeaveTab.as_view(),
            "accessibility": "leave.cbv.accessibility.leave_accessibility",
        },
    ]
)
