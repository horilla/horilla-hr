"""
employee/methods.py
"""

import logging
import re
import threading
from datetime import date, datetime
from itertools import chain, groupby

import pandas as pd
from django.apps import apps
from django.db import connection, models, transaction
from django.utils.translation import gettext as _

from base.context_processors import get_initial_prefix
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.models import HorillaUser

logger = logging.getLogger(__name__)

is_postgres = connection.vendor == "postgresql"

error_data_template = {
    field: []
    for field in [
        "Badge ID",
        "First Name",
        "Last Name",
        "Phone",
        "Email",
        "Gender",
        "Department",
        "Job Position",
        "Job Role",
        "Work Type",
        "Shift",
        "Employee Type",
        "Reporting Manager",
        "Company",
        "Location",
        "Date Joining",
        "Contract End Date",
        "Basic Salary",
        "Salary Hour",
        "Email Error",
        "First Name Error",
        "Name and Email Error",
        "Phone Error",
        "Gender Error",
        "Joining Date Error",
        "Contract Date Error",
        "Badge ID Error",
        "Basic Salary Error",
        "Salary Hour Error",
        "User ID Error",
        "Company Error",
    ]
}


def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def normalize_phone(phone):
    phone = str(phone).strip()
    if phone.startswith("+"):
        return "+" + re.sub(r"\D", "", phone[1:])
    return re.sub(r"\D", "", phone)


def import_valid_date(date_value, field_label, errors_dict, error_key):
    if date_value is None or pd.isna(date_value) or str(date_value).strip() == "":
        return None

    if isinstance(date_value, (pd.Timestamp, datetime)):
        return date_value.date()

    date_str = str(date_value).strip()
    date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    errors_dict[error_key] = (
        f"{field_label} is not a valid date. Expected formats: YYYY-MM-DD, DD/MM/YYYY"
    )
    return None


def clean_badge_id(value):
    """
    Cleans and converts a badge ID value from Excel import.

    - If the value is a whole number (e.g., 5480.0), returns it as an integer string ("5480").
    - If the value is a decimal (e.g., 567.67), returns it as a float string ("567.67").
    - If the value is a non-numeric string (e.g., "A101"), returns the stripped string.
    - If the value is NaN or None, returns an empty string.
    """
    if pd.isna(value):
        return ""

    try:
        float_val = float(value)
        if float_val.is_integer():
            return str(int(float_val))
        else:
            return str(float_val)
    except (ValueError, TypeError):
        return str(value).strip()


def convert_nan(field, data):
    import math

    """
    Returns None if value is NaN or empty, otherwise returns the value.
    """
    value = data.get(field)

    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def dynamic_prefix_sort(item):
    """
    Sorts items based on a dynamic prefix length.
    """
    # Assuming the dynamic prefix length is 3
    prefix = get_initial_prefix(None)["get_initial_prefix"]

    prefix_length = len(prefix) if len(prefix) >= 3 else 3
    return item[:prefix_length]


def get_ordered_badge_ids():
    """
    This method is used to return ordered badge ids
    """
    employees = Employee.objects.entire()
    data = (
        employees.exclude(badge_id=None)
        .order_by("badge_id")
        .values_list("badge_id", flat=True)
    )
    if not data.first():
        data = [
            f'{get_initial_prefix(None)["get_initial_prefix"]}0001',
        ]
    # Separate pure number strings and convert them to integers
    pure_numbers = [int(item) for item in data if item.isdigit()]

    # Remove pure number strings from the original data
    data = [item for item in data if not item.isdigit()]

    # Sort the remaining data by dynamic prefixes
    sorted_data = sorted(data, key=dynamic_prefix_sort)

    # Group the sorted data by dynamic prefixes
    grouped_data = [
        list(group) for _, group in groupby(sorted_data, key=dynamic_prefix_sort)
    ]

    # Sort each subgroup numerically by the digits in the badge id, so e.g.
    # "PEP100" correctly sorts after "PEP99" instead of before it as a string
    for index, group in enumerate(grouped_data):
        numeric_items = [item for item in group if any(char.isdigit() for char in item)]
        non_numeric_items = [item for item in group if item not in numeric_items]
        numeric_items.sort(key=lambda x: int("".join(filter(str.isdigit, x))))
        grouped_data[index] = non_numeric_items + numeric_items

    # Create a list containing the first and last items from each group
    result = [[group[0], group[-1]] for group in grouped_data]

    # Add the list of pure numbers at the beginning
    if pure_numbers:
        result.insert(0, [pure_numbers[0], pure_numbers[-1]])
    return result


