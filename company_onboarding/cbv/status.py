"""
company_onboarding/cbv/status.py

Status lifecycle: Onboarding -> Active -> On Hold <-> Resume,
Active -> Deactivated -> Reinstate.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView

from base.models import Company
from horilla.decorators import login_required, permission_required

from company_onboarding.models import CompanyDeactivationRecord
from company_onboarding.wizard_utils import get_bank_details


@method_decorator(login_required, name="dispatch")
class ClientListView(ListView):
    model = Company
    template_name = "company_onboarding/list.html"
    context_object_name = "companies"


@method_decorator(login_required, name="dispatch")
class ClientDetailView(View):
    template_name = "company_onboarding/detail.html"

    def get(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        return render(
            request,
            self.template_name,
            {
                "company": company,
                "state_registrations": company.state_registrations.all(),
                "poc_contacts": company.poc_contacts.all(),
                "bank_details": get_bank_details(company),
                "contracts": company.contracts.order_by("-created_at"),
                "signatories": company.signatories.all(),
                "branded_templates": company.branded_templates.all(),
                "documents": company.documents.all(),
                "deactivation_records": company.deactivation_records.all(),
            },
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_status_company"), name="dispatch")
class PutOnHoldView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        if company.status != "ACTIVE":
            messages.error(request, "Only an Active client can be put On Hold.")
        else:
            company.status = "ON_HOLD"
            company.save(update_fields=["status"])
            messages.success(request, "Client put On Hold.")
        return redirect("company-onboarding-detail", company_id=company.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_status_company"), name="dispatch")
class ResumeView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        if company.status != "ON_HOLD":
            messages.error(request, "Client is not On Hold.")
        else:
            company.status = "ACTIVE"
            company.save(update_fields=["status"])
            messages.success(request, "Client resumed to Active.")
        return redirect("company-onboarding-detail", company_id=company.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_status_company"), name="dispatch")
class DeactivateView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        if company.status != "ACTIVE":
            messages.error(request, "Only an Active client can be deactivated.")
            return redirect("company-onboarding-detail", company_id=company.pk)

        reason = request.POST.get("reason", "").strip()
        checklist_values = {
            field: request.POST.get(field) == "on"
            for field in CompanyDeactivationRecord.CHECKLIST_FIELDS
        }
        if not reason:
            messages.error(request, "A deactivation reason is required.")
            return redirect("company-onboarding-detail", company_id=company.pk)
        if not all(checklist_values.values()):
            messages.error(request, "All checklist items must be confirmed.")
            return redirect("company-onboarding-detail", company_id=company.pk)

        CompanyDeactivationRecord.objects.create(
            company=company,
            reason=reason,
            confirmed_by=request.user,
            **checklist_values,
        )
        company.status = "DEACTIVATED"
        company.save(update_fields=["status"])
        messages.success(request, "Company deactivated.")
        return redirect("company-onboarding-detail", company_id=company.pk)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("base.change_status_company"), name="dispatch")
class ReinstateView(View):
    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        if company.status != "DEACTIVATED":
            messages.error(request, "Only a Deactivated client can be reinstated.")
            return redirect("company-onboarding-detail", company_id=company.pk)
        # No PAN/Foreign Tax ID retyping: those fields can't be edited once
        # deactivated (the wizard blocks edits at that status), so the
        # stored value already IS "the original" — nothing to compare.
        company.status = "ACTIVE"
        company.save(update_fields=["status"])
        messages.success(request, "Company reinstated to Active.")
        return redirect("company-onboarding-detail", company_id=company.pk)
