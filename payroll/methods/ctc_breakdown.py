"""
payroll/methods/ctc_breakdown.py

How a CTC Down payslip adds up to its CTC, from the figures the payslip stores.

CTC is what the employer spends: the earnings paid inside the package plus the employer's own
contributions. Deductions taken from the employee come out of those earnings, so they are not added
on, and earnings paid outside the structure (a bonus, a loan payout) sit on top of the package.
"""

DEDUCTION_BUCKETS = (
    "basic_pay_deductions",
    "gross_pay_deductions",
    "pretax_deductions",
    "post_tax_deductions",
    "tax_deductions",
    "net_deductions",
)


def _amount(row):
    return float(row.get("amount") or 0)


def ctc_breakdown(payslip):
    """
    The package, what was paid inside it, the employer's contributions and anything outside it,
    or ``None`` when the payslip is not under a CTC Down structure.
    """
    data = payslip.pay_head_data or {}
    context = data.get("component_context") or {}
    ctc = float(context.get("CTC") or 0)
    # Gross Up leaves CTC at zero; only CTC Down states a package for the period.
    if ctc <= 0:
        return None

    lop = float(context.get("_basic_lop") or 0)
    basic = float(payslip.basic_pay or data.get("basic_pay") or 0)
    inside = [{"title": "Basic Pay", "amount": basic}]
    outside = []
    for row in data.get("allowances") or []:
        target = outside if row.get("outside_ctc") else inside
        target.append({"title": row.get("title", ""), "amount": _amount(row)})

    employer = []
    taken = []
    for bucket in DEDUCTION_BUCKETS:
        for row in data.get(bucket) or []:
            share = float(row.get("employer_contribution_amount") or 0)
            if share:
                employer.append({"title": row.get("title", ""), "amount": share})
            taken.append({"title": row.get("title", ""), "amount": _amount(row)})

    package = ctc - lop
    inside_total = sum(row["amount"] for row in inside)
    employer_total = sum(row["amount"] for row in employer)
    return {
        "ctc": ctc,
        "lop": lop,
        "package": package,
        "inside": inside,
        "inside_total": inside_total,
        "employer": employer,
        "employer_total": employer_total,
        "total": inside_total + employer_total,
        "difference": package - inside_total - employer_total,
        "outside": outside,
        "outside_total": sum(row["amount"] for row in outside),
        "taken": taken,
        "taken_total": sum(row["amount"] for row in taken),
    }
