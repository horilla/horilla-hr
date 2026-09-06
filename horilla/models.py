"""
models.py
=========

This module defines the abstract base model `HorillaModel` for the Horilla HRMS project.
The `HorillaModel` provides common fields and functionalities for other models within
the application, such as tracking creation and modification timestamps and user
information, audit logging, and active/inactive status management.
"""

import html
import re
from uuid import uuid4

from auditlog.models import AuditlogHistoryField
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.files import FieldFile
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from horilla.horilla_middlewares import _thread_locals
from horilla.inherit.model_inherit import EXTENSION_REGISTRY, HorillaModelBase
from horilla_auth.models import HorillaUser
from horilla_views.cbv_methods import render_template


@property
def url(self: FieldFile):
    """
    Custom url attribute/property
    """
    try:
        self._require_file()
    except Exception as e:
        return reverse("404")
    return self.storage.url(self.name)


setattr(FieldFile, "url", url)


def has_xss(value: str) -> bool:
    """Detect common XSS attempts (scripts, event handlers, js URLs, active content)."""
    if not isinstance(value, str):
        return False

    # Decode HTML entities so obfuscated payloads (e.g. "jav&#x61;script:")
    # are matched after the browser would have decoded them. Decode twice to
    # catch double-encoded variants (e.g. "&amp;#x61;").
    decoded = html.unescape(html.unescape(value))

    # Every tag pattern matches the OPENING tag only. Requiring a closing tag,
    # or even a closing ">", is a bypass: `<script>fetch("file:///etc/passwd")`
    # with no `</script>` slipped through the previous
    # `<script.*?>.*?</script>` pattern, while an HTML parser runs an unclosed
    # script to end-of-document. That mattered most in generate_pdf, where the
    # body reaches wkhtmltopdf with --enable-local-file-access, turning it into
    # a local file read and exfiltration (GHSA-cjr4-rrp6-g72j).
    #
    # A word boundary after the tag name keeps `<scriptural>` and `<linked>`
    # from matching, so ordinary prose is unaffected.
    xss_patterns = [
        r"<\s*script\b",  # <script, closed or not
        r"javascript\s*:",  # javascript: pseudo-protocol
        r"on\w+\s*=",  # inline event handlers (onclick, onload, etc.)
        r"<\s*(embed|object|iframe|svg|math|link|meta|base|form)\b",  # active content
        r"on\w+\s*=\s*['\"]?\s*(eval|setTimeout|setInterval|new\s+Function|XMLHttpRequest|fetch|\$\s*\()[^>]*",  # JS API abuse
        # file:// anywhere is a local-file read once the document reaches
        # wkhtmltopdf, and has no legitimate use in user-authored content.
        r"file\s*:\s*/\s*/",
    ]

    combined = re.compile("|".join(xss_patterns), re.IGNORECASE | re.DOTALL)
    return bool(combined.search(value) or combined.search(decoded))


def upload_path(instance, filename):
    """
    Generates a unique file path for uploads in the format:
    app_label/model_name/field_name/originalfilename-uuid.ext
    """
    ext = filename.split(".")[-1]
    base_name = ".".join(filename.split(".")[:-1]) or "file"
    unique_name = f"{slugify(base_name)}-{uuid4().hex[:8]}.{ext}"

    # Try to find which field is uploading this file
    field_name = next(
        (
            k
            for k, v in instance.__dict__.items()
            if hasattr(v, "name") and v.name == filename
        ),
        None,
    )

    app_label = instance._meta.app_label
    model_name = instance._meta.model_name

    if field_name:
        return f"{app_label}/{model_name}/{field_name}/{unique_name}"
    return f"{app_label}/{model_name}/{unique_name}"


