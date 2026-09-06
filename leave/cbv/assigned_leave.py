"""
this page handles cbv of assigned leave page
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.decorators import manager_can_enter
from base.methods import eval_validate, filtersubordinates, has_export_access
from horilla_views.cbv_methods import (
    get_short_uuid,
    hx_request_required,
    login_required,
)
from horilla_views.forms import DynamicBulkUpdateForm
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from leave.filters import AssignedLeaveFilter
from leave.forms import AssignLeaveForm, AvailableLeaveColumnExportForm
from leave.models import AvailableLeave


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("leave.view_availableleave"), name="dispatch")
class AssignedLeaveViewPage(TemplateView):
    """
    for assigned leave page
    """

    template_name = "cbv/assigned_leave/assigned_leave_home.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("leave.view_availableleave"), name="dispatch")
class AssignedleaveList(HorillaListView):
    """
    list view of the page
    """

    model = AvailableLeave
    filter_class = AssignedLeaveFilter
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("assign-filter")
        self.view_id = "assignedleavedelete"

    row_attrs = """
                hx-get='{assigned_leave_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = filtersubordinates(
            self.request, queryset, "leave.view_availableleave"
        )
        return queryset

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Badge ID"), "employee_id__badge_id"),
        (_("Leave Type"), "leave_type_id"),
        (_("Available Days"), "available_days"),
        (_("Carryforward Days"), "carryforward_days"),
        (_("Total Leave Days"), "total_leave_days"),
        (_("Assigned Date"), "assigned_date"),
        (_("Taken Leaves"), "leave_taken"),
    ]

    action_method = "assigned_leave_actions"
    # Mirrors AssignedLeaveNavView.nested_group_by_fields -- needed here
    # too since this (List) and Nav are separate classes; see the same
    # split in employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("available_days", _("Available Days")),
        ("carryforward_days", _("Carryforward Days")),
        ("total_leave_days", _("Total Leave Days")),
        ("assigned_date", _("Assigned Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employement Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]

    bulk_update_fields = [
        "leave_type_id",
        "available_days",
        "carryforward_days",
        "total_leave_days",
        "assigned_date",
    ]

    def get_bulk_form(self):
        form = super().get_bulk_form()
        form.fields["add_available_days"] = forms.FloatField(
            required=False,
            label=_("Add Available Days"),
            help_text=_(
                "Adds this value to each selected record's existing Available "
                "Days, instead of replacing it."
            ),
            widget=forms.NumberInput(attrs={"class": "oh-input w-100"}),
        )
        return form

    def handle_bulk_submission(self, request):
        """
        This method to handle bulk update form submission, including the
        custom "Add Available Days" field that increments available_days
        per selected record instead of replacing it.
        """
        if not self.bulk_update_accessibility():
            return HttpResponse("You dont have permission")

        instance_ids = eval_validate(request.POST.get("instance_ids", "[]"))
        form = DynamicBulkUpdateForm(
            request.POST,
            request.FILES,
            root_model=self.model,
            bulk_update_fields=self.bulk_update_fields,
            ids=instance_ids,
        )
        form.fields["add_available_days"] = forms.FloatField(
            required=False, label=_("Add Available Days")
        )
        if instance_ids and form.is_valid():
            form.save()

            add_available_days = request.POST.get("add_available_days")
            if add_available_days:
                for available_leave in AvailableLeave.objects.filter(
                    id__in=instance_ids
                ):
                    available_leave.available_days = (
                        available_leave.available_days or 0
                    ) + float(add_available_days)
                    available_leave.save()

            messages.success(request, _("Selected Records updated"))

            script_id = get_short_uuid(length=3, prefix="bulk")
            return HttpResponse(
                f"""
                <script id="{script_id}">
                    $("#{script_id}").closest(".oh-modal--show").removeClass("oh-modal--show");
                    $("#{self.selected_instances_key_id}").attr("data-ids", "[]");
                    $(".reload-record").click()
                    $("#reloadMessagesButton").click()
                </script>
                """
            )
        if not instance_ids:
            messages.info(request, _("No records selected"))
        return render(
            request,
            self.bulk_template,
            {"form": form, "post_bulk_path": self.post_bulk_path},
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("leave.view_availableleave"), name="dispatch")
class AssignedLeaveNavView(HorillaNavView):
    """
    navbar of the page
    """

    template_name = "cbv/assigned_leave/nav_fixed_filter.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("assign-filter")

        self.actions = [
            {
                "action": _("Import"),
                "attrs": """
                        onclick="
                        importAssignedLeave();
                        "
                        data-toggle = "oh-modal-toggle"
                        data-target = "#assignLeaveTypeImport
                        "
                        style="cursor: pointer;"
                    """,
            },
        ]
        if has_export_access(self.request, AvailableLeave):
            self.actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                        data-toggle = "oh-modal-toggle"
                        data-target = "#genericModal"
                        hx-target="#genericModalBody"
                        hx-get ="{reverse('assigned-leave-nav-export')}"
                        hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                        style="cursor: pointer;"
                    """,
                }
            )
        self.actions.append(
            {
                "action": _("Delete"),
                "attrs": """
                            onclick="leaveAssigBulkDelete()"
                            data-action ="delete"
                            style="cursor: pointer; color:red !important"
                             """,
            }
        )

        if self.request.user.has_perm("leave.add_availableleave"):
            self.create_attrs = f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#objectCreateModal"
                    hx-target="#objectCreateModalTarget"
                    hx-get="{reverse_lazy('assign')}"
                """

    nav_title = _("All Leave Balances")
    filter_instance = AssignedLeaveFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/assigned_leave/assigned_filter.html"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel -- nav_fixed_filter.html just
    # includes generic/horilla_nav.html, which already has the
    # {% if modern_filter %} branch, so no template change is needed
    # here. AssignedLeaveFilter.ajax_fields carries the AJAX-loaded
    # comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("available_days", _("Available Days")),
        ("carryforward_days", _("Carryforward Days")),
        ("total_leave_days", _("Total Leave Days")),
        ("assigned_date", _("Assigned Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employement Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors AssignedleaveList.nested_group_by_fields below -- List and
    # Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the inline
    # "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by the List view) need this
    # here too, not just the currently-active fields it already had access
    # to via nested_fields_active.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("available_days", _("Available Days")),
        ("carryforward_days", _("Carryforward Days")),
        ("total_leave_days", _("Total Leave Days")),
        ("assigned_date", _("Assigned Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employement Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(manager_can_enter("leave.view_availableleave"), name="dispatch")
class AssignedLeaveExport(TemplateView):
    """
    view for Export leave assigns
    """

    template_name = "cbv/assigned_leave/assigned_leave_export.html"

    def get_context_data(self, **kwargs: Any):
        """
        context to get data
        """
        leaves = AvailableLeave.objects.all()
        export_column = AvailableLeaveColumnExportForm()
        export_filter = AssignedLeaveFilter(queryset=leaves)
        context = super().get_context_data(**kwargs)
        context["export_column"] = export_column
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("leave.view_availableleave"), name="dispatch")
class AssignedLeaveDetailView(HorillaDetailedView):
    """
    detail view
    """

    model = AvailableLeave
    ttile = _("Details")
    header = {
        "title": "assigned_leave_detail_name_subtitle",
        "subtitle": "assigned_leave_detail_postion_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    body = [
        (_("Leave Type"), "leave_type_id"),
        (_("Available Days"), "available_days"),
        (_("Carryforward Days"), "carryforward_days"),
        (_("Total Leave Days"), "total_leave_days"),
        (_("Assigned Date"), "assigned_date"),
        (_("Leave Reset Date"), "reset_date"),
    ]

    action_method = "assigned_leave_detail_actions"


# not done
class AssignedLeaveFormView(HorillaFormView):
    """
    form view
    """

    form_class = AssignLeaveForm
    model = AvailableLeave
    new_display_title = _("Assign Leaves")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Available Leave")

        return context

    def form_valid(self, form: AssignLeaveForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Available Leave Updated Successfully")
            else:
                message = _("Available Leave Created Successfully")
            form.save()

            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)
