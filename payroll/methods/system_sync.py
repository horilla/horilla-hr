"""
Keep generated pay rows in line with their standard component.

A loan payout, an instalment, a reimbursement or a penalty copies its tax treatment (taxable, pre-tax)
from the standard component when it is made. Editing that component afterwards has to reach the rows
not yet paid, or the setting would only apply to loans raised after the change.

Rows a payslip already carries are left alone: a paid payslip records what was paid, and rewriting the
component behind it would leave its stored figures unexplained.
"""

from payroll.methods.deductions import LOAN_PAYOUT_KEYS, LOAN_REPAYMENT_KEYS
from payroll.models.models import Deduction, LoanAccount, Payslip, Reimbursement
from payroll.system_components import policy_fields

REIMBURSEMENT_KEYS = {"reimbursement", "leave_encashment", "bonus_encashment"}


def paid_deduction_ids():
    """Deductions already carried on a payslip, by id."""
    return set(
        Payslip.objects.values_list("installment_ids__id", flat=True).exclude(
            installment_ids__id=None
        )
    )


def rows_to_check(keys=None):
    """
    Every generated row paired with the key that should govern it, limited to ``keys`` when given.

    Walked from the owning records, because a generated component carries no mark saying which
    kind produced it. The owner is the only place the kind is known.
    """
    wanted = set(keys) if keys is not None else None
    pairs = []

    def want(key):
        return key and (wanted is None or key in wanted)

    for loan in LoanAccount.objects.entire().select_related("allowance_id"):
        payout_key = LOAN_PAYOUT_KEYS.get(loan.type)
        if want(payout_key) and loan.allowance_id_id:
            pairs.append((loan.allowance_id, payout_key))
        repayment_key = LOAN_REPAYMENT_KEYS.get(loan.type)
        if want(repayment_key):
            pairs.extend(
                (deduction, repayment_key) for deduction in loan.deduction_ids.all()
            )

    for claim in Reimbursement.objects.entire().select_related("allowance_id"):
        key = claim.type if claim.type in REIMBURSEMENT_KEYS else "reimbursement"
        if want(key) and claim.allowance_id_id:
            pairs.append((claim.allowance_id, key))

    if want("penalty"):
        from base.models import PenaltyAccounts

        for account in PenaltyAccounts._base_manager.all():
            ids = (account.additional_info or {}).get("deduction_ids") or []
            pairs.extend(
                (deduction, "penalty")
                for deduction in Deduction.objects.entire().filter(pk__in=ids)
            )
    return pairs


def align(keys=None, apply=True):
    """
    Bring generated rows into line with their standard component.

    Returns ``(changes, frozen)``: ``changes`` is ``[(row, {field: new value})]`` for the rows that
    differ (written when ``apply``), ``frozen`` the paid deductions left as they are.
    """
    paid = paid_deduction_ids()
    changes, frozen = [], []
    for row, key in rows_to_check(keys):
        if row is None or getattr(row, "is_system", False):
            continue
        differs = {
            field: value
            for field, value in policy_fields(key).items()
            if getattr(row, field) != value
        }
        if not differs:
            continue
        if isinstance(row, Deduction) and row.pk in paid:
            frozen.append(row)
            continue
        changes.append((row, differs))
        if apply:
            for field, value in differs.items():
                setattr(row, field, value)
            row.save(update_fields=list(differs))
    return changes, frozen
