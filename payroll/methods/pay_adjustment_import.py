"""
Importing arrears and recovery entries from a sheet.

Three steps, so nothing is written until it has been looked at: read the sheet, check every row
(this module; it writes nothing), then create the rows that passed, as Drafts, only when the user
confirms. A row that fails says why and is left out; it never stops the others.
"""

import datetime
import math

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from payroll.models.models import PayAdjustment

# The sheet's columns, as the template has them.
HEADERS = [
    "Badge ID",
    "Type",
    "Title",
    "Amount",
    "Pay Date",
    "Taxable / Pre-Tax",
    "Reason",
]
MAX_ROWS = 2000

# What each column may be called in a sheet somebody built by hand, keyed by what it means.
ALIASES = {
    "badge_id": ("badge id", "badge", "employee badge id", "badge_id"),
    "kind": ("type",),
    "title": ("title",),
    "amount": ("amount",),
    "pay_date": ("pay date", "date", "pay_date"),
    "tax": (
        "taxable / pre-tax",
        "taxable/pre-tax",
        "taxable",
        "pre-tax",
        "pre tax",
        "pretax",
    ),
    "reason": ("reason",),
}
REQUIRED = ("badge_id", "kind", "title", "amount", "pay_date")
LABELS = {
    "badge_id": "Badge ID",
    "kind": "Type",
    "title": "Title",
    "amount": "Amount",
    "pay_date": "Pay Date",
    "tax": "Taxable / Pre-Tax",
    "reason": "Reason",
}
YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}


class SheetProblem(Exception):
    """The file as a whole cannot be used (not a sheet, empty, columns missing, too long)."""


def _blank(value):
    return (
        value is None
        or (isinstance(value, float) and math.isnan(value))
        or (isinstance(value, str) and not value.strip())
        or value is pd.NaT
    )


def _text(value):
    if _blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_sheet(file):
    """The uploaded file as a table of values, or a SheetProblem saying why not."""
    name = (getattr(file, "name", "") or "").lower()
    try:
        if name.endswith(".csv"):
            frame = pd.read_csv(file, dtype=object)
        elif name.endswith((".xlsx", ".xls")):
            frame = pd.read_excel(file, dtype=object)
        else:
            raise SheetProblem(_("Upload An Excel (.xlsx) Or CSV File."))
    except SheetProblem:
        raise
    except Exception:
        raise SheetProblem(_("That File Could Not Be Read As A Sheet."))
    if frame.empty:
        raise SheetProblem(_("The Sheet Has No Rows."))
    if len(frame) > MAX_ROWS:
        raise SheetProblem(
            _("The Sheet Has %(count)s Rows; Import At Most %(max)s At A Time.")
            % {"count": len(frame), "max": MAX_ROWS}
        )
    return frame


def _columns(frame):
    """``{meaning: column name in the sheet}``, or a SheetProblem naming the columns that are missing."""
    found = {}
    for column in frame.columns:
        key = " ".join(str(column).strip().lower().split())
        for meaning, names in ALIASES.items():
            if key in names and meaning not in found:
                found[meaning] = column
    missing = [LABELS[meaning] for meaning in REQUIRED if meaning not in found]
    if missing:
        raise SheetProblem(
            _("The Sheet Is Missing These Columns: %(columns)s.")
            % {"columns": ", ".join(missing)}
        )
    return found


def _date(value):
    if isinstance(value, (pd.Timestamp, datetime.datetime)):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = _text(value)
    try:
        return (
            datetime.date.fromisoformat(text[:10])
            if len(text) >= 10
            else datetime.date.fromisoformat(text)
        )
    except ValueError:
        return None


