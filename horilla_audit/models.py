"""
models.py
"""

import logging
from collections.abc import Iterable

from django.db import models
from django.dispatch import receiver
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from simple_history.models import (
    HistoricalRecords,
    _default_get_user,
    _history_user_getter,
    _history_user_setter,
)
from simple_history.signals import (  # pre_create_historical_m2m_records,; post_create_historical_m2m_records,
    post_create_historical_record,
    pre_create_historical_record,
)

# from employee.models import Employee
from horilla.models import HorillaModel
from horilla_audit.methods import remove_duplicate_history

logger = logging.getLogger(__name__)

# Create your models here.


class AuditTag(models.Model):
    """
    HistoryTag model
    """

    title = models.CharField(max_length=20)
    highlight = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.title)

    class Meta:
        """
        Meta class for aditional info
        """

        app_label = "horilla_audit"

    def custom_highlight_col(self):
        """
        return yes or no based on highlight true or false
        """
        return _("Yes") if self.highlight else _("No")

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("settings-audit-tag-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("audit-tag-delete", kwargs={"obj_id": self.pk})
        return url

    def get_delete_instance(self):
        """
        to get instance for delete
        """

        return self.pk


class HorillaAuditInfo(models.Model):
    """
    HorillaAuditInfo model to store additional info
    """

    history_title = models.CharField(max_length=20, null=True, blank=True)
    history_description = models.TextField(null=True)
    history_highlight = models.BooleanField(default=False, null=True)
    history_tags = models.ManyToManyField(AuditTag)

    class Meta:
        """
        Meta class for aditional info
        """

        app_label = "horilla_audit"
        abstract = True


class HorillaAuditLog(HistoricalRecords):
    """
    Model to store additional information for historical records.
    """

    # def __init__(self, *args, bases=None, **kwargs):
    #     super(HorillaAuditLog, self).__init__(*args, **kwargs)
    #     self.is_horilla_audit_log = True

    pass

    # history_comments = models.ManyToManyField("HistoryComment", blank=True)


@receiver(pre_create_historical_record)
def pre_create_horilla_audit_log(sender, instance, *args, **kwargs):
    """
    Pre create horill audit log method
    """
    try:
        history_instance = kwargs["history_instance"]
        history_instance.history_title = HistoricalRecords.thread.request.POST.get(
            "history_title"
        )
        history_instance.history_description = (
            HistoricalRecords.thread.request.POST.get("history_description")
        )
        history_instance.history_highlight = (
            True
            if HistoricalRecords.thread.request.POST.get("history_highlight") == "on"
            else False
        )
        instance.skip_history = True
    except (AttributeError, KeyError) as error:
        # HistoricalRecords.thread.request is absent outside a request cycle
        # (shell, migrations, the scheduler), so audit metadata simply is not
        # available there. Narrowed from a bare except so a real failure in
        # the assignments above is no longer silent.
        logger.debug("audit metadata not captured: %s", error)


@receiver(post_create_historical_record)
def post_create_horilla_audit_log(sender, instance, *_args, **kwargs):
    """
    Post create horill audit log method
    """
    try:
        history_instance = kwargs["history_instance"]
        from horilla_audit.models import AuditTag as _AuditTag

        tag_ids = []
        for raw_value in HistoricalRecords.thread.request.POST.getlist("history_tags"):
            if raw_value.isdigit() and _AuditTag.objects.filter(pk=raw_value).exists():
                tag_ids.append(int(raw_value))
            elif raw_value:
                tag, _created = _AuditTag.objects.get_or_create(title=raw_value)
                tag_ids.append(tag.pk)
        history_instance.history_tags.set(tag_ids)
        if isinstance(history_instance, HorillaAuditLog):
            history_instance.history_title = "Demo Title"
            remove_duplicate_history(instance)
            if instance.skip_history:
                instance.history_set.filter(pk=history_instance.pk).delete()
            kwargs["history_instance"] = None
    except (AttributeError, KeyError) as error:
        # Same as above: no request thread means no tags to attach.
        logger.debug("audit tags not applied: %s", error)


class HistoryTrackingFields(HorillaModel):
    """
    Per-company work-information history tracking settings.
    When company_id is null, the row is the default used for "All Companies"
    and as a fallback for companies without their own configuration.
    """

    # Pre-selected on a fresh install so history tracking is useful out of the
    # box instead of silently tracking nothing until an admin visits Settings.
    DEFAULT_TRACKING_FIELDS = [
        "job_position_id",
        "department_id",
        "job_role_id",
        "work_type_id",
        "employee_type_id",
        "shift_id",
        "reporting_manager_id",
        "company_id",
        "basic_salary",
    ]

    tracking_fields = models.JSONField(null=True, blank=True, editable=False)
    work_info_track = models.BooleanField(default=True)
    company_id = models.ForeignKey(
        "base.Company",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = models.Manager()

    class Meta:
        verbose_name = _("History Tracking Fields")
        verbose_name_plural = _("History Tracking Fields")

    def tracked_field_names(self):
        """Return the list of field names selected for tracking."""
        if not self.tracking_fields:
            return []
        if isinstance(self.tracking_fields, dict):
            return list(self.tracking_fields.get("tracking_fields") or [])
        return []

    @classmethod
    def default_setting(cls):
        """Return the All Companies (company_id=None) setting row, if any."""
        return cls.objects.filter(company_id__isnull=True).order_by("id").first()

    @classmethod
    def seed_default_row(cls):
        """
        Create the "All Companies" row with ``DEFAULT_TRACKING_FIELDS`` if no
        such row exists yet. Safe to call repeatedly (e.g. on every
        post_migrate) — never overwrites an existing configuration.
        """
        if cls.objects.filter(company_id__isnull=True).exists():
            return
        cls.objects.create(
            company_id=None,
            work_info_track=True,
            tracking_fields={"tracking_fields": list(cls.DEFAULT_TRACKING_FIELDS)},
        )

    @classmethod
    def for_company(cls, company=None):
        """
        Return the tracking settings for ``company``. Prefers a company-
        specific row; falls back to the default (company_id=None) row.
        """
        if company is not None:
            instance = cls.objects.filter(company_id=company).first()
            if instance is not None:
                return instance
        return cls.default_setting()

    @classmethod
    def for_settings_ui(cls, company=None):
        """
        Settings used to render the System Preferences controls.

        - All Companies: the default row (or an unsaved stub)
        - Specific company with its own row: that row
        - Specific company without its own row: inherit the default for display
          (caller should not persist the inherited instance as the company row
          unless the user explicitly saves)
        """
        if company is None:
            instance = cls.default_setting()
            return instance or cls(
                work_info_track=True,
                tracking_fields={"tracking_fields": list(cls.DEFAULT_TRACKING_FIELDS)},
            )

        own = cls.objects.filter(company_id=company).first()
        if own is not None:
            return own

        default = cls.default_setting()
        if default is not None:
            # Unsaved copy for display only — keeps All Companies values visible
            # until this company saves its own configuration.
            return cls(
                company_id=company,
                work_info_track=default.work_info_track,
                tracking_fields={
                    "tracking_fields": list(default.tracked_field_names())
                },
            )
        return cls(
            company_id=company,
            work_info_track=True,
            tracking_fields={"tracking_fields": list(cls.DEFAULT_TRACKING_FIELDS)},
        )

    @classmethod
    def get_or_create_for_company(cls, company=None):
        """
        Fetch or create the settings row for ``company``.
        New company rows copy field selections from the All Companies default.
        """
        if company is None:
            instance = cls.default_setting()
            if instance is not None:
                return instance, False
            return (
                cls.objects.create(
                    company_id=None,
                    work_info_track=True,
                    tracking_fields={
                        "tracking_fields": list(cls.DEFAULT_TRACKING_FIELDS)
                    },
                ),
                True,
            )

        instance = cls.objects.filter(company_id=company).first()
        if instance is not None:
            return instance, False

        default = cls.default_setting()
        return (
            cls.objects.create(
                company_id=company,
                work_info_track=default.work_info_track if default else True,
                tracking_fields=(
                    default.tracking_fields
                    if default and default.tracking_fields is not None
                    else {"tracking_fields": list(cls.DEFAULT_TRACKING_FIELDS)}
                ),
            ),
            True,
        )

    @classmethod
    def assigned_company_ids(cls):
        """Company IDs that already have their own tracking configuration."""
        return list(
            cls.objects.exclude(company_id=None)
            .values_list("company_id_id", flat=True)
            .distinct()
        )

    @classmethod
    def apply_settings(
        cls,
        *,
        work_info_track,
        field_names,
        company=None,
        assign_company_ids=None,
        update_fields=False,
    ):
        """
        Persist tracking settings.

        - Always updates the row for ``company`` (None = All Companies default).
        - When ``company`` is None and ``assign_company_ids`` is provided, also
          applies settings to those companies without wiping company-specific
          field selections: existing company fields are kept and new default
          fields are merged in.
        """
        field_names = list(field_names or [])
        payload = {"tracking_fields": field_names}
        history_object, _created = cls.get_or_create_for_company(company)
        history_object.work_info_track = work_info_track
        if update_fields:
            history_object.tracking_fields = payload
        history_object.save()

        if company is None and assign_company_ids is not None:
            from base.models import Company

            companies = Company.objects.filter(id__in=assign_company_ids)
            for target in companies:
                target_object = cls.objects.filter(company_id=target).first()
                if target_object is None:
                    cls.objects.create(
                        company_id=target,
                        work_info_track=work_info_track,
                        tracking_fields=(
                            payload if update_fields else {"tracking_fields": []}
                        ),
                    )
                else:
                    target_object.work_info_track = work_info_track
                    if update_fields:
                        existing_fields = target_object.tracked_field_names()
                        if existing_fields:
                            # Keep company-specific fields; add any new default fields.
                            merged = list(dict.fromkeys(existing_fields + field_names))
                            target_object.tracking_fields = {"tracking_fields": merged}
                        # Empty list means "track all" — leave it alone.
                    target_object.save()

        return history_object


class AccountBlockUnblock(HorillaModel):
    is_enabled = models.BooleanField(default=False, null=True, blank=True)
    objects = models.Manager()


class AuditModelConfig(HorillaModel):
    """
    Stores which models (and optionally which fields) are tracked by the
    django-auditlog registry. When no rows exist, a built-in default set
    of Employee-related models is tracked. Rows here fully override the
    defaults.
    """

    app_label = models.CharField(max_length=100, verbose_name=_("App"))
    model_name = models.CharField(max_length=100, verbose_name=_("Model"))
    is_enabled = models.BooleanField(default=True, verbose_name=_("Enabled"))
    tracked_fields = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Tracked Fields"),
        help_text=_("Leave empty to track every field on the model."),
    )

    class Meta:
        unique_together = ("app_label", "model_name")
        verbose_name = _("Audit Tracking Configuration")
        verbose_name_plural = _("Audit Tracking Configurations")

    def __str__(self):
        return f"{self.app_label}.{self.model_name}"

    @property
    def dotted_path(self):
        return f"{self.app_label}.{self.model_name}"
