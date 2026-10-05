"""
This page handles the cbv methods of employee individual view
"""

from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from base import views as base_views
from base.cbv.mail_log_tab import MailLogTabList
from base.cbv.work_shift_tab import WorkAndShiftTabView
from base.context_processors import enable_profile_edit
from base.forms import AddToUserGroupForm
from employee import views
from employee.cbv.document_request import DocumentIndividualTabShell
from employee.filters import EmployeeFilter
from employee.history import get_employee_history_models, get_employee_model_history
from employee.models import Employee
from horilla import settings
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import HorillaDetailedView, HorillaProfileView

Employee.cbv_employee_profile_edi_url = reverse_lazy("edit-profile")


@method_decorator(login_required, name="dispatch")
class EmployeeProfileView(HorillaProfileView):
    """
    EmployeeProfileView
    """

    template_name = "cbv/profile/profile_view.html"

    model = Employee
    filter_class = EmployeeFilter
    push_url = "employee-view-individual"
    key_name = "obj_id"

    def get_queryset(self):
        return Employee.objects.entire()

    def dispatch(self, request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("login")

        obj_id = kwargs.get("pk")
        if not Employee.objects.entire().filter(id=obj_id).exists():
            return HorillaRedirect(
                request, message=_("No employee found matching the query.")
            )

        employee = request.user.employee_get

        if request.user.has_perm("employee.change_employee"):
            self.actions = [
                {
                    "title": _("Edit"),
                    "src": f"/{settings.STATIC_URL}images/ui/editing.png",
                    "accessibility": "employee.cbv.accessibility.edit_accessibility",
                    "attrs": """
                        href="#"
                        hx-get="{get_update_url}?container=true"
                        hx-target="#listContainer"
                        hx-swap="innerHTML"
                        hx-push-url="{get_update_url}?container=true"
                        onclick="if (!document.getElementById('listContainer')) {{ event.preventDefault(); event.stopPropagation(); window.location.href = this.getAttribute('hx-get'); return false; }}"
                    """,
                },
                {
                    "divider": True,
                },
                {
                    "title": _("Send password reset link"),
                    "src": f"/{settings.STATIC_URL}images/ui/key.png",
                    "accessibility": "employee.cbv.accessibility.password_reset_accessibility",
                    "attrs": """onclick="$('#reset-button').click();" """,
                },
                {
                    "divider": True,
                },
                {
                    "title": _("Block Account"),
                    "src": f"/{settings.STATIC_URL}images/ui/block-user.png",
                    "accessibility": "employee.cbv.accessibility.block_account_accessibility",
                    "attrs": """id="block-account" """,
                    "variant": "danger",
                },
                {
                    "title": _("Un-Block Account"),
                    "src": f"/{settings.STATIC_URL}images/ui/unlock.png",
                    "accessibility": "employee.cbv.accessibility.un_block_account_accessibility",
                    "attrs": """id="block-account" """,
                    "variant": "success",
                },
            ]
        elif employee.pk == kwargs.get("pk") and not enable_profile_edit(request).get(
            "profile_edit_enabled"
        ):
            self.actions = [
                {
                    "title": _("Edit Profile"),
                    "src": f"/{settings.STATIC_URL}images/ui/editing.png",
                    "accessibility": "employee.cbv.accessibility.edit_accessibility",
                    "attrs": """onclick="window.location.href='{cbv_employee_profile_edi_url}'" """,
                },
                {
                    "title": _("Send password reset link"),
                    "src": f"/{settings.STATIC_URL}images/ui/key.png",
                    "accessibility": "employee.cbv.accessibility.password_reset_accessibility",
                    "attrs": """onclick="$('#reset-button').click();" """,
                },
            ]

        return super().dispatch(request, *args, **kwargs)


class UserProfileView(EmployeeProfileView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["instance_ids"] = None
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="employee.view_employee"), name="dispatch")
class EmployeeRelatedDetailView(HorillaDetailedView):
    """
    Concise employee summary opened via related-object navigation (e.g. from
    a leave request/allocation detail view), instead of the full profile page.
    """

    model = Employee
    detail_view_url_name = "employee-related-detail-view"
    detail_view_permission = "employee.view_employee"
    title = _("Employee")
    header = {
        "title": "get_full_name",
        "subtitle": "get_job_position",
        "avatar": "get_avatar",
    }
    body = [
        (_("Employee ID"), "badge_id"),
        (_("Job Position"), "get_job_position"),
        (_("Department"), "get_department"),
        (_("Company"), "employee_work_info__company_id"),
        (_("Work Location"), "employee_work_info__location"),
        (_("Work Type"), "get_work_type"),
        (_("Shift"), "get_shift"),
        (_("Reporting Manager"), "get_reporting_manager"),
        (_("Employment Type"), "get_employee_type"),
        (_("Email"), "get_email"),
        (_("Date of Joining"), "employee_work_info__date_joining"),
        (_("Status"), "get_active_status"),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["instance_ids"] = None
        return context


@method_decorator(login_required, name="dispatch")
class EmployeeHistoryTabView(TemplateView):
    """
    Lets the viewer pick which of the employee's linked models to show
    history for, filtered and sorted by date.
    """

    template_name = "tabs/history.html"
    default_model = "employee.employeeworkinformation"

    def _parse_date(self, value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = Employee.objects.get(id=self.kwargs.get("pk"))
        model_options = get_employee_history_models()

        selected_model = self.request.GET.get("model") or self.default_model
        if selected_model not in {m["key"] for m in model_options}:
            selected_model = self.default_model

        date_from = self._parse_date(self.request.GET.get("date_from"))
        date_to = self._parse_date(self.request.GET.get("date_to"))
        sort = self.request.GET.get("sort") or "-date"
        if sort not in {"date", "-date"}:
            sort = "-date"

        entries, tracking_status = get_employee_model_history(
            employee,
            selected_model,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
        )

        context.update(
            {
                "employee": employee,
                "model_options": model_options,
                "selected_model": selected_model,
                "date_from": date_from,
                "date_to": date_to,
                "sort": sort,
                "entries": entries,
                "tracking_status": tracking_status,
            }
        )
        return context


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("About"),
            "view": views.about_tab,
        },
        {
            "title": _("Work Type & Shift"),
            # "view": views.shift_tab,
            "view": WorkAndShiftTabView.as_view(),
            "accessibility": "employee.cbv.accessibility.workshift_accessibility",
        },
        {
            "title": _("Groups & Permissions"),
            "view": base_views.employee_permission_assign,
            "accessibility": "employee.cbv.accessibility.permission_accessibility",
        },
        {
            "title": _("Note"),
            "view": views.note_tab,
            "accessibility": "employee.cbv.accessibility.note_accessibility",
        },
        {
            "title": _("Documents"),
            "view": DocumentIndividualTabShell.as_view(),
            "accessibility": "employee.cbv.accessibility.document_accessibility",
        },
        {
            "title": _("Mail Log"),
            "view": MailLogTabList.as_view(),
            "accessibility": "employee.cbv.accessibility.mail_log_accessibility",
        },
        {
            "title": _("History"),
            "view": EmployeeHistoryTabView.as_view(),
            "accessibility": "employee.cbv.accessibility.history_accessibility",
        },
    ]
)


