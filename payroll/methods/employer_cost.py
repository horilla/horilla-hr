"""
payroll/methods/employer_cost.py

What the employer pays on top of an employee's earnings, worked out in one place.

The same figure is needed three times: stamped on each deduction row of a
payslip, shown in a structure's worked example, and -- under CTC Down -- taken
off the package before the balance earning absorbs what is left. Written once
here so the three cannot drift apart, which is what the worked example had done:
it took the rate of the employee's own deduction (12% of a 2,400 PF = 288)
while the payslip took it of the figure the deduction is based on (12% of a
20,000 basic = 2,400).
"""

from payroll.methods.component_engine import EARNED, component_applies_to
from payroll.methods.component_formula import (
    ComponentFormulaError,
    run_component_formula,
)

# Figures an employer rate can be based on while the balance earning is still
# unknown. Basic pay is already worked out when the balance runs; gross is
# solved for. Anything else (taxable gross, net pay) depends on the balance
# itself, so a CTC Down structure cannot reconcile on it -- see structure_rules.
RECONCILABLE_BASES = ("basic_pay", "gross_pay")


def employer_amount(component, figures, context):
    """
    The employer's contribution on one deduction, as ``(amount, formula)``, or
    ``None`` when it has none. ``formula`` is the text used for a formula basis
    and ``None`` for a percentage.

    ``figures`` maps a deduction's ``based_on`` to the amount it names (basic
    pay, gross pay, ...); ``context`` is the component context a formula reads.
    """
    from payroll.models.models import Deduction

    if component.employer_basis == Deduction.EMPLOYER_BASIS_FORMULA:
        formula = (component.employer_formula or "").strip()
        if not formula:
            return None
        return (
            float(run_component_formula(formula, context)),
            component.employer_formula,
        )

    if not (component.employer_rate or 0) > 0:
        return None
    figure = figures.get(component.based_on) or 0
    return (figure * component.employer_rate) / 100, None


def eligible_deductions(employee, start_date, end_date):
    """
    Every deduction that applies to this employee in the period, whichever of
    the pre-tax, post-tax and tax passes it belongs to. The membership rules are
    the ones those passes use.
    """
    from payroll.models.models import Deduction

    specific = Deduction.objects.filter(specific_employees=employee)
    conditional = Deduction.objects.filter(is_condition_based=True).exclude(
        exclude_employees=employee
    )
    active = Deduction.objects.filter(include_active_employees=True).exclude(
        exclude_employees=employee
    )
    deductions = (
        (specific | conditional | active)
        .distinct()
        .exclude(one_time_date__lt=start_date)
        .exclude(one_time_date__gt=end_date)
        .exclude(update_compensation__isnull=False)
        .exclude(is_system=True)
    )
    return [
        deduction
        for deduction in deductions
        if not deduction.is_condition_based or component_applies_to(deduction, employee)
    ]


def balance_after_employer_cost(deductions, context):
    """
    What is left of CTC for the balance earning once the employer's own costs
    are met, given the earnings already paid in ``context``.

    CTC is the whole cost to the employer: what the employee is paid plus what
    the employer adds on top. A contribution on basic pay is a known figure by
    the time the balance runs. One on gross pay moves with the balance itself,
    so it is solved for rather than guessed::

        balance = CTC - earned - fixed - rate * (earned + balance)
        balance = (CTC - earned * (1 + rate) - fixed) / (1 + rate)

    Never negative, like the balance itself.
    """
    earned = float(context.get(EARNED, 0) or 0)
    # Loss of pay already taken off basic is money the package no longer pays
    # out; leaving it in CTC would let the balance win it straight back.
    ctc = float(context.get("CTC", 0) or 0) - float(context.get("_basic_lop", 0) or 0)
    figures = {"basic_pay": float(context.get("BASIC", 0) or 0)}

    fixed = 0.0
    gross_rate = 0.0
    for component in deductions or ():
        if component.employer_basis == "formula":
            try:
                result = employer_amount(component, figures, context)
            except ComponentFormulaError:
                continue
            fixed += result[0] if result else 0.0
        elif (component.employer_rate or 0) > 0:
            if component.based_on == "gross_pay":
                gross_rate += component.employer_rate / 100
            else:
                fixed += employer_amount(component, figures, context)[0]

    return max((ctc - earned * (1 + gross_rate) - fixed) / (1 + gross_rate), 0.0)