def check_relationship_with_employee_model(model):
    """
    Checks the relationship of a given model with the Employee model.

    This function iterates through all the fields of the specified model
    and identifies fields that are either `ForeignKey` or `ManyToManyField`
    and are related to the `Employee` model. For each such field, it adds
    the field name and the type of relationship to a list.
    """
    related_fields = []
    for field in model._meta.get_fields():
        # Check if the field is a ForeignKey or ManyToManyField and related to Employee
        if isinstance(field, models.ForeignKey) and field.related_model == Employee:
            related_fields.append((field.name, "ForeignKey"))
        elif (
            isinstance(field, models.ManyToManyField)
            and field.related_model == Employee
        ):
            related_fields.append((field.name, "ManyToManyField"))
    return related_fields


def valid_import_file_headers(data_frame):
    if data_frame.empty:
        message = _("The uploaded file is empty, Not contain records.")
        return False, message

    required_keys = [
        "Badge ID",
        "First Name",
        "Last Name",
        "Phone",
        "Email",
        "Gender",
        "Department",
        "Job Position",
        "Job Role",
        "Work Type",
        "Shift",
        "Employee Type",
        "Reporting Manager",
        "Company",
        "Location",
        "Date Joining",
        "Contract End Date",
        "Basic Salary",
        "Salary Hour",
    ]

    missing_keys = [key for key in required_keys if key not in data_frame.columns]
    if missing_keys:
        message = _(
            "These required headers are missing in the uploaded file: "
        ) + ", ".join(missing_keys)
        return False, message
    return True, ""


