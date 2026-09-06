from typing import Any

from django import template
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.methods import (
    filter_own_and_subordinate_recordes,
    is_reportingmanager,
    sanitize_mail_template_body,
)
from employee.models import Employee
from horilla import horilla_middlewares
from horilla.decorators import login_required, owner_can_enter, permission_required
from horilla.methods import handle_no_permission
from horilla_views.generic.cbv import views
from pms import models
from pms.filters import BonusPointSettingFilter, EmployeeBonusPointFilter
from pms.forms import (
    BonusPointSettingForm,
    BulkFeedbackForm,
    EmployeeBonusPointForm,
    EmployeeFeedbackForm,
    FeedbackForm,
)
from pms.methods import check_duplication


# ================Models for BonusPointSetting==============
@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("pms.view_bonuspointsetting"), name="dispatch")
class BonusPointSettingSectionView(views.HorillaSectionView):
    """
    BonusPointSetting SectionView
    """

    nav_url = reverse_lazy("bonus-point-setting-nav")
    view_url = reverse_lazy("bonus-point-setting-list-view")
    view_container_id = "listContainer"

    # script_static_paths = [
    #     "static/automation/automation.js",
    # ]

    template_name = "bonus/bonus_point_setting_section.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("pms.view_bonuspointsetting"), name="dispatch")
