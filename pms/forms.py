"""
forms.py

This module is used to register the forms for pms models
"""

import datetime
import uuid
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.db.models.base import Model
from django.forms import ModelForm
from django.forms.utils import ErrorList
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm as BaseForm
from base.forms import ModelForm as HorillaModelForm
from base.methods import (
    filtersubordinatesemployeemodel,
    is_reportingmanager,
    reload_queryset,
)
from base.models import Company
from employee.filters import EmployeeFilter
from horilla import horilla_middlewares
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from pms.models import (
    AnonymousFeedback,
    BonusPointSetting,
    Comment,
    Employee,
    EmployeeBonusPoint,
    EmployeeKeyResult,
    EmployeeObjective,
    Feedback,
    KeyResult,
    Meetings,
    Objective,
    Period,
    Question,
    QuestionOptions,
    QuestionTemplate,
)


def validate_date(start_date, end_date):
    """
    Validates that the start date is before or equal to the end date.
    """
    if start_date and end_date and start_date > end_date:
        raise forms.ValidationError(_("The start date must be before the end date."))


def set_date_field_initial(instance):
    """this is used to update change the date value format"""
    initial = {}
    if instance.start_date is not None:
        initial["start_date"] = instance.start_date.strftime("%Y-%m-%d")
    if instance.end_date is not None:
        initial["end_date"] = instance.end_date.strftime("%Y-%m-%d")
    return initial


class ObjectiveForm(BaseForm):
    """
    A form to create or update instances of the Objective, model.
    """

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "oh-input w-100", "type": "date"}),
    )
    add_assignees = forms.BooleanField(required=False)
    archive = forms.BooleanField(required=False)
    key_result_id = forms.ModelMultipleChoiceField(
        queryset=KeyResult.objects.all().exclude(archive=True),
        label=_("Key result"),
        widget=forms.SelectMultiple(
            attrs={
                "class": "oh-select oh-select-2 select2-hidden-accessible",
                "onchange": "keyResultChange($(this))",
            }
        ),
    )

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = Objective
        fields = [
            "title",
            "managers",
            "duration_unit",
            "duration",
            "key_result_id",
            "description",
            "add_assignees",
            "assignees",
            "start_date",
            "archive",
            "self_employee_progress_update",
        ]
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        """
        Constructor for ObjectiveForm. If an instance is provided, set initial values for date fields
        """

        employee = kwargs.pop(
            "employee", None
        )  # access the logged-in user's information
        super().__init__(*args, **kwargs)
        self.fields["assignees"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                required=False,
                instance=self.instance,
            ),
            label="Assignees",
        )

        self.fields["managers"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                required=False,
                instance=self.instance,
            ),
            label="Managers",
        )

        reload_queryset(self.fields)
        self.fields["key_result_id"].choices = list(
            self.fields["key_result_id"].choices
        )
        self.fields["key_result_id"].choices.append(
            ("create_new_key_result", "Create new Key result")
        )

    def clean(self):
        """
        Validates form fields and raises a validation error if any fields are invalid
        """
        cleaned_data = super().clean()
        add_assignees = cleaned_data.get("add_assignees")
        for field_name, field_instance in self.fields.items():
            if isinstance(field_instance, HorillaMultiSelectField):
                self.errors.pop(field_name, None)
                if (
                    add_assignees
                    and len(self.data.getlist(field_name)) < 1
                    and add_assignees
                ):
                    raise forms.ValidationError({field_name: "This field is required"})
                cleaned_data = super().clean()
                data = self.fields[field_name].queryset.filter(
                    id__in=self.data.getlist(field_name)
                )
                cleaned_data[field_name] = data
        cleaned_data = super().clean()
        add_assignees = cleaned_data.get("add_assignees")
        assignees = cleaned_data.get("assignees")
        start_date = cleaned_data.get("start_date")
        managers = cleaned_data.get("managers")
        if not managers or managers == None:
            raise forms.ValidationError(_("Managers is a required field"))
        if add_assignees:
            if not assignees.exists() or start_date is None:
                raise forms.ValidationError(_("Assign employees and start date"))
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        # Check that start date is before end date
        validate_date(start_date, end_date)
        return cleaned_data

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class AddAssigneesForm(BaseForm):
    """
    A form to create or update instances of the EmployeeObjective, model.
    """

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "oh-input w-100", "type": "date"}),
    )

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = Objective
        fields = [
            "assignees",
        ]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["assignees"].queryset = self.fields[
                "assignees"
            ].queryset.exclude(id__in=self.instance.assignees.all())

    def clean(self):
        cleaned_data = super().clean()
        assignees = cleaned_data.get("assignees")
        if len(assignees) == 0:
            raise forms.ValidationError({"assignees": _("This field is required.")})
        return cleaned_data


