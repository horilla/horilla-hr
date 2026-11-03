"""
admin.py

Used to register models on admin site
"""

from django import forms
from django.contrib import admin

from payroll.methods.safe_tax_code import (
    PYTHON_FORMULAS_OFF_MESSAGE,
    TaxCodeValidationError,
    python_formulas_enabled,
    same_formula,
    validate_tax_code,
)
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    FilingStatus,
    LoanAccount,
    MultipleCondition,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    ReimbursementrequestComment,
)
from payroll.models.tax_models import PayrollSettings, TaxBracket


class FilingStatusAdminForm(forms.ModelForm):
    """
    The admin used to save any formula, with neither the opt-in setting nor
    the formula check. It now applies the same rules as the payroll pages:
    turning Python mode on, or new or edited code, needs
    HORILLA_ALLOW_PYTHON_TAX_FORMULAS, and code is always checked.
    """

    class Meta:
        model = FilingStatus
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        stored = self.instance if self.instance.pk else None
        code = cleaned.get("python_code")
        turning_on = cleaned.get("use_py") and not (stored and stored.use_py)
        code_changed = not same_formula(code, stored.python_code if stored else "")
        if not python_formulas_enabled() and (
            turning_on or (cleaned.get("use_py") and code_changed)
        ):
            raise forms.ValidationError(PYTHON_FORMULAS_OFF_MESSAGE)
        if cleaned.get("use_py") and code_changed and (code or "").strip():
            try:
                validate_tax_code(code)
            except TaxCodeValidationError as exc:
                self.add_error("python_code", str(exc))
        return cleaned


@admin.register(FilingStatus)
class FilingStatusAdmin(admin.ModelAdmin):
    form = FilingStatusAdminForm


# Register your models here.
admin.site.register(TaxBracket)
admin.site.register(Contract)
admin.site.register(Allowance)
admin.site.register(Deduction)
admin.site.register(Payslip)
admin.site.register(PayrollSettings)
admin.site.register(LoanAccount)
admin.site.register(Reimbursement)
admin.site.register(ReimbursementrequestComment)
admin.site.register(MultipleCondition)
admin.site.register(PayslipAutoGenerate)
