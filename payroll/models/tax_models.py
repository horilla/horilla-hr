"""
tax_models.py

This module contains the models for the tax calculation of taxable income.
"""

import math

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from horilla.horilla_middlewares import _thread_locals, get_selected_company
from horilla.models import HorillaModel
from payroll.models.models import FilingStatus


class PayrollSettings(HorillaModel):
    """
    Payroll settings model
    """

    choices = [
        ("prefix", _("Prefix")),
        ("postfix", _("Suffix")),
    ]

    currency_symbol = models.CharField(null=True, default="$", max_length=5)
    position = models.CharField(
        max_length=15, null=True, choices=choices, default="postfix"
    )

    company_id = models.ForeignKey(Company, null=True, on_delete=models.PROTECT)
    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Payroll Settings")
        verbose_name_plural = _("Payroll Settings")

    def __str__(self):
        return f"Payroll Settings {self.currency_symbol}"

    @classmethod
    def for_selected_company(cls):
        """
        Return the selected company's settings, else the settings without a
        company, else any settings (None if there are none).

        HorillaCompanyManager also lets the row without a company through, so
        a bare .objects.first() returns whichever row has the lower id. That
        is usually the "$" row default_currency() creates on the very first
        page load, not the company's own row saved from the settings page.

        Remembered on the current request, per company: a payroll list formats
        every amount through the currency filter. Saving or deleting settings
        forgets it (payroll/signals.py).
        """
        request = _thread_locals.request
        company_id = get_selected_company()
        remembered = getattr(request, "_payroll_settings", None) or {}
        if company_id in remembered:
            return remembered[company_id]
        settings = None
        if company_id and company_id != "all":
            settings = cls.objects.filter(company_id=company_id).first()
        if settings is None:
            settings = cls.objects.filter(company_id__isnull=True).first()
        if settings is None:
            settings = cls.objects.first()
        if request is not None:
            request._payroll_settings = {**remembered, company_id: settings}
        return settings

    @classmethod
    def currency_for_selected_company(cls):
        """The selected company's currency symbol; "$" when none is set up."""
        settings = cls.for_selected_company()
        return (settings.currency_symbol if settings else None) or "$"

    @staticmethod
    def forget_remembered():
        """Drop the settings remembered on the current request."""
        request = _thread_locals.request
        if request is not None and hasattr(request, "_payroll_settings"):
            del request._payroll_settings


class TaxBracket(HorillaModel):
    """
    TaxBracket model
    """

    filing_status_id = models.ForeignKey(
        FilingStatus,
        on_delete=models.CASCADE,
        verbose_name=_("Filing status"),
    )
    min_income = models.FloatField(
        null=False, blank=False, verbose_name=_("Min. Income")
    )
    max_income = models.FloatField(null=True, blank=True, verbose_name=_("Max. Income"))
    tax_rate = models.FloatField(
        null=False, blank=False, default=0.0, verbose_name=_("Tax Rate")
    )
    objects = models.Manager()

    def __str__(self):
        if self.max_income != math.inf:
            return (
                f"{self.filing_status_id}"
                f"{self.tax_rate}% tax rate on "
                f"{self.min_income} and {self.max_income}"
            )
        return (
            f"{self.tax_rate}% tax rate on taxable income equal or above "
            f"{self.min_income} for {self.filing_status_id}"
        )

    def band_label(self):
        """
        The income range this slab covers, as one phrase.

        One column rather than a From and a To. Split across two, a range reads
        as two unrelated numbers with the page's width between them, which is
        what made a seven-slab table hard to follow.

        The open-ended top slab is stored as NULL by some tax packs and as
        float("inf") by others, and only the first was handled -- so the last
        row of a US table read "inf". Both mean the same thing and both say so.
        """
        top = self.max_income
        if top is None or top == math.inf:
            return _("%(floor)s and above") % {"floor": f"{self.min_income:,.0f}"}
        return f"{self.min_income:,.0f} – {top:,.0f}"

    def get_display_max_income(self):
        """
        Retrieves the maximum income.
        Returns:
            float or None: The maximum income if it is a finite value, otherwise None.
        """
        if self.max_income != math.inf:
            return self.max_income
        return None

    def get_update_url(self):
        """
        Returns the URL for updating the tax bracket.
        """

        return reverse("tax-bracket-update", kwargs={"pk": self.pk})

    def get_delete_url(self):
        """
        Returns the URL for updating the tax bracket.
        """

        return reverse("tax-bracket-delete", kwargs={"tax_bracket_id": self.pk})

    def clean(self):
        super().clean()

        existing_bracket = TaxBracket.objects.filter(
            filing_status_id=self.filing_status_id,
            min_income=self.min_income,
            max_income=self.max_income,
            tax_rate=self.tax_rate,
        ).exclude(pk=self.pk)
        if existing_bracket.exists():
            raise ValidationError(_("This tax bracket already exists"))

        # Open-ended is NULL, read as infinity but never written back as it.
        top = math.inf if self.max_income is None else self.max_income

        if self.min_income >= top:
            raise ValidationError(
                {"max_income": _("Maximum income must be greater than minimum income.")}
            )

        # The slab grid validates the whole table itself.
        if getattr(self, "_table_validated", False):
            return

        # Slabs that meet are fine; only a real overlap is refused.
        overlapping = TaxBracket.objects.filter(
            filing_status_id=self.filing_status_id
        ).exclude(pk=self.pk)
        overlapping = overlapping.filter(
            models.Q(max_income__isnull=True) | models.Q(max_income__gt=self.min_income)
        )
        if top != math.inf:
            overlapping = overlapping.filter(min_income__lt=top)
        tax_bracket = overlapping.first()
        if tax_bracket is not None:
            raise ValidationError(
                {
                    "min_income": format_lazy(
                        "This tax bracket overlaps {}.", tax_bracket
                    )
                }
            )
