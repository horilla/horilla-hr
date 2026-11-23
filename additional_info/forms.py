"""Forms: the admin's field definition, and the per-employee values form built from the definitions."""

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from additional_info.models import (
    DATE,
    DROPDOWN,
    FILE,
    LONG_TEXT,
    NUMBER,
    TEXT,
    YES_NO,
    AdditionalInfoField,
)
from base.forms import ModelForm

MAX_FILE_MB = 10
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv",
    "png", "jpg", "jpeg", "gif", "webp",
}  # fmt: skip


class AdditionalInfoFieldForm(ModelForm):
    """Create or edit a field. Its type is locked once any employee has a value for it."""

    # Two steps: the details, then where the field sits among the others (the generic form draws the steps).
    wizard_template = "additional_info/field_wizard.html"
    wizard_details_label = _("Field")
    wizard_details_hint = _("Label, type and options.")
    # The details step shows Options for a Dropdown only, the two switches on one row, and a preview of the input.
    cols = {
        "label": 6,
        "field_type": 6,
        "options": 12,
        "help_text": 12,
        "is_required": 6,
        "is_active": 6,
    }

    options = forms.CharField(
        label=_("Options"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("One Option Per Line. Employees Pick One Of Them."),
    )
    # The order of every field as a JSON list of ids, with "new" standing for the field being created.
    field_order = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = AdditionalInfoField
        fields = [
            "label",
            "field_type",
            "options",
            "help_text",
            "is_required",
            "is_active",
            "field_order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The base form fills each placeholder with the label; these two say something more useful.
        self.fields["help_text"].widget.attrs["placeholder"] = _(
            "Shown Under The Input To Guide Whoever Fills It"
        )
        self.fields["options"].widget.attrs["placeholder"] = _(
            "One Option Per Line, For Example: A+, B+, O-"
        )
        if self.instance.pk:
            self.fields["options"].initial = "\n".join(
                o["label"] for o in self.instance.choices or []
            )
            if self.instance.has_values():
                self.fields["field_type"].disabled = True
                self.fields["field_type"].help_text = _(
                    "The Type Cannot Change Once Employees Have Values."
                )

    @property
    def order_json(self):
        """The rows of the order step: every field in its saved order, this one included (new ones last)."""
        rows = [
            {
                "id": f.pk,
                "label": f.label,
                "type": str(f.get_field_type_display()),
                "current": f.pk == self.instance.pk,
            }
            for f in AdditionalInfoField.objects.all()
        ]
        if not self.instance.pk:
            rows.append({"id": "new", "label": "", "type": "", "current": True})
        posted = self.data.get("field_order") if self.is_bound else None
        if posted:
            try:
                wanted = {str(i): n for n, i in enumerate(json.loads(posted))}
            except (ValueError, TypeError):
                wanted = {}
            # Keep the order the person chose when the form comes back with an error.
            saved = {str(r["id"]): n for n, r in enumerate(rows)}
            rows.sort(
                key=lambda r: wanted.get(
                    str(r["id"]), len(wanted) + saved[str(r["id"])]
                )
            )
        return json.dumps(rows)

    def clean_field_order(self):
        raw = self.cleaned_data.get("field_order") or ""
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        valid = (
            isinstance(data, list)
            and len(data) <= 1000
            and all(
                item == "new" or (isinstance(item, int) and not isinstance(item, bool))
                for item in data
            )
        )
        if not valid:
            raise ValidationError(_("The Order Could Not Be Read. Please Try Again."))
        return data

    def clean_label(self):
        label = (self.cleaned_data.get("label") or "").strip()
        taken = AdditionalInfoField.objects.filter(label__iexact=label).exclude(
            pk=self.instance.pk
        )
        if taken.exists():
            raise ValidationError(_("A Field With This Label Already Exists."))
        return label

    def clean(self):
        data = super().clean()
        lines = [
            " ".join(line.split()) for line in (data.get("options") or "").splitlines()
        ]
        lines = [line for line in lines if line]
        if data.get("field_type") == DROPDOWN:
            if not lines:
                self.add_error("options", _("Add At Least One Option For A Dropdown."))
            elif len({line.lower() for line in lines}) != len(lines):
                self.add_error("options", _("Each Option Must Be Different."))
        data["option_lines"] = lines
        return data

    def _choices(self, lines):
        """Option keys stay the same for a label that was kept, so saved values keep their meaning."""
        known = {o["label"].lower(): o["key"] for o in (self.instance.choices or [])}
        taken = set(known.values())
        choices = []
        for line in lines:
            key = known.get(line.lower())
            if key is None:
                base = slugify(line).replace("-", "_") or "option"
                key, n = base, 2
                while key in taken:
                    key, n = f"{base}_{n}", n + 1
                taken.add(key)
            choices.append({"key": key, "label": line})
        return choices

    def _apply_order(self, instance, order):
        """Number every field from the chosen order. Ids that no longer exist are skipped, unlisted fields keep their place."""
        fields = list(AdditionalInfoField.objects.all())
        if not order and not self._creating:
            return
        by_id = {f.pk: f for f in fields}
        ordered, seen = [], set()
        for item in order:
            pk = instance.pk if item == "new" else item
            field = by_id.get(pk)
            if field is not None and pk not in seen:
                ordered.append(field)
                seen.add(pk)
        rest = [f for f in fields if f.pk not in seen]
        if self._creating and instance.pk not in seen:
            rest = [f for f in rest if f.pk != instance.pk] + [
                by_id[instance.pk]
            ]  # a new field goes last
        ordered += rest
        changed = []
        for position, field in enumerate(ordered):
            if field.sequence != position:
                field.sequence = position
                changed.append(field)
        AdditionalInfoField.objects.bulk_update(changed, ["sequence"])
        instance.sequence = by_id[instance.pk].sequence

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.choices = (
            self._choices(self.cleaned_data["option_lines"])
            if instance.field_type == DROPDOWN
            else []
        )
        if commit:
            self._creating = not instance.pk
            instance.save()
            self._apply_order(instance, self.cleaned_data.get("field_order") or [])
        return instance


def _validate_file(upload):
    """Size and extension checks for an uploaded additional-info file."""
    if upload is None or upload is False or not hasattr(upload, "size"):
        return upload
    extension = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(_("This File Type Is Not Allowed."))
    if upload.size > MAX_FILE_MB * 1024 * 1024:
        raise ValidationError(
            _("The File Is Larger Than %(mb)s MB.") % {"mb": MAX_FILE_MB}
        )
    return upload


# The same look as the other steps of the employee form (see update_form/bank_details.html).
INPUT = "emp-input w-full h-9 px-3 text-xs border border-secondary-200 rounded-md bg-white text-dark-500"
TEXTAREA = "emp-input w-full px-3 py-2 text-xs border border-secondary-200 rounded-md bg-white text-dark-500 resize-y"
FILE_INPUT = "oh-input w-100"


def build_values_form(fields):
    """A form class with one input for each field, keyed by the field's key."""
    attrs = {}
    for field in fields:
        label = field.label
        common = {
            "label": label,
            "required": field.is_required,
            "help_text": field.help_text,
        }
        kind = field.field_type
        if kind == TEXT:
            form_field = forms.CharField(
                max_length=255, widget=forms.TextInput(attrs={"class": INPUT}), **common
            )
        elif kind == LONG_TEXT:
            form_field = forms.CharField(
                widget=forms.Textarea(attrs={"class": TEXTAREA, "rows": 3}), **common
            )
        elif kind == NUMBER:
            form_field = forms.DecimalField(
                max_digits=20,
                decimal_places=6,
                widget=forms.NumberInput(attrs={"class": INPUT, "step": "any"}),
                **common,
            )
        elif kind == DATE:
            form_field = forms.DateField(
                widget=forms.DateInput(
                    attrs={"class": INPUT, "type": "date"}, format="%Y-%m-%d"
                ),
                **common,
            )
        elif kind == DROPDOWN:
            options = [("", "---------")] + [
                (o["key"], o["label"]) for o in field.choices or []
            ]
            form_field = forms.ChoiceField(
                choices=options, widget=forms.Select(attrs={"class": INPUT}), **common
            )
        elif kind == YES_NO:
            form_field = forms.TypedChoiceField(
                choices=[("", "---------"), ("yes", _("Yes")), ("no", _("No"))],
                coerce=lambda value: value == "yes",
                empty_value=None,
                widget=forms.Select(attrs={"class": INPUT}),
                **common,
            )
        else:
            form_field = forms.FileField(
                widget=forms.ClearableFileInput(attrs={"class": FILE_INPUT}),
                validators=[_validate_file],
                **common,
            )
        attrs[field.key] = form_field
    return type("AdditionalInfoValuesForm", (forms.Form,), attrs)
