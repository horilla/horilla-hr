"""
this page is handling the cbv methods of holiday page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import HolidayFilter
from base.forms import HolidayForm, HolidaysColumnExportForm
from base.methods import has_export_access
from base.models import Holidays
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


@method_decorator(login_required, name="dispatch")
class HolidaysView(TemplateView):
    """
    Standalone Public Holidays page, linked from the Leave app sidebar.
    """

    template_name = "cbv/holidays/holidays_home.html"


@method_decorator(login_required, name="dispatch")
class HolidayListView(HorillaListView):
    """
    list view
    """

    bulk_update_fields = ["recurring"]

    filter_class = HolidayFilter
    model = Holidays
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("holiday-filter")
        self.view_id = "holidaydelete"
        if self.request.user.has_perm(
            "base.change_holidays"
        ) or self.request.user.has_perm("base.delete_holidays"):
            self.action_method = "holidays_actions"

    columns = [
        (_("Holiday Name"), "name"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Recurring"), "get_recurring_status"),
    ]

    header_attrs = {
        "name": """ style="width:200px !important;" """,
        "action": """ style="width:180px !important;" """,
    }

    sortby_mapping = [
        (_("Holiday Name"), "name"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
    ]

    row_attrs = """
        hx-get='{detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
class HolidayNavView(HorillaNavView):
    """
    nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("holiday-filter")
        self.actions = []
        if self.request.user.has_perm("base.add_holidays"):
            self.create_attrs = f"""
                hx-get="{reverse_lazy('holiday-creation')}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """
            self.actions.append(
                {
                    "action": _("Import"),
                    "attrs": """
                        onclick="importHolidays();"
                        data-toggle = "oh-modal-toggle"
                        data-target = "#holidayImport"
                        style="cursor: pointer;"
                    """,
                }
            )
        if has_export_access(self.request, Holidays):
            self.actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                        data-toggle = "oh-modal-toggle"
                        data-target = "#genericModal"
                        hx-target="#genericModalBody"
                        hx-get ="{reverse('holiday-nav-export')}"
                        hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                        style="cursor: pointer;"
                    """,
                }
            )
        if self.request.user.has_perm("base.add_holidays"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                        onclick="bulkDeleteHoliday();"
                        data-action ="delete"
                        style="cursor: pointer; color:red !important"
                    """,
                }
            )

    nav_title = _("Public Holidays")
    filter_body_template = "cbv/holidays/holiday_filter.html"
    filter_form_context_name = "form"
    filter_instance = HolidayFilter()
    search_swap_target = "#listContainer"
    template_name = "generic/inline_nav.html"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. HolidayFilter has no FK/M2M fields, so no
    # ajax_fields are needed here.
    modern_filter = True


@method_decorator(login_required, name="dispatch")
class HolidayDetailView(HorillaDetailedView):
    """
    detail view of the page
    """

    model = Holidays
    title = _("Details")
    template_name = "holiday/holiday_detail_view.html"

    header = {"title": "name", "subtitle": "", "avatar": "get_avatar"}
    body = [
        (_("Holiday Name"), "name"),
        (_("Start Date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Recurring"), "get_recurring_status"),
        (_("Company"), "company_id"),
    ]

    action_method = "detail_view_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class HolidayExport(TemplateView):
    """
    for bulk export
    """

    template_name = "cbv/holidays/holidays_export.html"

    def get_context_data(self, **kwargs: Any):
        """
        get data for export
        """

        holiday = Holidays.objects.all()
        export_column = HolidaysColumnExportForm
        export_filter = HolidayFilter(queryset=holiday)
        context = super().get_context_data(**kwargs)
        context["export_column"] = export_column
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
class HolidayFormView(HorillaFormView):
    """
    form view for create button
    """

    form_class = HolidayForm
    model = Holidays
    new_display_title = _("Create Holiday")
    template_name = "holiday/holiday_cbv_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Holiday")

        return context

    def form_valid(self, form: HolidayForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Holiday Updated Successfully")
            else:
                message = _("New Holiday Created Successfully")
            form.save()

            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)
