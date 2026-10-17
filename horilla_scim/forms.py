from django.db.models import Q
from django.template.loader import render_to_string

from base.forms import ModelForm
from base.models import Department, EmployeeShift, EmployeeType, JobPosition

from .models import ScimProvider


class ScimProviderForm(ModelForm):
    """company comes from the admin's selected company, so it is excluded."""

    class Meta:
        model = ScimProvider
        fields = [
            "is_enabled",
            "name",
            "delete_mode",
            "match_existing_by_email",
            "send_invitation_email",
            "default_department",
            "default_job_position",
            "default_shift",
            "default_employee_type",
        ]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            in_company = Q(company_id=company) | Q(company_id__isnull=True)
            self.fields["default_department"].queryset = (
                Department.objects.entire().filter(in_company).distinct()
            )
            self.fields["default_job_position"].queryset = (
                JobPosition.objects.entire().filter(in_company).distinct()
            )
            self.fields["default_shift"].queryset = (
                EmployeeShift.objects.entire().filter(in_company).distinct()
            )
            self.fields["default_employee_type"].queryset = (
                EmployeeType.objects.entire().filter(in_company).distinct()
            )

    def as_p(self):
        return render_to_string("common_form.html", {"form": self})
