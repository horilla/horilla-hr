"""
models.py

A ScimProvider is one IdP connection for one company. The IdP authenticates
with a bearer token; only its SHA-256 is stored, so a database leak does not
hand out working provisioning credentials. The raw token is shown once.
"""

import hashlib
import secrets

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from base.models import Company, Department, EmployeeShift, EmployeeType, JobPosition

TOKEN_PREFIX = "hscim_"


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class ScimProvider(models.Model):
    DELETE_SOFT = "soft"
    DELETE_HARD = "hard"
    DELETE_CHOICES = [
        (DELETE_SOFT, _("Archive the employee and disable login")),
        (DELETE_HARD, _("Permanently delete the employee")),
    ]

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="scim_providers"
    )
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    is_enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))
    delete_mode = models.CharField(
        max_length=10,
        choices=DELETE_CHOICES,
        default=DELETE_SOFT,
        verbose_name=_("When the identity provider deletes a user"),
    )
    match_existing_by_email = models.BooleanField(
        default=True,
        verbose_name=_("Link existing employees by e-mail"),
        help_text=_(
            "When the identity provider creates a user whose e-mail already "
            "belongs to an employee of this company, link to that employee "
            "instead of rejecting the request."
        ),
    )
    reactivate_archived_employees = models.BooleanField(
        default=False,
        verbose_name=_("Allow the identity provider to reactivate archived employees"),
        help_text=_(
            "When on, a user the identity provider marks active is reactivated "
            "even if HR archived them in Horilla. When off, only employees the "
            "identity provider itself deactivated are reactivated."
        ),
    )
    send_invitation_email = models.BooleanField(
        default=False,
        verbose_name=_("Send invitation e-mail to new employees"),
        help_text=_(
            "Leave off when employees sign in through single sign-on and never "
            "need a Horilla password."
        ),
    )
    default_department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Default department"),
    )
    default_job_position = models.ForeignKey(
        JobPosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Default job position"),
    )
    default_shift = models.ForeignKey(
        EmployeeShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Default shift"),
    )
    default_employee_type = models.ForeignKey(
        EmployeeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Default employee type"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("SCIM Provider")
        verbose_name_plural = _("SCIM Providers")

    def __str__(self):
        return f"{self.name} ({self.company})"


class ScimToken(models.Model):
    """A provider has at most one token; resetting it replaces the old one."""

    provider = models.OneToOneField(
        ScimProvider, on_delete=models.CASCADE, related_name="token"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("SCIM Token")
        verbose_name_plural = _("SCIM Tokens")

    def __str__(self):
        return f"SCIM token of {self.provider}"

    @classmethod
    @transaction.atomic
    def issue(cls, provider):
        """
        Create the provider's token, replacing any previous one, and return
        ``(token, raw_value)``. The raw value is shown once and never stored.
        """
        cls.objects.filter(provider=provider).delete()
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(provider=provider, token_hash=hash_token(raw))
        return token, raw


class ScimEvent(models.Model):
    """Request log shown on the settings page; for debugging IdP setups."""

    provider = models.ForeignKey(
        ScimProvider, on_delete=models.CASCADE, related_name="events"
    )
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=255)
    status = models.PositiveSmallIntegerField()
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
