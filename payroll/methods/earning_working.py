"""
payroll/methods/earning_working.py

How each earning on a saved payslip was worked out, for its info popover.

Derived from the component the line came from and the figures the engine stored
on the payslip (``component_context``), by the same summaries the salary
structure pages use, so the payslip cannot describe a component differently from
the page that configures it. Nothing here recalculates a payslip: it explains
the amounts that are on it.

Each working is a plain dict the popover template lays out:

    rule      one line: "50% of BASIC", "Fixed 1,600.00", the formula, ...
    steps     [(label, value)] -- the figures the amount followed from
    equation  the arithmetic with the real numbers, when there is one
    ceiling   (limit, capped) when the component has an upper limit
    notes     short sentences: proration, taxable or not, when it applies
"""

import re

from django.utils.translation import gettext as _

from payroll.methods.component_summary import (
    applies_summary,
    calculation_summary,
    ceiling_summary,
    proration_summary,
)
from payroll.methods.payslip_edit import (
    AGGREGATE_CODES,
    FORMULA_CALLS,
    _components_on,
    formula_context,
)

BASIC = "basic"


def _num(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _percent_of(component, context, amount):
    """Base × rate = amount for a "percentage of ..." component, or None."""
    based_on = getattr(component, "based_on", "") or ""
    if based_on == "component":
        code = (getattr(component, "percentage_of_code", "") or "").strip().upper()
    elif based_on in AGGREGATE_CODES:
        code = AGGREGATE_CODES[based_on]
    else:
        return None
    if not code or code not in context:
        return None
    rate = float(getattr(component, "rate", 0) or 0)
    base = float(context[code])
    return {
        "steps": [(code, _num(base)), (_("Rate"), f"{rate:g}%")],
        "equation": f"{_num(base)} × {rate:g}% = {_num(base * rate / 100)}",
        "worked": base * rate / 100,
    }


def _formula(component, context):
    """The formula and the figures it read, or None."""
    if getattr(component, "based_on", "") != "formula":
        return None
    expression = (getattr(component, "formula", "") or "").strip()
    if not expression:
        return None
    names = sorted(
        set(re.findall(r"[A-Z_][A-Z0-9_]*", expression.upper())) - FORMULA_CALLS
    )
    return {
        "steps": [(name, _num(context[name])) for name in names if name in context],
        "equation": expression,
        "worked": None,
    }


def _working_for(component, row, amount, context):
    """One earning's working, from its component and its stored amount."""
    working = {
        "title": row.get("title", ""),
        "amount": amount,
        "rule": "",
        "steps": [],
        "equation": "",
        "ceiling": None,
        "notes": [],
    }
    if component is None:
        working["rule"] = _("Added by hand on this payslip")
        working["manual"] = True
        return working

    working["rule"] = str(calculation_summary(component))
    working["manual"] = False

    if getattr(component, "is_fixed", False):
        configured = float(getattr(component, "amount", 0) or 0)
        working["steps"].append((_("Set amount"), _num(configured)))
        if abs(configured - float(amount)) > 0.005:
            working["steps"].append((_("For this period"), _num(amount)))
            working["notes"].append(
                _("Prorated: %(how)s.")
                % {"how": str(proration_summary(component)).lower()}
            )
    else:
        derived = _percent_of(component, context, amount) or _formula(
            component, context
        )
        if derived:
            working["steps"] = derived["steps"]
            working["equation"] = derived["equation"]

    if getattr(component, "has_max_limit", False):
        limit = getattr(component, "maximum_amount", None)
        if limit is not None:
            working["ceiling"] = (
                _num(limit),
                float(amount) >= float(limit) - 0.005,
            )

    applies = str(applies_summary(component))
    if applies not in {_("Always"), "Always", "—"}:
        working["notes"].append(_("Applies when: %(rule)s.") % {"rule": applies})
    return working


def earning_workings(payslip):
    """
    ``{allowance_id or "basic": working}`` for every earning on the payslip.

    A line added by hand has no allowance_id; it is found by its title instead
    (``working_key``), which is the only thing it has.
    """
    data = payslip.pay_head_data or {}
    allowances, _deductions = _components_on(payslip)
    context = formula_context(payslip)
    workings = {}

    basic_component = allowances.get(data.get("basic_pay_component_id"))
    basic = float(payslip.basic_pay or data.get("basic_pay") or 0)
    lop = float(data.get("loss_of_pay") or 0)
    in_basic = bool(data.get("lop_reflected_in_basic")) and lop > 0
    working = _working_for(basic_component, {"title": _("Basic Pay")}, basic, context)
    if basic_component is None:
        working["manual"] = False
        working["rule"] = _("The contract wage")
        contract = payslip.employee_id.contract_set.filter(
            contract_status="active"
        ).first()
        if contract is not None and getattr(contract, "wage", None):
            working["steps"].append((_("Contract wage"), _num(contract.wage)))
    working["notes"].append(
        _(
            "Worked out by the structure's basic pay component (CTC Down), not the contract wage."
        )
        if basic_component is not None
        else _(
            "The contract wage under Gross Up; under CTC Down the structure's basic pay component works it out from the CTC instead."
        )
    )
    if in_basic:
        working["steps"].append((_("Before loss of pay"), _num(basic + lop)))
        working["steps"].append((_("Less loss of pay"), "−" + _num(lop)))
        working["equation"] = f"{_num(basic + lop)} − {_num(lop)} = {_num(basic)}"
    if data.get("basic_edited"):
        working["notes"].append(_("Changed by hand on this payslip."))
    workings[BASIC] = working

    for row in data.get("allowances") or []:
        amount = float(row.get("amount") or 0)
        entry = _working_for(
            allowances.get(row.get("allowance_id")), row, amount, context
        )
        entry["taxable"] = bool(row.get("is_taxable", True))
        if row.get("outside_ctc"):
            entry["notes"][:0] = [
                _("Extra Pay, Outside The Salary Structure."),
                _(
                    "It Is Added On Top Of The CTC, So The Other Earnings Stay The Same."
                ),
            ]
        entry["notes"].append(
            _("Counts toward taxable gross.") if entry["taxable"] else _("Not taxable.")
        )
        workings[working_key(row)] = entry
    return workings


def working_key(row):
    """The key a stored earning or deduction line is filed under."""
    if not row.get("custom_id"):
        if row.get("deduction_id") is not None:
            return f"d:{row['deduction_id']}"
        if row.get("allowance_id") is not None:
            return f"a:{row['allowance_id']}"
    return f"title:{row.get('title', '')}"


# Where a deduction sits on the payslip, in a sentence.
BUCKET_NOTES = {
    "basic_pay_deductions": _("Comes off basic pay."),
    "gross_pay_deductions": _("Comes off gross pay."),
    "pretax_deductions": _("Taken before income tax is worked out."),
    "post_tax_deductions": _("Taken after income tax."),
    "tax_deductions": _("A tax charged alongside income tax."),
    "net_deductions": _("Comes off net pay."),
}


def _deduction_components(data):
    from payroll.models.models import Deduction

    ids = [
        row.get("deduction_id")
        for bucket in BUCKET_NOTES
        for row in data.get(bucket) or []
        if row.get("deduction_id")
    ]
    return Deduction.objects.entire().in_bulk(ids)


def _income_tax_working(payslip, amount):
    """The Income Tax line's working, from the same explanation the Tax Working panel uses."""
    from payroll.templatetags.payrollfilters import income_tax_explanation

    tax = income_tax_explanation(payslip)
    if not tax:
        return None
    breakdown = tax.get("breakdown") or {}
    basis = {
        "gross_pay": _("Gross pay this period"),
        "taxable_gross_pay": _("Taxable gross this period"),
    }.get(tax.get("based_on"), _("Basic pay this period"))
    steps = [
        (basis, _num(tax["income"])),
        (_("Yearly income"), _num(tax["yearly_income"])),
    ]
    if breakdown.get("standard_deduction"):
        steps.append(
            (_("Taxable yearly income"), _num(breakdown.get("taxable_income")))
        )
    steps.append((_("Tax for the year"), _num(tax["yearly_tax"])))
    if tax.get("method") == "periods":
        divide = f"÷ {tax.get('periods')}"
    else:
        divide = f"÷ {tax.get('year_days')} × {tax.get('days')}"
    notes = [_("The full working is in the Tax Working panel.")]
    if tax.get("adjusted"):
        notes.insert(0, _("Changed by hand on this payslip."))
    return {
        "title": _("Income Tax"),
        "amount": amount,
        "rule": str(tax["filing_status"]),
        "steps": steps,
        "equation": f"{_num(tax['yearly_tax'])} {divide} = {_num(tax['period_tax'])}",
        "ceiling": None,
        "notes": notes,
        "manual": False,
    }


def deduction_workings(payslip):
    """``{key: working}`` for the deductions on a saved payslip, and ``"tax"`` for income tax."""
    data = payslip.pay_head_data or {}
    components = _deduction_components(data)
    context = formula_context(payslip)
    workings = {}
    under_ctc_down = float((data.get("component_context") or {}).get("CTC") or 0) > 0
    for bucket, note in BUCKET_NOTES.items():
        for row in data.get(bucket) or []:
            amount = float(row.get("amount") or 0)
            component = components.get(row.get("deduction_id"))
            entry = _working_for(component, row, amount, context)
            entry["notes"].append(note)
            if under_ctc_down:
                entry["notes"].append(
                    _("Comes Out Of The Earnings, So It Is Not Part Of The CTC.")
                )
            employer = (
                getattr(component, "employer_rate", 0) if component is not None else 0
            )
            share = float(row.get("employer_contribution_amount") or 0)
            if employer or share:
                entry["notes"].append(
                    _(
                        "Employer Contribution: %(rate)s%(amount)s. It Is Not Taken From This Payslip."
                    )
                    % {
                        "rate": f"{float(employer):g}% = " if employer else "",
                        "amount": f"{share:,.2f}",
                    }
                )
            workings[working_key(row)] = entry
    tax = _income_tax_working(payslip, float(data.get("federal_tax") or 0))
    if tax:
        workings["tax"] = tax
    return workings
