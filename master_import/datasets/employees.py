"""Employees: the person, their work information and bank account, in one sheet."""

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from django.contrib.auth.hashers import make_password
from django.db import transaction

from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.methods.methods import (
    bulk_create_department_import,
    bulk_create_employee_import,
    bulk_create_employee_types,
    bulk_create_job_position_import,
    bulk_create_job_role_import,
    bulk_create_shifts,
    bulk_create_user_import,
    bulk_create_work_info_import,
    bulk_create_work_types,
    process_employee_records,
    set_initial_password,
)
from employee.models import Employee, EmployeeBankDetails, EmployeeWorkInformation
from horilla_auth.models import HorillaUser
from payroll.models.models import SalaryStructure

from . import additional
from .base import Checked, Context, Dataset, Field
from .salary_structure import (
    get_or_create_structure,
    pick_structure,
    put_on_contract,
    structure_table,
)
from .scoping import managers_by_name, pick, pick_manager

BANK_KEYS = [
    "Bank Name",
    "Account Number",
    "Bank Branch",
    "Bank Code 1",
    "Bank Code 2",
    "Bank Country",
    "Bank State",
    "Bank City",
    "Bank Address",
]

# Where each column ends up, so a value too long for it is caught as that
# row's problem and not as a database error that stops the whole import.
LIMITS = {
    "Badge ID": (Employee, "badge_id"),
    "First Name": (Employee, "employee_first_name"),
    "Last Name": (Employee, "employee_last_name"),
    "Email": (Employee, "email"),
    "Phone": (Employee, "phone"),
    "Company": (Company, "company"),
    "Department": (Department, "department"),
    "Job Position": (JobPosition, "job_position"),
    "Job Role": (JobRole, "job_role"),
    "Work Type": (WorkType, "work_type"),
    "Shift": (EmployeeShift, "employee_shift"),
    "Employee Type": (EmployeeType, "employee_type"),
    "Location": (EmployeeWorkInformation, "location"),
    "Bank Name": (EmployeeBankDetails, "bank_name"),
    "Account Number": (EmployeeBankDetails, "account_number"),
    "Bank Branch": (EmployeeBankDetails, "branch"),
    "Bank Code 1": (EmployeeBankDetails, "any_other_code1"),
    "Bank Code 2": (EmployeeBankDetails, "any_other_code2"),
    "Bank Country": (EmployeeBankDetails, "country"),
    "Bank State": (EmployeeBankDetails, "state"),
    "Bank City": (EmployeeBankDetails, "city"),
}

# Error keys that do not carry the field's own name, and the fields they are about.
ERROR_FIELDS = {
    "Joining Date Error": ["Date Joining"],
    "Contract Date Error": ["Contract End Date", "Date Joining"],
    "Name and Email Error": ["First Name", "Last Name", "Email"],
    "User ID Error": ["Email"],
    "Bank Error": ["Bank Name", "Account Number"],
}

GENDERS = {
    "m": "male",
    "male": "male",
    "man": "male",
    "f": "female",
    "female": "female",
    "woman": "female",
    "o": "other",
    "other": "other",
    "others": "other",
}


