"""
Forms for the payroll run wizard and the pay period configuration.

The scope form is deliberately not ``GeneratePayslipForm``. That one asks for
a free-text batch name and two dates typed by hand, which is how a run came to
be generated for the 1st to the 28th with the name left blank. Here the period
comes from the company's configured pay period, and the name is suggested from
it.
"""

import datetime
import uuid

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla_widgets.forms import HorillaForm
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from payroll.models.models import PayPeriodSettings


class PayPeriodSettingsForm(ModelForm):
    """The company's pay period, configured once."""

    class Meta:
        model = PayPeriodSettings
        fields = ["boundary", "pay_day_offset", "input_cutoff_days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].widget.attrs.update({"class": "oh-input w-100"})
        self.fields["boundary"].widget.attrs.update({"class": "oh-select oh-select-2"})


class PayrollBatchScopeForm(HorillaForm):
    """
    Step one: which period, and who is in it.

    The dates are filled from ``PayPeriodSettings`` rather than defaulted to
    the 1st of the month, so a company that has configured its pay period gets
    that period and not a guess.
    """

    SCOPE_ALL = "all"
    SCOPE_SELECTED = "selected"

    batch_name = forms.CharField(
        label=_("Run name"),
        max_length=150,
        help_text=_("What this run is called in the list. Suggested from the period."),
    )
    period_start = forms.DateField(
        label=_("Period start"), widget=forms.DateInput(attrs={"type": "date"})
    )
    period_end = forms.DateField(
        label=_("Period end"), widget=forms.DateInput(attrs={"type": "date"})
    )
    scope = forms.ChoiceField(
        label=_("Include"),
        choices=[
            (SCOPE_ALL, _("Everyone with an active contract")),
            (SCOPE_SELECTED, _("Specific employees")),
        ],
        initial=SCOPE_ALL,
        widget=forms.RadioSelect,
    )
    employee_id = HorillaMultiSelectField(
        queryset=Employee.objects.none(),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label=_("Employees"),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        period = kwargs.pop("period", None)
        super().__init__(*args, **kwargs)

        self.fields["employee_id"].queryset = Employee.objects.filter(
            is_active=True,
            contract_set__isnull=False,
            contract_set__contract_status="active",
        ).distinct()
        self.fields["employee_id"].widget.attrs.update(
            {"class": "oh-select oh-select-2", "id": uuid.uuid4()}
        )
        for name in ("batch_name", "period_start", "period_end"):
            self.fields[name].widget.attrs.update({"class": "oh-input w-100"})

        if period and not self.is_bound:
            start, end = period
            self.initial["period_start"] = start
            self.initial["period_end"] = end
            self.initial["batch_name"] = start.strftime("%B %Y")

    def clean(self):
        """
        Not ``HorillaForm.clean``: it requires every HorillaMultiSelectField
        on the form whatever the field's own ``required`` says, so the
        "everyone with an active contract" path -- which leaves the picker
        empty on purpose -- could never validate. The employee list is
        resolved the same way it does, only when the chosen scope calls for
        it.
        """
        cleaned = forms.Form.clean(self)
        self.errors.pop("employee_id", None)
        cleaned["employee_id"] = self.fields["employee_id"].queryset.filter(
            id__in=self._posted_employee_ids()
        )

        start = cleaned.get("period_start")
        end = cleaned.get("period_end")
        today = datetime.date.today()

        if start and end:
            if end < start:
                self.add_error("period_end", _("The period ends before it starts."))
            elif start > today:
                self.add_error(
                    "period_start", _("A period that has not begun cannot be paid.")
                )

        if cleaned.get("scope") == self.SCOPE_SELECTED and not cleaned["employee_id"]:
            self.add_error("employee_id", _("Choose at least one employee."))

        return cleaned

    def _posted_employee_ids(self):
        """The picker's raw values, whether posted as a QueryDict or a dict."""
        getlist = getattr(self.data, "getlist", None)
        if getlist is not None:
            return getlist("employee_id")
        value = self.data.get("employee_id") or []
        return value if isinstance(value, (list, tuple)) else [value]

    def selected_employees(self):
        """The people this run covers, after validation."""
        if self.cleaned_data["scope"] == self.SCOPE_SELECTED:
            return list(self.cleaned_data["employee_id"])
        return list(
            Employee.objects.filter(
                is_active=True,
                contract_set__isnull=False,
                contract_set__contract_status="active",
            ).distinct()
        )
