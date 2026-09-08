"""
company_onboarding/urls.py

Mounted at "company-onboarding/" by company_onboarding/apps.py's ready()
hook (self-registers into horilla.urls.urlpatterns, same pattern
onboarding/apps.py already uses).
"""

from django.urls import path

from company_onboarding.cbv import bank_verification, status, wizard

urlpatterns = [
    path("create/", wizard.Step1View.as_view(), name="company-onboarding-create"),
    path(
        "<int:company_id>/step-1/",
        wizard.Step1View.as_view(),
        name="company-onboarding-step1",
    ),
    path(
        "<int:company_id>/step-2/",
        wizard.Step2View.as_view(),
        name="company-onboarding-step2",
    ),
    path(
        "<int:company_id>/step-3/",
        wizard.Step3View.as_view(),
        name="company-onboarding-step3",
    ),
    path(
        "state-row/add/", wizard.add_state_registration_row, name="company-onboarding-add-state-row"
    ),
    path(
        "state-row/remove/",
        wizard.remove_state_registration_row,
        name="company-onboarding-remove-state-row",
    ),
    path("poc-row/add/", wizard.add_poc_contact_row, name="company-onboarding-add-poc-row"),
    path(
        "poc-row/remove/",
        wizard.remove_poc_contact_row,
        name="company-onboarding-remove-poc-row",
    ),
    path(
        "signatory-row/add/",
        wizard.add_signatory_row,
        name="company-onboarding-add-signatory-row",
    ),
    path(
        "signatory-row/remove/",
        wizard.remove_signatory_row,
        name="company-onboarding-remove-signatory-row",
    ),
    path("", status.ClientListView.as_view(), name="company-onboarding-list"),
    path("<int:company_id>/", status.ClientDetailView.as_view(), name="company-onboarding-detail"),
    path(
        "<int:company_id>/put-on-hold/",
        status.PutOnHoldView.as_view(),
        name="company-onboarding-put-on-hold",
    ),
    path("<int:company_id>/resume/", status.ResumeView.as_view(), name="company-onboarding-resume"),
    path(
        "<int:company_id>/deactivate/",
        status.DeactivateView.as_view(),
        name="company-onboarding-deactivate",
    ),
    path(
        "<int:company_id>/reinstate/",
        status.ReinstateView.as_view(),
        name="company-onboarding-reinstate",
    ),
    path(
        "<int:company_id>/bank-verification/initiate/",
        bank_verification.InitiatePennyDropView.as_view(),
        name="company-onboarding-bank-verification-initiate",
    ),
    path(
        "<int:company_id>/bank-verification/confirm/",
        bank_verification.ConfirmPennyDropView.as_view(),
        name="company-onboarding-bank-verification-confirm",
    ),
]