class EmployeeObjectiveForm(BaseForm):
    """
    A form to create or update instances of the EmployeeObjective, model.
    """

    key_result_id = forms.ModelChoiceField(
        queryset=KeyResult.objects.all(),
        label=_("Key result"),
        widget=forms.Select(
            attrs={
                "class": "oh-select oh-select-2 select2-hidden-accessible",
                "onchange": "keyResultChange($(this))",
            }
        ),
    )

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = EmployeeObjective
        fields = [
            "objective_id",
            "start_date",
            "end_date",
            "status",
            "archive",
        ]
        exclude = ["is_active"]
        widgets = {
            "objective_id": forms.HiddenInput(),
            "start_date": forms.DateInput(
                attrs={"class": "oh-input w-100", "type": "date"}
            ),
            "end_date": forms.DateInput(
                attrs={"class": "oh-input w-100", "type": "date"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        try:
            del self.fields["key_result_id"]
        except Exception as _err:
            pass

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class EmployeeObjectiveCreateForm(BaseForm):
    """
    A form to create or update instances of the EmployeeObjective, model.
    """

    key_result_id = forms.ModelMultipleChoiceField(
        queryset=KeyResult.objects.all().exclude(archive=True),
        label=_("Key result"),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "oh-select oh-select-2 select2-hidden-accessible",
                "onchange": "keyResultChange($(this))",
            }
        ),
    )
    objective_id = forms.ModelChoiceField(
        queryset=Objective.objects.all()
        .exclude(archive=True)
        .exclude(is_template=True),
        required=True,
        label=_("Objective"),
        widget=forms.Select(
            attrs={
                "hx-include": "#empObjectiveCreateForm",
                "hx-target": "#id_key_result_id_parent_div",
                "hx-select": "#id_key_result_id_parent_div",
                "hx-swap": "outerHTML",
                "hx-trigger": "change",
                "hx-get": "/pms/get-objective-keyresult",
            }
        ),
    )

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = EmployeeObjective
        fields = [
            "employee_id",
            "objective_id",
            "key_result_id",
            "start_date",
            "status",
            "archive",
        ]
        widgets = {
            "start_date": forms.DateInput(
                attrs={"class": "oh-input w-100", "type": "date"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(horilla_middlewares._thread_locals, "request", None)

        if request.user.has_perm("pms.add_keyresult"):
            self.fields["key_result_id"].choices = list(
                self.fields["key_result_id"].choices
            )
            self.fields["key_result_id"].choices.append(
                ("create_new_key_result", "Create new Key result")
            )
        if request.user.has_perm("pms.add_employeeobjective") or is_reportingmanager(
            request
        ):
            employees = filtersubordinatesemployeemodel(
                request,
                queryset=Employee.objects.filter(is_active=True),
                perm="pms.add_employeeobjective",
            )
            self.fields["employee_id"].queryset = employees | Employee.objects.filter(
                employee_user_id=request.user
            )
        else:
            self.fields["employee_id"].queryset = Employee.objects.filter(
                employee_user_id=request.user
            )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class EmployeeKeyResultForm(BaseForm):
    """
    A form to create or update instances of the EmployeeKeyResult, model.
    """

    key_result_id = forms.ModelChoiceField(
        queryset=KeyResult.objects.all().exclude(archive=True),
        label=_("Key result"),
        widget=forms.Select(
            attrs={
                "class": "oh-select oh-select-2 select2-hidden-accessible",
                "onchange": "keyResultChange($(this))",
            }
        ),
    )

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = EmployeeKeyResult
        fields = [
            "employee_objective_id",
            "key_result_id",
            "start_value",
            "current_value",
            "target_value",
            "start_date",
            "end_date",
        ]
        widgets = {
            "employee_objective_id": forms.HiddenInput(),
            "start_date": forms.DateInput(
                attrs={
                    "class": "oh-input w-100",
                    "type": "date",
                    "required": True,
                    "onchange": "startDateChange()",
                }
            ),
            "end_date": forms.DateInput(
                attrs={"class": "oh-input w-100", "type": "date"}
            ),
        }

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if self.initial.get("employee_objective_id"):
            if (
                type(self.initial.get("employee_objective_id")) is int
                or type(self.initial.get("employee_objective_id")) is str
            ):
                self.verbose_name = str(
                    EmployeeObjective.objects.get(
                        id=int(self.initial.get("employee_objective_id"))
                    ).employee_id
                )
            else:
                self.verbose_name = str(
                    self.initial.get("employee_objective_id").employee_id
                )
        if request.user.has_perm("pms.add_keyresult") or is_reportingmanager(request):
            self.fields["key_result_id"].choices = list(
                self.fields["key_result_id"].choices
            )
            self.fields["key_result_id"].choices.append(
                ("create_new_key_result", "Create new Key result")
            )


class KRForm(HorillaModelForm):
    """
    A form used for creating KeyResult object
    """

    class Meta:
        """
        A nested class that specifies the model,fields and exclude fields for the form.
        """

        model = KeyResult
        fields = [
            "title",
            "description",
            "progress_type",
            "target_value",
            "duration",
            "company_id",
        ]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()
        duration = cleaned_data.get("duration")
        target_value = cleaned_data.get("target_value")
        progress_type = cleaned_data.get("progress_type")

        if duration is None or duration == "":
            raise ValidationError({"duration": "This field is required"})
        if target_value is None or target_value == "":
            raise ValidationError({"target_value": "This field is required"})
        if duration <= 0:
            raise ValidationError(
                {"duration": "Duration cannot be less than or equal to zero"}
            )
        if target_value <= 0:
            raise ValidationError(
                {"target_value": "Duration cannot be less than or equal to zero"}
            )
        if progress_type == "%" and target_value > 100:
            raise ValidationError(
                {
                    "target_value": 'Target value cannot be greater than hundred for progress type "percentage"'
                }
            )


class KeyResultForm(ModelForm):
    """
    A form used for creating and updating EmployeeKeyResult objects.

    Includes fields for title, description, current value, target value,
    start date, end date, progress type, and the associated period and employee.

    Excludes fields for status, progress_boolean, progress_integer,
    employee_objective_id, and start value.

    """

    period = forms.ModelChoiceField(
        queryset=Period.objects.all(),
        empty_label="",
        widget=forms.Select(attrs={"style": "width:100%; display:none;"}),
        required=False,
    )

    class Meta:
        """
        A nested class that specifies the model,fields and exclude fields for the form.
        """

        model = EmployeeKeyResult
        fields = "__all__"
        exclude = [
            "status",
            "progress_boolean",
            "progress_integer",
            "employee_objective_id",
            "start_value",
        ]

        widgets = {
            "key_result": forms.TextInput(
                attrs={
                    "placeholder": _("Enter a title"),
                    "class": "oh-input w-100",
                    "required": True,
                }
            ),
            "key_result_description": forms.Textarea(
                attrs={
                    "placeholder": _("Enter a description"),
                    "class": "oh-input oh-input--textarea w-100",
                    "required": True,
                    "rows": 3,
                    "cols": 40,
                }
            ),
            "employee_id": forms.Select(
                attrs={
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                    "style": "display:none;",
                }
            ),
            "current_value": forms.NumberInput(
                attrs={"class": "oh-input w-100", "required": True}
            ),
            "target_value": forms.NumberInput(
                attrs={"class": "oh-input w-100", "required": True}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100", "required": True}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100", "required": True}
            ),
            "progress_type": forms.Select(
                attrs={
                    "class": "oh-select oh-select--lg oh-select-no-search w-100",
                    "required": True,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        if instance:
            kwargs["initial"] = set_date_field_initial(instance)
        employee = kwargs.pop(
            "employee", None
        )  # access the logged-in user's information
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        employees = Employee.objects.filter(
            is_active=True, employee_work_info__reporting_manager_id=employee
        )
        if employee and employees:
            # manager level access
            self.fields["employee_id"].queryset = employees

        # Set unique IDs for employee_id fields to prevent conflicts with other forms on the same page
        self.fields["employee_id"].widget.attrs.update({"id": str(uuid.uuid4())})

    def clean_value(self, value_type):
        """
        Validate the 'current_value' and 'target_value' field of model EmployeeKeyResult.
        """
        value = self.cleaned_data.get(value_type)
        other_value = self.cleaned_data.get(
            "current_value" if value_type == "target_value" else "target_value"
        )
        if (
            value is not None
            and other_value is not None
            and value_type == "current_value"
            and value > other_value
        ):
            raise forms.ValidationError(
                _("Current value cannot be greater than target value")
            )
        elif (
            value is not None
            and other_value is not None
            and value_type == "target_value"
            and value < other_value
        ):
            raise forms.ValidationError(
                _("Target value cannot be less than current value")
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        employee_objective_id = self.initial.get("employee_objective_id")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        target_value = cleaned_data.get("target_value")
        current_value = cleaned_data.get("current_value")

        validate_date(start_date, end_date)
        # date comparing with objective start and end date
        if employee_objective_id and start_date and end_date:
            if start_date < employee_objective_id.start_date:
                raise ValidationError(
                    _("Start date should be after Objective start date")
                )

            if end_date > employee_objective_id.end_date:
                raise ValidationError(_("End date should be below Objective end date"))
        else:
            raise forms.ValidationError(_("Employee Objective not found"))
        # target value and current value comparison
        if target_value <= 0:
            raise ValidationError(_("Target value should be greater than zero"))
        if current_value > target_value:
            raise forms.ValidationError(
                _("Current value cannot be greater than target value")
            )
        return cleaned_data


class FeedbackForm(HorillaModelForm):
    """
    FeedbackForm for better performance.
    """

    period = forms.ModelChoiceField(
        queryset=Period.objects.none(),
        label=_("Period"),
        empty_label="",
        widget=forms.Select(attrs={"class": "oh-select--period-change"}),
        required=False,
    )

    class Meta:
        model = Feedback
        fields = [
            "review_cycle",
            "employee_id",
            "manager_id",
            "subordinate_id",
            "colleague_id",
            "start_date",
            "end_date",
            "question_template_id",
            "employee_key_results_id",
            "cyclic_feedback",
            "cyclic_feedback_days_count",
            "cyclic_feedback_period",
        ]
        # fields = "__all__"
        exclude = [
            "status",
            "archive",
            "is_active",
            "cyclic_next_start_date",
            "cyclic_next_end_date",
        ]

        labels = {
            "manager_id": _("Manager"),
            "employee_id": _("Employee"),
            "colleague_id": _("Colleague"),
            "question_template_id": _("Question Template"),
            "employee_key_results_id": _("Key Result"),
            "cyclic_feedback": _("Is Cyclic Feedback"),
            # "cyclic_feedback_period":_("")
        }

        widgets = {
            "employee_key_results_id": forms.SelectMultiple(
                attrs={
                    "class": "oh-select oh-select-2 w-100",
                    "multiple": "multiple",
                    "style": "width:100%; display:none;",
                    "required": False,
                }
            ),
            "review_cycle": forms.TextInput(
                attrs={"placeholder": _("Enter a title"), "class": "oh-input w-100"}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "cyclic_feedback": forms.CheckboxInput(
                attrs={
                    "class": "oh-switch__checkbox",
                    "onchange": "changeCyclicFeedback(this)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the form and queryset filtering.
        """
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        super().__init__(*args, **kwargs)
        # if instance:
        #     kwargs["initial"] = set_date_field_initial(instance)

        user = request.user if request else None
        user_perms = user.get_all_permissions() if user else set()

        self.fields["period"].queryset = Period.objects.all()
        self.fields["period"].widget.attrs.update({"class": "w-100"})

        if user and ("pms.add_period" in user_perms or is_reportingmanager(request)):
            self.fields["period"].choices = [
                *self.fields["period"].choices,
                ("create_new_period", "Create new period"),
            ]

        employee_queryset = Employee.objects.none()
        if user and ("pms.add_feedback" in user_perms or is_reportingmanager(request)):
            employee_queryset = filtersubordinatesemployeemodel(
                request,
                Employee.objects.all(),
                perm="pms.add_feedback",
            )

        self.fields["employee_id"].queryset = (
            employee_queryset | Employee.objects.filter(employee_user_id=request.user)
        )
        self.fields["employee_id"].widget.attrs["onchange"] = "get_collegues($(this))"

        reload_queryset(self.fields)
        selected_employee_id = self.data.get("employee_id") if self.data else None
        if not selected_employee_id and self.instance and self.instance.pk:
            selected_employee_id = self.instance.employee_id_id

        self.fields["employee_key_results_id"].queryset = (
            EmployeeKeyResult.objects.filter(
                employee_objective_id__employee_id=selected_employee_id
            )
            if selected_employee_id
            else EmployeeKeyResult.objects.none()
        )

        if self.instance and self.instance.pk:
            employee = self.instance.employee_id
            reporting_manager = (
                getattr(employee.employee_work_info, "reporting_manager_id", None)
                if employee
                and hasattr(employee, "employee_work_info")
                and employee.employee_work_info
                else None
            )
            subordinates = Employee.objects.filter(
                is_active=True, employee_work_info__reporting_manager_id=employee
            )
            department = employee.get_department()

            exclude_ids = [employee.id]
            if reporting_manager:
                exclude_ids.append(reporting_manager.id)

            colleagues = Employee.objects.filter(
                is_active=True, employee_work_info__department_id=department
            ).exclude(id__in=exclude_ids)

            self.fields["colleague_id"].queryset = colleagues
            self.fields["subordinate_id"].queryset = subordinates
            self.fields["manager_id"].queryset = (
                Employee.objects.filter(id=reporting_manager.id)
                if reporting_manager
                else Employee.objects.none()
            )

        # # Horilla multi-select filter for subordinates
        # self.fields["subordinate_id"] = HorillaMultiSelectField(
        #     queryset=Employee.objects.all(),
        #     widget=HorillaMultiSelectWidget(
        #         filter_route_name="employee-widget-filter",
        #         filter_class=EmployeeFilter,
        #         filter_instance_context_name="f",
        #         filter_template_path="employee_filters.html",
        #         instance=self.instance,
        #         required=False,
        #     ),
        #     label=_("Subordinates"),
        # )

    def clean(self):
        """
        Cleans and validates the feedback form data.
        Ensures that the start date is before the end date and validates the start date.
        """
        super().clean()
        self.errors.pop("subordinate_id", None)
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if "employee_key_results_id" in self.errors:
            del self.errors["employee_key_results_id"]

        self.instance
        validate_date(start_date, end_date)
        return cleaned_data


class QuestionTemplateForm(ModelForm):
    """
    Form for creating or updating a question template instance
    """

    cols = {"question_template": 12, "company_id": 12}

    question_template = forms.CharField(
        label=_("Question Template"),
        widget=forms.TextInput(
            attrs={
                "class": "oh-input oh-input--small oh-input--res-height w-100",
                "placeholder": _("For Developer"),
            }
        ),
    )

    class Meta:
        """
        A nested class that specifies the model and fields for the form.
        """

        model = QuestionTemplate
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["company_id"].required = True
        self.fields["company_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2 w-100",
            }
        )
        if not self.instance.pk:
            from base.auth_backends import resolve_company_id_for_new_record

            company_id = resolve_company_id_for_new_record()
            if company_id:
                self.initial["company_id"] = Company.objects.filter(id=company_id)

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class QuestionForm(ModelForm):
    """
    Form for creating or updating a question  instance
    """

    question = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "oh-input oh-input--small oh-input--res-height w-100",
                "placeholder": _("Enter question"),
            }
        ),
        required=True,
    )
    options = forms.ModelChoiceField(
        queryset=QuestionOptions.objects.all(), required=False
    )
    option_a = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "oh-input oh-input--res-height w-100", "type": "text"}
        ),
        max_length=240,
        required=False,
    )
    option_b = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "oh-input oh-input--res-height w-100", "type": "text"}
        ),
        max_length=240,
        required=False,
    )
    option_c = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "oh-input oh-input--res-height w-100", "type": "text"}
        ),
        max_length=240,
        required=False,
    )
    option_d = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "oh-input oh-input--res-height w-100", "type": "text"}
        ),
        max_length=240,
        required=False,
    )

    class Meta:
        """
        A nested class that specifies the model,exclude fields and style of fields for the form.
        """

        model = Question
        exclude = ["question_option_id", "template_id", "is_active"]
        widgets = {
            "question_type": forms.Select(
                attrs={
                    "class": "oh-select oh-select--sm oh-select--qa-change w-100",
                    "required": True,
                    "onchange": "questionTypeChange($(this))",
                }
            )
        }
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["question_type"].widget.attrs.update({"id": str(uuid.uuid4())})
        if (
            self.instance.pk
            and self.instance.question_type == "4"
            and self.instance.question_options.first()
        ):
            self.fields["option_a"].initial = (
                self.instance.question_options.first().option_a
            )
            self.fields["option_b"].initial = (
                self.instance.question_options.first().option_b
            )
            self.fields["option_c"].initial = (
                self.instance.question_options.first().option_c
            )
            self.fields["option_d"].initial = (
                self.instance.question_options.first().option_d
            )


class ObjectiveCommentForm(ModelForm):
    """
    A form used to add a comment to an employee's objective.
    Excludes fields for the employee and employee objective and uses a textarea widget for the comment field.
    """

    class Meta:
        """
        A nested class that specifies the model,exclude fields and style of fields for the form.
        """

        model = Comment
        exclude = ["employee_id", "employee_objective_id"]
        widgets = {
            "comment": forms.Textarea(
                attrs={
                    "class": "oh-input oh-input--small oh-input--textarea",
                    "rows": "4",
                    "placeholder": _("Add a comment..."),
                }
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)


class PeriodForm(ModelForm):
    """
    A form for creating or updating a Period object.
    """

    class Meta:
        """
        A nested class that specifies the model,fields and style of fields for the form.
        """

        model = Period
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "period_name": forms.TextInput(
                attrs={"placeholder": "Q1.", "class": "oh-input w-100"}
            ),
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input  w-100"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input  w-100"}
            ),
        }

    def __init__(self, *args, **kwargs):
        """
        django forms not showing value inside the date, time html element.
        so here overriding default forms instance method to set initial value
        """
        if instance := kwargs.get("instance"):
            kwargs["initial"] = set_date_field_initial(instance)
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["company_id"].required = True
        self.fields["company_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2 w-100",
            }
        )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        validate_date(start_date, end_date)


class AnonymousFeedbackForm(BaseForm):
    cols = {
        "feedback_subject": 12,
        "based_on": 12,
        "feedback_description": 12,
        "employee_id": 12,
        "department_id": 12,
        "job_position_id": 12,
    }

    class Meta:
        model = AnonymousFeedback
        fields = "__all__"
        exclude = ["status", "archive"]


class MeetingsForm(BaseForm):

    cols = {
        "employee_id": 12,
        "manager": 12,
        "answer_employees": 12,
        "question_template": 12,
    }
    date = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"class": "oh-input w-100", "type": "datetime-local"}
        ),
    )

    class Meta:
        model = Meetings
        fields = "__all__"
        exclude = ["response", "is_active"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()

        answerable_employees = self.data.getlist("answer_employees", [])
        employees = Employee.objects.filter(id__in=answerable_employees)
        cleaned_data["answer_employees"] = employees

        employee_id = self.data.getlist("employee_id", [])
        employees = Employee.objects.filter(id__in=employee_id)
        cleaned_data["employee_id"] = employees

        if isinstance(self.fields["employee_id"], HorillaMultiSelectField):
            ids = self.data.getlist("employee_id")
            if ids:
                self.errors.pop("employee_id", None)

        if cleaned_data["answer_employees"] and not cleaned_data["question_template"]:
            raise ValidationError(
                {
                    "question_template": _(
                        "Question template is required when answer employees are choosed"
                    )
                }
            )

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"] = HorillaMultiSelectField(
            queryset=Employee.objects.filter(employee_work_info__isnull=False),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                form=self,
                instance=self.instance,
            ),
            label=_("Employees"),
        )
        try:
            if self.data.getlist("employee_id"):
                employees = Employee.objects.filter(
                    id__in=self.data.getlist("employee_id")
                )
                self.fields["answer_employees"].queryset = employees
        except:
            pass


class MeetingResponseForm(ModelForm):
    """
    Meeting response form
    """

    cols = {"response": 12}

    class Meta:
        model = Meetings
        fields = ["response"]
        widgets = {
            "response": forms.Textarea(attrs={"data-summernote": ""}),
        }


class BonusPointSettingForm(HorillaModelForm):
    """
    BonusPointSetting form
    """

    model = forms.ChoiceField(
        choices=BonusPointSetting.MODEL_CHOICES,
        widget=forms.Select(
            attrs={
                "onchange": "ModelChange($(this))",
            }
        ),
    )

    class Meta:
        model = BonusPointSetting
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["company_id"].widget.attrs.update(
            {"class": "oh-select oh-select-2 w-100"}
        )
        # Always required: signals.py uses this to decide who receives the
        # bonus point, so a blank value silently awards nobody.
        self.fields["applicable_for"].required = True

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get("model")
        applicable_for = cleaned_data.get("applicable_for")

        if model in ["pms.models.EmployeeObjective", "pms.models.EmployeeKeyResult"]:
            if applicable_for != "owner":
                raise ValidationError(
                    _("For Objective and Key Result, 'Applicable For' must be 'Owner'.")
                )
            if cleaned_data.get("bonus_for") != "Closed":
                raise ValidationError(
                    _("For Objective and Key Result, 'Bonus For' must be 'Closing'.")
                )
        if model in ["project.models.Task", "project.models.Project"]:
            if applicable_for == "owner":
                raise ValidationError(
                    _(
                        "For Task and Project, 'Applicable For' must be 'Members' or 'Managers'."
                    )
                )
        if cleaned_data.get("points", 0) <= 0:
            raise ValidationError(_("Bonus point must be greater than zero"))

        return cleaned_data


class EmployeeBonusPointForm(HorillaModelForm):
    """
    EmployeeBonusPoint form
    """

    class Meta:
        model = EmployeeBonusPoint
        fields = "__all__"
        exclude = ["bonus_point_id", "instance", "is_active"]

    def __init__(self, *args, **kwargs):
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        super().__init__(*args, **kwargs)
        if request.GET.get("employee_id"):
            employee = Employee.objects.filter(id=request.GET["employee_id"])
            if employee:
                self.fields["employee_id"].queryset = employee
                self.initial["employee_id"] = employee.first()

    def clean(self):
        cleaned_data = super().clean()
        bonus_point = cleaned_data.get("bonus_point")
        if bonus_point <= 0:
            raise forms.ValidationError(
                {"bonus_point": _("Point should be greater than zero.")}
            )
        return cleaned_data


class EmployeeFeedbackForm(HorillaModelForm):

    cols = {"others_id": 12}

    class Meta:
        model = Feedback
        fields = ["others_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["others_id"] = HorillaMultiSelectField(
            queryset=Employee.objects.filter(employee_work_info__isnull=False),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                form=self,
                instance=self.instance,
            ),
            label=_("Employees"),
        )

    def clean(self):
        cleaned_data = super().clean()
        if isinstance(self.fields["others_id"], HorillaMultiSelectField):
            self.errors.pop("others_id", None)

            employee_data = self.fields["others_id"].queryset.filter(
                id__in=self.data.getlist("others_id")
            )

            cleaned_data["others_id"] = employee_data

        return cleaned_data


class BulkFeedbackForm(HorillaModelForm):
    """Form for creating feedback in bulk"""

    title = forms.CharField(required=True, label=_("Title"))
    employee_ids = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True), required=True
    )
    other_employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(is_active=True),
        required=False,
        label=_("Other employees"),
        help_text=_("Employees need to sent feedback request."),
    )
    include_manager = forms.BooleanField(
        initial=True,
        required=False,
    )
    include_subordinates = forms.BooleanField(
        initial=True, required=False, label=_("Include all subordinates")
    )
    include_colleagues = forms.BooleanField(
        initial=True, required=False, label=_("Include all colleagues")
    )
    include_keyresult = forms.BooleanField(
        initial=True,
        required=False,
        label=_("Include all keyresults"),
        help_text=_("Include all keyresults assigned to the employee."),
    )
    period = forms.ModelChoiceField(
        queryset=Period.objects.all(),
        label=_("Period"),
        required=False,
        widget=forms.Select(
            attrs={
                "onchange": "periodChange($(this))",
            }
        ),
    )

    class Meta:
        model = Feedback
        fields = [
            "title",
            "employee_ids",
            "status",
            "other_employees",
            "include_manager",
            "include_subordinates",
            "include_colleagues",
            "include_keyresult",
            "question_template_id",
            "cyclic_feedback",
            "cyclic_feedback_period",
            "cyclic_feedback_days_count",
            "period",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "end_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_ids"] = HorillaMultiSelectField(
            queryset=Employee.objects.filter(employee_work_info__isnull=False),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                form=self,
                instance=self.instance,
                required=True,
            ),
            label=_("Employees"),
        )
        self.fields["status"].initial = "Not Started"
        self.fields["cyclic_feedback"].widget.attrs["onchange"] = "cyclicFeedback()"
        self.fields["title"].widget.attrs["autocomplete"] = "off"

    def clean(self):
        cleaned_data = super().clean()
        if isinstance(self.fields["employee_ids"], HorillaMultiSelectField):
            self.errors.pop("employee_ids", None)

            employee_data = self.fields["employee_ids"].queryset.filter(
                id__in=self.data.getlist("employee_ids")
            )

            cleaned_data["employee_ids"] = employee_data

        return cleaned_data
