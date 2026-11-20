import re

from django import forms
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from horilla_sso import providers
from horilla_sso.models import GoogleSSOSettings, MicrosoftSSOSettings, SSOLoginSettings
from horilla_sso.providers import GUID

TENANT = re.compile(
    r"^(organizations|common|consumers|[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+|[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)

DOMAIN = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
)

GOOGLE_CLIENT = re.compile(r"^\d+-[a-z0-9]+\.apps\.googleusercontent\.com$", re.I)


class SSOSettingsForm(ModelForm):
    """What every provider's settings page shares: the secret, the domains and the login page switch."""

    label = ""
    client_secret = forms.CharField(
        label=_("Client Secret"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password"}, render_value=True
        ),
        help_text=_("The Saved Secret Is Filled In. Replace It To Change It."),
    )
    hide_password_form = forms.BooleanField(
        label=_("Hide Password Sign-In"),
        required=False,
        help_text=_(
            "Shows Only The Sign-In Buttons. A Link On The Login Page Still Opens The Password Form."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["client_secret"] = self.instance.client_secret
        self.initial["hide_password_form"] = SSOLoginSettings.hides_password_form()

    def clean_client_secret(self):
        """The secret value; the usual slip is a copy with spaces or line breaks in it."""
        secret = (self.cleaned_data.get("client_secret") or "").strip()
        if re.search(r"\s", secret):
            raise forms.ValidationError(
                _("The Client Secret Cannot Contain Spaces Or Line Breaks.")
            )
        return secret

    def clean_allowed_domains(self):
        """Domains only, such as contoso.com: cleaned up, lower-cased and without repeats."""
        raw = self.cleaned_data.get("allowed_domains") or ""
        domains = []
        for entry in re.split(r"[,;\s]+", raw):
            entry = entry.strip().lower().lstrip("@")
            if not entry:
                continue
            if "@" in entry:
                raise forms.ValidationError(
                    _(
                        "Enter Domains Only, Like contoso.com, Not Email Addresses (%(entry)s)."
                    )
                    % {"entry": entry}
                )
            if not DOMAIN.match(entry):
                raise forms.ValidationError(
                    _(
                        "%(entry)s Is Not A Valid Domain. Use Something Like contoso.com."
                    )
                    % {"entry": entry}
                )
            if entry not in domains:
                domains.append(entry)
        cleaned = ", ".join(domains)
        if len(cleaned) > 500:
            raise forms.ValidationError(
                _("Too Many Domains. Keep It Under 500 Characters.")
            )
        return cleaned

    def _another_is_ready(self):
        return any(
            provider.key != self.instance.provider_key
            for provider, _config in providers.ready_providers()
        )

    def clean(self):
        data = super().clean()
        has_secret = bool(
            data.get("client_secret") or self.instance.client_secret_encrypted
        )
        name = {"provider": self.label}
        if data.get("is_enabled"):
            if not data.get("client_id"):
                self.add_error(
                    "client_id",
                    _("Enter The Client ID To Enable %(provider)s Sign-In.") % name,
                )
            if not has_secret:
                self.add_error(
                    "client_secret",
                    _("Enter The Client Secret To Enable %(provider)s Sign-In.") % name,
                )
        if (
            data.get("hide_password_form")
            and not data.get("is_enabled")
            and not self._another_is_ready()
        ):
            self.add_error(
                "hide_password_form",
                _("Turn On A Sign-In Provider Before Hiding The Password Form."),
            )
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        secret = self.cleaned_data.get("client_secret")
        if secret:
            instance.client_secret = secret
        if commit:
            instance.save()
            login_settings = SSOLoginSettings.objects.first() or SSOLoginSettings()
            login_settings.hide_password_form = self.cleaned_data.get(
                "hide_password_form", False
            )
            login_settings.save()
        return instance

    def as_p(self):
        """Render the form fields with the shared settings form layout."""
        return render_to_string("common_form.html", {"form": self})


class MicrosoftSSOSettingsForm(SSOSettingsForm):
    """The Microsoft sign-in settings; the saved client secret is filled in, and kept when the box is emptied."""

    label = "Microsoft"

    class Meta:
        model = MicrosoftSSOSettings
        fields = [
            "is_enabled",
            "tenant_id",
            "client_id",
            "client_secret",
            "allowed_domains",
            "hide_password_form",
        ]

    def clean_tenant_id(self):
        """A directory ID, a domain, or one of Microsoft's names; nothing that could change the address."""
        tenant = (self.cleaned_data.get("tenant_id") or "").strip()
        if not TENANT.match(tenant):
            raise forms.ValidationError(
                _(
                    "Use The Directory (Tenant) ID, A Domain Such As contoso.com, Or Organizations, Common Or Consumers."
                )
            )
        return tenant

    def clean_client_id(self):
        """Azure always gives the Application (client) ID as a long ID like 12345678-abcd-...; anything else is a slip."""
        client_id = (self.cleaned_data.get("client_id") or "").strip()
        if client_id and not GUID.match(client_id):
            raise forms.ValidationError(
                _(
                    "The Client ID Is A Long ID Like 12345678-1234-1234-1234-123456789abc."
                    " Copy The Application (Client) ID From The Azure Overview Page."
                )
            )
        return client_id.lower()

    def clean_client_secret(self):
        """The secret Value; the other usual slip is pasting the Secret ID next to it."""
        secret = super().clean_client_secret()
        if secret and GUID.match(secret):
            raise forms.ValidationError(
                _(
                    "This Looks Like The Secret ID. Copy The Value Column Of The Client Secret Instead."
                )
            )
        return secret


class GoogleSSOSettingsForm(SSOSettingsForm):
    """The Google sign-in settings; sign-in is limited to the Workspace domains entered here."""

    label = "Google"

    class Meta:
        model = GoogleSSOSettings
        fields = [
            "is_enabled",
            "client_id",
            "client_secret",
            "allowed_domains",
            "hide_password_form",
        ]

    def clean_client_id(self):
        """Google gives the client ID as 1234567890-abc123.apps.googleusercontent.com."""
        client_id = (self.cleaned_data.get("client_id") or "").strip()
        if client_id and not GOOGLE_CLIENT.match(client_id):
            raise forms.ValidationError(
                _(
                    "The Client ID Looks Like 1234567890-abc123.apps.googleusercontent.com."
                    " Copy It From The OAuth Client In Google Cloud Console."
                )
            )
        return client_id.lower()

    def clean_client_secret(self):
        secret = super().clean_client_secret()
        if secret and GOOGLE_CLIENT.match(secret):
            raise forms.ValidationError(
                _(
                    "This Looks Like The Client ID. Copy The Client Secret Of The OAuth Client Instead."
                )
            )
        return secret

    def clean(self):
        data = super().clean()
        if data.get("is_enabled") and not data.get("allowed_domains"):
            self.add_error(
                "allowed_domains",
                _("Enter At Least One Workspace Domain To Enable Google Sign-In."),
            )
        return data


FORMS = {"microsoft": MicrosoftSSOSettingsForm, "google": GoogleSSOSettingsForm}