def process_employee_records(data_frame):

    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    phone_regex = re.compile(r"^\+?\d{10,15}$")
    allowed_genders = frozenset(choice[0] for choice in Employee.choice_gender)
    # Preload entire badge IDs for duplicate validation during import
    existing_badge_ids = frozenset(
        Employee.objects.entire().values_list("badge_id", flat=True)
    )
    existing_usernames = frozenset(
        HorillaUser.objects.values_list("username", flat=True)
    )
    existing_name_emails = frozenset(
        (fname, lname, email)
        for fname, lname, email in Employee.objects.values_list(
            "employee_first_name", "employee_last_name", "email"
        )
    )
    existing_companies = frozenset(Company.objects.values_list("company", flat=True))
    success_list, error_list = [], []
    employee_dicts = data_frame.to_dict("records")

    created_count = 0
    seen_badge_ids = set(existing_badge_ids)
    seen_usernames = set(existing_usernames)
    seen_name_emails = set(existing_name_emails)

    today = date.today()

    for emp in employee_dicts:
        errors = {}
        save = True
        gender = emp.get("Gender")

        email = str(emp.get("Email", "")).strip().lower()
        raw_phone = emp.get("Phone", "")
        phone = normalize_phone(raw_phone)
        badge_id = clean_badge_id(emp.get("Badge ID"))
        first_name = emp.get("First Name")
        last_name = emp.get("Last Name")
        address = emp.get("Address")
        gender = str(gender).strip().lower() if gender else None
        company = emp.get("Company")
        basic_salary = emp.get("Basic Salary")
        salary_hour = emp.get("Salary Hour")

        # Date validation
        joining_date = import_valid_date(
            emp.get("Date Joining"), "Joining Date", errors, "Joining Date Error"
        )
        if joining_date:
            if joining_date > today:
                errors["Joining Date Error"] = "Joining date cannot be in the future."
                save = False

        contract_end_date = import_valid_date(
            emp.get("Contract End Date"),
            "Contract End Date",
            errors,
            "Contract Date Error",
        )
        if contract_end_date and joining_date and contract_end_date < joining_date:
            errors["Contract Date Error"] = (
                "Contract end date cannot be before joining date."
            )
            save = False

        # Email validation
        if not email or not email_regex.match(email):
            errors["Email Error"] = "Invalid email address."
            save = False

        # Name validation
        if not first_name:
            errors["First Name Error"] = "First name cannot be empty."
            save = False

        # Phone validation
        if not phone_regex.match(phone):
            errors["Phone Error"] = "Invalid phone number format."
            save = False

        # Badge ID validation
        if not badge_id:
            errors["Badge ID Error"] = "Badge ID cannot be empty."
            save = False

        elif badge_id in seen_badge_ids:
            errors["Badge ID Error"] = "An employee with this badge ID already exists."
            save = False

        else:
            # Ensure consistent type (convert to string if needed)
            badge_id = str(badge_id).strip()
            emp["Badge ID"] = badge_id
            seen_badge_ids.add(badge_id)

        # Username/email uniqueness
        if email in seen_usernames:
            errors["User ID Error"] = "User with this email already exists."
            save = False
        else:
            seen_usernames.add(email)

        # Name+email uniqueness
        name_email_tuple = (first_name, last_name, email)
        if name_email_tuple in seen_name_emails:
            errors["Name and Email Error"] = (
                "This employee already exists in the system."
            )
            save = False
        else:
            seen_name_emails.add(name_email_tuple)

        # Gender validation
        if gender and gender not in allowed_genders:
            errors["Gender Error"] = (
                f"Invalid gender. Allowed values: {', '.join(allowed_genders)}."
            )
            save = False

        # Company validation
        if company and company not in existing_companies:
            errors["Company Error"] = f"Company '{company}' does not exist."
            save = False

        # Salary validation
        if basic_salary not in [None, ""]:
            try:
                basic_salary_val = float(basic_salary)
                if basic_salary_val <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors["Basic Salary Error"] = "Basic salary must be a positive number."
                save = False

        if salary_hour not in [None, ""]:
            try:
                salary_hour_val = float(salary_hour)
                if salary_hour_val < 0:
                    raise ValueError
            except (ValueError, TypeError):
                errors["Salary Hour Error"] = (
                    "Salary hour must be a non-negative number."
                )
                save = False

        # Final processing
        if save:
            emp["Phone"] = phone
            emp["Date Joining"] = joining_date
            emp["Contract End Date"] = contract_end_date
            success_list.append(emp)
            created_count += 1
        else:
            emp.update(errors)
            error_list.append(emp)

    return success_list, error_list, created_count


def bulk_create_user_import(success_lists):
    """
    Creates new HorillaUser instances in bulk from a list of dictionaries containing user data.

    Returns:
        list: A list of created HorillaUser instances. If no new users are created, returns an empty list.
    """
    emails = [row["Email"] for row in success_lists]
    existing_usernames = (
        set(
            HorillaUser.objects.filter(username__in=emails).values_list(
                "username", flat=True
            )
        )
        if is_postgres
        else set(
            chain.from_iterable(
                HorillaUser.objects.filter(username__in=chunk).values_list(
                    "username", flat=True
                )
                for chunk in chunked(emails, 999)
            )
        )
    )

    users_to_create = [
        HorillaUser(
            username=row["Email"],
            email=row["Email"],
            password=str(row["Phone"]).strip(),
            is_superuser=False,
        )
        for row in success_lists
        if row["Email"] not in existing_usernames
    ]

    created_users = []
    if users_to_create:
        with transaction.atomic():
            created_users = HorillaUser.objects.bulk_create(
                users_to_create, batch_size=None if is_postgres else 999
            )
    return created_users


