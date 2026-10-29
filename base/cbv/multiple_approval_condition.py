"""
Multiple approval condition page
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import MultipleApprovalConditionFilter
from base.forms import MultipleApproveConditionForm
from base.models import MultipleApprovalCondition, MultipleApprovalManagers
from base.widgets import CustomModelChoiceWidget
from employee.models import Employee
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
class MultipleApprovalConditionView(TemplateView):
    """
    Legacy standalone Multiple Approval page. Migrated into Leave > Configuration;
    redirect direct visits to the merged settings page.
    """

    template_name = "cbv/multiple_approval_condition/multiple_approval_condition.html"

    def get(self, request, *args, **kwargs):
        return redirect("leave-settings-view")


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="base.view_multipleapprovalcondition"), name="dispatch"
)
class MultipleApprovalConditionList(HorillaListView):
    """
    List view of the resticted days page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.search_url = reverse("hx-multiple-approval-condition")
        self.action_method = "actions_col"
        self.view_id = "multipleApproveCondition"

    model = MultipleApprovalCondition
    filter_class = MultipleApprovalConditionFilter

    columns = [
        (_("Department"), "department"),
        (_("Condition Field"), "get_condition_field"),
        (_("Condition Operator"), "get_condition_operator"),
        (_("Condition Value"), "get_condition_value"),
        (_("Approval Managers"), "approval_managers_col"),
        (_("Company"), "company_id"),
    ]

    header_attrs = {
        "department": """ style="width:180px !important" """,
        "approval_managers_col": """ style="width:200px !important" """,
        "action": """ style="width:180px !important" """,
    }

    sortby_mapping = [
        (_("Department"), "department__department"),
        (_("Condition Operator"), "get_condition_operator"),
        (_("Condition Value"), "get_condition_value"),
    ]

    row_attrs = """
                hx-get='{detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="base.view_multipleapprovalcondition"), name="dispatch"
)
class MultipleApprovalConditionNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("hx-multiple-approval-condition")
        if self.request.user.has_perm("base.add_multipleapprovalcondition"):
            self.create_attrs = f"""
                                onclick = "event.stopPropagation();"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-target="#genericModalBody"
                                hx-get="{reverse('multiple-level-approval-create')}"
                                """
        if self.request.user.has_perm("base.view_multipleapprovalcondition"):
            self.filter_body_template = "cbv/multiple_approval_condition/filter.html"

    nav_title = _("Multiple Approval Rules")
    filter_instance = MultipleApprovalConditionFilter()
    modern_filter = True
    # "#listContainer" is a generic id every tab's own content template
    # reuses (e.g. the sibling "Leave Types" tab on the same Leave Settings
    # page) - once both tabs have been visited, both live in the DOM at once
    # (inactive tabs are hidden via CSS, not removed), so a non-namespaced
    # target here can resolve to the wrong tab's stale container and quietly
    # swap content into it instead of this view's own. Target the list
    # view's own, page-unique view_id instead.
    search_swap_target = "#multipleApproveCondition"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="base.view_multipleapprovalcondition"), name="dispatch"
)
class MultipleApprovalConditionDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Condition Field"), "get_condition_field"),
            (_("Condition Operator"), "get_condition_operator"),
            (_("Condition Value"), "get_condition_value"),
            (_("Approval Managers"), "approval_managers_col"),
        ]

    action_method = "detail_actions"
    detail_note_method = "get_description"

    model = MultipleApprovalCondition
    title = _("Details")
    header = {
        "title": "department",
        "subtitle": "",
        "avatar": "get_avatar",
    }


@method_decorator(login_required, name="dispatch")
class MultipleApprovalConditionFormView(HorillaFormView):
    """
    Create and edit form
    """

    model = MultipleApprovalCondition
    form_class = MultipleApproveConditionForm
    new_display_title = _("Create Multiple Approval Condition")
    template_name = "cbv/multiple_approval_condition/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form.fields["condition_operator"].widget.attrs[
            "hx-target"
        ] = "#id_condition_value_parent_div"
        self.form.fields["condition_operator"].widget.attrs["hx-swap"] = "innerHTML"
        return context

    def get_submitted_managers(self):
        """
        Every submitted "Add Manager" slot, in the order they were added.

        The first slot is always named "multi_approval_manager"; each one
        added afterward via the "Add Manager" button gets
        "multi_approval_manager_<n>" (base/views.py's add_more_approval_
        managers), so collecting just the exact key "multi_approval_manager"
        (the create path used to, via request.POST.getlist()) silently
        dropped every manager beyond the first. Sorted by that numeric
        suffix (the first slot sorts before all of them) so the resulting
        list still reflects the order managers were actually added in,
        regardless of dict/POST key order.
        """
        entries = []
        for key, value in self.request.POST.items():
            if not value:
                continue
            if key == "multi_approval_manager":
                entries.append((0, value))
            elif key.startswith("multi_approval_manager_"):
                suffix = key[len("multi_approval_manager_") :]
                if suffix.isdigit():
                    entries.append((int(suffix), value))
        entries.sort(key=lambda pair: pair[0])
        return [value for _, value in entries]

    def form_valid(self, form: MultipleApproveConditionForm) -> HttpResponse:
        if form.is_valid():
            condition_approval_managers = self.get_submitted_managers()
            if not condition_approval_managers:
                form.add_error(None, _("At least one approval manager is required."))
                return self.form_invalid(form)
            instance = form.save()
            MultipleApprovalManagers.objects.filter(
                condition_id=self.form.instance
            ).delete()
            message = _("Multiple approval condition Created Successfully")
            for sequence, emp_id in enumerate(condition_approval_managers, start=1):
                reporting_manager = None
                try:
                    employee_id = int(emp_id)
                except:
                    employee_id = None
                    reporting_manager = emp_id
                MultipleApprovalManagers.objects.create(
                    condition_id=instance,
                    sequence=sequence,
                    employee_id=employee_id,
                    reporting_manager=reporting_manager,
                )
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class EditApprovalConditionFormView(MultipleApprovalConditionFormView):
    """
    Edit form
    """

    template_name = "cbv/multiple_approval_condition/form_edit.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form.fields["condition_operator"].widget.attrs["hx-swap"] = "innerHTML"
        self.form.fields["condition_operator"].widget.attrs[
            "hx-target"
        ] = "#id_condition_value_parent_div"
        managers = MultipleApprovalManagers.objects.filter(
            condition_id=self.form.instance
        ).order_by("sequence")
        self.approval_managers_edit(self.form, managers)
        context["managers_count"] = len(managers)
        context["form"] = self.form
        self.form_class.verbose_name = _("Update Multiple Approval Condition")
        return context

    def approval_managers_edit(self, form, managers):
        for i, manager in enumerate(managers):
            if i == 0:
                form.initial["multi_approval_manager"] = managers[0].employee_id
            else:
                field_name = f"multi_approval_manager_{i}"
                form.fields[field_name] = forms.ModelChoiceField(
                    queryset=Employee.objects.all(),
                    label=_("Approval Manager") if i == 0 else "",
                    widget=CustomModelChoiceWidget(
                        delete_url="/configuration/remove-approval-manager",
                        attrs={
                            "class": "oh-select oh-select-2 mb-3",
                            "name": field_name,
                            "id": f"id_{field_name}",
                        },
                    ),
                    required=False,
                )
                form.initial[field_name] = manager.employee_id

    def form_valid(self, form: MultipleApproveConditionForm) -> HttpResponse:
        if form.is_valid():
            condition_approval_managers = self.get_submitted_managers()
            if not condition_approval_managers:
                form.add_error(None, _("At least one approval manager is required."))
                return self.form_invalid(form)
            instance = form.save()
            MultipleApprovalManagers.objects.filter(
                condition_id=self.form.instance
            ).delete()
            message = _("Multiple approval condition updated Successfully")
            for sequence, emp_id in enumerate(condition_approval_managers, start=1):
                reporting_manager = None
                try:
                    employee_id = int(emp_id)
                except:
                    employee_id = None
                    reporting_manager = emp_id
                MultipleApprovalManagers.objects.create(
                    condition_id=instance,
                    sequence=sequence,
                    employee_id=employee_id,
                    reporting_manager=reporting_manager,
                )
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)
