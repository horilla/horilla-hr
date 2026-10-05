"""
payroll/methods/structure_rules.py

What makes a salary structure coherent.

`Contract.wage` is the only salary input the engine has, and its meaning depends
entirely on the structure the employee is on: basic pay under Gross Up, the total
to divide up under CTC Down. Nothing checked that the structure agreed with that
reading, so two silent failures were reachable:

  * A Gross Up structure containing a component coded BASIC. The wage is already
    basic, so gross becomes wage + BASIC + the rest — basic counted twice. Worse,
    `record()` publishes that component under BASIC, so every later "percentage of
    BASIC" is a percentage of the component instead of the contract's basic.

  * A CTC Down structure with no BASIC component. `basic_pay` stays 0, so a filing
    status "based on basic pay" taxes nothing and the payslip shows no basic.

Neither raised. Both produced a payslip that looked fine.

The rules live here, away from both the form and the engine, because both need
them: the form to refuse a bad set, the engine to refuse a bad run, and a
management command to find the ones already stored. The v2 engine reached the
same conclusion in its own component-set validation.
"""

from django.utils.translation import gettext_lazy as _

from payroll.methods.employer_cost import RECONCILABLE_BASES


def _flagged_basics(allowances):
    return [c for c in allowances if getattr(c, "is_basic_pay", False)]


def structure_problems(structure_mode, allowances, deductions=()):
    """
    Everything wrong with this component set, as a list of messages.

    Takes the mode and the components rather than a SalaryStructure, so it can be
    called on a form's cleaned_data before anything is saved — the M2M is not
    populated during model validation, which is why this cannot live in
    Model.clean(). The v2 engine documented hitting the same wall.

    Basic pay is identified by the `is_basic_pay` flag, not by a component's
    code. The code is derived from the title, so a rename could silently change
    which earning the engine treated as basic; a flag someone ticked cannot.
    """
    mode = structure_mode or "gross_up"
    allowances = list(allowances or [])
    deductions = list(deductions or [])
    problems = []

    basics = _flagged_basics(allowances)
    balances = [
        component
        for component in allowances
        if getattr(component, "based_on", None) == "balance"
        and not getattr(component, "is_fixed", False)
    ]

    if len(basics) > 1:
        titles = ", ".join(str(c.title) for c in basics)
        problems.append(
            _(
                "Only one earning can be the basic pay. These are all marked "
                "as it: %(titles)s."
            )
            % {"titles": titles}
        )

    if mode == "ctc_down" and not basics:
        problems.append(
            _(
                "A CTC Down structure divides the package up, so the contract "
                "wage is not basic pay — one earning here has to be marked as "
                "basic pay instead. Without it basic pay is nothing, which "
                "also means income tax based on basic pay is worked out on "
                "nothing."
            )
        )

    if mode != "ctc_down" and balances:
        titles = ", ".join(str(component.title) for component in balances)
        problems.append(
            _(
                "A balance earning absorbs what is left of the CTC, so it only "
                "means something in a CTC Down structure: %(titles)s."
            )
            % {"titles": titles}
        )

    if mode == "ctc_down" and len(balances) > 1:
        problems.append(_("Only one earning may absorb the balance of the CTC."))

    # A balance earning has to run last: it can only see what has already been
    # worked out, so anything after it is simply left out of the remainder.
    if balances:
        last = max(
            (getattr(c, "sequence", 0) or 0 for c in allowances + deductions),
            default=0,
        )
        trailing = [
            component
            for component in balances
            if (getattr(component, "sequence", 0) or 0) < last
        ]
        if trailing:
            titles = ", ".join(str(component.title) for component in trailing)
            problems.append(
                _(
                    "A balance earning has to be worked out last, so give it the "
                    "highest sequence in the structure: %(titles)s."
                )
                % {"titles": titles}
            )

    # CTC is the whole cost to the employer, so the balance earning is worked
    # out net of the employer's contributions. That only closes if each of them
    # can be known before the balance is: a percentage of basic or gross pay can
    # (gross is solved for), but one of taxable gross or net pay is itself
    # derived from the balance, and a formula that names the balance cannot be
    # evaluated before it exists.
    if mode == "ctc_down" and balances:
        balance_codes = {
            (getattr(c, "code", "") or "").strip().upper() for c in balances
        } - {""}
        for deduction in deductions:
            if getattr(deduction, "employer_basis", "rate") == "formula":
                import re

                used = set(
                    re.findall(
                        r"[A-Z_][A-Z0-9_]*",
                        (getattr(deduction, "employer_formula", "") or "").upper(),
                    )
                )
                if used & balance_codes:
                    problems.append(
                        _(
                            "The employer share of %(title)s refers to the balance "
                            "earning, which is worked out from it."
                        )
                        % {"title": deduction.title}
                    )
            elif (getattr(deduction, "employer_rate", 0) or 0) > 0 and getattr(
                deduction, "based_on", None
            ) not in RECONCILABLE_BASES:
                problems.append(
                    _(
                        "The employer share of %(title)s is a percentage of a "
                        "figure that depends on the balance earning, so the CTC "
                        "cannot add up. Base it on basic pay or gross pay."
                    )
                    % {"title": deduction.title}
                )

    return problems