def check_sheet(frame):
    """
    Check every row, writing nothing.

    Returns ``(rows, table)``: ``rows`` are the ones that passed, ready to create; ``table`` is every
    row as the preview shows it, in order, each with the problems found (none for a good one).
    """
    columns = _columns(frame)
    rows, table = [], []
    seen = set()
    employees = {}

    for index, record in frame.iterrows():
        cells = {meaning: record.get(column) for meaning, column in columns.items()}
        if all(_blank(value) for value in cells.values()):
            continue
        number = int(index) + 2  # the sheet's own row number: the header is row 1
        problems = []

        badge = _text(cells["badge_id"])
        employee = None
        if not badge:
            problems.append(_("Badge ID Is Missing."))
        else:
            if badge not in employees:
                employees[badge] = list(Employee.objects.filter(badge_id=badge))
            matches = employees[badge]
            if not matches:
                problems.append(_("No Employee Has This Badge ID."))
            elif len(matches) > 1:
                problems.append(_("More Than One Employee Has This Badge ID."))
            elif not matches[0].is_active:
                problems.append(_("This Employee Is Not Active."))
            else:
                employee = matches[0]

        kind_text = _text(cells["kind"]).lower()
        kind = {"arrears": "arrears", "arrear": "arrears", "recovery": "recovery"}.get(
            kind_text
        )
        if not kind:
            problems.append(_("Type Must Be Arrears Or Recovery."))

        title = _text(cells["title"])
        if not title:
            problems.append(_("Title Is Missing."))
        elif len(title) > 100:
            problems.append(_("Title Is Longer Than 100 Characters."))

        amount = None
        if _blank(cells["amount"]):
            problems.append(_("Amount Is Missing."))
        else:
            try:
                amount = round(float(str(cells["amount"]).replace(",", "").strip()), 2)
                if not math.isfinite(amount) or amount <= 0:
                    raise ValueError
            except ValueError:
                amount = None
                problems.append(_("Amount Must Be A Number More Than Zero."))

        pay_date = None
        if _blank(cells["pay_date"]):
            problems.append(_("Pay Date Is Missing."))
        else:
            pay_date = _date(cells["pay_date"])
            if pay_date is None:
                problems.append(_("Pay Date Must Be A Date, As YYYY-MM-DD."))

        tax = None
        tax_text = _text(cells.get("tax")).lower()
        if tax_text in YES:
            tax = True
        elif tax_text in NO:
            tax = False
        elif tax_text:
            problems.append(_("Taxable / Pre-Tax Must Be Yes, No Or Empty."))

        if (
            employee
            and pay_date
            and PayAdjustment._month_has_payslip(employee, pay_date)
        ):
            problems.append(
                _("A Payslip Already Exists For %(month)s, So It Cannot Take This.")
                % {"month": pay_date.strftime("%B %Y")}
            )

        if employee and kind and title and amount is not None and pay_date:
            key = (employee.pk, kind, title.lower(), amount, pay_date)
            if key in seen:
                problems.append(_("This Row Is Repeated Earlier In The Sheet."))
            elif PayAdjustment.objects.filter(
                employee_id=employee,
                kind=kind,
                title=title,
                amount=amount,
                pay_date=pay_date,
            ).exists():
                problems.append(_("This Entry Already Exists."))
            seen.add(key)

        shown = {
            "row": number,
            "employee": employee.get_full_name() if employee else badge,
            "badge": badge,
            "kind": kind or _text(cells["kind"]),
            # Plain strings throughout: this row is kept in the session, which holds only JSON.
            "kind_label": str(
                {"arrears": _("Arrears"), "recovery": _("Recovery")}.get(
                    kind, _text(cells["kind"])
                )
            ),
            "title": title,
            "amount": amount if amount is not None else _text(cells["amount"]),
            "pay_date": str(pay_date) if pay_date else _text(cells["pay_date"]),
            "tax": str({True: _("Yes"), False: _("No")}.get(tax, "—")),
            "reason": _text(cells.get("reason")),
            "errors": [str(problem) for problem in problems],
        }
        table.append(shown)
        if not problems:
            rows.append(
                {
                    "row": number,
                    "employee_pk": employee.pk,
                    "kind": kind,
                    "title": title,
                    "amount": amount,
                    "pay_date": str(pay_date),
                    "tax": tax,
                    "reason": _text(cells.get("reason")),
                }
            )
    return rows, table


def create_entries(rows):
    """
    Create the checked rows as Drafts, in one transaction: ``(created, skipped)``.

    Each is checked once more as it is made, since a payslip may have been generated or the same entry
    added since the preview; one that no longer passes is skipped and named, and the rest are made.
    """
    created, skipped = 0, []
    with transaction.atomic():
        for row in rows:
            employee = Employee.objects.filter(
                pk=row["employee_pk"], is_active=True
            ).first()
            if employee is None:
                skipped.append((row["row"], str(_("This Employee Is Not Active."))))
                continue
            entry = PayAdjustment(
                employee_id=employee,
                kind=row["kind"],
                title=row["title"],
                amount=row["amount"],
                pay_date=datetime.date.fromisoformat(row["pay_date"]),
                tax_treatment=row["tax"],
                reason=row["reason"],
            )
            try:
                entry.clean()
            except ValidationError as error:
                skipped.append((row["row"], " ".join(error.messages)))
                continue
            if PayAdjustment.objects.filter(
                employee_id=employee,
                kind=entry.kind,
                title=entry.title,
                amount=entry.amount,
                pay_date=entry.pay_date,
            ).exists():
                skipped.append((row["row"], str(_("This Entry Already Exists."))))
                continue
            entry.save()
            created += 1
    return created, skipped
