"""
company_onboarding/forms.py

Step 1 uses two separate ModelForms over the same Company instance:
CompanyIdentityForm (the "1.1" subset — always required, even on Draft) and
CompanyComplianceForm (everything else new on Company — relaxed on Draft,
strict on Next). Every form here takes a `strict=` kwarg toggling
`field.required`, which is how the wizard's Draft/Next/Back validation
tiers are implemented.
"""

from django import forms
from django.forms import ModelForm

from base.models import Company

from company_onboarding.models import (
    CompanyBankDetails,
    CompanyContract,
    CompanyPOCContact,
    CompanySignatory,
    CompanyStateRegistration,
)


class _WidgetStyleMixin:
    """
    Applies the app's standard oh-input/oh-select/oh-switch CSS classes to
    every field's widget, so plain ModelForms here render consistently with
    the rest of the app without every template having to know widget types.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = (existing + " oh-switch__checkbox").strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = (existing + " oh-select oh-select-2 w-100").strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = (existing + " oh-input w-100 oh-input--textarea").strip()
            else:
                widget.attrs["class"] = (existing + " oh-input w-100").strip()


class _StrictToggleMixin(_WidgetStyleMixin):
    """Shared `strict=` handling for every relaxed-on-Draft form below."""

    always_required_fields: tuple = ()

    def __init__(self, *args, strict=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._strict = strict
        if not strict:
            for name, field in self.fields.items():
                if name not in self.always_required_fields:
                    field.required = False


class CompanyIdentityForm(_WidgetStyleMixin, ModelForm):
    """
    1.1 Identity & Basic Info — the Draft-minimum subset. These fields stay
    required regardless of draft/strict, per the PRD's explicit exception.
    """

    cols = {"company": 6, "address": 6, "country": 6, "state": 6, "city": 6, "zip": 6, "icon": 12}

    class Meta:
        model = Company
        fields = ["company", "address", "country", "state", "city", "zip", "icon"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["icon"].required = False


class CompanyComplianceForm(_StrictToggleMixin, ModelForm):
    """
    1.2 Tax & Registration + 1.5 Contract&Billing's non-repeatable fields.

    require_payroll_signoff is deliberately NOT a field here — per the PRD
    it's a "2.2 Payroll Sign-off" concept, paired with the "Select
    Approver" dropdown that only exists in Step 2 (Step2View already
    handles it directly). Including it here would let Step 1 set it True
    without ever going through Step 2's "must have an approver" check.
    """

    cols = {
        "legal_name": 12,
        "tax_country": 6,
        "ldc_applied": 6,
        "pan": 6,
        "foreign_tax_id": 6,
        "invoice_cycle": 6,
        "payment_terms": 6,
    }

    class Meta:
        model = Company
        fields = [
            "legal_name",
            "tax_country",
            "ldc_applied",
            "pan",
            "foreign_tax_id",
            "invoice_cycle",
            "payment_terms",
        ]

    def clean(self):
        cleaned = super().clean()
        if self._strict:
            tax_country = cleaned.get("tax_country")
            if tax_country == "INDIA" and not cleaned.get("pan"):
                self.add_error("pan", "PAN is required for domestic clients.")
            elif tax_country == "FOREIGN" and not cleaned.get("foreign_tax_id"):
                self.add_error(
                    "foreign_tax_id",
                    "Foreign Tax ID is required for foreign clients.",
                )
        return cleaned


class CompanyBankDetailsForm(_StrictToggleMixin, ModelForm):
    cols = {
        "account_number": 6,
        "bank_name": 6,
        "ifsc_swift": 6,
        "currency": 6,
        "account_holder_name": 6,
        "contact_number": 6,
    }

    class Meta:
        model = CompanyBankDetails
        fields = [
            "account_number",
            "bank_name",
            "ifsc_swift",
            "currency",
            "account_holder_name",
            "contact_number",
        ]


class CompanyContractForm(_StrictToggleMixin, ModelForm):
    cols = {
        "msa_reference_number": 6,
        "start_date": 3,
        "end_date": 3,
        "billing_model": 6,
        "billing_value": 6,
        "msa_document": 6,
    }

    class Meta:
        model = CompanyContract
        fields = [
            "msa_reference_number",
            "start_date",
            "end_date",
            "billing_model",
            "billing_value",
            "msa_document",
        ]
        widgets = {
            # type="date" -> native browser calendar picker; HTML5 date
            # inputs always submit/display in yyyy-mm-dd regardless of the
            # user's locale, so no separate format= is needed.
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class StateRegistrationRowForm(_StrictToggleMixin, ModelForm):
    """
    GSTIN is explicitly soft/non-blocking even on the strict (Next/Active)
    tier per the PRD, so it's never in always_required_fields.
    """

    cols = {"state": 6, "gstin": 6}

    class Meta:
        model = CompanyStateRegistration
        fields = ["state", "gstin"]


class POCContactRowForm(_StrictToggleMixin, ModelForm):
    """
    is_payroll_approver is deliberately not a field here — the PRD sets it
    via Step 2's "Select Approver" dropdown (sourced from these contacts),
    not a per-row checkbox during Step 1 entry.
    """

    cols = {"designation": 3, "name": 3, "email": 3, "mobile": 3}

    class Meta:
        model = CompanyPOCContact
        fields = ["designation", "name", "email", "mobile"]


class SignatoryRowForm(_StrictToggleMixin, ModelForm):
    cols = {"signatory_type": 3, "name": 3, "designation": 3, "email": 3}

    class Meta:
        model = CompanySignatory
        fields = ["signatory_type", "name", "designation", "email", "is_enabled"]
