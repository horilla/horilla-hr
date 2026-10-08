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

from datetime import datetime
from typing import Any

from django import forms
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from base.methods import filtersubordinatesemployeemodel, is_reportingmanager
from base.models import Department, JobPosition
from employee.forms import MultipleFileField
from employee.models import Employee
from helpdesk.models import (
    FAQ,
    Attachment,
    Comment,
    DepartmentManager,
    FAQCategory,
    Ticket,
    TicketType,
)
from horilla import horilla_middlewares


class TicketTypeForm(ModelForm):

    cols = {"title": 12, "type": 12, "prefix": 12}

    class Meta:
        model = TicketType
        fields = "__all__"
        exclude = ["is_active"]

    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get("title")
        prefix = cleaned_data.get("prefix")
        instance = self.instance

        request = getattr(horilla_middlewares._thread_locals, "request", None)
        from base.auth_backends import resolve_company_id_for_new_record

        company_id = resolve_company_id_for_new_record(request)
        if company_id:
            from base.models import Company as CompanyModel

            company = CompanyModel.find(company_id)
            qs_title = TicketType.objects.filter(title=title, company_id=company)
            qs_prefix = TicketType.objects.filter(prefix=prefix, company_id=company)
        else:
            qs_title = TicketType.objects.filter(title=title, company_id__isnull=True)
            qs_prefix = TicketType.objects.filter(
                prefix=prefix, company_id__isnull=True
            )

        if instance.pk:
            qs_title = qs_title.exclude(pk=instance.pk)
            qs_prefix = qs_prefix.exclude(pk=instance.pk)

        if title and qs_title.exists():
            self.add_error("title", _("Ticket type with this title already exists."))
        if prefix and qs_prefix.exists():
            self.add_error("prefix", _("Ticket type with this prefix already exists."))

        return cleaned_data

    def as_p(self, *args, **kwargs):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html


class FAQForm(ModelForm):

    cols = {"question": 12, "answer": 12, "tags": 12}

    class Meta:
        model = FAQ
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "category": forms.HiddenInput(),
            "tags": forms.SelectMultiple(
                attrs={
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                    "onchange": "updateTag(this)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the Ticket tag form instance.
        If an instance is provided, sets the initial value for the form's .
        """
        super().__init__(*args, **kwargs)
        self.fields["tags"].choices = list(self.fields["tags"].choices)
        self.fields["tags"].choices.append(("create_new_tag", "Create new tag"))


class TicketForm(ModelForm):

    cols = {"description": 12, "tags": 12}

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "employee_id",
            "description",
            "ticket_type",
            "priority",
            "assigning_type",
            "raised_on",
            "deadline",
            "status",
            "tags",
        ]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "raised_on": forms.Select(
                attrs={"class": "oh-select oh-select-2", "required": "true"}
            ),
            "description": forms.Textarea(
                attrs={
                    "data-summernote": True,
                    "hidden": True,
                }
            ),
        }

    def as_p(self, *args, **kwargs):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields.pop("attachment", None)
        else:
            self.fields["attachment"] = MultipleFileField(
                label="Attachements", required=False
            )
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if self.instance and self.instance.pk:
            is_manager = self.instance.can_manage_priority()
        else:
            is_manager = request.user.has_perm("helpdesk.change_ticket") or (
                is_reportingmanager(request)
            )
        if not is_manager:
            self.fields.pop("deadline", None)
            if self.instance and self.instance.pk:
                self.fields.pop("priority", None)
        instance = kwargs.get("instance")
        if instance:
            employee = instance.employee_id
        else:
            employee = request.user.employee_get
        # initialising employee queryset according to the user
        self.fields["employee_id"].queryset = (
            filtersubordinatesemployeemodel(
                request,
                Employee.objects.filter(is_active=True),
                perm="helpdesk.add_ticket",
            )
        ).distinct() | (
            Employee.objects.filter(employee_user_id=request.user)
        ).distinct()
        self.fields["employee_id"].initial = employee
        # appending dynamic create option according to user
        if is_reportingmanager(request) or request.user.has_perm(
            "helpdesk.add_tickettype"
        ):
            self.fields["ticket_type"].choices = list(
                self.fields["ticket_type"].choices
            )
            # self.fields["ticket_type"].choices.append(
            #     ("create_new_ticket_type", "Create new ticket type")
            # )
        if is_reportingmanager(request) or request.user.has_perm("base.add_tags"):
            self.fields["tags"].choices = list(self.fields["tags"].choices)
            self.fields["tags"].choices.append(("create_new_tag", "Create new tag"))

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)
        deadline = cleaned_data.get("deadline")
        today = datetime.today().date()
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        user = getattr(request, "user", None)

        if deadline and deadline < today:
            if self.instance and self.instance.pk:
                if not (
                    user.has_perm("helpdesk.change_ticket")
                    or user.has_perm(
                        "helpdesk.add_ticket"
                        or self.instance.employee_id == user.employee_get
                    )
                ):
                    raise forms.ValidationError(
                        _("Deadline should be greater than today")
                    )
            else:
                raise forms.ValidationError(_("Deadline should be greater than today"))

        return cleaned_data


class TicketTagForm(ModelForm):
    class Meta:
        model = Ticket
        fields = [
            "tags",
        ]
        widgets = {
            "tags": forms.SelectMultiple(
                attrs={
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                    "onchange": "updateTag()",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the Ticket tag form instance.
        If an instance is provided, sets the initial value for the form's .
        """
        super().__init__(*args, **kwargs)
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if is_reportingmanager(request) or request.user.has_perm("base.add_tags"):
            self.fields["tags"].choices = list(self.fields["tags"].choices)
            self.fields["tags"].choices.append(("create_new_tag", "Create new tag"))


class TicketRaisedOnForm(ModelForm):
    class Meta:
        model = Ticket
        fields = ["assigning_type", "raised_on"]
        widgets = {
            "raised_on": forms.Select(
                attrs={"class": "oh-select oh-select-2", "required": "true"},
            ),
        }


class TicketAssigneesForm(ModelForm):
    class Meta:
        model = Ticket
        fields = [
            "assigned_to",
        ]


class FAQCategoryForm(ModelForm):
    cols = {"title": 12, "description": 12}

    class Meta:
        model = FAQCategory
        fields = "__all__"
        exclude = ["is_active"]


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = [
            "comment",
        ]
        exclude = ["is_active"]
        widgets = {"employee_id": forms.HiddenInput()}


class AttachmentForm(forms.ModelForm):
    file = forms.FileField(
        widget=forms.TextInput(
            attrs={
                "name": "file",
                "type": "File",
                "class": "form-control",
                "multiple": "True",
            }
        ),
        label="",
    )

    class Meta:
        model = Attachment
        fields = ["file", "comment", "ticket"]
        exclude = ["is_active"]


class DepartmentManagerCreateForm(ModelForm):

    cols = {"department": 12, "manager": 12}

    class Meta:
        model = DepartmentManager
        fields = ["department", "manager"]
        widgets = {
            "department": forms.Select(
                attrs={
                    "hx-get": reverse_lazy("get-department-employee"),
                    "hx-trigger": "change",
                    "hx-target": "#id_manager",
                    "hx-vals": 'js:{"dep_id": event.target.value}',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            if "instance" in kwargs:
                department = kwargs["instance"].department
                # Get the employees related to this department
                employees = department.employeeworkinformation_set.values_list(
                    "employee_id", flat=True
                )
                # Set the manager field queryset to be those employees
                self.fields["manager"].queryset = Employee.objects.filter(
                    id__in=employees
                )
