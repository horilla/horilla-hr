from decimal import Decimal

from django.test import TestCase

from horilla.testkit import make_company

from company_onboarding.models import CompanyBankDetails
from company_onboarding.services.bank_verification import (
    confirm_penny_drop,
    initiate_penny_drop,
)


class PennyDropServiceTests(TestCase):
    def setUp(self):
        self.company = make_company()
        self.bank_details = CompanyBankDetails.objects.create(
            company=self.company,
            account_number="1234567890",
            bank_name="Test Bank",
            ifsc_swift="TEST0001234",
        )

    def test_new_bank_details_start_pending(self):
        self.assertEqual(self.bank_details.verification_status, "PENDING")

    def test_initiate_creates_attempt_in_valid_range(self):
        attempt = initiate_penny_drop(self.bank_details)
        self.assertGreaterEqual(attempt.dropped_amount, Decimal("0.01"))
        self.assertLess(attempt.dropped_amount, Decimal("2.00"))
        self.assertEqual(attempt.drop_status, "SUCCESS")

    def test_confirm_correct_amount_verifies_and_does_not_persist_guess(self):
        attempt = initiate_penny_drop(self.bank_details)
        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "VERIFIED")
        # entered_amount is never persisted anywhere on the attempt itself —
        # only the outcome, on CompanyBankDetails.verification_status.
        self.assertFalse(hasattr(attempt, "entered_amount"))

    def test_confirm_wrong_amount_marks_failed(self):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("0.01")
        matched = confirm_penny_drop(attempt, wrong)
        self.assertFalse(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "FAILED")

    def test_failed_attempt_can_still_be_verified_afterward(self):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("0.01")
        confirm_penny_drop(attempt, wrong)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "FAILED")

        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)
        self.bank_details.refresh_from_db()
        self.assertEqual(self.bank_details.verification_status, "VERIFIED")

    def test_resubmitting_after_mismatch_is_never_blocked(self):
        attempt = initiate_penny_drop(self.bank_details)
        wrong = Decimal("1.99") if attempt.dropped_amount != Decimal("1.99") else Decimal("0.01")
        confirm_penny_drop(attempt, wrong)
        confirm_penny_drop(attempt, wrong)  # no cap — should not raise
        matched = confirm_penny_drop(attempt, attempt.dropped_amount)
        self.assertTrue(matched)

    def test_reinitiating_creates_new_attempt_without_deleting_old(self):
        first = initiate_penny_drop(self.bank_details)
        second = initiate_penny_drop(self.bank_details)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.bank_details.verifications.count(), 2)


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
