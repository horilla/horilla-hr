"""
dynamic_fields/forms.py
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from dynamic_fields import models
from dynamic_fields.df_not_allowed_models import DF_NOT_ALLOWED_MODELS
from dynamic_fields.models import DynamicField
from horilla.horilla_middlewares import _thread_locals


class DynamicFieldForm(ModelForm):
    """
    DynamicFieldForm
    """

    display_title = _("Add Field")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields = {
                "verbose_name": self.fields["verbose_name"],
                "is_required": self.fields["is_required"],
            }

    class Meta:
        """
        Meta class for additional options
        """

        model = models.DynamicField
        fields = "__all__"
        exclude = [
            "model",
            "remove_column",
            "choices",
        ]


class ChoiceForm(ModelForm):
    """
    ChoiceForm
    """

    class Meta:
        """
        Meta class for additional option
        """

        model = models.Choice
        fields = "__all__"


og_init = forms.ModelForm.__init__
og_get_item = forms.ModelForm.__getitem__


class AddFieldWidget(forms.Widget):
    """
    Widget to add DynamicFields
    """

    template_name = "dynamic_fields/add_df.html"

    def __init__(self, attrs=None, form=None):
        self.form = form
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["form"] = self.form
        return context


class DFWidget(forms.Widget):
    """
    DFWidget
    """

    template_name = "dynamic_fields/df.html"

    def __init__(self, attrs=None, form=None):
        self.form = form
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["form"] = self.form
        return context


def get_item_override(self: forms.ModelForm, name):
    """Return a custom BoundField."""
    if name not in self.removed_hdf:
        result = og_get_item(self, name)
        return result


def init_override(self: forms.ModelForm, *args, **kwargs):
    """
    Method to override the ModelForm actual __init__ method
    """
    model: models.Model = self._meta.model
    model_path = f"{model.__module__}.{model.__name__}"
    removed_fields = DynamicField.objects.filter(
        model=model_path, remove_column=True
    ).values_list("field_name", flat=True)
    self.removed_hdf = removed_fields
    og_init(self, *args, **kwargs)
    for df in removed_fields:
        if df in self.fields.keys():
            del self.fields[df]
    other_df = DynamicField.objects.filter(model=model_path, remove_column=False)
    for df in other_df:
        if df not in self.fields:
            form_field = df.get_field().formfield()
            form_field.widget = DFWidget(attrs=form_field.widget.attrs, form=self)
            attrs = form_field.widget.attrs
            attrs["pk"] = df.pk
            attrs["class"] = attrs.get("class", "") + "oh-input w-100"
            if df.type == "2":
                attrs["type"] = "number"
            elif df.type == "3":
                attrs["type"] = "text_area"
                attrs["cols"] = "40"
                attrs["rows"] = "2"
            elif df.type == "4":
                attrs["type"] = "date"
            elif df.type == "5":
                attrs["type"] = "file"
            self.fields[df.field_name] = form_field
            if self._meta.fields is not None:
                self._meta.fields.append(df.field_name)

    # A form can be built outside a request, by a background job for example.
    request = getattr(_thread_locals, "request", None)
    if (
        request
        # self._meta.model in DF_ALLOWED_MODELS and
        and self._meta.model not in DF_NOT_ALLOWED_MODELS
        and request.user.has_perm("dynamic_fields.add_dynamicfield")
    ):
        self.df_user_has_change_perm = request.user.has_perm(
            "dynamic_fields.change_dynamicfield"
        )
        self.df_user_has_delete_perm = request.user.has_perm(
            "dynamic_fields.delete_dynamicfield"
        )
        self.fields["add_df"] = forms.CharField(
            label="Add field",
            widget=AddFieldWidget(
                form=self,
            ),
            required=False,
        )
        self.df_form_model_path = model_path


forms.ModelForm.__init__ = init_override
forms.ModelForm.__getitem__ = get_item_override
