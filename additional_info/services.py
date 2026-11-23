"""
Reading, writing and querying additional info, in bulk.

Everything that needs the values of many employees (a list column, an export, a filter) goes through here, so
it costs one query however many employees there are.
"""

from decimal import Decimal

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils.translation import gettext as _

from additional_info.models import (
    COLUMN,
    DATE,
    DROPDOWN,
    FILE,
    NUMBER,
    YES_NO,
    AdditionalInfoField,
    AdditionalInfoValue,
)

# The lookups a filter may use for each column.
LOOKUPS = {
    "value_text": {"exact", "iexact", "icontains", "istartswith", "in"},
    "value_number": {"exact", "gt", "gte", "lt", "lte"},
    "value_date": {"exact", "gt", "gte", "lt", "lte"},
    "value_bool": {"exact"},
}


def active_fields():
    """The fields shown on every employee, in order."""
    return list(AdditionalInfoField.objects.filter(is_active=True))


def python_value(field, row):
    """The value in a row as the type the field is: text, Decimal, date, bool or a file."""
    value = getattr(row, field.column)
    if field.field_type == FILE:
        return value if value else None
    return value


def values_for(employee_ids, fields=None):
    """
    ``{employee_id: {field_key: value}}`` for these employees, in a single query.

    Only the fields given (default: every active field) are read, and only filled values appear.
    """
    fields = active_fields() if fields is None else list(fields)
    by_id = {field.pk: field for field in fields}
    result = {}
    if not by_id:
        return result
    rows = AdditionalInfoValue.objects.filter(
        employee_id__in=list(employee_ids), field_id__in=list(by_id)
    )
    for row in rows:
        field = by_id[row.field_id]
        value = python_value(field, row)
        if value is not None and value != "":
            result.setdefault(row.employee_id_id, {})[field.key] = value
    return result


def display_value(field, value):
    """A value as text for people: dropdown label, Yes or No, a trimmed number, the file name."""
    if value is None or value == "":
        return ""
    if field.field_type == DROPDOWN:
        return field.option_label(value)
    if field.field_type == YES_NO:
        return _("Yes") if value else _("No")
    if field.field_type == NUMBER:
        return format(Decimal(value).normalize(), "f")
    if field.field_type == DATE:
        return value.isoformat()
    if field.field_type == FILE:
        return value.name.rsplit("/", 1)[-1]
    return str(value)


def rows_for(employee):
    """What the employee's tab shows: one dict per active field, filled or not."""
    fields = active_fields()
    values = values_for([employee.pk], fields).get(employee.pk, {})
    rows = []
    for field in fields:
        value = values.get(field.key)
        rows.append(
            {
                "field": field,
                "value": value,
                "display": display_value(field, value),
                "is_file": field.field_type == FILE and value is not None,
            }
        )
    return rows


def initial_for(employee, fields):
    """The values to prefill the edit form with, by field key."""
    return {
        key: value
        for key, value in values_for([employee.pk], fields).get(employee.pk, {}).items()
    }


@transaction.atomic
def set_values(employee, fields, cleaned_data):
    """
    Save the submitted values of ``fields`` for one employee.

    An empty value removes the row, so absent keeps meaning empty. For a file field a new upload replaces the
    old file, ``False`` (the clear box) removes it, and anything else leaves it as it is.
    """
    existing = {
        row.field_id: row
        for row in AdditionalInfoValue.objects.filter(
            employee_id=employee, field__in=fields
        )
    }
    for field in fields:
        value = cleaned_data.get(field.key)
        row = existing.get(field.pk)
        column = COLUMN[field.field_type]
        if field.field_type == FILE:
            if isinstance(value, UploadedFile):
                row = row or AdditionalInfoValue(employee_id=employee, field=field)
                if row.value_file:
                    row.value_file.delete(save=False)
                row.value_file = value
                row.save()
            elif value is False and row is not None:
                if row.value_file:
                    row.value_file.delete(save=False)
                row.delete()
            continue
        # A Yes / No field has three states: Yes, No, and not answered (None).
        empty = value is None or value == ""
        if empty:
            if row is not None:
                row.delete()
            continue
        row = row or AdditionalInfoValue(employee_id=employee, field=field)
        setattr(row, column, value)
        row.save()


def filter_employees(queryset, key, lookup, value):
    """
    The employees (from ``queryset``) whose value for the field ``key`` matches, using the column that suits its type.

    Raises ``ValueError`` for an unknown field or a lookup the type does not support.
    """
    field = AdditionalInfoField.objects.filter(key=key).first()
    if field is None:
        raise ValueError(f"Unknown field: {key}")
    if lookup not in LOOKUPS.get(field.column, set()):
        raise ValueError(
            f"{lookup} is not supported for {field.get_field_type_display()}"
        )
    matching = AdditionalInfoValue.objects.filter(
        field=field, **{f"{field.column}__{lookup}": value}
    )
    return queryset.filter(pk__in=matching.values("employee_id"))


def export_columns():
    """``[(key, label)]`` of the active fields, the extra columns of an export or a list."""
    return [(field.key, field.label) for field in active_fields()]


def export_row(values, fields=None):
    """The display text of each active field for one employee, in column order, from ``values_for``."""
    fields = active_fields() if fields is None else fields
    return [display_value(field, values.get(field.key)) for field in fields]
