from django.contrib import admin

from company_onboarding.models import (
    CashfreeApiLog,
    CompanyBankDetails,
    CompanyBankVerification,
    CompanyBrandedTemplate,
    CompanyContract,
    CompanyDeactivationRecord,
    CompanyDocument,
    CompanyPOCContact,
    CompanySignatory,
    CompanyStateRegistration,
)

admin.site.register(CompanyStateRegistration)
admin.site.register(CompanyPOCContact)
admin.site.register(CompanyBankDetails)
admin.site.register(CompanyBankVerification)
admin.site.register(CashfreeApiLog)
admin.site.register(CompanyContract)
admin.site.register(CompanySignatory)
admin.site.register(CompanyBrandedTemplate)
admin.site.register(CompanyDocument)
admin.site.register(CompanyDeactivationRecord)
