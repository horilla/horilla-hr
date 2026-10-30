"""
Which contracts an employee was on during a pay period, and the days each one covers.

Payroll used to read the one contract whose status is "active" and pay the whole period on it. A
contract that ended mid-period was already expired by payslip time, so its days were never paid, and
a replacement contract was paid only from its own start date. Here the period is cut by contract
instead: each contract is paid for the days it was in force, at its own wage and structure.

A contract is in force from its start date to its end date (open-ended when it has none). When two
overlap, the later one takes over on its start date. Days no contract covers are not paid.
"""

import contextvars
from contextlib import contextmanager
from datetime import timedelta

from django.db.models import Q

# Expired ones count: an ended contract still has days to be paid in its last period.
PAYABLE_STATUSES = ("active", "expired")

_forced = contextvars.ContextVar("payroll_forced_contract", default=None)


@contextmanager
def use_contract(contract):
    """Make payroll calculations for this contract's employee read ``contract`` instead of the active one."""
    token = _forced.set(contract)
    try:
        yield contract
    finally:
        _forced.reset(token)


def forced_contract(employee):
    """The contract a calculation was told to use for ``employee``, or None."""
    contract = _forced.get()
    if contract is None:
        return None
    return contract if contract.employee_id_id == getattr(employee, "pk", employee) else None


def contracts_in_period(employee, start, end):
    """``[(contract, first_day, last_day)]``: the contracts in force from ``start`` to ``end``, in date order."""
    from payroll.models.models import Contract

    candidates = list(
        Contract.objects.filter(
            employee_id=employee, contract_status__in=PAYABLE_STATUSES, contract_start_date__lte=end
        )
        .filter(Q(contract_end_date__isnull=True) | Q(contract_end_date__gte=start))
        .order_by("contract_start_date", "pk")
    )
    # An expired contract with no end date has no days to pay: it is not known when it stopped.
    candidates = [c for c in candidates if c.contract_status == "active" or c.contract_end_date]

    slices = []
    for index, contract in enumerate(candidates):
        first = max(contract.contract_start_date, start)
        last = min(contract.contract_end_date or end, end)
        later = [c.contract_start_date for c in candidates[index + 1:] if c.contract_start_date <= last]
        if later:
            last = min(later) - timedelta(days=1)
        if first <= last:
            slices.append((contract, first, last))
    return slices
