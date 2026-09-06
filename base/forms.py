"""
forms.py

This module is used to register forms for base module
"""

import calendar
import ipaddress
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import bleach
from django import forms
from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm, _unicode_ci_compare
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_ipv46_address
from django.db.models import Q
from django.forms import DateInput, HiddenInput, TextInput
from django.template import loader
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

from base.methods import reload_queryset
from base.models import (
    Announcement,
    AnnouncementComment,
    AnnouncementExpire,
    Attachment,
    AttendanceAllowedIP,
    BaserequestFile,
    Company,
    CompanyLeaves,
    Department,
    DriverViewed,
    DynamicEmailConfiguration,
    EmployeeShift,
    EmployeeShiftDay,
    EmployeeShiftSchedule,
    EmployeeType,
    Holidays,
    HorillaMailTemplate,
    JobPosition,
    JobRole,
    MultipleApprovalCondition,
    PenaltyAccounts,
    Roster,
    RotatingShift,
    RotatingShiftAssign,
    RotatingWorkType,
    RotatingWorkTypeAssign,
    ShiftRequest,
    ShiftRequestComment,
    Tags,
    TrackLateComeEarlyOut,
    WorkType,
    WorkTypeRequest,
    WorkTypeRequestComment,
)
from base.widgets import CustomModelChoiceWidget
from employee.filters import EmployeeFilter
from employee.models import Employee, EmployeeTag
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla_audit.models import AuditTag
from horilla_auth.models import HorillaUser
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget

# your form here


def validate_time_format(value):
    """
    this method is used to validate the format of duration like fields.
    """
    if len(value) > 6:
        raise ValidationError(_("Invalid format, it should be HH:MM format"))
    try:
        hour, minute = value.split(":")
        hour = int(hour)
        minute = int(minute)
        if len(str(hour)) > 3 or minute not in range(60):
            raise ValidationError(_("Invalid format, it should be HH:MM format"))
    except ValueError as error:
        raise ValidationError(_("Invalid format, it should be HH:MM format")) from error


BASED_ON = [
    ("after", _("After")),
    ("weekly", _("Weekend")),
    ("monthly", _("Monthly")),
]


def get_next_week_date(target_day, start_date):
    """
    Calculates the date of the next occurrence of the target day within the next week.

    Parameters:
        target_day (int): The target day of the week (0-6, where Monday is 0 and Sunday is 6).
        start_date (date): The starting date.

    Returns:
        date: The date of the next occurrence of the target day within the next week.
    """
    if start_date.weekday() == target_day:
        return start_date
    days_until_target_day = (target_day - start_date.weekday()) % 7
    if days_until_target_day == 0:
        days_until_target_day = 7
    return start_date + timedelta(days=days_until_target_day)


def get_next_monthly_date(start_date, rotate_every):
    """
    Given a start date and a rotation day (specified as an integer between 1 and 31, or
    the string 'last'),calculates the next rotation date for a monthly rotation schedule.

    If the rotation day has not yet occurred in the current month, the next rotation date
    will be on the rotation day of the current month. If the rotation day has already
    occurred in the current month, the next rotation date will be on the rotation day of
    the next month.

    If 'last' is specified as the rotation day, the next rotation date will be on the
    last day of the current month.

    Parameters:
    - start_date: The start date of the rotation schedule, as a date object.
    - rotate_every: The rotation day, specified as an integer between 1 and 31, or the
      string 'last'.

    Returns:
    - A date object representing the next rotation date.
    """

    if rotate_every == "last":
        # Set rotate_every to the last day of the current month
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        rotate_every = str(last_day)
    rotate_every = int(rotate_every)

    # Calculate the next change date
    if start_date.day <= rotate_every or rotate_every == 0:
        # If the rotation day has not occurred yet this month, or if it's the last-
        # day of the month, set the next change date to the rotation day of this month
        try:
            next_change = date(start_date.year, start_date.month, rotate_every)
        except ValueError:
            next_change = date(
                start_date.year, start_date.month + 1, 1
            )  # Advance to next month
            # Set day to rotate_every
            next_change = date(next_change.year, next_change.month, rotate_every)
    else:
        # If the rotation day has already occurred this month, set the next change
        # date to the rotation day of the next month
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        next_month_start = start_date.replace(day=last_day) + timedelta(days=1)
        try:
            next_change = next_month_start.replace(day=rotate_every)
        except ValueError:
            next_change = (
                next_month_start.replace(month=next_month_start.month + 1)
                + timedelta(days=1)
            ).replace(day=rotate_every)

    return next_change


