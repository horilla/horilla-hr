"""
forms.py
"""

from typing import Any

from django import forms
from django.forms import widgets
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import Form, ModelForm
from employee.filters import EmployeeFilter
from employee.forms import MultipleFileField
from employee.models import Employee
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from payroll.context_processors import get_active_employees
from payroll.models.models import (
    Contract,
    EncashmentGeneralSettings,
    PayrollGeneralSetting,
    ReimbursementFile,
    ReimbursementrequestComment,
    SalaryStructure,
)

# What the contract wage IS depends on the structure the contract is on, and
# the field cannot say "Basic Salary" in both cases without lying in one of
# them. Under CTC Down the wage is the whole figure the components divide up,
# and basic is one of the components — often "50% of gross" — so calling that
# box basic pay describes the opposite of what it does.
WAGE_LABELS = {
    "gross_up": _("Basic Salary"),
    "ctc_down": _("Gross / CTC"),
}

# The unit the wage is in, said in the label rather than left to Wage Type two
# boxes away. The same number means three different things depending on it, and
# a list column showing "100" cannot tell you which.
WAGE_UNITS = {
    "monthly": _("per month"),
    "daily": _("per day"),
    "hourly": _("per hour"),
}
WAGE_HELP = {
    "gross_up": _("Basic pay. Allowances are added on top of it to reach gross."),
    "ctc_down": _(
        "The total to divide up. Every earning, including basic pay, comes "
        "from a component of this structure — so a component can be defined "
        "as a percentage of gross, and the balance component absorbs whatever "
        "is left."
    ),
}

# Said plainly, next to the box, naming the structure responsible. The label
# alone changes silently when the structure changes, which is easy to miss on a
# form this long — and reading the wrong meaning into this number is how a
# payslip comes out wrong.
WAGE_READING = {
    "gross_up": _("Read as basic pay."),
    "ctc_down": _("Read as cost to company, and divided up by the structure."),
}


class SalaryStructureSelect(forms.Select):
    """
    The structure picker, with each option carrying its structure's mode.

    The mode lives on SalaryStructure, not on Contract, so the form cannot know
    which reading of the wage applies until one is picked. Publishing it per
    option lets the wage label follow the choice on screen instead of only
    being right again after a save.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.structure_modes = {}

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        mode = self.structure_modes.get(str(value))
        if mode:
            option["attrs"]["data-structure-mode"] = mode
        return option


class UnavailableChoicesSelect(forms.Select):
    """
    A select that lists some options but will not let them be picked.

    For choices the product names but cannot honour yet: showing them says what
    is coming, disabling them says it is not here, and the form refuses a
    posted value for one regardless, because a disabled option is only a hint
    to the browser.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unavailable = set()

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        if str(value) in self.unavailable:
            option["attrs"]["disabled"] = True
        return option


