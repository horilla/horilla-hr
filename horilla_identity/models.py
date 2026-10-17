"""
models.py

ExternalIdentity is the stable link between an identity at an external
provider and a Horilla user. Matching on e-mail alone is not enough: an IdP
can rename or reuse an address, and the next login or provisioning call would
then land on whichever employee owns that address now. The (source, provider,
subject) triple does not change when the e-mail does.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import Company
from horilla_auth.models import HorillaUser


class ExternalIdentity(models.Model):
    SOURCE_SCIM = "scim"
    SOURCE_SAML = "saml"
    SOURCE_OIDC = "oidc"
    SOURCE_CHOICES = [
        (SOURCE_SCIM, "SCIM"),
        (SOURCE_SAML, "SAML"),
        (SOURCE_OIDC, "OIDC"),
    ]

    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    # pk of the protocol app's provider row (ScimProvider, SamlProvider, ...).
    # Not a FK so this table does not depend on every protocol app.
    provider_id = models.PositiveIntegerField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    # SCIM: the resource id we issued; SAML: NameID; OIDC: sub.
    subject = models.CharField(max_length=255)
    # SCIM externalId: the IdP's own id for the user, sent back on reads.
    external_id = models.CharField(max_length=255, blank=True, default="")
    user = models.ForeignKey(
        HorillaUser, on_delete=models.CASCADE, related_name="external_identities"
    )
    # Set when the IdP deleted the resource but the employee was kept
    # (soft delete). An unlinked identity is invisible to the IdP.
    unlinked_at = models.DateTimeField(null=True, blank=True)
    # Deactivated at the IdP, login cut, but the employee could not be
    # archived because others still depend on them (reports, managers).
    pending_offboarding = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("External Identity")
        verbose_name_plural = _("External Identities")
        constraints = [
            models.UniqueConstraint(
                fields=["source", "provider_id", "subject"],
                name="uniq_external_identity_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["source", "provider_id", "external_id"]),
        ]

    def __str__(self):
        return f"{self.source}:{self.provider_id}:{self.subject}"
