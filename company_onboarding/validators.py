"""
company_onboarding/validators.py

Structured-ID format validators for the Company Setup module, mirroring the
module-level RegexValidator convention already used for phone numbers
(employee.models.phone_validator).
"""

from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

pan_validator = RegexValidator(
    regex=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
    message=_("Enter a valid PAN (format: AAAAA9999A)."),
)

gstin_validator = RegexValidator(
    regex=r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$",
    message=_("Enter a valid 15-character GSTIN."),
)
