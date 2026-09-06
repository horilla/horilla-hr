"""
CBV of timesheet page
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import resolve, reverse
from django.utils.decorators import method_decorator
from django.utils.formats import localize
from django.utils.functional import cached_property
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from project.cbv.cbv_decorators import is_projectmanager_or_member_or_perms
from project.cbv.projects import DynamicProjectCreationFormView
from project.cbv.tasks import DynamicTaskCreateFormView
from project.filters import TimeSheetFilter
from project.forms import TimeSheetForm
from project.models import Project, Task, TimeSheet


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetView(TemplateView):
    """
    for timesheet page
    """

    template_name = "cbv/timesheet/timesheet.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetNavView(HorillaNavView):
    """
    Nav bar
    """

    filter_form_context_name = "form"
    filter_instance = TimeSheetFilter()
    search_swap_target = "#listContainer"
    template_name = "cbv/timesheet/timesheet_nav.html"
    filter_body_template = "cbv/timesheet/filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. TimeSheetFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True
    group_by_fields = [
        "employee_id",
        "project_id",
        "date",
        "status",
        "employee_id__employee_work_info__reporting_manager_id",
        "employee_id__employee_work_info__department_id",
        "employee_id__employee_work_info__job_position_id",
        "employee_id__employee_work_info__employee_type_id",
        "employee_id__employee_work_info__company_id",
    ]

    # Mirrors TimeSheetList.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split).
    nested_group_by_fields = [
        "employee_id",
        "project_id",
        "task_id",
        "date",
        "status",
        "employee_id__employee_work_info__reporting_manager_id",
        "employee_id__employee_work_info__department_id",
        "employee_id__employee_work_info__job_position_id",
        "employee_id__employee_work_info__employee_type_id",
        "employee_id__employee_work_info__company_id",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("time-sheet-list")
        self.actions = [
            {
                "action": _("Delete"),
                "attrs": """
                    class="oh-dropdown__link--danger"
                    data-action ="delete"
                    onclick="deleteTimeSheet();"
                    style="cursor: pointer; color:red !important"
                    """,
            },
        ]
        self.create_attrs = f"""
                                onclick = "event.stopPropagation();"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-target="#genericModalBody"
                                hx-get="{reverse('create-time-sheet')}"
                                """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        url = f"{reverse('personal-time-sheet-view',kwargs={'emp_id': self.request.user.employee_get.id})}"
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse("time-sheet-list"),
                "attrs": f"""
                        title ='{_("List")}'
                        """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("time-sheet-card"),
                "attrs": f"""
                          title ='{_("Card")}'
                          """,
            },
            {
                "type": "graph",
                "icon": "bar-chart",
                "url": url,
                "attrs": f"""
                          title ='Graph'
                          """,
            },
        ]
        context["view_types"] = self.view_types
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetList(HorillaListView):
    """
    Time sheet list view
    """

    model = TimeSheet
    filter_class = TimeSheetFilter
    view_id = "timeSheetListContainer"

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.has_perm("project.view_timesheet"):
            employee = self.request.user.employee_get
            queryset = queryset.filter(
                Q(task_id__task_managers=employee)
                | Q(project_id__managers=employee)
                | Q(employee_id=employee)
            ).distinct()
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.search_url = reverse("time-sheet-list")
        self.action_method = "actions"

    header_attrs = {
        "action": """style="width:110px !important;" """,
    }

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        "project_id",
        "task_id",
        "date",
        "time_spent",
        (_("Status"), "get_status_display"),
        (_("Description"), "get_description_col"),
    ]

    @cached_property
    def sortby_mapping(self):
        get_field = self.model()._meta.get_field
        return [
            (
                get_field("employee_id").verbose_name,
                "employee_id__employee_first_name",
                "employee_id__get_avatar",
            ),
            (get_field("project_id").verbose_name, "project_id__title"),
            (get_field("task_id").verbose_name, "task_id__title"),
            (get_field("time_spent").verbose_name, "time_spent"),
            (get_field("date").verbose_name, "date"),
        ]

    row_status_indications = [
        (
            "in-progress--dot",
            _("In progress"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('in_Progress');
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
    ]
    row_attrs = """
                hx-get='{detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    row_status_class = "status-{status}"

    # Mirrors TimeSheetNavView.nested_group_by_fields
    nested_group_by_fields = [
        "employee_id",
        "project_id",
        "task_id",
        "date",
        "status",
        "employee_id__employee_work_info__reporting_manager_id",
        "employee_id__employee_work_info__department_id",
        "employee_id__employee_work_info__job_position_id",
        "employee_id__employee_work_info__employee_type_id",
        "employee_id__employee_work_info__company_id",
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TaskTimeSheet(TimeSheetList):

    row_attrs = ""
    row_status_indications = False
    bulk_select_option = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "task-timesheet-container"
        task_id = resolve(self.request.path_info).kwargs.get("task_id")
        self.request.task_id = task_id
        employee_id = self.request.GET.get("employee_id")
        if employee_id:
            self.action_method = "actions"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        task_id = self.kwargs.get("task_id")
        task = Task.find(task_id)
        if not task:
            return context
        project = task.project
        context["task_id"] = task_id
        context["project"] = project
        context["task"] = task
        self.template_name = "cbv/timesheet/task_timesheet.html"
        return context

    def get_queryset(self):
        queryset = HorillaListView.get_queryset(self)
        task_id = self.kwargs.get("task_id")
        task = Task.objects.filter(id=task_id).first()
        queryset = TimeSheet.objects.filter(task_id=task_id)
        employee_id = self.request.GET.get("employee_id")
        if employee_id and employee_id.isdigit():
            employee = Employee.objects.filter(id=employee_id).first()
            if not task:
                return queryset.none()
            if (
                employee
                and not employee in task.task_managers.all()
                and not employee in task.project.managers.all()
                and not employee.employee_user_id.is_superuser
            ):
                queryset = queryset.filter(employee_id=employee_id)
        else:
            return queryset.none()

        return queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetFormView(HorillaFormView):
    """
    form view for create project
    """

    form_class = TimeSheetForm
    model = TimeSheet
    new_display_title = _("Create") + " " + model._meta.verbose_name

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dynamic_create_fields = [
            ("task_id", DynamicTaskCreateFormView),
        ]
        if self.request.user.has_perm("project.add_project"):
            self.dynamic_create_fields.append(
                ("project_id", DynamicProjectCreationFormView)
            )

    form_class = TimeSheetForm
    model = TimeSheet
    new_display_title = _("Create") + " " + model._meta.verbose_name
    # template_name = "cbv/timesheet/form.html"

    def get_initial(self) -> dict:
        initial = super().get_initial()
        task_id = self.kwargs.get("task_id")
        if task_id:
            task = Task.find(task_id)
            if not task:
                return initial
            project_id = task.project
            initial["project_id"] = project_id.id
            initial["task_id"] = task.id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task_id = self.kwargs.get("task_id")
        user_employee_id = self.request.user.employee_get.id
        project = None
        if task_id:
            task = Task.objects.get(id=task_id)
            project = task.project
            employee = Employee.objects.filter(id=user_employee_id)

        if self.form.instance.pk:
            task_id = self.form.instance.task_id.id
            project = self.form.instance.project_id
            tasks = Task.objects.filter(project=project)
            employee = Employee.objects.filter(id=user_employee_id)
            task = Task.objects.get(id=task_id)
            self.form.fields["task_id"].queryset = tasks
            self.form.fields["task_id"].choices = [
                (item.id, item.title) for item in tasks
            ]
            self.form.fields["task_id"].choices.append(
                ("dynamic_create", "Dynamic create")
            )
            task_id = self.request.GET.get("task_id")
            self.form_class.verbose_name = _("Update Timesheet")
        # If the timesheet create from task or project
        if project:
            if self.request.user.is_superuser or self.request.user.has_perm(
                "project.add_project"
            ):
                members = (
                    project.managers.all()
                    | task.task_members.all()
                    | task.task_managers.all()
                ).distinct()
            elif employee.first() in project.managers.all():
                members = (
                    employee | task.task_members.all() | task.task_managers.all()
                ).distinct()
            elif employee.first() in task.task_managers.all():
                members = (employee | task.task_members.all()).distinct()
            else:
                members = employee
            if task_id:
                self.form.fields["project_id"].widget = forms.HiddenInput()
                self.form.fields["task_id"].widget = forms.HiddenInput()
            self.form.fields["employee_id"].queryset = members

        # If the timesheet create directly
        else:
            employee = self.request.user.employee_get
            if self.request.user.has_perm("project.add_timesheet"):
                projects = Project.objects.all()
            else:
                projects = (
                    Project.objects.filter(managers=employee)
                    | Project.objects.filter(
                        id__in=Task.objects.filter(task_managers=employee).values_list(
                            "project", flat=True
                        )
                    )
                    | Project.objects.filter(
                        id__in=Task.objects.filter(task_members=employee).values_list(
                            "project", flat=True
                        )
                    )
                ).distinct()
            self.form.fields["project_id"].queryset = projects
        return context

    def form_valid(self, form: TimeSheetForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _(f"{self.form.instance} Updated")
            else:
                message = _("New timesheet created")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetCardView(HorillaCardView):
    """
    For card view
    """

    model = TimeSheet
    filter_class = TimeSheetFilter
    records_per_page = 20

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related(
                "employee_id",
                "employee_id__employee_work_info",
                "employee_id__employee_work_info__company_id",
                "project_id",
                "task_id",
            )
        )
        if not self.request.user.has_perm("project.view_timesheet"):
            employee = self.request.user.employee_get
            queryset = queryset.filter(
                Q(task_id__task_managers=employee)
                | Q(project_id__managers=employee)
                | Q(employee_id=employee)
            ).distinct()
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("time-sheet-card")
        self.actions = [
            {
                "action": _("Edit"),
                "attrs": """
                         hx-get='{get_update_url}'
                         hx-target='#genericModalBody'
                         data-toggle="oh-modal-toggle"
                         data-target="#genericModal"
                         class="oh-dropdown__link"
                         """,
            },
            {
                "action": _("Delete"),
                "attrs": """
                onclick="
                            event.stopPropagation()
                            deleteItem({get_delete_url});
                            "
                            class="oh-dropdown__link oh-dropdown__link--danger"
                """,
            },
        ]

    details = {
        "image_src": "employee_id__get_avatar",
        "title": "{employee_id}",
        "subtitle": format_lazy(
            "<b>{date_str}</b> <br>"
            "{project_str} : <b>{project}</b> <br>"
            "<b>{task}</b> |  {time_str} : <b>{time}</b>",
            date_str=localize("{date}"),
            project_str=_("Project"),
            project="{project_id}",
            time_str=_("Time Spent"),
            task="{task_id}",
            time="{time_spent}",
        ),
    }

    card_status_class = "status-{status}"

    card_status_indications = [
        (
            "in-progress--dot",
            _("In progress"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('in_Progress');
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
    ]

    card_attrs = """
                hx-get='{detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_timesheet"), name="dispatch"
)
class TimeSheetDetailView(HorillaDetailedView):
    """
    detail view of the page
    """

    model = TimeSheet
    title = _("Details")
    header = {
        "title": "employee_id",
        "subtitle": "project_id",
        "avatar": "employee_id__get_avatar",
    }
    action_method = "detail_actions"

    @cached_property
    def body(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("task_id").verbose_name, "task_id"),
            (get_field("date").verbose_name, "date"),
            (get_field("time_spent").verbose_name, "time_spent"),
            (get_field("status").verbose_name, "get_status_display"),
            (get_field("description").verbose_name, "description"),
        ]

    cols = {
        "description": 12,
    }
