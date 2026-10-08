"""
These forms provide a convenient way to handle data input, validation, and customization
of form fields and widgets for the corresponding models in the payroll management system.
"""

import datetime
import logging
import uuid
from typing import Any

from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

import payroll.models.models
from base.forms import Form, ModelForm
from base.methods import reload_queryset
from base.models import Company
from employee.filters import EmployeeFilter
from employee.models import BonusPoint, Employee
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla_widgets.forms import HorillaForm, default_select_option_template
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from notifications.signals import notify
from payroll.models import tax_models as models
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    LoanAccount,
    MultipleCondition,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    ReimbursementMultipleAttachment,
    SalaryStructure,
)
from payroll.widgets import component_widgets as widget

logger = logging.getLogger(__name__)


class CalendarDaysOnlySelect(forms.Select):
    """
    "This amount is" (maximum_unit), with every option but calendar days
    disabled rather than removed: an existing component already set to one
    of the other three bases keeps displaying and working exactly as before
    (the model field and its choices are untouched), but a new or edited one
    can no longer be switched to it from this form.
    """

    ENABLED_VALUE = "month_calendar_days"

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if str(value) != self.ENABLED_VALUE:
            option["attrs"]["disabled"] = "disabled"
        return option


def restrict_maximum_unit_to_calendar_days(form):
    """Swap in CalendarDaysOnlySelect for maximum_unit, keeping whatever
    attrs (CSS classes etc.) and choices the form's own widget already carries.

    A widget's `choices` is only ever populated via the field's `choices`
    property setter, which forwards to `widget.choices` -- replacing
    `field.widget` with a fresh instance skips that, leaving the new widget
    with none and the rendered <select> with no <option> tags at all.
    """
    field = form.fields.get("maximum_unit")
    if field is not None:
        field.widget = CalendarDaysOnlySelect(attrs=field.widget.attrs)
        field.widget.choices = field.choices


def save_apply_conditions(form, commit):
    """
    Persist the extra "when it applies" rows posted alongside the component.

    Rebuilt from the post each time rather than diffed: the rows have no
    identity in the form, so matching them up would mean inventing one, and a
    rule nobody can point at is not worth the machinery.
    """
    from payroll.models.models import ApplyCondition

    data = form.data
    choices = data.getlist("apply_choices") if hasattr(data, "getlist") else []
    if not form.instance.pk:
        return []

    form.instance.apply_conditions.all().delete()

    conditions = data.getlist("apply_conditions")
    amounts = data.getlist("apply_amounts")
    starts = data.getlist("apply_starts")
    ends = data.getlist("apply_ends")
    codes = data.getlist("apply_codes")

    def number(values, index):
        try:
            return float(values[index])
        except (IndexError, TypeError, ValueError):
            return None

    rows = []
    for index, choice in enumerate(choices):
        if not choice:
            continue
        condition = conditions[index] if index < len(conditions) else "gt"
        row = ApplyCondition(
            choice=choice,
            condition=condition or "gt",
            amount=number(amounts, index) or 0.0,
            start_range=number(starts, index),
            end_range=number(ends, index),
            component_code=(codes[index] if index < len(codes) else "") or "",
        )
        row.save()
        rows.append(row)

    if commit and rows:
        form.instance.apply_conditions.add(*rows)
    return rows


