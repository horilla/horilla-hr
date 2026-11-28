"""
Forecast of an employee's leave balance on a future date.

A request is first tried against the balance held now. When that falls short, the resets that come before its end
date are tried in order and the first one after which the balance covers it is the cycle it is charged to: only
the resets up to that one are brought forward, so the later ones still happen on their own. Nothing here saves
anything; ``check`` says whether a request fits and which resets approving it brings forward.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime

MAX_RESETS = 400  # stops a stale reset date from looping for years
OK_NOW = "ok_now"  # fits the balance the employee has now
OK_FORECAST = (
    "ok_forecast"  # fits the balance after one of the resets before the end date
)
SHORT = "short"


def as_date(value):
    """A date from a date, datetime or ``YYYY-MM-DD`` text; ``None`` for anything else."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


@dataclass
class Balance:
    """What an employee is expected to hold at some point."""

    available: float
    carryforward: float
    resets: list = field(default_factory=list)  # the resets up to that point
    pending: float = 0.0  # days of other requests still waiting for a decision
    steps: list = field(
        default_factory=list
    )  # each reset or expiry on the way: date, kind, allowance, carryforward

    @property
    def cycle_start(self):
        """The reset that starts the cycle of that point, or ``None`` for the current cycle."""
        return self.resets[-1] if self.resets else None

    @property
    def total(self):
        return round(self.available + self.carryforward - self.pending, 3)


@dataclass
class Check:
    """The outcome of ``check``."""

    kind: str
    needed: float
    balance: Balance
    can_reset_now: bool = False

    @property
    def ok(self):
        return self.kind != SHORT

    @property
    def ahead(self):
        """The leave is charged to a later cycle, so approving it brings the balance forward to that cycle."""
        return self.kind == OK_FORECAST

    @property
    def shortfall(self):
        return round(max(self.needed - self.balance.total, 0), 3)


def reset_dates(available_leave, until):
    """The reset dates of a balance up to ``until``, oldest first. Empty for a leave type that never resets."""
    leave_type = available_leave.leave_type_id
    until = as_date(until)
    current = as_date(available_leave.reset_date)
    if not leave_type.reset or current is None or until is None:
        return []
    found = []
    while current <= until and len(found) < MAX_RESETS:
        found.append(current)
        try:
            following = as_date(
                available_leave.set_reset_date(
                    assigned_date=current, available_leave=available_leave
                )
            )
        except (TypeError, ValueError):  # a leave type missing its reset month or day
            break
        if following is None or following <= current:
            break
        current = following
    return found


def reset_after(available_leave, after):
    """The first reset of a balance later than ``after``, or ``None`` for a leave type that never resets."""
    leave_type = available_leave.leave_type_id
    after = as_date(after)
    found = reset_dates(available_leave, after)
    if found:
        try:
            return as_date(
                available_leave.set_reset_date(
                    assigned_date=found[-1], available_leave=available_leave
                )
            )
        except (TypeError, ValueError):
            return None
    stored = as_date(available_leave.reset_date)
    return stored if leave_type.reset and stored and stored > after else None


def after_reset(leave_type, available, carryforward):
    """The balance right after one reset, the same way ``AvailableLeave.update_carryforward`` makes it."""
    total = max(available + carryforward, 0)
    if leave_type.carryforward_type == "no carryforward":
        carryforward = 0
    else:
        carryforward = leave_type.capped_carryforward(total)
    return float(leave_type.total_days or 0), float(carryforward)


def steps_until(available_leave, until):
    """
    Every reset, and the carryforward expiry if it falls before then, up to ``until`` in the order they happen,
    each with the balance right after it: ``{date, kind, allowance, carryforward}``. A reset comes before an expiry
    on the same day, as the scheduler does it.
    """
    leave_type = available_leave.leave_type_id
    until = as_date(until)
    events = [(day, 0, "reset") for day in reset_dates(available_leave, until)]
    expiry = as_date(available_leave.expired_date)
    if (
        leave_type.reset
        and leave_type.carryforward_type == "carryforward expire"
        and expiry
        and expiry <= until
    ):
        events.append(
            (expiry, 1, "expiry")
        )  # what the scheduler does once the expiry date is reached
    events.sort()
    available = float(available_leave.available_days or 0)
    carryforward = float(available_leave.carryforward_days or 0)
    steps = []
    for day, _order, kind in events:
        if kind == "reset":
            available, carryforward = after_reset(leave_type, available, carryforward)
        else:
            available, carryforward = float(leave_type.total_days or 0), 0.0
        steps.append(
            {
                "date": day,
                "kind": kind,
                "allowance": available,
                "carryforward": carryforward,
            }
        )
    return steps