def bulk_create_employee_import(success_lists):
    """
    Creates Employee instances in bulk based on imported data.
    Uses adaptive chunking for compatibility with SQLite, avoids chunking in PostgreSQL.
    """
    emails = [row["Email"] for row in success_lists]
    is_postgres = connection.vendor == "postgresql"

    existing_users = {
        user.username: user
        for user in (
            HorillaUser.objects.filter(username__in=emails).only("id", "username")
            if is_postgres
            else chain.from_iterable(
                HorillaUser.objects.filter(username__in=chunk).only("id", "username")
                for chunk in chunked(emails, 999)
            )
        )
    }

    employees_to_create = [
        Employee(
            employee_user_id=existing_users[row.get("Email")],
            badge_id=row.get("Badge ID"),
            employee_first_name=row.get("First Name"),
            employee_last_name=row.get("Last Name"),
            address=row.get("Address"),
            email=row.get("Email"),
            phone=row.get("Phone"),
            gender=row.get("Gender").lower() if row.get("Gender") else None,
        )
        for row in success_lists
        if row["Email"] in existing_users
    ]

    created_employees = []
    if employees_to_create:
        with transaction.atomic():
            created_employees = Employee.objects.bulk_create(
                employees_to_create, batch_size=None if is_postgres else 999
            )

    return created_employees


def set_initial_password(employees):
    """
    method to set initial password
    """

    logger.info("started to set initial password")
    for employee in employees:
        try:
            employee.employee_user_id.set_password(str(employee.phone))
            employee.employee_user_id.save()
        except Exception as e:
            logger.error(f"falied to set initial password for {employee}")
    logger.info("initial password configured")


def optimize_reporting_manager_lookup():
    """
    Optimizes the lookup of reporting managers from a list of work information.

    This function identifies unique reporting manager names from the provided
    list of work information, queries all matching `Employee` objects in a
    single database query, and creates a dictionary for quick lookups based
    on the full name of the reporting managers.
    """
    employees = Employee.objects.entire()

    employee_dict = {
        f"{employee.employee_first_name} {employee.employee_last_name}": employee
        for employee in employees
    }
    return employee_dict


def bulk_create_department_import(success_lists):
    """
    Bulk creation of department instances based on the excel import of employees
    """
    departments_to_import = {
        dept for work_info in success_lists if (dept := work_info.get("Department"))
    }

    existing_departments = set(Department.objects.values_list("department", flat=True))

    new_departments = [
        Department(department=dept)
        for dept in departments_to_import - existing_departments
    ]

    if new_departments:
        with transaction.atomic():
            Department.objects.bulk_create(
                new_departments, batch_size=None if is_postgres else 999
            )


def bulk_create_job_position_import(success_lists):
    """
    Optimized: Bulk creation of job position instances based on the Excel import of employees.
    """

    # Step 1: Extract unique (job_position, department_name) pairs
    job_positions_to_import = {
        (jp, dep)
        for item in success_lists
        if (jp := item.get("Job Position")) and (dep := item.get("Department"))
    }

    if not job_positions_to_import:
        return  # No valid data to import

    # Step 2: Fetch all departments at once and build a name -> object map
    department_objs = Department.objects.only("id", "department")
    department_lookup = {dep.department: dep for dep in department_objs}

    # Step 3: Filter out entries with unknown departments
    valid_pairs = [
        (jp, department_lookup[dept].id)
        for jp, dept in job_positions_to_import
        if dept in department_lookup
    ]

    if not valid_pairs:
        return  # No valid (job_position, department_id) pairs to process

    # Step 4: Fetch existing job positions
    existing_pairs = set(
        JobPosition.objects.filter(
            department_id__in={dept_id for _, dept_id in valid_pairs}
        ).values_list("job_position", "department_id")
    )

    # Step 5: Create list of new JobPosition instances
    new_positions = [
        JobPosition(job_position=jp, department_id_id=dept_id)
        for jp, dept_id in valid_pairs
        if (jp, dept_id) not in existing_pairs
    ]

    # Step 6: Bulk create in a transaction
    if new_positions:
        with transaction.atomic():
            JobPosition.objects.bulk_create(
                new_positions, batch_size=None if is_postgres else 999
            )


