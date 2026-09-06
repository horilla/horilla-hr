"""
forms.py

This module contains the form classes used in the application.

Each form represents a specific functionality or data input in the
application. They are responsible for validating
and processing user input data.

Classes:
- YourForm: Represents a form for handling specific data input.

Usage:
from django import forms

class YourForm(forms.Form):
    field_name = forms.CharField()

    def clean_field_name(self):
        # Custom validation logic goes here
        pass
"""

import uuid
from datetime import date
from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm as UserForm
from django.forms import DateInput, ValidationError
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from base.methods import reload_queryset
from employee.filters import EmployeeFilter
from employee.models import Employee, EmployeeBankDetails
from horilla_auth.models import HorillaUser
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from onboarding.models import (
    CandidateStage,
    CandidateTask,
    OnboardingStage,
    OnboardingTask,
)
from recruitment.models import Candidate


class UserCreationFormCustom(UserForm):
    """
    Overriding user creation form to apply some styles
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        for _unused, field in self.fields.items():
            widget = field.widget
            if isinstance(
                widget,
                (
                    forms.NumberInput,
                    forms.EmailInput,
                    forms.TextInput,
                    forms.PasswordInput,
                ),
            ):
                field.widget.attrs.update(
                    {
                        "class": "oh-input oh-input--password w-100",
                        "placeholder": field.label,
                    }
                )
            elif isinstance(widget, (forms.DateField)):
                field.widget.attrs.update({"class": "oh-input oh-calendar-input w-100"})
            elif isinstance(
                widget, (forms.NumberInput, forms.EmailInput, forms.TextInput)
            ):
                field.widget.attrs.update(
                    {"class": "oh-input w-100", "placeholder": field.label}
                )
            elif isinstance(widget, (forms.Select,)):
                field.empty_label = f"---Choose {field.label}---"
                field.widget.attrs.update(
                    {"class": "oh-select oh-select-2 select2-hidden-accessible"}
                )
            elif isinstance(widget, (forms.Textarea)):
                field.widget.attrs.update(
                    {
                        "class": "oh-input w-100",
                        "placeholder": field.label,
                        "rows": 2,
                        "cols": 40,
                    }
                )
            elif isinstance(
                widget,
                (
                    forms.CheckboxInput,
                    forms.CheckboxSelectMultiple,
                ),
            ):
                field.widget.attrs.update({"class": "oh-switch__checkbox"})


class OnboardingCandidateForm(ModelForm):
    """
    Form for Candidate model
    """

    class Meta:
        """
        Meta class for some additional options
        """

        model = Candidate
        fields = "__all__"
        exclude = (
            "stage_id",
            "assigned_manager",
            "confirmation",
            "hired",
            "referral",
            "portfolio",
            "canceled",
            "is_active",
            "resume",
            "schedule_date",
            "job_position_id",
        )
        widgets = {
            "joining_date": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": _("Full Name"),
            "email": _("Email"),
            "mobile": _("Mobile"),
        }


class UserCreationForm(UserCreationFormCustom):
    """
    Form for HorillaUser model
    """

    class Meta:
        """
        Meta class to add some additional options
        """

        model = HorillaUser
        fields = ["password1", "password2"]


class OnboardingViewTaskForm(ModelForm):
    """
    Form for OnboardingTask model
    """

    candidates = forms.ModelMultipleChoiceField(
        queryset=Candidate.objects.all(),
        # widget=forms.SelectMultiple(attrs={"class": "select2-hidden-accessible "}),
        required=False,
    )
    stage_id = forms.HiddenInput()
    task_title = forms.CharField(label=(_("Task title")))
    managers = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.all(),
        # widget=forms.SelectMultiple(attrs={"class": "select2-hidden-accessible "})
    )
    is_required = forms.BooleanField(required=False, label=_("Is Required"))

    class Meta:
        """
        Meta class for some additional options
        """

        model = CandidateTask
        fields = "__all__"
        exclude = ["status", "candidate_id", "onboarding_task_id", "is_active"]

    def clean(self):
        for field_name, field_instance in self.fields.items():
            if isinstance(field_instance, HorillaMultiSelectField):
                self.errors.pop(field_name, None)
                if len(self.data.getlist(field_name)) < 1:
                    raise forms.ValidationError({field_name: "Thif field is required"})
                cleaned_data = super().clean()
                employee_data = self.fields[field_name].queryset.filter(
                    id__in=self.data.getlist(field_name)
                )
                cleaned_data[field_name] = employee_data
        cleaned_data = super().clean()
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["managers"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                required=True,
                instance=self.instance,
            ),
            label=_("Task Managers"),
        )
        reload_queryset(self.fields)


class OnboardingTaskForm(ModelForm):
    """
    Form for OnboardingTaskModel
    """

    class Meta:
        """
        Meta class for add some additional options
        """

        model = OnboardingTask
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "candidates": forms.SelectMultiple(
                attrs={"class": "oh-select oh-select-2 w-100 select2-hidden-accessible"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                required=True,
                instance=self.instance,
            ),
            label=self.fields["employee_id"].label,
        )
        stage_id = self.initial.get("stage_id")
        if stage_id:
            stage = OnboardingStage.objects.get(id=stage_id)
            recruitment = stage.recruitment_id

            # Adjust the queryset based on the 'stage'
            stage_queryset = recruitment.onboarding_stage.all()
            self.fields["stage_id"].queryset = stage_queryset
            candidate_ids = stage.candidate.all().values_list("candidate_id", flat=True)
            cand_queryset = Candidate.objects.filter(id__in=candidate_ids)
            self.fields["candidates"].queryset = cand_queryset

    def clean(self):
        if isinstance(self.fields["employee_id"], HorillaMultiSelectField):
            ids = self.data.getlist("employee_id")
            if ids:
                self.errors.pop("employee_id", None)
        super().clean()


class OnboardingViewStageForm(ModelForm):
    """
    Form for OnboardingStageModel
    """

    class Meta:
        """
        Meta class for add some additional options
        """

        model = OnboardingStage
        fields = ["stage_title", "employee_id", "is_final_stage", "recruitment_id"]
        labels = {
            "stage_title": _("Stage Title"),
            "is_final_stage": _("Is Final Stage"),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the form with custom field settings and widgets.
        """
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["employee_id"] = HorillaMultiSelectField(
            queryset=Employee.objects.filter(is_active=True),
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                required=True,
                instance=self.instance,
            ),
            label=self.fields["employee_id"].label,
        )

        # Loop through form fields and generate unique IDs for their attributes
        for field_name, field in self.fields.items():
            unique_id = str(uuid.uuid4())  # You can customize the unique ID format

            # Set the widget's attributes with the unique ID
            field.widget.attrs.update({"id": unique_id})

    def as_p(self, *args, **kwargs):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def clean(self):
        if isinstance(self.fields["employee_id"], HorillaMultiSelectField):
            ids = self.data.getlist("employee_id")
            if ids:
                self.errors.pop("employee_id", None)
        super().clean()


