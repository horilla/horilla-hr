"""
This page handles the cbv methods for task page
"""

import logging
from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from base.methods import get_subordinates
from employee.models import Employee
from horilla.http import HorillaRedirect
from horilla.methods import handle_no_permission
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.kanban import HorillaKanbanView
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from project.cbv.cbv_decorators import is_projectmanager_or_member_or_perms
from project.cbv.project_stage import StageDynamicCreateForm
from project.cbv.projects import DynamicProjectCreationFormView
from project.filters import TaskAllFilter
from project.forms import TaskAllForm
from project.methods import employees_for_project
from project.models import Project, ProjectStage, Task
from project.templatetags.taskfilters import task_crud_perm

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms(perm="project.view_task"), name="dispatch"
)
class TasksTemplateView(TemplateView):
    """
    view page of the task page
    """

    template_name = "cbv/tasks/task_template_view.html"


@method_decorator(login_required, name="dispatch")
class TaskListView(HorillaListView):
    """
    list view of the page
    """

    model = Task
    filter_class = TaskAllFilter
    action_method = "actions"

    header_attrs = {
        "action": """style="width:150px !important;" """,
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "task-list-container"
        self.search_url = reverse("tasks-list-view")

    def get_queryset(self):
        queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)
        if not self.request.user.has_perm("project.view_task"):
            employee_id = self.request.user.employee_get
            subordinates = get_subordinates(self.request)
            subordinate_ids = [subordinate.id for subordinate in subordinates]
            project = queryset.filter(
                Q(project__managers=employee_id)
                | Q(project__managers__in=subordinate_ids)
            )
            queryset = (
                queryset.filter(
                    Q(task_members=employee_id)
                    | Q(task_managers=employee_id)
                    | Q(task_members__in=subordinate_ids)
                    | Q(task_managers__in=subordinate_ids)
                )
                | project
            )
        return queryset.distinct()

    @cached_property
    def columns(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("title").verbose_name, "title"),
            (get_field("project").verbose_name, "project"),
            (get_field("stage").verbose_name, "stage"),
            (get_field("task_managers").verbose_name, "get_managers"),
            (get_field("task_members").verbose_name, "get_members"),
            (get_field("end_date").verbose_name, "end_date"),
            (get_field("status").verbose_name, "get_status_display"),
            (get_field("description").verbose_name, "get_description"),
        ]

    @cached_property
    def sortby_mapping(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("title").verbose_name, "title"),
            (get_field("project").verbose_name, "project__title"),
            (get_field("stage").verbose_name, "stage"),
            (get_field("end_date").verbose_name, "end_date"),
            (get_field("status").verbose_name, "status"),
        ]

    row_status_indications = [
        (
            "todo--dot",
            _("To Do"),
            """
                onclick="
                    $('#applyFilter').closest('form').find('[name=status]').val('to_do');
                    $('#applyFilter').click();
                "
            """,
        ),
        (
            "in-progress--dot",
            _("In progress"),
            """
                onclick="
                    $('#applyFilter').closest('form').find('[name=status]').val('in_progress');
                    $('#applyFilter').click();
                "
            """,
        ),
        (
            "completed--dot",
            _("Completed"),
            """
                onclick="
                    $('#applyFilter').closest('form').find('[name=status]').val('completed');
                    $('#applyFilter').click();
                "
            """,
        ),
        (
            "expired--dot",
            _("Expired"),
            """
                onclick="
                    $('#applyFilter').closest('form').find('[name=status]').val('expired');
                    $('#applyFilter').click();
                "
            """,
        ),
    ]

    row_status_class = "status-{status}"

    row_attrs = """
        hx-get='{task_detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """

    # Mirrors TasksNavBar.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Task Managers" and
    # "Task Members" are deliberately left out: they're ManyToManyFields,
    # and the nested engine's `values(*fields).annotate(Count("pk"))`
    # aggregate would fan out one row per related employee, double-
    # counting tasks with more than one manager/member assigned.
    nested_group_by_fields = [
        "project",
        "stage",
        "status",
        "is_active",
        "start_date",
        "end_date",
    ]


