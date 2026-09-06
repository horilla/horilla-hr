"""
filters.py
"""

import uuid

import django_filters
from django import forms
from django.core.exceptions import ValidationError
from django.core.paginator import Page, Paginator
from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import Coalesce, Concat
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django_filters.filterset import FILTER_FOR_DBFIELD_DEFAULTS

from base.methods import reload_queryset
from horilla.horilla_middlewares import _thread_locals
from horilla_views.templatetags.generic_template_filters import getattribute
from horilla_widgets.generic_ajax import register_ajax_field
from horilla_widgets.widgets.select_widgets import HorillaAjaxSelectWidget

FILTER_FOR_DBFIELD_DEFAULTS[models.ForeignKey][
    "filter_class"
] = django_filters.ModelMultipleChoiceFilter


def filter_by_name(queryset, name, value):
    """
    Filter queryset by first name or last name.
    """
    qs = queryset
    value = " ".join(value.split())

    queryset = queryset.annotate(
        full_name=Concat(
            Coalesce("employee_id__employee_first_name", Value("")),
            Value(" "),
            Coalesce("employee_id__employee_last_name", Value("")),
        )
    )

    queryset = queryset.filter(full_name__icontains=value)

    queryset = (queryset | qs.filter(employee_id__badge_id__icontains=value)).distinct()

    return queryset


def filter_name_or_badge_terms(
    queryset, value, first_name_field, last_name_field, badge_field
):
    """
    Comma-separated "Name or Badge ID" search -- splits `value` into
    individual terms (blank terms from stray/trailing commas dropped,
    e.g. "PEP01, PEP02, jane"); a record matches if ANY term is found in
    its first name, last name, or badge ID. Field paths are
    parameterized since the model being filtered varies (EmployeeFilter
    matches its own employee fields directly; a FilterSet for a model
    with an `employee_id` FK, like AttendanceFilters, matches through
    that relation instead) -- see EmployeeFilter.filter_name_or_badge /
    AttendanceFilters.filter_name_or_badge for the two current callers.
    Reuse this (rather than re-implementing the comma-split matching by
    hand) for any new FilterSet's own "Name or Badge ID" field.
    """
    terms = [term.strip() for term in value.split(",") if term.strip()]
    if not terms:
        return queryset
    q_objects = Q()
    for term in terms:
        q_objects |= (
            Q(**{f"{first_name_field}__icontains": term})
            | Q(**{f"{last_name_field}__icontains": term})
            | Q(**{f"{badge_field}__icontains": term})
        )
    return queryset.filter(q_objects).distinct()


class FilterSet(django_filters.FilterSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        reload_queryset(self.form.fields)

        default_input_class = "oh-input w-100"
        select_class = "oh-select oh-select-2"
        checkbox_class = "oh-switch__checkbox"

        for field_name, field in self.form.fields.items():
            widget = field.widget
            label = _(field.label) if field.label else ""

            # Date field
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"
                field.input_formats = ["%Y-%m-%d"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Time field
            elif isinstance(widget, forms.TimeInput):
                widget.input_type = "time"
                widget.format = "%H:%M"
                field.input_formats = ["%H:%M"]

                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                    }
                )

            # Number, Email, Text, File, URL fields
            elif isinstance(
                widget,
                (
                    forms.NumberInput,
                    forms.EmailInput,
                    forms.TextInput,
                    forms.FileInput,
                    forms.URLInput,
                ),
            ):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": _(field.label.title()) if field.label else "",
                    }
                )

            # Select fields
            elif isinstance(widget, forms.Select):
                if not isinstance(field, forms.ModelMultipleChoiceField):
                    field.empty_label = _("---Choose {label}---").format(label=label)
                existing_class = widget.attrs.get("class", select_class)
                widget.attrs.update(
                    {
                        "class": existing_class,
                        "id": str(uuid.uuid4()),
                    }
                )

            # Textarea
            elif isinstance(widget, forms.Textarea):
                existing_class = widget.attrs.get("class", default_input_class)
                widget.attrs.update(
                    {
                        "class": f"{existing_class} form-control",
                        "placeholder": label,
                        "rows": 2,
                        "cols": 40,
                    }
                )

            # Checkbox types
            elif isinstance(
                widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)
            ):
                existing_class = widget.attrs.get("class", checkbox_class)
                widget.attrs.update({"class": existing_class})


