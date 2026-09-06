from typing import Any

from django import forms
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.auth_backends import (
    company_scoped_active,
    get_allowed_company_ids,
    resolve_company_id_for_new_record,
)
from base.forms import ModelForm
from base.models import Company
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals
from project.methods import employees_for_project

from .models import *


class ProjectForm(ModelForm):
    """
    Form for Project model
    """

    cols = {"description": 12}

    company_id = forms.ModelChoiceField(
        queryset=Company.objects.all(),
        required=False,
        label=_("Company"),
        widget=forms.HiddenInput(),
    )

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Project
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        selected_company = request.session.get("selected_company") if request else None
        company = self.instance.company_id if self.instance.pk else None

        if selected_company and selected_company != "all":
            # A specific company is active: the field stays hidden and locked
            # to that company, the project is auto-assigned to it on save.
            company = Company.objects.filter(id=selected_company).first() or company
            self.fields["company_id"].initial = company
            self.fields["company_id"].widget = forms.HiddenInput()
        elif not self.instance.pk:
            # "All Company" is active for a new project: reveal the selector
            # and require a company before employees can be picked.
            scoped = (
                company_scoped_active()
                and request is not None
                and request.user.is_authenticated
                and not request.user.is_superuser
            )
            queryset = Company.objects.all()
            if scoped:
                allowed_ids = get_allowed_company_ids(request.user)
                queryset = queryset.filter(id__in=allowed_ids or [])
            # The widget must be swapped in before the queryset is assigned:
            # ModelChoiceField.queryset's setter pushes `choices` onto
            # whichever widget is current at that moment.
            self.fields["company_id"].widget = forms.Select(
                attrs={
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                    "onchange": """
                        $('[name=dynamic_company]').val(this.value);
                        setTimeout(() => {
                            $('#getManagersButton').click();
                        }, 100);
                    """,
                }
            )
            self.fields["company_id"].queryset = queryset
            self.fields["company_id"].required = True
            submitted_company = self.data.get("company_id") if self.data else None
            if submitted_company:
                company = Company.objects.filter(id=submitted_company).first()
            else:
                # Pre-select a sensible default so Managers isn't left empty
                # on first load: the user's write company (non-superuser on
                # "All my companies"), falling back to the first company a
                # superuser is allowed to see.
                default_company_id = resolve_company_id_for_new_record(request)
                company = (
                    Company.objects.filter(id=default_company_id).first()
                    if default_company_id
                    else queryset.first()
                )
            if company:
                self.fields["company_id"].initial = company
        else:
            # Editing an existing project: the company is already fixed.
            self.fields["company_id"].widget = forms.HiddenInput()

        if company:
            self.fields["managers"].queryset = Employee.objects.filter(
                employee_work_info__company_id=company
            )
        elif not self.instance.pk:
            self.fields["managers"].queryset = Employee.objects.none()

        self.order_fields(["title", "company_id"])

    def save(self, commit=True):
        company = self.cleaned_data.get("company_id")
        if company:
            self.instance.company_id = company
        return super().save(commit)


