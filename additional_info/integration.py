"""
What the employee create and edit pages need from additional info.

The employee views import this only when the app is installed, so the employee app does not depend on it.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from additional_info import services
from additional_info.cbv.section import _initial, can_edit
from additional_info.forms import build_values_form
from additional_info.models import (
    DATE,
    DROPDOWN,
    FILE,
    LONG_TEXT,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
)

# Prefix of a field's key in the employee Advanced filter, so it cannot clash with the built-in ones.
FILTER_PREFIX = "addinfo_"

# Prefix of a field's value in the employee export's column list, so it cannot clash with a built-in column.
EXPORT_PREFIX = "addinfo_export_"

# The Advanced filter's type for each field type; a file cannot be filtered on.
_FILTER_TYPE = {
    TEXT: "text",
    LONG_TEXT: "text",
    NUMBER: "number",
    DATE: "date_range",
    DROPDOWN: "choice",
    YES_NO: "choice",
}


def has_step(request, employee=None):
    """True when the pages should show an Additional Information step: a field exists and the user may edit it."""
    if not services.active_fields():
        return False
    return employee is None or can_edit(request, employee)


def edit_form(request, employee):
    """The values form for the edit page's Additional Information step, or None when there is no step."""
    if not has_step(request, employee):
        return None
    fields = services.active_fields()
    return build_values_form(fields)(initial=_initial(employee, fields))


def save_form(request, employee):
    """
    Handle the step's submit: returns ``(form, saved)``.

    The form is bound, so its errors show on the page; ``form`` is None when there is nothing to save.
    """
    if not has_step(request, employee):
        return None, False
    fields = services.active_fields()
    form = build_values_form(fields)(
        request.POST, request.FILES, initial=_initial(employee, fields)
    )
    if not form.is_valid():
        return form, False
    try:
        services.set_values(employee, fields, form.cleaned_data)
    except ValidationError as error:
        form.add_error(None, "; ".join(error.messages))
        return form, False
    return form, True


def filter_fields():
    """The employee Advanced filter's entries for the active fields, one each, in field order."""
    entries = []
    for field in services.active_fields():
        kind = _FILTER_TYPE.get(field.field_type)
        if kind is None:
            continue
        entry = {
            "key": FILTER_PREFIX + field.key,
            "additional_info": field.key,
            "label": field.label,
            "type": kind,
        }
        if field.field_type == DROPDOWN:
            entry["choices"] = [
                [o.get("key"), o.get("label", o.get("key"))]
                for o in field.choices or []
            ]
        elif field.field_type == YES_NO:
            entry["choices"] = [["true", str(_("Yes"))], ["false", str(_("No"))]]
        entries.append(entry)
    return entries


def apply_filter(queryset, key, lookup, value):
    """
    ``queryset`` narrowed to the employees whose additional field ``key`` matches; unchanged when the
    field is gone or the value cannot be read for its type, so a stale or hand-typed row filters nothing.
    """
    field = AdditionalInfoField.objects.filter(key=key, is_active=True).first()
    if field is None or field.field_type == FILE:
        return queryset
    try:
        if field.field_type == NUMBER:
            value = Decimal(value)
        elif field.field_type == YES_NO:
            value = value == "true"
        return services.filter_employees(queryset, key, lookup, value)
    except (InvalidOperation, ValueError, ValidationError):
        return queryset


def export_fields():
    """``{column value: field}`` for the active fields, in order: the extra columns of the employee export."""
    return {EXPORT_PREFIX + field.key: field for field in services.active_fields()}


def export_cells(employee_ids, fields, request=None):
    """
    ``{employee id: {column value: text}}`` for the columns in ``fields`` (from ``export_fields``), read in
    one query however many employees there are; an employee with nothing filled in has no entry.

    A file field is the complete media URL (with the host), so it opens from the exported sheet; without
    a ``request`` to take the host from, it is the file's name.
    """

    def cell(field, value):
        if field.field_type == FILE and value and request is not None:
            return request.build_absolute_uri(value.url)
        return services.display_value(field, value)

    values = services.values_for(employee_ids, list(fields.values()))
    return {
        employee_id: {
            column: cell(field, filled.get(field.key))
            for column, field in fields.items()
        }
        for employee_id, filled in values.items()
    }
