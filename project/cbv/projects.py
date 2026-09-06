"""
CBV of projects page
"""

from typing import Any

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView

from base.methods import has_export_access
from base.models import Company
from employee.models import Employee
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from project.cbv.cbv_decorators import is_projectmanager_or_member_or_perms
from project.filters import ProjectFilter
from project.forms import ProjectForm
from project.methods import any_project_manager
from project.models import Project


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_project"), name="dispatch"
)
class ProjectsView(TemplateView):
    """
    for projects page
    """

    template_name = "cbv/projects/projects.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_project"), name="dispatch"
)
class ProjectsNavView(HorillaNavView):
    """
    Nav bar
    """

    filter_form_context_name = "form"
    filter_instance = ProjectFilter()
    search_swap_target = "#listContainer"
    group_by_fields = ["status", "is_active"]
    template_name = "cbv/projects/project_nav.html"
    filter_body_template = "cbv/projects/filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. ProjectFilter.ajax_fields carries the
    # AJAX-loaded managers combobox this needs.
    modern_filter = True

    # Mirrors ProjectsList.nested_group_by_fields
    nested_group_by_fields = [
        "title",
        "status",
        "is_active",
        "start_date",
        "end_date",
        ("company_id", _("Company")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("project-list-view")
        # self.search_in = [
        #     ("status", _("Managers")),
        #     ("members", _("Members")),
        # ]
        if self.request.user.has_perm("project.view_project"):
            self.actions = [
                {
                    "action": _("Import"),
                    "attrs": """
                        id="importProject"
                        data-toggle="oh-modal-toggle"
                        data-target="#projectImport"
                        style="cursor: pointer;"
                    """,
                },
                {
                    "action": _("Archive"),
                    "attrs": """
                        id="archiveProject"
                        style="cursor: pointer;"
                        onclick="validateProjectIds(event);"
                        data-action="archive"
                    """,
                },
                {
                    "action": _("Un-archive"),
                    "attrs": """
                        id="unArchiveProject"
                        style="cursor: pointer;"
                        onclick="validateProjectIds(event);"
                        data-action="unarchive"
                    """,
                },
                {
                    "action": _("Delete"),
                    "attrs": """
                        class="oh-dropdown__link--danger"
                        data-action ="delete"
                        id="deleteProject"
                        onclick="validateProjectIds(event);"
                        style="cursor: pointer; color:red !important"
                    """,
                },
            ]
            if has_export_access(self.request, Project):
                self.actions.insert(
                    1,
                    {
                        "action": _("Export"),
                        "attrs": """
                            id="exportProject"
                            style="cursor: pointer;"
                        """,
                    },
                )
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse("project-list-view"),
                "attrs": f"""
                    title ='{_("List")}'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("project-card-view"),
                "attrs": f"""
                    title ='{_("Card")}'
                """,
            },
        ]
        if self.request.user.has_perm("project.add_project"):
            self.create_attrs = f"""
                onclick = "event.stopPropagation();"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('create-project')}"
            """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_project"), name="dispatch"
)
class ProjectsList(HorillaListView):
    """
    Projects list view
    """

    model = Project
    filter_class = ProjectFilter
    quick_export = False

    def get_queryset(self):
        queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)
        if not self.request.user.has_perm("project.view_project"):
            employee = self.request.user.employee_get
            task_filter = queryset.filter(
                Q(task__task_members=employee) | Q(task__task_managers=employee)
            )
            project_filter = queryset.filter(Q(managers=employee))
            queryset = task_filter | project_filter
        return queryset.distinct()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("project-list-view")
        if self.request.user.is_superuser:
            self.action_method = "actions"

    header_attrs = {
        "action": """style="width:150px !important;" """,
    }

    @cached_property
    def columns(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("title").verbose_name, "title"),
            (get_field("managers").verbose_name, "get_managers"),
            (get_field("status").verbose_name, "get_status_display"),
            (get_field("start_date").verbose_name, "start_date"),
            (get_field("end_date").verbose_name, "end_date"),
            (get_field("document").verbose_name, "get_document_html"),
            (get_field("description").verbose_name, "get_description"),
        ]

    @cached_property
    def sortby_mapping(self):
        get_field = self.model()._meta.get_field
        return [
            (get_field("title").verbose_name, "title"),
            (get_field("start_date").verbose_name, "start_date"),
            (get_field("end_date").verbose_name, "end_date"),
        ]

    row_status_indications = [
        (
            "new--dot",
            _("New"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('new');
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
            "on-hold--dot",
            _("On Hold"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('on_hold');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "cancelled--dot",
            _("Cancelled"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('cancelled');
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

    row_attrs = """ {redirect} """

    # Mirrors ProjectsNavView.nested_group_by_fields below -- List and
    # Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Project Managers"
    # (managers) is deliberately left out: it's a ManyToManyField, and
    # the nested engine's `values(*fields).annotate(Count("pk"))`
    # aggregate would fan out one row per related manager, double-
    # counting projects with more than one manager assigned.
    nested_group_by_fields = [
        "title",
        "status",
        "is_active",
        "start_date",
        "end_date",
        ("company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
# @method_decorator(permission_required("project.add_project"), name="dispatch")
class ProjectFormView(HorillaFormView):
    """
    form view for create project
    """

    model = Project
    form_class = ProjectForm
    template_name = "cbv/projects/project_form.html"
    new_display_title = _("Create") + " " + model._meta.verbose_name

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        user = self.request.user

        if not user.is_superuser and not user.has_perm("project.add_project"):
            self.template_name = "decorator_404.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = (
                _("Update") + " " + self.model._meta.verbose_name
            )

        dynamic_company_id = self.request.GET.get("dynamic_company")
        if dynamic_company_id and not self.form.instance.pk:
            company = Company.objects.filter(id=dynamic_company_id).first()
            self.form.fields["company_id"].initial = company
            self.form.fields["managers"].queryset = (
                Employee.objects.filter(employee_work_info__company_id=company)
                if company
                else Employee.objects.none()
            )
        return context

    def form_valid(self, form: ProjectForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _(f"{self.form.instance} Updated")
                HTTP_REFERER = self.request.META.get("HTTP_REFERER", None)
                if HTTP_REFERER and "task-view/" in HTTP_REFERER:
                    form.save()
                    messages.success(self.request, message)
                    return self.HttpResponse(
                        "<script>window.location.reload()</script>"
                    )
            else:
                message = _("New project created")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


class DynamicProjectCreationFormView(ProjectFormView):

    is_dynamic_create_view = True


@method_decorator(login_required, name="dispatch")
@method_decorator(
    is_projectmanager_or_member_or_perms("project.view_project"), name="dispatch"
)
class ProjectCardView(HorillaCardView):
    """
    For card view
    """

    model = Project
    filter_class = ProjectFilter

    def get_queryset(self):
        queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)
        if not self.request.user.has_perm("project.view_project"):
            employee = self.request.user.employee_get
            task_filter = queryset.filter(
                Q(task__task_members=employee) | Q(task__task_managers=employee)
            )
            project_filter = queryset.filter(Q(managers=employee))
            queryset = task_filter | project_filter
        return queryset.distinct()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("project-card-view")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if (
            self.request.user.has_perm("project.change_project")
            or self.request.user.has_perm("project.delete_project")
            or any_project_manager(self.request.user)
        ):
            self.actions = [
                {
                    "action": _("Edit"),
                    "accessibility": "project.cbv.accessibility.project_manager_accessibility",
                    "attrs": """
                        hx-get='{get_update_url}'
                        hx-target='#genericModalBody'
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        class="oh-dropdown__link"
                    """,
                },
                {
                    "action": "archive_status",
                    "accessibility": "project.cbv.accessibility.project_manager_accessibility",
                    "attrs": """
                        hx-get="{get_archive_url}"
                        hx-target="#listContainer"
                        hx-swap="innerHTML"
                        hx-confirm="Do you want to {archive_status} this project?"
                        onclick="event.stopPropagation()"
                        class="oh-dropdown__link"
                    """,
                },
                {
                    "action": _("Delete"),
                    "accessibility": "project.cbv.accessibility.project_manager_accessibility",
                    "attrs": """
                        hx-get="{get_delete_url}?view=card"
                        hx-target="#listContainer"
                        hx-swap="innerHTML"
                        hx-confirm="Do you want to delete this project?"
                        onclick="event.stopPropagation()"
                        class="oh-dropdown__link oh-dropdown__link--danger"
                    """,
                },
            ]
        context["actions"] = self.actions
        return context

    details = {
        "image_src": "get_avatar",
        "title": "{get_task_badge_html}",
        "subtitle": "{get_card_view_subtitle}",
    }

    card_status_class = "status-{status}"

    card_status_indications = [
        (
            "new--dot",
            _("New"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('new');
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
            "on-hold--dot",
            _("On Hold"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('on_hold');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "cancelled--dot",
            _("Cancelled"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=status]').val('cancelled');
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
    card_attrs = """
                 {redirect}
                 """


# def projects_tab(request, pk=None):
#     """
#     This method is used to projects tab
#     """

#     projects = Project.objects.filter(
#         Q(manager=pk)
#         | Q(members=pk)
#         | Q(task__task_members=pk)
#         | Q(task__task_manager=pk)
#     )
#     context = {"projects": projects}
#     if pk:
#         template = "cbv/projects/project_tab.html"
#         employees = Employee.objects.filter(id=pk).distinct()
#         emoloyee = employees.first()
#         context["employee"] = emoloyee
#     return render(
#         request,
#         template,
#         context,
#     )


@method_decorator(login_required, name="dispatch")
class ProjectsTabView(ListView):
    model = Project
    template_name = "cbv/projects/project_tab.html"
    context_object_name = "projects"

    def get_queryset(self):
        pk = self.kwargs.get("pk")
        queryset = Project.objects.filter(
            Q(managers=pk) | Q(task__task_members=pk) | Q(task__task_managers=pk)
        )
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        if pk:
            employees = Employee.objects.filter(id=pk).distinct()
            employee = employees.first()
            context["employee"] = employee
        return context


from employee.cbv.employee_profile import EmployeeProfileView

EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Projects"),
            # "view": projects_tab,
            "view": ProjectsTabView.as_view(),
            "accessibility": "employee.cbv.accessibility.project_accessibility",
        },
    ]
)