class ContractForm(ModelForm):
    """
    ContactForm
    """

    verbose_name = _("Contract")
    contract_start_date = forms.DateField()
    contract_end_date = forms.DateField(required=False)

    class Meta:
        """
        Meta class for additional options
        """

        fields = "__all__"
        exclude = [
            "is_active",
        ]
        model = Contract

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"].widget.attrs.update(
            {"onchange": "contractInitial(this)"}
        )
        self.fields["contract_start_date"].widget = widgets.DateInput(
            attrs={
                "type": "date",
                "class": "oh-input w-100",
                "placeholder": "Select a date",
            }
        )
        self.fields["contract_end_date"].widget = widgets.DateInput(
            attrs={
                "type": "date",
                "class": "oh-input w-100",
                "placeholder": "Select a date",
            }
        )
        self.fields["contract_status"].widget.attrs.update(
            {
                "class": "oh-select",
            }
        )
        if self.instance and self.instance.pk:
            dynamic_url = self.get_dynamic_hx_post_url(self.instance)
            self.fields["contract_status"].widget.attrs.update(
                {
                    "hx-target": "this",
                    "hx-post": dynamic_url,
                    "hx-swap": "beforebegin",
                }
            )
        # The notice period is not asked for on the contract. A new contract
        # starts from the payroll setting's default (30 days when there is none),
        # and an existing one keeps what it has: the field is left off the form,
        # so saving never touches it.
        if self.instance.pk is None:
            first = PayrollGeneralSetting.objects.first()
            self.instance.notice_period_in_days = (
                first.notice_period if first and first.notice_period is not None else 30
            )
        self.fields.pop("notice_period_in_days", None)
        self.fields["contract_document"].widget.attrs[
            "accept"
        ] = ".jpg, .jpeg, .png, .pdf"
        self._disable_unsupported_pay_frequencies()
        self._label_wage_for_structure()

    # The engine pays monthly. A weekly or semi-monthly contract would be read
    # as monthly and the amounts would be wrong, so they are listed but cannot
    # be chosen. A contract that already holds one keeps it, so editing an old
    # record is not blocked by a choice it made before this existed.
    UNSUPPORTED_PAY_FREQUENCIES = {"weekly", "semi_monthly"}

    def _disable_unsupported_pay_frequencies(self):
        field = self.fields.get("pay_frequency")
        if field is None:
            return
        current = getattr(self.instance, "pay_frequency", None)
        widget = UnavailableChoicesSelect(choices=field.widget.choices)
        widget.attrs.update(field.widget.attrs)
        widget.unavailable = self.UNSUPPORTED_PAY_FREQUENCIES - {current}
        field.widget = widget

    def clean_pay_frequency(self):
        value = self.cleaned_data.get("pay_frequency")
        current = getattr(self.instance, "pay_frequency", None)
        if value in self.UNSUPPORTED_PAY_FREQUENCIES and value != current:
            raise forms.ValidationError(
                _("Only monthly pay is supported at the moment.")
            )
        return value

    def _label_wage_for_structure(self):
        """
        Name the wage box after what it holds on the chosen structure, and give
        the picker what the page needs to keep doing so as the choice changes.
        """
        structure = getattr(self.instance, "salary_structure_id", None)
        mode = getattr(structure, "structure_mode", None) or "gross_up"

        wage = self.fields["wage"]
        wage.label = WAGE_LABELS.get(mode, WAGE_LABELS["gross_up"])
        wage.help_text = WAGE_HELP.get(mode, WAGE_HELP["gross_up"])
        wage.widget.attrs.update(
            {
                "data-wage-label-gross-up": WAGE_LABELS["gross_up"],
                "data-wage-label-ctc-down": WAGE_LABELS["ctc_down"],
                "data-wage-help-gross-up": WAGE_HELP["gross_up"],
                "data-wage-help-ctc-down": WAGE_HELP["ctc_down"],
                "data-wage-reading-gross-up": WAGE_READING["gross_up"],
                "data-wage-reading-ctc-down": WAGE_READING["ctc_down"],
                "data-wage-structure": str(structure) if structure else "",
            }
        )

        # An hourly contract is paid from its own box, so the monthly figure is
        # not what the engine reads and should not be demanded.
        if (self.instance.wage_type or "monthly") == "hourly":
            self.fields["wage"].required = False
        unit = WAGE_UNITS.get(self.instance.wage_type or "monthly")
        if unit and wage.label:
            wage.label = f"{wage.label} ({unit})"
        for name, per in (
            ("hourly_wage", WAGE_UNITS["hourly"]),
            ("monthly_ctc", WAGE_UNITS["monthly"]),
        ):
            field = self.fields.get(name)
            if field is not None and field.label:
                field.label = f"{field.label} ({per})"

        picker = self.fields.get("salary_structure_id")
        if picker is None:
            return
        widget = SalaryStructureSelect(choices=picker.widget.choices)
        widget.attrs.update(picker.widget.attrs)
        widget.structure_modes = {
            str(pk): mode
            for pk, mode in SalaryStructure.objects.values_list("pk", "structure_mode")
        }
        picker.widget = widget

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("contract_form.html", context)
        return table_html

    def get_dynamic_hx_post_url(self, instance):
        """
        Render the url for contract status update through hx request
        """
        return f"/payroll/update-contract-status/{instance.pk}"


