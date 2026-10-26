from typing import Any

from django.apps import apps
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import PenaltyAccountFilter, PenaltyFilter
from base.forms import PenaltyAccountCreateForm
from base.methods import filtersubordinates
from base.models import PenaltyAccounts
from employee.models import Employee
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)

LEAVE_PENALTY_COLUMNS = (
    [
        (_("Leave Type"), "leave_type_id"),
        (_("Deduct Leave"), "minus_leaves"),
        (_("Deducted From CFD"), "get_deduct_from_carry_forward"),
    ]
    if apps.is_installed("leave")
    else []
)


@method_decorator(login_required, name="dispatch")
class ViewPenaltyList(HorillaListView):
    """
    List view of penalty
    """

    bulk_select_option = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("view-penalties")
        self.view_id = "view-penalty"

    model = PenaltyAccounts
    filter_class = PenaltyFilter
    columns = [
        (_("Penalty Type"), "penalty_type_col"),
        (_("Applied For"), "penalty_reference_col"),
        *LEAVE_PENALTY_COLUMNS,
        (_("Penalty amount"), "penalty_amount"),
        (_("Date"), "penalty_date_col"),
    ]

    header_attrs = {
        "penalty_amount": """
                            style="width:180px !important;"
                            """,
        "penalty_date_col": """
                            style="width:180px !important;"
                            """,
    }


@method_decorator(login_required, name="dispatch")
class PenaltyRecordsList(HorillaListView):
    """
    List view of the Penalty tab under Policies & Discipline
    """

    model = PenaltyAccounts
    filter_class = PenaltyAccountFilter
    bulk_select_option = False
    show_toggle_form = False

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Penalty Type"), "penalty_type_col"),
        (_("Applied For"), "penalty_reference_col"),
        (_("Date"), "penalty_date_col"),
        *LEAVE_PENALTY_COLUMNS,
        (_("Penalty amount"), "penalty_amount"),
    ]

    row_attrs = """ id = "penaltyTr{get_delete_instance}" """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("penalty-records-list")
        self.view_id = "penalty-records"
        if self.request.user.has_perm("base.delete_penaltyaccounts"):
            confirm_text = _("Are you sure you want to delete this penalty?")
            self.actions = [
                {
                    "action": _("Delete"),
                    "icon": "trash-outline",
                    "attrs": f"""
                        class="oh-btn oh-btn--danger oh-btn--sq-sm"
                        hx-confirm="{confirm_text}"
                        hx-post="{{get_delete_url}}"
                        hx-target="#penaltyTr{{get_delete_instance}}"
                        hx-swap="delete"
                    """,
                }
            ]

    def get_queryset(self):
        queryset = super().get_queryset()
        return filtersubordinates(self.request, queryset, "base.view_penaltyaccounts")


@method_decorator(login_required, name="dispatch")
class PenaltyRecordsNav(HorillaNavView):
    """
    Navigation bar of the Penalty tab under Policies & Discipline
    """

    template_name = "generic/inline_nav.html"
    nav_title = _("Penalties")
    filter_instance = PenaltyAccountFilter()
    search_swap_target = "#listContainer"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("penalty-records-list")
        if self.request.user.has_perm("base.add_penaltyaccounts"):
            self.create_attrs = f"""
                                onclick="event.stopPropagation();"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-target="#genericModalBody"
                                hx-get="{reverse('penalty-records-create')}"
                                """


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.add_penaltyaccounts"), name="dispatch")
class PenaltyRecordsFormView(HorillaFormView):
    """
    Create form of the Penalty tab under Policies & Discipline
    """

    model = PenaltyAccounts
    form_class = PenaltyAccountCreateForm
    template_name = "penalty/create_form.html"
    new_display_title = _("Create Penalty")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee_id = self.request.GET.get("employee_id") or self.request.POST.get(
            "employee_id"
        )
        employee = (
            Employee.objects.filter(pk=employee_id).first()
            if str(employee_id).isdigit()
            else None
        )
        context["available"] = (
            employee.available_leave.select_related("leave_type_id")
            if employee and apps.is_installed("leave")
            else []
        )
        return context

    def form_valid(self, form: PenaltyAccountCreateForm) -> HttpResponse:
        if form.is_valid():
            form.save()
            messages.success(self.request, _("Penalty added"))
            return self.HttpResponse()
        return super().form_valid(form)
