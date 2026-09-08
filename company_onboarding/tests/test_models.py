from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from horilla.testkit import CompanyFilterTestMixin, make_company

from company_onboarding.models import (
    CompanyContract,
    CompanyPOCContact,
    CompanyStateRegistration,
)


class CompanyContractTests(CompanyFilterTestMixin, TestCase):
    def setUp(self):
        self.company = make_company()

    def test_rejects_second_active_contract(self):
        CompanyContract.objects.create(
            company=self.company,
            msa_reference_number="MSA-1",
            start_date=date(2026, 1, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
            status=CompanyContract.Status.ACTIVE,
        )
        with self.assertRaises(ValidationError):
            CompanyContract.objects.create(
                company=self.company,
                msa_reference_number="MSA-2",
                start_date=date(2026, 2, 1),
                billing_model=CompanyContract.BillingModel.PER_HEAD,
                status=CompanyContract.Status.ACTIVE,
            )

    def test_allows_terminated_alongside_active(self):
        CompanyContract.objects.create(
            company=self.company,
            msa_reference_number="MSA-1",
            start_date=date(2026, 1, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
            status=CompanyContract.Status.TERMINATED,
        )
        # should not raise
        CompanyContract.objects.create(
            company=self.company,
            msa_reference_number="MSA-2",
            start_date=date(2026, 2, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
            status=CompanyContract.Status.ACTIVE,
        )

    def test_end_date_before_start_date_rejected(self):
        with self.assertRaises(ValidationError):
            CompanyContract.objects.create(
                company=self.company,
                msa_reference_number="MSA-1",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 1),
                billing_model=CompanyContract.BillingModel.PER_HEAD,
            )

    def test_msa_reference_number_unique_across_companies(self):
        other_company = make_company("Other Co", address="2 Other St")
        CompanyContract.objects.create(
            company=self.company,
            msa_reference_number="MSA-SHARED",
            start_date=date(2026, 1, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
        )
        with self.assertRaises(ValidationError):
            CompanyContract.objects.create(
                company=other_company,
                msa_reference_number="MSA-SHARED",
                start_date=date(2026, 1, 1),
                billing_model=CompanyContract.BillingModel.PER_HEAD,
                status=CompanyContract.Status.TERMINATED,
            )

    def test_blank_msa_reference_number_does_not_collide(self):
        other_company = make_company("Other Co", address="2 Other St")
        CompanyContract.objects.create(
            company=self.company,
            start_date=date(2026, 1, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
        )
        # A second contract with msa_reference_number left blank ("") must
        # normalize to None before the unique check, not collide with the
        # first blank one.
        CompanyContract.objects.create(
            company=other_company,
            msa_reference_number="",
            start_date=date(2026, 1, 1),
            billing_model=CompanyContract.BillingModel.PER_HEAD,
        )


class CompanyStateRegistrationTests(CompanyFilterTestMixin, TestCase):
    def setUp(self):
        self.company = make_company()

    def test_unique_together_company_state(self):
        CompanyStateRegistration.objects.create(company=self.company, state="27")
        with self.assertRaises(Exception):
            CompanyStateRegistration.objects.create(company=self.company, state="27")

    def test_mismatched_gstin_state_rejected(self):
        row = CompanyStateRegistration(
            company=self.company, state="27", gstin="07AAAAA0000A1Z5"
        )
        with self.assertRaises(ValidationError):
            row.full_clean()


class CompanyPOCContactTests(CompanyFilterTestMixin, TestCase):
    def setUp(self):
        self.company = make_company()

    def test_only_one_payroll_approver_per_company(self):
        CompanyPOCContact.objects.create(
            company=self.company, name="A", is_payroll_approver=True
        )
        second = CompanyPOCContact(
            company=self.company, name="B", is_payroll_approver=True
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_second_contact_without_approver_flag_is_fine(self):
        CompanyPOCContact.objects.create(
            company=self.company, name="A", is_payroll_approver=True
        )
        second = CompanyPOCContact(company=self.company, name="B")
        second.full_clean()  # should not raise