class ModelForm(forms.ModelForm):
    """
    Override of Django ModelForm to add initial styling and defaults.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        reload_queryset(self.fields)

        request = getattr(horilla_middlewares._thread_locals, "request", None)

        today = date.today()
        now = datetime.now()

        default_input_class = "oh-input w-100"
        select_class = "oh-select oh-select-2 select2-hidden-accessible"
        checkbox_class = "oh-switch__checkbox"

        for field_name, field in self.fields.items():
            widget = field.widget
            label = _(field.label).title() if field.label else ""
            # Date field
            if isinstance(widget, forms.DateInput):
                field.initial = today
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"
                field.input_formats = ["%Y-%m-%d"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Time field
            elif isinstance(widget, forms.TimeInput):
                field.initial = now.strftime("%H:%M")
                widget.input_type = "time"
                widget.format = "%H:%M"
                field.input_formats = ["%H:%M"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Number, Email, Text, File, URL fields
            elif isinstance(
                widget,
                (
                    forms.NumberInput,
                    forms.EmailInput,
                    forms.TextInput,
                    forms.FileInput,
                    forms.URLInput,
                ),
            ):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Select fields
            elif isinstance(widget, forms.Select):
                if not isinstance(field, forms.ModelMultipleChoiceField):
                    field.empty_label = _("---Choose {label}---").format(label=label)
                existing_class = widget.attrs.get("class", select_class)
                widget.attrs.update({"class": existing_class})

            # Textarea
            elif isinstance(widget, forms.Textarea):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                        "rows": 2,
                        "cols": 40,
                    }
                )

            # Checkbox types
            elif isinstance(
                widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)
            ):
                existing_class = widget.attrs.get("class", checkbox_class)
                widget.attrs.update({"class": existing_class})

            # Make the rendered field label title case everywhere
            if field.label:
                field.label = label

        # Set employee_id and company_id once
        if request:
            employee = getattr(request.user, "employee_get", None)
            if employee:
                if "employee_id" in self.fields:
                    self.fields["employee_id"].initial = employee

                if "company_id" in self.fields:
                    company_field = self.fields["company_id"]
                    company = getattr(employee, "get_company", None)
                    if company:
                        queryset = company_field.queryset
                        company_field.initial = (
                            company if company in queryset else queryset.first()
                        )

    def verbose_name(self):
        """
        Returns the verbose name of the model associated with the form.
        Provides fallback values if no model or verbose name is defined.
        """
        if hasattr(self, "_meta") and hasattr(self._meta, "model"):
            model = self._meta.model
            if hasattr(model._meta, "verbose_name") and model._meta.verbose_name:
                return model._meta.verbose_name
            return model.__name__
        return ""


class Form(forms.Form):
    """
    Overrides to add initial styling to the django Form instance
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(
                widget, (forms.NumberInput, forms.EmailInput, forms.TextInput)
            ):
                if field.label is not None:
                    label = _(field.label)
                    field.widget.attrs.update(
                        {"class": "oh-input w-100", "placeholder": label}
                    )
            elif isinstance(widget, (forms.Select,)):
                label = ""
                if field.label is not None:
                    label = field.label.replace("id", " ")
                field.empty_label = _("---Choose {label}---").format(label=label)
                field.widget.attrs.update(
                    {"class": "oh-select oh-select-2 select2-hidden-accessible"}
                )
            elif isinstance(widget, (forms.Textarea)):
                label = _(field.label)
                field.widget.attrs.update(
                    {
                        "class": "oh-input w-100",
                        "placeholder": label,
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


class UserGroupForm(ModelForm):
    """
    Django user groups form
    """

    try:
        permissions = forms.MultipleChoiceField(
            required=False,
            error_messages={
                "required": "Please choose a permission.",
            },
        )
    except:
        pass

    class Meta:
        """
        Meta class for additional options
        """

        model = Group
        fields = ["name", "permissions"]
        labels = {
            "name": _("Group name"),
        }
        help_texts = {
            "name": _(
                "Give this group a clear name, e.g. HR Managers or Finance Team."
            ),
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": _("e.g. HR Managers"),
                    "class": "oh-input w-100",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields["permissions"].choices = [
                (perm.codename, perm.name) for perm in Permission.objects.all()
            ]
        except Exception:
            # Safe fallback when DB is not ready
            self.fields["permissions"].choices = []

    def save(self, commit=True):
        """
        ModelForm save override
        """
        group = super().save(commit=False)
        if self.instance:
            group = self.instance
        group.save()

        # Convert the selected codenames back to Permission instances
        permissions_codenames = self.cleaned_data["permissions"]
        permissions = Permission.objects.filter(codename__in=permissions_codenames)

        # Set the associated permissions
        group.permissions.set(permissions)

        if commit:
            group.save()

        return group


class AssignUserGroup(Form):
    """
    Form to assign employees to a group (searchable multi-select).
    """

    employee = HorillaMultiSelectField(
        queryset=Employee.objects.filter(
            is_active=True, employee_user_id__isnull=False
        ),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
            required=False,
        ),
        label=_("Employees"),
        required=False,
        help_text=_("Search and select who should belong to this group."),
    )

    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        error_messages={
            "invalid_choice": _("Invalid group ID."),
        },
    )

    companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Companies"),
        help_text=_(
            "Members get this group's permissions only in the selected "
            "companies. Leave empty for all companies you can manage."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["employee"].widget.attrs.update(
            {"data-placeholder": _("Search employees...")}
        )
        from base.auth_backends import company_scoped_active, get_assigned_company_ids
        from horilla.horilla_middlewares import _thread_locals

        self._grantable_company_ids = None
        if not company_scoped_active():
            self.fields.pop("companies", None)
            return

        request = getattr(_thread_locals, "request", None)
        user = getattr(request, "user", None) if request else None
        if user and user.is_authenticated and not user.is_superuser:
            # Only companies where the editor already holds a role — blocks
            # self-escalation onto companies they do not manage.
            grantable = get_assigned_company_ids(user)
            self._grantable_company_ids = grantable
            self.fields["companies"].queryset = Company.objects.filter(
                id__in=grantable or []
            )
            self.fields["companies"].help_text = _(
                "Members get this group's permissions only in the selected "
                "companies. You can only assign companies you already have "
                "access to. Leave empty for all of those companies."
            )
        else:
            self.fields["companies"].queryset = Company.objects.all()
            self._grantable_company_ids = None

    def clean(self):
        emps = self.data.getlist("employee") if hasattr(self.data, "getlist") else []
        if emps is not None:
            self.errors.pop("employee", None)
        super().clean()
        companies = list(self.cleaned_data.get("companies") or [])
        if self._grantable_company_ids is not None and companies:
            illegal = [c for c in companies if c.id not in self._grantable_company_ids]
            if illegal:
                self.add_error(
                    "companies",
                    _("You cannot assign this group for companies you do not manage."),
                )
        return self.cleaned_data

    def _companies_for_save(self):
        """Companies in scope for this save (never expands beyond grantable)."""
        companies = list(self.cleaned_data.get("companies") or [])
        if self._grantable_company_ids is not None:
            if companies:
                return [c for c in companies if c.id in self._grantable_company_ids]
            return list(Company.objects.filter(id__in=self._grantable_company_ids))
        if companies:
            return companies
        return list(Company.objects.all())

    def save(self, mode="add", target_employee_id=None):
        """
        Assign group membership for selected users in selected companies.

        mode="add": additive only — existing members and their company
        assignments are preserved; nothing is removed.

        mode="edit": reconciliation — members that are no longer selected
        are removed from the group entirely, and remaining members' company
        assignments are replaced to match exactly what was submitted.

        target_employee_id: when given, restricts an "edit" save to that one
        employee only — their company set is replaced (or they're removed
        if unchecked), and every other member of the group is left
        untouched. This avoids one shared ``companies`` field from being
        cross-applied to every employee selected in the form.
        """
        from base.models import CompanyGroupAssignment

        group = self.cleaned_data["group"]
        employee_ids = (
            self.data.getlist("employee") if hasattr(self.data, "getlist") else []
        )
        companies = self._companies_for_save()

        if mode == "edit" and target_employee_id:
            target_employee = Employee.objects.filter(id=target_employee_id).first()
            target_user = target_employee.employee_user_id if target_employee else None
            if target_user:
                if str(target_employee_id) in [str(e) for e in employee_ids]:
                    company_ids = {c.id for c in companies}
                    CompanyGroupAssignment.objects.filter(
                        group=group, user=target_user
                    ).exclude(company_id__in=company_ids).delete()
                    CompanyGroupAssignment.objects.bulk_create(
                        [
                            CompanyGroupAssignment(
                                user=target_user, company=company, group=group
                            )
                            for company in companies
                        ],
                        ignore_conflicts=True,
                    )
                    CompanyGroupAssignment.sync_user_group_membership(
                        target_user, group
                    )
                else:
                    CompanyGroupAssignment.objects.filter(
                        group=group, user=target_user
                    ).delete()
                    group.user_set.remove(target_user)
            return group

        assigning_employees = Employee.objects.filter(id__in=employee_ids)
        assigning_users = [
            e.employee_user_id for e in assigning_employees if e.employee_user_id
        ]

        if mode == "edit":
            previous_users = list(group.user_set.all())
            new_user_ids = {u.id for u in assigning_users}
            removed_users = [u for u in previous_users if u.id not in new_user_ids]
            if removed_users:
                CompanyGroupAssignment.objects.filter(
                    group=group, user_id__in=[u.id for u in removed_users]
                ).delete()
                group.user_set.remove(*removed_users)

            company_ids = {c.id for c in companies}
            CompanyGroupAssignment.objects.filter(
                group=group, user__in=assigning_users
            ).exclude(company_id__in=company_ids).delete()

        CompanyGroupAssignment.objects.bulk_create(
            [
                CompanyGroupAssignment(user=user, company=company, group=group)
                for user in assigning_users
                for company in companies
            ],
            ignore_conflicts=True,
        )

        for user in assigning_users:
            CompanyGroupAssignment.sync_user_group_membership(user, group)

        return group


class AddToUserGroupForm(Form):
    """
    Form to add employee in to  groups
    """

    group = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=False)
    employee = forms.ModelChoiceField(queryset=Employee.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)

    def save(self):
        """
        Save method to assign the selected groups to the employee
        """
        from base.models import CompanyGroupAssignment

        employee = self.cleaned_data["employee"]
        groups = self.cleaned_data["group"]
        user = employee.employee_user_id
        user.groups.clear()
        CompanyGroupAssignment.objects.filter(user=user).delete()
        companies = list(Company.objects.all())
        assignments = []
        for group in groups:
            user.groups.add(group)
            for company in companies:
                assignments.append(
                    CompanyGroupAssignment(user=user, company=company, group=group)
                )
        CompanyGroupAssignment.objects.bulk_create(assignments, ignore_conflicts=True)
        return employee


class AssignPermission(Form):
    """
    Forms to assign user permision
    """

    employee = HorillaMultiSelectField(
        queryset=Employee.objects.all(),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
            required=True,
        ),
        label="Employee",
    )
    try:
        permissions = forms.MultipleChoiceField(
            error_messages={
                "required": "Please choose a permission.",
            },
        )
    except:
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)

        # Dynamically load permission choices only when DB is ready
        try:
            self.fields["permissions"].choices = [
                (perm.codename, perm.name) for perm in Permission.objects.all()
            ]
        except Exception:
            # Fallback in case the DB isn't ready yet
            self.fields["permissions"].choices = []

    def clean(self):
        emps = self.data.getlist("employee")
        if emps:
            self.errors.pop("employee", None)
        super().clean()
        return

    def save(self):
        """
        Save method to assign permission to employee
        """
        user_ids = Employee.objects.filter(
            id__in=self.data.getlist("employee")
        ).values_list("employee_user_id", flat=True)
        permissions = self.cleaned_data["permissions"]
        permissions = Permission.objects.filter(codename__in=permissions)
        users = HorillaUser.objects.filter(id__in=user_ids)
        for user in users:
            user.user_permissions.add(*permissions)

        return self


