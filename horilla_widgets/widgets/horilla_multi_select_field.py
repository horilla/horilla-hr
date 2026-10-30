"""
horilla_multi_select_field.py
This module is used to write cutom multiple select field
"""

from django import forms
from django.apps import apps

from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget


class HorillaMultiSelectField(forms.ModelMultipleChoiceField):
    """
    Employee multi-select field that defaults to every employee and the picker widget.
    """

    def __init__(self, queryset="", *, widget=None, **kwargs):
        self.uses_default_queryset = isinstance(queryset, str) and queryset == ""
        if self.uses_default_queryset:
            queryset = apps.get_model("employee", "Employee").objects.none()
        super().__init__(
            queryset, widget=widget or HorillaMultiSelectWidget(), **kwargs
        )

    def __deepcopy__(self, memo):
        result = super().__deepcopy__(memo)
        if self.uses_default_queryset:
            result.queryset = apps.get_model("employee", "Employee").objects.all()
        return result