def _balance_after(available_leave, steps):
    """The ``Balance`` right after the last of ``steps`` (what is held now when there are none)."""
    last = steps[-1] if steps else None
    return Balance(
        available=(
            last["allowance"] if last else float(available_leave.available_days or 0)
        ),
        carryforward=(
            last["carryforward"]
            if last
            else float(available_leave.carryforward_days or 0)
        ),
        resets=[step["date"] for step in steps if step["kind"] == "reset"],
        steps=steps,
    )


def _employee_requests(available_leave, statuses, exclude):
    from leave.models import LeaveRequest

    requests = LeaveRequest._base_manager.filter(
        employee_id=available_leave.employee_id_id,
        leave_type_id=available_leave.leave_type_id_id,
        status__in=statuses,
    )
    if exclude is not None and exclude.pk:
        requests = requests.exclude(pk=exclude.pk)
    return requests


def pending_in_cycle(available_leave, on_date, exclude=None):
    """Days of the other waiting requests of this balance that end in the same cycle as ``on_date``."""
    on_date = as_date(on_date)
    waiting = list(_employee_requests(available_leave, ("requested",), exclude))
    ends = [as_date(r.end_date) or as_date(r.start_date) for r in waiting]
    horizon = max([on_date] + [d for d in ends if d])
    every = reset_dates(available_leave, horizon)
    cycle = bisect_right(every, on_date)
    return round(
        sum(
            r.requested_days or 0
            for r, end in zip(waiting, ends)
            if end and bisect_right(every, end) == cycle
        ),
        3,
    )


def balance_on(available_leave, on_date, exclude=None, include_pending=False):
    """
    The balance on ``on_date``: today's balance carried through each reset up to then and, when asked, less the
    other requests still waiting that end in the same cycle.

    ``exclude`` is a request to leave out (the one being judged).
    """
    on_date = as_date(on_date)
    balance = _balance_after(available_leave, steps_until(available_leave, on_date))
    if include_pending:
        balance.pending = pending_in_cycle(available_leave, on_date, exclude)
    return balance


def candidates(available_leave, end_date, exclude=None, include_pending=False):
    """
    The balance after each reset that comes by ``end_date``, in order. With ``include_pending`` the other waiting
    requests that end in the same cycle as ``end_date`` are taken off each of them: whichever reset the leave is
    charged to, those days are spoken for. Waiting requests in other cycles are not held against it.
    """
    steps = steps_until(available_leave, end_date)
    waiting = (
        pending_in_cycle(available_leave, end_date, exclude) if include_pending else 0.0
    )
    found = []
    for index, step in enumerate(steps):
        if step["kind"] != "reset":
            continue
        balance = _balance_after(available_leave, steps[: index + 1])
        balance.pending = waiting
        found.append(balance)
    return found


def best_balance(available_leave, end_date, exclude=None, include_pending=False):
    """The balance with the most days among what is held now and what each reset before ``end_date`` leaves."""
    options = [
        balance_on(
            available_leave, date.min, exclude=exclude, include_pending=include_pending
        )
    ]
    options += candidates(
        available_leave, end_date, exclude=exclude, include_pending=include_pending
    )
    return max(options, key=lambda balance: balance.total)


def reset_now_covers(available_leave, needed):
    """Whether resetting the balance today would leave enough for ``needed`` days."""
    leave_type = available_leave.leave_type_id
    if not leave_type.reset:
        return False
    available, carryforward = after_reset(
        leave_type,
        float(available_leave.available_days or 0),
        float(available_leave.carryforward_days or 0),
    )
    return round(available + carryforward, 3) + 1e-9 >= needed


def check(available_leave, end_date, needed, exclude=None, include_pending=False):
    """
    Whether ``needed`` days, for a leave ending on ``end_date``, fit.

    The balance held now comes first: a leave it covers is taken from it, however far ahead the dates are. When it
    falls short, the resets before the end date are tried in order and the first one that leaves enough is where
    the days are charged: approving brings the balance forward to that reset and no further. A leave type without
    a limit always fits.
    """
    needed = float(needed or 0)
    if not available_leave.leave_type_id.limit_leave:
        balance = Balance(
            available=float(available_leave.available_days or 0),
            carryforward=float(available_leave.carryforward_days or 0),
        )
        return Check(OK_NOW, needed, balance)
    # What is held now, before any reset (date.min: no reset has come yet).
    now = balance_on(
        available_leave, date.min, exclude=exclude, include_pending=include_pending
    )
    if now.total + 1e-9 >= needed:
        return Check(OK_NOW, needed, now)
    options = candidates(
        available_leave, end_date, exclude=exclude, include_pending=include_pending
    )
    for balance in options:
        if balance.total + 1e-9 >= needed:
            return Check(OK_FORECAST, needed, balance)
    best = max([now] + options, key=lambda balance: balance.total)
    return Check(
        SHORT, needed, best, can_reset_now=reset_now_covers(available_leave, needed)
    )
