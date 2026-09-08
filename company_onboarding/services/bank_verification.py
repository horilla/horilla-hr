"""
company_onboarding/services/bank_verification.py

Penny-drop bank account verification, with the real Cashfree API call
stubbed out. Both functions are the seam a future real integration plugs
into — see the docstrings for exactly what to replace.
"""

import random
from decimal import Decimal

from company_onboarding.models import CompanyBankDetails, CompanyBankVerification


def initiate_penny_drop(bank_details: CompanyBankDetails) -> CompanyBankVerification:
    """
    STUB: generates a random amount between ₹0.01 and ₹1.99 and marks
    drop_status='success' immediately, so the confirm-page flow is
    testable end-to-end without live bank rails.

    Real Cashfree integration point: replace the random-amount generation
    and immediate 'success' with an actual call to Cashfree's Penny Drop /
    Bank Account Verification API — store their reference_id in
    cashfree_reference_id, and set drop_status from their synchronous
    response or webhook instead of assuming success.
    """
    dropped_amount = Decimal(random.randint(1, 199)) / 100
    return CompanyBankVerification.objects.create(
        bank_details=bank_details,
        dropped_amount=dropped_amount,
        drop_status=CompanyBankVerification.DropStatus.SUCCESS,
    )


def confirm_penny_drop(
    attempt: CompanyBankVerification, entered_amount: Decimal
) -> bool:
    """
    entered_amount is never persisted itself — only compared in-memory
    against attempt.dropped_amount — but the OUTCOME now updates
    CompanyBankDetails.verification_status: Verified on match, Failed on
    mismatch. Still no cap on resubmissions — a Failed status can always
    be retried, flipping to Verified on a later correct attempt.
    """
    matched = Decimal(entered_amount) == attempt.dropped_amount
    attempt.bank_details.verification_status = (
        CompanyBankDetails.VerificationStatus.VERIFIED
        if matched
        else CompanyBankDetails.VerificationStatus.FAILED
    )
    attempt.bank_details.save()
    return matched