class CompanyForm(ModelForm):
    """
    Company model's form
    """

    cols = {
        "company": 12,
        "address": 12,
        "country": 12,
        "state": 12,
        "city": 12,
        "zip": 12,
    }

    class Meta:
        """
        Meta class for additional options
        """

        model = Company
        fields = "__all__"
        exclude = ["date_format", "time_format", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icon"].required = False

    def validate_image(self, file):
        max_size = 5 * 1024 * 1024

        if file.size > max_size:
            raise ValidationError(_("File size should be less than 5MB."))

        # Check file extension
        valid_extensions = [".jpg", ".jpeg", ".png", ".webp", ".svg"]
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in valid_extensions:
            raise ValidationError(_("Unsupported file extension."))

    def clean_icon(self):
        icon = self.cleaned_data.get("icon")
        if icon:
            self.validate_image(icon)
        return icon


class DepartmentForm(ModelForm):
    """
    Department model's form
    """

    manager = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        required=False,
        label=_("Manager"),
        help_text=_(
            "Assigning a manager here also reflects in the Helpdesk"
            " department managers section."
        ),
    )

    cols = {"department": 12, "company_id": 12, "manager": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = Department
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Manager can be any employee, not just current members of this
        # department -- so both create and update keep the field's own
        # default queryset (Employee.objects.all()), letting the "All
        # Company" session context surface every employee in every company
        # instead of narrowing to whoever's already assigned to this
        # department.
        if self.instance.pk and apps.is_installed("helpdesk"):
            from helpdesk.models import DepartmentManager

            existing = DepartmentManager.objects.filter(
                department=self.instance
            ).first()
            if existing:
                self.fields["manager"].initial = existing.manager_id

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data

    def save(self, commit=True):
        department = super().save(commit=commit)
        if commit and apps.is_installed("helpdesk"):
            from helpdesk.models import DepartmentManager

            manager = self.cleaned_data.get("manager")
            DepartmentManager.objects.filter(department=department).delete()
            if manager:
                DepartmentManager.objects.create(department=department, manager=manager)
        return department


class JobPositionForm(ModelForm):
    """
    JobPosition model's form
    """

    department_id = forms.ModelMultipleChoiceField(
        queryset=Department.objects.all(),
        label="Department",
        widget=forms.SelectMultiple(
            attrs={"class": "oh-select oh-select2 w-100", "style": "height:45px;"}
        ),
    )

    cols = {"job_position": 12, "department_id": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = JobPosition
        fields = "__all__"
        exclude = ["is_active", "department_id", "company_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["department_id"] = forms.ModelChoiceField(
                queryset=self.fields["department_id"].queryset,
                label="Department",
                widget=forms.Select(
                    attrs={
                        "class": "oh-select oh-select2 w-100",
                        "style": "height:45px;",
                    }
                ),
            )

    def clean(self):
        """
        Perform custom validation.
        """
        cleaned_data = super().clean()
        job_position = cleaned_data.get("job_position")
        department_ids = cleaned_data.get("department_id")

        if department_ids and not hasattr(department_ids, "__iter__"):
            department_ids = [department_ids]

        if self.instance.pk and job_position and department_ids:
            for department_id in department_ids:
                if (
                    JobPosition.objects.filter(
                        department_id=department_id, job_position=job_position
                    )
                    .exclude(pk=self.instance.pk)
                    .exists()
                ):
                    raise ValidationError(
                        _(
                            f"Job position '{job_position}' already exists under department {department_id}"
                        )
                    )

        return cleaned_data

    def save(self, commit, *args, **kwargs) -> Any:
        if not self.instance.pk:
            request = getattr(_thread_locals, "request")
            department = Department.objects.filter(
                id__in=self.data.getlist("department_id")
            )
            positions = []
            for dep in department:
                position = JobPosition()
                position.department_id = dep
                position.job_position = self.data["job_position"]
                form_data = self.data["job_position"]
                if JobPosition.objects.filter(
                    department_id=dep, job_position=form_data
                ).exists():
                    messages.error(
                        request,
                        _("Job position already exists under %(dep)s") % {"dep": dep},
                    )
                else:
                    messages.success(
                        request, _("Job position has been created successfully!")
                    )
                    position.save()
                positions.append(position.pk)
            return JobPosition.objects.filter(id__in=positions)
        super().save(commit, *args, **kwargs)


class JobPositionMultiForm(ModelForm):
    """
    JobPosition model's form
    """

    department_id = HorillaMultiSelectField(
        queryset=Department.objects.all(),
        label=JobPosition._meta.get_field("department_id").verbose_name,
        widget=forms.SelectMultiple(
            attrs={
                "class": "oh-select oh-select2 w-100",
                "style": "height:45px;",
            }
        ),
    )

    class Meta:
        model = JobPosition
        fields = "__all__"
        exclude = ["department_id", "is_active"]

    def clean(self):
        """
        Validate that the job position does not already exist in the selected departments.
        """
        cleaned_data = super().clean()
        department_ids = self.data.getlist("department_id")
        job_position = self.data.get("job_position")

        existing_positions = JobPosition.objects.filter(
            department_id__in=department_ids, job_position=job_position
        )

        if existing_positions.exists():
            existing_deps = existing_positions.values_list("department_id", flat=True)
            dep_names = Department.objects.filter(id__in=existing_deps).values_list(
                "department", flat=True
            )
            raise ValidationError(
                {
                    "department_id": _("Job position already exists under {}").format(
                        ", ".join(dep_names)
                    )
                }
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        """
        Save the job positions for each selected department.
        """
        if not self.instance.pk:
            request = getattr(_thread_locals, "request")
            department_ids = self.data.getlist("department_id")
            job_position = self.data.get("job_position")
            positions = []

            for dep_id in department_ids:
                dep = Department.objects.get(id=dep_id)
                if JobPosition.objects.filter(
                    department_id=dep, job_position=job_position
                ).exists():
                    messages.error(
                        request,
                        _("Job position already exists under %(dep)s") % {"dep": dep},
                    )
                else:
                    position = JobPosition(department_id=dep, job_position=job_position)
                    position.save()
                    positions.append(position.pk)

            return JobPosition.objects.filter(id__in=positions)
        return super().save(*args, **kwargs)


class JobRoleForm(ModelForm):
    """
    JobRole model's form
    """

    job_position_id = forms.ModelMultipleChoiceField(
        queryset=JobPosition.objects.all(),
        label="Job Position",
        widget=forms.SelectMultiple(
            attrs={
                "class": "w-100 oh-select",
                "style": "height:45px;",
            }
        ),
    )

    cols = {"job_position_id": 12, "job_role": 12}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            job_position_id = forms.ModelChoiceField(
                queryset=self.fields["job_position_id"].queryset,
                label="Job Position",
                widget=forms.Select(
                    attrs={
                        "class": "w-100 oh-select",
                        "style": "height:45px;",
                    }
                ),
            )
            self.fields["job_position_id"] = job_position_id

    class Meta:
        """
        Meta class for additional options
        """

        model = JobRole
        fields = "__all__"
        exclude = ["is_active", "job_position_id", "company_id"]

    def clean(self):
        cleaned_data = super().clean()
        job_position_id = cleaned_data.get("job_position_id")
        job_role = cleaned_data.get("job_role")

        if job_position_id and not hasattr(job_position_id, "__iter__"):
            job_position_id = [job_position_id]

        if self.instance.pk and job_position_id and job_role:
            existing_roles = JobRole.objects.filter(
                job_position_id__in=job_position_id, job_role=job_role
            ).exclude(pk=self.instance.pk)
            if existing_roles.exists():
                raise ValidationError(
                    f"{job_role} already exists under this job position"
                )
        return cleaned_data

    def save(self, commit, *args, **kwargs) -> Any:
        if not self.instance.pk:
            request = getattr(_thread_locals, "request")
            job_positions = JobPosition.objects.filter(
                id__in=self.data.getlist("job_position_id")
            )
            roles = []
            for position in job_positions:
                role = JobRole()
                role.job_position_id = position
                role.job_role = self.data["job_role"]
                try:
                    role.save()
                    messages.success(
                        request, _("Job role has been created successfully!")
                    )
                except:
                    messages.info(
                        request,
                        _("Role already exists under %(position)s")
                        % {"position": position},
                    )
                roles.append(role.pk)
            return JobRole.objects.filter(id__in=roles)
        super().save(commit, *args, **kwargs)


class WorkTypeForm(ModelForm):
    """
    WorkType model's form
    """

    cols = {"work_type": 12, "company_id": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = WorkType
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            from base.auth_backends import resolve_company_id_for_new_record

            company_id = resolve_company_id_for_new_record()
            if company_id:
                self.initial["company_id"] = Company.objects.filter(id=company_id)


class RotatingWorkTypeForm(ModelForm):
    """
    RotatingWorkType model's form
    """

    cols = {
        "name": 12,
        "work_type1": 12,
        "work_type2": 12,
    }

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingWorkType
        fields = "__all__"
        exclude = ["employee_id", "is_active"]
        widgets = {
            "start_date": DateInput(attrs={"type": "date"}),
            "additional_data": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        work_type_counts = 0

        def create_work_type_field(work_type_key, required, initial=None, label=""):

            self.fields[work_type_key] = forms.ModelChoiceField(
                queryset=WorkType.objects.all(),
                widget=CustomModelChoiceWidget(
                    delete_url="/add-remove-work-type-fields",
                    attrs={
                        "class": "oh-select oh-select-2 mb-3 ",
                        "name": work_type_key,
                        "id": f"id_{work_type_key}",
                    },
                ),
                required=required,
                empty_label=_("---Choose Work Type---"),
                initial=initial,
                label=label,
            )

        for key in self.data.keys():
            if key.startswith("work_type"):
                work_type_counts += 1
                # work_type1/work_type2 already carry their model verbose_name
                # label; preserve it instead of blanking it out like the
                # dynamically added (3rd+) work type fields.
                existing_field = self.fields.get(key)
                label = existing_field.label if existing_field else ""
                create_work_type_field(key, work_type_counts <= 2, label=label)

        if not self.is_bound:
            # Unbound form (initial GET): work_type1 and work_type2 always
            # exist as base fields. When editing an existing instance, its
            # saved additional work types (from self.initial, populated by
            # ModelForm from the instance) seed the extra fields here. Once
            # the form is bound (POST, valid or invalid-reload), the loop
            # above already rebuilt every work_type field from what was
            # actually submitted, so this stale, DB-only snapshot must not
            # run and clobber that count/fields with outdated data.
            work_type_counts = 2
            additional_data = self.initial.get("additional_data")
            additional_work_types = (
                additional_data.get("additional_work_types")
                if additional_data
                else None
            )
            if additional_work_types:
                for work_type_id in additional_work_types:
                    work_type_counts += 1
                    create_work_type_field(
                        f"work_type{work_type_counts}",
                        False,
                        initial=work_type_id,
                    )

        self.work_type_counts = work_type_counts
        # Every work_type field (base or dynamically added) should render
        # full width; relying on client-side JS to fix this up after the
        # fact is fragile, so drive it from the same col() lookup the
        # template already uses for every other field.
        self.cols = {
            **self.cols,
            **{f"work_type{i}": 12 for i in range(1, work_type_counts + 1)},
        }

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string(
            "base/rotating_work_type/htmx/rotating_work_type_as_p.html", context
        )

    def clean(self):
        cleaned_data = super().clean()
        additional_work_types = []
        model_fields = list(self.instance.__dict__.keys())

        for key, value in self.data.items():
            if (
                f"{key}_id" not in model_fields
                and key.startswith("work_type")
                and value
            ):
                additional_work_types.append(value)

        if additional_work_types:
            if (
                "additional_data" not in cleaned_data
                or cleaned_data["additional_data"] is None
            ):
                cleaned_data["additional_data"] = {}
            cleaned_data["additional_data"][
                "additional_work_types"
            ] = additional_work_types

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("additional_data"):
            if instance.additional_data is None:
                instance.additional_data = {}
            instance.additional_data["additional_work_types"] = self.cleaned_data[
                "additional_data"
            ].get("additional_work_types")
        else:
            instance.additional_data = None

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RotatingWorkTypeAssignForm(ModelForm):
    """
    RotatingWorkTypeAssign model's form
    """

    cols = {
        "employee_id": 12,
        "rotating_work_type_id": 12,
        "start_date": 12,
        "based_on": 12,
        "rotate_after_day": 12,
        "rotate_every_weekend": 12,
        "rotate_every": 12,
    }

    # employee_id = HorillaMultiSelectField(
    #     queryset=Employee.objects.filter(employee_work_info__isnull=False),
    #     widget=HorillaMultiSelectWidget(
    #         filter_route_name="employee-widget-filter",
    #         filter_class=EmployeeFilter,
    #         filter_instance_context_name="f",
    #         filter_template_path="employee_filters.html",
    #     ),
    #     label=_("Employees"),
    # )
    based_on = forms.ChoiceField(choices=BASED_ON, initial="daily", label=_("Based on"))
    rotate_after_day = forms.IntegerField(initial=5, label=_("Rotate after day"))
    start_date = forms.DateField(
        initial=date.today, widget=forms.DateInput, label=_("Start date")
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingWorkTypeAssign
        fields = "__all__"
        exclude = [
            "next_change_date",
            "current_work_type",
            "next_work_type",
            "is_active",
            "additional_data",
        ]
        widgets = {
            "start_date": DateInput(attrs={"type": "date"}),
            "is_active": HiddenInput(),
        }
        labels = {
            "is_active": _("Is Active"),
            "rotate_every_weekend": _("Rotate every weekend"),
            "rotate_every": _("Rotate every"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        request = getattr(_thread_locals, "request", None)
        self.fields["employee_id"].initial = request.GET.get("emp_id")
        if not self.instance.pk and not request.GET.get("emp_id"):
            self.fields["employee_id"] = HorillaMultiSelectField(
                queryset=Employee.objects.filter(
                    employee_work_info__isnull=False, is_active=True
                ),
                widget=HorillaMultiSelectWidget(
                    filter_route_name="employee-widget-filter",
                    filter_class=EmployeeFilter,
                    filter_instance_context_name="f",
                    filter_template_path="employee_filters.html",
                ),
                label=_("Employees"),
            )

    def clean_employee_id(self):
        if self.instance.pk:
            return self.cleaned_data.get("employee_id")
        else:
            employee_ids = self.cleaned_data.get("employee_id")
            if isinstance(employee_ids, Employee):
                return employee_ids
            else:
                if employee_ids:
                    return employee_ids[0]
                else:
                    return ValidationError(_("This field is required"))

    def clean(self):
        if self.instance.pk:
            return super().clean()

        super().clean()
        self.instance.employee_id = Employee.objects.filter(
            id=self.data.get("employee_id")
        ).first()

        self.errors.pop("employee_id", None)
        if self.data.getlist("employee_id"):
            raise ValidationError({"employee_id": _("This field is required")})
        super().clean()
        cleaned_data = super().clean()
        if "rotate_after_day" in self.errors:
            del self.errors["rotate_after_day"]
        return cleaned_data

    def save(self, commit=False, manager=None):

        day_name = self.cleaned_data["rotate_every_weekend"]
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        target_day = day_names.index(day_name.lower())

        if self.instance.pk:
            employee = Employee.objects.get(id=self.instance.pk)
            rotating_work_type_assign = RotatingWorkTypeAssign()
            rotating_work_type = RotatingWorkType.objects.get(
                id=self.data["rotating_work_type_id"]
            )
            rotating_work_type_assign.next_change_date = self.cleaned_data["start_date"]
            rotating_work_type_assign.current_work_type = (
                employee.employee_work_info.work_type_id
            )
            rotating_work_type_assign.next_work_type = rotating_work_type.work_type1
            rotating_work_type_assign.additional_data["next_work_type_index"] = 1
            based_on = self.cleaned_data["based_on"]
            start_date = self.instance.start_date
            if based_on == "weekly":
                next_date = get_next_week_date(target_day, start_date)
                self.instance.next_change_date = next_date
            elif based_on == "monthly":
                rotate_every = self.instance.rotate_every  # 0, 1, 2, ..., 31, or "last"
                start_date = self.instance.start_date
                next_date = get_next_monthly_date(start_date, rotate_every)
                self.instance.next_change_date = next_date
            elif based_on == "after":
                self.instance.next_change_date = self.instance.start_date + timedelta(
                    days=int(self.data.get("rotate_after_day"))
                )
            return super().save()

        else:
            employee_ids = self.data.getlist("employee_id")
            rotating_work_type = RotatingWorkType.objects.get(
                id=self.data["rotating_work_type_id"]
            )
            for employee_id in employee_ids:
                employee = Employee.objects.filter(id=employee_id).first()
                rotating_work_type_assign = RotatingWorkTypeAssign()
                rotating_work_type_assign.rotating_work_type_id = rotating_work_type
                rotating_work_type_assign.employee_id = employee
                rotating_work_type_assign.based_on = self.cleaned_data["based_on"]
                rotating_work_type_assign.start_date = self.cleaned_data["start_date"]
                rotating_work_type_assign.next_change_date = self.cleaned_data[
                    "start_date"
                ]
                rotating_work_type_assign.rotate_after_day = self.data.get(
                    "rotate_after_day"
                )
                rotating_work_type_assign.rotate_every = self.cleaned_data[
                    "rotate_every"
                ]
                rotating_work_type_assign.rotate_every_weekend = self.cleaned_data[
                    "rotate_every_weekend"
                ]
                rotating_work_type_assign.next_change_date = self.cleaned_data[
                    "start_date"
                ]
                rotating_work_type_assign.current_work_type = (
                    employee.employee_work_info.work_type_id
                )
                rotating_work_type_assign.next_work_type = rotating_work_type.work_type2
                rotating_work_type_assign.additional_data["next_shift_index"] = 1
                based_on = self.cleaned_data["based_on"]
                start_date = self.cleaned_data["start_date"]
                if based_on == "weekly":
                    next_date = get_next_week_date(target_day, start_date)
                    rotating_work_type_assign.next_change_date = next_date
                elif based_on == "monthly":
                    # 0, 1, 2, ..., 31, or "last"
                    rotate_every = self.cleaned_data["rotate_every"]
                    start_date = self.cleaned_data["start_date"]
                    next_date = get_next_monthly_date(start_date, rotate_every)
                    rotating_work_type_assign.next_change_date = next_date
                elif based_on == "after":
                    rotating_work_type_assign.next_change_date = (
                        rotating_work_type_assign.start_date
                        + timedelta(days=int(self.data.get("rotate_after_day")))
                    )

                rotating_work_type_assign.save()


class RotatingWorkTypeAssignUpdateForm(forms.ModelForm):
    """
    RotatingWorkTypeAssign model's form
    """

    based_on = forms.ChoiceField(choices=BASED_ON, initial="daily", label=_("Based on"))

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingWorkTypeAssign
        fields = "__all__"
        exclude = [
            "next_change_date",
            "current_work_type",
            "next_work_type",
            "is_active",
            "additional_data",
        ]
        widgets = {
            "start_date": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "start_date": _("Start date"),
            "rotate_after_day": _("Rotate after day"),
            "rotate_every_weekend": _("Rotate every weekend"),
            "rotate_every": _("Rotate every"),
            "based_on": _("Based on"),
            "is_active": _("Is Active"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        for field_name, field in self.fields.items():
            if field.required:
                self.fields[field_name].label_suffix = " *"

        self.fields["rotate_every_weekend"].widget.attrs.update(
            {
                "class": "w-100",
                "style": "display:none; height:50px; border-radius:0;border:1px\
                    solid hsl(213deg,22%,84%);",
                "data-hidden": True,
            }
        )
        self.fields["rotate_every"].widget.attrs.update(
            {
                "class": "w-100",
                "style": "display:none; height:50px; border-radius:0;border:1px \
                    solid hsl(213deg,22%,84%);",
                "data-hidden": True,
            }
        )
        self.fields["rotate_after_day"].widget.attrs.update(
            {
                "class": "w-100 oh-input",
                "style": " height:50px; border-radius:0;",
            }
        )
        self.fields["based_on"].widget.attrs.update(
            {
                "class": "w-100",
                "style": " height:50px; border-radius:0; border:1px solid \
                    hsl(213deg,22%,84%);",
            }
        )
        self.fields["start_date"].widget = forms.DateInput(
            attrs={
                "class": "w-100 oh-input",
                "type": "date",
                "style": " height:50px; border-radius:0;",
            }
        )
        self.fields["rotating_work_type_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2",
            }
        )
        self.fields["employee_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2",
            }
        )

    def save(self, *args, **kwargs):
        day_name = self.cleaned_data["rotate_every_weekend"]
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        target_day = day_names.index(day_name.lower())

        based_on = self.cleaned_data["based_on"]
        start_date = self.instance.start_date
        if based_on == "weekly":
            next_date = get_next_week_date(target_day, start_date)
            self.instance.next_change_date = next_date
        elif based_on == "monthly":
            rotate_every = self.instance.rotate_every  # 0, 1, 2, ..., 31, or "last"
            start_date = self.instance.start_date
            next_date = get_next_monthly_date(start_date, rotate_every)
            self.instance.next_change_date = next_date
        elif based_on == "after":
            self.instance.next_change_date = self.instance.start_date + timedelta(
                days=int(self.data.get("rotate_after_day"))
            )
        return super().save()


class EmployeeTypeForm(ModelForm):
    """
    EmployeeType form
    """

    cols = {"employee_type": 12, "company_id": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeType
        fields = "__all__"
        exclude = ["is_active"]


class EmployeeShiftForm(ModelForm):
    """
    EmployeeShift Form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeShift
        fields = "__all__"
        exclude = ["days", "is_active", "weekly_full_time", "full_time"]


class EmployeeShiftScheduleUpdateForm(ModelForm):
    """
    EmployeeShiftSchedule model's form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeShiftSchedule
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")

        if instance:
            self.fields["start_time"].initial = (
                instance.start_time.strftime("%H:%M") if instance.start_time else None
            )
            self.fields["end_time"].initial = (
                instance.end_time.strftime("%H:%M") if instance.end_time else None
            )
            if apps.is_installed("attendance"):
                self.fields["auto_punch_out_time"].initial = (
                    instance.auto_punch_out_time.strftime("%H:%M")
                    if instance.auto_punch_out_time
                    else None
                )

        if not apps.is_installed("attendance"):
            self.fields.pop("auto_punch_out_time", None)
            self.fields.pop("is_auto_punch_out_enabled", None)
        else:
            self.fields["auto_punch_out_time"].widget = forms.TimeInput(
                attrs={"type": "time", "class": "oh-input w-100 form-control"}
            )
            self.fields["is_auto_punch_out_enabled"].widget.attrs.update(
                {"onchange": "toggleDivVisibility(this)"}
            )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """

        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()
        if apps.is_installed("attendance"):
            auto_punch_out_enabled = cleaned_data.get("is_auto_punch_out_enabled")
            auto_punch_out_time = cleaned_data.get("auto_punch_out_time")
            end_time = cleaned_data.get("end_time")

            if auto_punch_out_enabled:
                if not auto_punch_out_time:
                    raise ValidationError(
                        {
                            "auto_punch_out_time": _(
                                "Automatic punch out time is required when automatic punch out is enabled."
                            )
                        }
                    )
                elif auto_punch_out_time < end_time:
                    raise ValidationError(
                        {
                            "auto_punch_out_time": _(
                                "Automatic punch out time cannot be earlier than the end time."
                            )
                        }
                    )

        return cleaned_data


class EmployeeShiftScheduleForm(ModelForm):
    """
    EmployeeShiftSchedule model's form
    """

    cols = {"day": 12}

    day = forms.ModelMultipleChoiceField(
        queryset=EmployeeShiftDay.objects.all(),
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeShiftSchedule
        fields = "__all__"
        exclude = ["is_active", "day"]
        widgets = {
            "start_time": forms.TimeInput(),
            "end_time": forms.TimeInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["end_time"].initial = None
        if self.instance.pk:
            self.fields["day"] = forms.ModelChoiceField(
                queryset=EmployeeShiftDay.objects.all(),
                widget=forms.Select(
                    attrs={
                        "class": "oh-select oh-select2 w-100",
                        "style": "height:45px;",
                    }
                ),
            )
        self.fields["day"].widget.attrs.update({"id": str(uuid.uuid4())})
        self.fields["shift_id"].widget.attrs.update({"id": str(uuid.uuid4())})
        if not apps.is_installed("attendance"):
            self.fields.pop("auto_punch_out_time", None)
            self.fields.pop("is_auto_punch_out_enabled", None)
        else:
            self.fields["auto_punch_out_time"].widget = forms.TimeInput(
                attrs={"type": "time", "class": "oh-input w-100 form-control"}
            )
            self.fields["is_auto_punch_out_enabled"].widget.attrs.update(
                {"onchange": "toggleDivVisibility(this)"}
            )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """

        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()
        if apps.is_installed("attendance"):
            auto_punch_out_enabled = self.cleaned_data["is_auto_punch_out_enabled"]
            auto_punch_out_time = self.cleaned_data["auto_punch_out_time"]
            end_time = self.cleaned_data["end_time"]
            if auto_punch_out_enabled:
                if not auto_punch_out_time:
                    raise ValidationError(
                        {
                            "auto_punch_out_time": _(
                                "Automatic punch out time is required when automatic punch out is enabled."
                            )
                        }
                    )
            if auto_punch_out_enabled and auto_punch_out_time and end_time:
                if auto_punch_out_time < end_time:
                    raise ValidationError(
                        {
                            "auto_punch_out_time": _(
                                "Automatic punch out time cannot be earlier than the end time."
                            )
                        }
                    )
        if self.instance.pk:
            shift_id = cleaned_data.get("shift_id")
            day_field = self["day"].value()
            if day_field and not hasattr(day_field, "__iter__"):
                day_field = [day_field]

            if self.instance.pk and shift_id and day_field:
                shift = EmployeeShiftSchedule.objects.filter(
                    day=day_field, shift_id=shift_id
                )
                shifts = shift.first()
                if shift.exclude(pk=self.instance.pk).exists():
                    raise ValidationError(
                        _(
                            f"Shift schedule already exists for '{shifts.day}' on '{shift_id}' "
                        )
                    )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not self.instance.pk:
            for day in self.data.getlist("day"):
                # if int(day) != int(instance.day.id):
                data_copy = self.data.copy()
                data_copy.update({"day": str(day)})
                shift_schedule = EmployeeShiftScheduleUpdateForm(data_copy).save(
                    commit=False
                )
                shift_schedule.save()
        return instance

    def clean_day(self):
        """
        Validation to day field
        """
        if not self.instance.pk:
            days = self.cleaned_data["day"]
            for day in days:
                attendance = EmployeeShiftSchedule.objects.filter(
                    day=day, shift_id=self.data["shift_id"]
                ).first()
                if attendance is not None:
                    raise ValidationError(
                        _("Shift schedule is already exist for {day}").format(
                            day=_(day.day)
                        )
                    )
            if days.first() is None:
                raise ValidationError(_("Employee not chosen"))
            return days.first()


class RotatingShiftForm(ModelForm):
    """
    RotatingShift model's form
    """

    cols = {"name": 12, "shift1": 12, "shift2": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingShift
        fields = "__all__"
        exclude = ["employee_id", "is_active"]
        widgets = {"additional_data": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        shift_counts = 0

        def create_shift_field(shift_key, required, initial=None):
            self.fields[shift_key] = forms.ModelChoiceField(
                queryset=EmployeeShift.objects.all(),
                widget=CustomModelChoiceWidget(
                    delete_url="/add-remove-shift-fields",
                    attrs={
                        "class": "oh-select oh-select-2 mb-3",
                        "name": shift_key,
                        "id": f"id_{shift_key}",
                    },
                ),
                required=required,
                empty_label=_("---Choose Shift---"),
                initial=initial,
            )

        # for field in self.fields:
        #     if field.startswith("shift"):
        #         shift_counts += 1
        #         create_shift_field(field, shift_counts <= 2)

        for key in self.data.keys():
            if key.startswith("shift") and self.data[key]:
                shift_counts += 1
                create_shift_field(key, shift_counts <= 2)

        additional_data = self.initial.get("additional_data")
        additional_shifts = (
            additional_data.get("additional_shifts") if additional_data else None
        )
        if additional_shifts:
            shift_counts = 3
            for shift_id in additional_shifts:
                create_shift_field(
                    f"shift{shift_counts}", shift_counts <= 2, initial=shift_id
                )
                shift_counts += 1

        self.shift_counts = shift_counts

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string(
            "base/rotating_shift/htmx/rotating_shift_as_p.html", context
        )

    def clean(self):
        cleaned_data = super().clean()
        additional_shifts = []
        model_fields = list(self.instance.__dict__.keys())

        for key, value in self.data.items():
            if f"{key}_id" not in model_fields and key.startswith("shift") and value:
                additional_shifts.append(value)

        if additional_shifts:
            if (
                "additional_data" not in cleaned_data
                or cleaned_data["additional_data"] is None
            ):
                cleaned_data["additional_data"] = {}
            cleaned_data["additional_data"]["additional_shifts"] = additional_shifts

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("additional_data"):
            if instance.additional_data is None:
                instance.additional_data = {}
            instance.additional_data["additional_shifts"] = self.cleaned_data[
                "additional_data"
            ].get("additional_shifts")
        else:
            instance.additional_data = None

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RotatingShiftAssignForm(ModelForm):
    """
    RotatingShiftAssign model's form
    """

    cols = {
        "employee_id": 12,
        "rotating_shift_id": 12,
        "start_date": 12,
        "based_on": 12,
        "rotate_after_day": 12,
        "rotate_every_weekend": 12,
        "rotate_every": 12,
    }

    # employee_id = HorillaMultiSelectField(
    #     queryset=Employee.objects.filter(employee_work_info__isnull=False),
    #     widget=HorillaMultiSelectWidget(
    #         filter_route_name="employee-widget-filter",
    #         filter_class=EmployeeFilter,
    #         filter_instance_context_name="f",
    #         filter_template_path="employee_filters.html",
    #     ),
    #     label=_("Employees"),
    # )
    based_on = forms.ChoiceField(choices=BASED_ON, initial="daily", label=_("Based on"))
    rotate_after_day = forms.IntegerField(initial=5, label=_("Rotate after day"))
    start_date = forms.DateField(
        initial=date.today, widget=forms.DateInput, label=_("Start date")
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingShiftAssign
        fields = "__all__"
        exclude = [
            "next_change_date",
            "current_shift",
            "next_shift",
            "is_active",
            "additional_data",
        ]
        widgets = {
            "start_date": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "rotating_shift_id": _("Rotating Shift"),
            "start_date": _("Start date"),
            "is_active": _("Is Active"),
            "rotate_every_weekend": _("Rotate every weekend"),
            "rotate_every": _("Rotate every"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        request = getattr(_thread_locals, "request", None)
        self.fields["employee_id"].initial = request.GET.get("emp_id")
        if not self.instance.pk and not request.GET.get("emp_id"):
            self.fields["employee_id"] = HorillaMultiSelectField(
                queryset=Employee.objects.filter(
                    employee_work_info__isnull=False, is_active=True
                ),
                widget=HorillaMultiSelectWidget(
                    filter_route_name="employee-widget-filter",
                    filter_class=EmployeeFilter,
                    filter_instance_context_name="f",
                    filter_template_path="employee_filters.html",
                ),
                label=_("Employees"),
            )

    def clean_employee_id(self):
        """
        Validation to employee_id field
        """
        if self.instance.pk:
            return self.cleaned_data.get("employee_id")
        else:
            employee_ids = self.cleaned_data.get("employee_id")
            if isinstance(employee_ids, Employee):
                return employee_ids
            else:
                if employee_ids:
                    return employee_ids[0]
                else:
                    return ValidationError(_("This field is required"))

    def clean(self):
        if self.instance.pk:
            return super().clean()
        super().clean()
        self.instance.employee_id = Employee.objects.filter(
            id=self.data.get("employee_id")
        ).first()

        self.errors.pop("employee_id", None)
        if not self.data.getlist("employee_id"):
            raise ValidationError({"employee_id": _("This field is required")})
        super().clean()
        cleaned_data = super().clean()
        if "rotate_after_day" in self.errors:
            del self.errors["rotate_after_day"]
        return cleaned_data

    def save(self, commit=False):
        day_name = self.cleaned_data["rotate_every_weekend"]
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        target_day = day_names.index(day_name.lower())

        if self.instance.pk:
            based_on = self.cleaned_data["based_on"]
            start_date = self.instance.start_date
            if based_on == "weekly":
                next_date = get_next_week_date(target_day, start_date)
                self.instance.next_change_date = next_date
            elif based_on == "monthly":
                rotate_every = self.instance.rotate_every  # 0, 1, 2, ..., 31, or "last"
                start_date = self.instance.start_date
                next_date = get_next_monthly_date(start_date, rotate_every)
                self.instance.next_change_date = next_date
            elif based_on == "after":
                self.instance.next_change_date = self.instance.start_date + timedelta(
                    days=int(self.data.get("rotate_after_day"))
                )
            return super().save()
        else:
            employee_ids = self.data.getlist("employee_id")
            rotating_shift = RotatingShift.objects.get(
                id=self.data["rotating_shift_id"]
            )
            for employee_id in employee_ids:
                employee = Employee.objects.filter(id=employee_id).first()
                rotating_shift_assign = RotatingShiftAssign()
                rotating_shift_assign.rotating_shift_id = rotating_shift
                rotating_shift_assign.employee_id = employee
                rotating_shift_assign.based_on = self.cleaned_data["based_on"]
                rotating_shift_assign.start_date = self.cleaned_data["start_date"]
                rotating_shift_assign.next_change_date = self.cleaned_data["start_date"]
                rotating_shift_assign.rotate_after_day = self.data.get(
                    "rotate_after_day"
                )
                rotating_shift_assign.rotate_every = self.cleaned_data["rotate_every"]
                rotating_shift_assign.rotate_every_weekend = self.cleaned_data[
                    "rotate_every_weekend"
                ]
                rotating_shift_assign.next_change_date = self.cleaned_data["start_date"]
                rotating_shift_assign.current_shift = (
                    employee.employee_work_info.shift_id
                )
                rotating_shift_assign.next_shift = rotating_shift.shift1
                rotating_shift_assign.additional_data["next_shift_index"] = 1
                based_on = self.cleaned_data["based_on"]
                start_date = self.cleaned_data["start_date"]
                if based_on == "weekly":
                    next_date = get_next_week_date(target_day, start_date)
                    rotating_shift_assign.next_change_date = next_date
                elif based_on == "monthly":
                    # 0, 1, 2, ..., 31, or "last"
                    rotate_every = self.cleaned_data["rotate_every"]
                    start_date = self.cleaned_data["start_date"]
                    next_date = get_next_monthly_date(start_date, rotate_every)
                    rotating_shift_assign.next_change_date = next_date
                elif based_on == "after":
                    rotating_shift_assign.next_change_date = (
                        rotating_shift_assign.start_date
                        + timedelta(days=int(self.data.get("rotate_after_day")))
                    )
                rotating_shift_assign.save()


class RotatingShiftAssignUpdateForm(ModelForm):
    """
    RotatingShiftAssign model's form
    """

    based_on = forms.ChoiceField(choices=BASED_ON, initial="daily", label=_("Based on"))

    class Meta:
        """
        Meta class for additional options
        """

        model = RotatingShiftAssign
        fields = "__all__"
        exclude = [
            "next_change_date",
            "current_shift",
            "next_shift",
            "is_active",
            "additional_data",
        ]
        widgets = {
            "start_date": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "start_date": _("Start date"),
            "rotate_after_day": _("Rotate after day"),
            "rotate_every_weekend": _("Rotate every weekend"),
            "rotate_every": _("Rotate every"),
            "based_on": _("Based on"),
            "is_active": _("Is Active"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        for field_name, field in self.fields.items():
            if field.required:
                self.fields[field_name].label_suffix = " *"

        self.fields["rotate_every_weekend"].widget.attrs.update(
            {
                "class": "w-100 ",
                "style": "display:none; height:50px; border-radius:0; border:1px \
                    solid hsl(213deg,22%,84%);",
                "data-hidden": True,
            }
        )
        self.fields["rotate_every"].widget.attrs.update(
            {
                "class": "w-100 ",
                "style": "display:none; height:50px; border-radius:0; border:1px \
                    solid hsl(213deg,22%,84%);",
                "data-hidden": True,
            }
        )
        self.fields["rotate_after_day"].widget.attrs.update(
            {
                "class": "w-100 oh-input",
                "style": " height:50px; border-radius:0;",
            }
        )
        self.fields["based_on"].widget.attrs.update(
            {
                "class": "w-100",
                "style": " height:50px; border-radius:0; border:1px solid hsl(213deg,22%,84%);",
            }
        )
        self.fields["start_date"].widget = forms.DateInput(
            attrs={
                "class": "w-100 oh-input",
                "type": "date",
                "style": " height:50px; border-radius:0;",
            }
        )
        self.fields["rotating_shift_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2",
            }
        )
        self.fields["employee_id"].widget.attrs.update(
            {
                "class": "oh-select oh-select-2",
            }
        )

    def save(self, *args, **kwargs):
        day_name = self.cleaned_data["rotate_every_weekend"]
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        target_day = day_names.index(day_name.lower())

        based_on = self.cleaned_data["based_on"]
        start_date = self.instance.start_date
        if based_on == "weekly":
            next_date = get_next_week_date(target_day, start_date)
            self.instance.next_change_date = next_date
        elif based_on == "monthly":
            rotate_every = self.instance.rotate_every  # 0, 1, 2, ..., 31, or "last"
            start_date = self.instance.start_date
            next_date = get_next_monthly_date(start_date, rotate_every)
            self.instance.next_change_date = next_date
        elif based_on == "after":
            self.instance.next_change_date = self.instance.start_date + timedelta(
                days=int(self.data.get("rotate_after_day"))
            )
        return super().save()


class ShiftRequestForm(ModelForm):
    """
    ShiftRequest model's form
    """

    cols = {"description": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = ShiftRequest
        fields = "__all__"
        exclude = [
            "reallocate_to",
            "approved",
            "canceled",
            "reallocate_approved",
            "reallocate_canceled",
            "previous_shift_id",
            "is_active",
            "shift_changed",
        ]
        widgets = {
            "requested_date": DateInput(attrs={"type": "date"}),
            "requested_till": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "description": _("Description"),
            "requested_date": _("Requested Date"),
            "requested_till": _("Requested Till"),
        }

    required_fields = ["requested_till"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def save(self, commit: bool = ...):
        if not self.instance.approved:
            employee = self.instance.employee_id
            if hasattr(employee, "employee_work_info"):
                self.instance.previous_shift_id = employee.employee_work_info.shift_id
                if self.instance.is_permanent_shift:
                    self.instance.requested_till = None
        return super().save(commit)

    # here set default filter for all the employees those have work information filled.


class ShiftAllocationForm(ModelForm):
    """
    ShiftRequest model's form
    """

    cols = {"description": 12}

    class Meta:
        """
        Meta class for additional options
        """

        model = ShiftRequest
        fields = "__all__"
        exclude = (
            "is_permanent_shift",
            "approved",
            "canceled",
            "reallocate_approved",
            "reallocate_canceled",
            "previous_shift_id",
            "is_active",
            "shift_changed",
        )
        widgets = {
            "requested_date": DateInput(attrs={"type": "date"}),
            "requested_till": DateInput(attrs={"type": "date", "required": "true"}),
        }

        labels = {
            "description": _("Description"),
            "requested_date": _("Requested Date"),
            "requested_till": _("Requested Till"),
        }

    required_fields = ["requested_till"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shift_id"].widget.attrs.update(
            {
                "hx-target": "#id_reallocate_to_parent_div",
                "hx-trigger": "change",
                "hx-swap": "innerHTML",
                "hx-get": "/update-employee-allocation",
            }
        )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def save(self, commit: bool = ...):
        if not self.instance.approved:
            employee = self.instance.employee_id
            if hasattr(employee, "employee_work_info"):
                self.instance.previous_shift_id = employee.employee_work_info.shift_id
                if not self.instance.requested_till:
                    self.instance.requested_till = (
                        employee.employee_work_info.contract_end_date
                    )
        return super().save(commit)


class WorkTypeRequestForm(ModelForm):
    """
    WorkTypeRequest model's form
    """

    cols = {"description": 12}
    required_fields = ["requested_till"]

    class Meta:
        """
        Meta class for additional options
        """

        model = WorkTypeRequest
        fields = "__all__"
        exclude = (
            "approved",
            "canceled",
            "previous_work_type_id",
            "is_active",
            "work_type_changed",
        )
        widgets = {
            "requested_date": DateInput(attrs={"type": "date"}),
            "requested_till": DateInput(attrs={"type": "date"}),
        }
        labels = {
            "requested_date": _("Requested Date"),
            "requested_till": _("Requested Till"),
            "description": _("Description"),
        }

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html

    def save(self, commit: bool = ...):
        if not self.instance.approved:
            employee = self.instance.employee_id
            if hasattr(employee, "employee_work_info"):
                self.instance.previous_work_type_id = (
                    employee.employee_work_info.work_type_id
                )
                if self.instance.is_permanent_work_type:
                    self.instance.requested_till = None
        return super().save(commit)


class ChangePasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_("Old password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": _("Enter Old Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
        help_text=_("Enter your old password."),
    )
    new_password = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": _("Enter New Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
    )
    confirm_password = forms.CharField(
        label=_("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": _("Re-Enter Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(ChangePasswordForm, self).__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get("old_password")
        if not self.user.check_password(old_password):
            raise forms.ValidationError(_("Incorrect old password."))
        return old_password

    def clean_new_password(self):
        new_password = self.cleaned_data.get("new_password")
        if self.user.check_password(new_password):
            raise forms.ValidationError(
                _("New password must be different from the old password.")
            )

        return new_password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")
        if new_password and confirm_password and new_password != confirm_password:
            raise ValidationError(
                {"new_password": _("New password and confirm password do not match")}
            )

        return cleaned_data


class ChangeUsernameForm(forms.Form):
    old_username = forms.CharField(
        label=_("Old Username"),
        strip=False,
        widget=forms.TextInput(
            attrs={
                "readonly": "readonly",
                "class": "oh-input oh-input--text w-100 mb-2",
            }
        ),
    )

    username = forms.CharField(
        label=_("Username"),
        strip=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": _("Enter New Username"),
                "class": "oh-input oh-input--text w-100 mb-2",
            }
        ),
        help_text=_("Enter your username."),
    )

    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": _("Enter Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
        help_text=_("Enter your password."),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(ChangeUsernameForm, self).__init__(*args, **kwargs)

    def clean_password(self):
        username = self.cleaned_data.get("username")
        if HorillaUser.objects.filter(username=username).exists():
            raise forms.ValidationError(_("Username already exists."))
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password):
            raise forms.ValidationError(_("Incorrect password."))
        return password


class ResetPasswordForm(SetPasswordForm):
    """
    ResetPasswordForm
    """

    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": _("Enter Strong Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
        help_text=_("Enter your new password."),
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": _("Re-Enter Password"),
                "class": "oh-input oh-input--password w-100 mb-2",
            }
        ),
        help_text=_("Enter the same password as before, for verification."),
    )

    def save(self, commit=True):
        if self.is_valid():
            request = getattr(_thread_locals, "request", None)
            if request:
                messages.success(request, _("Password changed successfully"))
        return super().save()

    def clean_confirm_password(self):
        """
        validation method for confirm password field
        """
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("confirm_password")
        if password == confirm_password:
            return confirm_password
        raise forms.ValidationError(_("Password must be same."))


excluded_fields = [
    "id",
    "is_active",
    "reallocate_approved",
    "reallocate_canceled",
    "shift_changed",
    "work_type_changed",
    "created_at",
    "created_by",
    "modified_by",
    "additional_data",
    "horilla_history",
    "additional_data",
]


class ShiftRequestColumnForm(forms.Form):
    model_fields = ShiftRequest._meta.get_fields()
    field_choices = [
        (field.name, field.verbose_name)
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in excluded_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "shift_id",
            "requested_date",
            "requested_till",
            "previous_shift_id",
            "approved",
        ],
    )


class WorkTypeRequestColumnForm(forms.Form):
    model_fields = WorkTypeRequest._meta.get_fields()
    field_choices = [
        (field.name, field.verbose_name)
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in excluded_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "work_type_id",
            "requested_date",
            "requested_till",
            "previous_shift_id",
            "approved",
        ],
    )


class RotatingShiftAssignExportForm(forms.Form):
    model_fields = RotatingShiftAssign._meta.get_fields()
    field_choices = [
        (field.name, field.verbose_name)
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in excluded_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "rotating_shift_id",
            "start_date",
            "next_change_date",
            "current_shift",
            "next_shift",
            "based_on",
        ],
    )


class RotatingWorkTypeAssignExportForm(forms.Form):
    model_fields = RotatingWorkTypeAssign._meta.get_fields()
    field_choices = [
        (field.name, field.verbose_name)
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in excluded_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "rotating_work_type_id",
            "start_date",
            "next_change_date",
            "current_work_type",
            "next_work_type",
            "based_on",
        ],
    )


class TagsForm(ModelForm):
    """
    Tags form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = Tags
        fields = "__all__"
        widgets = {"color": TextInput(attrs={"type": "color", "style": "height:50px"})}
        exclude = ["objects", "is_active"]

    def as_p(self, *args, **kwargs):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html


class EmployeeTagForm(ModelForm):
    """
    Employee Tags form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = EmployeeTag
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {"color": TextInput(attrs={"type": "color", "style": "height:50px"})}


class AuditTagForm(ModelForm):
    """
    Audit Tags form
    """

    cols = {
        "title": 12,
    }

    class Meta:
        """
        Meta class for additional options
        """

        model = AuditTag
        fields = "__all__"


class ShiftRequestCommentForm(ModelForm):
    """
    Shift request comment form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = ShiftRequestComment
        fields = ("comment",)


class WorkTypeRequestCommentForm(ModelForm):
    """
    WorkType request comment form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = WorkTypeRequestComment
        fields = ("comment",)


class DynamicMailConfForm(ModelForm):
    """
    DynamicEmailConfiguration
    """

    class Meta:
        model = DynamicEmailConfiguration
        fields = "__all__"
        exclude = ["is_active"]

    # def clean(self):
    #     from_mail = self.from_email
    #     return super().clean()
    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("horilla_form.html", context)
        return table_html


class DynamicMailTestForm(forms.Form):
    """
    DynamicEmailTest
    """

    to_email = forms.EmailField(label=_("To email"), required=True)


class MailTemplateForm(ModelForm):
    """
    MailTemplateForm
    """

    cols = {"title": 12, "body": 12, "company_id": 12}

    class Meta:
        model = HorillaMailTemplate
        fields = "__all__"
        widgets = {
            "body": forms.Textarea(
                attrs={"data-summernote": "", "style": "display:none;"}
            ),
            "is_active": forms.HiddenInput(),
        }

    def clean_body(self):
        body = self.cleaned_data.get("body", "")

        ALLOWED_TAGS = [
            "p",
            "b",
            "i",
            "u",
            "strong",
            "em",
            "ul",
            "ol",
            "li",
            "br",
            "hr",
            "table",
            "thead",
            "tbody",
            "tr",
            "td",
            "th",
            "a",
            "span",
        ]

        ALLOWED_ATTRIBUTES = {
            "a": ["href", "title"],
            "span": ["style"],
        }

        cleaned_body = bleach.clean(
            body, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True
        )

        return cleaned_body

    def get_template_language(self):
        mail_data = {
            "Receiver|Full name": "instance.get_full_name",
            "Sender|Full name": "self.get_full_name",
            "Receiver|Recruitment": "instance.recruitment_id",
            "Sender|Recruitment": "self.recruitment_id",
            "Receiver|Company": "instance.get_company",
            "Sender|Company": "self.get_company",
            "Receiver|Job position": "instance.get_job_position",
            "Sender|Job position": "self.get_job_position",
            "Receiver|Email": "instance.get_mail",
            "Sender|Email": "self.get_mail",
            "Receiver|Employee Type": "instance.get_employee_type",
            "Sender|Employee Type": "self.get_employee_type",
            "Receiver|Work Type": "instance.get_work_type",
            "Sender|Work Type": "self.get_work_type",
            "Candidate|Full name": "instance.get_full_name",
            "Candidate|Recruitment": "instance.recruitment_id",
            "Candidate|Company": "instance.get_company",
            "Candidate|Job position": "instance.get_job_position",
            "Candidate|Email": "instance.get_email",
            "Candidate|Interview Table": "instance.get_interview|safe",
        }
        return mail_data

    def get_employee_template_language(self):
        mail_data = {
            "Receiver|Full name": "instance.get_full_name",
            "Sender|Full name": "self.get_full_name",
            "Receiver|Recruitment": "instance.recruitment_id",
            "Sender|Recruitment": "self.recruitment_id",
            "Receiver|Company": "instance.get_company",
            "Sender|Company": "self.get_company",
            "Receiver|Job position": "instance.get_job_position",
            "Sender|Job position": "self.get_job_position",
            "Receiver|Email": "instance.get_mail",
            "Sender|Email": "self.get_mail",
            "Receiver|Employee Type": "instance.get_employee_type",
            "Sender|Employee Type": "self.get_employee_type",
            "Receiver|Work Type": "instance.get_work_type",
            "Sender|Work Type": "self.get_work_type",
        }
        return mail_data


class MultipleApproveConditionForm(ModelForm):

    cols = {
        "multi_approval_manager": 12,
    }

    CONDITION_CHOICE = [
        ("equal", _("Equal (==)")),
        ("notequal", _("Not Equal (!=)")),
        ("range", _("Range")),
        ("lt", _("Less Than (<)")),
        ("gt", _("Greater Than (>)")),
        ("le", _("Less Than or Equal To (<=)")),
        ("ge", _("Greater Than or Equal To (>=)")),
        ("icontains", _("Contains")),
    ]

    multi_approval_manager = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 mb-2"}),
        label=_("Approval Manager"),
        required=True,
    )
    condition_operator = forms.ChoiceField(
        choices=CONDITION_CHOICE,
        widget=forms.Select(
            attrs={
                "class": "oh-select oh-select-2 mb-2",
                "hx-trigger": "change",
                "hx-target": "#conditionValueDiv",
                "hx-get": "condition-value-fields",
            },
        ),
        label=_("Condition Operator"),
    )

    class Meta:
        model = MultipleApprovalCondition
        fields = "__all__"
        exclude = [
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("reporting_manager_id", _("Reporting Manager"))] + [
            (employee.pk, str(employee)) for employee in Employee.objects.all()
        ]
        self.fields["multi_approval_manager"].choices = choices


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [
                single_file_clean(data, initial),
            ]
        return result[0] if result else None


class AnnouncementForm(ModelForm):
    """
    Announcement Form
    """

    employees = HorillaMultiSelectField(
        queryset=Employee.objects.all(),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label="Employees",
        help_text=_(
            "If no employee, department or job position is selected, the announcement will be visible to all employees in the selected company."
        ),
    )

    cols = {
        "title": 12,
        "description": 12,
        "attachments": 12,
        "expire_date": 12,
        "employees": 12,
        "department": 12,
        "job_position": 12,
    }

    required_fields = ["description"]

    class Meta:
        """
        Meta class for additional options
        """

        model = Announcement
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"data-summernote": ""}),
            "expire_date": DateInput(attrs={"type": "date"}),
        }

    def clean_description(self):
        description = self.cleaned_data.get("description", "").strip()
        # Remove HTML tags and check if there's meaningful content
        text_content = strip_tags(description).strip()
        if not text_content:  # Checks if the field is empty after stripping HTML
            raise forms.ValidationError(_("Description is required."))
        return description

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachments"] = MultipleFileField(label=_("Attachments"))
        self.fields["attachments"].required = False
        self.fields["description"].required = False
        self.fields["disable_comments"].widget.attrs.update(
            {"hx-on:click": "togglePublicComments()"}
        )
        if not self.instance.pk:
            request = getattr(_thread_locals, "request", None)
            selected_company = (
                request.session.get("selected_company") if request else None
            )
            if not selected_company or selected_company == "all":
                company = None
            else:
                company = Company.objects.filter(id=selected_company).first()
            expire_setting = AnnouncementExpire.objects.filter(
                company_id=company
            ).first()
            if not expire_setting and company is not None:
                expire_setting = AnnouncementExpire.objects.filter(
                    company_id=None
                ).first()
            general_expire_date = (
                expire_setting.days
                if expire_setting and expire_setting.days is not None
                else 30
            )
            self.fields["expire_date"].initial = date.today() + timedelta(
                days=general_expire_date
            )

    def save(self, commit: bool = ...) -> Any:
        attachement = []
        multiple_attachment_ids = []
        attachements = None
        if self.files.getlist("attachments"):
            attachements = self.files.getlist("attachments")
            self.instance.attachement = attachements[0]
            multiple_attachment_ids = []

            for attachement in attachements:
                file_instance = Attachment()
                file_instance.file = attachement
                file_instance.save()
                multiple_attachment_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.attachements.add(*multiple_attachment_ids)
        return instance, multiple_attachment_ids

    def as_p(self, *args, **kwargs):
        context = {"form": self}
        return render_to_string("announcement/as_p.html", context)

    def clean(self):
        cleaned_data = super().clean()

        # Remove 'employees' field error if it's handled manually
        if isinstance(self.fields["employees"], HorillaMultiSelectField):
            self.errors.pop("employees", None)
            employee_data = self.fields["employees"].queryset.filter(
                id__in=self.data.getlist("employees")
            )
            cleaned_data["employees"] = employee_data

        # Get submitted M2M values
        employees_selected = cleaned_data.get("employees")
        departments_selected = self.cleaned_data.get("department")
        job_positions_selected = self.cleaned_data.get("job_position")

        # Check if none of the three are selected
        # if (
        #     not employees_selected
        #     and not departments_selected
        #     and not job_positions_selected
        # ):
        #     raise forms.ValidationError(
        #         _(
        #             "You must select at least one of: Employees, Department, or Job Position."
        #         )
        #     )

        return cleaned_data


class AnnouncementCommentForm(ModelForm):
    """
    Announcement comment form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = AnnouncementComment
        fields = ["comment"]


class DriverForm(forms.ModelForm):
    """
    DriverForm
    """

    class Meta:
        model = DriverViewed
        fields = "__all__"


UserModel = get_user_model()


class PassWordResetForm(forms.Form):
    email = forms.CharField()

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        """
        Send a django.core.mail.EmailMultiAlternatives to `to_email`.
        """
        subject = loader.render_to_string(subject_template_name, context)
        # Email subject *must not* contain newlines
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        email_message.send()

    def get_users(self, email):
        """
        Given an email, return matching user(s) who should receive a reset.

        This allows subclasses to more easily customize the default policies
        that prevent inactive users and users with unusable passwords from
        resetting their password.
        """
        email_field_name = UserModel.get_email_field_name()
        active_users = UserModel._default_manager.filter(
            **{
                "%s__iexact" % email_field_name: email,
                "is_active": True,
            }
        )
        return (
            u
            for u in active_users
            if u.has_usable_password()
            and _unicode_ci_compare(email, getattr(u, email_field_name))
        )

    def save(
        self,
        domain_override=None,
        subject_template_name="registration/password_reset_subject.txt",
        email_template_name="registration/password_reset_email.html",
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        """
        Generate a one-use only link for resetting password and send it to the
        user.
        """
        username = self.cleaned_data["email"]
        user = HorillaUser.objects.get(username=username)
        employee = user.employee_get
        email = employee.email
        work_mail = None
        try:
            work_mail = employee.employee_work_info.email
        except Exception as e:
            pass
        if work_mail:
            email = work_mail

        if not domain_override:
            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
        else:
            site_name = domain = domain_override
        if email:
            token = token_generator.make_token(user)
            context = {
                "email": email,
                "domain": domain,
                "site_name": site_name,
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                "token": token,
                "protocol": "https" if use_https else "http",
                **(extra_email_context or {}),
            }
            self.send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                email,
                html_email_template_name=html_email_template_name,
            )


def validate_ip_or_cidr(value):
    try:
        ipaddress.ip_address(value)
    except ValueError:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise ValidationError(
                f"{value} is not a valid IP address or CIDR notation."
            )


class AttendanceAllowedIPForm(forms.ModelForm):
    ip_addresses = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control oh-input"}),
        label=_("Allowed IP Addresses or Network Prefixes"),
        help_text=_(
            "Enter multiple IP addresses or network prefixes, separated by commas."
        ),
    )

    class Meta:
        model = AttendanceAllowedIP
        fields = ["ip_addresses"]

    def clean_ip_addresses(self):
        ip_addresses = self.cleaned_data.get("ip_addresses", "").strip().split("\n")
        cleaned_ips = []
        for ip in ip_addresses:
            ip = ip.strip().split(", ")
            if ip:
                for ip_addr in ip:
                    validate_ip_or_cidr(ip_addr)
                    cleaned_ips.append(ip_addr)
        return cleaned_ips

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.pk:
            existing_ips = set(instance.additional_data.get("allowed_ips", []))
            new_ips = set(self.cleaned_data["ip_addresses"])
            merged_ips = list(existing_ips.union(new_ips))
            instance.additional_data["allowed_ips"] = merged_ips
        else:
            instance.additional_data = {
                "allowed_ips": self.cleaned_data["ip_addresses"]
            }

        if commit:
            instance.save()

        return instance


class AttendanceAllowedIPUpdateForm(ModelForm):
    ip_address = forms.CharField(max_length=30, label="IP Address")

    class Meta:
        model = AttendanceAllowedIP
        fields = ["ip_address"]

    def validate_ip_address(self, value):
        try:
            validate_ipv46_address(value)
        except ValidationError:
            raise ValidationError(_("Enter a valid IPv4 or IPv6 address."))
        return value

    def clean(self):
        cleaned_data = super().clean()

        for field_name, value in self.data.items():
            cleaned_data[field_name] = self.validate_ip_address(value)

        return cleaned_data


class TrackLateComeEarlyOutForm(ModelForm):
    class Meta:
        model = TrackLateComeEarlyOut
        fields = ["is_enable", "company_id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_enable"].widget.attrs.update(
            {
                "hx-post": reverse_lazy("enable-disable-tracking-late-come-early-out"),
                "hx-target": "this",
                "hx-trigger": "change",
            }
        )


class HolidayForm(ModelForm):
    """
    Form for creating or updating a holiday.

    This form allows users to create or update holiday data by specifying details such as
    the start date and end date.

    Attributes:
        - start_date: A DateField representing the start date of the holiday.
        - end_date: A DateField representing the end date of the holiday.
    """

    cols = {"name": 12}

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_end_date(self):
        start_date = self.cleaned_data.get("start_date")
        end_date = self.cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise ValidationError(
                _("End date should not be earlier than the start date.")
            )
        return end_date

    def save(self, commit=True):
        instance = super().save(commit=False)
        departments = self.cleaned_data.get("department")
        job_positions = self.cleaned_data.get("job_position")
        direct_employees = self.cleaned_data.get("employees")
        instance.is_specific = bool(departments or job_positions or direct_employees)
        instance.assigning_type = None
        if commit:
            instance.save()
            instance.department.set(departments or [])
            instance.job_position.set(job_positions or [])
            if instance.is_specific:
                condition = Q(pk__in=[])
                if direct_employees:
                    condition |= Q(pk__in=direct_employees.values_list("pk", flat=True))
                if departments:
                    condition |= Q(employee_work_info__department_id__in=departments)
                if job_positions:
                    condition |= Q(
                        employee_work_info__job_position_id__in=job_positions
                    )
                expanded = Employee.objects.filter(condition, is_active=True).distinct()
                instance.employees.set(expanded)
            else:
                instance.employees.clear()
        return instance

    class Meta:
        model = Holidays
        fields = "__all__"
        exclude = ["is_active"]
        labels = {
            "name": _("Holiday Name"),
        }

    def __init__(self, *args, **kwargs):
        super(HolidayForm, self).__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["autocomplete"] = "name"
        self.fields["start_date"].label = (
            f"{self.Meta.model()._meta.get_field('start_date').verbose_name}"
        )
        self.fields["end_date"].label = (
            f"{self.Meta.model()._meta.get_field('end_date').verbose_name}"
        )
        self.fields["is_specific"].widget = forms.HiddenInput()
        self.fields["assigning_type"].widget = forms.HiddenInput()
        self.fields["assigning_type"].required = False
        self.fields["department"].required = False
        self.fields["job_position"].required = False
        self.fields["employees"].required = False
        self.fields["employees"].queryset = Employee.objects.filter(is_active=True)
        for fname in ("department", "job_position", "employees"):
            self.fields[fname].widget.attrs.update({"class": "oh-select oh-select-2"})
        reload_queryset(self.fields)


class HolidaysColumnExportForm(forms.Form):
    """
    Form for selecting columns to export in holiday data.
    """

    selected_fields = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        initial=[],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use a single model instance for dynamic verbose names
        model_instance = Holidays()
        meta = model_instance._meta

        field_choices = [
            (field.name, meta.get_field(field.name).verbose_name)
            for field in meta.fields
            if field.name not in excluded_fields
        ]

        self.fields["selected_fields"].choices = field_choices
        self.fields["selected_fields"].initial = [
            "name",
            "start_date",
            "end_date",
            "recurring",
        ]


class CompanyLeaveForm(ModelForm):
    """
    Form for managing company leave data.

    This form allows users to manage company leave data by including all fields from
    the CompanyLeaves model except for is_active.

    Attributes:
        - Meta: Inner class defining metadata options.
            - model: The model associated with the form (CompanyLeaves).
            - fields: A special value indicating all fields should be included in the form.
            - exclude: A list of fields to exclude from the form (is_active).
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = CompanyLeaves
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        """
        Custom initialization to configure the 'based_on' field.
        """
        super().__init__(*args, **kwargs)
        choices = [("", "All")] + list(self.fields["based_on_week"].choices[1:])
        self.fields["based_on_week"].choices = choices
        self.fields["based_on_week"].widget.option_template_name = (
            "horilla_widgets/select_option.html"
        )


class PenaltyAccountForm(ModelForm):
    """
    PenaltyAccountForm
    """

    class Meta:
        model = PenaltyAccounts
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        employee = kwargs.pop("employee", None)
        super().__init__(*args, **kwargs)
        if apps.is_installed("leave") and employee:
            LeaveType = get_horilla_model_class(app_label="leave", model="leavetype")
            available_leaves = employee.available_leave.all()
            assigned_leave_types = LeaveType.objects.filter(
                id__in=available_leaves.values_list("leave_type_id", flat=True)
            )
            self.fields["leave_type_id"].queryset = assigned_leave_types


# ---------------------------------------------------------------------------
# Roster Forms
# ---------------------------------------------------------------------------


class RosterCellUpdateForm(ModelForm):
    """
    Inline HTMX form for updating a single roster cell (shift / day-off / notes).
    """

    class Meta:
        model = Roster
        fields = ["shift", "is_off", "is_published", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shift"].required = False
