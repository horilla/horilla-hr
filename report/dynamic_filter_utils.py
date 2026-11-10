"""
Shared helpers for the dynamic Filters panel used across every report
(employee, asset, attendance, leave, payroll, pms, recruitment). Each
report's `_apply_dynamic_filter_row` duplicates its own field-path maps and
operator dispatch (they're independent, model-specific catalogs), but the
date-relative-range math is identical everywhere, so it lives here once.
"""

import datetime
import json

from dateutil.relativedelta import relativedelta

from horilla.week import week_start

# Operators that resolve to a self-contained date range computed from
# "today" -- unlike "between"/"equals"/etc., these take no user-supplied
# value at all.
RELATIVE_DATE_OPERATORS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_year",
    "last_year",
)


def resolve_relative_date_range(operator):
    """
    Returns an inclusive (start_date, end_date) tuple for a relative-date
    operator (e.g. "this_week"), or None if `operator` isn't one of
    RELATIVE_DATE_OPERATORS.
    """
    today = datetime.date.today()

    if operator == "today":
        return today, today
    if operator == "yesterday":
        yesterday = today - datetime.timedelta(days=1)
        return yesterday, yesterday
    if operator == "this_week":
        start = week_start(today)
        end = start + datetime.timedelta(days=6)
        return start, end
    if operator == "last_week":
        start = week_start(today) - datetime.timedelta(days=7)
        end = start + datetime.timedelta(days=6)
        return start, end
    if operator == "this_month":
        start = today.replace(day=1)
        end = (start + relativedelta(months=1)) - datetime.timedelta(days=1)
        return start, end
    if operator == "last_month":
        start = today.replace(day=1) - relativedelta(months=1)
        end = today.replace(day=1) - datetime.timedelta(days=1)
        return start, end
    if operator == "this_year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    if operator == "last_year":
        return (
            today.replace(month=1, day=1, year=today.year - 1),
            today.replace(month=12, day=31, year=today.year - 1),
        )
    return None


def parse_multi_value(value):
    """
    Dropdown-type fields can multi-select their value (e.g. "Department is
    one of Sales, Marketing"), sent from the Filters panel as a JSON-encoded
    array string. Returns that list; falls back to a single-item list for a
    plain (non-JSON-array) string, so callers can treat both the same way
    regardless of whether one or several values were picked.
    """
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return [value]
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return [value]
