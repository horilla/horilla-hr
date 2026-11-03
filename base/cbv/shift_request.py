"""
This page is handling the cbv methods of shift request page.
"""

import contextlib
from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from base.filters import ShiftRequestFilter
from base.forms import (
    EmployeeShiftForm,
    ShiftAllocationForm,
    ShiftRequestColumnForm,
    ShiftRequestForm,
)
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from base.models import EmployeeShift, ShiftRequest
from base.views import include_employee_instance, shift_requests_url
from employee.models import Employee
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import (
    EmployeeScopeMixin,
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class ShiftRequestView(TemplateView):
    """
    Shift request page
    """

    template_name = "cbv/shift_request/shift_request.html"


@method_decorator(login_required, name="dispatch")
class ShiftList(HorillaListView):
    """
    List view
    """

    model = ShiftRequest
    filter_class = ShiftRequestFilter
    quick_export = False

    row_status_class = (
        "approved-{approved} canceled-{canceled} requested-{approved}-{canceled}"
    )

    row_status_indications = [
        (
            "canceled--dot",
            _("Canceled"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('canceled').change();
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "approved--dot",
            _("Approved"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('approved').change();
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "requested--dot",
            _("Requested"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('requested').change();
                $('#applyFilter').click();
            "
            """,
        ),
    ]


@method_decorator(login_required, name="dispatch")
class ShiftRequestList(ShiftList):
    """
    List view for shift requests
    """

    selected_instances_key_id = "shiftselectedInstances"
    template_name = "cbv/shift_request/extended_shift.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-shift-request")
        self.view_id = "shift-container"
        # self.filter_keys_to_remove = ["deleted"]

    def get_queryset(self):
        queryset = super().get_queryset()
        data = queryset

        employee = self.request.user.employee_get
        queryset = filtersubordinates(
            self.request,
            queryset.filter(reallocate_to__isnull=True),
            "base.view_shiftrequest",
        )
        queryset = queryset | data.filter(
            employee_id=employee, reallocate_to__isnull=True
        )
        queryset = queryset.filter(employee_id__is_active=True)

        return queryset

    columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Requested Shift"), "shift_id"),
        (_("Previous/Current Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Status"), "request_status"),
        (_("Description"), "description"),
        (_("Comment"), "comment"),
    ]

    default_columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Requested Shift"), "shift_id"),
        (_("Previous/Current Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Status"), "request_status"),
    ]

    header_attrs = {
        "action": """ style="width:190px !important;" """,
        "description": """ style="width:300px !important;" """,
    }

    action_method = "shift_actions"

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name"),
        (_("Requested Shift"), "shift_id__employee_shift"),
        (_("Previous/Current Shift"), "previous_shift_id__employee_shift"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
    ]

    row_attrs = """
                hx-get='{shift_details}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
class AllocatedShift(ShiftList):
    """
    Allocated tab class
    """

    selected_instances_key_id = "allocatedselectedInstances"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("allocated-shift-view")

    columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Allocated Employee"), "reallocate_to__get_full_name"),
        (_("User Availability"), "user_availability"),
        (_("Requested Shift"), "shift_id"),
        (_("Previous/Current Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Description"), "description"),
        (_("Comment"), "comment"),
    ]

    default_columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Allocated Employee"), "reallocate_to__get_full_name"),
        (_("Requested Shift"), "shift_id"),
        (_("Previous/Current Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
    ]

    action_method = "allocated_confirm_action_col"

    def get_queryset(self):
        queryset = super().get_queryset()
        b = queryset
        employee = self.request.user.employee_get
        queryset = filtersubordinates(
            self.request,
            queryset.filter(reallocate_to__isnull=False),
            "base.view_shiftrequest",
        )
        allocated_requests = b.filter(reallocate_to__isnull=False)
        if not self.request.user.has_perm("base.view_shiftrequest"):
            allocated_requests = allocated_requests.filter(
                Q(reallocate_to=employee) | Q(employee_id=employee)
            )
        queryset = queryset | allocated_requests

        return queryset

    row_attrs = """
                hx-get='{allocate_shift_details}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name"),
        (_("Allocated Employee"), "reallocate_to__get_full_name"),
        (_("Requested Shift"), "shift_id__employee_shift"),
        (_("Previous/Current Shift"), "previous_shift_id__employee_shift"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
    ]


@method_decorator(login_required, name="dispatch")
class ShitRequestNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("shift-request-tab")
        self.create_attrs = f"""
             hx-get="{reverse_lazy('shift-request')}"
             data-toggle="oh-modal-toggle"
             data-target="#genericModal"
             hx-target="#genericModalBody"

         """
        self.actions = []
        if self.request.user.has_perm(
            "base.change_shiftrequest"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Approve Requests"),
                    "attrs": """
                    onclick="
                    shiftRequestApprove();
                    "
                    style="cursor: pointer;"
                    """,
                }
            )
            self.actions.append(
                {
                    "action": _("Reject Requests"),
                    "attrs": """
                    onclick="
                    shiftRequestReject();
                    "
                    style="cursor: pointer;"
                    """,
                }
            )
        if self.request.user.has_perm(
            "base.delete_shiftrequest"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                    onclick="
                    shiftRequestDelete();
                    "
                    data-action ="delete"
                    style="cursor: pointer; color:red !important"
                    """,
                }
            )

        if has_export_access(self.request, ShiftRequest):
            self.actions.insert(
                0,
                {
                    "action": _("Export"),
                    "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse('shift-export')}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                    """,
                },
            )

    nav_title = _("Shift Requests")
    template_name = "generic/inline_nav.html"
    filter_body_template = "cbv/shift_request/filter.html"
    filter_instance = ShiftRequestFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("shift_id", _("Requested Shift")),
        ("previous_shift_id", _("Current Shift")),
        ("requested_date", _("Requested Date")),
    ]


@method_decorator(login_required, name="dispatch")
class ShiftRequestTab(HorillaTabView):
    """
    Tab View
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "shift-tab"
        self.tabs = [
            {
                "title": _("Shift Requests"),
                "url": f"{reverse('list-shift-request')}",
            },
            {
                "title": _("Allocated Shift Requests"),
                "url": f"{reverse('allocated-shift-view')}",
            },
        ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class ExportView(TemplateView):
    """
    For candidate export
    """

    template_name = "cbv/shift_request/export_shift.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        shift_requests = ShiftRequest.objects.all()
        export_fields = ShiftRequestColumnForm
        export_filter = ShiftRequestFilter(queryset=shift_requests)
        context["export_fields"] = export_fields
        context["export_filter"] = export_filter
        return context


@method_decorator(login_required, name="dispatch")
class ShiftRequestDetailview(HorillaDetailedView):
    """
    Detail View
    """

    model = ShiftRequest

    title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "details_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Requested Shift"), "shift_id"),
        (_("Previous Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Permenent shift"), "is_permanent"),
        (_("Description"), "description"),
    ]

    cols = {
        "description": 12,
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # shift_detail_confirm_action.html carries the same per-role
        # conditions as the row's shift_actions() actions (Edit/Duplicate/
        # Remove/Approve/Reject), so there's no need to swap templates by
        # viewer role here - it was previously split into detail_confirmations
        # (manager-only Approve/Reject) and detail_actions (owner-only Edit/
        # Delete), which meant no viewer ever saw the full row button set.
        self.action_method = "shift_detail_confirm_action"


@method_decorator(login_required, name="dispatch")
class AllocatedShiftDetailView(ShiftRequestDetailview):
    """
    Allocated detail View
    """

    body = [
        (_("Allocated Employee"), "reallocate_to"),
        (_("User Availability"), "user_availability"),
        (_("Requested Shift"), "shift_id"),
        (_("Previous Shift"), "previous_shift_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Description"), "description"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.action_method = "allocated_detail_confirm_action"


class ShiftTypeFormView(HorillaFormView):
    """
    form view
    """

    model = EmployeeShift
    form_class = EmployeeShiftForm
    new_display_title = "Create Shift"
    is_dynamic_create_view = True

    def form_valid(self, form: EmployeeShiftForm) -> HttpResponse:
        if form.is_valid():
            form.save()
            message = _("Shift Created")
            messages.success(self.request, message)
            return HorillaRedirect(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.add_employeeshift"), name="dispatch")
class ShiftTypeCreateFormView(ShiftTypeFormView):

    is_dynamic_create_view = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # form = self.form_class()
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
            self.form_class.verbose_name = _("Update Shift")
        context["form"] = self.form
        return context

    def form_valid(self, form: EmployeeShiftForm) -> HttpResponse:
        if form.is_valid():
            if self.form.instance.pk:
                message = _("Shift Updated")
            else:
                message = _("Shift Created")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()


@method_decorator(login_required, name="dispatch")
class ShiftRequestFormView(EmployeeScopeMixin, HorillaFormView):
    """
    Form View
    """

    scope_perm = "base.add_shiftrequest"
    scope_include_self = True

    model = ShiftRequest
    form_class = ShiftRequestForm
    new_display_title = _("Create Shift Request")
    template_name = "cbv/shift_request/shift_request_form.html"
    dynamic_create_fields = [("shift_id", ShiftTypeFormView)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_get.id
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request,
            self.form,
            "base.add_shiftrequest",
        )
        self.form = include_employee_instance(self.request, self.form)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Request")
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )
        self.form.fields["employee_id"].initial = employee
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Request")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: ShiftRequestForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Shift request updated Successfully")
                form.save()
            else:
                instance = form.save()
                message = _("Shift request added Successfully")
                with contextlib.suppress(Exception):
                    notify.send(
                        instance.employee_id,
                        recipient=instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        verb=gettext_noop(
                            "You have new shift request to approve for %(employee)s"
                        ),
                        verb_params={"employee": str(instance.employee_id)},
                        icon="information",
                        redirect=shift_requests_url(instance),
                    )
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class ShiftRequestFormDuplicate(EmployeeScopeMixin, HorillaFormView):
    """
    Duplicate form view
    """

    scope_perm = "base.add_shiftrequest"
    scope_include_self = True

    def get_scope_perm(self):
        # Always creates a new record, although the route carries a pk.
        return self.scope_perm

    model = ShiftRequest
    form_class = ShiftRequestForm
    template_name = "cbv/shift_request/shift_request_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = ShiftRequest.objects.get(id=self.kwargs["pk"])
        self.form = self.form_class(instance=original_object)
        for field_name, field in self.form.fields.items():
            if isinstance(field, forms.CharField):
                if field.initial:
                    initial_value = field.initial
                else:
                    initial_value = f"{self.form.initial.get(field_name, '')} (copy)"
                self.form.initial[field_name] = initial_value
                self.form.fields[field_name].initial = initial_value
        self.form = choosesubordinates(
            self.request,
            self.form,
            "base.add_shiftrequest",
        )
        self.form = include_employee_instance(self.request, self.form)
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )
        context["form"] = self.form
        self.form_class.verbose_name = _("Duplicate")
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        # form = self.form_class(self.request.POST)
        self.form_class.verbose_name = _("Duplicate")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: ShiftRequestForm) -> HttpResponse:
        form = self.form_class(self.request.POST)
        if form.is_valid():
            form.save()
            message = _("Shift request added Successfully")
            messages.success(self.request, message)
            return HorillaRedirect(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class ShiftAllocationFormView(EmployeeScopeMixin, HorillaFormView):
    """
    Form View
    """

    scope_perm = "base.add_shiftrequest"
    scope_include_self = True

    model = ShiftRequest
    form_class = ShiftAllocationForm
    new_display_title = _("Shift Swap Request")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request,
            self.form,
            "base.add_shiftrequest",
        )
        self.form = include_employee_instance(self.request, self.form)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Request")
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].initial = employee
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:

        # form = self.form_class(self.request.POST)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Request")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: ShiftAllocationForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Shift request updated Successfully")
                form.save()
            else:
                instance = form.save()
                message = _("Shift request added Successfully")
                reallocate_emp = form.cleaned_data["reallocate_to"]
                with contextlib.suppress(Exception):
                    notify.send(
                        form.instance.employee_id,
                        recipient=form.instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        verb=gettext_noop(
                            "You have a new shift reallocation request to approve for %(employee)s."
                        ),
                        verb_params={"employee": str(instance.employee_id)},
                        icon="information",
                        redirect=shift_requests_url(instance),
                    )

                    notify.send(
                        instance.employee_id,
                        recipient=reallocate_emp.employee_user_id,
                        verb=gettext_noop(
                            "You have a new shift reallocation request from %(employee)s."
                        ),
                        verb_params={"employee": str(instance.employee_id)},
                        icon="information",
                        redirect=shift_requests_url(instance),
                    )
            messages.success(self.request, message)
            return HorillaRedirect(self.request)

        return super().form_valid(form)