def apply_component_code_choices(form, model):
    """
    Turn percentage_of_code into a dropdown of codes that actually exist.

    It is a plain CharField on the model — any component's code is a valid
    target, including one not created yet — so it cannot be a ModelChoiceField.
    But a free-text box for a value that has to match another record exactly is
    a typo waiting to be a silently wrong payslip: an unknown code resolves to
    0, which looks like a component that simply did not apply.

    The component's own code is excluded; a formula or percentage referring to
    itself reads either a stale value or nothing, depending on ordering.
    """
    from payroll.views.component_formula_views import available_codes

    # The component's own code is derived from its title and is never typed, so
    # it is not drawn on the form — but it still has to round-trip. Deriving it
    # again on save only happens when it is blank, so a form that omitted it
    # would re-derive from the current title and silently retarget every
    # formula and percentage pointing at the old code.
    if "code" in form.fields:
        # Drawn: typed, or left blank to be derived from the title on save. Changing
        # one that is already referenced would leave those formulas pointing at nothing.
        form.fields["code"].required = False
        form.fields["code"].widget.attrs.update(
            {
                "placeholder": _("Auto from title, e.g. HRA"),
                # Upper-cased as it is typed; a style would capitalise the placeholder too.
                "oninput": "this.value = this.value.toUpperCase();",
                "autocomplete": "off",
                "maxlength": 32,
            }
        )
        form.fields["code"].help_text = _(
            "Short name other components and formulas use to refer to this one "
            "(capital letters, digits, underscore; starts with a letter). Leave "
            "blank to make it from the title. Changing it later breaks anything "
            "that refers to the old one."
        )

        def _upper(value):
            return (value or "").strip().upper()

        def _clean_code(value, _f=form.fields["code"]):
            value = forms.CharField.clean(_f, _upper(value))
            _f.run_validators(value)
            instance = getattr(form, "instance", None)
            pk = instance.pk if instance is not None and instance.pk else None
            from payroll.models.models import component_code_taken

            if component_code_taken(value, model, pk):
                raise forms.ValidationError(
                    _("The code %(code)s is already used by another component."),
                    params={"code": value},
                )
            return value

        form.fields["code"].clean = _clean_code

    # Same reasoning as `code`: not drawn, but it has to survive an edit. A
    # form that simply omitted it would blank the setting on the next save.
    if "update_compensation" in form.fields:
        form.fields["update_compensation"].widget = forms.HiddenInput()
        form.fields["update_compensation"].required = False

    # Eleven flat options, three different kinds of answer. Grouping them is
    # what makes "Custom Formula" findable rather than something you have to
    # already know is in there.
    based_on = form.fields.get("based_on")
    if based_on is not None:
        from payroll.forms.component_layout import group_based_on_choices

        group_based_on_choices(based_on)

    field = form.fields.get("percentage_of_code")
    if field is None:
        return

    instance = getattr(form, "instance", None)
    exclude_pk = instance.pk if instance is not None and instance.pk else None
    rows = available_codes(exclude_pk=exclude_pk, exclude_model=model)

    choices = [("", _("Select a component..."))]
    # Labelled by name. The code is derived plumbing the user never chose, so
    # showing it here would ask them to recognise an identifier instead of the
    # component they created.
    choices += [
        (
            row["code"],
            # Under a CTC Down structure basic is worked out from a component, not
            # read off the contract; the label says which "Basic pay" this is.
            (
                f'{row["label"]} ({_("CTC Down structure")})'
                if row["code"] == "BASIC"
                else row["label"]
            ),
        )
        for row in rows
    ]

    current = (
        (form.data.get("percentage_of_code") if form.is_bound else None)
        or getattr(instance, "percentage_of_code", "")
        or ""
    )
    # Keep whatever is already stored selectable even if that code has since
    # been renamed or removed, so re-saving cannot silently retarget it.
    if current and not any(current == value for value, _label in choices):
        choices.insert(1, (current, f"{current} ({_('currently set')})"))

    # Styled like the form's other dropdowns. Not copied from the field being
    # replaced: on the model this is a plain CharField, so its widget is a text
    # input and its classes are the text-input ones. Rebuilding it as a
    # ChoiceField without this left the one bare browser dropdown on a form
    # where every other select is oh-select / select2.
    form.fields["percentage_of_code"] = forms.ChoiceField(
        choices=choices,
        required=False,
        label=field.label,
        help_text=field.help_text,
        initial=field.initial,
        widget=forms.Select(attrs=_select_attrs(form)),
    )

    # The same list for the "when it applies" rule, which measures a component
    # rather than taking a share of it. Deliberately a separate field: what a
    # component is a percentage OF and what decides whether it applies at all
    # are different questions and are often different components.
    gate = form.fields.get("if_component_code")
    if gate is not None:
        gate_current = (
            (form.data.get("if_component_code") if form.is_bound else None)
            or getattr(instance, "if_component_code", "")
            or ""
        )
        gate_choices = list(choices)
        if gate_current and not any(
            gate_current == value for value, _label in gate_choices
        ):
            gate_choices.insert(
                1, (gate_current, f"{gate_current} ({_('currently set')})")
            )
        form.fields["if_component_code"] = forms.ChoiceField(
            choices=gate_choices,
            required=False,
            label=gate.label,
            help_text=gate.help_text,
            initial=gate.initial,
            widget=forms.Select(attrs=_select_attrs(form)),
        )


def _select_attrs(form):
    """
    The widget attrs this form puts on an ordinary single-choice dropdown.

    Read off a sibling rather than hardcoded, so it keeps matching if the form
    styling changes.
    """
    for name in ("based_on", "if_choice", "if_condition", "maximum_unit"):
        widget = form.fields[name].widget if name in form.fields else None
        if isinstance(widget, forms.Select) and not isinstance(
            widget, forms.SelectMultiple
        ):
            if widget.attrs.get("class"):
                return dict(widget.attrs)
    return {"class": "oh-select oh-select-2"}


def restrict_to_system_fields(form):
    """
    Cut a system component's form down to the settings that mean anything.

    A template does not hold an amount, a formula, a rate or a list of
    employees: the loan schedule decides the amount, the attendance record
    decides the days, and the generator decides who it applies to. Leaving
    those fields on the form would offer settings that change nothing, which is
    worse than not offering them — someone sets a rate on "Loan repayment",
    saves, and reasonably expects repayments to change.

    So only the tax treatment and the proration basis survive, and only the
    ones that kind actually has. See payroll/system_components.py.
    """
    from payroll.system_components import editable_fields

    instance = getattr(form, "instance", None)
    if instance is None or not getattr(instance, "is_system", False):
        return

    keep = set(editable_fields(instance.system_key))
    for name in list(form.fields):
        if name not in keep:
            del form.fields[name]


