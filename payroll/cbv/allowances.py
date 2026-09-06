"""
this page handles cbv of allowances page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from payroll.filters import AllowanceFilter
from payroll.forms.component_forms import AllowanceForm
from payroll.models.models import Allowance


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.add_allowance"), name="dispatch")
class AllowanceFormView(HorillaFormView):
    """
    Form view for Allowance creation and update.
    """

    model = Allowance
    form_class = AllowanceForm
    new_display_title = _("Create Allowance")
    template_name = "payroll/allowance/allowance_form.html"

    def form_valid(self, form: AllowanceForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                msg = _("Allowance updated.")
            else:
                msg = _("Allowance created.")
            form.save()
            messages.success(self.request, msg)
            return self.HttpResponse(targets_to_reload=["#applyFilter"])
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_allowance"), name="dispatch")
class AllowanceViewPage(TemplateView):
    """
    for interview page
    """

    template_name = "cbv/allowances/allowances_home.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_allowance"), name="dispatch")
class AllowanceListView(HorillaListView):
    """
    list view of the page
    """

    bulk_update_fields = [
        "specific_employees",
        "exclude_employees",
        "is_taxable",
        "is_fixed",
        "amount",
        "based_on",
        "rate",
    ]

    model = Allowance
    filter_class = AllowanceFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "allowance_id"
        self.search_url = reverse("allowances-list-view")
        if self.request.user.has_perm(
            "payroll.change_allowance"
        ) or self.request.user.has_perm("payroll.delete_allowance"):
            self.action_method = "get_allowance_actions"
        else:
            self.action_method = None

    columns = [
        (_("Allowance"), "title"),
        (_("Is Taxable"), "get_is_taxable_display"),
        (_("Is Condition Based"), "get_is_condition_based"),
        (_("Condition"), "condition_based_display"),
        (_("Is Fixed"), "get_is_fixed"),
        (_("Amount"), "amount"),
        (_("Based On"), "get_based_on_display"),
        (_("Rate"), "rate"),
    ]

    sortby_mapping = [
        (_("Allowance"), "title"),
        (_("Amount"), "amount"),
    ]

    header_attrs = {
        "title": """
                style="width:200px !important;"
                """,
        "get_specific_employees": """
                                style="width:200px !important;"
                                """,
        "get_exclude_employees": """
                                style="width:200px !important;"
                                """,
    }

    row_attrs = """
                hx-get='{allowance_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    row_status_class = "taxable-{is_taxable} fixed-{is_fixed}"

    row_status_indications = [
        (
            "taxable--dot",
            _("Taxable"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=is_taxable]').val('true');
                $('[name=is_fixed]').val('unknown');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "non-taxable--dot",
            _("Non Taxable"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_taxable]').val('false');
            $('[name=is_fixed]').val('unknown');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "fixed--dot",
            _("Fixed"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_fixed]').val('true');
            $('[name=is_taxable]').val('unknown');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "not-fixed--dot",
            _("Not Fixed"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_fixed]').val('false');
            $('[name=is_taxable]').val('unknown');
                $('#applyFilter').click();
            "
            """,
        ),
    ]

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        self.request.allowance_div = "allowance_div"
        return context

    def get_queryset(self):
        """
        Returns a filtered queryset of allowance
        """

        queryset = super().get_queryset()
        queryset = queryset.exclude(only_show_under_employee=True)

        return queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_allowance"), name="dispatch")
class AllowanceNavView(HorillaNavView):
    """
    nav bar of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("allowances-list-view")

        if self.request.user.has_perm("payroll.add_allowance"):
            self.create_attrs = f"""
                                data-toggle="oh-modal-toggle"
                                data-target="#objectCreateModal"
                                hx-get="{reverse_lazy('create-allowance')}"
                                hx-target="#objectCreateModalTarget"
                                """

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse("allowances-list-view"),
                "attrs": f"""
                            title="{_('List')}"
                            """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("allowances-card-view"),
                "attrs": f"""
                            title="{_('Card')}"
                            """,
            },
        ]

    nav_title = _("Allowances")
    filter_instance = AllowanceFilter()
    filter_body_template = "cbv/allowances/allowance_filter.html"
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. AllowanceFilter has no FK/M2M fields, so no
    # ajax_fields are needed here.
    modern_filter = True
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_allowance"), name="dispatch")
class AllowancesCardView(HorillaCardView):
    """
    card view for the page
    """

    model = Allowance
    filter_class = AllowanceFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("allowances-card-view")
        self.view_id = "allowance_card"

    def get_queryset(self):
        """
        Returns a filtered queryset of allowance
        """

        queryset = super().get_queryset()
        queryset = queryset.exclude(only_show_under_employee=True)

        return queryset

    details = {
        "image_src": "get_avatar",
        "title": "{title}",
        "subtitle": format_lazy(
            "{} : {} <br> {} : {} <br> {} : {}",
            _("Amount"),
            "{based_on_amount}",
            _("One Time Allowance"),
            "{one_time_date_display}",
            _("Taxable"),
            "{get_is_taxable_display}",
        ),
    }

    card_attrs = """
                hx-get='{allowance_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    card_status_class = "taxable-{is_taxable} fixed-{is_fixed}"

    card_status_indications = [
        (
            "taxable--dot",
            _("Taxable"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=is_taxable]').val('true');
                $('[name=is_fixed]').val('unknown');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "non-taxable--dot",
            _("Non Taxable"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_taxable]').val('false');
            $('[name=is_fixed]').val('unknown');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "fixed--dot",
            _("Fixed"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_fixed]').val('true');
            $('[name=is_taxable]').val('unknown');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "not-fixed--dot",
            _("Not Fixed"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_fixed]').val('false');
            $('[name=is_taxable]').val('unknown');
                $('#applyFilter').click();
            "
            """,
        ),
    ]

    actions = [
        {
            "action": _("Edit"),
            "attrs": """
            class="oh-dropdown__link"
            hx-get="{get_update_url}"
            hx-target="#objectCreateModalTarget"
            data-target="#objectCreateModal"
            data-toggle="oh-modal-toggle"
            hx-swap="innerHTML"
            """,
        },
        {
            "action": _("Delete"),
            "attrs": """
                    class="oh-dropdown__link"
                    hx-get="{get_delete_url}?model=payroll.Allowance&pk={pk}"
                    data-toggle="oh-modal-toggle"
                    data-target="#deleteConfirmation"
                    hx-target="#deleteConfirmationBody"
                """,
        },
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_allowance"), name="dispatch")
class AllowanceDetailView(HorillaDetailedView):
    """
    detail view for allowances
    """

    model = Allowance
    title = _("Details")

    header = {
        "title": "title",
        "subtitle": "",
        "avatar": "get_avatar",
    }

    body = [
        (_("Taxable"), "get_is_taxable_display"),
        (_("One Time Allowance"), "one_time_date_display"),
        (_("Condition Based"), "condition_based_display"),
        (_("Amount"), "based_on_amount"),
        (_("Has Maximum Limit"), "cust_allowance_max_limit"),
        (_("Allowance Eligibility"), "allowance_eligibility"),
    ]

    action_method = "allowance_detail_actions"
