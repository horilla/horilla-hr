"""
company_onboarding/models.py

Repeatable / child-table models for the Company Setup module. The core
singular compliance fields (legal_name, tax_country, pan, status, ...) live
directly on base.Company — see base/models.py — not here. Everything in
this file FKs back to base.Company (or to a model that does), one direction
only, matching how the `onboarding` app already FKs to employee.Employee /
recruitment.Candidate.

Architecture note — plain models.Manager(), not HorillaCompanyManager:
these models look like typical company-scoped child records (the usual
convention elsewhere in this codebase), but they aren't — they're Ventura
staff's own administrative records ABOUT client companies, edited by
Ventura Admin/HR who operate ACROSS company boundaries by design (that's
the entire point of this module: one Ventura Admin onboards many
different client companies). HorillaCompanyManager filters by the ACTING
USER's currently-selected company, which is exactly wrong here — it
would silently hide a company's own state registrations, POC contacts,
etc. from the very Ventura Admin editing that company, the moment their
own Employee record happens to have a company link. Confirmed by hitting
this directly: a test admin whose Employee was linked to any company got
every one of these child queries filtered to empty during Mark-as-Active,
even though the rows genuinely existed. base.Company itself uses the same
plain-manager pattern for the identical reason — it isn't scoped by a
tenant context either.
"""

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import Company
from employee.models import phone_validator
from horilla.models import HorillaModel, upload_path
from horilla_auth.models import HorillaUser

from company_onboarding.encryption import mask_value
from company_onboarding.model_fields import EncryptedCharField
from company_onboarding.validators import gstin_validator