def bulk_create_job_role_import(success_lists):
    """
    Bulk creation of job role instances based on the excel import of employees
    """
    # Extract unique (job_role, job_position) pairs, filtering out empty values
    job_roles_to_import = {
        (role, pos)
        for work_info in success_lists
        if (role := work_info.get("Job Role"))
        and (pos := work_info.get("Job Position"))
    }

    # Prefetch existing data efficiently
    job_positions = JobPosition.objects.only("id", "job_position")
    job_position_lookup = {jp.job_position: jp.id for jp in job_positions}

    existing_job_roles = set(JobRole.objects.values_list("job_role", "job_position_id"))

    # Create new job roles
    new_job_roles = [
        JobRole(job_role=role, job_position_id_id=job_position_lookup[pos])
        for role, pos in job_roles_to_import
        if pos in job_position_lookup
        and (role, job_position_lookup[pos]) not in existing_job_roles
    ]

    # Bulk create if there are new roles
    if new_job_roles:
        with transaction.atomic():
            JobRole.objects.bulk_create(
                new_job_roles, batch_size=None if is_postgres else 999
            )


def bulk_create_work_types(success_lists):
    """
    Bulk creation of work type instances based on the excel import of employees
    """
    # Extract unique work types, filtering out None values
    work_types_to_import = {
        wt for work_info in success_lists if (wt := work_info.get("Work Type"))
    }

    # Get existing work types in one optimized query
    existing_work_types = set(WorkType.objects.values_list("work_type", flat=True))

    # Create new work type objects
    new_work_types = [
        WorkType(work_type=wt) for wt in work_types_to_import - existing_work_types
    ]

    # Bulk create if there are new work types
    if new_work_types:
        with transaction.atomic():
            WorkType.objects.bulk_create(
                new_work_types, batch_size=None if is_postgres else 999
            )


def bulk_create_shifts(success_lists):
    """
    Bulk creation of shift instances based on the excel import of employees
    """
    # Extract unique shifts, filtering out None values
    shifts_to_import = {
        shift for work_info in success_lists if (shift := work_info.get("Shift"))
    }

    # Get existing shifts in one optimized query
    existing_shifts = set(
        EmployeeShift.objects.values_list("employee_shift", flat=True)
    )

    # Create new shift objects
    new_shifts = [
        EmployeeShift(employee_shift=shift)
        for shift in shifts_to_import - existing_shifts
    ]

    # Bulk create if there are new shifts
    if new_shifts:
        with transaction.atomic():
            EmployeeShift.objects.bulk_create(
                new_shifts, batch_size=None if is_postgres else 999
            )


def bulk_create_employee_types(success_lists):
    """
    Bulk creation of EmployeeType instances based on imported employee data.
    """

    employee_types_to_import = {
        et for row in success_lists if (et := row.get("Employee Type"))
    }

    if not employee_types_to_import:
        return

    existing_employee_types = set(
        EmployeeType.objects.values_list("employee_type", flat=True)
    )

    new_employee_types = [
        EmployeeType(employee_type=et)
        for et in employee_types_to_import - existing_employee_types
    ]

    if new_employee_types:
        with transaction.atomic():
            EmployeeType.objects.bulk_create(
                new_employee_types, batch_size=None if is_postgres else 999
            )


