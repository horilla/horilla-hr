"""
Additional info columns for the master employee import.

Every active field becomes a column a sheet can fill (a file upload cannot come from a sheet, so those are left
out). The text of a cell is checked and turned into the field's own type here; the import dataset only asks for the
columns, a check of a row, and for the values to be written.
"""

import re
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from additional_info.models import (
    COLUMN,
    DATE,
    DROPDOWN,
    FILE,
    LONG_TEXT,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
    AdditionalInfoValue,
)
from horilla.models import has_xss

TEXT_MAX = 255
NUMBER_DIGITS = 20
NUMBER_PLACES = 6
YES = {"yes", "y", "true", "t", "1"}
NO = {"no", "n", "false", "f", "0"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
SAMPLES = {
    TEXT: "Sample text",
    LONG_TEXT: "A longer note",
    NUMBER: "1",
    DATE: "2025-01-31",
    YES_NO: "Yes",
}
SUFFIX = " (Additional Info)"


@dataclass
class ImportColumn:
    """One additional info field as a sheet column."""

    key: str  # the column header, and the key the import rows carry
    field: AdditionalInfoField
    kind: str  # how the review page edits it
    options: list = dataclass_field(
        default_factory=list
    )  # a dropdown's labels, or Yes and No
    sample: str = ""
    aliases: tuple = ()


def _normal(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def build_columns(taken=()):
    """
    The columns for the active fields, in their order.

    ``taken`` holds the names the import already uses; a field with one of those names is called
    "<label> (Additional Info)" so the two never share a column.
    """
    used = {_normal(name) for name in taken}
    columns = []
    for field in AdditionalInfoField.objects.filter(is_active=True):
        if field.field_type == FILE:
            continue
        key = field.label
        if _normal(key) in used:
            key = f"{field.label}{SUFFIX}"
        used.add(_normal(key))
        options = (
            [o["label"] for o in field.choices or []]
            if field.field_type == DROPDOWN
            else []
        )
        if field.field_type == YES_NO:
            options = ["Yes", "No"]
        columns.append(
            ImportColumn(
                key=key,
                field=field,
                kind=(
                    "suggest"
                    if options
                    else {NUMBER: "number", DATE: "date"}.get(field.field_type, "text")
                ),
                options=options,
                sample=(options[0] if options else SAMPLES.get(field.field_type, "")),
                aliases=(field.key.replace("_", " "),),
            )
        )
    return columns


_cache = {"at": 0.0, "taken": None, "columns": []}


def columns(taken=()):
    """``build_columns`` kept for a couple of seconds, since one request asks for the columns many times."""
    names = tuple(sorted(taken))
    if _cache["taken"] != names or time.monotonic() - _cache["at"] > 2:
        _cache.update(at=time.monotonic(), taken=names, columns=build_columns(names))
    return _cache["columns"]


def forget():
    """Drop the kept columns, after a field changed."""
    _cache["at"] = 0.0


# ------------------------------------------------------------------ one cell
def parse(field, raw):
    """``(value, error)``: a cell's text as the field's own type. A blank cell is ``(None, None)``."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None, None
    kind = field.field_type
    if kind in (TEXT, LONG_TEXT):
        if kind == TEXT and len(text) > TEXT_MAX:
            return None, f"is {len(text)} characters; the most allowed is {TEXT_MAX}."
        if has_xss(text):
            return None, "contains characters that are not allowed."
        return text, None
    if kind == NUMBER:
        try:
            number = Decimal(text.replace(",", "").replace(" ", ""))
        except InvalidOperation:
            return None, "is not a number."
        if not number.is_finite():
            return None, "is not a number."
        try:
            number = number.quantize(Decimal(1).scaleb(-NUMBER_PLACES))
        except InvalidOperation:  # more digits than a number can hold
            return None, "is too large."
        if len(number.as_tuple().digits) > NUMBER_DIGITS:
            return None, "is too large."
        return number, None
    if kind == DATE:
        if re.match(
            r"^\d{4}-\d{2}-\d{2}[ T]", text
        ):  # a date cell read as text carries a midnight time
            text = text[:10]
        for pattern in DATE_FORMATS:
            try:
                return datetime.strptime(text, pattern).date(), None
            except ValueError:
                continue
        return None, "is not a valid date. Expected formats: YYYY-MM-DD, DD/MM/YYYY."
    if kind == YES_NO:
        word = text.lower()
        if word in YES:
            return True, None
        if word in NO:
            return False, None
        return None, "must be Yes or No."
    if kind == DROPDOWN:
        wanted = text.lower()
        for option in field.choices or []:
            if wanted in (option["label"].lower(), option["key"].lower()):
                return option["key"], None
        labels = [o["label"] for o in field.choices or []]
        shown = ", ".join(labels[:8]) + (", ..." if len(labels) > 8 else "")
        return None, f"is not one of: {shown}."
    return None, "cannot be imported."


def values_from_row(row, cols):
    """``({field id: value}, {"<column> Error": message})`` for the additional columns of one sheet row."""
    values, problems = {}, {}
    for col in cols:
        value, error = parse(col.field, row.get(col.key))
        if error:
            problems[f"{col.key} Error"] = f"{col.key} {error}"
        elif value is not None:
            values[col.field.pk] = value
    return values, problems


def show(field, value):
    """A value as people read it, for the list of changes."""
    if value in (None, ""):
        return "-"
    if field.field_type == YES_NO:
        return "Yes" if value else "No"
    if field.field_type == DROPDOWN:
        return next(
            (o["label"] for o in field.choices or [] if o["key"] == value), str(value)
        )
    if field.field_type == NUMBER:
        return format(Decimal(value).normalize(), "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)


# --------------------------------------------------------------- the database
def current_values(employee_ids, cols):
    """``{employee id: {field id: value}}`` for those columns (of those employees, or of everyone when ``None``)."""
    by_pk = {c.field.pk: c.field for c in cols}
    found = {}
    rows = AdditionalInfoValue.objects.filter(field__in=list(by_pk))
    if employee_ids is not None:
        rows = rows.filter(employee_id__in=list(employee_ids))
    for row in rows:
        field = by_pk[row.field_id]
        found.setdefault(row.employee_id_id, {})[row.field_id] = getattr(
            row, COLUMN[field.field_type]
        )
    return found


def changes_for(current, values, cols):
    """``[(field id, old, new)]`` for the values that differ from what an employee has. Blank cells never appear."""
    fields = {c.field.pk: c.field for c in cols}
    return [
        (pk, current.get(pk), new)
        for pk, new in values.items()
        if pk in fields and current.get(pk) != new
    ]


def write_values(items):
    """
    Save values: ``[(employee, {field id: value})]``. A row that exists is updated, otherwise one is added.

    Done in a few queries however many people there are. Returns how many values were written.
    """
    items = [(employee, values) for employee, values in items if values]
    if not items:
        return 0
    fields = {
        f.pk: f
        for f in AdditionalInfoField.objects.filter(
            pk__in={pk for _e, v in items for pk in v}
        )
    }
    existing = {
        (row.employee_id_id, row.field_id): row
        for row in AdditionalInfoValue.objects.filter(
            employee_id__in=[e.pk for e, _v in items], field__in=list(fields)
        )
    }
    created, changed, written = [], {}, 0
    for employee, values in items:
        for pk, value in values.items():
            field = fields.get(pk)
            if field is None:
                continue
            column = COLUMN[field.field_type]
            row = existing.get((employee.pk, pk))
            if row is None:
                row = AdditionalInfoValue(employee_id=employee, field=field)
                setattr(row, column, value)
                created.append(row)
            else:
                setattr(row, column, value)
                changed.setdefault(column, []).append(row)
            written += 1
    AdditionalInfoValue.objects.bulk_create(created)
    for column, rows in changed.items():
        AdditionalInfoValue.objects.bulk_update(rows, [column])
    return written
