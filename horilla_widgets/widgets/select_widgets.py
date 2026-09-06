"""
select_widgets.py

This module is used to write horilla form select widgets
"""

import uuid

from django import forms

from horilla import horilla_middlewares

ALL_INSTANCES = {}


def get_short_uuid(length: int, prefix: str = "widget"):
    """
    Short uuid generating method
    """
    uuid_str = str(uuid.uuid4().hex)
    return prefix + str(uuid_str[:length]).replace("-", "")


class HorillaMultiSelectWidget(forms.Widget):
    """
    HorillaMultiSelectWidget
    """

    def __init__(
        self,
        *args,
        filter_route_name,
        filter_class=None,
        filter_instance_context_name=None,
        filter_template_path=None,
        instance=None,
        required=False,
        form=None,
        help_text=None,
        **kwargs
    ) -> None:
        self.filter_route_name = filter_route_name
        self.required = required
        self.filter_class = filter_class
        self.filter_instance_context_name = filter_instance_context_name
        self.filter_template_path = filter_template_path
        self.instance = instance
        self.form = form
        self.help_text = help_text
        super().__init__()

    template_name = "horilla_widgets/horilla_multiselect_widget.html"

    def get_context(self, name, value, attrs):
        # Get the default context from the parent class
        context = super().get_context(name, value, attrs)
        # Django form widget templates don't receive `request` in their
        # context by default, which breaks the {% get_company %} templatetag
        # (theme lookup) used inside horilla_multiselect_widget.html. Pull it
        # from the thread-local set by ThreadLocalMiddleware instead.
        context["request"] = horilla_middlewares._thread_locals.request
        # Add your custom data to the context
        queryset = self.choices.queryset
        field = self.choices.field
        context["queryset"] = queryset
        context["field_name"] = name
        if self.form and name in self.form.data:
            initial = self.form.data.getlist(name)
            context["initial"] = initial
        elif value:
            context["initial"] = value

        elif self.instance and self.instance.pk:
            initial = list(getattr(self.instance, name).values_list("id", flat=True))
            context["initial"] = initial
        else:
            context["initial"] = []
        context["field"] = field
        context["self"] = self
        context["filter_template_path"] = self.filter_template_path
        context["filter_route_name"] = self.filter_route_name
        context["required"] = self.required
        context["help_text"] = self.help_text
        self.attrs["id"] = (
            ("id_" + name) if self.attrs.get("id") is None else self.attrs.get("id")
        )
        uid = get_short_uuid(5)
        context["section_id"] = uid
        context[self.filter_instance_context_name] = self.filter_class
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        ALL_INSTANCES[str(request.user.id)] = self

        return context


class HorillaAjaxSelectWidget(forms.SelectMultiple):
    """
    A plain forms.SelectMultiple that defers option loading to an AJAX
    search endpoint (see
    horilla_widgets.generic_ajax.build_ajax_choices_response) instead of
    pre-rendering the whole queryset as <option> tags -- for
    ModelMultipleChoiceFields whose option list is large/expensive (e.g.
    Permissions). SelectMultiple, not Select: FILTER_FOR_DBFIELD_DEFAULTS
    (horilla/filters.py) makes every FK/M2M filter in this app a
    ModelMultipleChoiceField, whose value_from_datadict expects a
    multi-value widget -- pairing it with a single-value Select would
    silently misparse a submitted id as several single-character ids.

    The caller is responsible for trimming the field's queryset down to
    just the currently selected instance(s) (or none) before rendering,
    so the widget still displays correctly without an extra round trip --
    see horilla.filters.HorillaFilterSet._apply_ajax_fields (the generic
    ajax_fields mechanism) for the pattern. Everything else is fetched on
    demand by the .oh-select-ajax initializer
    (horilla_theme/static/horilla_theme/assets/js/htmxSelect2.js).
    """

    def __init__(self, *args, ajax_url="", placeholder="", **kwargs):
        self.ajax_url = ajax_url
        self.placeholder = placeholder
        super().__init__(*args, **kwargs)

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["class"] = (attrs.get("class", "") + " oh-select-ajax").strip()
        attrs["data-ajax-url"] = self.ajax_url
        attrs["data-placeholder"] = self.placeholder
        return attrs
