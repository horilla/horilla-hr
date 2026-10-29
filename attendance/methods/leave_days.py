"""
Which days of an approved leave count as leave, and which stay a holiday or a week off.

A leave type can exclude holidays and the company's week-off days ("Exclude Holidays" and "Exclude
Company Holidays" on the leave type). A leave that spans such a day then does not take it as leave:
it stays what it was. A leave type that does not exclude them takes those days as leave too.

The week-off days are the employee's own: their roster for the period it was assigned, the
company's week-off days outside it (see ``employee_week_off_dates``).
"""

from base.methods import get_company_leave_dates, get_holiday_dates


def employee_week_off_dates(roster_rows, company_dates, start, end):
    """
    The week-off dates in ``start``..``end`` for one employee.

    A roster rules the period it was assigned for, from its first entry's date to its last: inside
    it only the days it marks off are week-offs, and the company's week-off days are not
    consulted. Outside that period (before it starts, after it ends) the company's apply, as for
    an employee with no roster at all.

    ``roster_rows``: ``(date, is_off)`` pairs inside the range; ``company_dates``: the company's
    week-off days.
    """
    company = {d for d in company_dates if start <= d <= end}
    rows = [(d, off) for d, off in roster_rows if start <= d <= end]
    if not rows:
        return company
    first = min(d for d, _off in rows)
    last = max(d for d, _off in rows)
    rostered_off = {d for d, off in rows if off}
    return rostered_off | {d for d in company if not first <= d <= last}


def company_week_off_dates(start, end):
    """The company's week-off days between two dates."""
    raw = set(get_company_leave_dates(start.year)) | set(
        get_company_leave_dates(end.year)
    )
    return {d for d in raw if start <= d <= end}


def exclusion_sets(employee, start, end):
    """``(holidays, week_offs)`` for one employee between two dates: what a leave may exclude."""
    from base.models import Roster

    holidays = {d for d in get_holiday_dates(start, end, employee) if start <= d <= end}
    rows = [
        (r["date"], r["is_off"])
        for r in Roster.objects.filter(
            employee_id=employee, date__range=(start, end)
        ).values("date", "is_off")
    ]
    return holidays, employee_week_off_dates(
        rows, company_week_off_dates(start, end), start, end
    )


def excluded_dates(leave_type, holidays, week_offs):
    """The dates a leave of this type does not take as leave."""
    skip = set()
    if getattr(leave_type, "exclude_holiday", "no") == "yes":
        skip |= set(holidays)
    if getattr(leave_type, "exclude_company_leave", "no") == "yes":
        skip |= set(week_offs)
    return skip


def leave_counted_dates(leave):
    """The dates of one leave request that count as leave: its span less what its type excludes."""
    start = leave.start_date
    end = leave.end_date or start
    holidays, week_offs = exclusion_sets(leave.employee_id, start, end)
    skip = excluded_dates(leave.leave_type_id, holidays, week_offs)
    return [d for d in leave.requested_dates() if d not in skip]
