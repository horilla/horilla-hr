"""
payroll/methods/ctc_breakdown.py

How a CTC Down payslip adds up to its CTC, from the figures the payslip stores.

CTC is what the employer spends: the earnings paid inside the package plus the employer's own
contributions. Deductions taken from the employee come out of those earnings, so they are not added
on, and earnings paid outside the structure (a bonus, a loan payout) sit on top of the package.
"""

from django.utils.translation import gettext_lazy as _

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


def _balance_ids(ids):
    """Which of these allowances are the balance component: the one that fills the rest of the package."""
    if not ids:
        return set()
    from payroll.models.models import Allowance

    return set(
        Allowance.objects.entire()
        .filter(pk__in=ids, based_on="balance")
        .values_list("pk", flat=True)
    )


def lop_note(ctc, lop, context):
    """
    Why the total is below the monthly CTC when loss of pay was taken off basic, or ``None``.

    A payslip that adds up exactly to its (reduced) package has nothing to warn about, but the
    total still reads lower than the CTC at the top of the page, so the reason is said outright.
    """
    if lop <= 0.005:
        return None
    days = float(context.get("UNPAID_DAYS") or 0)
    return _(
        "%(gap)s Less Than The Monthly CTC Of %(ctc)s: Loss Of Pay%(days)s Was Taken Off Basic Pay, So The Package For This Period Is %(package)s."
    ) % {
        "gap": f"{lop:,.2f}",
        "ctc": f"{ctc:,.2f}",
        "days": f" For {days:g} Unpaid Day{'' if days == 1 else 's'}" if days else "",
        "package": f"{ctc - lop:,.2f}",
    }


def difference_reason(data, difference):
    """
    Why a payslip does not add up to its package, in a sentence, from what the payslip records.

    A gap is not always a mistake: a structure with no balance component leaves the rest of the
    package unallocated by design. What is stated is the cause the data supports, never a guess
    between several.
    """
    rows = data.get("allowances") or []
    gap = f"{abs(difference):,.2f}"
    if data.get("basic_edited"):
        return _(
            "Basic Pay Was Changed By Hand On This Payslip, So It No Longer Follows The Package."
        )
    if any(row.get("custom_id") for row in rows):
        return _(
            "A Line Was Added To This Payslip By Hand, So It Is Not Part Of The Structure's Package."
        )

    balance = _balance_ids(
        [row["allowance_id"] for row in rows if row.get("allowance_id")]
    )
    balance_paid = sum(
        _amount(row) for row in rows if row.get("allowance_id") in balance
    )
    if difference > 0:
        if not balance:
            return _(
                "The Structure Has No Balance Component To Fill The Rest Of The Package, So %(gap)s Of It Is Not Paid Out."
            ) % {"gap": gap}
        return _(
            "The Balance Component Is Short By %(gap)s: A Line On This Payslip Was Changed Or Removed After It Was Generated."
        ) % {"gap": gap}
    if balance and balance_paid <= 0.005:
        return _(
            "The Other Components Already Add Up To %(gap)s More Than The Package, So The Balance Component Has Nothing Left To Fill."
        ) % {"gap": gap}
    return _(
        "A Line On This Payslip Was Raised Or Added After It Was Generated, Taking It %(gap)s Over The Package."
    ) % {"gap": gap}


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
    if not lop and data.get("lop_reflected_in_basic"):
        # A payslip that did not keep the cut in its context still states the loss of pay it took
        # off basic, and the package is short of the CTC by exactly that.
        lop = float(data.get("loss_of_pay") or 0)
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
        "difference_reason": difference_reason(
            data, package - inside_total - employer_total
        ),
        "lop_note": lop_note(ctc, lop, context),
        "outside": outside,
        "outside_total": sum(row["amount"] for row in outside),
        "taken": taken,
        "taken_total": sum(row["amount"] for row in taken),
    }
