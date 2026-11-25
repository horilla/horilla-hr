"""Forms for the Firma e-signature integration."""

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from horilla_firma.models import FirmaSettings


class FirmaSettingsForm(ModelForm):
    """The settings page. Saved secrets are never written back into the page."""

    api_key = forms.CharField(
        label=_("Firma API Key"),
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_(
            "From the Firma dashboard, Settings, API Keys. Leave empty to keep the "
            "saved key."
        ),
    )
    webhook_secret = forms.CharField(
        label=_("Webhook Signing Secret"),
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_(
            "From the Firma dashboard, Settings, Webhook Configuration. Leave empty "
            "to keep the saved secret."
        ),
    )

    class Meta:
        model = FirmaSettings
        fields = ["is_enabled", "default_expiration_hours"]

    def _clean_secret(self, name, label):
        value = (self.cleaned_data.get(name) or "").strip()
        if re.search(r"\s", value):
            raise forms.ValidationError(
                _("The %(label)s cannot contain spaces or line breaks.")
                % {"label": label}
            )
        if len(value) > 500:
            raise forms.ValidationError(_("This value is too long."))
        return value

    def clean_api_key(self):
        return self._clean_secret("api_key", _("API key"))

    def clean_webhook_secret(self):
        return self._clean_secret("webhook_secret", _("webhook signing secret"))

    def clean_default_expiration_hours(self):
        hours = self.cleaned_data.get("default_expiration_hours")
        if hours is not None and hours < 1:
            raise forms.ValidationError(_("Enter 1 hour or more, or leave it empty."))
        return hours

    def clean(self):
        data = super().clean()
        has_key = bool(data.get("api_key") or self.instance.api_key)
        if data.get("is_enabled") and not has_key:
            self.add_error(
                "api_key", _("Enter the Firma API key to switch the integration on.")
            )
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("api_key"):
            instance.api_key = self.cleaned_data["api_key"]
        if self.cleaned_data.get("webhook_secret"):
            instance.webhook_secret = self.cleaned_data["webhook_secret"]
        if commit:
            instance.save()
        return instance


class SendForSignatureForm(forms.Form):
    """What the send form posts. Choices are checked again in the view."""

    mode = forms.ChoiceField(
        choices=[("template", _("Firma template")), ("document", _("Offer letter PDF"))]
    )
    template_id = forms.CharField(required=False, max_length=64)
    mail_template = forms.IntegerField(required=False)
    title = forms.CharField(required=False, max_length=255)
    expiration_hours = forms.IntegerField(required=False, min_value=1, max_value=8760)
    send_token = forms.CharField(max_length=64)
    confirm_uncertain = forms.BooleanField(required=False)
