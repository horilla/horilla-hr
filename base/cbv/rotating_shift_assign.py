"""
Rotating shift request

"""

import contextlib
from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.cbv.rotating_shift import DynamicRotatingShiftTypeFormView
from base.decorators import manager_can_enter
from base.filters import RotatingShiftAssignFilters
from base.forms import RotatingShiftAssignExportForm, RotatingShiftAssignForm
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from base.models import RotatingShiftAssign
from employee.models import Employee
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingShiftAssignView(TemplateView):
    """
    Shift request page
    """

    template_name = "cbv/rotating_shift/rotating_shift.html"


@method_decorator(login_required, name="dispatch")
class RotatingShiftListParent(HorillaListView):
    """
    Parent class
    """

    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("rotating-shift-request-list")
        # self.filter_keys_to_remove = ["deleted"]
        self.view_id = "rotating-shift-container"
        if (
            self.request.user.has_perm("base.delete_rotatingshiftassign")
            or self.request.user.has_perm("base.change_rotatingshiftassign")
            or is_reportingmanager(self.request)
        ):
            self.action_method = "actions"
        else:
            self.action_method = None

    model = RotatingShiftAssign
    filter_class = RotatingShiftAssignFilters
    template_name = "cbv/rotating_shift/extended_rotating_shift.html"
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Rotating Shift"), "rotating_shift_id"),
        (_("Based on"), "get_based_on_display"),
        (_("Rotate"), "rotating_column"),
        (_("Start Date"), "start_date"),
        (_("Current Shift"), "current_shift"),
        (_("Next Switch"), "next_change_date"),
        (_("Next Shift"), "next_shift"),
    ]

    header_attrs = {
        "action": """
                   style="width:130px !important;"
                   """
    }

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Rotating Shift"), "rotating_shift_id__name"),
        (_("Based on"), "get_based_on_display"),
        (_("Rotate"), "rotating_column"),
        (_("Next Shift"), "next_shift__employee_shift"),
        (_("Start Date"), "start_date"),
        (_("Current Shift"), "current_shift__employee_shift"),
        (_("Next Switch"), "next_change_date"),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingShiftList(RotatingShiftListParent):
    """
    List view
    """

    bulk_update_fields = ["rotating_shift_id", "start_date"]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = filtersubordinates(
            self.request, queryset, "base.view_rotatingshiftassign"
        )

        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)

        return queryset

    row_attrs = """
                hx-get='{rotating_shift_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingShiftAssignNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("rotating-shift-request-list")
        if self.request.user.has_perm(
            "base.add_rotatingshiftassign"
        ) or is_reportingmanager(self.request):
            self.create_attrs = f"""
                hx-get="{reverse_lazy('rotating-shift-assign-add')}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
            """
        self.actions = []

        if self.request.user.has_perm(
            "base.view_rotatingshiftassign"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Import"),
                    "attrs": f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#shiftImport"
                            class="oh-dropdown__link"
                            role = "button"
                            onclick="template_download(event)"
                         """,
                },
            )

        if has_export_access(self.request, RotatingShiftAssign):
            self.actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-get="{reverse('export-rshift')}"
                        hx-target ="#genericModalBody"
                        hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                        style="cursor: pointer;"
                        """,
                },
            )
        if self.request.user.has_perm(
            "base.change_rotatingshiftassign"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Archive"),
                    "attrs": """
                        onclick = "archiveRotateShift();"
                        style="cursor: pointer;"
                        """,
                }
            )
            self.actions.append(
                {
                    "action": _("Un-Archive"),
                    "attrs": """
                        onclick = "un_archiveRotateShift();"
                        style="cursor: pointer;"
                        """,
                }
            )
        if self.request.user.has_perm(
            "base.delete_rotatingshiftassign"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                            class ="shift"
                            onclick = "deleteRotatingShift();"
                            data-action ="delete"
                            style="cursor: pointer; color:red !important"
                            """,
                }
            )

    nav_title = _("Rotating Shift Assigns")
    template_name = "generic/inline_nav.html"
    filter_body_template = "cbv/rotating_shift/rotating_shift_filter.html"
    filter_instance = RotatingShiftAssignFilters()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. RotatingShiftAssignFilters.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("rotating_shift_id", _("Rotating Shift")),
        ("based_on", _("Based on")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job role")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingShiftDetailview(HorillaDetailedView):
    """
    Detail View
    """

    model = RotatingShiftAssign

    title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "rotating_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Title"), "rotating_shift_id"),
        (_("Based on"), "get_based_on_display"),
        (_("Rotate"), "rotating_column"),
        (_("Start Date"), "start_date"),
        (_("Current Shift"), "current_shift"),
        (_("Next Shift"), "next_shift"),
        (_("Next Change Date"), "next_change_date"),
        (_("Status"), "check_active"),
    ]

    action_method = "rotating_detail_actions"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = context.get("object")
        if instance is None:
            # No matching row (e.g. a stale/invalid pk) -- the parent's own
            # get_context_data already skips setting instance_ids for this
            # case, and its get() renders empty_template / redirects with
            # "No record found" once this returns, so there's nothing to
            # attach ordered_ids to here.
            return context
        instance.ordered_ids = context.get("instance_ids", [])
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingExportView(TemplateView):
    """
    For candidate export
    """

    template_name = "cbv/rotating_shift/rshift_export.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        rshift_requests = RotatingShiftAssign.objects.all()
        export_columns = RotatingShiftAssignExportForm
        export_filter = RotatingShiftAssignFilters(queryset=rshift_requests)
        context["export_columns"] = export_columns
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.add_rotatingshiftassign"), name="dispatch")
class RotatingShiftFormView(HorillaFormView):
    """
    Create and edit form
    """

    model = RotatingShiftAssign
    form_class = RotatingShiftAssignForm
    new_display_title = _("Rotating Shift Assign")
    dynamic_create_fields = [("rotating_shift_id", DynamicRotatingShiftTypeFormView)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].initial = employee
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )
        if self.form.instance.pk:
            form = self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request, self.form, "base.add_rotatingshiftassign"
        )
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Rotating Shift Assign Update")
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Rotating Shift Assign Update")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: RotatingShiftAssignForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Rotating Shift Assign Updated Successfully")
            else:
                message = _("Rotating Shift Assign Created Successfully")
                employee_ids = self.request.POST.getlist("employee_id")
                employees = Employee.objects.filter(id__in=employee_ids).select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in employees]
                with contextlib.suppress(Exception):
                    notify.send(
                        self.request.user.employee_get,
                        recipient=users,
                        verb="You are added to rotating shift",
                        verb_ar="تمت إضافتك إلى وردية الدورية",
                        verb_de="Sie werden der rotierenden Arbeitsschicht hinzugefügt",
                        verb_es="Estás agregado a turno rotativo",
                        verb_fr="Vous êtes ajouté au quart de travail rotatif",
                        icon="infinite",
                        redirect=reverse("employee-profile"),
                    )
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse("")
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.view_rotatingshiftassign"), name="dispatch")
class RotatingShiftAssignDuplicate(HorillaFormView):
    """
    Duplicate form view
    """

    model = RotatingShiftAssign
    form_class = RotatingShiftAssignForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = RotatingShiftAssign.objects.get(id=self.kwargs["pk"])
        form = self.form_class(instance=original_object)
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate")
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        self.form_class.verbose_name = _("Duplicate")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: RotatingShiftAssignForm) -> HttpResponse:
        form = self.form_class(self.request.POST)
        self.form_class.verbose_name = _("Duplicate")
        if form.is_valid():
            message = _("Rotating Shift Assign Created Successfully")
            messages.success(self.request, message)
            form.save()
            return self.HttpResponse()
        return self.form_invalid(form)
