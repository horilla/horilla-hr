"""
company_onboarding/services/bank_verification.py

Real penny-drop bank account verification via Cashfree (cashfree_client.py):

  1. verify_bank_account() -- instant, no money moves -- checks the
     account_number/ifsc are real before we even attempt a transfer.
  2. initiate_bank_transfer() -- moves real money, a random amount
     between Rs 1.00 and Rs 1.99 (Cashfree's Payouts API requires
     amount >= 1.00, so this can't go as low as Rs 0.01 the way the
     original local-only stub did).

Transfers V2 is async, so initiate_penny_drop() records the attempt as
PENDING when Cashfree hasn't resolved it yet within the same request --
check_penny_drop_status() is the follow-up call to find out what actually
happened. confirm_penny_drop() (checking what the admin says landed in
the account against what we actually sent) is purely a local comparison,
no further Cashfree call needed for that half.
"""

import random
from decimal import Decimal

from company_onboarding.models import (
    CashfreeApiLog,
    CompanyBankDetails,
    CompanyBankVerification,
)
from company_onboarding.services.cashfree_client import (
    CashfreePayoutError,
    get_transfer_status,
    initiate_bank_transfer,
    verify_bank_account,
)


def initiate_penny_drop(bank_details: CompanyBankDetails) -> CompanyBankVerification:
    """
    Verifies the account is real via Cashfree's instant Bank Account
    Verification, then transfers a random Rs 1.00-1.99 amount to it via
    Cashfree Payouts V2, and records the attempt. The beneficiary name/
    phone come straight from bank_details (captured when the bank details
    were entered), not looked up from a point of contact -- the account
    holder isn't necessarily any of the company's POCs. Raises
    CashfreePayoutError if the transfer couldn't even be attempted
    (account holder name/contact number missing on bank_details, the
    account fails instant verification, bad credentials, network
    failure) -- the caller (the view) is responsible for turning that
    into a user-facing message. A transfer Cashfree itself declines
    (e.g. bank offline) is NOT an exception -- it's recorded as
    drop_status=FAILED like any other failed attempt, and can be retried.
    """
    company = bank_details.company
    beneficiary_name = bank_details.account_holder_name
    beneficiary_phone = bank_details.contact_number
    if not beneficiary_name or not beneficiary_phone:
        raise CashfreePayoutError(
            "Add the account holder's name and contact number to bank "
            "details before initiating bank verification -- Cashfree "
            "requires both to register the beneficiary."
        )

    check = verify_bank_account(
        account_number=bank_details.account_number,
        ifsc=bank_details.ifsc_swift,
        name=beneficiary_name,
        phone=beneficiary_phone,
    )
    CashfreeApiLog.objects.create(
        bank_details=bank_details,
        call_type=CashfreeApiLog.CallType.VERIFY_BANK_ACCOUNT,
        http_status=check["http_status"],
        request_payload=check["request_payload"],
        response_payload=check["response_payload"],
    )
    if not check["valid"]:
        raise CashfreePayoutError(
            f"Bank account verification failed: {check['message'] or check['account_status']}"
        )

    amount = Decimal(random.randint(100, 199)) / 100
    beneficiary_logs = []
    try:
        result = initiate_bank_transfer(
            account_number=bank_details.account_number,
            ifsc=bank_details.ifsc_swift,
            amount=amount,
            company_id=company.pk,
            beneficiary_name=beneficiary_name,
            beneficiary_email="",
            beneficiary_phone=beneficiary_phone,
            beneficiary_address=company.address,
            log_sink=beneficiary_logs,
        )
    finally:
        # Logged even on failure -- beneficiary_logs is mutated in place
        # by initiate_bank_transfer() regardless of whether it raises, so
        # a beneficiary lookup/creation failure still leaves a trail.
        for entry in beneficiary_logs:
            CashfreeApiLog.objects.create(
                bank_details=bank_details,
                call_type=entry["call_type"],
                http_status=entry["http_status"],
                request_payload=entry["request_payload"],
                response_payload=entry["response_payload"],
            )

    if not result["resolved"]:
        drop_status = CompanyBankVerification.DropStatus.PENDING
    elif result["success"]:
        drop_status = CompanyBankVerification.DropStatus.SUCCESS
    else:
        drop_status = CompanyBankVerification.DropStatus.FAILED

    attempt = CompanyBankVerification.objects.create(
        bank_details=bank_details,
        dropped_amount=amount,
        drop_status=drop_status,
        cashfree_reference_id=result["transfer_id"],
    )
    CashfreeApiLog.objects.create(
        bank_details=bank_details,
        verification=attempt,
        call_type=CashfreeApiLog.CallType.REQUEST_TRANSFER,
        transfer_id=result["transfer_id"],
        http_status=result["http_status"],
        request_payload=result["request_payload"],
        response_payload=result["response_payload"],
    )
    # Only when Cashfree's transfer status is RECEIVED/PENDING/SUCCESS
    # (drop_status PENDING or SUCCESS) -- not when it's already come back
    # FAILED, since nothing is actually "in progress" in that case and
    # the admin should see the FAILED state, not a stale PAYMENT_INITIATED.
    if drop_status != CompanyBankVerification.DropStatus.FAILED:
        bank_details.verification_status = CompanyBankDetails.VerificationStatus.PAYMENT_INITIATED
        bank_details.save(update_fields=["verification_status"])
    return attempt


def check_penny_drop_status(attempt: CompanyBankVerification) -> CompanyBankVerification:
    """
    Follow-up for a PENDING attempt -- asks Cashfree what actually
    happened and updates drop_status if it's resolved now. A no-op
    (returns the attempt unchanged) if it isn't PENDING, or if Cashfree
    still hasn't resolved it.
    """
    if attempt.drop_status != CompanyBankVerification.DropStatus.PENDING:
        return attempt
    result = get_transfer_status(attempt.cashfree_reference_id)
    CashfreeApiLog.objects.create(
        bank_details=attempt.bank_details,
        verification=attempt,
        call_type=CashfreeApiLog.CallType.GET_TRANSFER_STATUS,
        transfer_id=attempt.cashfree_reference_id,
        http_status=result["http_status"],
        response_payload=result["response_payload"],
    )
    if result["resolved"]:
        attempt.drop_status = (
            CompanyBankVerification.DropStatus.SUCCESS
            if result["success"]
            else CompanyBankVerification.DropStatus.FAILED
        )
        attempt.save(update_fields=["drop_status"])
    return attempt


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