def create_contracts_in_thread(new_work_info_list, update_work_info_list):
    """
    Creates employee contracts in bulk based on provided work information.
    """
    from payroll.models.models import Contract

    contracts_list = [
        Contract(
            contract_name=f"{work_info.employee_id}'s Contract",
            employee_id=work_info.employee_id,
            contract_start_date=(
                work_info.date_joining if work_info.date_joining else datetime.today()
            ),
            department=work_info.department_id,
            job_position=work_info.job_position_id,
            job_role=work_info.job_role_id,
            shift=work_info.shift_id,
            work_type=work_info.work_type_id,
            wage=work_info.basic_salary or 0,
        )
        for work_info in new_work_info_list + update_work_info_list
        if work_info.employee_id
    ]

    Contract.objects.bulk_create(contracts_list)


def bulk_create_work_info_import(success_lists):
    """
    Bulk creation of employee work info instances based on the excel import of employees
    """
    new_work_info_list = []
    update_work_info_list = []

    badge_ids = [row["Badge ID"] for row in success_lists]
    departments = set(row.get("Department") for row in success_lists)
    job_positions = set(row.get("Job Position") for row in success_lists)
    job_roles = set(row.get("Job Role") for row in success_lists)
    work_types = set(row.get("Work Type") for row in success_lists)
    employee_types = set(row.get("Employee Type") for row in success_lists)
    shifts = set(row.get("Shift") for row in success_lists)
    companies = set(row.get("Company") for row in success_lists)

    chunk_size = None if is_postgres else 999
    employee_qs = (
        chain.from_iterable(
            Employee.objects.entire().filter(badge_id__in=chunk).only("badge_id")
            for chunk in chunked(badge_ids, chunk_size)
        )
        if chunk_size
        else Employee.objects.entire().filter(badge_id__in=badge_ids).only("badge_id")
    )

    existing_employees = {emp.badge_id: emp for emp in employee_qs}

    existing_employee_work_infos = {
        emp.employee_id: emp
        for emp in (
            EmployeeWorkInformation.objects.filter(
                employee_id__in=existing_employees.values()
            ).only("employee_id")
            if is_postgres
            else chain.from_iterable(
                EmployeeWorkInformation.objects.filter(employee_id__in=chunk).only(
                    "employee_id"
                )
                for chunk in chunked(list(existing_employees.values()), 900)
            )
        )
    }

    existing_departments = {
        dep.department: dep
        for dep in Department.objects.filter(department__in=departments).only(
            "department"
        )
    }
    existing_job_positions = {
        (jp.department_id, jp.job_position): jp
        for jp in JobPosition.objects.filter(job_position__in=job_positions)
        .select_related("department_id")
        .only("department_id", "job_position")
    }
    existing_job_roles = {
        (jr.job_position_id, jr.job_role): jr
        for jr in JobRole.objects.filter(job_role__in=job_roles)
        .select_related("job_position_id")
        .only("job_position_id", "job_role")
    }
    existing_work_types = {
        wt.work_type: wt
        for wt in WorkType.objects.filter(work_type__in=work_types).only("work_type")
    }
    existing_shifts = {
        es.employee_shift: es
        for es in EmployeeShift.objects.filter(employee_shift__in=shifts).only(
            "employee_shift"
        )
    }
    existing_employee_types = {
        et.employee_type: et
        for et in EmployeeType.objects.filter(employee_type__in=employee_types).only(
            "employee_type"
        )
    }
    existing_companies = {
        comp.company: comp
        for comp in Company.objects.filter(company__in=companies).only("company")
    }
    reporting_manager_dict = optimize_reporting_manager_lookup()

    for work_info in success_lists:
        badge_id = work_info["Badge ID"]
        employee_obj = existing_employees.get(badge_id)
        if not employee_obj:
            continue

        email = work_info["Email"]
        employee_work_info = existing_employee_work_infos.get(employee_obj)
        department_obj = existing_departments.get(work_info.get("Department"))

        job_position_key = (
            existing_departments.get(work_info.get("Department")),
            work_info.get("Job Position"),
        )
        job_position_obj = existing_job_positions.get(job_position_key)

        job_role_key = (
            job_position_obj,
            work_info.get("Job Role"),
        )
        job_role_obj = existing_job_roles.get(job_role_key)

        work_type_obj = existing_work_types.get(work_info.get("Work Type"))
        employee_type_obj = existing_employee_types.get(work_info.get("Employee Type"))
        shift_obj = existing_shifts.get(work_info.get("Shift"))
        reporting_manager = work_info.get("Reporting Manager")
        reporting_manager_obj = None
        if isinstance(reporting_manager, str) and " " in reporting_manager:
            if reporting_manager in reporting_manager_dict:
                reporting_manager_obj = reporting_manager_dict[reporting_manager]

        company_obj = existing_companies.get(work_info.get("Company"))
        location = work_info.get("Location")

        # Parsing dates and salary
        date_joining = (
            work_info["Date Joining"]
            if not pd.isnull(work_info["Date Joining"])
            else datetime.today()
        )

        contract_end_date = (
            work_info["Contract End Date"]
            if not pd.isnull(work_info["Contract End Date"])
            else None
        )
        basic_salary = (
            work_info.get("Basic Salary") if work_info.get("Basic Salary") else 0
        )
        salary_hour = (
            work_info.get("Salary Hour") if work_info.get("Salary Hour") else 0
        )

        if employee_work_info is None:
            # Create a new instance
            employee_work_info = EmployeeWorkInformation(
                employee_id=employee_obj,
                email=email,
                department_id=department_obj,
                job_position_id=job_position_obj,
                job_role_id=job_role_obj,
                work_type_id=work_type_obj,
                employee_type_id=employee_type_obj,
                shift_id=shift_obj,
                reporting_manager_id=reporting_manager_obj,
                company_id=company_obj,
                location=location,
                date_joining=(
                    date_joining if not pd.isnull(date_joining) else datetime.today()
                ),
                contract_end_date=(
                    contract_end_date if not pd.isnull(contract_end_date) else None
                ),
                basic_salary=basic_salary,
                salary_hour=salary_hour,
            )
            new_work_info_list.append(employee_work_info)
        else:
            # Update the existing instance
            employee_work_info.email = email
            employee_work_info.department_id = department_obj
            employee_work_info.job_position_id = job_position_obj
            employee_work_info.job_role_id = job_role_obj
            employee_work_info.work_type_id = work_type_obj
            employee_work_info.employee_type_id = employee_type_obj
            employee_work_info.shift_id = shift_obj
            employee_work_info.reporting_manager_id = reporting_manager_obj
            employee_work_info.company_id = company_obj
            employee_work_info.location = location
            employee_work_info.date_joining = (
                date_joining if not pd.isnull(date_joining) else datetime.today()
            )
            employee_work_info.contract_end_date = (
                contract_end_date if not pd.isnull(contract_end_date) else None
            )
            employee_work_info.basic_salary = basic_salary
            employee_work_info.salary_hour = salary_hour
            update_work_info_list.append(employee_work_info)
    if new_work_info_list:
        EmployeeWorkInformation.objects.bulk_create(
            new_work_info_list, batch_size=None if is_postgres else 999
        )
    if update_work_info_list:
        EmployeeWorkInformation.objects.bulk_update(
            update_work_info_list,
            [
                "email",
                "department_id",
                "job_position_id",
                "job_role_id",
                "work_type_id",
                "employee_type_id",
                "shift_id",
                "reporting_manager_id",
                "company_id",
                "location",
                "date_joining",
                "contract_end_date",
                "basic_salary",
                "salary_hour",
            ],
            batch_size=None if is_postgres else 999,
        )
    if apps.is_installed("payroll"):

        contract_creation_thread = threading.Thread(
            target=create_contracts_in_thread,
            args=(new_work_info_list, update_work_info_list),
        )
        contract_creation_thread.start()
