from django import forms
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm

from .models import OidcProvider


class OidcProviderForm(ModelForm):
    """
    company comes from the admin's currently selected company and slug is
    generated on first save, so both are excluded on purpose.

    client_secret is a write-only PasswordInput, matching
    horilla_ldap.LDAPSettingsForm's bind_password convention -- masked in
    the UI, and here (unlike LDAP's plaintext bind_password) the
    underlying storage is genuinely encrypted, not just hidden on screen.
    """

    client_secret = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "oh-input w-100"}, render_value=False),
        required=True,
    )

    class Meta:
        model = OidcProvider
        fields = [
            "is_enabled",
            "display_name",
            "issuer",
            "client_id",
            "client_secret",
            "scopes",
            "authorization_endpoint",
            "token_endpoint",
            "jwks_uri",
            "skip_2fa_for_sso",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An existing config already has a secret; editing the other fields
        # should not force re-entering it. A fresh config has none to keep.
        if self.instance and self.instance.pk:
            self.fields["client_secret"].required = False
            self.fields["client_secret"].help_text = _("Leave blank to keep the current secret.")

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_secret = self.cleaned_data.get("client_secret")
        if new_secret:
            instance.client_secret = new_secret
        if commit:
            instance.save()
        return instance

    def as_p(self):
        return render_to_string("common_form.html", {"form": self})
