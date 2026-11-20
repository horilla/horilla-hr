from django.db import models
from django.utils.translation import gettext_lazy as _

from horilla_sso import crypto


class MicrosoftSSOSettings(models.Model):
    """The company-wide Microsoft (Entra ID) sign-in settings. One row."""

    is_enabled = models.BooleanField(
        default=False, verbose_name=_("Enable Microsoft Sign-In")
    )
    tenant_id = models.CharField(
        max_length=255,
        default="organizations",
        verbose_name=_("Tenant ID"),
        help_text=_(
            "The Directory (Tenant) ID, Or Organizations To Allow Any Work Account."
        ),
    )
    client_id = models.CharField(
        max_length=255, blank=True, verbose_name=_("Client ID")
    )
    client_secret_encrypted = models.TextField(blank=True, editable=False)
    allowed_domains = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Allowed Email Domains"),
        help_text=_("Comma Separated. Leave Empty To Allow Any Domain."),
    )

    provider_key = "microsoft"

    class Meta:
        verbose_name = "Microsoft SSO Settings"

    def __str__(self):
        return "Microsoft SSO Settings"

    @property
    def client_secret(self):
        return crypto.decrypt(self.client_secret_encrypted)

    @client_secret.setter
    def client_secret(self, value):
        self.client_secret_encrypted = crypto.encrypt(value)

    @classmethod
    def current(cls):
        return cls.objects.first()

    def is_ready(self):
        """True when it is switched on and has everything the sign-in needs."""
        return bool(
            self.is_enabled and self.tenant_id and self.client_id and self.client_secret
        )

    def domains(self):
        return [
            d.strip().lower().lstrip("@")
            for d in self.allowed_domains.split(",")
            if d.strip()
        ]


class GoogleSSOSettings(models.Model):
    """The company-wide Google sign-in settings. One row; sign-in is limited to Workspace domains."""

    is_enabled = models.BooleanField(
        default=False, verbose_name=_("Enable Google Sign-In")
    )
    client_id = models.CharField(
        max_length=255, blank=True, verbose_name=_("Client ID")
    )
    client_secret_encrypted = models.TextField(blank=True, editable=False)
    allowed_domains = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Allowed Workspace Domains"),
        help_text=_(
            "Comma Separated. Only Accounts Of These Google Workspace Domains Can Sign In."
        ),
    )

    provider_key = "google"

    class Meta:
        verbose_name = "Google SSO Settings"

    def __str__(self):
        return "Google SSO Settings"

    @property
    def client_secret(self):
        return crypto.decrypt(self.client_secret_encrypted)

    @client_secret.setter
    def client_secret(self, value):
        self.client_secret_encrypted = crypto.encrypt(value)

    @classmethod
    def current(cls):
        return cls.objects.first()

    def is_ready(self):
        """True when it is switched on and has a client and at least one domain, which Google sign-in requires."""
        return bool(
            self.is_enabled and self.client_id and self.client_secret and self.domains()
        )

    def domains(self):
        return [
            d.strip().lower().lstrip("@")
            for d in self.allowed_domains.split(",")
            if d.strip()
        ]


class SSOLoginSettings(models.Model):
    """What the login page does for every single sign-on provider. One row."""

    hide_password_form = models.BooleanField(
        default=False,
        verbose_name=_("Hide Password Sign-In"),
        help_text=_(
            "Shows Only The Sign-In Buttons. A Link On The Login Page Still Opens The Password Form."
        ),
    )

    class Meta:
        verbose_name = "SSO Login Settings"

    def __str__(self):
        return "SSO Login Settings"

    @classmethod
    def hides_password_form(cls):
        row = cls.objects.first()
        return bool(row and row.hide_password_form)
