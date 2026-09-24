"""
models.py

One OidcProvider row per Company: the IdP registration (issuer, client
credentials, endpoints) that company's employees sign in through.

A OneToOneField, not the nullable-FK-plus-two-UniqueConstraint shape
base.models.DefaultExportPermission uses for other per-company settings.
That shape exists to support a "same value for every company unless
overridden" global-fallback row -- there is no equivalent concept for an
OIDC registration: client_id/client_secret are inherently tied to one IdP
tenant, so "the OIDC config for all companies" is not a meaningful state.
OneToOneField enforces the actual requirement (at most one config per
company, and a config always belongs to exactly one company) with less
code than replicating a constraint pair built for a different problem.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from base.models import Company
from horilla.models import HorillaModel

from . import crypto


class OidcProvider(HorillaModel):
    """
    OIDC identity provider registration for one company.
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="oidc_provider",
        verbose_name=_("Company"),
    )
    slug = models.SlugField(
        unique=True,
        editable=False,
        help_text=_("Generated from the company name. Used in the SSO login URL."),
    )
    display_name = models.CharField(
        max_length=100,
        default=_("Single Sign-On"),
        verbose_name=_("Button label"),
        help_text=_('Shown on the login page, e.g. "Sign in with Okta".'),
    )
    is_enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))

    issuer = models.URLField(
        verbose_name=_("Issuer"),
        help_text=_("The OIDC issuer URL, e.g. https://acme.okta.com"),
    )
    client_id = models.CharField(max_length=255, verbose_name=_("Client ID"))
    # Stored encrypted (see crypto.py). The `client_secret` property below is
    # what every caller should read/write -- never touch this column directly.
    _client_secret = models.TextField(db_column="client_secret", verbose_name=_("Client secret"))

    # Manual overrides for IdPs whose discovery document is missing, wrong, or
    # slow to reach. Left blank, the callback fetches these from
    # `{issuer}/.well-known/openid-configuration` and caches the result.
    authorization_endpoint = models.URLField(blank=True, verbose_name=_("Authorization endpoint (override)"))
    token_endpoint = models.URLField(blank=True, verbose_name=_("Token endpoint (override)"))
    jwks_uri = models.URLField(blank=True, verbose_name=_("JWKS URI (override)"))

    scopes = models.CharField(
        max_length=255,
        default="openid email profile",
        verbose_name=_("Scopes"),
    )
    skip_2fa_for_sso = models.BooleanField(
        default=True,
        verbose_name=_("Skip local 2FA for SSO sessions"),
        help_text=_(
            "The identity provider is presumed to already enforce its own "
            "MFA. Turn this off to also require Horilla's email OTP after "
            "SSO login."
        ),
    )

    objects = models.Manager()

    # HorillaModel.clean_fields() runs has_xss() over every CharField/TextField
    # on every save. That check is built for user-authored freeform text and
    # matches on patterns like `on\w+=` (inline event handlers) -- a Fernet
    # token is long, effectively-random base64, and a coincidental match on
    # that pattern is a near-certainty over enough saves, not a rare edge
    # case. Found by the functional test suite hitting a real ValidationError
    # on an otherwise-correct save. xss_exempt_fields is the sanctioned
    # escape hatch clean_fields() already supports for exactly this: a field
    # whose content is never rendered as HTML and was never user-authored
    # text in the first place.
    xss_exempt_fields = {"_client_secret"}

    class Meta:
        verbose_name = _("OIDC Provider")
        verbose_name_plural = _("OIDC Providers")

    def __str__(self):
        return f"{self.display_name} ({self.company})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.company.company) or "company"
            slug = base_slug
            suffix = 1
            while OidcProvider.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                suffix += 1
                slug = f"{base_slug}-{suffix}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def client_secret(self) -> str:
        return crypto.decrypt(self._client_secret)

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        self._client_secret = crypto.encrypt(value)
