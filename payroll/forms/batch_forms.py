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
from payroll.models.payroll_batch import _ordinal


class _CompanySelect(forms.Select):
    """A company select that shows the companies already set up, but does not let them be picked."""

    def __init__(self, *args, taken=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.taken = {str(pk) for pk in taken}

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if str(getattr(value, "value", value)) in self.taken:
            option["attrs"]["disabled"] = True
            option["label"] = f"{label} ({_('already has a pay period')})"
        return option


class PayPeriodSettingsForm(ModelForm):
    """The company's pay period, configured once: the day a period begins, and the pay day."""

    # The day of the month people are paid, posted as "day:15" (or "after:5" for a pay day saved
    # earlier as days after the period) and stored in the two columns that carry it.
    pay_day = forms.ChoiceField(
        label=_("Pay Day"),
        choices=[],
        help_text=_(
            "The day of the month people are paid, counted from the day after the period ends: "
            "a period ending on the 31st and paid on the 5th is paid on the 5th of the next month. "
            "The 29th and 30th fall back to the month's last day when it is shorter."
        ),
    )

    @staticmethod
    def pay_day_label(days):
        if days == 0:
            return _("On the last day of the period")
        if days == 1:
            return _("1 day after the period ends")
        return _("%(days)s days after the period ends") % {"days": days}

    @staticmethod
    def day_of_month_label(day):
        return _("Last day") if day == PayPeriodSettings.LAST_DAY else _ordinal(day)

    @classmethod
    def pay_day_choices(cls, legacy_after=None):
        """
        The day of the month people are paid on, as Period Runs lists its start day. A pay
        day saved earlier as "N days after the period ends" has no place in that list, so it
        stays as its own first option until a day is chosen.
        """
        choices = [(f"day:{day}", cls.day_of_month_label(day)) for day in range(1, 31)]
        choices.append(
            (
                f"day:{PayPeriodSettings.LAST_DAY}",
                cls.day_of_month_label(PayPeriodSettings.LAST_DAY),
            )
        )
        if legacy_after is not None:
            choices.insert(
                0, (f"after:{legacy_after}", cls.pay_day_label(legacy_after))
            )
        return choices

    class Meta:
        model = PayPeriodSettings
        fields = ["company_id", "cycle_start_day", "auto_generate"]

    def __init__(self, *args, modal=False, with_company=False, **kwargs):
        super().__init__(*args, **kwargs)
        if with_company:
            self._limit_companies()
        else:
            # The wizard's own dialog edits the setting of the signed-in user's company.
            del self.fields["company_id"]
        legacy = (
            None
            if self.instance.pay_day_of_month
            else (self.instance.pay_day_offset or 0)
        )
        self.fields["pay_day"].choices = self.pay_day_choices(legacy)
        if self.instance.pay_day_of_month:
            self.fields["pay_day"].initial = f"day:{self.instance.pay_day_of_month}"
        else:
            self.fields["pay_day"].initial = (
                f"after:{self.instance.pay_day_offset or 0}"
            )
        for name in self.fields:
            self.fields[name].widget.attrs.update({"class": "oh-input w-100"})
        # A plain select, not select2: the page's select2 setup does not reach content loaded
        # into a modal afterwards, and thirty options do not need a search box.
        for name in [
            n for n in ("company_id", "cycle_start_day", "pay_day") if n in self.fields
        ]:
            self.fields[name].widget.attrs.update(
                {"class": "oh-input w-100" if modal else "oh-select oh-select-2"}
            )

    def _limit_companies(self):
        """
        The companies in view: the selected one, or all of them. A company that already has a
        pay period stays in the list but cannot be picked (one setting per company).
        """
        from base.models import Company
        from horilla import horilla_middlewares

        taken = PayPeriodSettings.objects.entire().filter(company_id__isnull=False)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        self.taken_company_ids = set(taken.values_list("company_id", flat=True))
        try:
            active = horilla_middlewares.get_selected_company()
        except Exception:
            active = None
        companies = Company.objects.all()
        if active and active != "all":
            companies = companies.filter(pk=active)
        field = self.fields["company_id"]
        field.widget = _CompanySelect(taken=self.taken_company_ids)
        field.widget.attrs.update({"class": "oh-input w-100"})
        field.queryset = companies
        field.label = _("Company")
        field.required = True
        field.empty_label = _("Select a company")
        free = [c.pk for c in companies if c.pk not in self.taken_company_ids]
        self.has_free_company = bool(free)
        if not self.instance.pk and len(free) == 1 and active and active != "all":
            field.initial = free[0]

    def clean_company_id(self):
        company = self.cleaned_data.get("company_id")
        if company and company.pk in getattr(self, "taken_company_ids", ()):
            raise forms.ValidationError(_("This company already has a pay period."))
        return company

    def clean_pay_day(self):
        value = self.cleaned_data["pay_day"]
        kind, _sep, number = value.partition(":")
        if kind not in ("after", "day") or not number.isdigit():
            raise forms.ValidationError(_("Choose when people are paid."))
        return value

    def save(self, commit=True):
        _apply_pay_day(self.instance, self.cleaned_data.get("pay_day"))
        return super().save(commit=commit)


def _apply_pay_day(form_instance, value):
    """Store a "after:N" / "day:N" choice in the columns it belongs to."""
    kind, _sep, number = (value or "after:0").partition(":")
    if kind == "day":
        form_instance.pay_day_of_month = int(number)
    else:
        form_instance.pay_day_of_month = 0
        form_instance.pay_day_offset = int(number)


def suggest_batch_name(start, end):
    """ "September 2026" for a calendar month, "15 Sep 2026 – 14 Oct 2026" for a period that crosses months."""
    if start.day == 1 and (start.year, start.month) == (end.year, end.month):
        return start.strftime("%B %Y")
    return f"{start.strftime('%d %b %Y').lstrip('0')} – {end.strftime('%d %b %Y').lstrip('0')}"


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
        label=_("Batch Name"),
        max_length=150,
        help_text=_(
            "What this batch is called in the list. Suggested from the period."
        ),
    )
    period_start = forms.DateField(
        label=_("Period Start"), widget=forms.DateInput(attrs={"type": "date"})
    )
    # Never typed: it is always the start plus the days of the start's month, so
    # whatever is posted for it is ignored (see clean()).
    period_end = forms.DateField(
        label=_("Period End"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "readonly": "readonly"}),
        help_text=_(
            "Worked out from the start: as many days as the start's month has."
        ),
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
        self.pay_settings = kwargs.pop("settings", None) or PayPeriodSettings()
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
        self.fields["period_end"].widget.attrs["class"] = "oh-input w-100 pb__readonly"

        if period and not self.is_bound:
            start, end = period
            self.initial["period_start"] = start
            self.initial["period_end"] = end
            self.initial["batch_name"] = suggest_batch_name(start, end)

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
        today = datetime.date.today()

        if start:
            # The end is not a choice: it follows from the start.
            cleaned["period_end"] = self.pay_settings.end_for(start)
            if start > today:
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
