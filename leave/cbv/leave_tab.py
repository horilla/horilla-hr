"""
This page is handling the cbv methods of leave tab in employee profile page.
"""

from typing import Any

from django.http import HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.methods import is_reportingmanager
from employee.models import Employee
from leave.cbv.my_leave_request import MainParentListView, MyLeaveRequestListView


class IndividualLeaveTab(MainParentListView):
    """
    class for rendering leave tab in employee profile
    """

    template_name = "cbv/employee_individual/leave_tab.html"

    def dispatch(self, request, *args, **kwargs):
        if not Employee.objects.filter(id=kwargs.get("pk")).exists():
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any):
        """
        context data
        """
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        employee = Employee.objects.get(id=pk)
        user_leave = employee.available_leave.all()

        if self.request.user.employee_get == employee:
            context["user_leaves"] = user_leave
        else:
            context["employee_leaves"] = user_leave
        return context

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset

    def get_template_names(self):
        """
        template_name renders the leave-type summary cards above the
        paginated request list. Pagination/sort/filter links inside that
        list target "#leave-tab" (view_id) directly with hx-swap="outerHTML",
        expecting back just the list+pagination fragment. Returning the full
        template for those requests re-renders a second, nested copy of the
        summary cards on every "next page"/sort/filter click, since the
        original cards - siblings outside the swapped div - are never
        removed. Only the tab's initial load (targeted at the profile page's
        own generic tab container, not "#leave-tab") needs the full template.
        """
        if self.request.META.get("HTTP_HX_TARGET") == self.view_id:
            return ["generic/horilla_list_table.html"]
        return [self.template_name]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "leave-tab"
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("individual-leave-tab-list", kwargs={"pk": pk})
        if self.request.user.has_perm(
            "leave.change_leaverequest"
        ) or is_reportingmanager(self.request):
            self.action_method = "confirmation_col"
        else:
            self.action_method = None

    columns = [
        col for col in MyLeaveRequestListView.columns if col[1] != "comment_action"
    ]

    # option_method = None
    # row_status_indications = None
