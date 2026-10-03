"""
payroll/methods/component_summary.py

Plain-language descriptions of what a component does.

A salary structure is a list of rules, and until now reading one meant opening
every component in turn: the structure's detail view showed titles only, so
"House Rent Allowance (HRA)" told you nothing about whether it was a fixed
1,600 or half of basic, or when it applied.

These produce the one-line summaries the structure listing shows. Deliberately
derived from the same fields the engine reads, and nothing else, so a
description cannot claim something the calculation does not do.

Duck-typed on purpose — it takes an Allowance or a Deduction, and the tests
pass plain stand-ins.
"""

from django.utils.translation import gettext_lazy as _

from payroll.methods.proration import (
    FULL_PERIOD,
    MONTH_CALENDAR_DAYS,
    MONTH_WORKING_DAYS,
    PER_WORKING_DAY,
)

# What each aggregate is called in a summary. The engine's own context keys, so
# a formula referring to GROSS and a summary saying "of GROSS" agree.
AGGREGATE_NAMES = {
    "basic_pay": "BASIC",
    "gross_pay": "GROSS",
    "taxable_gross_pay": "TAXABLE GROSS",
    "net_pay": "NET",
    "ctc": "CTC",
}

PRORATION_NAMES = {
    MONTH_CALENDAR_DAYS: _("By calendar days"),
    MONTH_WORKING_DAYS: _("By working days"),
    PER_WORKING_DAY: _("Per working day"),
    FULL_PERIOD: _("No"),
}


def _number(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _rate(value):
    try:
        return f"{float(value):g}%"
    except (TypeError, ValueError):
        return _("an unset rate")


def calculation_summary(component):
    """
    One line saying how this component's amount is worked out.

    Covers every strategy the engine dispatches on, and falls back to the
    stored label rather than inventing one — a summary that guessed would be
    worse than a summary that admits it does not know.
    """
    if getattr(component, "is_fixed", False):
        return _number(getattr(component, "amount", None))

    based_on = getattr(component, "based_on", None) or ""
    rate = getattr(component, "rate", None)

    if based_on == "component":
        target = (getattr(component, "percentage_of_code", "") or "").strip().upper()
        return f"{_rate(rate)} {_('of')} {target or _('nothing chosen')}"

    if based_on == "formula":
        formula = (getattr(component, "formula", "") or "").strip()
        return formula or str(_("No formula yet"))

    if based_on == "balance":
        return str(_("Balance of CTC"))

    if based_on in AGGREGATE_NAMES:
        return f"{_rate(rate)} {_('of')} {AGGREGATE_NAMES[based_on]}"

    per_unit = {
        "children": ("per_children_fixed_amount", _("per child")),
        "attendance": ("per_attendance_fixed_amount", _("per day present")),
        "shift_id": ("shift_per_attendance_amount", _("per shift day")),
        "work_type_id": ("work_type_per_attendance_amount", _("per work-type day")),
        "overtime": ("amount_per_one_hr", _("per overtime hour")),
        "week_off_overtime": ("amount_per_one_hr", _("per week-off hour")),
        "holiday_overtime": ("amount_per_one_hr", _("per holiday hour")),
    }
    if based_on in per_unit:
        field, unit = per_unit[based_on]
        return f"{_number(getattr(component, field, None))} {unit}"

    display = getattr(component, "get_based_on_display", None)
    if callable(display):
        try:
            return str(display() or _("Not configured"))
        except Exception:  # a stale based_on value with no label
            pass
    return str(_("Not configured"))


def proration_summary(component):
    """
    How this component's figures follow the period: by calendar days, by
    working days, per working day, not at all, or inherited.

    "Inherited" covers every calculated component, and it is the accurate word
    rather than a hedge. A percentage of basic reads a basic that
    compute_salary_on_period has already prorated; a per-hour overtime rate is
    multiplied by hours actually worked; a balance figure is the remainder of an
    already-prorated CTC. All of them follow the period without a setting of
    their own, and applying one would prorate them twice. Only a flat amount has
    nothing to inherit from, which is why the basis governs just those.

    The v2 engine arrived at the same three-state answer for the same reason.
    """
    if not getattr(component, "is_fixed", False):
        return str(_("Inherited"))
    basis = getattr(component, "maximum_unit", None)
    return str(PRORATION_NAMES.get(basis, _("No")))


def in_ctc_summary(component, kind):
    """
    Whether this component is part of what a CTC figure has to cover.

    Derived, not stored. An earning is paid to the employee and an employer
    share is a company cost, so both are inside the total cost; a deduction
    comes out of gross, which is already counted, so counting it again would
    double up. Mirrors the CTC component types the v2 engine used.
    """
    if kind == "earning":
        return str(_("Yes"))
    if getattr(component, "employer_rate", 0):
        return str(_("Employer share only"))
    return str(_("—"))


def ceiling_summary(component):
    """The upper limit, if there is one."""
    if not getattr(component, "has_max_limit", False):
        return str(_("—"))
    amount = getattr(component, "maximum_amount", None)
    if amount is None:
        return str(_("Set, but no figure"))
    return _number(amount)


def applies_summary(component):
    """
    When the component applies, counting the extra rules.

    Every component carries a default "basic pay > 0" rule, which is really
    asking whether the employee is being paid at all, so that on its own is
    reported as "Always" rather than as a condition someone configured.
    """
    extra = 0
    related = getattr(component, "apply_conditions", None)
    if related is not None and getattr(component, "pk", None):
        extra = related.count()

    choice = getattr(component, "if_choice", "") or ""
    condition = getattr(component, "if_condition", "") or ""
    amount = getattr(component, "if_amount", None)
    default_gate = (
        choice == "basic_pay" and condition == "gt" and (amount in (0, 0.0, None))
    )

    if default_gate and not extra:
        return str(_("Always"))

    parts = []
    if not default_gate:
        target = AGGREGATE_NAMES.get(choice, choice.upper() or "?")
        if choice == "component":
            target = (
                getattr(component, "if_component_code", "") or ""
            ).strip().upper() or "?"
        if condition == "range":
            parts.append(
                f"{target} {_('between')} {_number(getattr(component, 'start_range', None))}"
                f" – {_number(getattr(component, 'end_range', None))}"
            )
        else:
            symbol = {
                "equal": "=",
                "notequal": "≠",
                "lt": "<",
                "gt": ">",
                "le": "≤",
                "ge": "≥",
            }.get(condition, condition)
            parts.append(f"{target} {symbol} {_number(amount)}")
    if extra:
        parts.append(f"+{extra} {_('more')}")
    return ", ".join(parts) or str(_("Always"))