class HorillaPaginator(Paginator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_count = 0
        self.end_count = 0

    def get_page(self, number):
        self.page = super().get_page(number)
        self.page.start_count = (
            1
            if number == 1 or number is None
            else max((int(number) - 1) * self.per_page + 1, 1)
        )
        self.page.end_count = (
            min(int(number) * self.per_page, self.count)
            if number and int(number) > 1
            else self.per_page
        )
        return self.page


class HorillaFilterSet(FilterSet):
    """
    HorillaFilterSet

    Any subclass can opt a ModelMultipleChoiceField into an AJAX-loaded
    combobox -- searched/paginated on the server instead of pre-rendering
    its whole queryset as <option> tags, for fields whose option count is
    large (100s-1000s) -- by declaring `ajax_fields` on the class body:

        class MyFilter(HorillaFilterSet):
            ajax_fields = {
                "some_fk_or_m2m_field": {
                    "key": "my-app-my-field",   # unique across the whole app
                    "queryset_fn": lambda request: SomeModel.objects.all(),
                    "display_fn": lambda obj: str(obj),
                    "search_fields": ["name", "code"],
                    "placeholder": _("Search..."),
                    "permission": "app.view_somemodel",  # optional
                },
            }

    That declaration is the entire integration surface -- no new view, no
    new URL. One endpoint (horilla_widgets.views.ajax_select_choices, at
    the "horilla-ajax-choices" URL name) serves every field registered
    this way, dispatching on "key" via the registry in
    horilla_widgets.generic_ajax. queryset_fn is called per-request (not
    the widget-swap's own bound queryset), so it can apply request-time
    scoping (company, permission-filtered subordinates, etc.) the same
    way any other view would.

    Beyond that, the caller still owns placing the field in a template
    (`{{form.field_name}}`) same as any other field -- widget/rendering
    only, no extra markup needed since HorillaAjaxSelectWidget carries
    its own class/data attrs that the existing .oh-select-ajax JS init
    already picks up.
    """

    verbose_name: dict = {}
    ajax_fields: dict = {}

    # Lookups allowed per custom-filter field type, for the Advanced
    # section's "+ Add filter" builder (see _build_custom_filter_fields) --
    # deliberately a small, explicit whitelist (not e.g. every lookup
    # Django supports) since these get built into a queryset.filter(**{...})
    # call straight from client-supplied field/lookup keys in
    # _apply_custom_filters, or (for the "duration_*" categories)
    # dispatched to one specific already-declared Filter -- anything not
    # listed here for the field's own type is rejected outright either way.
    # Shared across every FilterSet that opts into the builder (see
    # EmployeeFilter/AttendanceFilters for the two current registries) so
    # the categories don't get redefined per subclass.
    CUSTOM_FILTER_LOOKUPS: dict = {
        "text": [
            ("icontains", _("Contains")),
            ("iexact", _("Is exactly")),
            ("istartswith", _("Starts with")),
        ],
        "choice": [("exact", _("Is"))],
        # date/time_range: a real ORM-comparable field (DateField/
        # TimeField), so every standard comparison lookup makes sense --
        # unlike duration_from/till below, this isn't dispatched through
        # a declared Filter, just a plain queryset.filter(**{field__
        # lookup: value}) in _apply_custom_filters (Django's DateField/
        # TimeField.to_python parses the raw submitted string directly,
        # no form-cleaning round trip needed).
        "date_range": [
            ("gte", _("From")),
            ("lte", _("Till")),
            ("gt", _("After")),
            ("lt", _("Before")),
            ("exact", _("Is")),
        ],
        "time_range": [
            ("gte", _("From")),
            ("lte", _("Till")),
            ("gt", _("After")),
            ("lt", _("Before")),
            ("exact", _("Is")),
        ],
        # datetime_range: same reasoning as date_range/time_range above --
        # a plain DateTimeField column, so every standard comparison
        # lookup applies via a raw queryset.filter() call (e.g.
        # AttendanceActivityFilter's in_datetime/out_datetime).
        "datetime_range": [
            ("gte", _("From")),
            ("lte", _("Till")),
            ("gt", _("After")),
            ("lt", _("Before")),
            ("exact", _("Is")),
        ],
        # duration_from/till: the field being picked already has ONE
        # fixed direction baked in (e.g. AttendanceFilters.
        # overtime_second__gte IS the ">=" side of that range, via a
        # separate Filter object from overtime_second__lte -- there's no
        # OTHER lookup that filter itself supports), so there's exactly
        # one option here. Kept as a real (key, label) pair rather than
        # hiding the lookup column entirely, so the row still reads as
        # "field >= value" / "field <= value" instead of just "field
        # value".
        "duration_from": [("gte", _("Greater or Equal"))],
        "duration_till": [("lte", _("Lesser or Equal"))],
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for config in cls.ajax_fields.values():
            register_ajax_field(
                config["key"],
                config["queryset_fn"],
                config["display_fn"],
                config["search_fields"],
                config.get("permission"),
            )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in self.verbose_name.items():
            self.form.fields[key].label = value
        self._apply_ajax_fields()
        # custom_filter_fields/custom_filter_rows: the Advanced section's
        # "+ Add filter" builder (see _build_custom_filter_fields,
        # _extract_custom_filter_rows below). Built here so every
        # subclass gets this for free just by overriding
        # _build_custom_filter_fields -- _build_custom_filter_fields's
        # own default returns [], so a FilterSet that doesn't opt in
        # renders nothing extra.
        self.custom_filter_fields = self._build_custom_filter_fields()
        self.custom_filter_rows = self._extract_custom_filter_rows()

        request = getattr(_thread_locals, "request", None)
        if request:
            setattr(request, "is_filtering", True)

    def _apply_ajax_fields(self):
        """
        Per-instance half of `ajax_fields`: swap in the AJAX widget and
        trim the bound field's queryset down to just whatever's currently
        selected (so the widget still displays correctly without an
        extra round trip) -- everything else is fetched on demand by the
        generic endpoint. Separate from __init_subclass__'s registration
        because this part needs self.data (this request's selected
        values), not just the static config.
        """
        for field_name, config in self.ajax_fields.items():
            field = self.form.fields.get(field_name)
            if field is None:
                continue
            selected_values = self.data.getlist(field_name) if self.data else []
            field.widget = HorillaAjaxSelectWidget(
                # reverse_lazy, not reverse: some FilterSets are
                # instantiated at class-body time (e.g. a NavView's
                # `filter_instance = MyFilter()`), while urls.py may
                # still be mid-import -- resolving now would risk a
                # circular import. The lazy proxy only resolves to a
                # real path when stringified, which HorillaAjaxSelectWidget
                # only does inside build_attrs, at actual render time.
                ajax_url=reverse_lazy("horilla-ajax-choices", args=[config["key"]]),
                placeholder=config.get("placeholder", ""),
            )
            if selected_values:
                field.queryset = field.queryset.filter(pk__in=selected_values)
            else:
                field.queryset = field.queryset.none()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder --
        empty by default (a subclass that doesn't override this gets no
        builder at all). See EmployeeFilter/AttendanceFilters for real
        registries and the two supported entry shapes:

        - Plain field+lookup (e.g. EmployeeFilter's Phone/Country/Gender,
          or AttendanceFilters' Clock In/Out): {"key", "field": "<model
          path>", "label", "type", ...}. Applied as a raw queryset.
          filter(**{f"{field}__{lookup}": value}) -- "type" must be one
          of CUSTOM_FILTER_LOOKUPS's plain categories ("text"/"choice"/
          "date_range"/"time_range"). Works for any field the database
          itself can compare directly (a DateField/TimeField's own
          to_python parses the raw submitted string), which is why
          date/time_range offer a full gte/lte/gt/lt/exact choice instead
          of one fixed direction.
        - Declared-filter (e.g. AttendanceFilters' Pending Hour/OT
          ranges): {"key", "filter_name": "<name in self.filters>",
          "label", "type", ...}, where "type" is one of the
          "duration_from"/"duration_till" categories. Applied by cleaning
          the raw value through that Filter's OWN field.clean() and
          calling its OWN .filter() -- reusing whatever custom conversion
          that filter already does (e.g. AttendanceFilters.
          overtime_second__gte's "HH:MM:SS" -> seconds conversion, or
          filter_pending_hour's per-record computation) instead of
          assuming every field is a plain ORM lookup the way the first
          shape does. Each direction needs its own Filter object here
          (unlike Clock In/Out above), so unlike date/time_range this
          can't offer more than the one lookup that Filter itself does.

        Either shape also accepts an "ajax" sub-dict (see
        EmployeeFilter.CUSTOM_FILTER_AJAX_FIELDS) for a model-backed
        "choice" field, so its value input is an AJAX-searched combobox
        instead of a fully preloaded <select>.

        Consumed generically by HorillaNavView (as context
        "custom_filter_fields") and rendered by each app's own filter
        template; applied server-side by _apply_custom_filters below.
        """
        return []

    def _extract_custom_filter_rows(self):
        """
        Field/lookup/value triples currently applied via the Advanced
        section's custom-filter builder, for the client to restore its
        row UI from (see custom_filter_rows in the nav context and
        initCustomFilterBuilder in horilla_nav.html). Same parsing/
        validation as _apply_custom_filters, just returning the rows
        instead of filtering a queryset with them.
        """
        if not self.data:
            return []
        registry = {f["key"]: f for f in self.custom_filter_fields}
        keys = self.data.getlist("custom_field")
        lookups = self.data.getlist("custom_lookup")
        values = self.data.getlist("custom_value")
        ajax_registry = getattr(self, "CUSTOM_FILTER_AJAX_FIELDS", {})
        rows = []
        for key, lookup, value in zip(keys, lookups, values):
            if not key or key not in registry:
                continue
            row = {"field": key, "lookup": lookup, "value": value}
            ajax_config = ajax_registry.get(key)
            if ajax_config and value:
                obj = ajax_config["queryset_fn"](self.request).filter(pk=value).first()
                if obj:
                    row["label"] = ajax_config["display_fn"](obj)
            rows.append(row)
        return rows

    def _apply_custom_filters(self, queryset):
        """
        Apply the Advanced section's custom (field, lookup, value) rows.
        Reads the raw parallel arrays directly off self.data rather than
        going through a declared django_filters Filter for the whole
        row, since those skip calling filter() entirely when their OWN
        field's value is empty -- there's no single "custom" field with
        a value here, only the three arrays. field/lookup are validated
        against custom_filter_fields and CUSTOM_FILTER_LOOKUPS (never
        used to build a filter() call unless both match a known,
        intended combination), so a client can't submit an arbitrary
        field path or lookup expression.

        A subclass's caller must actually invoke this -- it isn't wired
        into filter_queryset automatically here, since some subclasses
        (EmployeeFilter) override filter_queryset entirely with their own
        extra logic. See AttendanceFilters.filter_queryset for the
        minimal "call this at the end" pattern.
        """
        if not self.data:
            return queryset
        registry = {f["key"]: f for f in self.custom_filter_fields}
        keys = self.data.getlist("custom_field")
        lookups = self.data.getlist("custom_lookup")
        values = self.data.getlist("custom_value")
        for key, lookup, value in zip(keys, lookups, values):
            if not key or not value:
                continue
            config = registry.get(key)
            if not config:
                continue
            allowed_lookups = {
                lk for lk, _label in self.CUSTOM_FILTER_LOOKUPS.get(config["type"], [])
            }
            if lookup not in allowed_lookups:
                continue
            filter_name = config.get("filter_name")
            if filter_name:
                declared_filter = self.filters.get(filter_name)
                if declared_filter is None:
                    continue
                try:
                    cleaned_value = declared_filter.field.clean(value)
                except ValidationError:
                    continue
                queryset = declared_filter.filter(queryset, cleaned_value)
            else:
                queryset = queryset.filter(**{f'{config["field"]}__{lookup}': value})
        return queryset

    def search_in(self, queryset, name, value):
        """
        Search in generic method for filter field
        """
        search = self.data.get("search", "")
        search_field = self.data.get("search_field")
        if not search_field:
            search_field = self.filters[name].field_name

        def _icontains(instance):
            result = str(getattribute(instance, search_field)).lower()
            return instance.pk if search in result else None

        ids = list(filter(None, map(_icontains, queryset)))
        return queryset.filter(id__in=ids)