@method_decorator([login_required], name="dispatch")
class GroupAssignView(View):
    """
    View to assign multiple groups to a single employee.
    Allowed for superadmin or the employee's reporting manager.
    """

    def _allowed(self, request, employee):
        from employee.cbv.accessibility import can_edit_employee_permissions

        return can_edit_employee_permissions(request, employee)

    def get(self, request, *args, **kwargs):
        from horilla.methods import handle_no_permission

        employee_id = request.GET.get("employee")
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return HorillaRedirect(
                request, message=_("No Employee found matching the query.")
            )
        if not self._allowed(request, employee):
            return handle_no_permission(request)
        groups = employee.employee_user_id.groups.all
        form = AddToUserGroupForm(
            initial={
                "group": groups,
                "employee": request.GET.get("employee"),
            }
        )
        return render(
            request,
            "cbv/auth/user_assign_to_group.html",
            {"form": form, "employee_id": request.GET.get("employee")},
        )

    def post(self, request, *args, **kwargs):
        from horilla.methods import handle_no_permission

        form = AddToUserGroupForm(request.POST)
        employee_id = request.POST.get("employee")
        employee = Employee.objects.filter(id=employee_id).first()
        if not employee or not self._allowed(request, employee):
            return handle_no_permission(request)
        if form.is_valid():
            form.save()
            messages.success(request, _("Employee assigned to group"))
            return HorillaRedirect(request)
        return render(
            request,
            "cbv/auth/user_assign_to_group.html",
            {"form": form, "employee_id": request.POST.get("employee")},
        )
