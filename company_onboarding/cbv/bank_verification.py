"""
company_onboarding/cbv/bank_verification.py
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View

from base.models import Company
from horilla.decorators import login_required, permission_required

from company_onboarding.services.bank_verification import (
    confirm_penny_drop,
    initiate_penny_drop,
)
from company_onboarding.wizard_utils import get_bank_details


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_company"), name="dispatch")
class InitiatePennyDropView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        bank_details = get_bank_details(company)
        if not bank_details or not all(
            [bank_details.account_number, bank_details.bank_name, bank_details.ifsc_swift]
        ):
            messages.error(request, "Save bank details before initiating a penny drop.")
        else:
            initiate_penny_drop(bank_details)
            messages.success(request, "Penny drop initiated.")
        return redirect("company-onboarding-step1", company_id=company.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_company"), name="dispatch")
class ConfirmPennyDropView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        bank_details = get_bank_details(company)
        attempt = bank_details.verifications.first() if bank_details else None
        if not attempt:
            messages.error(request, "Initiate a penny drop first.")
            return redirect("company-onboarding-step1", company_id=company.pk)

        try:
            entered_amount = Decimal(request.POST.get("entered_amount", ""))
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid amount.")
            return redirect("company-onboarding-step1", company_id=company.pk)

        if confirm_penny_drop(attempt, entered_amount):
            messages.success(request, "Bank account verified.")
        else:
            messages.error(request, "Amount does not match. You can try again.")
        return redirect("company-onboarding-step1", company_id=company.pk)
