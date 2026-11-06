import random

import pandas as pd
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _

from base.methods import get_pagination, get_subordinates
from employee.models import Employee
from horilla.http import HorillaRedirect
from project.models import Project, Task, TimeSheet

decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


def strtime_seconds(time):
    """
    this method is used to reconvert time in H:M formate string back to seconds and return it
    args:
        time : time in H:M format
    """
    ftr = [3600, 60, 1]
    return sum(a * b for a, b in zip(ftr, map(int, time.split(":"))))


def paginator_qry(qryset, page_number):
    """
    This method is used to generate common paginator limit.
    """
    paginator = Paginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


def random_color_generator():
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    if r == g or g == b or b == r:
        random_color_generator()
    return f"rgba({r}, {g}, {b} , 0.7)"


# color_palette=[]
# Function to generate distinct colors for each project
def generate_colors(num_colors):
    # Define a color palette with distinct colors
    color_palette = [
        "rgba(255, 99, 132, 1)",  # Red
        "rgba(54, 162, 235, 1)",  # Blue
        "rgba(255, 206, 86, 1)",  # Yellow
        "rgba(75, 192, 192, 1)",  # Green
        "rgba(153, 102, 255, 1)",  # Purple
        "rgba(255, 159, 64, 1)",  # Orange
    ]

    if num_colors > len(color_palette):
        for i in range(num_colors - len(color_palette)):
            color_palette.append(random_color_generator())

    colors = []
    for i in range(num_colors):
        # color=random_color_generator()
        colors.append(color_palette[i % len(color_palette)])

    return colors


def employees_for_project(project):
    """
    Employees eligible to be selected as managers/members for the given
    project. Restricted to the project's own company; projects without a
    company assignment (legacy data) are left unrestricted.
    """
    if not project:
        return Employee.objects.none()
    if project.company_id:
        return Employee.objects.filter(
            employee_work_info__company_id=project.company_id
        )
    return Employee.objects.all()


def any_project_manager(user):
    employee = user.employee_get
    if employee.project_managers.all().exists():
        return True
    else:
        return False


def any_task_manager(user):
    employee = user.employee_get
    if employee.task_set.all().exists():
        return True
    else:
        return False


def any_task_member(user):
    employee = user.employee_get
    if employee.tasks.all().exists():
        return True
    else:
        return False


@decorator_with_arguments
def is_projectmanager_or_member_or_perms(function, perm):
    def _function(request, *args, **kwargs):
        """
        This method is used to check the employee is project manager or not
        """
        user = request.user
        if (
            user.has_perm(perm)
            or any_project_manager(user)
            or any_task_manager(user)
            or any_task_member(user)
        ):
            return function(request, *args, **kwargs)
        return HorillaRedirect(request, message=_("You don't have permission."))

    return _function


def is_task_member(request, task_id):
    """
    This method is used to check the employee is task member or not
    """
    task = Task.find(task_id)
    if not task:
        return False  # Task not found, treat as not a member
    if (
        request.user.has_perm("project.change_task")
        or request.user.employee_get in task.task_managers.all()
        or request.user.employee_get in task.task_members.all()
    ):
        return True
    return False


def is_task_manager(request, task_id):
    """
    This method is used to check the employee is task member or not
    """
    task = Task.find(task_id)
    if not task:
        return False  # Task not found, treat as not a manager
    if (
        request.user.has_perm("project.delete_task")
        or request.user.employee_get in task.task_managers.all()
    ):
        return True
    return False


def time_sheet_update_permissions(request, time_sheet_id):
    timesheet = TimeSheet.find(time_sheet_id)
    if not timesheet:
        return False  # Timesheet not found, treat as no permission
    if (
        request.user.has_perm("project.change_timesheet")
        or request.user.employee_get == timesheet.employee_id
        or timesheet.employee_id
        in Employee.objects.filter(
            employee_work_info__reporting_manager_id=request.user.employee_get
        )
    ):
        return True
    else:
        return False


def time_sheet_delete_permissions(request, time_sheet_id):
    employee = request.user.employee_get
    timesheet = TimeSheet.objects.filter(id=time_sheet_id).first()
    if (
        request.user.has_perm("project.delete_timesheet")
        or timesheet.employee_id == employee
        or employee in timesheet.task_id.task_managers.all()
        or employee in timesheet.task_id.project.managers.all()
    ):
        return True
    else:
        return False


def get_all_project_members_and_managers():
    all_projects = Project.objects.all()
    all_tasks = Task.objects.all()

    all_ids = set()

    for project in all_projects:
        all_ids.update(
            manager.id for manager in project.managers.all()
        )  # Add manager ID

    for task in all_tasks:
        all_ids.update(
            task_manager.id for task_manager in task.task_managers.all()
        )  # Add task manager ID
        all_ids.update(
            task_member.id for task_member in task.task_members.all()
        )  # Add task member IDs

    # Return a single queryset for all employees
    return Employee.objects.filter(id__in=all_ids)


def has_subordinates(request):
    """
    used to check whether the project contain users subordinates or not
    """
    all_members_info = get_all_project_members_and_managers()
    subordinates = get_subordinates(request)

    member = {member for member in all_members_info}

    for subordinate in subordinates:
        if subordinate in member:
            return True

    return False


def is_project_manager_or_super_user(request, project):
    """
    Method to check whether user is a manager of project or
    user is a super user.
    """
    return (
        request.user.employee_get in project.managers.all() or request.user.is_superuser
    )


PROJECT_IMPORT_REQUIRED_HEADERS = ["Title", "Status", "Start Date", "Description"]

