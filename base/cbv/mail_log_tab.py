"""
This page is handling the cbv methods of mail log tab in employee individual page.
"""

from typing import Any

from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from accessibility.cbv_decorators import enter_if_accessible
from base.filters import MailLogFilter
from base.models import EmailLog
from employee.models import Employee
from horilla.decorators import check_manager
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import HorillaDetailedView, HorillaListView


def _can_view_mail_log(request, employee):
    """Own log, a subordinate's log, or the employee.view_employee permission."""
    viewer = request.user.employee_get
    return (
        request.user.has_perm("employee.view_employee")
        or employee == viewer
        or check_manager(viewer, employee)
    )


def _employee_for_log(log):
    if not log or not log.to:
        return None
    addresses = [a.strip().lower() for a in str(log.to).split(",") if a.strip()]
    return Employee.objects.filter(
        Q(email__in=addresses) | Q(employee_work_info__email__in=addresses)
    ).first()


@method_decorator(login_required, name="dispatch")
class MailLogTabList(HorillaListView):
    """
    list view for mail log  tab
    """

    model = EmailLog
    filter_class = MailLogFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "maillog"

        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("individual-email-log-list", kwargs={"pk": pk})

    # def get_context_data(self, **kwargs: Any):
    #     context = super().get_context_data(**kwargs)
    #     pk = self.kwargs.get('pk')
    #     context["search_url"] = f"{reverse('individual-email-log-list',kwargs={'pk': pk})}"
    #     return context

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        employee = Employee.objects.filter(id=pk).first()
        if not employee:
            messages.error(request, _("Employee not found."))
            return HorillaRedirect(request)
        if not _can_view_mail_log(request, employee):
            messages.info(request, _("You dont have access to the feature"))
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        employee = Employee.objects.get(id=pk)
        query_filter = Q(to__icontains=employee.email)
        queryset = queryset.filter(to__icontains=employee.email)
        if employee.employee_work_info and employee.employee_work_info.email:
            query_filter |= Q(to__icontains=employee.employee_work_info.email)
            queryset = queryset.filter(query_filter)
            queryset = queryset.order_by("-created_at")

        return queryset

    columns = [
        (_("Subject"), "subject"),
        (_("Date"), "created_at"),
        (_("Status"), "status_display"),
    ]

    sortby_mapping = [
        (_("Subject"), "subject"),
        (_("Date"), "created_at"),
    ]

    row_attrs = """
                hx-get='{mail_log_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
class MailLogDetailView(HorillaDetailedView):
    """
    detail view for mail log tab
    """

    template_name = "cbv/mail_log_tab/iframe.html"
    model = EmailLog

    def dispatch(self, request, *args, **kwargs):
        log = EmailLog.objects.filter(id=kwargs.get("pk")).first()
        if not _can_view_mail_log(request, _employee_for_log(log)):
            messages.info(request, _("You dont have access to the feature"))
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        log = EmailLog.objects.filter(id=pk).first()
        context["log"] = log
        return context

    header = {"title": "", "subtitle": "", "avatar": ""}
