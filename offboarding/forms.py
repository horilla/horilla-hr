"""
offboarding/forms.py

This module is used to register forms for offboarding app
"""

import contextlib
from datetime import date
from typing import Any

from django import forms
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from base.forms import ModelForm
from employee.forms import MultipleFileField
from employee.models import Employee
from horilla import horilla_middlewares
from notifications.signals import notify
from offboarding.models import (
    EmployeeTask,
    Offboarding,
    OffboardingEmployee,
    OffboardingNote,
    OffboardingStage,
    OffboardingStageMultipleFile,
    OffboardingTask,
    ResignationComment,
    ResignationLetter,
)


class OffboardingForm(ModelForm):
    """
    OffboardingForm model form class
    """

    verbose_name = "Offboarding"

    cols = {"title": 12, "description": 12, "managers": 12, "status": 12}

    class Meta:
        model = Offboarding
        fields = "__all__"
        exclude = ["is_active"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class OffboardingStageForm(ModelForm):
    """
    OffboardingStage model form
    """

    verbose_name = "Stage"

    cols = {"title": 12, "type": 12, "managers": 12}

    class Meta:
        model = OffboardingStage
        fields = "__all__"
        exclude = ["is_active"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class OffboardingEmployeeForm(ModelForm):
    """
    OffboardingEmployeeForm model form
    """

    verbose_name = "Offboarding "

    class Meta:
        model = OffboardingEmployee
        fields = "__all__"
        exclude = ["notice_period", "unit", "is_active"]
        widgets = {
            "notice_period_starts": forms.DateInput(attrs={"type": "date"}),
            "notice_period_ends": forms.DateInput(attrs={"type": "date"}),
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
        attrs = self.fields["employee_id"].widget.attrs
        attrs["onchange"] = "initialNoticePeriod($(this))"
        self.fields["employee_id"].widget.attrs.update(attrs)
        attrs = self.fields["notice_period_starts"].widget.attrs
        attrs["onchange"] = "noticePeriodUpdate($(this))"
        self.fields["notice_period_starts"].widget.attrs.update(attrs)
        if self.instance.pk:
            if self.instance.notice_period_starts:
                self.initial["notice_period_starts"] = (
                    self.instance.notice_period_starts.strftime("%Y-%m-%d")
                )
            if self.instance.notice_period_ends:
                self.initial["notice_period_ends"] = (
                    self.instance.notice_period_ends.strftime("%Y-%m-%d")
                )


class StageSelectForm(ModelForm):
    """
    This form is used to register drop down for the pipeline
    """

    class Meta:
        model = OffboardingEmployee
        fields = [
            "stage_id",
        ]

    def __init__(self, *args, offboarding=None, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = self.fields["stage_id"].widget.attrs
        attrs["onchange"] = "offboardingUpdateStage($(this))"
        attrs["class"] = "w-100 oh-custom-select"
        self.fields["stage_id"].widget.attrs.update(attrs)
        self.fields["stage_id"].empty_label = None
        self.fields["stage_id"].queryset = OffboardingStage.objects.filter(
            offboarding_id=offboarding
        )
        self.fields["stage_id"].label = ""


class NoteForm(ModelForm):
    """
    Offboarding note model form
    """

    verbose_name = "Add Note"

    class Meta:
        model = OffboardingNote
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"] = MultipleFileField(label="Attachements")
        self.fields["attachment"].required = False

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        multiple_attachment_ids = []
        attachments = None
        if self.files.getlist("attachment"):
            attachments = self.files.getlist("attachment")
            self.instance.attachment = attachments[0]
            multiple_attachment_ids = []
            for attachment in attachments:
                file_instance = OffboardingStageMultipleFile()
                file_instance.attachment = attachment
                file_instance.save()
                multiple_attachment_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.attachments.add(*multiple_attachment_ids)
        return instance, attachments


class TaskForm(ModelForm):
    """
    TaskForm model form
    """

    verbose_name = "Offboarding Task"
    tasks_to = forms.ModelMultipleChoiceField(
        queryset=OffboardingEmployee.objects.all(), required=False, label=_("Task To")
    )
    cols = {"title": 12, "managers": 12, "stage_id": 12, "tasks_to": 12}

    class Meta:
        model = OffboardingTask
        fields = "__all__"
        exclude = ["status", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage_id"].empty_label = "All Stages in Offboarding"
        self.fields["managers"].empty_label = None
        if not self.instance.pk:
            stage = OffboardingStage.objects.filter(
                id=self.initial.get("stage_id")
            ).first()
            queryset = (
                OffboardingEmployee.objects.filter(
                    stage_id__offboarding_id=stage.offboarding_id
                )
                if stage
                else OffboardingEmployee.objects.none()
            )
            self.fields["tasks_to"].queryset = queryset

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        super().save(commit)
        if commit:
            employees = self.cleaned_data["tasks_to"]
            for employee in employees:
                assigned_task = EmployeeTask.objects.get_or_create(
                    employee_id=employee,
                    task_id=self.instance,
                )


class ResignationLetterForm(ModelForm):
    """
    Resignation Letter
    """

    cols = {
        "employee_id": 12,
        "title": 12,
        "description": 12,
    }

    description = forms.CharField(
        widget=forms.Textarea(attrs={"data-summernote": "", "style": "display:none;"}),
        label="Description",
    )
    verbose_name = "Resignation Letter"

    class Meta:
        model = ResignationLetter
        fields = "__all__"
        # planned_to_leave_on is no longer asked for: the notice period start/end
        # are chosen when the request is approved (see __init__ for the default).
        # status isn't either: new letters start as "requested" (model default) and
        # move to approved/rejected only through the Approve/Reject actions.
        exclude = ["is_active", "planned_to_leave_on", "status"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The column is required, so a new letter starts the notice period today;
        # existing letters keep whatever date they already have.
        if not self.instance.planned_to_leave_on:
            self.instance.planned_to_leave_on = date.today()
        exclude = []
        if self.instance.pk:
            exclude.append("employee_id")
            self.verbose_name = (
                self.instance.employee_id.get_full_name() + "'s Resignation Letter"
            )

        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if request and not request.user.has_perm("offboarding.add_resignationletter"):
            # A regular employee can only resign for themselves, so there is
            # nothing to choose: drop the field and bind the letter to them.
            exclude = exclude + ["status", "employee_id"]
            if not self.instance.pk:
                self.instance.employee_id = request.user.employee_get
        if request and request.user.has_perm("offboarding.add_resignationletter"):
            if request.GET.get("emp_id"):
                emp_id = request.GET.get("emp_id")
                self.fields["employee_id"].queryset = Employee.objects.filter(id=emp_id)
                self.fields["employee_id"].initial = emp_id
        exclude = list(set(exclude))
        for field in exclude:
            self.fields.pop(field, None)

    def save(self, commit: bool = ...) -> Any:
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        instance = self.instance
        if (
            not request.user.has_perm("offboarding.add_resignationletter")
            and instance.status == "requested"
        ) or request.user.has_perm("offboarding.add_resignationletter"):
            instance = super().save(commit)
        else:
            messages.info(
                request, _("You cannot edit a request that has been rejected/approved")
            )
            return None

        if (
            instance.status == "requested"
            and request
            and not request.user.has_perm("offboarding.add_resignationletter")
        ):
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=self.instance.employee_id.get_reporting_manager().employee_user_id,
                    verb=gettext_noop("%(get_full_name)s requested for resignation."),
                    verb_params={
                        "get_full_name": str(self.instance.employee_id.get_full_name())
                    },
                    redirect="#",
                    icon="information",
                )
        return instance


class ResignationCancelForm(forms.Form):
    """
    Reason an employee gives when cancelling a resignation request.
    """

    cancel_reason = forms.CharField(
        label=_("Reason for Cancellation"),
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 255,
                "class": "p-4 oh-input w-100",
                "placeholder": _("Reason for Cancellation"),
            }
        ),
    )


class ResignationCommentForm(ModelForm):
    """
    Resignation letter comment form
    """

    class Meta:
        model = ResignationComment
        fields = ("comment",)
