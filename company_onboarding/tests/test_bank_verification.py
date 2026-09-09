from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from horilla.testkit import make_company

from company_onboarding.models import CompanyBankDetails
from company_onboarding.services.bank_verification import (
    check_penny_drop_status,
    confirm_penny_drop,
    initiate_penny_drop,
)
from company_onboarding.services.cashfree_client import CashfreePayoutError

_VALID_ACCOUNT = {
    "valid": True,
    "account_status": "VALID",
    "name_at_bank": "Test Bank Co",
    "name_match_result": "GOOD_MATCH",
    "message": "",
    "http_status": 200,
    "request_payload": {"bank_account": "1234567890", "ifsc": "TEST0001234"},
    "response_payload": {"account_status": "VALID"},
}
_INVALID_ACCOUNT = {
    "valid": False,
    "account_status": "INVALID",
    "name_at_bank": "",
    "name_match_result": "",
    "message": "ACCOUNT_IS_INVALID",
    "http_status": 200,
    "request_payload": {"bank_account": "1234567890", "ifsc": "TEST0001234"},
    "response_payload": {"account_status": "INVALID"},
}
_RESOLVED_SUCCESS_TRANSFER = {
    "transfer_id": "pdtest123",
    "resolved": True,
    "success": True,
    "message": "",
    "http_status": 200,
    "request_payload": {"transfer_id": "pdtest123"},
    "response_payload": {"status": "SUCCESS"},
}
_RESOLVED_FAILED_TRANSFER = {
    "transfer_id": "pdtest456",
    "resolved": True,
    "success": False,
    "message": "BENEFICIARY_BANK_OFFLINE",
    "http_status": 200,
    "request_payload": {"transfer_id": "pdtest456"},
    "response_payload": {"status": "FAILED"},
}
_UNRESOLVED_TRANSFER = {
    "transfer_id": "pdtest789",
    "resolved": False,
    "success": None,
    "message": "",
    "http_status": 200,
    "request_payload": {"transfer_id": "pdtest789"},
    "response_payload": {"status": "RECEIVED"},
}

# Every test here mocks these two -- both are real Cashfree calls (one a
# real money transfer), never something a unit test should invoke for real.
_VERIFY_TARGET = "company_onboarding.services.bank_verification.verify_bank_account"
_TRANSFER_TARGET = "company_onboarding.services.bank_verification.initiate_bank_transfer"
_STATUS_TARGET = "company_onboarding.services.bank_verification.get_transfer_status"


class PennyDropServiceTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.bank_details = CompanyBankDetails.objects.create(
            company=self.company,
            account_number="1234567890",
            bank_name="Test Bank",
            ifsc_swift="TEST0001234",
            account_holder_name="Jane Doe",
            contact_number="9999999999",
        )

    def test_new_bank_details_start_pending(self):
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_creates_attempt_in_valid_range(self, mock_verify, mock_transfer):
        # Cashfree's Payouts API requires amount >= 1.00, so the range
        # starts at 1.00, not 0.01 the way the old local-only stub did.
        attempt = initiate_penny_drop(self.bank_details)
        self.assertGreaterEqual(attempt.dropped_amount, Decimal("1.00"))
        self.assertLess(attempt.dropped_amount, Decimal("2.00"))
        self.assertEqual(attempt.drop_status, "SUCCESS")
        self.assertEqual(attempt.cashfree_reference_id, "pdtest123")
        mock_verify.assert_called_once()
        mock_transfer.assert_called_once()

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_passes_account_and_beneficiary_details(self, mock_verify, mock_transfer):
        initiate_penny_drop(self.bank_details)
        _, kwargs = mock_transfer.call_args
        self.assertEqual(kwargs["account_number"], "1234567890")
        self.assertEqual(kwargs["ifsc"], "TEST0001234")
        self.assertEqual(kwargs["company_id"], self.company.pk)
        # Beneficiary name/phone come from bank_details, not a POC contact.
        self.assertEqual(kwargs["beneficiary_name"], "Jane Doe")
        self.assertEqual(kwargs["beneficiary_phone"], "9999999999")

        verify_kwargs = mock_verify.call_args.kwargs
        self.assertEqual(verify_kwargs["name"], "Jane Doe")
        self.assertEqual(verify_kwargs["phone"], "9999999999")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_marks_bank_details_payment_initiated(self, mock_verify, mock_transfer):
        initiate_penny_drop(self.bank_details)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PAYMENT_INITIATED")

    @patch(_TRANSFER_TARGET, return_value=_UNRESOLVED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_marks_payment_initiated_even_when_transfer_stays_pending(
        self, mock_verify, mock_transfer
    ):
        initiate_penny_drop(self.bank_details)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PAYMENT_INITIATED")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_FAILED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_records_a_declined_transfer_as_failed_not_an_exception(
        self, mock_verify, mock_transfer
    ):
        attempt = initiate_penny_drop(self.bank_details)
        self.assertEqual(attempt.drop_status, "FAILED")
        self.assertEqual(attempt.cashfree_reference_id, "pdtest456")
        # Nothing is actually "in progress" for an outright-declined
        # transfer -- verification_status should NOT move to
        # PAYMENT_INITIATED, it should stay at its prior value.
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    @patch(_TRANSFER_TARGET, return_value=_UNRESOLVED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_records_an_unresolved_transfer_as_pending(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)
        self.assertEqual(attempt.drop_status, "PENDING")
        self.assertEqual(attempt.cashfree_reference_id, "pdtest789")

    @patch(_TRANSFER_TARGET)
    @patch(_VERIFY_TARGET, return_value=_INVALID_ACCOUNT)
    def test_initiate_raises_before_transferring_when_account_fails_verification(
        self, mock_verify, mock_transfer
    ):
        with self.assertRaises(CashfreePayoutError):
            initiate_penny_drop(self.bank_details)
        mock_transfer.assert_not_called()

    def test_initiate_without_account_holder_name_raises_before_calling_cashfree(self):
        self.bank_details.account_holder_name = ""
        self.bank_details.save()
        with patch(_VERIFY_TARGET) as mock_verify, patch(_TRANSFER_TARGET) as mock_transfer:
            with self.assertRaises(CashfreePayoutError):
                initiate_penny_drop(self.bank_details)
            mock_verify.assert_not_called()
            mock_transfer.assert_not_called()

    def test_initiate_without_contact_number_raises_before_calling_cashfree(self):
        self.bank_details.contact_number = ""
        self.bank_details.save()
        with patch(_VERIFY_TARGET) as mock_verify, patch(_TRANSFER_TARGET) as mock_transfer:
            with self.assertRaises(CashfreePayoutError):
                initiate_penny_drop(self.bank_details)
            mock_verify.assert_not_called()
            mock_transfer.assert_not_called()

    @patch(_STATUS_TARGET, return_value={"resolved": True, "success": True, "reference_id": "pdtest789", "message": "", "http_status": 200, "response_payload": {"status": "SUCCESS"}})
    @patch(_TRANSFER_TARGET, return_value=_UNRESOLVED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_check_status_resolves_a_pending_attempt(self, mock_verify, mock_transfer, mock_status):
        attempt = initiate_penny_drop(self.bank_details)
        self.assertEqual(attempt.drop_status, "PENDING")

        resolved = check_penny_drop_status(attempt)
        self.assertEqual(resolved.drop_status, "SUCCESS")
        attempt.refresh_from_db()
        self.assertEqual(attempt.drop_status, "SUCCESS")

    @patch(_STATUS_TARGET, return_value={"resolved": False, "success": None, "reference_id": "pdtest789", "message": "", "http_status": 200, "response_payload": {"status": "RECEIVED"}})
    @patch(_TRANSFER_TARGET, return_value=_UNRESOLVED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_check_status_leaves_a_still_unresolved_attempt_pending(
        self, mock_verify, mock_transfer, mock_status
    ):
        attempt = initiate_penny_drop(self.bank_details)
        resolved = check_penny_drop_status(attempt)
        self.assertEqual(resolved.drop_status, "PENDING")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_check_status_is_a_noop_for_an_already_resolved_attempt(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)
        with patch(_STATUS_TARGET) as mock_status:
            check_penny_drop_status(attempt)
            mock_status.assert_not_called()

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_confirm_correct_amount_verifies_and_does_not_persist_guess(
        self, mock_verify, mock_transfer
    ):
        attempt = initiate_penny_drop(self.bank_details)
        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "VERIFIED")
        # entered_amount is never persisted anywhere on the attempt itself —
        # only the outcome, on CompanyBankDetails.verification_status.
        self.assertFalse(hasattr(attempt, "entered_amount"))

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_confirm_wrong_amount_marks_failed(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("1.01")
        matched = confirm_penny_drop(attempt, wrong)
        self.assertFalse(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "FAILED")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_failed_attempt_can_still_be_verified_afterward(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("1.01")
        confirm_penny_drop(attempt, wrong)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "FAILED")

        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "VERIFIED")

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_resubmitting_after_mismatch_is_never_blocked(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("1.01")
        confirm_penny_drop(attempt, wrong)
        confirm_penny_drop(attempt, wrong)  # no cap — should not raise
        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_reinitiating_creates_new_attempt_without_deleting_old(self, mock_verify, mock_transfer):
        first = initiate_penny_drop(self.bank_details)
        second = initiate_penny_drop(self.bank_details)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.bank_details.verifications.count(), 2)


class AccountNumberEncryptionTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.bank_details = CompanyBankDetails.objects.create(
            company=self.company,
            account_number="1234567890",
            bank_name="Test Bank",
            ifsc_swift="TEST0001234",
        )

    def test_account_number_stored_encrypted_at_rest(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_number FROM company_onboarding_companybankdetails "
                "WHERE id = %s",
                [self.bank_details.pk],
            )
            raw_value = cursor.fetchone()[0]
        self.assertNotEqual(raw_value, "1234567890")

    def test_account_number_round_trips_through_the_orm(self):
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.account_number, "1234567890")

    def test_masked_account_number_shows_only_last_four_digits(self):
        self.assertEqual(self.bank_details.masked_account_number, "XXXXXX7890")

    def test_masked_account_number_blank_when_saved_without_account_number(self):
        blank = CompanyBankDetails.objects.create(
            company=make_company("No Bank Co", address="2 X St")
        )
        self.assertEqual(blank.masked_account_number, "")

    def test_masked_account_number_is_persisted_in_the_db(self):
        # Not computed on read -- a fresh query should already have it,
        # with no decryption needed to display it.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT masked_account_number FROM company_onboarding_companybankdetails "
                "WHERE id = %s",
                [self.bank_details.pk],
            )
            stored_value = cursor.fetchone()[0]
        self.assertEqual(stored_value, "XXXXXX7890")

    def test_masked_account_number_updates_when_account_number_changes(self):
        self.bank_details.account_number = "555555555555"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.masked_account_number, "XXXXXXXX5555")


class BankDetailsReverificationTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.bank_details = CompanyBankDetails.objects.create(
            company=self.company,
            account_number="1234567890",
            bank_name="Test Bank",
            ifsc_swift="TEST0001234",
            verification_status=CompanyBankDetails.VerificationStatus.VERIFIED,
        )

    def test_changing_account_number_resets_to_pending(self):
        self.bank_details.account_number = "0987654321"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    def test_changing_bank_name_resets_to_pending(self):
        self.bank_details.bank_name = "New Bank"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    def test_changing_ifsc_resets_to_pending(self):
        self.bank_details.ifsc_swift = "OTHER0005678"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    def test_changing_currency_alone_does_not_reset_verification(self):
        self.bank_details.currency = "USD"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "VERIFIED")

    def test_editing_a_failed_verification_also_resets_to_pending(self):
        self.bank_details.verification_status = CompanyBankDetails.VerificationStatus.FAILED
        self.bank_details.save()
        self.bank_details.account_number = "0987654321"
        self.bank_details.save()
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "PENDING")


class CashfreeApiLogTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.bank_details = CompanyBankDetails.objects.create(
            company=self.company,
            account_number="1234567890",
            bank_name="Test Bank",
            ifsc_swift="TEST0001234",
            account_holder_name="Jane Doe",
            contact_number="9999999999",
        )

    @patch(_TRANSFER_TARGET, return_value=_RESOLVED_SUCCESS_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_initiate_logs_both_calls_with_raw_payloads(self, mock_verify, mock_transfer):
        attempt = initiate_penny_drop(self.bank_details)

        logs = list(self.bank_details.cashfree_logs.order_by("created_at"))
        self.assertEqual(len(logs), 2)

        verify_log, transfer_log = logs
        self.assertEqual(verify_log.call_type, "VERIFY_BANK_ACCOUNT")
        self.assertIsNone(verify_log.verification)
        self.assertEqual(verify_log.http_status, 200)
        self.assertEqual(verify_log.response_payload, {"account_status": "VALID"})

        self.assertEqual(transfer_log.call_type, "REQUEST_TRANSFER")
        self.assertEqual(transfer_log.verification_id, attempt.pk)
        self.assertEqual(transfer_log.transfer_id, "pdtest123")
        self.assertEqual(transfer_log.response_payload, {"status": "SUCCESS"})

    @patch(_TRANSFER_TARGET)
    @patch(_VERIFY_TARGET, return_value=_INVALID_ACCOUNT)
    def test_a_failed_verification_is_still_logged_even_though_it_blocks_the_transfer(
        self, mock_verify, mock_transfer
    ):
        with self.assertRaises(CashfreePayoutError):
            initiate_penny_drop(self.bank_details)

        logs = list(self.bank_details.cashfree_logs.all())
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].call_type, "VERIFY_BANK_ACCOUNT")
        self.assertEqual(logs[0].response_payload, {"account_status": "INVALID"})

    @patch(_STATUS_TARGET, return_value={"resolved": True, "success": True, "reference_id": "pdtest789", "message": "", "http_status": 200, "response_payload": {"status": "SUCCESS"}})
    @patch(_TRANSFER_TARGET, return_value=_UNRESOLVED_TRANSFER)
    @patch(_VERIFY_TARGET, return_value=_VALID_ACCOUNT)
    def test_check_status_adds_a_third_log_entry(self, mock_verify, mock_transfer, mock_status):
        attempt = initiate_penny_drop(self.bank_details)
        check_penny_drop_status(attempt)

        logs = list(self.bank_details.cashfree_logs.order_by("created_at"))
        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[2].call_type, "GET_TRANSFER_STATUS")
        self.assertEqual(logs[2].verification_id, attempt.pk)
