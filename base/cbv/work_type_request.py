"""
this page is handling the cbv methods of work request page
"""

import contextlib
from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import WorkTypeRequestFilter
from base.forms import WorkTypeForm, WorkTypeRequestColumnForm, WorkTypeRequestForm
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from base.models import WorkType, WorkTypeRequest
from base.views import include_employee_instance
from employee.models import Employee
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class WorkRequestView(TemplateView):
    """
    for page view
    """

    template_name = "cbv/work_type_request/work_type_home.html"


@method_decorator(login_required, name="dispatch")
class WorkRequestListView(HorillaListView):
    """
    list view of the work request page
    """

    filter_class = WorkTypeRequestFilter
    model = WorkTypeRequest
    # The Actions dropdown's own Export entry covers this (exports the
    # selection, or everything when nothing is selected), so this standalone
    # quick-action button would just duplicate it.
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("work-list-view")
        self.view_id = "work-shift"

    def get_queryset(self):
        """
        queryset to filter data based on permission
        """
        queryset = super().get_queryset()
        view_data = queryset

        employee = self.request.user.employee_get
        queryset = filtersubordinates(
            self.request, queryset, "base.view_worktyperequest"
        )
        queryset = queryset | view_data.filter(employee_id=employee)
        queryset = queryset.filter(employee_id__is_active=True)
        return queryset

    columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Requested Work Type"), "work_type_id"),
        (_("Previous/current Work Type"), "previous_work_type_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Status"), "request_status"),
        (_("Description"), "description"),
        (_("Comment"), "comment_note"),
    ]

    default_columns = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Requested Work Type"), "work_type_id"),
        (_("Previous/current Work Type"), "previous_work_type_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Status"), "request_status"),
    ]

    action_method = "confirmation"

    header_attrs = {
        "action": """
                style="width:200px !important;"
                """,
    }

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Requested Work Type"), "work_type_id__work_type"),
        (_("Previous/current Work Type"), "previous_work_type_id__work_type"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
    ]
    row_attrs = """
                hx-get='{detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    row_status_class = (
        "approved-{approved} canceled-{canceled} requested-{approved}-{canceled}"
    )
    row_status_indications = [
        (
            "canceled--dot",
            _("Rejected"),
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
class WorkRequestNavView(HorillaNavView):
    """
    nav view of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("work-list-view")
        self.actions = []
        if self.request.user.has_perm(
            "base.change_worktyperequest"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Approve Requests"),
                    "attrs": """
                    onclick="
                    handleApproveRequestsClick();
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
                    handleRejectRequestsClick();
                    "
                    style="cursor: pointer;"
                    """,
                }
            )
        if self.request.user.has_perm(
            "base.delete_worktyperequest"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                    onclick="
                    handleDeleteRequestsClick();
                    "
                    data-action ="delete"
                    style="cursor: pointer; color:red !important"

                    """,
                }
            )
        if has_export_access(self.request, WorkTypeRequest):
            self.actions.insert(
                0,
                {
                    "action": _("Export"),
                    "attrs": f"""
                hx-target = "#genericModalBody"
                data-toggle = "oh-modal-toggle"
                data-target = "#genericModal"
                hx-get ="{reverse('work-export-candidate')}"
                hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                style="cursor: pointer;"
            """,
                },
            )

        self.create_attrs = f"""
             hx-get="{reverse_lazy("work-type-request")}"
             hx-target="#genericModalBody"
             data-target="#genericModal"
             data-toggle="oh-modal-toggle"
         """

    nav_title = _("Work Type Requests")
    template_name = "generic/inline_nav.html"
    filter_body_template = "cbv/work_type_request/filter.html"
    filter_instance = WorkTypeRequestFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. WorkTypeRequestFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("work_type_id", _("Requested Work Type")),
        ("previous_work_type_id", _("current Work Type")),
        ("requested_date", _("Requested Date")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
    ]


@method_decorator(login_required, name="dispatch")
class WorkTypeDetailView(HorillaDetailedView):
    """
    Detail view of page
    """

    model = WorkTypeRequest
    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    body = [
        (_("Requested Work Type"), "work_type_id"),
        (_("Previous Work Type"), "previous_work_type_id"),
        (_("Requested Date"), "requested_date"),
        (_("Requested Till"), "requested_till"),
        (_("Is Permanent Work Type"), "is_permanent_work_type_display"),
        (_("Description"), "description"),
    ]

    cols = {
        "description": 12,
    }

    action_method = "detail_confirmation"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # detail_confirmation.html carries the same per-role conditions as
        # the row's confirmation() actions (Edit/Duplicate/Delete/Approve/
        # Reject), so there's no need to swap templates by viewer role here.
        self.action_method = "detail_confirmation"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class WorkExportCandidate(TemplateView):
    """
    view for Export candidates
    """

    template_name = "cbv/work_type_request/work_export.html"

    def get_context_data(self, **kwargs: Any):
        """
        get data for export
        """
        candidates = WorkTypeRequest.objects.all()
        export_fields = WorkTypeRequestColumnForm()
        export_filter = WorkTypeRequestFilter(queryset=candidates)
        context = super().get_context_data(**kwargs)
        context["export_fields"] = export_fields
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
class DynamicWorkTypeCreateForm(HorillaFormView):
    """
    form view for creating dynamic work types
    """

    model = WorkType
    form_class = WorkTypeForm
    new_display_title = _("Create Work Type")
    is_dynamic_create_view = True

    def form_valid(self, form: WorkTypeForm) -> HttpResponse:
        if form.is_valid():
            form.save()
            messages.success(self.request, _("New Work Type Created"))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.add_worktype"), name="dispatch")
class WorkTypesCreateForm(DynamicWorkTypeCreateForm):
    """
    form view for creating work types on settings
    """

    is_dynamic_create_view = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = self.form_class()
        if self.form.instance.pk:
            form = self.form_class(instance=self.form.instance)
            self.form_class.verbose_name = _("Update Work Type")
        context[form] = form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Work Type")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: WorkTypeForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                messages.success(self.request, _("Work Type Updated"))
            else:
                messages.success(self.request, _("New Work Type Created"))
            form.save()
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class WorkTypeFormView(HorillaFormView):
    """
    form view for creating work types in app
    """

    model = WorkTypeRequest
    form_class = WorkTypeRequestForm
    template_name = "cbv/work_type_request/form/form.html"

    new_display_title = _("Work Type Request")
    dynamic_create_fields = [("work_type_id", DynamicWorkTypeCreateForm)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_get.id
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request,
            self.form,
            "base.add_worktyperequest",
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

        # form = self.form_class(self.request.POST)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Request")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: WorkTypeRequestForm) -> HttpResponse:

        if form.is_valid():
            if form.instance.pk:
                message = _("Request Updated Successfully")
                form.save()
            else:
                instance = form.save()
                message = _("Work type Request Created")
                with contextlib.suppress(Exception):
                    notify.send(
                        instance.employee_id,
                        recipient=(
                            instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                        ),
                        verb=f"You have new work type request to \
                            validate for {instance.employee_id}",
                        verb_ar=f"لديك طلب نوع وظيفة جديد للتحقق من \
                                {instance.employee_id}",
                        verb_de=f"Sie haben eine neue Arbeitstypanfrage zur \
                                Validierung für {instance.employee_id}",
                        verb_es=f"Tiene una nueva solicitud de tipo de trabajo para \
                                validar para {instance.employee_id}",
                        verb_fr=f"Vous avez une nouvelle demande de type de travail\
                                à valider pour {instance.employee_id}",
                        icon="information",
                        redirect=reverse("work-type-request-view")
                        + f"?id={instance.id}",
                    )

            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class WorkTypeDuplicateForm(HorillaFormView):
    """
    duplicate form
    """

    model = WorkTypeRequest
    form_class = WorkTypeRequestForm
    # template_name = "cbv/work_type_request/form/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = WorkTypeRequest.objects.get(id=self.kwargs["pk"])
        self.form = self.form_class(instance=original_object)

        for field_name, field in self.form.fields.items():
            if isinstance(field, forms.CharField):
                initial_value = self.form.initial.get(field_name, "")
                if initial_value:
                    initial_value += " (copy)"
                self.form.initial[field_name] = initial_value
                self.form.fields[field_name].initial = initial_value
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request,
            self.form,
            "base.add_worktyperequest",
        )
        self.form = include_employee_instance(self.request, self.form)
        if hasattr(self.form.instance, "id"):
            self.form.instance.id = None
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )

        # context["form"] = form
        context["form"] = self.form
        self.form_class.verbose_name = _("Work Type Request")
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        # form = self.form_class(self.request.POST)
        self.form_class.verbose_name = _("Work Type Request")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: WorkTypeRequestForm) -> HttpResponse:
        form = self.form_class(self.request.POST)
        if form.is_valid():
            form.save()
            message = _("Work type Request Created")
            messages.success(self.request, message)
            return self.HttpResponse()

        return super().form_valid(form)
