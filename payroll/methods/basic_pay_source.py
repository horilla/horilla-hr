"""
payroll/methods/basic_pay_source.py

Where an employee's basic pay comes from.

There are two places it can be stated, and they are both legitimate:

  * **The contract.** ``Contract.wage``, in the unit its ``wage_type`` says.
    This is where an employee's pay is actually agreed, so it wins.
  * **A component.** An earning on their salary structure with
    ``is_basic_pay`` set. Used when the contract states no wage — a CTC Down
    structure works basic out as a share of the package rather than having it
    typed in.

The rule, in one sentence: **the contract wins; the component is the fallback.**

The consequence that matters is what happens to the flagged component when the
contract does state a wage. It must be *skipped*, not paid — if it were paid it
would be added to gross on top of a basic that is already there, and basic would
be counted twice. That single decision is why this lives in its own module and
returns an explicit source rather than being an ``or`` somewhere: every caller
has to agree about it.

Nothing here changes an existing payslip. Every contract in normal use has a
wage, so ``CONTRACT`` is the answer and the engine behaves exactly as before.
The component path only opens up for a contract left at zero, which previously
produced a payslip with no basic pay at all.
"""

CONTRACT = "contract"
COMPONENT = "component"
NEITHER = "neither"


def basic_pay_component(allowances):
    """
    The earning flagged as basic pay, if there is one.

    Takes an iterable rather than a structure so the engine can pass the
    candidates it already resolved, and the structure form can pass unsaved
    cleaned_data.
    """
    for allowance in allowances or []:
        if getattr(allowance, "is_basic_pay", False):
            return allowance
    return None


def resolve_basic_pay_source(contract_basic, allowances, wage_is_the_pot=False):
    """
    Which source is in force, as ``(source, component)``.

    ``contract_basic`` is the rate the CONTRACT states — ``Contract.pay_rate``
    — not the figure it produced for this period.

    That distinction was got wrong once and it matters: an hourly contract
    states 10/hour and computes to zero in a period with no attendance, and a
    monthly contract on full loss of pay computes to zero too. Keying on the
    computed figure read both as "the contract states nothing" and fell
    through to the flagged earning, or to refusing the payslip. Whether a
    contract names a rate is a property of the contract; what it came to this
    period is a different question.

    ``wage_is_the_pot`` is the case that cannot be decided from the numbers
    alone: a CTC Down structure with no CTC of its own divides the *wage*, so
    that figure is already spoken for and says nothing about basic. Reading it
    as basic there would spend it twice — once as the package being divided,
    once as basic pay on top. The component is then the only source.
    """
    component = basic_pay_component(allowances)
    if wage_is_the_pot:
        return (COMPONENT, component) if component is not None else (NEITHER, None)
    if contract_basic and float(contract_basic) > 0:
        return CONTRACT, component
    if component is not None:
        return COMPONENT, component
    return NEITHER, None


def describe(source, component=None, contract_basic=None):
    """
    One line for the UI saying where basic pay will come from.

    Written for someone configuring a structure who cannot see an employee's
    contract from here, which is why it names the mechanism rather than a
    figure.
    """
    from django.utils.translation import gettext_lazy as _

    if source == CONTRACT:
        if component is not None:
            return _(
                "Basic pay comes from each employee's contract wage. "
                "%(component)s is marked as basic pay, so it is only used for "
                "an employee whose contract has no wage — for anyone else it "
                "is not paid, because their basic is already set."
            ) % {"component": component.title}
        return _("Basic pay comes from each employee's contract wage.")
    if source == COMPONENT:
        return _(
            "Basic pay is worked out by %(component)s, for employees whose "
            "contract has no wage."
        ) % {"component": component.title}
    return _(
        "No earning is marked as basic pay, so basic pay comes from each "
        "employee's contract wage. An employee whose contract has no wage "
        "would be paid no basic pay at all."
    )
