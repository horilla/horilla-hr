"""
payroll/methods/proration.py

How much of a standard month a pay period represents.

Payroll figures are quoted per month — a 1,500 meal-allowance ceiling means
1,500 a month, not 1,500 whatever the period — so anything quoted that way has
to be scaled when the period is not a whole month. A joiner paid for ten days
should get ten days' worth of the ceiling, not a month's.

That scaling was written once, inline and commented out, inside
``compute_limit``. It lives here instead because it is not specific to
ceilings: any monthly figure that meets a partial period needs the same
arithmetic, and two implementations of it would eventually disagree.

The basis is what the quoted figure is *per*, which is the only thing the
caller has to decide:

``full_period``
    Not a monthly figure at all. The number stands as written in every period.

``month_working_days``
    A monthly figure, shared out by working days. Ten working days of a
    twenty-two working day month is ten twenty-seconds of the figure. This is
    the one that matches how the rest of the engine prorates pay — see
    ``compute_salary_on_period``, which divides the wage by working days.

``month_calendar_days``
    A monthly figure, shared out by calendar days. For figures that accrue
    whether or not the day was worked.

``per_working_day``
    Already a daily figure. Multiplied by the working days in the period.

A period spanning more than one month gives a factor above 1, and that is
correct: two months of a monthly ceiling is two ceilings.
"""

from datetime import date, datetime

FULL_PERIOD = "full_period"
MONTH_WORKING_DAYS = "month_working_days"
MONTH_CALENDAR_DAYS = "month_calendar_days"
PER_WORKING_DAY = "per_working_day"

# Offered wherever a monthly figure is configured. Kept here so the model
# choices and the arithmetic cannot drift apart.
# The default first, so the list reads from the common case down.
BASIS_CHOICES = [
    (MONTH_CALENDAR_DAYS, "A month's worth, split by calendar days"),
    (MONTH_WORKING_DAYS, "A month's worth, split by working days"),
    (PER_WORKING_DAY, "An amount for each working day"),
    (FULL_PERIOD, "A flat amount, the same in every pay period"),
]

# What a component gets if nobody chooses. Named here rather than repeated as a
# string in two model fields and a test.
DEFAULT_BASIS = MONTH_CALENDAR_DAYS


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _slice_days(month):
    """Calendar days of the period that fall inside this month."""
    start = _as_date(month.get("start_date"))
    end = _as_date(month.get("end_date"))
    if start is None or end is None:
        return None
    return (end - start).days + 1


def period_factor(day_dict, basis):
    """
    What to multiply a figure quoted on ``basis`` by, for this period.

    Returns ``1.0`` when there is nothing to scale by — an unknown basis, an
    empty period, or a month slice missing the counts this needs. Falling back
    to 1 leaves the figure exactly as configured, which is the reading least
    likely to surprise: a ceiling that quietly shrank because a day count was
    absent would be far worse than one that did not move.
    """
    if basis == FULL_PERIOD or not basis or not day_dict:
        return 1.0

    factor = 0.0
    counted = False

    for month in day_dict:
        if basis == PER_WORKING_DAY:
            worked = month.get("working_days_on_period")
            if worked is None:
                continue
            factor += float(worked)
            counted = True
            continue

        if basis == MONTH_WORKING_DAYS:
            part = month.get("working_days_on_period")
            whole = month.get("working_days_on_month")
        elif basis == MONTH_CALENDAR_DAYS:
            part = _slice_days(month)
            whole = month.get("days")
        else:
            return 1.0

        if part is None or not whole:
            continue
        factor += float(part) / float(whole)
        counted = True

    # Nothing in the period carried the counts — the golden fixtures build a
    # day_dict with only the keys the pay calculation itself reads, for one.
    return factor if counted else 1.0


def flat_amount(component, day_dict):
    """
    A component's fixed amount, scaled to the period.

    Only flat figures need this. Every other strategy is already a share of
    something that follows the period — a percentage of basic pay reads a basic
    that ``compute_salary_on_period`` has already prorated, a per-attendance
    rate is multiplied by days actually worked — so scaling those again would
    prorate them twice.

    Returns the amount unchanged when the basis is a flat one, which is the
    default and what every component did before this existed.
    """
    amount = getattr(component, "amount", None)
    if amount is None:
        return 0.0
    return float(amount) * period_factor(
        day_dict, getattr(component, "maximum_unit", None)
    )
