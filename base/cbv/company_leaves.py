"""
this page is handling the cbv methods of company leaves page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import CompanyLeaveFilter
from base.forms import CompanyLeaveForm
from base.models import CompanyLeaves
from horilla_views.cbv_methods import (
    AddOrChangePermissionMixin,
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
class CompanyLeavesView(TemplateView):
    """
    Standalone Weekly Off Days page. For admins it has been migrated into
    Settings > Organization, so users with the manage permission are redirected
    there; employees without the permission keep the read-only list view.
    """

    template_name = "cbv/company_leaves/company_leave_home.html"

    def get(self, request, *args, **kwargs):
        if request.user.has_perm("base.view_companyleaves"):
            return redirect("company-leaves-view")
        return super().get(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class CompanyleaveListView(HorillaListView):
    """
    list view
    """

    filter_class = CompanyLeaveFilter
    model = CompanyLeaves

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("company-leave-filter")
        self.view_id = "companyleavedelete"

        if self.request.user.has_perm("base.view_companyleaves"):
            self.action_method = "company_leave_actions"

        if self.request.user.has_perm("base.view_company"):
            if (_("Company"), "get_company_display") not in self.columns:
                self.columns.append((_("Company"), "get_company_display"))

    columns = [
        (_("Based On Week"), "custom_based_on_week"),
        (_("Based On Week Day"), "based_on_week_day_col"),
    ]

    header_attrs = {
        "action": """ style="width:200px !important;" """,
    }

    sortby_mapping = [
        ("Based On Week", "custom_based_on_week"),
        ("Based On Week Day", "based_on_week_day_col"),
    ]

    row_attrs = """
        hx-get='{detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
class CompanyLeaveNavView(HorillaNavView):
    """
    nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("company-leave-filter")
        if self.request.user.has_perm("base.add_companyleaves"):
            self.create_attrs = f"""
                hx-get="{reverse_lazy('company-leave-creation')}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """

    nav_title = _("Weekly Off Days")
    filter_body_template = "cbv/company_leaves/company_leave_filter.html"
    filter_form_context_name = "form"
    filter_instance = CompanyLeaveFilter()
    search_swap_target = "#listContainer"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
class CompanyLeaveDetailView(HorillaDetailedView):
    """
    detail view of the page
    """

    model = CompanyLeaves
    title = _("Details")
    header = {"title": "get_detail_title", "subtitle": "", "avatar": "get_avatar"}
    body = [
        (_("Based On Week"), "custom_based_on_week"),
        (_("Based On Week Day"), "based_on_week_day_col"),
        (_("Company"), "get_company_display"),
    ]
    action_method = "detail_view_actions"


@method_decorator(login_required, name="dispatch")
class CompanyleaveFormView(AddOrChangePermissionMixin, HorillaFormView):
    """
    form view for create button
    """

    add_perm = "base.add_companyleaves"
    change_perm = "base.change_companyleaves"
    form_class = CompanyLeaveForm
    model = CompanyLeaves
    new_display_title = _("Create Weekly Off Days")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Weekly Off Days")

        return context

    def form_valid(self, form: CompanyLeaveForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Weekly Off Day Updated Successfully")
            else:
                message = _("New Weekly Off Day Created Successfully")
            form.save()

            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)
