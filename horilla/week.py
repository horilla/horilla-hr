"""
Calendar-week helpers driven by settings.HORILLA_FIRST_DAY_OF_WEEK.

Kept free of app imports so filters, dashboards, reports and views can all
share one definition of "this week" without circular imports.
"""

from datetime import timedelta

from django.conf import settings


def first_day_of_week():
    """
    settings.HORILLA_FIRST_DAY_OF_WEEK (0 = Sunday, 1 = Monday ... 6 =
    Saturday). Monday, like the attendance dashboard, when it is unset,
    empty or anything other than 0 to 6.
    """
    value = str(getattr(settings, "HORILLA_FIRST_DAY_OF_WEEK", "")).strip()
    return int(value) if value in ("0", "1", "2", "3", "4", "5", "6") else 1


def week_start(day):
    """First day of the calendar week containing `day` (see first_day_of_week)."""
    return day - timedelta(days=(day.isoweekday() - first_day_of_week()) % 7)
