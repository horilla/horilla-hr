"""
Forms for handling payroll-related operations.

This module provides Django ModelForms for creating and managing payroll-related data,
including filing status, tax brackets, and federal tax records.

The forms in this module inherit from the Django `forms.ModelForm` class and customize
the widget attributes to enhance the user interface and provide a better user experience.

"""

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from payroll.methods import federal_tax
from payroll.methods.safe_tax_code import TaxCodeValidationError, validate_tax_code
from payroll.models.models import FilingStatus
from payroll.models.tax_models import TaxBracket


class FilingStatusForm(ModelForm):
    """Form for creating and updating filing status."""

    cols = {
        "filing_status": 12,
        "based_on": 12,
        "description": 12,
    }

    class Meta:
        """Meta options for the form."""

        model = FilingStatus
        # Identity only. The rules — slabs, adjustments, formula — are edited on
        # the filing status' own page, which has room for a grid, validation and
        # a preview. A code editor never fitted this modal anyway: the generic
        # form template owns the <form> and its Save buttons, so anything
        # appended after it rendered outside the form and spilled below the
        # dialog.
        fields = ["filing_status", "based_on", "use_py", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # use_py stays on the form for the life of the record. It used to be
        # deleted whenever self.instance.pk was set, which made the choice
        # between bracket mode and Python mode a one-way door fixed at creation:
        # the only way to change it afterwards was to delete the filing status,
        # and Contract.filing_status PROTECTs it, so that first meant
        # re-pointing every contract using it.
        self.fields["use_py"].label = _("Use a Python formula")
        self.fields["use_py"].help_text = _(
            "Leave this off to use tax slabs, which is what most tax systems "
            "need. Either way, the rules themselves are edited on this filing "
            "status' own page after saving."
        )

    def save(self, commit=True):
        """
        Seed the starter formula when a record is first created in Python mode.

        python_code is not on this form, so a new Python-mode filing status
        would otherwise be saved with nothing to run — the exact state that
        used to tax everyone on it at 0. The dedicated editor replaces this
        template the moment anyone opens it.
        """
        instance = super().save(commit=False)
        if instance.use_py and not (instance.python_code or "").strip():
            instance.python_code = federal_tax.CODE
        if commit:
            instance.save()
        return instance


class FilingStatusTaxRulesForm(ModelForm):
    """
    The declarative half of a filing status, edited on its own page.

    Kept separate from FilingStatusForm because these are the *rules*, not the
    identity: name and description belong in a quick create modal, while slabs,
    adjustments and a formula need room, validation and a preview beside them.
    """

    cols = {
        "standard_deduction": 6,
        "rebate_income_limit": 6,
        "rebate_max_amount": 6,
        "cess_percent": 6,
    }

    class Meta:
        model = FilingStatus
        fields = [
            "standard_deduction",
            "rebate_income_limit",
            "rebate_max_amount",
            "cess_percent",
            "python_code",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["python_code"].required = False
        if self.instance.pk and not (self.instance.python_code or "").strip():
            self.initial["python_code"] = federal_tax.CODE

    def clean(self):
        cleaned = super().clean()
        rebate_limit = cleaned.get("rebate_income_limit")
        rebate_max = cleaned.get("rebate_max_amount")
        # Half a rebate silently does nothing, which is worse than refusing it:
        # the admin believes relief is configured and the payslip disagrees.
        if rebate_limit is not None and rebate_max is None:
            self.add_error(
                "rebate_max_amount",
                _("Set the maximum rebate, or clear the income limit."),
            )
        if rebate_max is not None and rebate_limit is None:
            self.add_error(
                "rebate_income_limit",
                _("Set the income limit, or clear the maximum rebate."),
            )
        return cleaned

    def clean_python_code(self):
        """Reject tax code that violates the sandbox policy at save time."""
        code = self.cleaned_data.get("python_code")
        if not self.instance.use_py:
            return code
        # Refuse to store the combination that silently taxed everyone on this
        # filing status at 0: Python mode on with nothing to run.
        if not (code or "").strip():
            raise forms.ValidationError(
                _(
                    "Python mode is enabled but there is no code to run. Enter a "
                    "calculate_federal_tax(yearly_income) function, or switch this "
                    "filing status to tax slabs."
                )
            )
        if code != federal_tax.CODE:
            try:
                validate_tax_code(code)
            except TaxCodeValidationError as exc:
                raise forms.ValidationError(str(exc)) from exc
        return code


class TaxBracketForm(ModelForm):
    """Form for creating and updating tax bracket."""

    cols = {"min_income": 12, "max_income": 12, "tax_rate": 12}

    class Meta:
        """Meta options for the form."""

        model = TaxBracket
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "filing_status_id": forms.HiddenInput(),
        }


class BaseTaxBracketFormSet(forms.BaseInlineFormSet):
    """
    Validates the slab table as a whole.

    TaxBracket.clean() checks one row against an *unordered* queryset and takes
    .first() of whatever matches, so overlaps slip through non-deterministically
    and nothing ever notices a gap. A slab table is only meaningful as a set:
    it has to start at zero, not overlap, and not leave holes income can fall
    into — a hole silently under-taxes, because the engine stops walking the
    brackets at the first one that does not apply.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        rows = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            low = form.cleaned_data.get("min_income")
            high = form.cleaned_data.get("max_income")
            if low is None:
                continue
            rows.append((float(low), None if high is None else float(high), form))

        if not rows:
            return

        rows.sort(key=lambda row: row[0])

        if rows[0][0] != 0:
            rows[0][2].add_error("min_income", _("The first slab must start at 0."))

        for (low, high, form), (next_low, _next_high, next_form) in zip(rows, rows[1:]):
            if high is None:
                form.add_error(
                    "max_income",
                    _("Only the highest slab may be left open-ended."),
                )
                continue
            if high > next_low:
                next_form.add_error(
                    "min_income",
                    _("This slab overlaps the one ending at %(end)s.") % {"end": high},
                )
            elif high < next_low:
                next_form.add_error(
                    "min_income",
                    _(
                        "Income between %(gap_start)s and %(gap_end)s falls in no "
                        "slab. Start this one at %(gap_start)s."
                    )
                    % {"gap_start": high, "gap_end": next_low},
                )


TaxBracketFormSet = forms.inlineformset_factory(
    FilingStatus,
    TaxBracket,
    form=TaxBracketForm,
    formset=BaseTaxBracketFormSet,
    fields=["min_income", "max_income", "tax_rate"],
    extra=1,
    can_delete=True,
)