class ReimbursementRequestCommentForm(ModelForm):
    """
    ReimbursementRequestCommentForm form
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = ReimbursementrequestComment
        fields = ("comment",)


class reimbursementCommentForm(ModelForm):
    """
    Reimbursement request comment model form
    """

    verbose_name = "Add Comment"

    class Meta:
        """
        Meta class for additional options
        """

        model = ReimbursementrequestComment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["files"] = MultipleFileField(label="files")
        self.fields["files"].required = False
        self.fields["files"].widget.attrs["accept"] = ".jpg, .jpeg, .png, .pdf"

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        multiple_files_ids = []
        files = None
        if self.files.getlist("files"):
            files = self.files.getlist("files")
            self.instance.attachemnt = files[0]
            multiple_files_ids = []
            for attachemnt in files:
                file_instance = ReimbursementFile()
                file_instance.file = attachemnt
                file_instance.save()
                multiple_files_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.files.add(*multiple_files_ids)
        return instance, files


class EncashmentGeneralSettingsForm(ModelForm):
    class Meta:
        model = EncashmentGeneralSettings
        fields = "__all__"
        # Toggled independently via its own hx-post (toggle-leave-encashment)
        # and its own eligibility form (EncashmentEligibilityForm) below --
        # excluded here so re-saving the redeem-unit amounts can't silently
        # reset them (a bare, unchecked BooleanField posts nothing, which
        # Django would otherwise read as False; an untouched M2M field is
        # never included in this form's data at all).
        exclude = [
            "leave_encashment_enabled",
            "is_applicable_to_all",
            "employees",
            "department",
            "job_position",
            "filtered_employees",
        ]


class EncashmentEligibilityForm(ModelForm):
    """
    Who Leave Encashment applies to -- saved independently of both the
    redeem-unit amounts and the enable/disable toggle.
    """

    employees = HorillaMultiSelectField(
        queryset=Employee.objects.all(),
        required=False,
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label=_("Employees"),
        help_text=_(
            "Used only when 'Apply to all employees' is disabled below -- "
            "restricts Leave Encashment to these employees plus anyone in "
            "the selected department(s) or job position(s)."
        ),
    )

    cols = {
        "employees": 12,
        "department": 12,
        "job_position": 12,
    }

    class Meta:
        model = EncashmentGeneralSettings
        # is_applicable_to_all is toggled independently via its own hx-post
        # (toggle-encashment-apply-to-all) -- excluded here so re-saving the
        # employees/department/job position selection can't silently reset
        # it (an untouched BooleanField would post nothing and Django would
        # read that as False).
        fields = ["employees", "department", "job_position"]


class DashboardExport(Form):
    status_choices = [
        ("", ""),
        ("draft", "Draft"),
        ("review_ongoing", "Review Ongoing"),
        ("confirmed", "Confirmed"),
        ("paid", "Paid"),
    ]
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    employees = forms.ChoiceField(
        required=False,
        choices=[(emp.id, emp.get_full_name()) for emp in Employee.objects.all()],
        widget=forms.SelectMultiple,
    )
    status = forms.ChoiceField(required=False, choices=status_choices)
    contributions = forms.ChoiceField(
        required=False,
        choices=[
            (emp.id, emp.get_full_name())
            for emp in get_active_employees(None)["get_active_employees"]
        ],
        widget=forms.SelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employees"].widget.attrs.update({"class": "oh-select oh-select-2"})
        self.fields["status"].widget.attrs.update({"class": "oh-select oh-select-2"})
        self.fields["contributions"].widget.attrs.update(
            {"class": "oh-select oh-select-2"}
        )