def _text(value):
    """Numbers that came out of a spreadsheet as 9876543210.0 are the text 9876543210."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


class _FieldList:
    """``fields`` of the employee sheet: the fixed ones, then a column for each additional info field."""

    def __get__(self, instance, owner):
        extra = [
            Field(
                c.key,
                group="Additional Info",
                sample=c.sample,
                aliases=c.aliases,
                kind=c.kind,
                suggest=f"additional:{c.key}" if c.kind == "suggest" else "",
            )
            for c in owner.additional_columns()
        ]
        return list(owner.BASE_FIELDS) + extra


class EmployeesDataset(Dataset):
    key = "employees"
    label = "Employees"
    subtitle = "People, work information and bank details"
    icon = "people-outline"
    permission = "employee.add_employee"
    update_permissions = ["employee.change_employee"]
    supports_update = True
    match_choices = ["Badge ID", "Email", "Phone"]
    preview_columns = [
        "Badge ID",
        "First Name",
        "Last Name",
        "Email",
        "Phone",
        "Company",
        "Department",
        "Job Position",
        "Date Joining",
    ]
    created_models = {
        "companies": Company,
        "departments": Department,
        "job_positions": JobPosition,
        "salary_structures": SalaryStructure,
    }

    BASE_FIELDS = [
        Field(
            "Badge ID",
            required=True,
            group="Person",
            sample="E-1048",
            aliases=(
                "employee id",
                "emp id",
                "employee code",
                "staff id",
                "badge",
                "id",
                "employee number",
            ),
        ),
        Field(
            "First Name",
            required=True,
            group="Person",
            sample="Maya",
            aliases=("firstname", "given name", "fname"),
        ),
        Field(
            "Last Name",
            group="Person",
            sample="Chen",
            aliases=("lastname", "surname", "family name", "lname"),
        ),
        Field(
            "Full Name",
            group="Person",
            sample="",
            aliases=("name", "employee name", "full name"),
        ),
        Field(
            "Email",
            required=False,
            group="Person",
            sample="maya.chen@acme.co",
            aliases=("work email", "email address", "e-mail", "mail", "official email"),
            kind="email",
        ),
        Field(
            "Phone",
            required=False,
            group="Person",
            sample="9876543210",
            aliases=(
                "mobile",
                "phone number",
                "contact",
                "contact number",
                "mobile number",
                "cell",
            ),
            kind="tel",
        ),
        Field(
            "Gender",
            group="Person",
            sample="female",
            aliases=("sex",),
            kind="choice",
            choices=("male", "female", "other"),
        ),
        Field(
            "Address",
            group="Person",
            sample="12 Park Street",
            aliases=("home address",),
        ),
        Field(
            "Username",
            group="Login",
            sample="",
            aliases=("user name", "login", "user id", "login id"),
        ),
        Field(
            "Password",
            group="Login",
            sample="",
            aliases=("initial password", "temp password"),
            kind="password",
        ),
        Field(
            "Company",
            group="Work",
            sample="Acme Ltd",
            aliases=("company name", "organisation", "organization", "entity"),
            kind="suggest",
            suggest="companies",
        ),
        Field(
            "Department",
            group="Work",
            sample="Engineering",
            aliases=("dept", "team"),
            kind="suggest",
            suggest="departments",
        ),
        Field(
            "Job Position",
            group="Work",
            sample="Product designer",
            aliases=("position", "designation", "title", "job title"),
            kind="suggest",
            suggest="job_positions",
        ),
        Field(
            "Job Role",
            group="Work",
            sample="Designer",
            aliases=("role",),
            kind="suggest",
            suggest="job_roles",
        ),
        Field(
            "Work Type",
            group="Work",
            sample="Remote",
            aliases=("worktype",),
            kind="suggest",
            suggest="work_types",
        ),
        Field(
            "Shift",
            group="Work",
            sample="Day",
            aliases=("employee shift",),
            kind="suggest",
            suggest="shifts",
        ),
        Field(
            "Employee Type",
            group="Work",
            sample="Full-Time",
            aliases=("employment type", "emp type"),
            kind="suggest",
            suggest="employee_types",
        ),
        Field(
            "Reporting Manager",
            group="Work",
            sample="Jon Bell",
            aliases=("manager", "reports to", "supervisor"),
        ),
        Field(
            "Location",
            group="Work",
            sample="Austin",
            aliases=("work location", "office", "branch location"),
        ),
        Field(
            "Date Joining",
            group="Work",
            sample="2024-06-12",
            aliases=(
                "start date",
                "joining date",
                "date of joining",
                "doj",
                "hire date",
            ),
            kind="date",
        ),
        Field(
            "Contract End Date",
            group="Work",
            sample="",
            aliases=("end date", "contract end"),
            kind="date",
        ),
        Field(
            "Basic Salary",
            group="Pay",
            sample="45000",
            aliases=("salary", "wage", "basic"),
            kind="number",
        ),
        Field(
            "Salary Hour",
            group="Pay",
            sample="",
            aliases=("hourly wage", "hourly rate"),
            kind="number",
        ),
        Field(
            "CTC",
            group="Pay",
            sample="",
            aliases=("monthly ctc", "cost to company"),
            kind="number",
        ),
        Field(
            "Salary Structure",
            group="Pay",
            sample="",
            aliases=("structure", "pay structure", "salary structure name"),
            kind="suggest",
            suggest="salary_structures",
        ),
        Field("Bank Name", group="Bank", sample="First National", aliases=("bank",)),
        Field(
            "Account Number",
            group="Bank",
            sample="000123456789",
            aliases=(
                "account no",
                "a/c no",
                "account",
                "bank account",
                "bank account number",
            ),
        ),
        Field("Bank Branch", group="Bank", sample="Main", aliases=("branch",)),
        Field(
            "Bank Code 1",
            group="Bank",
            sample="FNBK0001",
            aliases=("ifsc", "swift", "routing number", "sort code"),
        ),
        Field("Bank Code 2", group="Bank", sample="", aliases=("micr",)),
        Field("Bank Country", group="Bank", sample=""),
        Field("Bank State", group="Bank", sample=""),
        Field("Bank City", group="Bank", sample=""),
        Field("Bank Address", group="Bank", sample=""),
    ]
    fields = _FieldList()

    @classmethod
    def additional_columns(cls):
        """The additional info columns, named so that none repeats a fixed column."""
        taken = {name for f in cls.BASE_FIELDS for name in (f.key, f.label, *f.aliases)}
        return additional.columns(taken)

    def suggestions(self):
        def names(model, column):
            return sorted(
                set(model.objects.entire().values_list(column, flat=True)) - {None, ""}
            )

        offered = {
            f"additional:{c.key}": c.options
            for c in self.additional_columns()
            if c.options
        }
        return {
            **offered,
            "companies": sorted(Company.objects.values_list("company", flat=True)),
            "departments": names(Department, "department"),
            "job_positions": names(JobPosition, "job_position"),
            "job_roles": names(JobRole, "job_role"),
            "work_types": names(WorkType, "work_type"),
            "shifts": names(EmployeeShift, "employee_shift"),
            "employee_types": names(EmployeeType, "employee_type"),
            "salary_structures": sorted({t for t in structure_table()}),
        }

    # ------------------------------------------------------------ prepare
    def prepare(self, rows, ctx):
        for row in rows:
            full = row.get("Full Name")
            if full and not row.get("First Name"):
                first, _, last = str(full).strip().partition(" ")
                row["First Name"] = first
                row["Last Name"] = row.get("Last Name") or (last or None)
            for key in (
                "Badge ID",
                "Phone",
                "Account Number",
                "Bank Code 1",
                "Bank Code 2",
            ):
                row[key] = _text(row.get(key))
            for key in ("Date Joining", "Contract End Date"):
                value = row.get(key)
                # A date cell read as text carries a midnight time with it.
                if isinstance(value, str) and re.match(
                    r"^\d{4}-\d{2}-\d{2}[ T]", value
                ):
                    row[key] = value[:10]
            # Sign-in name: what the sheet gives, else the email, else the badge ID.
            row["Username"] = (
                _text(row.get("Username"))
                or _text(row.get("Email"))
                or row.get("Badge ID")
            )
            row["Password"] = _text(row.get("Password"))
            gender = row.get("Gender")
            if gender:
                row["Gender"] = GENDERS.get(
                    str(gender).strip().lower(), str(gender).strip().lower()
                )
            # On a single company the sheet need not name it.
            if ctx.company and not row.get("Company"):
                row["Company"] = ctx.company.company
        return rows

    # -------------------------------------------------------------- check
    def check(
        self, rows, ctx: Context, progress=None, mode="create", match_keys=()
    ) -> Checked:
        if mode == "update":
            from .employee_update import EmployeeUpdater

            return EmployeeUpdater(self).check(rows, ctx, list(match_keys), progress)
        if mode == "both":
            return self._check_both(rows, ctx, progress, list(match_keys))
        return self._check_create(rows, ctx, progress)

    def _check_both(self, rows, ctx, progress, match_keys):
        """Rows that find an existing person update them; the rest are created."""
        from .employee_update import EmployeeUpdater

        updater = EmployeeUpdater(self)
        rows = self.prepare(rows, ctx)
        existing, new = updater.split_known(rows, ctx, match_keys)
        if progress:
            progress(10)
        updated = updater.check(existing, ctx, match_keys) if existing else Checked()
        if progress:
            progress(45)
        created = self._check_create(new, ctx) if new else Checked()
        for row in updated.valid:
            row["__op"] = "update"
        for row in created.valid:
            row["__op"] = "create"
            row["__changes"] = ["New employee"]
        merged = Checked(
            valid=sorted(updated.valid + created.valid, key=lambda r: r["__row"]),
            errors=sorted(updated.errors + created.errors, key=lambda e: e["row"]),
            unchanged=updated.unchanged,
        )
        for source in (created.will_create, updated.will_create):
            for key, names in source.items():
                merged.will_create[key] = sorted(
                    set(merged.will_create.get(key, [])) | set(names)
                )
        if progress:
            progress(100)
        return merged

    def _check_create(self, rows, ctx: Context, progress=None) -> Checked:
        rows = self.prepare(rows, ctx)
        result = Checked()
        if not rows:
            return result

        keys = ["__row"] + [f.key for f in self.fields]
        frame = pd.DataFrame(rows, columns=keys).astype(object)
        frame = frame.where(pd.notnull(frame), None)

        # Any company may be named, and a new one is created, only when the
        # session is on all companies; on one company the sheet must match it.
        def rows_done(done, total):
            if progress:
                progress(5 + int(done / total * 80))

        success, errors, _count = process_employee_records(
            frame,
            ctx.company,
            auto_create_companies=ctx.company is None,
            progress=rows_done,
        )

        structures = structure_table()
        taken = set(HorillaUser.objects.values_list("username", flat=True))
        extra_columns = self.additional_columns()
        valid = []
        for row in success:
            too_long = self._too_long(row)
            too_long.update(self._login_problems(row, taken))
            problem = self._bank_problem(row)
            if extra_columns:
                row["__additional"], column_problems = (
                    additional.importing().values_from_row(row, extra_columns)
                )
                too_long.update(column_problems)
            if row.get("Salary Structure"):
                found, why = pick_structure(
                    row["Salary Structure"], row.get("Company"), structures
                )
                if why:
                    too_long["Salary Structure Error"] = why
                elif found is not None:
                    row["__structure"] = found.pk
                else:
                    row["__structure_new"] = row["Salary Structure"]
            if too_long or problem:
                row.update(too_long)
                if problem:
                    row["Bank Error"] = problem
                errors.append(row)
            else:
                valid.append(row)

        if progress:
            progress(90)
        result.valid = valid
        result.errors = [self._error_entry(row) for row in errors]
        result.errors.sort(key=lambda e: e["row"])
        result.will_create = self._will_create(valid, ctx)
        if progress:
            progress(100)
        return result

    @staticmethod
    def _too_long(row):
        """{"<Field> Error": message} for each value longer than its column allows."""
        found = {}
        for key, (model, name) in LIMITS.items():
            limit = model._meta.get_field(name).max_length
            value = row.get(key)
            if limit and value is not None and len(str(value)) > limit:
                found[f"{key} Error"] = (
                    f"{key} is {len(str(value))} characters; the most allowed is {limit}."
                )
        return found

    @staticmethod
    def _login_problems(row, taken):
        """Errors for a username already in use (here or in the file) or too long."""
        found = {}
        username = row.get("Username")
        if username in taken:
            found["Username Error"] = "This username is already in use."
        elif len(username) > HorillaUser._meta.get_field("username").max_length:
            found["Username Error"] = "This username is too long."
        else:
            taken.add(username)
        return found

    @staticmethod
    def _bank_problem(row):
        given = [k for k in BANK_KEYS if row.get(k)]
        if not given:
            return ""
        if not row.get("Bank Name") or not row.get("Account Number"):
            return "Bank details need both a bank name and an account number."
        return ""

    @staticmethod
    def _error_entry(row):
        keys = {f.key for f in EmployeesDataset.fields}
        messages, by_field = [], {}
        for key, value in row.items():
            if not (str(key).endswith(" Error") and value):
                continue
            messages.append(str(value))
            for field in ERROR_FIELDS.get(key) or [key[: -len(" Error")]]:
                if field in keys:
                    by_field.setdefault(field, str(value))
        name = " ".join(filter(None, [row.get("First Name"), row.get("Last Name")]))
        return {
            "row": int(row.get("__row") or 0),
            "name": name or "-",
            "badge": row.get("Badge ID") or "-",
            "messages": messages,
            "by_field": by_field,
            "data": {
                k: v
                for k, v in row.items()
                if k in {f.key for f in EmployeesDataset.fields}
            },
        }

    @staticmethod
    def _will_create(valid, ctx):
        """What the import would add besides the people, matched on exact spelling."""

        def new(names, existing):
            return sorted({n for n in names if n and n not in existing})

        return {
            "companies": new(
                (r.get("Company") for r in valid) if ctx.company is None else [],
                set(Company.objects.values_list("company", flat=True)),
            ),
            "departments": new(
                (r.get("Department") for r in valid),
                set(Department.objects.entire().values_list("department", flat=True)),
            ),
            "job_positions": new(
                (r.get("Job Position") for r in valid),
                set(
                    JobPosition.objects.entire().values_list("job_position", flat=True)
                ),
            ),
            "salary_structures": sorted(
                {r["__structure_new"] for r in valid if r.get("__structure_new")}
            ),
        }

    # ------------------------------------------------------------- commit
    @staticmethod
    def _hash_passwords(rows, progress):
        """Hash the sheet's passwords side by side; one hash is deliberately slow (~0.7s)."""
        wanted = [r for r in rows if r.get("Password")]
        if not wanted:
            return
        done = 0
        with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 2, 16)) as pool:
            futures = {pool.submit(make_password, r["Password"]): r for r in wanted}
            for future in as_completed(futures):
                futures[future]["__hash"] = future.result()
                done += 1
                if progress:
                    progress(5 + int(done / len(wanted) * 70))

    def commit(self, rows, ctx: Context, mode="create", progress=None) -> dict:
        """``progress(percent)`` is called as the import goes, 0 to 100."""
        if mode == "update":
            from .employee_update import EmployeeUpdater

            return EmployeeUpdater(self).commit(rows, ctx)
        if mode == "both":
            return self._commit_both(rows, ctx, progress)
        step = progress or (lambda percent: None)
        step(5)
        self._hash_passwords(rows, step)
        counts_before = {
            "departments": Department.objects.entire().count(),
            "job_positions": JobPosition.objects.entire().count(),
            "job_roles": JobRole.objects.entire().count(),
            "work_types": WorkType.objects.entire().count(),
            "shifts": EmployeeShift.objects.entire().count(),
            "employee_types": EmployeeType.objects.entire().count(),
            "salary_structures": SalaryStructure.objects.entire().count(),
        }
        companies_created = 0
        banks_created = 0
        with transaction.atomic():
            if ctx.company is None:
                existing = set(Company.objects.values_list("company", flat=True))
                for name in sorted(
                    {r["Company"] for r in rows if r.get("Company")} - existing
                ):
                    Company.objects.create(company=name)
                    companies_created += 1

            if ctx.company is not None:
                self._share_with_company(rows, ctx.company)
            bulk_create_user_import(rows)
            step(80)
            employees = bulk_create_employee_import(rows)
            bulk_create_department_import(rows)
            bulk_create_job_position_import(rows)
            bulk_create_job_role_import(rows)
            bulk_create_work_types(rows)
            bulk_create_shifts(rows)
            bulk_create_employee_types(rows)
            step(88)
            bulk_create_work_info_import(rows)
            self._own_company_records(rows, ctx)
            step(94)
            banks_created = self._create_banks(rows)
            additional_written = self._create_additional(rows)
            structures_set = self._apply_structures(rows)
            step(100)

        # A random password for everyone the sheet gave none, so nobody can
        # sign in until they are invited.
        has_password = {r["Badge ID"] for r in rows if r.get("Password")}
        threading.Thread(
            target=set_initial_password,
            args=([e for e in employees if e.badge_id not in has_password],),
        ).start()

        return {
            "employees": len(employees),
            "banks": banks_created,
            "additional_values": additional_written,
            "structures": structures_set,
            "companies": companies_created,
            "departments": Department.objects.entire().count()
            - counts_before["departments"],
            "job_positions": JobPosition.objects.entire().count()
            - counts_before["job_positions"],
            "job_roles": JobRole.objects.entire().count() - counts_before["job_roles"],
            "work_types": WorkType.objects.entire().count()
            - counts_before["work_types"],
            "shifts": EmployeeShift.objects.entire().count() - counts_before["shifts"],
            "employee_types": EmployeeType.objects.entire().count()
            - counts_before["employee_types"],
            "salary_structures": SalaryStructure.objects.entire().count()
            - counts_before["salary_structures"],
        }

    def _commit_both(self, rows, ctx, progress):
        from .employee_update import EmployeeUpdater

        new = [r for r in rows if r.get("__op") == "create"]
        known = [r for r in rows if r.get("__op") == "update"]
        counts = self.commit(new, ctx, "create", progress) if new else {}
        if known:
            for key, value in EmployeeUpdater(self).commit(known, ctx).items():
                counts[key] = counts.get(key, 0) + value
        if progress:
            progress(100)
        counts.setdefault("updated", 0)
        counts.setdefault("employees", 0)
        return counts

    @staticmethod
    def _own_company_records(rows, ctx):
        """Give each person their own company's department, position, role and manager.

        The creation steps match on the name alone, so two companies that each have
        a "Sales" end up sharing whichever was found last. This points each person
        at the one that belongs to their company.
        """
        employees = {
            e.badge_id: e
            for e in Employee.objects.entire().filter(
                badge_id__in=[r["Badge ID"] for r in rows]
            )
        }
        infos = {
            i.employee_id_id: i
            for i in EmployeeWorkInformation.objects.entire().filter(
                employee_id__in=employees.values()
            )
        }
        companies = {c.company: c for c in Company.objects.all()}
        managers = managers_by_name()
        for row in rows:
            employee = employees.get(row["Badge ID"])
            info = infos.get(employee.pk) if employee else None
            if info is None:
                continue
            company = companies.get(row.get("Company")) or ctx.company
            changes = {}
            department = info.department_id
            if row.get("Department"):
                department = (
                    pick(Department, "department", row["Department"], company)
                    or department
                )
                changes["department_id"] = department
            position = info.job_position_id
            if row.get("Job Position") and department is not None:
                position = (
                    pick(
                        JobPosition,
                        "job_position",
                        row["Job Position"],
                        company,
                        department_id=department,
                    )
                    or position
                )
                changes["job_position_id"] = position
            if row.get("Job Role") and position is not None:
                role = pick(
                    JobRole,
                    "job_role",
                    row["Job Role"],
                    company,
                    job_position_id=position,
                )
                if role is not None:
                    changes["job_role_id"] = role
            if row.get("Reporting Manager"):
                manager = pick_manager(row["Reporting Manager"], company, managers)
                if manager is not None and manager.pk != employee.pk:
                    changes["reporting_manager_id"] = manager
            if changes:
                EmployeeWorkInformation.objects.entire().filter(pk=info.pk).update(
                    **changes
                )

    @staticmethod
    def _share_with_company(rows, company):
        """A master that already exists for another company is reused, not copied.

        The creation steps only look at what the selected company can see, so a
        department that belongs to another company would be made a second time.
        Adding this company to one existing record makes the lookup find it. A
        name this company already has, or that belongs to no company at all, is
        left alone, so a company with its own "Sales" is never given another's.
        """
        for label, model, column in (
            ("Department", Department, "department"),
            ("Job Position", JobPosition, "job_position"),
            ("Job Role", JobRole, "job_role"),
        ):
            try:
                field = model._meta.get_field("company_id")
            except Exception:
                continue
            if not field.many_to_many:
                continue
            names = {r[label] for r in rows if r.get(label)}
            by_name = {}
            for record in (
                model.objects.entire()
                .filter(**{f"{column}__in": names})
                .prefetch_related("company_id")
            ):
                by_name.setdefault(getattr(record, column), []).append(record)
            for records in by_name.values():
                # already this company's, or everyone's: nothing to share
                if any(
                    company in r.company_id.all() or not r.company_id.all()
                    for r in records
                ):
                    continue
                records[0].company_id.add(company)

    @staticmethod
    def _apply_structures(rows):
        """Each new person's contract (made by the work-information step) gets its structure."""
        wanted = [r for r in rows if r.get("__structure") or r.get("__structure_new")]
        if not wanted:
            return 0
        employees = {
            e.badge_id: e
            for e in Employee.objects.entire().filter(
                badge_id__in=[r["Badge ID"] for r in wanted]
            )
        }
        from payroll.models.models import SalaryStructure

        structures = {
            s.pk: s
            for s in SalaryStructure.objects.entire().filter(
                pk__in={r["__structure"] for r in wanted if r.get("__structure")}
            )
        }
        made = {}
        done = 0
        for row in wanted:
            employee = employees.get(row["Badge ID"])
            if employee is None:
                continue
            structure = (
                structures[row["__structure"]]
                if row.get("__structure")
                else get_or_create_structure(
                    row["__structure_new"], row.get("Company"), made
                )
            )
            if put_on_contract(employee, structure):
                done += 1
        return done

    @staticmethod
    def _create_additional(rows):
        """The additional info values of the people just created; how many were saved."""
        wanted = [r for r in rows if r.get("__additional")]
        if not wanted:
            return 0
        employees = {
            e.badge_id: e
            for e in Employee.objects.entire().filter(
                badge_id__in=[r["Badge ID"] for r in wanted]
            )
        }
        return additional.importing().write_values(
            [
                (employees[r["Badge ID"]], r["__additional"])
                for r in wanted
                if r["Badge ID"] in employees
            ]
        )

    @staticmethod
    def _create_banks(rows):
        wanted = [r for r in rows if r.get("Bank Name") and r.get("Account Number")]
        if not wanted:
            return 0
        employees = {
            e.badge_id: e
            for e in Employee.objects.entire().filter(
                badge_id__in=[r["Badge ID"] for r in wanted]
            )
        }
        has_bank = set(
            EmployeeBankDetails.objects.entire()
            .filter(employee_id__in=employees.values())
            .values_list("employee_id", flat=True)
        )
        new = [
            EmployeeBankDetails(
                employee_id=employees[r["Badge ID"]],
                bank_name=r["Bank Name"],
                account_number=r["Account Number"],
                branch=r.get("Bank Branch"),
                any_other_code1=r.get("Bank Code 1"),
                any_other_code2=r.get("Bank Code 2"),
                country=r.get("Bank Country"),
                state=r.get("Bank State"),
                city=r.get("Bank City"),
                address=r.get("Bank Address"),
            )
            for r in wanted
            if r["Badge ID"] in employees
            and employees[r["Badge ID"]].pk not in has_bank
        ]
        EmployeeBankDetails.objects.bulk_create(new)
        return len(new)
