"""
payroll/methods/component_catalog.py

The salary components a run can use, read once and matched to each employee in Python.

Working out which allowances and deductions apply to one employee used to take a union of five
queries per kind, repeated for every payslip (and several times inside each). A run of a few hundred
people spent most of its time building and sending those. The components themselves are a few dozen
rows that do not change while a slice is being written, so a slice reads them once -- with the people,
departments, positions, roles and structures each one names -- and answers every employee from memory.

It is an accelerator and nothing else. It is only active inside ``use_catalog()`` (batch generation
turns it on for a slice); everywhere else the original queries run exactly as before, and the
membership rules here are written to be the same rules, which ``verify`` checks against them.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace

_active = ContextVar("component_catalog", default=None)

# The M2M fields that decide who a component applies to, read together with the rows.
_RELATED = (
    "specific_employees",
    "exclude_employees",
    "apply_departments",
    "apply_job_positions",
    "apply_job_roles",
    "salary_structures",
)
_EMPTY = frozenset()


def _links(model, name):
    """``{component pk: {related pks}}`` for one many-to-many field, from its link table."""
    field = model._meta.get_field(name)
    if field.auto_created and not field.concrete:
        # Declared on the other model (a salary structure lists its components): the reverse side.
        through = field.through
        source, target = (
            field.field.m2m_reverse_field_name(),
            field.field.m2m_field_name(),
        )
    else:
        through = field.remote_field.through
        source, target = field.m2m_field_name(), field.m2m_reverse_field_name()
    found = {}
    for component_id, related_id in through._base_manager.values_list(
        f"{source}_id", f"{target}_id"
    ):
        found.setdefault(component_id, set()).add(related_id)
    return found


def active():
    """The catalog of the slice being written, or None outside one."""
    return _active.get()


@contextmanager
def use_catalog():
    """Make a fresh catalog the one in force for the code run inside the block."""
    token = _active.set(Catalog())
    try:
        yield _active.get()
    finally:
        _active.reset(token)


class ComponentList(list):
    """
    Components in evaluation order, with the few queryset methods the payroll code calls on them.

    Not a queryset: nothing here goes back to the database. Only the calls the engine makes exist.
    """

    def exclude(self, **lookups):
        return ComponentList(
            item
            for item in self
            if not all(_value(item, name) == wanted for name, wanted in lookups.items())
        )

    def filter(self, **lookups):
        return ComponentList(
            item
            for item in self
            if all(_value(item, name) == wanted for name, wanted in lookups.items())
        )

    def values_list(self, name, flat=False):
        if not flat:
            raise NotImplementedError("values_list is only offered with flat=True")
        return [_value(item, name) for item in self]

    def exists(self):
        return bool(self)


def _value(item, name):
    return item.pk if name == "pk" else getattr(item, name)


class Catalog:
    """Every Allowance and Deduction of the company in view, with who each one applies to."""

    def __init__(self):
        self._rows = {}

    def rows(self, model):
        """All components of ``model`` the current company filter lets through, loaded once."""
        if model not in self._rows:
            rows = list(model.objects.filter().prefetch_related("apply_conditions"))
            # The who-it-applies-to relations are read straight from their link tables: only ids are
            # needed, and going through the related models' managers costs a company filter each.
            relations = {name: _links(model, name) for name in _RELATED}
            for row in rows:
                row._cat = SimpleNamespace(
                    specific=relations["specific_employees"].get(row.pk, _EMPTY),
                    excluded=relations["exclude_employees"].get(row.pk, _EMPTY),
                    departments=relations["apply_departments"].get(row.pk, _EMPTY),
                    positions=relations["apply_job_positions"].get(row.pk, _EMPTY),
                    roles=relations["apply_job_roles"].get(row.pk, _EMPTY),
                    structures=relations["salary_structures"].get(row.pk, _EMPTY),
                )
            self._rows[model] = rows
        return self._rows[model]

    # -- who the employee is on the day ------------------------------------

    def _structure_id(self, employee, forced):
        """The salary structure the employee is paid on, as component_engine.structure_components finds it."""
        from payroll.models.models import Contract

        if forced is not None:
            return forced.salary_structure_id_id
        cache = employee.__dict__.setdefault("_catalog_structure", {})
        if "id" not in cache:
            contract = (
                Contract.objects.entire()
                .filter(
                    employee_id=employee,
                    contract_status="active",
                    salary_structure_id__isnull=False,
                )
                .order_by("-contract_start_date", "-pk")
                .first()
            )
            cache["id"] = (
                contract.salary_structure_id_id if contract is not None else None
            )
        return cache["id"]

    def _work_info(self, employee):
        from employee.models import EmployeeWorkInformation

        try:
            return employee.employee_work_info
        except EmployeeWorkInformation.DoesNotExist:
            return None

    # -- the questions the engine asks -------------------------------------

    def structure_pks(self, model, employee):
        """Primary keys of the components the employee's structure carries."""
        from payroll.methods.contract_periods import forced_contract

        structure = self._structure_id(employee, forced_contract(employee))
        if structure is None:
            return set()
        return {row.pk for row in self.rows(model) if structure in row._cat.structures}

    def eligible(
        self,
        model,
        employee,
        start_date,
        end_date,
        *,
        conditional=True,
        pretax=None,
        tax=None,
        compensation=False,
    ):
        """
        The components that apply to ``employee`` in the period, ordered by (sequence, pk).

        ``conditional`` is whether condition-based components join the set (the tax pass leaves them
        out); ``pretax`` / ``tax`` restrict deductions to one pass; ``compensation`` keeps only the
        components that adjust basic or gross pay (``False`` leaves those out, as the passes do).
        """
        from payroll.methods.contract_periods import forced_contract

        forced = forced_contract(employee)
        own_structure = forced.salary_structure_id_id if forced is not None else None
        structure = self._structure_id(employee, forced)
        info = self._work_info(employee)
        found = []
        for row in self.rows(model):
            cat = row._cat
            if row.is_system:
                continue
            if pretax is not None and row.is_pretax != pretax:
                continue
            if tax is not None and row.is_tax != tax:
                continue
            if (
                compensation is False
                and getattr(row, "update_compensation", None) is not None
            ):
                continue
            if row.one_time_date is not None and not (
                start_date <= row.one_time_date <= end_date
            ):
                continue
            excluded = employee.pk in cat.excluded
            specific = employee.pk in cat.specific
            if (
                specific
                and own_structure is not None
                and cat.structures
                and own_structure not in cat.structures
            ):
                # Mirrored onto the employee from a structure they are no longer on.
                specific = False
            matched = (
                specific
                or (conditional and row.is_condition_based and not excluded)
                or (row.include_active_employees and not excluded)
                or (not excluded and info is not None and _group_match(row, cat, info))
                or (structure is not None and structure in cat.structures)
            )
            if matched:
                found.append(row)
        found.sort(key=lambda row: (row.sequence, row.pk))
        return ComponentList(found)

    def compensation_heads(self, employee, kind, start_date, end_date):
        """Deductions that adjust basic or gross pay (``update_compensation_deduction``), in order."""
        from payroll.methods.contract_periods import forced_contract
        from payroll.models.models import Deduction

        forced = forced_contract(employee)
        own_structure = forced.salary_structure_id_id if forced is not None else None
        found = []
        for row in self.rows(Deduction):
            cat = row._cat
            if row.update_compensation != kind or employee.pk not in cat.specific:
                continue
            if (
                own_structure is not None
                and cat.structures
                and own_structure not in cat.structures
            ):
                continue
            if row.one_time_date is not None and not (
                start_date <= row.one_time_date <= end_date
            ):
                continue
            found.append(row)
        found.sort(key=lambda row: (row.sequence, row.pk))
        return found


def _group_match(row, cat, info):
    """Targeted at the employee's department, job position or job role (component_engine.group_targeted)."""
    return (
        (
            row.apply_by == "department"
            and info.department_id_id is not None
            and info.department_id_id in cat.departments
        )
        or (
            row.apply_by == "job_position"
            and info.job_position_id_id is not None
            and info.job_position_id_id in cat.positions
        )
        or (
            row.apply_by == "job_role"
            and info.job_role_id_id is not None
            and info.job_role_id_id in cat.roles
        )
    )