PROJECT_IMPORT_ERROR_COLUMNS = [
    "Title",
    "Manager Badge ID",
    "Status",
    "Start Date",
    "End Date",
    "Description",
    "Company",
    "Title Error",
    "Company Error",
    "Manager Error",
    "Status Error",
    "Start Date Error",
    "End Date Error",
    "Description Error",
    "Duplicate Error",
    "Other Error",
]


def project_import_error_template():
    """Fresh column map for generate_error_report (it mutates what it is given)."""
    return {column: [] for column in PROJECT_IMPORT_ERROR_COLUMNS}


def valid_project_import_headers(data_frame):
    """Return ``(is_valid, message)`` for the uploaded project file."""
    if data_frame.empty:
        return False, _("The uploaded file is empty, Not contain records.")
    missing = [
        h for h in PROJECT_IMPORT_REQUIRED_HEADERS if h not in data_frame.columns
    ]
    if missing:
        return False, _(
            "These required headers are missing in the uploaded file: "
        ) + ", ".join(missing)
    return True, ""


def resolve_project_import_company(
    name, companies, selected_company=None, allowed_ids=None
):
    """
    Resolve the "Company" cell of one import row to ``(company, error)``
    (same rules as the employee import).

    - `selected_company` (a Company instance): the row must name that company;
      a blank Company is rejected.
    - None ("All Company"/no selection): the row may name any existing
      company, or leave it blank (company_id=None).
    ``allowed_ids`` (set for non-superusers) limits which companies may be
    named. ``companies`` maps lower-cased company name -> Company.
    """
    name = str(name).strip() if name is not None and not pd.isna(name) else ""
    if selected_company and not name:
        return None, _(
            "Company is required and must match the selected company '{}'."
        ).format(selected_company.company)
    if not name:
        return None, None
    company = companies.get(name.lower())
    if company is None:
        return None, _("Company '{}' does not exist.").format(name)
    if selected_company and company.pk != selected_company.pk:
        return None, _("Company '{}' does not match the selected company.").format(name)
    if allowed_ids is not None and company.pk not in allowed_ids:
        return None, _("You do not have access to company '{}'.").format(name)
    return company, None


def process_project_records(data_frame, selected_company=None, allowed_ids=None):
    """
    Validate and save the rows of a project import file.

    Returns ``(created_count, error_list)``; every failed row is returned as
    its original cells plus ``* Error`` entries, ready for the error report.
    Valid rows are saved even when others fail. A title that already exists in
    the same company is updated (as the importer always did); the same title
    in another company is a separate project (title + company is unique).
    """
    from django.db import transaction

    from base.models import Company
    from employee.methods.methods import clean_badge_id, import_valid_date

    companies = {c.company.lower(): c for c in Company.objects.all()}
    status_lookup = {}
    for value, label in Project.PROJECT_STATUS:
        status_lookup[value.lower()] = value
        status_lookup[str(label).lower()] = value

    created_count, error_list = 0, []
    for row in data_frame.to_dict("records"):
        errors = {}
        title = row.get("Title")
        title = str(title).strip() if title is not None else ""
        if not title:
            errors["Title Error"] = _("Title is a required field.")
        elif len(title) > 200:
            errors["Title Error"] = _("Title cannot exceed 200 characters.")

        company, company_error = resolve_project_import_company(
            row.get("Company"), companies, selected_company, allowed_ids
        )
        if company_error:
            errors["Company Error"] = company_error

        status = row.get("Status")
        status = str(status).strip() if status is not None else ""
        if not status:
            errors["Status Error"] = _("Status is a required field.")
        elif status.lower() not in status_lookup:
            errors["Status Error"] = _("{} not available in Project status").format(
                status
            )
        else:
            status = status_lookup[status.lower()]

        start_date = import_valid_date(
            row.get("Start Date"), "Start Date", errors, "Start Date Error"
        )
        if not start_date and "Start Date Error" not in errors:
            errors["Start Date Error"] = _("Start Date is a required field.")
        end_date = import_valid_date(
            row.get("End Date"), "End Date", errors, "End Date Error"
        )
        if start_date and end_date and end_date < start_date:
            errors["End Date Error"] = _("End date must be greater than Start date")

        description = row.get("Description")
        description = str(description).strip() if description is not None else ""
        if not description:
            errors["Description Error"] = _("Description is a required field.")

        managers = []
        raw_badges = row.get("Manager Badge ID")
        if raw_badges is not None and not pd.isna(raw_badges):
            badge_ids = [
                clean_badge_id(b) for b in str(raw_badges).split(",") if b.strip()
            ]
            found = {
                e.badge_id: e
                for e in Employee.objects.entire()
                .filter(badge_id__in=badge_ids)
                .select_related("employee_work_info")
            }
            problems = []
            for badge_id in badge_ids:
                employee = found.get(badge_id)
                if employee is None:
                    problems.append(f"{badge_id} - This id not exists")
                    continue
                work_info = getattr(employee, "employee_work_info", None)
                employee_company_id = work_info.company_id_id if work_info else None
                if company and employee_company_id != company.pk:
                    problems.append(
                        f"{badge_id} - Does not belong to company '{company.company}'"
                    )
                    continue
                managers.append(employee)
            if problems:
                errors["Manager Error"] = "; ".join(problems)

        existing = None
        if title and "Company Error" not in errors:
            # Title is unique per company: same title + company is updated.
            existing = (
                Project.objects.entire().filter(title=title, company_id=company).first()
            )

        if not errors:
            try:
                with transaction.atomic():
                    project = existing or Project(title=title)
                    project.company_id = company
                    project.status = status
                    project.start_date = start_date
                    project.end_date = end_date
                    project.description = description
                    project.save()
                    if managers:
                        project.managers.add(*managers)
                created_count += 1
                continue
            except Exception as exception:
                errors["Other Error"] = str(exception)
        row.update(errors)
        error_list.append(row)
    return created_count, error_list
