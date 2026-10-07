"""
payroll/methods/component_engine.py

The ordered evaluation pass for salary components.

Two things were missing from the old gatherers, and they are the same thing
twice: a component had no defined position in the run, and no way to see what
an earlier component had computed.

  * Candidates were collected as a three-way queryset union with no order_by,
    so evaluation order was whatever the database returned.
  * Each amount was appended to one list and each component to another, then
    the two were re-paired with zip() at the end — which only holds while both
    lists are appended to in lockstep, and in calculate_post_tax_deduction they
    are not.

This module replaces that with one loop that carries a context dict keyed by
component code, so a later component can be expressed in terms of an earlier
one. The phase structure around it is deliberately unchanged: pretax, post-tax,
tax and net-pay deductions still run in their existing order against their
existing aggregates, because those aggregates are what the legacy semantics are
built on and changing them would move everyone's pay.

Ordering is always ``(sequence, pk)``, written explicitly at every call site
rather than left to Meta.ordering — a ``|`` union of querysets discards it.
"""

from payroll.models.models import RESERVED_COMPONENT_CODES, Allowance

# Seeded into every context so a formula or percentage can refer to the period
# itself, not only to other components.
CONTEXT_PERIOD_KEYS = ("BASIC", "GROSS", "CTC")

# Bookkeeping the engine needs but nobody configures. Lowercase on purpose:
# component codes are validated ^[A-Z][A-Z0-9_]*$, so these cannot be shadowed
# by a component, and they never appear in the formula builder's code list.
EARNED = "_earned"
GROSS_IS_FIXED = "_gross_is_fixed"


def new_context(basic_pay=0.0, total_gross=None):
    """
    Fresh evaluation context. Keys are component codes (uppercase) plus the
    period figures above; values are the amounts computed so far this run.

    What GROSS means depends on which direction the structure runs, and both
    readings are the true one for their mode:

    * Gross-up (``total_gross is None``) — gross is built from the bottom, so
      GROSS is a running total. It starts at basic pay rather than zero because
      gross IS basic plus the earnings on top of it; seeding it empty made
      "0.75% of GROSS" charge 0.75% of the allowances alone. A component
      referring to GROSS sees the figure as at its own position in the order,
      and by the time any deduction phase runs every earning has been added and
      it is the final gross.

    * CTC-Down (``total_gross`` given) — the contract wage IS the gross, and
      the components divide it up. GROSS is therefore known before a single
      component runs and stays fixed, which is what lets a structure say
      "basic is 50% of gross" — inexpressible while gross was only ever
      discovered by adding basic to everything else.

    ``EARNED`` tracks what has actually been paid out so far in either mode.
    That is what the balance component subtracts from CTC, and it has to be
    separate from GROSS precisely because GROSS stops moving in CTC-Down.
    """
    basic = float(basic_pay or 0)
    if total_gross is None:
        return {"BASIC": basic, "GROSS": basic, "CTC": 0.0, EARNED: basic}
    total = float(total_gross or 0)
    return {
        "BASIC": basic,
        "GROSS": total,
        "CTC": total,
        EARNED: basic,
        GROSS_IS_FIXED: True,
    }


def years_between(start, end):
    """Whole and fractional years from ``start`` to ``end``, two decimals; never negative."""
    if not start or not end:
        return 0.0
    days = (end - start).days
    return round(max(days, 0) / 365.25, 2)


def add_service_years(context, employee, contract, as_of):
    """
    Seed YEARS_OF_SERVICE and YEARS_OF_CONTRACT, both measured to the end of the
    pay period.

    * YEARS_OF_SERVICE: from the employee's joining date. Gratuity and similar
      service-based entitlements run on this.
    * YEARS_OF_CONTRACT: from the start of the active contract, for a rule that
      counts only the present term.

    Fractional (6.4, not 6): ``round(YEARS_OF_SERVICE)`` gives a rounded figure
    where a formula wants whole years. An employee with no joining date reads 0.
    """
    joined = None
    work_info = getattr(employee, "employee_work_info", None)
    if work_info is not None:
        joined = work_info.date_joining
    context["YEARS_OF_SERVICE"] = years_between(joined, as_of)
    context["YEARS_OF_CONTRACT"] = years_between(
        getattr(contract, "contract_start_date", None), as_of
    )
    return context


def accumulate(context, amount):
    """
    Add an earning to the running totals.

    GROSS only moves where it is a running total. In CTC-Down it is the pot
    being divided and already holds its final value, so adding to it would take
    it past the wage and make every percentage of gross grow as the pass went
    on.
    """
    value = float(amount or 0)
    context[EARNED] = float(context.get(EARNED, 0.0) or 0) + value
    if not context.get(GROSS_IS_FIXED):
        context["GROSS"] = float(context.get("GROSS", 0.0) or 0) + value
    return context


