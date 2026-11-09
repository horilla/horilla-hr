"""
Arrears and recovery: the configuration tab's nav and list, the form, and the approve, cancel and
delete actions.
"""

import json
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from base.methods import eval_validate
from horilla.decorators import login_required as login_required_fn
from horilla.decorators import permission_required as permission_required_fn
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)
from payroll.filters import PayAdjustmentFilter
from payroll.forms.component_forms import PayAdjustmentBulkForm, PayAdjustmentForm
from payroll.models.models import PayAdjustment

# What the list can be grouped by, in the nav's Group By and the list's "Grouped by" breadcrumb (the
# two are separate classes, so both carry it).
GROUP_BY_FIELDS = [
    ("kind", _("Type")),
    ("status", _("Status")),
    ("employee_id", _("Employee")),
    ("title", _("Title")),
    ("pay_date", _("Pay Date")),
    ("employee_id__employee_work_info__department_id", _("Department")),
    ("employee_id__employee_work_info__job_position_id", _("Job Position")),
    ("employee_id__employee_work_info__reporting_manager_id", _("Reporting Manager")),
    ("employee_id__employee_work_info__company_id", _("Company")),
]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_payadjustment"), name="dispatch")
class PayAdjustmentNav(HorillaNavView):
    """Title, search and Create for the Arrears & Recovery tab."""

    nav_title = _("Arrears & Recovery")
    search_swap_target = "#payAdjustmentListContainer"
    apply_first_filter = False
    template_name = "generic/inline_nav.html"
    # The Filter button and its slide-over panel, as on the other configuration lists.
    filter_body_template = "cbv/pay_adjustment/filter.html"
    filter_instance = PayAdjustmentFilter()
    filter_form_context_name = "form"
    modern_filter = True
    group_by_fields = GROUP_BY_FIELDS
    nested_group_by_fields = GROUP_BY_FIELDS

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("pay-adjustment-list-view")
        if self.request.user.has_perm("payroll.add_payadjustment"):
            self.create_attrs = f"""
                hx-get="{reverse('create-pay-adjustment')}"
                data-toggle="oh-modal-toggle"
                data-target="#objectCreateModal"
                hx-target="#objectCreateModalTarget"
                hx-swap="innerHTML"
                """
            # Bringing entries in from a sheet: the upload and its preview open in the modal.
            self.actions = [
                {
                    "action": _("Import"),
                    "attrs": f"""
                        hx-get="{reverse('pay-adjustment-import')}"
                        data-toggle="oh-modal-toggle"
                        data-target="#objectCreateModal"
                        hx-target="#objectCreateModalTarget"
                        hx-swap="innerHTML"
                        """,
                },
            ]
        if self.request.user.has_perm("payroll.delete_payadjustment"):
            # Deletes the ticked rows, with the shared confirm, progress and summary dialogs.
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                        onclick="payAdjustmentBulkDelete()"
                        data-action="delete"
                        style="cursor: pointer; color: red !important"
                        """,
                }
            )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_payadjustment"), name="dispatch")
class PayAdjustmentListView(HorillaListView):
    """The arrears and recovery entries; a row opens its form."""

    model = PayAdjustment
    filter_class = PayAdjustmentFilter
    # Select rows and Update them. The fields only switch Update on: the changes are made by
    # handle_bulk_submission, one entry at a time, by the rules of the entry's own form (the base
    # view's raw UPDATE would change confirmed entries and skip the closed-month check).
    bulk_update_fields = ["status", "tax_treatment", "pay_date"]
    nested_group_by_fields = GROUP_BY_FIELDS

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Type"), "get_kind_display"),
        (_("Title"), "title"),
        (_("Amount"), "amount"),
        (_("Pay Date"), "pay_date"),
        (_("Status"), "status_select"),
        (_("Applied In"), "applied_in"),
    ]
    sortby_mapping = [
        (_("Employee"), "employee_id__employee_first_name"),
        (_("Amount"), "amount"),
        (_("Pay Date"), "pay_date"),
    ]
    row_attrs = """
        hx-get="{get_update_url}"
        hx-target="#objectCreateModalTarget"
        data-target="#objectCreateModal"
        data-toggle="oh-modal-toggle"
        hx-swap="innerHTML"
        """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("pay-adjustment-list-view")

    def get_bulk_form(self):
        return PayAdjustmentBulkForm()

    def handle_bulk_submission(self, request):
        """Update the selected entries: each changes by the rules of one, or is named and left alone."""
        if not self.bulk_update_accessibility():
            return HttpResponse("You don't have permission")
        instance_ids = eval_validate(request.POST.get("instance_ids", "[]"))
        form = PayAdjustmentBulkForm(request.POST)
        if instance_ids and form.is_valid():
            entries = PayAdjustment.objects.filter(pk__in=instance_ids).order_by("pk")
            updated, problems = PayAdjustment.bulk_change(
                entries,
                approved_by=getattr(request.user, "employee_get", None),
                **form.changes(),
            )
            if updated:
                messages.success(
                    request, _("%(count)s Entries Updated.") % {"count": updated}
                )
            for problem in problems[:5]:
                messages.error(request, problem)
            if len(problems) > 5:
                messages.error(
                    request,
                    _("%(count)s More Could Not Be Changed.")
                    % {"count": len(problems) - 5},
                )
            return HttpResponse(
                f"""
                <script id="bulkDone">
                    $("#bulkDone").closest(".oh-modal--show").removeClass("oh-modal--show");
                    $("#{self.selected_instances_key_id}").attr("data-ids", "[]");
                    if (typeof clearSelectionsOnTabSwitch === "function") {{
                        clearSelectionsOnTabSwitch("{self.view_id}");
                    }}
                    $("#applyFilter").click();
                    $("#reloadMessagesButton").click();
                </script>
                """
            )
        if not instance_ids:
            messages.info(request, _("No Records Selected"))
        form.verbose_name = f"{form.verbose_name} ({len(instance_ids)} {_('Records')})"
        return render(
            request,
            self.bulk_template,
            {
                "form": form,
                "post_bulk_path": self.post_bulk_path,
                "instance_ids": instance_ids,
            },
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.add_payadjustment"), name="dispatch")
class PayAdjustmentFormView(HorillaFormView):
    """Create an entry, or open one: only a draft can be changed."""

    model = PayAdjustment
    form_class = PayAdjustmentForm
    new_display_title = _("Arrears & Recovery")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # The base view points every form at the generic template; this form has its own.
        setattr(self.form_class, "structured", PayAdjustmentForm.render_structured)

    def form_valid(self, form: PayAdjustmentForm) -> HttpResponse:
        if form.is_valid():
            was_new = not form.instance.pk
            form.save()
            status = form.instance.status
            if status == "approved":
                message = _("Entry Confirmed.")
            else:
                message = (
                    _("Entry Saved As A Draft.") if was_new else _("Entry Updated.")
                )
            messages.success(self.request, message)
            return self.HttpResponse(targets_to_reload=["#applyFilter"])
        return super().form_valid(form)


def _reloaded(request):
    """A response that makes the list reload itself."""
    response = HttpResponse("", status=200)
    response["HX-Trigger"] = json.dumps({"reloadPayAdjustments": {"target": "body"}})
    return response


@login_required_fn
@permission_required_fn("payroll.change_payadjustment")
@require_http_methods(["POST"])
def set_pay_adjustment_status(request, pk):
    """The Status dropdown in the list: Confirmed makes the pay lines, Draft takes them away."""
    entry = get_object_or_404(PayAdjustment, pk=pk)
    target = request.POST.get("status")
    try:
        if target == entry.status:
            messages.info(
                request,
                _("%(title)s Is Already %(status)s.")
                % {"title": entry.title, "status": entry.get_status_display()},
            )
        elif target == "approved":
            entry.approve(approved_by=getattr(request.user, "employee_get", None))
            messages.success(
                request, _("%(title)s Confirmed.") % {"title": entry.title}
            )
        elif target == "draft":
            entry.revert()
            messages.success(
                request, _("%(title)s Is Back To Draft.") % {"title": entry.title}
            )
        else:
            messages.error(request, _("That Is Not A Status."))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return _reloaded(request)


@login_required_fn
@permission_required_fn("payroll.delete_payadjustment")
@require_http_methods(["POST"])
def delete_pay_adjustment(request, pk):
    """Delete a draft; a confirmed entry has to go back to Draft first."""
    entry = get_object_or_404(PayAdjustment, pk=pk)
    try:
        entry.delete()
        messages.success(request, _("Entry Deleted."))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return _reloaded(request)


@login_required_fn
@permission_required_fn("payroll.delete_payadjustment")
@require_http_methods(["POST"])
def pay_adjustment_bulk_delete(request):
    """
    Delete the posted ids, one by one. A confirmed entry, or one already on a payslip, refuses and is
    left; the page's delete summary counts what is gone, so nothing is said per entry here.
    """
    try:
        ids = json.loads(request.POST.get("ids", "[]"))
    except ValueError:
        ids = []
    if not ids:
        messages.error(request, _("No IDs Provided For Deletion."))
        return JsonResponse({"message": "error."}, status=400)
    for entry in PayAdjustment.objects.filter(pk__in=ids):
        try:
            entry.delete()
        except ValidationError as error:
            messages.error(request, f"{entry}: {' '.join(error.messages)}")
    return JsonResponse({"message": "Success"})
