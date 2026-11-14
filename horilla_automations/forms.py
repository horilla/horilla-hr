"""
horilla_automations/forms.py
"""

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla_automations.methods.methods import generate_choices
from horilla_automations.models import MODEL_CHOICES, MailAutomation
from horilla_widgets.forms import default_select_option_template
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget


class AutomationForm(ModelForm):
    """
    AutomationForm
    """

    condition_html = forms.CharField(widget=forms.HiddenInput())
    condition_querystring = forms.CharField(widget=forms.HiddenInput())

    cols = {"template_attachments": 12}

    class Meta:
        model = MailAutomation
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- Field: also_sent_to ---
        self.fields["also_sent_to"] = HorillaMultiSelectField(
            queryset=Employee.objects.all(),
            required=False,
            widget=HorillaMultiSelectWidget(
                filter_route_name="employee-widget-filter",
                filter_class=EmployeeFilter,
                filter_instance_context_name="f",
                filter_template_path="employee_filters.html",
                instance=self.instance,
            ),
            label=_("Also Sent to"),
            help_text=_("The employees selected here will receive the email as Cc."),
        )

        # --- Determine model for generate_choices ---
        model = getattr(self.instance, "model", None) or self.data.get("model")
        mail_to, mail_details_choice = [], []

        if model:
            choices = generate_choices(model)
            mail_to, mail_details_choice = choices[0], choices[1]

        # --- Field: mail_to ---
        self.fields["mail_to"] = forms.MultipleChoiceField(
            choices=mail_to,
            initial=self.data.get("mail_to"),
            widget=forms.SelectMultiple(attrs={"class": "oh-select oh-select-2 w-100"}),
            label=_("Mail To"),
        )

        # --- Field: mail_details ---
        self.fields["mail_details"] = forms.ChoiceField(
            choices=mail_details_choice,
            help_text=_(
                "Fill mail template details (receiver/instance, `self` will be the person who triggers the automation)"
            ),
            label=_("Mail Details"),
        )
        self.fields["mail_details"].widget.attrs = {
            "class": "oh-select oh-select-2 w-100"
        }

        # --- Field: model ---
        self.fields["model"].choices = [("", "Select model")] + sorted(
            set(MODEL_CHOICES)
        )
        self.fields["model"].widget.attrs["onchange"] = "getToMail($(this))"

        # --- Field: mail_template ---
        self.fields["mail_template"].empty_label = "----------"

        # --- Field: condition fields ---
        self.fields["condition"].initial = getattr(
            self.instance, "condition", None
        ) or self.data.get("condition")
        self.fields["condition_html"].initial = getattr(
            self.instance, "condition_html", None
        ) or self.data.get("condition_html")
        self.fields["condition_querystring"].initial = getattr(
            self.instance, "condition_querystring", None
        ) or self.data.get("condition_querystring")

        # --- Apply option template name for all select fields ---
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.option_template_name = default_select_option_template

        # --- Re-insert is_active field to ensure order ---
        self.fields["is_active"] = self.fields.pop("is_active")

    def clean(self):
        cleaned_data = super().clean()
        if isinstance(self.fields["also_sent_to"], HorillaMultiSelectField):
            self.errors.pop("also_sent_to", None)

            employee_data = self.fields["also_sent_to"].queryset.filter(
                id__in=self.data.getlist("also_sent_to")
            )
            cleaned_data["also_sent_to"] = employee_data

        return cleaned_data

    def save(self, commit: bool = ...) -> Any:
        self.instance: MailAutomation = self.instance
        condition_querystring = self.cleaned_data["condition_querystring"]
        condition_html = self.cleaned_data["condition_html"]
        mail_to = self.data.getlist("mail_to")
        self.instance.mail_to = str(mail_to)
        self.instance.mail_details = self.data["mail_details"]
        self.instance.condition_querystring = condition_querystring
        self.instance.condition_html = condition_html
        return super().save(commit)
