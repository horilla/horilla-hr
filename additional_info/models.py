"""
Admin-defined extra information about employees.

A field is defined once (``AdditionalInfoField``) and applies to every employee. A value
(``AdditionalInfoValue``) is one row per employee and field, created only when it is filled in, so adding a
field never changes the schema and never needs a backfill.
"""

from django.db import models
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla.models import HorillaModel, upload_path

TEXT = "text"
LONG_TEXT = "long_text"
NUMBER = "number"
DATE = "date"
DROPDOWN = "dropdown"
YES_NO = "yes_no"
FILE = "file"

FIELD_TYPES = [
    (TEXT, _("Text")),
    (LONG_TEXT, _("Long Text")),
    (NUMBER, _("Number")),
    (DATE, _("Date")),
    (DROPDOWN, _("Dropdown")),
    (YES_NO, _("Yes / No")),
    (FILE, _("File Upload")),
]

# The column of AdditionalInfoValue that holds each type.
COLUMN = {
    TEXT: "value_text",
    LONG_TEXT: "value_text",
    DROPDOWN: "value_text",
    NUMBER: "value_number",
    DATE: "value_date",
    YES_NO: "value_bool",
    FILE: "value_file",
}


class AdditionalInfoField(HorillaModel):
    """One piece of extra information an admin wants on every employee."""

    label = models.CharField(max_length=100, verbose_name=_("Label"))
    key = models.SlugField(max_length=80, unique=True, editable=False)
    field_type = models.CharField(
        max_length=20, choices=FIELD_TYPES, default=TEXT, verbose_name=_("Type")
    )
    choices = models.JSONField(default=list, blank=True, editable=False)
    is_required = models.BooleanField(default=False, verbose_name=_("Required"))
    sequence = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    help_text = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("Help Text")
    )

    class Meta:
        ordering = ["sequence", "id"]
        verbose_name = _("Additional Info Field")
        verbose_name_plural = _("Additional Info Fields")

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self._unique_key()
        super().save(*args, **kwargs)

    def _unique_key(self):
        """A slug of the label that no other field uses; it never changes after this."""
        base = slugify(self.label).replace("-", "_")[:70] or "field"
        key, n = base, 2
        while AdditionalInfoField.objects.filter(key=key).exists():
            key, n = f"{base}_{n}", n + 1
        return key

    @property
    def column(self):
        return COLUMN[self.field_type]

    def has_values(self):
        return self.pk is not None and self.values.exists()

    def option_label(self, option_key):
        """The label of a dropdown option; the raw key if the option was removed."""
        for option in self.choices or []:
            if option.get("key") == option_key:
                return option.get("label", option_key)
        return option_key

    def get_update_url(self):
        return reverse_lazy("additional-info-field-update-form", kwargs={"pk": self.pk})

    def get_delete_url(self):
        return reverse_lazy("additional-info-field-delete", kwargs={"pk": self.pk})

    def get_instance_id(self):
        return self.pk

    def type_display(self):
        return self.get_field_type_display()

    def required_display(self):
        return _("Yes") if self.is_required else _("No")

    def active_display(self):
        return _("Yes") if self.is_active else _("No")


class AdditionalInfoValue(HorillaModel):
    """What one employee has for one field. Absent means empty."""

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="additional_info_values",
        verbose_name=_("Employee"),
    )
    field = models.ForeignKey(
        AdditionalInfoField, on_delete=models.CASCADE, related_name="values"
    )
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(
        max_digits=20, decimal_places=6, null=True, blank=True
    )
    value_date = models.DateField(null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_file = models.FileField(upload_to=upload_path, null=True, blank=True)

    class Meta:
        verbose_name = _("Additional Info Value")
        verbose_name_plural = _("Additional Info Values")
        constraints = [
            models.UniqueConstraint(
                fields=["employee_id", "field"], name="uniq_additional_info_value"
            ),
        ]
        indexes = [
            models.Index(
                fields=["field", "value_number"], name="addinfo_field_number_idx"
            ),
            models.Index(fields=["field", "value_date"], name="addinfo_field_date_idx"),
            models.Index(fields=["field", "value_bool"], name="addinfo_field_bool_idx"),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.field}"
