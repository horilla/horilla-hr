"""Updating people who already exist, found by a key from the sheet.

Only the matched person is touched, a blank cell never overwrites a value, and a
row whose key finds nobody, or more than one person, is an error and not a guess.
"""

import re

from django.db import transaction

from base.models import (
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.methods.methods import (
    clean_badge_id,
    import_valid_date,
    normalize_phone,
    optimize_reporting_manager_lookup,
)
from employee.models import Employee, EmployeeBankDetails, EmployeeWorkInformation
from horilla_auth.models import HorillaUser
from payroll.models.models import SalaryStructure

from . import additional
from .base import Checked
from .salary_structure import (
    contract_of,
    get_or_create_structure,
    pick_structure,
    put_on_contract,
    structure_table,
)
from .scoping import managers_by_name, pick, pick_manager

EMAIL = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE = re.compile(r"^\+?\d{10,15}$")

# The fields that can be used to find a person. A combination must all agree.
MATCH_KEYS = ["Badge ID", "Email", "Phone"]

PERSON = {
    "First Name": "employee_first_name",
    "Last Name": "employee_last_name",
    "Gender": "gender",
    "Address": "address",
    "Phone": "phone",
}
# name column -> (work information FK, model, model's name column)
MASTERS = {
    "Department": ("department_id", Department, "department"),
    "Work Type": ("work_type_id", WorkType, "work_type"),
    "Shift": ("shift_id", EmployeeShift, "employee_shift"),
    "Employee Type": ("employee_type_id", EmployeeType, "employee_type"),
}
BANK = {
    "Bank Name": "bank_name",
    "Account Number": "account_number",
    "Bank Branch": "branch",
    "Bank Code 1": "any_other_code1",
    "Bank Code 2": "any_other_code2",
    "Bank Country": "country",
    "Bank State": "state",
    "Bank City": "city",
    "Bank Address": "address",
}


def _norm(key, value):
    value = str(value).strip()
    if key == "Email":
        return value.lower()
    if key == "Phone":
        return normalize_phone(value)
    return value


def _name(obj, column):
    return getattr(obj, column, "") if obj is not None else ""


class EmployeeUpdater:
    def __init__(self, dataset):
        self.dataset = dataset

    # ------------------------------------------------------------- loading
    def _employees(self, ctx):
        qs = Employee.objects.entire().select_related(
            "employee_work_info__department_id",
            "employee_work_info__job_position_id",
            "employee_work_info__job_role_id",
            "employee_work_info__work_type_id",
            "employee_work_info__shift_id",
            "employee_work_info__employee_type_id",
            "employee_work_info__reporting_manager_id",
            "employee_work_info__company_id",
            "employee_bank_details",
        )
        if ctx.company is not None:
            qs = qs.filter(employee_work_info__company_id=ctx.company)
        return list(qs)

    @staticmethod
    def _index(employees):
        index = {k: {} for k in MATCH_KEYS}
        for emp in employees:
            values = {
                "Badge ID": emp.badge_id,
                "Email": emp.email,
                "Phone": emp.phone,
            }
            for key, value in values.items():
                if value:
                    index[key].setdefault(_norm(key, value), []).append(emp)
        return index

    def split_known(self, rows, ctx, match_keys):
        """(rows that find someone, rows that find nobody): the second group are new people."""
        match_keys = [k for k in match_keys if k in MATCH_KEYS] or ["Badge ID"]
        index = self._index(self._employees(ctx))
        known, new = [], []
        for row in rows:
            hit = any(
                row.get(key) and index[key].get(_norm(key, row[key]))
                for key in match_keys
            )
            (known if hit else new).append(row)
        return known, new

    # --------------------------------------------------------------- check
    def check(self, rows, ctx, match_keys, progress=None) -> Checked:
        rows = self.dataset.prepare(rows, ctx)
        result = Checked()
        match_keys = [k for k in match_keys if k in MATCH_KEYS] or ["Badge ID"]
        employees = self._employees(ctx)
        index = self._index(employees)
        managers = managers_by_name()
        self.structures = structure_table()
        taken_emails = {
            e.lower() for e in HorillaUser.objects.values_list("username", flat=True)
        } | {
            e.lower()
            for e in Employee.objects.entire().values_list("email", flat=True)
            if e
        }
        seen_people, new_emails, new_badges = {}, set(), set()
        all_badges = {
            str(b)
            for b in Employee.objects.entire().values_list("badge_id", flat=True)
            if b
        }
        total = len(rows) or 1
        # Only the additional info columns the sheet fills in are looked at, with what people have now in one query.
        extra_columns = [
            c
            for c in self.dataset.additional_columns()
            if any(r.get(c.key) for r in rows)
        ]
        current = (
            additional.importing().current_values(None, extra_columns)
            if extra_columns
            else {}
        )

        for position, row in enumerate(rows, start=1):
            if progress and (position % 10 == 0 or position == total):
                progress(5 + int(position / total * 80))
            errors = {}
            employee = self._match(row, match_keys, index, errors)
            if employee is not None:
                if employee.pk in seen_people:
                    errors["Badge ID Error"] = (
                        f"This employee is already updated by row {seen_people[employee.pk]}."
                    )
                else:
                    seen_people[employee.pk] = row["__row"]
            if employee is not None and not errors:
                changes, apply = self._changes(
                    row,
                    employee,
                    match_keys,
                    managers,
                    taken_emails,
                    new_emails,
                    all_badges,
                    new_badges,
                    errors,
                )
                if extra_columns:
                    self._additional(
                        row, employee, current, extra_columns, changes, apply, errors
                    )
            else:
                changes, apply = [], {}

            if errors:
                row.update(errors)
                result.errors.append(self.dataset._error_entry(row))
            elif not changes:
                result.unchanged.append(row)
            else:
                row["__pk"] = employee.pk
                row["__changes"] = changes
                row["__apply"] = apply
                result.valid.append(row)

        result.errors.sort(key=lambda e: e["row"])
        result.will_create = self._will_create(result.valid)
        if progress:
            progress(100)
        return result

    @staticmethod
    def _additional(row, employee, current, columns, changes, apply, errors):
        """Additional info values the sheet changes for this person; a blank cell leaves the value as it is."""
        tools = additional.importing()
        values, problems = tools.values_from_row(row, columns)
        if problems:
            errors.update(problems)
            return
        by_pk = {c.field.pk: c for c in columns}
        delta = tools.changes_for(current.get(employee.pk, {}), values, columns)
        for pk, old, new in delta:
            column = by_pk[pk]
            changes.append(
                f"{column.key}: {tools.show(column.field, old)} → {tools.show(column.field, new)}"
            )
        if delta:
            apply["additional"] = {pk: new for pk, _old, new in delta}

    @staticmethod
    def _match(row, match_keys, index, errors):
        candidate_sets = []
        for key in match_keys:
            value = row.get(key)
            if not value:
                errors[f"{key} Error"] = (
                    f"{key} is empty, and it is used to find the employee."
                )
                continue
            found = index[key].get(_norm(key, value), [])
            if not found:
                errors[f"{key} Error"] = f"No employee has this {key}."
                continue
            candidate_sets.append({e.pk: e for e in found})
        if errors:
            return None
        shared = set.intersection(*(set(c) for c in candidate_sets))
        if not shared:
            errors[f"{match_keys[0]} Error"] = (
                " and ".join(match_keys) + " belong to different employees."
            )
            return None
        if len(shared) > 1:
            errors[f"{match_keys[0]} Error"] = (
                f"{len(shared)} employees share this "
                + " and ".join(match_keys)
                + "; it must find exactly one."
            )
            return None
        return candidate_sets[0][shared.pop()]

    def _changes(
        self,
        row,
        emp,
        match_keys,
        managers,
        taken_emails,
        new_emails,
        all_badges,
        new_badges,
        errors,
    ):
        from .employees import LIMITS

        info = getattr(emp, "employee_work_info", None)
        changes, apply = [], {
            "person": {},
            "work": {},
            "masters": {},
            "bank": {},
            "user": None,
        }

        def note(label, old, new):
            changes.append(f"{label}: {old if old not in (None, '') else '-'} → {new}")

        # values too long for their column are that row's error, found before saving
        errors.update(
            self.dataset._too_long(
                {k: v for k, v in row.items() if k not in match_keys}
            )
        )

        # ---- person
        for label, column in PERSON.items():
            new = row.get(label)
            if new is None:
                continue
            if label == "Phone":
                new = normalize_phone(new)
                if not PHONE.match(new):
                    errors["Phone Error"] = "Invalid phone number format."
                    continue
                if label in match_keys:
                    continue
            if label == "Gender":
                new = str(new).lower()
                if new not in dict(Employee.choice_gender):
                    errors["Gender Error"] = "Invalid gender."
                    continue
            old = getattr(emp, column)
            if str(old or "") != str(new):
                apply["person"][column] = new
                note(label, old, new)

        # ---- badge ID: changeable when people are found by something else
        new_badge = row.get("Badge ID")
        if new_badge and "Badge ID" not in match_keys:
            new_badge = clean_badge_id(new_badge)
            if new_badge and new_badge != str(emp.badge_id or ""):
                if new_badge in all_badges or new_badge in new_badges:
                    errors["Badge ID Error"] = (
                        "Another employee already has this Badge ID."
                    )
                else:
                    new_badges.add(new_badge)
                    apply["person"]["badge_id"] = new_badge
                    note("Badge ID", emp.badge_id, new_badge)

        # ---- email: it is also the sign-in name, so it only changes when found by badge ID
        new_email = row.get("Email")
        if new_email and "Email" not in match_keys:
            new_email = str(new_email).strip().lower()
            if not EMAIL.match(new_email):
                errors["Email Error"] = "Invalid email address."
            elif new_email != (emp.email or "").lower():
                if "Badge ID" not in match_keys:
                    errors["Email Error"] = (
                        "Email can only be changed when employees are found by Badge ID."
                    )
                elif new_email in taken_emails or new_email in new_emails:
                    errors["Email Error"] = "Another user already has this email."
                else:
                    new_emails.add(new_email)
                    apply["person"]["email"] = new_email
                    apply["user"] = new_email
                    note("Email", emp.email, new_email)

        # ---- company is never moved by an update
        company = row.get("Company")
        current = _name(getattr(info, "company_id", None), "company")
        if company and ctx_company_differs(company, current):
            errors["Company Error"] = (
                f"Belongs to {current or 'no company'}; an update does not move employees."
            )

        # ---- work information
        work_old = {
            "Department": _name(getattr(info, "department_id", None), "department"),
            "Job Position": _name(
                getattr(info, "job_position_id", None), "job_position"
            ),
            "Job Role": _name(getattr(info, "job_role_id", None), "job_role"),
            "Work Type": _name(getattr(info, "work_type_id", None), "work_type"),
            "Shift": _name(getattr(info, "shift_id", None), "employee_shift"),
            "Employee Type": _name(
                getattr(info, "employee_type_id", None), "employee_type"
            ),
        }
        for label, (fk, model, column) in MASTERS.items():
            new = row.get(label)
            if new and new != work_old[label]:
                apply["masters"][label] = new
                note(label, work_old[label], new)
        new_dept = row.get("Department") or work_old["Department"]
        new_position = row.get("Job Position")
        if new_position and new_position != work_old["Job Position"]:
            if not new_dept:
                errors["Job Position Error"] = "A job position needs a department."
            apply["masters"]["Job Position"] = new_position
            note("Job Position", work_old["Job Position"], new_position)
        new_role = row.get("Job Role")
        if new_role and new_role != work_old["Job Role"]:
            if not (new_position or work_old["Job Position"]):
                errors["Job Role Error"] = "A job role needs a job position."
            apply["masters"]["Job Role"] = new_role
            note("Job Role", work_old["Job Role"], new_role)

        manager = row.get("Reporting Manager")
        if manager:
            target = pick_manager(manager, getattr(info, "company_id", None), managers)
            if target is None:
                errors["Reporting Manager Error"] = f"No employee is named '{manager}'."
            elif target.pk == emp.pk:
                errors["Reporting Manager Error"] = (
                    "An employee cannot report to themselves."
                )
            elif target.pk != getattr(info, "reporting_manager_id_id", None):
                apply["work"]["reporting_manager_id"] = target
                current_manager = getattr(info, "reporting_manager_id", None)
                note(
                    "Reporting Manager",
                    current_manager.get_full_name() if current_manager else "",
                    manager,
                )

        location = row.get("Location")
        if location and location != (getattr(info, "location", "") or ""):
            apply["work"]["location"] = location
            note("Location", getattr(info, "location", ""), location)

        for label, column in (
            ("Date Joining", "date_joining"),
            ("Contract End Date", "contract_end_date"),
        ):
            if row.get(label) is None:
                continue
            date_errors = {}
            parsed = import_valid_date(row[label], label, date_errors, f"{label} Error")
            if date_errors:
                errors.update(date_errors)
            elif parsed and parsed != getattr(info, column, None):
                apply["work"][column] = parsed
                note(label, getattr(info, column, None), parsed)

        # ---- salary structure, on the employee's contract
        title = row.get("Salary Structure")
        if title:
            company_name = _name(getattr(info, "company_id", None), "company")
            found, why = pick_structure(title, company_name, self.structures)
            contract = contract_of(emp) if not why else None
            if why:
                errors["Salary Structure Error"] = why
            elif contract is None:
                errors["Salary Structure Error"] = (
                    "This employee has no contract to put the structure on."
                )
            elif found is None:
                apply["structure_new"] = (title, company_name)
                old = (
                    contract.salary_structure_id.title
                    if contract.salary_structure_id_id
                    else ""
                )
                note("Salary Structure", old, f"{title} (new)")
            elif contract.salary_structure_id_id != found.pk:
                apply["structure"] = found.pk
                old = (
                    contract.salary_structure_id.title
                    if contract.salary_structure_id_id
                    else ""
                )
                note("Salary Structure", old, title)

        # ---- bank
        bank = getattr(emp, "employee_bank_details", None)
        given = {label: row[label] for label in BANK if row.get(label)}
        if given:
            if bank is None and not (
                given.get("Bank Name") and given.get("Account Number")
            ):
                errors["Bank Error"] = (
                    "A new bank account needs both a bank name and an account number."
                )
            else:
                for label, value in given.items():
                    column = BANK[label]
                    old = getattr(bank, column, None) if bank else None
                    if str(old or "") != str(value):
                        apply["bank"][column] = value
                        note(label, old, value)
        apply["bank_new"] = bank is None

        return changes, apply

    @staticmethod
    def _will_create(valid):
        """New masters this update would add, by exact name."""
        wanted = {
            "departments": set(),
            "job_positions": set(),
            "job_roles": set(),
            "work_types": set(),
            "shifts": set(),
            "employee_types": set(),
            "salary_structures": set(),
        }
        keys = {
            "Department": "departments",
            "Job Position": "job_positions",
            "Job Role": "job_roles",
            "Work Type": "work_types",
            "Shift": "shifts",
            "Employee Type": "employee_types",
        }
        for row in valid:
            for label, bucket in keys.items():
                if label in row["__apply"]["masters"]:
                    wanted[bucket].add(row["__apply"]["masters"][label])
        for row in valid:
            if row["__apply"].get("structure_new"):
                wanted["salary_structures"].add(row["__apply"]["structure_new"][0])
        existing = {
            "salary_structures": set(),
            "departments": set(
                Department.objects.entire().values_list("department", flat=True)
            ),
            "job_positions": set(
                JobPosition.objects.entire().values_list("job_position", flat=True)
            ),
            "job_roles": set(
                JobRole.objects.entire().values_list("job_role", flat=True)
            ),
            "work_types": set(
                WorkType.objects.entire().values_list("work_type", flat=True)
            ),
            "shifts": set(
                EmployeeShift.objects.entire().values_list("employee_shift", flat=True)
            ),
            "employee_types": set(
                EmployeeType.objects.entire().values_list("employee_type", flat=True)
            ),
        }
        return {k: sorted(v - existing[k]) for k, v in wanted.items()}

    # -------------------------------------------------------------- commit
    def commit(self, rows, ctx) -> dict:
        updated = banks = 0
        pending = []
        structures_before = SalaryStructure.objects.entire().count()
        made_structures = {}
        with transaction.atomic():
            caches = {}

            def master(model, column, name, company=None, **extra):
                key = (
                    model,
                    column,
                    name,
                    getattr(company, "pk", None),
                    tuple(sorted((k, v.pk) for k, v in extra.items())),
                )
                if key not in caches:
                    found = pick(model, column, name, company, **extra)
                    caches[key] = found or model.objects.create(
                        **{column: name}, **extra
                    )
                return caches[key]

            for row in rows:
                apply = row["__apply"]
                emp = (
                    Employee.objects.entire()
                    .select_related("employee_work_info")
                    .get(pk=row["__pk"])
                )
                info = getattr(emp, "employee_work_info", None)
                company = getattr(info, "company_id", None)
                if apply["person"]:
                    Employee.objects.entire().filter(pk=emp.pk).update(
                        **apply["person"]
                    )
                if apply["user"]:
                    HorillaUser.objects.filter(pk=emp.employee_user_id_id).update(
                        username=apply["user"], email=apply["user"]
                    )

                work = dict(apply["work"])
                if apply["user"]:
                    work["email"] = apply["user"]
                names = apply["masters"]
                for label, (fk, model, column) in MASTERS.items():
                    if label in names:
                        work[fk] = master(model, column, names[label], company)
                if (
                    "Department" in names
                    or "Job Position" in names
                    or "Job Role" in names
                ):
                    dept = work.get("department_id") or getattr(
                        info, "department_id", None
                    )
                    position = getattr(info, "job_position_id", None)
                    if "Job Position" in names:
                        position = master(
                            JobPosition,
                            "job_position",
                            names["Job Position"],
                            company,
                            department_id=dept,
                        )
                        work["job_position_id"] = position
                    if "Job Role" in names:
                        work["job_role_id"] = master(
                            JobRole,
                            "job_role",
                            names["Job Role"],
                            company,
                            job_position_id=position,
                        )
                if work and info is not None:
                    EmployeeWorkInformation.objects.entire().filter(pk=info.pk).update(
                        **work
                    )

                if apply.get("structure"):
                    put_on_contract(
                        emp, SalaryStructure.objects.entire().get(pk=apply["structure"])
                    )
                elif apply.get("structure_new"):
                    title, company_name = apply["structure_new"]
                    put_on_contract(
                        emp,
                        get_or_create_structure(title, company_name, made_structures),
                    )

                if apply["bank"]:
                    if apply["bank_new"]:
                        EmployeeBankDetails.objects.create(
                            employee_id=emp, **apply["bank"]
                        )
                        banks += 1
                    else:
                        EmployeeBankDetails.objects.entire().filter(
                            employee_id=emp
                        ).update(**apply["bank"])
                if apply.get("additional"):
                    pending.append((emp, apply["additional"]))
                updated += 1
            additional_written = (
                additional.importing().write_values(pending) if pending else 0
            )
        return {
            "updated": updated,
            "banks": banks,
            "additional_values": additional_written,
            "salary_structures": SalaryStructure.objects.entire().count()
            - structures_before,
        }


def ctx_company_differs(sheet_company, current):
    return bool(current) and sheet_company != current
