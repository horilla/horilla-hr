"""
Restricted page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from leave.filters import RestrictLeaveFilter
from leave.forms import RestrictLeaveForm
from leave.models import RestrictLeave


@method_decorator(login_required, name="dispatch")
class RestrictedDaysView(TemplateView):
    """
    Standalone Restricted Leave Periods page.
    """

    template_name = "cbv/restricted_days/restricted_days.html"


@method_decorator(login_required, name="dispatch")
class RestrictedDaysList(HorillaListView):
    """
    List view of the resticted days page
    """

    bulk_update_fields = ["department", "job_position"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.search_url = reverse("restrict-filter")
        if self.request.user.has_perm("leave.add_restrictleave"):
            self.action_method = "actions_col"
        self.view_id = "restrictday"

    model = RestrictLeave
    filter_class = RestrictLeaveFilter

    columns = [
        (_("Title"), "title"),
        (_("Start Date"), "start_date"),
        (_("End date"), "end_date"),
        (_("Department"), "department"),
        (_("Job Position"), "job_position_col"),
        (_("Description"), "description"),
    ]

    header_attrs = {
        "title": """ style="width:180px !important" """,
        "action": """ style="width:150px !important" """,
    }

    sortby_mapping = [
        (_("Start Date"), "start_date"),
        (_("End date"), "end_date"),
        (_("Department"), "department__department"),
        (_("Job Position"), "job_position_col"),
    ]

    row_attrs = """
        hx-get='{restricted_days_detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
class RestrictedDaysNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("restrict-filter")
        if self.request.user.has_perm("leave.add_restrictleave"):
            self.create_attrs = f"""
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('restrict-creation')}"
            """
            self.actions = [
                {
                    "action": _("Delete"),
                    "attrs": """
                        onclick="bulkRestrictedDaysDelete();"
                        data-action ="delete"
                        style="cursor: pointer; color:red !important"
                    """,
                }
            ]

    nav_title = _("Restricted Leave Periods")
    filter_instance = RestrictLeaveFilter()
    filter_body_template = "cbv/restricted_days/filter.html"
    search_swap_target = "#restrictLeavesListContainer"
    filter_form_context_name = "form"
    template_name = "generic/inline_nav.html"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. RestrictLeaveFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("leave.add_restrictleave"), name="dispatch")
class RestrictedDaysFormView(HorillaFormView):
    """
    Create and edit form
    """

    model = RestrictLeave
    form_class = RestrictLeaveForm
    new_display_title = _("Create Restricted Day")
    template_name = "cbv/restricted_days/restrict_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Restricted Day")
        return context

    def form_valid(self, form: RestrictLeaveForm) -> HttpResponse:

        if form.is_valid():
            if form.instance.pk:
                message = _("Restricted Day Updated Successfully")
            else:
                message = _("Restricted Day Created Successfully")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class RestrictedDaysDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Start Date"), "start_date"),
            (_("End date"), "end_date"),
            (_("Department"), "department"),
            (_("Job Position"), "job_position_col"),
            (_("Description"), "description"),
        ]

    action_method = "detail_action"
    cols = {
        "description": 12,
    }

    model = RestrictLeave
    title = _("Details")
    header = {
        "title": "title",
        "subtitle": "",
        "avatar": "get_avatar",
    }
