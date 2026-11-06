"""
horilla_tour/models.py

Data model for the enterprise product-tour engine.

A ``Tour`` is an ordered set of ``TourStep`` rows that is rendered on the
client with driver.js. Tours are authored by admins from the UI (no code),
scoped per company (``company_id=None`` => a global/default tour visible to
every tenant), targeted at an audience + page, and their per-user completion
is tracked with ``TourProgress`` (the enterprise successor to the legacy
``base.DriverViewed`` model).
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from horilla.models import HorillaModel
from horilla_auth.models import HorillaUser


class Tour(HorillaModel):
    """A guided product tour made of ordered steps, rendered with driver.js."""

    AUDIENCE_CHOICES = [
        ("all", _("Everyone")),
        ("admins", _("Admins / Superusers")),
        ("managers", _("Reporting managers")),
        ("employees", _("Employees (non-managers)")),
    ]
    TRIGGER_CHOICES = [
        ("auto_once", _("Auto-start once, then on demand")),
        ("manual", _("Only from the Help launcher")),
    ]
    MATCH_TYPE_CHOICES = [
        ("url_name", _("URL name (exact)")),
        ("path_prefix", _("Path starts with")),
    ]

    title = models.CharField(max_length=120, verbose_name=_("Title"))
    slug = models.SlugField(
        max_length=120,
        verbose_name=_("Key"),
        help_text=_(
            "Stable identifier used in code/seed data, e.g. 'getting-started'."
        ),
    )
    description = models.TextField(
        blank=True, default="", verbose_name=_("Description")
    )
    page_match = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Page"),
        help_text=_(
            "Where this tour applies. With 'URL name' enter the resolver name "
            "(e.g. 'dashboard'); with 'Path starts with' enter a path prefix "
            "(e.g. '/employee/'). Leave blank to allow on any page."
        ),
    )
    match_type = models.CharField(
        max_length=20,
        choices=MATCH_TYPE_CHOICES,
        default="url_name",
        verbose_name=_("Match by"),
    )
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default="all",
        verbose_name=_("Audience"),
    )
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default="auto_once",
        verbose_name=_("Trigger"),
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name=_("Published"),
        help_text=_("Unpublished tours are drafts and never shown to users."),
    )
    priority = models.IntegerField(
        default=0,
        verbose_name=_("Priority"),
        help_text=_(
            "Higher priority tours auto-start first when several match a page."
        ),
    )
    show_progress = models.BooleanField(
        default=True, verbose_name=_("Show progress bar")
    )
    allow_close = models.BooleanField(default=True, verbose_name=_("Allow close"))
    icon = models.CharField(
        max_length=60,
        blank=True,
        default="map-outline",
        verbose_name=_("Icon"),
        help_text=_("ion-icon name shown in the Help launcher."),
    )
    company_id = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Company"),
        help_text=_("Leave blank for a global tour shared by every company."),
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Tour")
        verbose_name_plural = _("Tours")
        ordering = ["-priority", "title"]

    def __str__(self):
        return f"{self.title}"

    @property
    def step_count(self):
        """Number of steps — used as a list column."""
        return self.steps.count()

    def get_update_url(self):
        """Edit URL — consumed by HorillaListView row actions."""
        return reverse_lazy("tour-update-form", kwargs={"pk": self.pk})

    def get_delete_url(self):
        """Delete URL — the shared generic-delete endpoint."""
        return reverse_lazy("generic-delete")

    def get_delete_instance(self):
        """PK used by the generic-delete confirmation + row id."""
        return self.pk


class TourStep(HorillaModel):
    """A single highlighted step within a :class:`Tour`."""

    SIDE_CHOICES = [
        ("top", _("Top")),
        ("bottom", _("Bottom")),
        ("left", _("Left")),
        ("right", _("Right")),
        ("over", _("Center (no element)")),
    ]
    ALIGN_CHOICES = [
        ("start", _("Start")),
        ("center", _("Center")),
        ("end", _("End")),
    ]

    tour = models.ForeignKey(
        Tour,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name=_("Tour"),
    )
    sequence = models.IntegerField(default=0, verbose_name=_("Order"))
    title = models.CharField(max_length=120, verbose_name=_("Title"))
    description = models.TextField(verbose_name=_("Description"))
    element_selector = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Element selector"),
        help_text=_(
            "CSS selector of the element to highlight (e.g. '#notificationIcon'). "
            "Leave blank for a centered message step."
        ),
    )
    side = models.CharField(
        max_length=10,
        choices=SIDE_CHOICES,
        default="bottom",
        verbose_name=_("Position"),
    )
    align = models.CharField(
        max_length=10, choices=ALIGN_CHOICES, default="start", verbose_name=_("Align")
    )
    page_match = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Step page"),
        help_text=_(
            "Optional: for multi-page tours, the URL name this step lives on. "
            "Leave blank to use the tour's page."
        ),
    )

    objects = HorillaCompanyManager("tour__company_id")

    class Meta:
        verbose_name = _("Tour step")
        verbose_name_plural = _("Tour steps")
        ordering = ["sequence", "id"]

    def __str__(self):
        return f"{self.tour.title} · {self.sequence}. {self.title}"


class TourProgress(HorillaModel):
    """Per-user completion state for a tour (supersedes ``base.DriverViewed``)."""

    STATUS_CHOICES = [
        ("in_progress", _("In progress")),
        ("completed", _("Completed")),
        ("skipped", _("Skipped")),
    ]

    tour = models.ForeignKey(
        Tour,
        on_delete=models.CASCADE,
        related_name="progress",
        verbose_name=_("Tour"),
    )
    user = models.ForeignKey(
        HorillaUser,
        on_delete=models.CASCADE,
        related_name="tour_progress",
        verbose_name=_("User"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress",
        verbose_name=_("Status"),
    )
    last_step = models.IntegerField(default=0, verbose_name=_("Last step index"))
    completed_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Completed at")
    )

    objects = HorillaCompanyManager("tour__company_id")

    class Meta:
        verbose_name = _("Tour progress")
        verbose_name_plural = _("Tour progress")
        unique_together = ("tour", "user")

    def __str__(self):
        return f"{self.user} · {self.tour} · {self.status}"

    def mark(self, status, last_step=None):
        """Update status (+ completion timestamp) and optionally the step index."""
        self.status = status
        if last_step is not None:
            self.last_step = last_step
        if status in ("completed", "skipped"):
            self.completed_at = timezone.now()
        self.save()


class TourTranslation(HorillaModel):
    """Per-language mirror of a :class:`Tour`'s ``title``/``description``."""

    tour = models.ForeignKey(
        Tour,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("Tour"),
    )
    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default="en",
        verbose_name=_("Language"),
    )
    title = models.CharField(max_length=120, verbose_name=_("Title"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("Description")
    )

    class Meta:
        verbose_name = _("Tour translation")
        verbose_name_plural = _("Tour translations")
        unique_together = ("tour", "language")

    def __str__(self):
        return f"{self.tour.title} ({self.language})"


class TourStepTranslation(HorillaModel):
    """Per-language mirror of a :class:`TourStep`'s ``title``/``description``."""

    tour_step = models.ForeignKey(
        TourStep,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("Tour step"),
    )
    language = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default="en",
        verbose_name=_("Language"),
    )
    title = models.CharField(max_length=120, verbose_name=_("Title"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("Description")
    )

    class Meta:
        verbose_name = _("Tour step translation")
        verbose_name_plural = _("Tour step translations")
        unique_together = ("tour_step", "language")

    def __str__(self):
        return f"{self.tour_step.title} ({self.language})"


def sync_tour_translation(tour):
    """Keep the English ``TourTranslation`` of ``tour`` mirrored to its current text."""
    TourTranslation.objects.update_or_create(
        tour=tour,
        language="en",
        defaults={"title": tour.title, "description": tour.description},
    )


def sync_tour_step_translation(tour_step):
    """Keep the English ``TourStepTranslation`` of ``tour_step`` mirrored to its current text."""
    TourStepTranslation.objects.update_or_create(
        tour_step=tour_step,
        language="en",
        defaults={"title": tour_step.title, "description": tour_step.description},
    )


@receiver(post_save, sender=Tour)
def _sync_tour_translation_on_save(sender, instance, **kwargs):
    sync_tour_translation(instance)


@receiver(post_save, sender=TourStep)
def _sync_tour_step_translation_on_save(sender, instance, **kwargs):
    sync_tour_step_translation(instance)
