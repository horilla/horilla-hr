"""
Forms for the horilla_theme app
"""

# Define your horilla_theme forms here

from django import forms

from accessibility.filters import (
    AccessibilityFilter,
    HorillaFilterSet,
    _filter_form_structured,
)


def __new_init__(self, *args, **kwargs):
    AccessibilityFilter.__bases__[0].__init__(self, *args, **kwargs)
    for field_name, field in self.form.fields.items():
        filter_widget = self.filters[field_name]
        widget = filter_widget.field.widget
        if isinstance(widget, (forms.NumberInput, forms.EmailInput, forms.TextInput)):
            field.widget.attrs.update({"class": "oh-input w-100"})
        elif isinstance(widget, (forms.Select,)):
            field.widget.attrs.update(
                {
                    "class": "",
                    "id": "",
                }
            )
        elif isinstance(widget, (forms.Textarea)):
            field.widget.attrs.update({"class": "oh-input w-100"})
        elif isinstance(
            widget,
            (
                forms.CheckboxInput,
                forms.CheckboxSelectMultiple,
            ),
        ):
            field.widget.attrs.update({"class": "oh-switch__checkbox"})
        elif isinstance(widget, (forms.ModelChoiceField)):
            field.widget.attrs.update(
                {
                    "class": "oh-select oh-select-2 select2-hidden-accessible",
                }
            )
    self.form.structured = _filter_form_structured(self.form)


AccessibilityFilter.__init__ = __new_init__