class GSTStateConfig(HorillaModel):
    """
    DB-backed config table for India's GST state codes (previously a
    hardcoded list in gst_states.py) -- lets these be edited via Django
    admin without a code deploy. Seeded from the CBIC GST state code list
    by this app's migrations; `is_active` lets a state be retired from
    new selections without deleting it (and breaking existing
    CompanyStateRegistration rows that reference it).
    """

    code = models.CharField(max_length=2, unique=True, verbose_name=_("GST State Code"))
    name = models.CharField(max_length=100, verbose_name=_("State / UT Name"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    objects = models.Manager()

    class Meta:
        verbose_name = _("GST State")
        verbose_name_plural = _("GST States")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class CompanyStateRegistration(HorillaModel):
    """
    "Place of Work" — one row per Indian state the client operates in.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="state_registrations",
        verbose_name=_("Company"),
    )
    state = models.ForeignKey(
        GSTStateConfig,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="state_registrations",
        limit_choices_to={"is_active": True},
        verbose_name=_("State"),
    )
    gstin = models.CharField(
        max_length=15,
        null=True,
        blank=True,
        validators=[gstin_validator],
        verbose_name=_("GSTIN"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Place of Work / State Registration")
        verbose_name_plural = _("Places of Work / State Registrations")
        unique_together = ("company", "state")

    def __str__(self):
        return f"{self.company} — {self.state.name if self.state else '—'}"

    def clean(self):
        super().clean()
        if self.gstin and self.state and not self.gstin.startswith(self.state.code):
            raise ValidationError(
                {"gstin": _("GSTIN state code does not match the selected state.")}
            )


class CompanyPOCContact(HorillaModel):
    """
    Point-of-contact for a client company. One (at most) may be flagged as
    the payroll approver — see base.Company.require_payroll_signoff.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="poc_contacts",
        verbose_name=_("Company"),
    )
    designation = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_("Designation")
    )
    name = models.CharField(
        max_length=150, null=True, blank=True, verbose_name=_("Name")
    )
    email = models.EmailField(null=True, blank=True, verbose_name=_("Email"))
    mobile = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        validators=[phone_validator],
        verbose_name=_("Mobile"),
    )
    is_payroll_approver = models.BooleanField(
        default=False, verbose_name=_("Payroll Approver")
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Point of Contact")
        verbose_name_plural = _("Points of Contact")

    def __str__(self):
        return f"{self.name or _('Unnamed contact')} ({self.designation or '—'})"

    def clean(self):
        super().clean()
        if self.is_payroll_approver:
            existing = CompanyPOCContact.objects.filter(
                company=self.company, is_payroll_approver=True
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(
                    {
                        "is_payroll_approver": _(
                            "Only one point of contact can be the payroll "
                            "approver — unset the current one first."
                        )
                    }
                )


class CompanyBankDetails(HorillaModel):
    """
    Client bank account. Mirrors EmployeeBankDetails' shape
    (employee/models.py:1014).
    """

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        # Set as soon as a penny-drop transfer is actually sent to
        # Cashfree (see initiate_penny_drop()) -- distinct from PENDING
        # ("never attempted") so the UI can show "money is on its way,
        # awaiting confirmation" rather than "nothing has happened yet".
        PAYMENT_INITIATED = "PAYMENT_INITIATED", _("Payment Initiated")
        VERIFIED = "VERIFIED", _("Verified")
        FAILED = "FAILED", _("Failed")

    VERIFICATION_SENSITIVE_FIELDS = ("account_number", "bank_name", "ifsc_swift")

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="bank_details",
        verbose_name=_("Company"),
    )
    # Stored encrypted at rest (see company_onboarding/model_fields.py) --
    # DB column is wide enough for ciphertext; plain_max_length is the
    # real limit enforced on the form.
    account_number = EncryptedCharField(
        plain_max_length=50, null=True, blank=True, verbose_name=_("Account Number")
    )
    # Derived from account_number on every save() (below) -- never set
    # directly. Stored (not just computed on read) so displaying it never
    # requires decrypting the real number.
    masked_account_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Masked Account Number"),
    )
    bank_name = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_("Bank Name")
    )
    ifsc_swift = models.CharField(
        max_length=20, null=True, blank=True, verbose_name=_("IFSC / SWIFT Code")
    )
    currency = models.CharField(
        max_length=10, default="INR", verbose_name=_("Currency")
    )
    # Captured here (not looked up from a POC contact at verification
    # time) -- these are specifically who Cashfree should register as the
    # beneficiary for this account, which may not be any of the company's
    # points of contact.
    account_holder_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Account Holder Name"),
        help_text=_("Used as the Cashfree beneficiary name for bank verification."),
    )
    contact_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        validators=[phone_validator],
        verbose_name=_("Contact Number"),
        help_text=_("Used as the Cashfree beneficiary phone for bank verification."),
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        verbose_name=_("Verification Status"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Company Bank Details")
        verbose_name_plural = _("Company Bank Details")

    def __str__(self):
        return f"{self.company} — {self.bank_name or _('Bank details')}"

    def save(self, *args, **kwargs):
        self.masked_account_number = mask_value(self.account_number)
        if self.pk:
            previous = CompanyBankDetails.objects.filter(pk=self.pk).first()
            if previous and any(
                getattr(previous, field) != getattr(self, field)
                for field in self.VERIFICATION_SENSITIVE_FIELDS
            ):
                # Editing the account-identifying fields un-verifies it —
                # back to Pending (not Failed — nothing was actually
                # attempted and failed here, it's just unverified again).
                self.verification_status = self.VerificationStatus.PENDING
        super().save(*args, **kwargs)


class CompanyBankVerification(HorillaModel):
    """
    One row per penny-drop verification attempt, transferred for real via
    Cashfree Payouts V2 -- see
    company_onboarding/services/bank_verification.py /
    company_onboarding/services/cashfree_client.py.
    """

    class DropStatus(models.TextChoices):
        # Transfers V2 is async: a fresh attempt starts PENDING (Cashfree
        # has only acknowledged the request, not confirmed it landed) and
        # is resolved to SUCCESS/FAILED later via a status check.
        PENDING = "PENDING", _("Pending")
        SUCCESS = "SUCCESS", _("Success")
        FAILED = "FAILED", _("Failed")

    bank_details = models.ForeignKey(
        CompanyBankDetails,
        on_delete=models.CASCADE,
        related_name="verifications",
        verbose_name=_("Bank Details"),
    )
    dropped_amount = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        verbose_name=_("Dropped Amount (₹)"),
    )
    drop_status = models.CharField(
        max_length=10,
        choices=DropStatus.choices,
        verbose_name=_("Drop Status"),
    )
    cashfree_reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Cashfree Reference ID"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Bank Verification Attempt")
        verbose_name_plural = _("Bank Verification Attempts")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bank_details} — ₹{self.dropped_amount} ({self.drop_status})"