class EmployeeCreationForm(ModelForm):
    """
    Form for Employee Model
    """

    employee_first_name = forms.CharField(required=True, label=_("First Name"))
    employee_last_name = forms.CharField(required=False, label=_("Last Name"))
    phone = forms.CharField(required=True, label=_("Phone"))
    address = forms.CharField(required=True, label=_("Address"))
    country = forms.CharField(required=True, label=_("Country"))
    state = forms.CharField(required=True, label=_("State"))
    zip = forms.CharField(required=True, label=_("Zip"))
    qualification = forms.CharField(required=True, label=_("Qualification"))
    experience = forms.IntegerField(required=True, label=_("Experience"))
    children = forms.IntegerField(required=True, label=_("Children"))
    emergency_contact = forms.CharField(
        required=True, label=_("Emergency Contact Number")
    )
    emergency_contact_name = forms.CharField(
        required=True, label=_("Emergency Contact Name")
    )
    emergency_contact_relation = forms.CharField(
        required=True, label=_("Emergency Contact Relation")
    )

    class Meta:
        """
        Meta class to add some additional options
        """

        model = Employee
        fields = "__all__"
        exclude = (
            "employee_user_id",
            "employee_profile",
            "email",
            "is_active",
            "additional_info",
            "is_from_onboarding",
            "is_directly_converted",
        )
        widgets = {
            "dob": DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = self.cleaned_data
        if cleaned_data["experience"] and cleaned_data["experience"] < 0:
            raise ValidationError(
                {"experience": _("Experience should be a postive integier")}
            )
        if cleaned_data["children"] and cleaned_data["children"] < 0:
            raise ValidationError(
                {"children": _("No of children should be a postive integier")}
            )

        return super().clean()


class BankDetailsCreationForm(ModelForm):
    """
    Form for BankDetailsCreationForm
    """

    bank_name = forms.CharField(required=True, label="Bank Name")
    account_number = forms.CharField(required=True, label="Account Number")
    branch = forms.CharField(required=True, label="Branch")
    address = forms.Textarea()
    country = forms.CharField(required=True, label="Country")
    state = forms.CharField(required=True, label="State")
    city = forms.CharField(required=True, label="City")
    any_other_code1 = forms.CharField(required=True, label="Code #1")
    any_other_code2 = forms.CharField(required=False, label="Code #2")

    class Meta:
        """
        Meta class to add some additional options
        """

        model = EmployeeBankDetails
        fields = "__all__"
        exclude = ["employee_id", "additional_info", "is_active"]


class StageChangeForm(forms.ModelForm):
    """
    StageChangeForm
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = CandidateStage
        fields = [
            "onboarding_stage_id",
        ]

    def clean(self):
        cleaned_data = super().clean()
        new_stage = cleaned_data.get("onboarding_stage_id")
        old_stage = self.instance.onboarding_stage_id
        if (
            new_stage
            and old_stage
            and new_stage.sequence is not None
            and old_stage.sequence is not None
        ):
            pending_tasks = self.instance.pending_required_tasks(old_stage)
            if pending_tasks.exists():
                task_titles = ", ".join(
                    pending_tasks.values_list("task_title", flat=True)
                )
                raise forms.ValidationError(
                    _(
                        "Complete the following required task(s) before "
                        "moving to the next stage: %(tasks)s"
                    )
                    % {"tasks": task_titles}
                )
        return cleaned_data
