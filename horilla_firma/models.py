"""
Models for the Firma e-signature integration.

FirmaSettings is one row, like the single sign-on settings: the API key and
the webhook signing secret are stored encrypted (see crypto.py).
FirmaSignatureRequest is one send of a document to a candidate, created
before the call to Firma so that a second send of the same form, or a
concurrent one, is refused (see services.send).
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from horilla.models import HorillaModel, upload_path
from horilla_firma import crypto

STATUS_SENDING = "sending"
STATUS_FAILED = "failed"
STATUS_UNCERTAIN = "uncertain"
STATUS_SENT = "sent"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_DECLINED = "declined"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"

STATUS_CHOICES = [
    (STATUS_SENDING, _("Sending")),
    (STATUS_FAILED, _("Not Sent")),
    (STATUS_UNCERTAIN, _("Outcome Unknown")),
    (STATUS_SENT, _("Sent")),
    (STATUS_IN_PROGRESS, _("In Progress")),
    (STATUS_COMPLETED, _("Signed")),
    (STATUS_DECLINED, _("Declined")),
    (STATUS_CANCELLED, _("Cancelled")),
    (STATUS_EXPIRED, _("Expired")),
]

# Status only moves forward. The four end states share the top rank, so a
# signed request never becomes declined because of a late event.
STATUS_RANK = {
    STATUS_SENDING: 0,
    STATUS_UNCERTAIN: 1,
    STATUS_SENT: 2,
    STATUS_IN_PROGRESS: 3,
    STATUS_COMPLETED: 4,
    STATUS_DECLINED: 4,
    STATUS_CANCELLED: 4,
    STATUS_EXPIRED: 4,
    STATUS_FAILED: 4,
}

SOURCE_TEMPLATE = "template"
SOURCE_DOCUMENT = "document"
SOURCE_CHOICES = [
    (SOURCE_TEMPLATE, _("Firma Template")),
    (SOURCE_DOCUMENT, _("Offer Letter PDF")),
]


class FirmaSettings(models.Model):
    """The company-wide Firma settings. One row."""

    is_enabled = models.BooleanField(
        default=False, verbose_name=_("Enable Firma E-Signature")
    )
    api_key_encrypted = models.TextField(blank=True, editable=False)
    webhook_secret_encrypted = models.TextField(blank=True, editable=False)
    default_expiration_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Default Expiration (Hours)"),
        help_text=_("Leave empty to use the expiration set in Firma."),
    )
    webhook_id = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        verbose_name = _("Firma Settings")

    def __str__(self):
        return "Firma Settings"

    @property
    def api_key(self):
        return crypto.decrypt(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value):
        self.api_key_encrypted = crypto.encrypt(value)

    @property
    def webhook_secret(self):
        return crypto.decrypt(self.webhook_secret_encrypted)

    @webhook_secret.setter
    def webhook_secret(self, value):
        self.webhook_secret_encrypted = crypto.encrypt(value)

    @classmethod
    def current(cls):
        return cls.objects.first()

    @classmethod
    def ready(cls):
        """The settings when switched on and holding an API key, else None."""
        config = cls.current()
        return config if config and config.is_ready() else None

    def is_ready(self):
        return bool(self.is_enabled and self.api_key)


class FirmaSignatureRequest(HorillaModel):
    """One document sent to a candidate for signature through Firma."""

    # The candidate is the only record this one hangs from. Horilla's per-file
    # media rule (base/media_access.py) grants the signed PDF to anyone who may
    # view, or who created, any record reached through a foreign key, so no
    # other foreign key belongs here. The reverse link is hidden ("+") so that
    # this model's permission or authorship never opens the candidate's files.
    candidate_id = models.ForeignKey(
        "recruitment.Candidate",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("Candidate"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, verbose_name=_("Source")
    )
    firma_template_id = models.CharField(max_length=64, blank=True)
    firma_template_name = models.CharField(
        max_length=255, blank=True, verbose_name=_("Firma Template")
    )
    # The mail template the offer letter was rendered from, kept as plain
    # values (see candidate_id above for why this is not a foreign key).
    mail_template_title = models.CharField(
        max_length=255, blank=True, verbose_name=_("Offer Letter Template")
    )
    mail_template_pk = models.PositiveIntegerField(null=True, blank=True)
    recipient_name = models.CharField(max_length=255, verbose_name=_("Recipient"))
    recipient_email = models.EmailField(verbose_name=_("Recipient Email"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    firma_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Firma Signing Request ID"),
    )
    # One value per rendered send form: a replayed submission of the same form
    # finds this row instead of sending again.
    send_token = models.CharField(max_length=64, unique=True, editable=False)
    message = models.TextField(blank=True, verbose_name=_("Message"))
    no_invitation_email = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent At"))
    completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Signed At")
    )
    signed_document = models.FileField(
        upload_to=upload_path,
        null=True,
        blank=True,
        verbose_name=_("Signed Document"),
    )
    fetch_attempts = models.PositiveIntegerField(default=0, editable=False)
    next_fetch_at = models.DateTimeField(null=True, blank=True, editable=False)
    fetch_stopped = models.BooleanField(default=False, editable=False)

    objects = HorillaCompanyManager(
        related_company_field="candidate_id__recruitment_id__company_id"
    )
    # Unscoped, for the webhook and the scheduler, which have no company.
    all_objects = models.Manager()

    class Meta:
        verbose_name = _("Firma Signature Request")
        ordering = ["-created_at", "-id"]
        constraints = [
            # Two sends for one candidate cannot be in flight at once.
            models.UniqueConstraint(
                fields=["candidate_id"],
                condition=Q(status="sending"),
                name="horilla_firma_one_send_in_flight_per_candidate",
            )
        ]

    def __str__(self):
        return self.title


class FirmaWebhookEvent(models.Model):
    """A processed webhook delivery, kept to ignore Firma's retries of it."""

    event_id = models.CharField(max_length=140, unique=True)
    event_type = models.CharField(max_length=140, blank=True)
    signing_request_id = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Firma Webhook Event")

    def __str__(self):
        return self.event_id