def basic_pay_note(structure_mode, allowances):
    """
    Where basic pay comes from for employees on this structure, and which
    source wins when both state one.

    Said here because this is where components are chosen and no employee's
    contract is visible from it. The precedence is the part nobody could infer:
    the contract wins, and a flagged earning is only the fallback — so a
    structure can carry one and never use it for most of the workforce.
    """
    from payroll.methods.basic_pay_source import basic_pay_component

    mode = structure_mode or "gross_up"
    flagged = basic_pay_component(allowances or [])

    if mode == "ctc_down":
        if flagged is None:
            return _(
                "Basic pay: nothing works it out. This structure divides the "
                "contract's Monthly CTC into components, so basic pay has to "
                "come from one of them — mark the earning that calculates it. "
                "Until then basic pay is zero, and income tax based on basic "
                "pay would be worked out on nothing."
            )
        return _(
            "Basic pay: %(component)s. This structure divides the contract's "
            "Monthly CTC, so the contract wage is not read as basic pay here — "
            "%(component)s is. If Monthly CTC is empty, the wage is divided "
            "instead."
        ) % {"component": flagged.title}

    if flagged is None:
        return _(
            "Basic pay: each employee's contract wage. No earning here is "
            "marked as basic pay, so an employee whose contract has no wage "
            "would be paid no basic pay at all."
        )
    return _(
        "Basic pay: the contract wage wins. %(component)s is marked as basic "
        "pay, but it is only the fallback — it is used for an employee whose "
        "contract has no wage, and for everyone else it is not paid at all, "
        "because paying it as well would count basic twice."
    ) % {"component": flagged.title}


def assignable_employees(structure=None):
    """
    The employees a structure may be assigned to.

    Two conditions, and both matter for the same reason: a structure reaches an
    employee only through their active contract's ``salary_structure_id``.

      * They must have an active contract. Without one there is nothing to
        write the structure onto, so the assignment silently does nothing.

      * That contract must not already name a different structure. Assigning
        one here overwrites it, which moves the employee off the other
        structure without saying so -- and the other structure's own form would
        then show them missing with no record of why.

    Both conditions are on the SAME contract, which is why they are one
    ``filter()`` call: a Django filter across one multi-valued relation matches
    a single related row, so this cannot be satisfied by an active contract and
    a separate unassigned one.

    ``structure`` is the structure being edited, whose own employees stay
    eligible -- otherwise editing a structure would offer to remove everybody
    on it and never offer to keep them.
    """
    from django.db.models import Q

    from employee.models import Employee

    unassigned = Q(contract_set__salary_structure_id__isnull=True)
    if structure is not None and getattr(structure, "pk", None):
        unassigned |= Q(contract_set__salary_structure_id=structure.pk)

    return (
        Employee.objects.filter(Q(contract_set__contract_status="active") & unassigned)
        .distinct()
        .order_by("employee_first_name", "employee_last_name")
    )


def unassignable_reason(employee, structure=None):
    """
    Why an employee cannot be put on this structure, or None if they can.

    Two separate messages rather than one: "no active contract" and "already on
    another structure" need different things done about them, and a single
    "cannot be assigned" would send someone looking in the wrong place.
    """
    contract = employee.contract_set.filter(contract_status="active").first()
    if contract is None:
        return "no_contract"

    current = contract.salary_structure_id
    if current is None:
        return None
    if structure is not None and current.pk == getattr(structure, "pk", None):
        return None
    return current