class HorillaModel(models.Model, metaclass=HorillaModelBase):
    """
    An abstract base model that includes common fields and functionalities
    for models within the Horilla application.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
        blank=True,
        verbose_name=_("Created At"),
    )
    created_by = models.ForeignKey(
        HorillaUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Created By"),
    )

    modified_by = models.ForeignKey(
        HorillaUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("Modified By"),
        related_name="%(class)s_modified_by",
    )
    horilla_history = AuditlogHistoryField()
    objects = models.Manager()
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    @property
    def get_created_at_date(self):
        """
        get_created_at_date
        """
        return self.created_at.date()

    class Meta:
        """
        Meta class for HorillaModel
        """

        abstract = True

    def save(self, *args, **kwargs):
        """
        Override the save method to automatically set the created_by and
        modified_by fields based on the current request user.
        """
        # XSS validation runs on EVERY write, not only through a ModelForm.
        #
        # clean_fields() below is the only place has_xss() is applied, and it
        # reaches a save only via full_clean(). full_clean() used to be called
        # here, but was commented out during an unrelated CBV merge, which
        # silently reduced the check to ModelForm submissions alone. Every DRF
        # serializer.save() and every direct .save() then stored raw markup --
        # reported as GHSA-rf47-2qgf-qq4j, a bypass of CVE-2025-59525 that
        # re-opened the sink of CVE-2025-59832.
        #
        # clean_fields() is called directly rather than restoring full_clean().
        # full_clean() also runs clean(), validate_unique() and
        # validate_constraints() over every field, and code written in the
        # years it was disabled has come to rely on saves that would not pass
        # it -- turning it back on globally would reject writes that work
        # today. This is the narrow version: the security check, nothing else.
        self.clean_fields()

        request = getattr(_thread_locals, "request", None)

        if request:
            user = request.user

            if (
                hasattr(self, "created_by")
                and hasattr(self._meta.get_field("created_by"), "related_model")
                and self._meta.get_field("created_by").related_model == HorillaUser
            ):
                if request and not self.pk:
                    if user.is_authenticated:
                        self.created_by = user

            if request and not request.user.is_anonymous:
                self.modified_by = user

        super(HorillaModel, self).save(*args, **kwargs)

    def clean_fields(self, exclude=None):
        errors = {}

        # Get the list of fields to exclude from validation
        total_exclude = set(exclude or []).union(getattr(self, "xss_exempt_fields", []))

        for field in self._meta.get_fields():
            if (
                isinstance(field, (models.CharField, models.TextField))
                and field.name not in total_exclude
            ):
                value = getattr(self, field.name, None)
                if value and has_xss(value):
                    errors[field.name] = ValidationError(
                        _("Potential XSS content detected.")
                    )

        if errors:
            raise ValidationError(errors)

    def get_verbose_name(self):
        return self._meta.verbose_name

    def get_verbose_name_plural(self):
        return self._meta.verbose_name_plural

    def get_model_history(self):
        """
        returns the history button column
        """

        return render_template(
            path="generic/history_col.html",
            context={"instance": self},
        )

    def get_history_url(self):
        """
        URL for opening this instance's history sidebar
        """
        return (
            reverse("generic-history", kwargs={"pk": self.pk})
            + f"?model={self._meta.app_label}.{self._meta.model_name}"
        )

    @classmethod
    def find(cls, object_id):
        """
        Find an object of this class by its ID.
        """
        try:
            obj = cls.objects.filter(id=object_id).first()
            return obj
        except Exception as e:
            # Log the exception if needed
            return None

    @classmethod
    def activate_deactivate(cls, object_id):
        """
        Toggle the is_active status of an object of this class.
        """
        obj = cls.find(object_id)
        if obj:
            obj.is_active = not obj.is_active
            obj.save()

    @classmethod
    def get_verbose_name_related_field(cls, field_path):
        """
        Traverse related fields to get verbose_name using Django's _meta API.
        Example: "employee_id__employee_work_info__reporting_manager_id"
        """
        parts = field_path.split("__")
        instance_model = cls

        for part in parts[:-1]:
            field = instance_model._meta.get_field(part)
            instance_model = field.remote_field.model

        final_field = instance_model()._meta.get_field(parts[-1])
        return final_field.verbose_name


class NoPermissionModel:
    _no_permission_model = True