class AllowanceForm(ModelForm):
    """
    Form for Allowance model
    """

    verbose_name = _("Allowance")

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Allowance
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        if instance := kwargs.get("instance"):
            # django forms not showing value inside the date, time html element.
            # so here overriding default forms instance method to set initial value
            initial = {}
            if instance.one_time_date is not None:
                initial = {
                    "one_time_date": instance.one_time_date.strftime("%Y-%m-%d"),
                }
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields["one_time_date"].initial = None
        apply_component_code_choices(self, payroll.models.models.Allowance)
        restrict_to_system_fields(self)
        from payroll.forms.component_layout import apply_labels

        apply_labels(self)
        restrict_maximum_unit_to_calendar_days(self)

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("generic/form.html", context)
        return table_html

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)

        if cleaned_data.get("if_condition") == "range":
            cleaned_data["if_amount"] = 0
            start_range = cleaned_data.get("start_range")
            end_range = cleaned_data.get("end_range")
            if start_range and end_range and end_range <= start_range:
                raise forms.ValidationError(
                    {"end_range": "End range cannot be less than start range."}
                )
            if not start_range and not end_range:
                raise forms.ValidationError(
                    {
                        "start_range": 'This field is required when condition is "range".',
                        "end_range": 'This field is required when condition is "range".',
                    }
                )
            elif not start_range:
                raise forms.ValidationError(
                    {"start_range": 'This field is required when condition is "range".'}
                )
            elif not end_range:
                raise forms.ValidationError(
                    {"end_range": 'This field is required when condition is "range".'}
                )
        else:
            cleaned_data["start_range"] = None
            cleaned_data["end_range"] = None

    def save(self, commit: bool = ...) -> Any:
        super().save(commit)
        other_conditions = self.data.getlist("other_conditions")
        other_fields = self.data.getlist("other_fields")
        other_values = self.data.getlist("other_values")
        multiple_conditions = []
        try:
            if self.instance.pk:
                self.instance.other_conditions.all().delete()
            if self.instance.is_condition_based:
                for index, field in enumerate(other_fields):
                    condition = MultipleCondition(
                        field=field,
                        condition=other_conditions[index],
                        value=other_values[index],
                    )
                    condition.save()
                    multiple_conditions.append(condition)
        except Exception as e:
            logger(e)
        if commit:
            self.instance.other_conditions.add(*multiple_conditions)
        save_apply_conditions(self, commit)
        return multiple_conditions


class DeductionForm(ModelForm):
    """
    Form for Deduction model
    """

    verbose_name = _("Deduction")

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Deduction
        fields = "__all__"
        exclude = [
            "is_active",
            "specific_employees",
            "exclude_employees",
            "include_active_employees",
        ]
        widgets = {
            "one_time_date": forms.DateTimeInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        if instance := kwargs.get("instance"):
            # django forms not showing value inside the date, time html element.
            # so here overriding default forms instance method to set initial value
            initial = {}
            if instance.one_time_date is not None:
                initial = {
                    "one_time_date": instance.one_time_date.strftime("%Y-%m-%d"),
                }
            kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        apply_component_code_choices(self, payroll.models.models.Deduction)
        restrict_to_system_fields(self)
        from payroll.forms.component_layout import apply_labels

        apply_labels(self)
        restrict_maximum_unit_to_calendar_days(self)

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)

        if cleaned_data.get("if_condition") == "range":
            cleaned_data["if_amount"] = 0
            start_range = cleaned_data.get("start_range")
            end_range = cleaned_data.get("end_range")

            if start_range and end_range and int(end_range) <= int(start_range):
                raise forms.ValidationError(
                    {"end_range": "End range cannot be less than start range."}
                )
            if not start_range and not end_range:
                raise forms.ValidationError(
                    {
                        "start_range": 'This field is required when condition is "range".',
                        "end_range": 'This field is required when condition is "range".',
                    }
                )
            elif not start_range:
                raise forms.ValidationError(
                    {"start_range": 'This field is required when condition is "range".'}
                )
            elif not end_range:
                raise forms.ValidationError(
                    {"end_range": 'This field is required when condition is "range".'}
                )
        else:
            cleaned_data["start_range"] = None
            cleaned_data["end_range"] = None

        if (
            self.data.get("update_compensation") is not None
            and self.data.get("update_compensation") != ""
        ):
            if (
                self.data.get("one_time_date") is None
                and self.data.get("one_time_date") == ""
            ):
                raise forms.ValidationError(
                    {"one_time_date": _("This field is required.")}
                )
            if self.data.get("amount") is None and self.data.get("amount") == "":
                raise forms.ValidationError({"amount": _("This field is required.")})
        return cleaned_data

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        specific_employees = self.data.getlist("specific_employees")
        include_all = self.data.get("include_active_employees")
        condition_based = self.data.get("is_condition_based")
        in_structure = (
            bool(self.instance.pk) and self.instance.salary_structures.exists()
        )
        if (
            not specific_employees
            and not include_all
            and not condition_based
            and not in_structure
        ):
            self.instance.include_active_employees = True
        super().save(commit)
        other_conditions = self.data.getlist("other_conditions")
        other_fields = self.data.getlist("other_fields")
        other_values = self.data.getlist("other_values")
        multiple_conditions = []
        try:
            if self.instance.pk:
                self.instance.other_conditions.all().delete()
            if self.instance.is_condition_based:
                for index, field in enumerate(other_fields):
                    condition = MultipleCondition(
                        field=field,
                        condition=other_conditions[index],
                        value=other_values[index],
                    )
                    condition.save()
                    multiple_conditions.append(condition)
        except Exception as e:
            print(e)
        if commit:
            self.instance.other_conditions.add(*multiple_conditions)
        save_apply_conditions(self, commit)
        return multiple_conditions