class BonusPointSettingNavView(views.HorillaNavView):
    """
    BonusPointSetting nav view
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.request.user.has_perm("pms.add_bonuspointsetting"):
            self.create_attrs = f"""
                onclick="event.stopPropagation();"
                hx-get="{reverse_lazy("create-bonus-point-setting")}"
                hx-target="#genericModalBody"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
            """

    nav_title = _("Bonus Point Settings")
    search_url = reverse_lazy("bonus-point-setting-list-view")
    search_swap_target = "#bonusPointSettingListContainer"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("pms.add_bonuspointsetting"), name="dispatch")
class BonusPointSettingFormView(views.HorillaFormView):
    """
    BonusPointSettingForm View
    """

    form_class = BonusPointSettingForm
    model = models.BonusPointSetting
    new_display_title = _("Create Bonus Point Setting")
    template_name = "bonus/bonus_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        instance = models.BonusPointSetting.objects.filter(pk=self.kwargs["pk"]).first()
        kwargs["instance"] = instance
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

    def form_invalid(self, form: Any) -> HttpResponse:

        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: BonusPointSettingForm) -> views.HttpResponse:
        if form.is_valid():
            message = "Bonus Point Setting added"
            if form.instance.pk:
                message = "Bonus Point Setting updated"
            form.save()

            messages.success(self.request, _(message))
            return self.HttpResponse()

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("pms.view_bonuspointsetting"), name="dispatch")
class BonusPointSettingListView(views.HorillaListView):
    """
    BnusPointSetting list view
    """

    model = models.BonusPointSetting
    search_url = reverse_lazy("bonus-point-setting-list-view")
    filter_class = BonusPointSettingFilter
    action_method = "action_template"

    columns = [
        ("Model", "get_model_display"),
        ("Applicable For", "get_applicable_for_display"),
        ("Bonus For", "get_bonus_for_display"),
        ("Condition", "get_condition"),
        ("Points", "points"),
        ("Is Active", "is_active_toggle"),
    ]

    header_attrs = {
        "action": """ style="width:150px !important" """,
    }


# ================Models for EmployeeBonusPoint==============


class EmployeeBonusPointSectionView(views.HorillaSectionView):
    """
    EmployeeBonusPoint SectionView
    """

    nav_url = reverse_lazy("employee-bonus-point-nav")
    view_url = reverse_lazy("employee-bonus-point-list-view")
    view_container_id = "listContainer"

    # script_static_paths = [
    #     "static/automation/automation.js",
    # ]

    template_name = "bonus/employee_bonus_point_section.html"


@method_decorator(login_required, name="dispatch")
class EmployeeBonusPointNavView(views.HorillaNavView):
    """
    BonusPoint nav view
    """

    template_name = "bonus/bonus_point_nav.html"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        request = self.request
        if request:
            if is_reportingmanager(request) or request.user.has_perm(
                "pms.add_employeebonuspoint"
            ):
                self.create_attrs = f"""
                    hx-get="{reverse_lazy("create-employee-bonus-point")}"
                    hx-target="#genericModalBody"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    """

    nav_title = _("Employee Bonus Point ")
    search_url = reverse_lazy("employee-bonus-point-list-view")
    search_swap_target = "#listContainer"
    group_by_fields = [
        ("employee_id", _("Employee")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employement Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class EmployeeBonusPointFormView(views.HorillaFormView):
    """
    BonusPointForm View
    """

    form_class = EmployeeBonusPointForm
    model = models.EmployeeBonusPoint
    new_display_title = _("Create Employee Bonus Point ")
    # template_name = "bonus/bonus_form.html"

    def dispatch(self, request, *args, **kwargs):
        perm = (
            "pms.change_employeebonuspoint"
            if kwargs.get("pk")
            else "pms.add_employeebonuspoint"
        )
        if is_reportingmanager(request) or request.user.has_perm(perm):
            return super().dispatch(request, *args, **kwargs)
        return handle_no_permission(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

    def form_invalid(self, form: Any) -> HttpResponse:

        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: EmployeeBonusPointForm) -> views.HttpResponse:
        if form.is_valid():
            message = "Bonus Point added"
            if form.instance.pk:
                message = "Bonus Point updated"
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse(
                """
                    <script>
                        $('#bonus-tab-button').click()
                    </script>
                """
            )

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class EmployeeBonusPointListView(views.HorillaListView):
    """
    BnusPoint list view
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        request = self.request
        if request:
            if is_reportingmanager(request) or request.user.has_perm(
                "pms.change_employeebonuspoint"
            ):
                self.action_method = "action_template"

    model = models.EmployeeBonusPoint
    search_url = reverse_lazy("employee-bonus-point-list-view")
    filter_class = EmployeeBonusPointFilter
    bulk_update_fields = [
        "employee_id",
        "bonus_point",
        "based_on",
    ]

    columns = [
        ("Employee", "employee_id"),
        ("Bonus Point", "bonus_point"),
        ("Based On", "based_on"),
    ]

    header_attrs = {
        "action": 'style="width: 110px;"',
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if is_reportingmanager(request) or request.user.has_perm(
            "pms.view_employeebonuspoint"
        ):
            return filter_own_and_subordinate_recordes(
                request, queryset, perm="pms.view_employeebonuspoint"
            )
        else:
            return queryset.filter(employee_id=request.user.employee_get)


####################### Feedback ########################################


@method_decorator(login_required, name="dispatch")
class FeedbackEmployeeFormView(views.HorillaFormView):
    """
    Feedback other employee form View
    """

    form_class = EmployeeFeedbackForm
    model = models.Feedback
    new_display_title = _("Share Feedback request ")
    # template_name = "bonus/bonus_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: EmployeeFeedbackForm) -> views.HttpResponse:
        if form.is_valid():
            message = "Feedback request sent."
            other_employees = check_duplication(
                form.instance, form.cleaned_data.get("others_id", [])
            )
            form.cleaned_data["others_id"] = other_employees
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse("<script>window.location.reload()</script>")
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("pms.add_feedback"), name="dispatch")
class BulkFeedbackFormView(views.HorillaFormView):
    """
    Feedback other employee form View
    """

    form_class = BulkFeedbackForm
    model = models.Feedback
    view_id = "BulkFeedbackForm"
    new_display_title = _("Bulk Feedback request ")
    template_name = "feedback/bulk_feedback_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hints = {
            "Employee|Full name": "employee.get_full_name",
            "Employee|Email": "employee.get_mail",
            "Employee|Employee Type": "employee.get_employee_type",
            "Employee|Work Type": "employee.get_work_type",
            "Employee|Company": "employee.get_company",
            "Employee|Job position": "employee.get_job_position",
        }
        context["hints"] = hints
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: BulkFeedbackForm) -> views.HttpResponse:
        if form.is_valid():
            message = "Bulk Feedback request sent."
            cleaned_data = form.cleaned_data
            employees = cleaned_data["employee_ids"]
            for employee in employees:
                reporting_manager = employee.get_reporting_manager()
                manager_id = (
                    reporting_manager if cleaned_data["include_manager"] else None
                )
                title_template = cleaned_data["title"]
                temp = template.Template(sanitize_mail_template_body(title_template))
                title_context = template.Context({"employee": employee})
                render_title = temp.render(title_context)
                data = {
                    "review_cycle": render_title,
                    "employee_id": employee,
                    "manager_id": manager_id,
                    "question_template_id": cleaned_data["question_template_id"],
                    "start_date": cleaned_data["start_date"],
                    "end_date": cleaned_data["end_date"],
                    "cyclic_feedback": cleaned_data["cyclic_feedback"],
                    "cyclic_feedback_days_count": cleaned_data[
                        "cyclic_feedback_days_count"
                    ],
                    "cyclic_feedback_period": cleaned_data["cyclic_feedback_period"],
                    "status": cleaned_data["status"],
                }
                feedback_form = FeedbackForm(data)
                if feedback_form.is_valid():
                    feedback = feedback_form.save()
                    if cleaned_data["include_keyresult"]:
                        keyresults = models.EmployeeKeyResult.objects.filter(
                            employee_objective_id__employee_id=employee.id
                        )
                        feedback.employee_key_results_id.add(*keyresults)
                    if cleaned_data["include_colleagues"]:
                        department = employee.get_department()
                        # employee ids to exclude from collegue list
                        exclude_ids = [employee.id]
                        if reporting_manager:
                            exclude_ids.append(reporting_manager.id)
                        # Get employees in the same department as the employee
                        colleagues = Employee.objects.filter(
                            is_active=True, employee_work_info__department_id=department
                        ).exclude(id__in=exclude_ids)
                        feedback.colleague_id.add(*colleagues)

                    if cleaned_data["include_subordinates"]:
                        subordinates = Employee.objects.filter(
                            is_active=True,
                            employee_work_info__reporting_manager_id=employee,
                        )
                        feedback.subordinate_id.add(*subordinates)
                    other_employees = check_duplication(
                        feedback, cleaned_data["other_employees"]
                    )
                    feedback.others_id.add(*other_employees)
            messages.success(self.request, _(message))
            return self.HttpResponse("<script>window.location.reload()</script>")
        return super().form_valid(form)
