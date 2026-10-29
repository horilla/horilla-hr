"""
The date range the monthly summary opens on: this month, last month, the company's pay period, or
a month cycle starting on a day the user picks.

Every option spans one full month. A cycle starts on the chosen day and runs for as many days as
that month has (the same rule as the pay period in Payroll Settings), so the dates follow the
calendar and are not fixed. The choice is the user's own, kept in cookies like the last-used view.
"""

import calendar
import datetime

COOKIE = "ms_range"
START_DAY_COOKIE = "ms_range_day"
MONTH, PREVIOUS_MONTH, PAY_PERIOD, CUSTOM = (
    "month",
    "previous_month",
    "pay_period",
    "custom",
)
MODES = (MONTH, PREVIOUS_MONTH, PAY_PERIOD, CUSTOM)
LAST_DAY = 31


def _month(year, month):
    return datetime.date(year, month, 1), datetime.date(
        year, month, calendar.monthrange(year, month)[1]
    )


def user_company(request):
    work_info = getattr(
        getattr(request.user, "employee_get", None), "employee_work_info", None
    )
    return getattr(work_info, "company_id", None)


def parse_start_day(value):
    """A start day, 1 to 31 (31 is the last day of each month), or None."""
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if 1 <= day <= LAST_DAY else None


def _cycle(day, today):
    from payroll.models.payroll_batch import PayPeriodSettings

    return PayPeriodSettings(cycle_start_day=day).period_for(today)


def range_for(mode, today, company=None, start_day=None):
    """``(from, to)`` for a mode on a day. An unknown mode, or a cycle with no start day, is this month."""
    if mode == PREVIOUS_MONTH:
        last = today.replace(day=1) - datetime.timedelta(days=1)
        return _month(last.year, last.month)
    if mode == PAY_PERIOD:
        from payroll.models.payroll_batch import PayPeriodSettings

        return PayPeriodSettings.for_company(company).period_for(today)
    if mode == CUSTOM and start_day:
        return _cycle(start_day, today)
    return _month(today.year, today.month)


def chosen_mode(request):
    mode = request.COOKIES.get(COOKIE)
    return mode if mode in MODES else MONTH


def chosen_start_day(request):
    """The start day the user picked for the cycle option; the 1st until they pick."""
    return parse_start_day(request.COOKIES.get(START_DAY_COOKIE)) or 1


def default_range(request, today=None):
    """The range to open on: the user's choice, this month until they make one."""
    today = today or datetime.date.today()
    return range_for(
        chosen_mode(request), today, user_company(request), chosen_start_day(request)
    )


def rule_text(day):
    """A start day as a rule, not as dates: the dates move with the month."""
    from django.utils.translation import gettext as _

    from payroll.models.payroll_batch import _ordinal

    if day == 1:
        return _("Calendar Month (1st To Last Day)")
    if day == LAST_DAY:
        return _("Cycle Starting On The Last Day Of Each Month")
    return _("Cycle Starting On The %(day)s Of Each Month") % {"day": _ordinal(day)}


def short_month_note(day):
    """What happens in a month too short for the start day (29th to the last day), else empty."""
    from django.utils.translation import gettext as _

    if day == LAST_DAY:
        return _(
            "The Cycle Starts On Whichever Day Ends Each Month: The 28th To The 31st."
        )
    if day > 28:
        return _(
            "A Month With Fewer Than %(day)s Days (February, For Example) Starts On Its Last Day Instead, "
            "And The Cycle Ends The Day Before The Next One Starts."
        ) % {"day": day}
    return ""


def start_day_choices():
    """``(day, label, rule, note)`` for the cycle's start day select."""
    from django.utils.translation import gettext as _

    from payroll.models.payroll_batch import _ordinal

    return [
        (
            day,
            _("Last Day") if day == LAST_DAY else _ordinal(day),
            rule_text(day),
            short_month_note(day),
        )
        for day in range(1, LAST_DAY + 1)
    ]


def choices(request):
    """The options and the rule each follows, for the chooser."""
    from django.utils.translation import gettext as _

    from payroll.models.payroll_batch import PayPeriodSettings

    pay_day = PayPeriodSettings.for_company(user_company(request)).start_day
    return [
        {"key": MONTH, "label": _("This Month"), "text": rule_text(1)},
        {
            "key": PREVIOUS_MONTH,
            "label": _("Previous Month"),
            "text": _("The Whole Of Last Month"),
        },
        {
            "key": PAY_PERIOD,
            "label": _("Pay Period (From Payroll)"),
            "text": rule_text(pay_day),
        },
        {"key": CUSTOM, "label": _("Month Cycle"), "text": ""},
    ]