class CashfreeApiLog(HorillaModel):
    """
    Raw request/response audit trail for every Cashfree API call made
    during bank verification. CompanyBankVerification only stores the
    distilled final outcome (amount, SUCCESS/FAILED/PENDING, one
    reference id) -- this is the full record for debugging a specific
    call, including ones that never produce a CompanyBankVerification row
    at all (e.g. an instant verification that fails before any transfer
    is attempted).
    """

    class CallType(models.TextChoices):
        VERIFY_BANK_ACCOUNT = "VERIFY_BANK_ACCOUNT", _("Verify Bank Account")
        GET_BENEFICIARY = "GET_BENEFICIARY", _("Get Beneficiary")
        CREATE_BENEFICIARY = "CREATE_BENEFICIARY", _("Create Beneficiary")
        REQUEST_TRANSFER = "REQUEST_TRANSFER", _("Request Transfer")
        GET_TRANSFER_STATUS = "GET_TRANSFER_STATUS", _("Get Transfer Status")

    bank_details = models.ForeignKey(
        CompanyBankDetails,
        on_delete=models.CASCADE,
        related_name="cashfree_logs",
        verbose_name=_("Bank Details"),
    )
    verification = models.ForeignKey(
        CompanyBankVerification,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cashfree_logs",
        verbose_name=_("Verification Attempt"),
    )
    call_type = models.CharField(
        max_length=30, choices=CallType.choices, verbose_name=_("Call Type")
    )
    transfer_id = models.CharField(
        max_length=50, null=True, blank=True, verbose_name=_("Transfer ID")
    )
    http_status = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("HTTP Status")
    )
    request_payload = models.JSONField(
        null=True, blank=True, verbose_name=_("Request Payload")
    )
    response_payload = models.JSONField(
        null=True, blank=True, verbose_name=_("Response Payload")
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Cashfree API Log")
        verbose_name_plural = _("Cashfree API Logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_call_type_display()} — {self.bank_details} ({self.created_at})"


class CompanyContract(HorillaModel):
    """
    MSA / commercial contract. Mirrors payroll.Contract's one-active-at-a-time
    pattern (payroll/models/models.py:155) — old contracts are terminated,
    never deleted, so contract history stays visible for audit.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        TERMINATED = "TERMINATED", _("Terminated")

    class BillingModel(models.TextChoices):
        MANAGEMENT_FEE = "MANAGEMENT_FEE", _("% Management Fee")
        PER_HEAD = "PER_HEAD", _("Per-Head Fee")

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="contracts",
        verbose_name=_("Company"),
    )
    msa_reference_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_("MSA Reference Number"),
    )
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Start Date"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("End Date"))
    msa_document = models.FileField(
        upload_to=upload_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(["pdf"])],
        verbose_name=_("MSA Document"),
    )
    billing_model = models.CharField(
        max_length=20,
        choices=BillingModel.choices,
        null=True,
        blank=True,
        verbose_name=_("Billing Model"),
    )
    billing_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Billing Value"),
        help_text=_(
            "The rate for the selected Billing Model — a percentage "
            "(0-100) for % Management Fee, or a per-head currency amount "
            "for Per-Head Fee."
        ),
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name=_("Status"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("MSA / Contract")
        verbose_name_plural = _("MSA / Contracts")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.msa_reference_number or _('Draft contract')} ({self.get_status_display()})"

    MAX_MSA_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB

    def clean(self):
        super().clean()
        # Normalize "" -> None BEFORE validate_unique() runs (full_clean()
        # calls clean_fields() -> clean() -> validate_unique(), in that
        # order). A plain unique=True tolerates multiple NULLs in Postgres,
        # but a form-submitted blank CharField saves "" (Django's default
        # empty_value), not None — so two draft contracts left blank would
        # otherwise collide with each other on "" instead of correctly
        # being treated as "not set yet".
        if self.msa_reference_number == "":
            self.msa_reference_number = None
        if self.msa_document and self.msa_document.size > self.MAX_MSA_DOCUMENT_SIZE:
            raise ValidationError(
                {"msa_document": _("MSA document must be 10MB or smaller.")}
            )
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("End date must be after start date.")})
        if (
            self.billing_model == self.BillingModel.MANAGEMENT_FEE
            and self.billing_value is not None
            and not (0 <= self.billing_value <= 100)
        ):
            raise ValidationError(
                {"billing_value": _("% Management Fee must be between 0 and 100.")}
            )
        if (
            self.billing_model == self.BillingModel.PER_HEAD
            and self.billing_value is not None
            and self.billing_value < 0
        ):
            raise ValidationError(
                {"billing_value": _("Per-Head Fee cannot be negative.")}
            )
        if self.status == self.Status.ACTIVE:
            duplicate = (
                CompanyContract.objects.filter(
                    company=self.company, status=self.Status.ACTIVE
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "An active MSA already exists for this company. "
                        "Terminate it before adding a new one."
                    )
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CompanySignatory(HorillaModel):
    """
    Authorized signatory. `signatory_type` is a TextChoices enum (plain
    VARCHAR underneath) specifically so a future 3rd type is a one-line
    code change, no migration — per the PRD's explicit "built to be
    extensible for additional signatory types later" note.
    """

    class SignatoryType(models.TextChoices):
        VENTURA = "VENTURA", _("Ventura")
        CLIENT = "CLIENT", _("Client")

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="signatories",
        verbose_name=_("Company"),
    )
    signatory_type = models.CharField(
        max_length=20,
        choices=SignatoryType.choices,
        verbose_name=_("Signatory Type"),
    )
    name = models.CharField(
        max_length=150, null=True, blank=True, verbose_name=_("Name")
    )
    designation = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_("Designation")
    )
    email = models.EmailField(null=True, blank=True, verbose_name=_("Email"))
    is_enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))

    objects = models.Manager()

    class Meta:
        verbose_name = _("Authorized Signatory")
        verbose_name_plural = _("Authorized Signatories")

    def __str__(self):
        return f"{self.name or _('Unnamed')} — {self.get_signatory_type_display()}"


class CompanyBrandedTemplate(HorillaModel):
    """
    Client-branded document templates (Offer Letter / Payslip / Form 16).
    Uploading a new file for a template_type replaces the current one.
    """

    class TemplateType(models.TextChoices):
        OFFER_LETTER = "OFFER_LETTER", _("Offer Letter")
        PAYSLIP = "PAYSLIP", _("Payslip")
        FORM16 = "FORM16", _("Form 16")

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="branded_templates",
        verbose_name=_("Company"),
    )
    template_type = models.CharField(
        max_length=20,
        choices=TemplateType.choices,
        verbose_name=_("Template Type"),
    )
    file = models.FileField(upload_to=upload_path, verbose_name=_("File"))

    objects = models.Manager()

    class Meta:
        verbose_name = _("Client-Branded Template")
        verbose_name_plural = _("Client-Branded Templates")
        unique_together = ("company", "template_type")

    def __str__(self):
        return f"{self.company} — {self.get_template_type_display()}"


class CompanyDocument(HorillaModel):
    """
    Free-form tagged document upload — no fixed tag list, the Admin types
    the tag at upload time.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("Company"),
    )
    tag_name = models.CharField(max_length=100, verbose_name=_("Document Tag"))
    file = models.FileField(upload_to=upload_path, verbose_name=_("File"))

    objects = models.Manager()

    class Meta:
        verbose_name = _("Company Document")
        verbose_name_plural = _("Company Documents")

    def __str__(self):
        return f"{self.company} — {self.tag_name}"


class CompanyDeactivationRecord(HorillaModel):
    """
    One row per deactivation event — never overwritten, so a client's full
    deactivate/reinstate history stays visible across its lifetime.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="deactivation_records",
        verbose_name=_("Company"),
    )
    reason = models.TextField(verbose_name=_("Reason"))
    invoices_reconciled = models.BooleanField(default=False)
    advances_collected = models.BooleanField(default=False)
    employees_transferred_or_terminated = models.BooleanField(default=False)
    compliances_closed = models.BooleanField(default=False)
    employees_removed_from_insurance = models.BooleanField(default=False)
    employees_deactivated_from_hrms = models.BooleanField(default=False)
    data_handed_over = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(
        HorillaUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("Confirmed By"),
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        verbose_name = _("Deactivation Record")
        verbose_name_plural = _("Deactivation Records")
        ordering = ["-confirmed_at"]

    def __str__(self):
        return f"{self.company} deactivated {self.confirmed_at:%Y-%m-%d}"

    CHECKLIST_FIELDS = (
        "invoices_reconciled",
        "advances_collected",
        "employees_transferred_or_terminated",
        "compliances_closed",
        "employees_removed_from_insurance",
        "employees_deactivated_from_hrms",
        "data_handed_over",
    )

    def checklist_complete(self) -> bool:
        return all(getattr(self, field) for field in self.CHECKLIST_FIELDS)