@method_decorator(login_required, name="dispatch")
class TasksNavBar(HorillaNavView):
    """
    navbar of teh page
    """

    group_by_fields = [
        "project",
        "stage",
        "status",
    ]
    default_group_by = "status"

    # Mirrors TaskListView.nested_group_by_fields
    nested_group_by_fields = [
        "project",
        "stage",
        "status",
        "is_active",
        "start_date",
        "end_date",
    ]
    filter_form_context_name = "form"
    filter_instance = TaskAllFilter()
    search_swap_target = "#listContainer"
    filter_body_template = "cbv/tasks/task_filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. TaskAllFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("tasks-list-view")
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse("tasks-list-view"),
                "attrs": f"""
                    title ='{_("List")}'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("tasks-card-view"),
                "attrs": f"""
                    title ='{_("Card")}'
                """,
            },
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.request.user.employee_get
        projects = Project.objects.all()
        managers = [
            manager for project in projects for manager in project.managers.all()
        ]
        if employee in managers or self.request.user.has_perm("project.add_task"):
            self.create_attrs = f"""
                onclick = "event.stopPropagation();"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('create-task-all')}"
            """

        if self.request.user.has_perm("project.view_task"):
            self.actions = [
                {
                    "action": _("Archive"),
                    "attrs": """
                        id="archiveTask",
                        style="cursor: pointer;"
                    """,
                },
                {
                    "action": _("Un-Archive"),
                    "attrs": """
                        id="unArchiveTask",
                        style="cursor: pointer;"
                    """,
                },
                {
                    "action": _("Delete"),
                    "attrs": """
                        class="oh-dropdown__link--danger"
                        data-action = "delete"
                        id="deleteTask"
                        style="cursor: pointer; color:red !important"
                    """,
                },
            ]
        context["actions"] = self.actions
        context["create_attrs"] = self.create_attrs
        return context


@method_decorator(login_required, name="dispatch")
class TaskCreateForm(HorillaFormView):
    """
    Form view for create and update tasks
    """

    model = Task
    form_class = TaskAllForm
    template_name = "cbv/tasks/task_form.html"
    new_display_title = _("Create") + " " + model._meta.verbose_name

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.request.user.has_perm("project.view_task"):
            self.dynamic_create_fields = [
                ("project", DynamicProjectCreationFormView),
                ("stage", StageDynamicCreateForm, ["project"]),
            ]

    def get(self, request, *args, pk=None, **kwargs):
        project_id = self.kwargs.get("project_id")
        stage_id = self.kwargs.get("stage_id")
        task_id = self.kwargs.get("pk")
        if not task_id and not Project.objects.exists():
            messages.error(request, _("Please create a project first."))
            return HorillaRedirect(request)

        if project_id:
            project = Project.objects.filter(id=project_id).first()
            if not project:
                messages.error(request, _("Project not found."))
                return HorillaRedirect(request)
        elif stage_id:
            stage = ProjectStage.objects.filter(id=stage_id).first()
            if not stage:
                messages.error(request, _("Stage not found."))
                return HorillaRedirect(request)
            project = stage.project
        elif task_id:
            task = Task.objects.filter(id=task_id).first()
            if not task:
                messages.error(request, _("Task not found."))
                return HorillaRedirect(request)
            project = task.project
        elif not task_id:
            return super().get(request, *args, pk=pk, **kwargs)
        if (
            request.user.employee_get in project.managers.all()
            or request.user.is_superuser
            or request.user.has_perm("project.add_task")
        ):
            self.dynamic_create_fields = [
                ("project", DynamicProjectCreationFormView),
                ("stage", StageDynamicCreateForm),
            ]
            return super().get(request, *args, pk=pk, **kwargs)
        elif task_id:
            if request.user.employee_get in task.task_managers.all():
                return super().get(request, *args, pk=pk, **kwargs)

        else:
            return handle_no_permission(request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_id = self.kwargs.get("project_id")
        stage_id = self.kwargs.get("stage_id")
        task_id = self.kwargs.get("pk")

        dynamic_project_id = self.request.GET.get("dynamic_project")

        if dynamic_project_id and dynamic_project_id != "dynamic_create":
            stages = ProjectStage.objects.filter(project=dynamic_project_id)
            attrs = self.form.fields["stage"].widget.attrs
            attrs["style"] = "width:100% !important;"
            self.form.fields["stage"].choices = (
                [("", _("Select Stage"))]
                + [(stage.pk, stage) for stage in stages]
                + [("dynamic_create", _("Dynamic Create"))]
            )
            dynamic_project = Project.objects.filter(id=dynamic_project_id).first()
            employees = employees_for_project(dynamic_project)
            self.form.fields["task_managers"].queryset = employees
            self.form.fields["task_members"].queryset = employees

        if task_id and not dynamic_project_id:
            task = self.form.instance
            stages = task.project.project_stages.all()
            self.form.fields["stage"].choices = (
                [("", _("Select Stage"))]
                + [(stage.pk, stage) for stage in stages]
                + [("dynamic_create", _("Dynamic Create"))]
            )

        if stage_id:
            stage = ProjectStage.objects.filter(id=stage_id).first()
            if stage:
                project = stage.project
                self.form.fields["stage"].initial = stage
                self.form.fields["stage"].choices = [(stage.id, stage.title)]
                self.form.fields["stage"].widget = forms.HiddenInput()
                self.form.fields["project"].initial = project
                self.form.fields["project"].choices = [(project.id, project.title)]
                self.form.fields["project"].widget = forms.HiddenInput()
                self.form.initial["project"] = project.pk
                self.form.initial["stage"] = stage.pk
                employees = employees_for_project(project)
                self.form.fields["task_managers"].queryset = employees
                self.form.fields["task_members"].queryset = employees
        elif project_id:
            project = Project.objects.get(id=project_id)
            self.form.fields["project"].initial = project
            self.form.fields["project"].choices = [(project.id, project.title)]
            stages = ProjectStage.objects.filter(project=project)
            self.form.fields["stage"].choices = [
                (stage.id, stage.title) for stage in stages
            ]
            employees = employees_for_project(project)
            self.form.fields["task_managers"].queryset = employees
            self.form.fields["task_members"].queryset = employees
        elif self.form.instance.pk:
            self.form_class.verbose_name = _("Update Task")
            if self.request.GET.get("project_task"):
                self.form.fields["project"].widget = forms.HiddenInput()
                self.form.fields["stage"].widget = forms.HiddenInput()
        else:
            if self.request.user.is_superuser:
                self.dynamic_create_fields = [
                    ("project", DynamicProjectCreationFormView),
                    ("stage", StageDynamicCreateForm, ["project"]),
                ]

        if project_id or stage_id:
            if (
                self.request.user.employee_get in project.managers.all()
                or self.request.user.is_superuser
            ):

                self.form.fields["project"].choices.append(
                    ("dynamic_create", "Dynamic create")
                )
                self.form.fields["stage"].choices.append(
                    ("dynamic_create", "Dynamic create")
                )

        return context

    def form_valid(self, form: TaskAllForm) -> HttpResponse:
        stage_id = self.kwargs.get("stage_id")
        if form.is_valid():
            if form.instance.pk:
                message = _(f"{self.form.instance} Updated")
            else:
                message = _("New Task created")
            form.save()
            messages.success(self.request, _(message))
            if stage_id or self.request.GET.get("project_task"):
                return HorillaRedirect(self.request)
            return self.HttpResponse("<script>$('#applyFilter').click();</script>")
        return super().form_valid(form)


class DynamicTaskCreateFormView(TaskCreateForm):

    is_dynamic_create_view = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET:
            project_id = self.request.GET.get("project_id")
            if project_id:
                project = Project.objects.get(id=project_id)
                stages = ProjectStage.objects.filter(project__id=project_id)
                self.form.fields["project"].initial = project
                self.form.fields["project"].choices = [(project.id, project.title)]
                self.form.fields["stage"].queryset = stages
                employees = employees_for_project(project)
                self.form.fields["task_managers"].queryset = employees
                self.form.fields["task_members"].queryset = employees
                # self.form.fields["project"].widget = forms.HiddenInput()
        return context


@method_decorator(login_required, name="dispatch")
class TaskDetailView(HorillaDetailedView):
    """
    detail view of the task page
    """

    model = Task
    title = _("Task Details")
    action_method = "detail_view_actions"
    header = {"title": "title", "subtitle": "project", "avatar": "get_avatar"}

    @cached_property
    def body(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("project").verbose_name, "project"),
            (get_field("stage").verbose_name, "stage"),
            (get_field("task_managers").verbose_name, "get_managers"),
            (get_field("task_members").verbose_name, "get_members"),
            (get_field("status").verbose_name, "get_status_display"),
            (get_field("end_date").verbose_name, "end_date"),
            (get_field("document").verbose_name, "document_col", True),
            (get_field("description").verbose_name, "description"),
        ]

    cols = {
        "get_managers": 12,
        "get_members": 12,
        "description": 12,
    }


@method_decorator(login_required, name="dispatch")
class TaskCardView(HorillaKanbanView):
    """
    kanban card view of the page, with tasks arranged into columns by status
    """

    model = Task
    filter_class = TaskAllFilter
    disable_group_by = True
    filter_keys_to_remove = ["field"]
    group_key = "status"
    show_kanban_confirmation = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "task-card"
        self.search_url = reverse("tasks-card-view")
        self.actions = [
            {
                "action": _("Edit"),
                "accessibility": "project.cbv.accessibility.task_crud_accessibility",
                "attrs": """
                    data-toggle = "oh-modal-toggle"
                    data-target = "#genericModal"
                    hx-target="#genericModalBody"
                    hx-get ='{get_update_url}'
                    class="oh-dropdown__link"
                    style="cursor: pointer;"
                """,
            },
            {
                "action": _("archive_status"),
                "accessibility": "project.cbv.accessibility.task_crud_accessibility",
                "attrs": """
                    hx-get="{get_archive_url}"
                    hx-target="#listContainer"
                    hx-swap="innerHTML"
                    hx-confirm="Do you want to {archive_status} this task?"
                    onclick="event.stopPropagation()"
                    class="oh-dropdown__link"
                """,
            },
            {
                "action": _("Delete"),
                "accessibility": "project.cbv.accessibility.task_crud_accessibility",
                "attrs": """
                    hx-post="{get_delete_url}"
                    hx-target="#listContainer"
                    hx-swap="innerHTML"
                    hx-confirm="Do you want Delete this Task ?"
                    onclick="event.stopPropagation()"
                    class="oh-dropdown__link oh-dropdown__link--danger"
                """,
            },
        ]

    def get_queryset(self):
        self.queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        self.queryset = self.queryset.filter(is_active=active)
        if not self.request.user.has_perm("project.view_task"):
            employee_id = self.request.user.employee_get
            subordinates = get_subordinates(self.request)
            subordinate_ids = [subordinate.id for subordinate in subordinates]
            project = self.queryset.filter(
                Q(project__managers=employee_id)
                | Q(project__managers__in=subordinate_ids)
            )
            self.queryset = (
                self.queryset.filter(
                    Q(task_members=employee_id)
                    | Q(task_managers=employee_id)
                    | Q(task_members__in=subordinate_ids)
                    | Q(task_managers__in=subordinate_ids)
                )
                | project
            )
        self.queryset = self.queryset.distinct()
        return self.queryset

    details = {
        "image_src": "{get_avatar}",
        "title": "{title}",
        "Project": "{if_project}",
        "Stage": "{stage}",
        "End Date": "{end_date}",
    }

    kanban_attrs = """
        hx-get='{task_detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
class TasksInIndividualView(TaskListView):

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        employee_id = self.request.GET.get("employee_id")
        self.row_attrs = f"""
            hx-get='{{task_detail_view}}?instance_ids={{ordered_ids}}&employee_id={employee_id}'
            hx-target="#genericModalBody"
            data-target="#genericModal"
            data-toggle="oh-modal-toggle"
        """

    def get_queryset(self):
        queryset = super().get_queryset()
        employee_id = self.request.GET.get("employee_id")
        project_id = self.request.GET.get("project_id")
        queryset = queryset.filter(
            Q(task_members=employee_id) | Q(task_managers=employee_id)
        )
        queryset = queryset.filter(project=project_id).distinct()
        return queryset

    sortby_mapping = []
    header_attrs = {
        "title": """ style="width: 150px !important;" """,
    }

    show_filter_tags = False
    row_status_indications = None
    bulk_select_option = False
    action_method = None
    custom_empty_template = "cbv/projects/compact_empty.html"