def eligible_allowances(employee, start_date, end_date):
    """
    The allowances in scope for this employee and period, in evaluation order.

    The membership rules are exactly the legacy ones — targeted directly,
    condition-based, or applied to all active employees, minus anyone excluded,
    minus one-time components dated outside the period. The only addition is
    the ordering.
    """
    specific = Allowance.objects.filter(specific_employees=employee)
    conditional = Allowance.objects.filter(is_condition_based=True).exclude(
        exclude_employees=employee
    )
    active = Allowance.objects.filter(include_active_employees=True).exclude(
        exclude_employees=employee
    )

    allowances = specific | conditional | active
    return (
        allowances.exclude(one_time_date__lt=start_date)
        .exclude(one_time_date__gt=end_date)
        # A system component is a template for the rows a loan or a
        # reimbursement generates, not something anyone is paid. Nothing
        # targets one, so this excludes nothing today -- it is here so that
        # stays true if the targeting rules above ever change.
        .exclude(is_system=True)
        .distinct()
        .order_by("sequence", "pk")
    )


def record(context, component, amount):
    """
    Publish a component's result so later components can reference it.

    Codes are optional: a component nothing refers to does not need one, and
    an unnamed component simply contributes nothing to the context.

    The engine's own aggregates are never overwritten. Codes are derived away
    from those names at save time, but a row predating that — or edited around
    it — would otherwise redefine GROSS partway through the pass, and every
    percentage of gross after it would quietly use the wrong figure.
    """
    code = (getattr(component, "code", "") or "").strip().upper()
    if code and code not in RESERVED_COMPONENT_CODES:
        context[code] = float(amount or 0)

    # An earning marked as basic pay IS basic pay, whatever its code happens to
    # be. Codes are derived from titles, so "Basic Pay" becomes BASIC_PAY and
    # nothing would ever have populated BASIC — which is where payroll_run and
    # every "percentage of BASIC" read it from. The flag is the statement; this
    # is what makes it true in the context.
    if getattr(component, "is_basic_pay", False):
        context["BASIC"] = float(amount or 0)
    return context


def _coerce(actual, raw):
    """
    Parse the configured value into the same shape as the employee's value.

    The old code did ``type(actual)(raw)`` — construct whatever type the
    employee attribute happens to be, from a user-typed string. That is three
    bugs in one expression: ``bool("false")`` is True, so a false condition
    read as true; an unparseable number raised ValueError out of the middle of
    payslip generation rather than failing the condition; and a field that
    resolves to a model instance tried to construct a model.

    Returns ``(parsed_actual, parsed_expected)``, or ``None`` when the
    configured value cannot be read as the field's type — which is a condition
    that does not hold, not a crash.
    """
    raw = "" if raw is None else str(raw).strip()

    if isinstance(actual, bool):
        truthy = {"true", "1", "yes", "y", "on"}
        falsy = {"false", "0", "no", "n", "off"}
        lowered = raw.lower()
        if lowered in truthy:
            return actual, True
        if lowered in falsy:
            return actual, False
        return None

    if isinstance(actual, (int, float)):
        try:
            return float(actual), float(raw)
        except (TypeError, ValueError):
            return None

    # Everything else compares as text, case-insensitively. Deliberately WITHOUT
    # the old ``.lower().replace(" ", "_")`` mangling, which turned "United
    # States" into "united_states" and so could never match the stored value —
    # every multi-word country, state or department condition silently failed.
    return str(actual).strip().lower(), raw.lower()


def condition_holds(employee, field, op, raw):
    """One (field, operator, value) test against an employee."""
    from payroll.methods.payslip_calc import dynamic_attr

    actual = dynamic_attr(employee, field)
    if actual is None:
        return False

    coerced = _coerce(actual, raw)
    if coerced is None:
        return False
    actual, expected = coerced

    if op == "icontains":
        # Genuinely case-insensitive. The legacy operator map routed this to
        # operator.contains, which is case-SENSITIVE — so a condition labelled
        # "Contains" did not do what it said.
        return str(expected) in str(actual)

    comparisons = {
        "equal": lambda a, b: a == b,
        "notequal": lambda a, b: a != b,
        "lt": lambda a, b: a < b,
        "gt": lambda a, b: a > b,
        "le": lambda a, b: a <= b,
        "ge": lambda a, b: a >= b,
    }
    compare = comparisons.get(op)
    if compare is None:
        return False
    try:
        return bool(compare(actual, expected))
    except TypeError:
        # Mismatched types that survived coercion (a string against a number,
        # say) fail the condition rather than the payslip.
        return False


def component_applies_to(component, employee):
    """
    Whether a condition-based component applies to this employee.

    Replaces three divergent copies of this logic — one per gatherer — which
    had drifted apart: the post-tax copy ignored ``other_conditions`` entirely,
    so a deduction with extra conditions applied on the strength of its first
    one alone, and it had none of the all-must-hold accumulation the other two
    did.

    Every condition must hold. A component that is not condition-based always
    applies.
    """
    if not component.is_condition_based:
        return True

    conditions = list(
        component.other_conditions.values_list("field", "condition", "value")
    )
    if component.field:
        conditions.append((component.field, component.condition, component.value))

    return all(condition_holds(employee, f, op, raw) for f, op, raw in conditions)