class ProjectTimeSheetForm(ModelForm):
    """
    Form for Project model in Time sheet form
    """

    def __init__(self, *args, request=None, **kwargs):
        super(ProjectTimeSheetForm, self).__init__(*args, **kwargs)
        self.fields["managers"].widget.attrs.update({"id": "managers_id"})
        self.fields["status"].widget.attrs.update({"id": "status_id"})
        self.fields["title"].widget.attrs.update({"id": "id_project"})

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Project
        fields = "__all__"
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class TaskForm(ModelForm):
    """
    Form for Task model
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Task
        fields = "__all__"
        # exclude = ("project_id",)

        widgets = {
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "project": forms.HiddenInput(),
            "stage": forms.HiddenInput(),
            "sequence": forms.HiddenInput(),
        }


class QuickTaskForm(ModelForm):
    class Meta:
        model = Task
        fields = ["title", "task_managers", "project", "stage", "end_date"]
        widgets = {
            "project": forms.HiddenInput(),
            "stage": forms.HiddenInput(),
            "end_date": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(QuickTaskForm, self).__init__(*args, **kwargs)

        self.fields["title"].widget.attrs.update(
            {"class": "oh-input w-100 mb-2", "placeholder": _("Task Title")}
        )
        self.fields["task_managers"].required = True

        project = self.initial.get("project")
        if not isinstance(project, Project):
            project_value = project or (self.data.get("project") if self.data else None)
            project = (
                Project.objects.filter(pk=project_value).first()
                if project_value
                else None
            )
        self.fields["task_managers"].queryset = employees_for_project(project)


class TaskFormCreate(ModelForm):
    """
    Form for Task model in create button inside task view
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Task
        fields = "__all__"
        # exclude = ("project_id",)

        widgets = {
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "project": forms.HiddenInput(),
            "sequence": forms.HiddenInput(),
            "stage": forms.SelectMultiple(
                attrs={
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                    "onchange": "keyResultChange($(this))",
                }
            ),
        }

    def __init__(self, *args, request=None, **kwargs):
        super(TaskFormCreate, self).__init__(*args, **kwargs)
        self.fields["stage"].widget.attrs.update({"id": "project_stage"})

        project = self.initial.get("project")
        if not isinstance(project, Project):
            project_value = project or (self.data.get("project") if self.data else None)
            project = (
                Project.objects.filter(pk=project_value).first()
                if project_value
                else None
            )
        employees = employees_for_project(project)
        self.fields["task_managers"].queryset = employees
        self.fields["task_members"].queryset = employees

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class TaskAllForm(ModelForm):
    """
    Form for Task model in task all view
    """

    cols = {
        "description": 12,
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Task
        fields = "__all__"
        exclude = ["is_active"]

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "sequence": forms.HiddenInput(),
        }

    def __init__(self, *args, request=None, **kwargs):
        super(TaskAllForm, self).__init__(*args, **kwargs)
        request = getattr(_thread_locals, "request")

        self.fields["stage"].widget.attrs.update({"id": "project_stage"})
        self.fields["project"].widget.attrs.update(
            {
                "onchange": """
                    $('[name=dynamic_project]').val(this.value);
                    setTimeout(() => {
                        $('#getStageButton').click();
                        $('#getTaskManagersButton').click();
                        $('#getTaskMembersButton').click();
                    }, 100);
                """
            }
        )

        request = getattr(_thread_locals, "request", None)
        employee = request.user.employee_get
        if not self.instance.pk:
            if request.user.is_superuser or request.user.has_perm("project.add_task"):
                projects = Project.objects.all()
            elif Project.objects.filter(managers=employee).exists():
                projects = Project.objects.filter(managers=employee)
            else:
                projects = Project.objects.none()
            self.fields["project"].queryset = projects

        else:
            task = self.instance
            if request.user.is_superuser:
                projects = Project.objects.all()
            elif employee in task.project.managers.all():
                projects = Project.objects.filter(managers=employee)
            elif employee in task.task_managers.all():
                # Limit fields accessible to task managers
                projects = Project.objects.filter(id=self.instance.project.id)
                self.fields["project"].disabled = True
                self.fields["stage"].disabled = True
                self.fields["task_managers"].disabled = True
            else:
                projects = Project.objects.filter(id=self.instance.project.id)
            self.fields["project"].queryset = projects

        # Task Managers/Members must belong to the same company as the project
        project_value = self.data.get("project") if self.data else None
        if project_value:
            project = Project.objects.filter(pk=project_value).first()
        elif self.instance.pk:
            project = self.instance.project
        else:
            project = None
        employees = employees_for_project(project)
        self.fields["task_managers"].queryset = employees
        self.fields["task_members"].queryset = employees


class TimeSheetForm(ModelForm):
    """
    Form for Timesheet model
    """

    cols = {"description": 12}

    class Meta:
        """
        Meta class to add the additional info
        """

        model = TimeSheet
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, request=None, **kwargs):
        super(TimeSheetForm, self).__init__(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        employee = request.user.employee_get
        hx_trigger_value = "change" if self.instance.id else "load,change"
        if not self.initial.get("project_id") == "dynamic_create":
            self.fields["project_id"].widget.attrs.update(
                {
                    "hx-target": "#id_task_id_parent_div",
                    "hx-trigger": hx_trigger_value,
                    "hx-include": "#id_task_id",
                    "hx-swap": "innerHTML",
                    "hx-get": "/project/get-tasks-of-project/",
                }
            )
        self.fields["task_id"].widget.attrs.update(
            {
                "hx-target": "#id_employee_id_parent_div",
                "hx-include": "#id_project_id",
                "hx-trigger": hx_trigger_value,
                "hx-swap": "innerHTML",
                "hx-get": "/project/get-members-of-project/",
            }
        )

        if not request.user.has_perm("project.add_timesheet"):
            projects = Project.objects.filter(
                Q(managers=employee)
                | Q(task__task_members=employee)
                | Q(task__task_managers=employee)
            ).distinct()
            self.fields["project_id"].queryset = projects


class TimesheetInTaskForm(ModelForm):
    class Meta:
        """
        Meta class to add the additional info
        """

        model = TimeSheet
        fields = "__all__"
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "project_id": forms.HiddenInput(),
            "task_id": forms.HiddenInput(),
        }


class ProjectStageForm(ModelForm):
    """
    Form for Project stage model
    """

    cols = {
        "title": 12,
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = ProjectStage
        fields = "__all__"
        exclude = ["is_active"]

        widgets = {"project": forms.HiddenInput()}


class TaskTimeSheetForm(ModelForm):
    """
    Form for Task model in timesheet form
    """

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Task
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "project": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super(TaskTimeSheetForm, self).__init__(*args, **kwargs)
        # Add style to the start_date and end_date fields
        # self.fields["stage"].choices.append(
        #         ("create_new_project", "Create a new project")
        #     )
        self.fields["status"].widget.attrs.update(
            {
                "style": "width: 100%; height: 47px;",
                "class": "oh-select",
            }
        )
        self.fields["description"].widget.attrs.update(
            {
                "style": "width: 100%; height: 130px;",
                "class": "oh-select",
            }
        )
        self.fields["description"].widget.attrs.update(
            {
                "style": "width: 100%; height: 130px;",
                "class": "oh-select",
            }
        )

        self.fields["stage"].widget.attrs.update({"id": "project_stage"})
