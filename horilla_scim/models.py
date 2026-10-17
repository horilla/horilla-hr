"""
models.py

A ScimProvider is one IdP connection for one company. The IdP authenticates
with a bearer token; only its SHA-256 is stored, so a database leak does not
hand out working provisioning credentials. The raw token is shown once.
"""

import hashlib
import secrets

from django.db import models
from django.utils import timezone
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


class ScimTokenQuerySet(models.QuerySet):
    def usable(self):
        now = timezone.now()
        return self.filter(revoked_at__isnull=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )


class ScimToken(models.Model):
    provider = models.ForeignKey(
        ScimProvider, on_delete=models.CASCADE, related_name="tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=16, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ScimTokenQuerySet.as_manager()

    class Meta:
        verbose_name = _("SCIM Token")
        verbose_name_plural = _("SCIM Tokens")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.prefix}…"

    @classmethod
    def issue(cls, provider, expires_at=None):
        """Create a token and return ``(token, raw_value)``. Show raw once."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(
            provider=provider,
            token_hash=hash_token(raw),
            prefix=raw[: len(TOKEN_PREFIX) + 6],
            expires_at=expires_at,
        )
        return token, raw

    @property
    def is_usable(self):
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


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