class SalaryStructureForm(ModelForm):
    """
    Form for SalaryStructure model
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
    )

    class Meta:
        """
        Meta class for additional options
        """

        model = SalaryStructure
        # structure_mode was missing, which made CTC Down unreachable: the mode
        # existed on the model and was read by the engine, but nothing outside a
        # shell could set it.
        fields = ["title", "structure_mode", "allowances", "deductions"]

    def _employees_on_structure(self):
        if not self.instance.pk:
            return Employee.objects.none()
        return Employee.objects.filter(
            contract_set__salary_structure_id=self.instance,
            contract_set__contract_status="active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Neither the per-employee rows a loan generates nor the standard
        # components that govern them belong in a structure: the first are
        # already targeted at one person, the second are never paid at all.
        self.fields["allowances"].queryset = (
            self.fields["allowances"]
            .queryset.exclude(only_show_under_employee=True)
            .exclude(is_system=True)
        )
        self.fields["deductions"].queryset = (
            self.fields["deductions"]
            .queryset.exclude(only_show_under_employee=True)
            .exclude(is_system=True)
        )
        # Only employees this structure may actually take on: an active
        # contract, and that contract not already naming another structure.
        # Offering the rest was offering to silently move someone off whatever
        # structure they were on.
        from payroll.methods.structure_rules import assignable_employees

        self.fields["employees"].queryset = assignable_employees(self.instance)
        if self.instance.pk:
            self.initial["employees"] = self._employees_on_structure()

    def clean(self):

        cleaned_data = super().clean()
        self.errors.pop("employees", None)
        employees = Employee.objects.filter(pk__in=self.data.getlist("employees"))
        cleaned_data["employees"] = employees
        # Enforced here as well as in the queryset: the multi-select's own
        # filter panel queries employees through a generic route that knows
        # nothing about this restriction, so the list is not the last word on
        # what can be submitted.
        from payroll.methods.structure_rules import unassignable_reason

        no_active_contract = []
        taken = []
        for employee in employees:
            reason = unassignable_reason(employee, self.instance)
            if reason == "no_contract":
                no_active_contract.append(employee)
            elif reason is not None:
                taken.append((employee, reason))

        problems = []
        if no_active_contract:
            problems.append(
                _(
                    "These employees have no active contract, so a salary "
                    "structure can't be assigned to them: %(names)s"
                )
                % {"names": ", ".join(str(one) for one in no_active_contract)}
            )
        if taken:
            problems.append(
                _(
                    "These employees are already on another salary structure. "
                    "Remove them from it first, or change their contract: "
                    "%(names)s"
                )
                % {
                    "names": ", ".join(
                        f"{employee} ({structure})" for employee, structure in taken
                    )
                }
            )
        if problems:
            raise forms.ValidationError({"employees": problems})

        # One basic pay component per structure.
        flagged = [
            allowance
            for allowance in (cleaned_data.get("allowances") or [])
            if getattr(allowance, "is_basic_pay", False)
        ]
        if len(flagged) > 1:
            raise forms.ValidationError(
                {
                    "allowances": _(
                        "A structure can have only one basic pay component. "
                        "Marked as basic pay: %(names)s"
                    )
                    % {"names": ", ".join(str(one) for one in flagged)}
                }
            )

        # The component set has to agree with what the mode says the contract
        # wage means. Checked here rather than in Model.clean() because the M2M
        # is not populated during model validation.
        from payroll.methods.structure_rules import structure_problems

        problems = structure_problems(
            cleaned_data.get("structure_mode"),
            cleaned_data.get("allowances") or [],
            cleaned_data.get("deductions") or [],
        )
        if problems:
            raise forms.ValidationError({"allowances": problems})

        return cleaned_data

    def save(self, commit=True):

        previous_allowances = (
            set(self.instance.allowances.all()) if self.instance.pk else set()
        )
        previous_deductions = (
            set(self.instance.deductions.all()) if self.instance.pk else set()
        )
        previous_employees = set(self._employees_on_structure())

        instance = super().save(commit=False)
        instance.save()

        submitted_allowances = set(self.cleaned_data.get("allowances") or [])
        submitted_deductions = set(self.cleaned_data.get("deductions") or [])
        submitted_employees = set(self.cleaned_data.get("employees") or [])

        for allowance in submitted_allowances - previous_allowances:
            instance.add_allowance(allowance)
        for allowance in previous_allowances - submitted_allowances:
            instance.remove_allowance(allowance)

        for deduction in submitted_deductions - previous_deductions:
            instance.add_deduction(deduction)
        for deduction in previous_deductions - submitted_deductions:
            instance.remove_deduction(deduction)

        for employee in submitted_employees - previous_employees:
            contract = employee.contract_set.filter(contract_status="active").first()
            if contract:
                contract.set_salary_structure(instance)
        for employee in previous_employees - submitted_employees:
            contract = employee.contract_set.filter(
                contract_status="active", salary_structure_id=instance
            ).first()
            if contract:
                contract.set_salary_structure(None)

        return instance


class QuickAllowanceForm(ModelForm):
    """
    Minimal Allowance create form, used for the dynamic "create new allowance"
    option inside the Salary Structure form.
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = Allowance
        fields = ["title", "is_taxable", "is_fixed", "amount", "based_on", "rate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].required = True
        self.instance.include_active_employees = False


class QuickDeductionForm(ModelForm):
    """
    Minimal Deduction create form, used for the dynamic "create new deduction"
    option inside the Salary Structure form.
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = Deduction
        fields = [
            "title",
            "is_pretax",
            "is_fixed",
            "amount",
            "based_on",
            "rate",
            "employer_rate",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].required = True
        self.instance.include_active_employees = False


class PayslipForm(ModelForm):
    """
    Form for Payslip
    """

    cols = {
        "employee_id": 12,
        "start_date": 12,
        "end_date": 12,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_contracts = Contract.objects.filter(contract_status="active")
        self.fields["employee_id"].choices = [
            (contract.employee_id.id, contract.employee_id)
            for contract in active_contracts
            if contract.employee_id.is_active
        ]
        self.fields["employee_id"].widget.attrs.update(
            {
                "hx-get": "/payroll/check-contract-start-date",
                "hx-target": "#contractStartDateDiv",
                "hx-include": "#payslipCreateForm",
                "hx-trigger": "change delay:300ms",
                "hx-swap": "innerHTML",
            }
        )
        if self.instance.pk is None:
            self.initial["start_date"] = datetime.date.today().replace(day=1)
            self.initial["end_date"] = datetime.date.today()

    class Meta:
        """
        Meta class for additional options
        """

        model = payroll.models.models.Payslip
        fields = [
            "employee_id",
            "start_date",
            "end_date",
        ]
        exclude = ["is_active"]
        widgets = {
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "hx-get": "/payroll/check-contract-start-date",
                    "hx-target": "#contractStartDateDiv",
                    "hx-include": "#payslipCreateForm",
                    "hx-trigger": "change delay:300ms",
                    "hx-swap": "innerHTML",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


class GeneratePayslipForm(HorillaForm):
    """
    Form for Payslip
    """

    group_name = forms.CharField(
        label="Batch name",
        required=False,
        # help_text="Enter +-something if you want to generate payslips by batches",
    )
    employee_id = HorillaMultiSelectField(
        queryset=Employee.objects.none(),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
        ),
        label="Employee",
        required=True,
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        today = datetime.date.today()
        if end_date < start_date:
            raise forms.ValidationError(
                {
                    "end_date": "The end date must be greater than or equal to the start date."
                }
            )
        if start_date > today:
            raise forms.ValidationError(
                {"end_date": "The start date cannot be in the future."}
            )

        if end_date > today:
            raise forms.ValidationError(
                {"end_date": "The end date cannot be in the future."}
            )
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_id"].queryset = Employee.objects.filter(
            is_active=True,
            contract_set__isnull=False,
            contract_set__contract_status="active",
        )
        self.fields["employee_id"].widget.attrs.update(
            {"class": "oh-select oh-select-2", "id": uuid.uuid4()}
        )
        self.fields["start_date"].widget.attrs.update({"class": "oh-input w-100"})
        self.fields["group_name"].widget.attrs.update({"class": "oh-input w-100"})
        self.fields["end_date"].widget.attrs.update({"class": "oh-input w-100"})
        self.initial["start_date"] = datetime.date.today().replace(day=1)
        self.initial["end_date"] = datetime.date.today()

    class Meta:
        """
        Meta class for additional options
        """

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


class PayrollSettingsForm(ModelForm):
    """
    Form for PayrollSettings model
    """

    class Meta:
        """
        Meta class for additional options
        """

        model = models.PayrollSettings
        fields = ["currency_symbol", "position"]
        widgets = {
            "position": forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        }


excel_columns = [
    ("employee_id", _("Employee")),
    ("group_name", _("Batch")),
    ("start_date", _("Start Date")),
    ("end_date", _("End Date")),
    ("contract_wage", _("Contract Wage")),
    ("basic_pay", _("Basic Pay")),
    ("gross_pay", _("Gross Pay")),
    ("deduction", _("Deduction")),
    ("net_pay", _("Net Pay")),
    ("status", _("Status")),
    ("employee_id__employee_bank_details__bank_name", _("Bank Name")),
    ("employee_id__employee_bank_details__branch", _("Branch")),
    ("employee_id__employee_bank_details__account_number", _("Account Number")),
    ("employee_id__employee_bank_details__any_other_code1", _("Bank Code #1")),
    ("employee_id__employee_bank_details__any_other_code2", _("Bank Code #2")),
    ("employee_id__employee_bank_details__country", _("Country")),
    ("employee_id__employee_bank_details__state", _("State")),
    ("employee_id__employee_bank_details__city", _("City")),
]


class PayslipExportColumnForm(forms.Form):
    selected_fields = forms.MultipleChoiceField(
        choices=excel_columns,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "employee_id",
            "group_name",
            "start_date",
            "end_date",
            "basic_pay",
            "gross_pay",
            "net_pay",
            "status",
        ],
    )


exclude_fields = ["id", "contract_document", "is_active", "note", "note", "created_at"]


class ContractExportFieldForm(forms.Form):
    model_fields = Contract._meta.get_fields()
    field_choices = [
        (field.name, field.verbose_name)
        for field in model_fields
        if hasattr(field, "verbose_name") and field.name not in exclude_fields
    ]
    selected_fields = forms.MultipleChoiceField(
        choices=field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "contract_name",
            "employee_id",
            "contract_start_date",
            "contract_end_date",
            "wage_type",
            "wage",
            "filing_status",
            "contract_status",
        ],
    )


def rate_validator(value):
    """
    Percentage validator
    """
    if value < 0:
        raise ValidationError(_("Rate must be greater than 0"))
    if value > 100:
        raise ValidationError(_("Rate must be less than 100"))


class BonusForm(Form):
    """
    Bonus Creating Form
    """

    title = forms.CharField(max_length=100)
    date = forms.DateField(widget=forms.DateInput(), required=False)
    employee_id = forms.IntegerField(label="Employee", widget=forms.HiddenInput())
    is_fixed = forms.BooleanField(
        label="Is Fixed", initial=True, required=False, widget=forms.CheckboxInput()
    )
    amount = forms.DecimalField(
        label="Amount",
        required=False,
    )
    based_on = forms.ChoiceField(choices=[("BASIC_PAY", "Basic Pay")], required=False)
    rate = forms.FloatField(
        validators=[
            rate_validator,
        ],
        label="Rate",
        required=False,
    )

    def save(self, commit=True):
        title = self.cleaned_data["title"]
        date = self.cleaned_data["date"]
        employee_id = self.cleaned_data["employee_id"]
        amount = self.cleaned_data["amount"]
        is_fixed = self.cleaned_data["is_fixed"]
        rate = self.cleaned_data["rate"]

        bonus = Allowance()
        bonus.title = title
        bonus.one_time_date = date
        bonus.only_show_under_employee = True
        bonus.amount = amount
        bonus.is_fixed = is_fixed
        bonus.rate = rate
        bonus.save()
        bonus.include_active_employees = False
        bonus.specific_employees.set([employee_id])
        bonus.save()

        return bonus

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": "oh-input w-100"})
        self.fields["date"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )
        self.fields["is_fixed"].widget.attrs.update({"class": "oh-switch__checkbox"})


class PayslipAllowanceForm(BonusForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].widget = forms.HiddenInput()


class PayslipDeductionForm(ModelForm):
    """
    Bonus Creating Form
    """

    verbose_name = _("Deduction")

    class Meta:
        model = Deduction
        fields = [
            "title",
            "one_time_date",
            "update_compensation",
            "is_tax",
            "is_pretax",
            "is_fixed",
            "amount",
            "based_on",
            "rate",
            "employer_rate",
            "has_max_limit",
            "maximum_amount",
        ]
        widgets = {
            "one_time_date": forms.HiddenInput(),
        }

    # employee_id = forms.IntegerField(label="Employee", widget=forms.HiddenInput())

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("one_time_deduction.html", context)
        return table_html


class LoanAccountForm(ModelForm):
    """
    LoanAccountForm
    """

    verbose_name = _("Loans & Salary Advances")
    cols = {
        "description": 12,
    }

    class Meta:
        model = LoanAccount
        fields = "__all__"
        exclude = ["is_active", "settled_date"]
        widgets = {
            "provided_date": forms.DateTimeInput(attrs={"type": "date"}),
            "installment_start_date": forms.DateTimeInput(attrs={"type": "date"}),
        }

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["provided_date"] = str(datetime.date.today())
            self.initial["installment_start_date"] = str(datetime.date.today())
        if self.instance.pk:
            self.verbose_name = self.instance.title
            # <input type="date"> needs YYYY-MM-DD; the DateTimeInput widget
            # doesn't render date objects that way, so pass strings.
            if self.instance.provided_date:
                self.initial["provided_date"] = str(self.instance.provided_date)
            if self.instance.installment_start_date:
                self.initial["installment_start_date"] = str(
                    self.instance.installment_start_date
                )
            # Edit shows the same fields as create; the ones that must not
            # change any more are locked (disabled) instead of removed, so
            # both forms keep an identical layout across the Loan / Salary
            # Advance / Fine tabs.
            locked_fields = []
            if Payslip.objects.filter(
                installment_ids__in=list(
                    self.instance.deduction_ids.values_list("id", flat=True)
                )
            ).exists():
                # Once an installment is on a paid payslip the schedule can
                # no longer be regenerated (see payroll.signals
                # create_installments), so these become read-only.
                locked_fields += [
                    "employee_id",
                    "loan_amount",
                    "installments",
                    "installment_amount",
                    "installment_start_date",
                ]
            for field_name in locked_fields:
                if field_name not in self.fields:
                    continue
                field = self.fields[field_name]
                field.disabled = True
                if field_name == "employee_id":
                    # Disabled selects normally render as bare text (see
                    # .oh-select:disabled in the theme) - opt this one back
                    # into a boxed look via oh-select--boxed-locked so it
                    # doesn't stand out next to the other fields here.
                    attrs = field.widget.attrs
                    attrs["class"] = (
                        attrs.get("class", "") + " oh-select--boxed-locked"
                    ).strip()

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean(*args, **kwargs)

        start_date = cleaned_data.get("installment_start_date")
        provided_date = cleaned_data.get("provided_date")
        dates_touched = (
            not self.instance.pk
            or "installment_start_date" in self.changed_data
            or "provided_date" in self.changed_data
        )
        if (
            start_date
            and provided_date
            and dates_touched
            and start_date < provided_date
        ):
            raise forms.ValidationError(
                _(
                    "Installment start date should be greater than or equal to provided date"
                )
            )
        if cleaned_data.get("installments") != None:
            if cleaned_data.get("installments") <= 0:
                raise forms.ValidationError(
                    _("Installments needs to be a positive integer")
                )

        return cleaned_data


class AssetFineForm(LoanAccountForm):
    verbose_name = _("Asset Fine")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["loan_amount"].label = _("Fine Amount")
        self.fields["provided_date"].label = _("Fine Date")

        fields_to_exclude = [
            "employee_id",
            "type",
        ]
        for field in fields_to_exclude:
            if field in self.fields:
                del self.fields[field]
        field_order = [
            "title",
            "loan_amount",
            "provided_date",
            "description",
            "installments",
            "installment_start_date",
            "installment_amount",
            "settled",
        ]

        self.fields = {
            field: self.fields[field] for field in field_order if field in self.fields
        }


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result[0] if result else None


class ReimbursementForm(ModelForm):
    """
    Optimized Reimbursement / Encashment Form
    """

    cols = {"description": 12}

    verbose_name = "Reimbursement / Encashment"

    class Meta:
        model = Reimbursement
        fields = "__all__"
        exclude = ["is_active", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request = getattr(horilla_middlewares._thread_locals, "request", None)
        self.employee = self.get_employee()  # 819

        if not self.instance.pk:
            self.initial["allowance_on"] = str(datetime.date.today())

        self.initial["employee_id"] = self.employee.id if self.employee else None

        # When opened from a specific tab (Reimbursements / Leave Encashments /
        # Bonus Encashments), the tab's own Create button passes ?type=... so
        # the record being created always matches the tab it was opened from -
        # the Type field is then locked instead of shown as a free choice.
        self.fixed_type = (
            self.request.GET.get("type")
            if self.request and not self.instance.pk
            else None
        )
        if self.fixed_type:
            self.initial["type"] = self.fixed_type

        self.configure_fields()

    def get_employee(self):
        """Resolves employee either from form data or request."""
        if hasattr(self.instance, "employee_id") and self.instance.employee_id:
            return self.instance.employee_id

        employee_qs = self.fields["employee_id"].queryset
        employee_id = self.data.get("employee_id") if self.data else None

        if employee_id and (emp := employee_qs.filter(id=employee_id).first()):
            return emp

        if self.request and (emp := self.request.user.employee_get):
            if not self.instance.pk and emp in employee_qs:
                return emp
            if self.instance.pk and emp.id == self.instance.employee_id:
                return emp

        return employee_qs.first()

    def get_encashable_leaves(self, employee):
        LeaveType = get_horilla_model_class(app_label="leave", model="leavetype")
        return LeaveType.objects.filter(
            employee_available_leave__employee_id=employee,
            employee_available_leave__total_leave_days__gte=1,
            is_encashable=True,
        )

    def configure_fields(self):
        exclude_fields = []

        if self.request and not self.request.user.has_perm("payroll.add_reimbursement"):
            exclude_fields.append("employee_id")

        self.setup_leave_fields()

        self.fields["type"].widget.attrs["onchange"] = "toggleReimbursmentType($(this))"
        self.fields["employee_id"].widget.attrs[
            "onchange"
        ] = "getAssignedLeave($(this))"

        self.fields["allowance_on"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )

        self.fields["attachment"] = MultipleFileField(label="Attachments")
        self.fields["attachment"].widget.attrs["accept"] = ".jpg, .jpeg, .png, .pdf"

        # Also hidden when editing - which type a record is doesn't change
        # after creation, so there's nothing to pick here either.
        if self.fixed_type or self.instance.pk:
            self.fields["type"].widget = forms.HiddenInput()

        self.exclude_fields_by_type(exclude_fields)

        for field in exclude_fields:
            self.fields.pop(field, None)

    def setup_leave_fields(self):
        """Setup leave-related fields only if leave app is installed."""
        if not apps.is_installed("leave") or not self.employee:
            return

        AvailableLeave = get_horilla_model_class(
            app_label="leave", model="availableleave"
        )
        assigned_leaves = self.get_encashable_leaves(self.employee)

        self.assigned_leaves = AvailableLeave.objects.filter(
            leave_type_id__in=assigned_leaves, employee_id=self.employee
        )
        self.fields["leave_type_id"].queryset = assigned_leaves
        self.fields["leave_type_id"].empty_label = None
        self.fields["employee_id"].empty_label = None

    def exclude_fields_by_type(self, exclude_fields):
        """Determine which fields to exclude based on type."""
        type = (
            self.data.get("type")
            if self.data
            else (self.fixed_type or (self.instance.type if self.instance else None))
        )
        is_edit = self.instance and self.instance.pk

        if type == "reimbursement" and (is_edit or self.data or self.fixed_type):
            exclude_fields += [
                "leave_type_id",
                "cfd_to_encash",
                "ad_to_encash",
                "bonus_to_encash",
            ]
        elif type == "leave_encashment" and (is_edit or self.data or self.fixed_type):
            exclude_fields += ["attachment", "amount", "bonus_to_encash"]
        elif type == "bonus_encashment" and (is_edit or self.data or self.fixed_type):
            exclude_fields += [
                "attachment",
                "amount",
                "leave_type_id",
                "cfd_to_encash",
                "ad_to_encash",
            ]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def clean(self):
        cleaned_data = super().clean()

        type_ = cleaned_data.get("type")
        employee = cleaned_data.get("employee_id")

        if not type_ or not employee:
            return cleaned_data

        if type_ == "bonus_encashment":
            bonus_to_encash = (
                self.instance.bonus_to_encash
                if self.instance.pk
                else cleaned_data.get("bonus_to_encash")
            )
            available_points = BonusPoint.objects.filter(employee_id=employee).first()

            if bonus_to_encash is not None:
                if bonus_to_encash <= 0:
                    self.add_error(
                        "bonus_to_encash", "Points must be greater than zero to redeem."
                    )
                elif not available_points or available_points.points < bonus_to_encash:
                    self.add_error(
                        "bonus_to_encash", "Not enough bonus points to redeem"
                    )

        elif type_ == "leave_encashment":
            leave_type = (
                self.instance.leave_type_id
                if self.instance.pk
                else cleaned_data.get("leave_type_id")
            )
            cfd_to_encash = (
                self.instance.cfd_to_encash
                if self.instance.pk
                else cleaned_data.get("cfd_to_encash", 0)
            )
            ad_to_encash = (
                self.instance.ad_to_encash
                if self.instance.pk
                else cleaned_data.get("ad_to_encash", 0)
            )

            if not leave_type:
                self.add_error("leave_type_id", "This field is required")
            else:
                encashable = self.get_encashable_leaves(employee)
                if leave_type not in encashable:
                    self.add_error("leave_type_id", "This leave type is not encashable")
                else:
                    AvailableLeave = get_horilla_model_class("leave", "availableleave")
                    available_leave = AvailableLeave.objects.filter(
                        leave_type_id=leave_type, employee_id=employee
                    ).first()

                    if available_leave:
                        if cfd_to_encash < 0:
                            self.add_error(
                                "cfd_to_encash", _("Value can't be negative.")
                            )
                        elif cfd_to_encash > available_leave.carryforward_days:
                            self.add_error(
                                "cfd_to_encash",
                                _("Not enough carryforward days to redeem"),
                            )

                        if ad_to_encash < 0:
                            self.add_error(
                                "ad_to_encash", _("Value can't be negative.")
                            )
                        elif ad_to_encash > available_leave.available_days:
                            self.add_error(
                                "ad_to_encash", _("Not enough available days to redeem")
                            )

        return cleaned_data

    def save(self, commit: bool = True) -> Any:
        multiple_attachment_ids = []
        is_new = not self.instance.pk
        attachments = self.files.getlist("attachment")

        if attachments:
            self.instance.attachment = attachments[0]

        instance = super().save(commit=commit)

        if attachments:
            attachment_objs = [
                ReimbursementMultipleAttachment(attachment=file) for file in attachments
            ]
            created_attachments = ReimbursementMultipleAttachment.objects.bulk_create(
                attachment_objs
            )
            multiple_attachment_ids = [obj.pk for obj in created_attachments]
            instance.other_attachments.add(*multiple_attachment_ids)

        if is_new:
            try:
                manager = instance.employee_id.employee_work_info.reporting_manager_id
                if manager and manager.employee_user_id:
                    notify.send(
                        instance.employee_id,  # 816
                        recipient=manager.employee_user_id,
                        verb=gettext_noop(
                            "You have a new reimbursement request to approve for %(employee)s."
                        ),
                        verb_params={"employee": str(instance.employee_id)},
                        icon="information",
                        redirect=f"/payroll/view-reimbursement?id={instance.id}",
                    )
            except Exception:
                pass

        return instance, attachments


class ConditionForm(ModelForm):
    """
    Multiple condition form
    """

    class Meta:
        model = Allowance
        fields = [
            "field",
            "condition",
            "value",
        ]


# ===========================Auto payslip generate================================
class PayslipAutoGenerateForm(ModelForm):
    class Meta:
        model = PayslipAutoGenerate
        fields = ["generate_day", "company_id", "auto_generate"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_company_id = horilla_middlewares.get_selected_company()
        if active_company_id and active_company_id != "all":
            self.fields["company_id"].queryset = Company.objects.filter(
                id=active_company_id
            )

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html
