from django import template

register = template.Library()


@register.filter(name="paid_amount")
def paid_amount(installment):
    paid = [
        deduction.amount for deduction in installment if deduction.installment_payslip
    ]

    return round(sum(paid), 2)


@register.filter(name="balance_amount")
def balance_amount(amount, installment):
    balance = amount - paid_amount(installment)
    return round(balance, 2)


@register.filter(name="filing_status_of")
def filing_status_of(payslip):
    """
    The filing status the employee's active contract taxes them under, or None.

    Lets the payslip link its Income Tax line to that status's own page, where
    the slabs and rebates the figure came from are laid out.
    """
    from payroll.models.models import Contract

    employee = getattr(payslip, "employee_id", None)
    if employee is None:
        return None
    contract = (
        Contract.objects.entire()
        .filter(employee_id=employee, contract_status="active")
        .select_related("filing_status")
        .first()
    )
    return contract.filing_status if contract is not None else None


@register.filter(name="income_tax_explanation")
def income_tax_explanation(payslip):
    """
    How this payslip's Income Tax was worked out, for the info popover.

    Re-derived from the figures the payslip stores, by the same functions the
    engine used. ``adjusted`` says the stored tax is not what that comes to
    (someone typed over it), so the popover can say so rather than present a
    working that does not add up to the line beside it.
    """
    from payroll.methods.tax_calc import explain_period_tax
    from payroll.models.models import Contract

    employee = getattr(payslip, "employee_id", None)
    if employee is None:
        return None
    contract = (
        Contract.objects.entire()
        .filter(employee_id=employee, contract_status="active")
        .select_related("filing_status")
        .first()
    )
    filing = contract.filing_status if contract is not None else None
    if filing is None:
        return None
    data = payslip.pay_head_data or {}
    income = float(
        data.get(
            filing.based_on
            if filing.based_on in ("taxable_gross_pay", "gross_pay")
            else "basic_pay"
        )
        or 0
    )
    try:
        explained = explain_period_tax(
            filing,
            income,
            payslip.start_date,
            payslip.end_date,
            employee=employee,
            pay_frequency=contract.pay_frequency,
        )
    except Exception:
        return None
    explained["adjusted"] = (
        abs(float(data.get("federal_tax") or 0) - explained["period_tax"]) > 0.05
    )
    return explained


@register.filter(name="taxable_gross_working")
def taxable_gross_working(payslip):
    """
    How the payslip's taxable gross comes to what it does, line by line.

    Laid out the way the engine builds it -- gross, less earnings that are not
    taxable, less pre-tax deductions, less loss of pay when it is taken as a
    separate pre-tax deduction -- so lines that never show as a figure of their
    own on the payslip (a basic folded into Basic Pay, a loss of pay already
    inside it) are still accounted for. ``stored`` is what the payslip holds, so
    a difference (hand-edited, or generated before a fix) is visible rather than
    silently papered over.
    """
    data = payslip.pay_head_data or {}
    if not data:
        return None
    from payroll.methods.payslip_edit import taxable_loss_of_pay

    earnings = [
        {
            "title": "Basic Pay",
            "amount": float(payslip.basic_pay or data.get("basic_pay") or 0),
            "taxable": True,
        }
    ]
    for row in data.get("allowances") or []:
        earnings.append(
            {
                "title": row.get("title", ""),
                "amount": float(row.get("amount") or 0),
                "taxable": bool(row.get("is_taxable", True)),
            }
        )
    gross = sum(row["amount"] for row in earnings)
    taxable_earnings = [row for row in earnings if row["taxable"]]
    non_taxable = [row for row in earnings if not row["taxable"]]
    pretax = [
        {"title": row.get("title", ""), "amount": float(row.get("amount") or 0)}
        for row in data.get("pretax_deductions") or []
        if row.get("is_pretax", True)
    ]
    lop = taxable_loss_of_pay(payslip)
    # Taxable gross = taxable earnings - pre-tax deductions (- loss of pay when
    # it is a separate pre-tax deduction). The engine reaches the same figure as
    # gross - non-taxable earnings - pre-tax deductions - that loss of pay.
    taxable_total = sum(row["amount"] for row in taxable_earnings)
    pretax_total = sum(row["amount"] for row in pretax)
    computed = max(0.0, taxable_total - pretax_total - lop)
    stored = float(data.get("taxable_gross_pay") or 0)
    return {
        "earnings": earnings,
        "gross": round(gross, 2),
        "taxable_earnings": taxable_earnings,
        "taxable_total": round(taxable_total, 2),
        "pretax_total": round(pretax_total, 2),
        "non_taxable": non_taxable,
        "pretax": pretax,
        "loss_of_pay": round(lop, 2),
        "lop_in_basic": bool(data.get("lop_reflected_in_basic"))
        and bool(data.get("loss_of_pay")),
        "lop_amount_in_basic": round(float(data.get("loss_of_pay") or 0), 2),
        "computed": round(computed, 2),
        "stored": round(stored, 2),
        "matches": abs(computed - stored) < 0.05,
    }


@register.filter(name="basic_pay_working")
def basic_pay_working(payslip):
    """Basic pay as the payslip holds it: before loss of pay, less loss of pay."""
    data = payslip.pay_head_data or {}
    basic = float(payslip.basic_pay or data.get("basic_pay") or 0)
    lop = float(data.get("loss_of_pay") or 0)
    in_basic = bool(data.get("lop_reflected_in_basic")) and lop > 0
    return {
        "basic": round(basic, 2),
        "lop_in_basic": in_basic,
        "lop": round(lop, 2),
        "before_lop": round(basic + lop, 2) if in_basic else round(basic, 2),
        "edited": bool(data.get("basic_edited")),
    }
