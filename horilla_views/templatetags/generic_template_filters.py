"""
horilla_views/templatetags/generic_template_filters.py

This module is used to write custom template filters.

"""

import datetime
import functools
import json
import re
import types

from django import template
from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.db.models import Model, QuerySet
from django.db.models.utils import AltersData
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from horilla.config import import_method
from horilla.horilla_middlewares import _thread_locals
from horilla_views.related_link_registry import resolve_detail_link

register = template.Library()


numeric_test = re.compile(r"^\d+$")

date_format_mapping = {
    "DD-MM-YYYY": "%d-%m-%Y",
    "DD.MM.YYYY": "%d.%m.%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY/MM/DD": "%Y/%m/%d",
    "MMMM D, YYYY": "%B %d, %Y",
    "DD MMMM, YYYY": "%d %B, %Y",
    "MMM. D, YYYY": "%b. %d, %Y",
    "D MMM. YYYY": "%d %b. %Y",
    "dddd, MMMM D, YYYY": "%A, %B %d, %Y",
}

time_format_mapping = {
    "hh:mm A": "%I:%M %p",
    "HH:mm": "%H:%M",
}


@register.filter(name="selected_format")
def selected_format(date, company: object = None) -> str:
    if not isinstance(date, (datetime.date, datetime.time)):
        try:
            date = datetime.datetime.fromisoformat(date)
        except:
            return date
    if company and (company.date_format or company.time_format):
        if isinstance(date, datetime.date):
            format = company.date_format if company.date_format else "MMM. D, YYYY"
            date_format_mapping.get(format)
            return date.strftime(date_format_mapping[format])
        elif isinstance(date, datetime.time):
            format = company.time_format if company.time_format else "hh:mm A"
            return date.strftime(time_format_mapping[format])
    return date


@register.filter(name="cell_tooltip")
def cell_tooltip(value) -> str:
    """
    Tooltip text for a list-table cell: plain text collapsed to single spaces.
    Cells rendering interactive widgets get no tooltip — stripping their tags
    would concatenate hidden text (e.g. every option of a select).
    """
    from django.utils.html import strip_tags

    text = str(value)
    if re.search(r"<\s*(select|input|textarea|button|form)\b", text, re.IGNORECASE):
        return ""
    return re.sub(r"\s+", " ", strip_tags(text)).strip()


@register.filter(name="getattribute")
def getattribute(value, attr: str):
    """
    Gets an attribute of an object dynamically from a string name
    """
    result = ""
    attrs = attr.split("__")
    for attr in attrs:
        if isinstance(
            value,
            AltersData,
        ) and hasattr(value, "through"):
            result = []
            queryset = value.all()
            for record in queryset:
                result.append(getattribute(record, attr))
        elif hasattr(value, str(attr)):
            result = getattr(value, attr)
            if isinstance(result, (types.MethodType, functools.partial)):
                result = result()
            value = result
        else:
            return getattr(value, attr, "")

    # Python code we need raw bool values, not "Yes"/"No"
    # if isinstance(result, bool):
    #     return _("Yes") if result else _("No")

    return result


@register.filter(name="linkify")
def linkify(value, user=None):
    """
    Wrap a resolved related-object value in a link that opens its detail view in
    a dedicated secondary modal (#relatedObjectModal, stacked above #genericModal
    via a higher z-index), when one is registered and the given user has
    permission to view it. Falls back to the value unchanged otherwise.

    A separate modal (rather than reusing #genericModalBody) means opening a
    related object's detail from inside an already-open detail modal doesn't
    replace that modal's content — closing the related-object modal leaves the
    original one still open underneath.

    Detail-view use only — do not wire this into list-view templates, where
    related values must stay plain text.

    Styling uses the app's own primary-color utility classes (text-primary-600),
    not hardcoded colors: the text stays default-colored until hover, when it
    and the arrow both take the primary color and the text underlines.

    A QuerySet (or list/tuple) of Model instances — e.g. a many-to-many field
    such as Recruitment.recruitment_managers — is linkified item by item, each
    as its own clickable link, joined with line breaks.
    """
    if isinstance(value, Model):
        url = resolve_detail_link(value, user)
        if url:
            return format_html(
                '<a href="javascript:void(0)" hx-get="{}" hx-target="#relatedObjectModalBody" '
                'data-target="#relatedObjectModal" data-toggle="oh-modal-toggle" '
                'onclick="event.stopPropagation()" '
                'class="oh-related-link hover:text-primary-600 cursor-pointer">{}'
                '<span class="text-primary-600" style="font-size:0.95em; margin-left:2px;">↗</span></a>',
                url,
                str(value),
            )
        return value

    if isinstance(value, QuerySet) or (
        isinstance(value, (list, tuple)) and value and isinstance(value[0], Model)
    ):
        items = list(value)
        if not items:
            return ""
        return format_html_join(
            mark_safe("<br>"), "{}", ((linkify(item, user),) for item in items)
        )

    return value


@register.filter(name="employee_profile_url")
def employee_profile_url(obj):
    """
    Return the employee individual-view URL for the employee a record belongs
    to — the record's `employee_id` FK, or the record itself when it already
    is an Employee. Returns "" when the record has no employee (e.g. Leave
    Type), letting templates fall back to plain text.

    Used by the generic detail-view modal to make the employee-name heading a
    link to that employee's profile.
    """
    from django.urls import NoReverseMatch, reverse

    from employee.models import Employee

    employee = obj if isinstance(obj, Employee) else getattr(obj, "employee_id", None)
    if isinstance(employee, Employee):
        try:
            return reverse("employee-view-individual", kwargs={"obj_id": employee.pk})
        except NoReverseMatch:
            return ""
    return ""


@register.filter(name="format")
def format(string: str, instance: object):
    """
    format
    """
    string = str(string)
    attr_placeholder_regex = r"{([^}]*)}"
    attr_placeholders = re.findall(attr_placeholder_regex, string)

    if not attr_placeholders:
        return string
    flag = instance
    format_context = {}
    for attr_placeholder in attr_placeholders:
        attr_name: str = attr_placeholder
        attrs = attr_name.split("__")
        for attr in attrs:
            if (
                attr.startswith("get_")
                and attr.endswith("_display")
                and callable(getattr(instance, attr, None))
            ):  # 874
                value = getattr(instance, attr)()
            else:
                value = getattr(instance, attr, "")

            if isinstance(value, types.MethodType):
                value = value()
            instance = value
            format_context[attr_name] = value
        instance = flag
    formatted_string = string.format(**format_context)

    return formatted_string


@register.filter("accessibility")
def accessibility(method: str, instance=None):
    if method:
        request = getattr(_thread_locals, "request")
        method = import_method(method)
        return method(
            request,
            instance,
            PermWrapper(request.user),
        )
    return True


@register.filter("col")
def col(field: object):
    """
    Method to get field col sepration
    """
    field_name = field.name
    cols = getattr(field.form, "cols", {})
    return cols.get(field_name, 6)


@register.filter("get_item")
def get_item(dictionary: dict, key: str):
    """
    get_item method to access from dictionary
    """
    if dictionary:
        return dictionary.get(key, "")
    return ""


@register.filter("id_list_json")
def id_list_json(queryset):
    """
    JSON-encode the pks of every row in queryset, not just the current page.
    Used to make a group's "Select" bulk-action select every matching record
    instead of only the rows rendered on the current pagination page.

    A group's `.paginator.object_list` isn't always a real queryset -- both
    the single-field and nested group-by engines build it via
    `_page_from_list`, paginating an already-fetched plain Python list of
    model instances instead. `.values_list()` doesn't exist on a list, so
    try that first and fall back to reading `.pk` off each instance
    directly, instead of silently returning "[]" for every grouped view.
    """
    try:
        return mark_safe(json.dumps(list(queryset.values_list("pk", flat=True))))
    except AttributeError:
        try:
            return mark_safe(json.dumps([obj.pk for obj in queryset]))
        except (AttributeError, TypeError):
            return "[]"
    except TypeError:
        return "[]"


@register.filter("get_id")
def get_id(string: str):
    """
    Generate target/id for the generic delete summary
    """
    return string.split("-")[0].lower().replace(" ", "")


@register.filter
def is_image_file(filename):
    """
    Django template filter to check if a given filename is an image file.
    """
    return filename.lower().endswith((".png", ".jpg", ".jpeg", ".svg"))


@register.filter(name="index")
def index(sequence, i):
    """
    sequence[i] with a runtime index — Django's dot-notation list access
    only works with a literal index in the template source (`.0`, `.1`),
    not a variable, since the segment after the dot is always resolved as
    a literal token, never substituted with that variable's value.
    """
    try:
        i = int(i)
    except (TypeError, ValueError):
        return None
    try:
        return sequence[i]
    except (IndexError, TypeError, KeyError):
        return None


@register.filter(name="has_attr")
def has_attr(instance, attr_name):
    """
    Whether `instance` exposes `attr_name` at all — used to gate optional,
    model-specific UI (e.g. an online/offline dot that only Employee
    supports) inside shared generic row templates without breaking other
    models that don't have it.
    """
    return hasattr(instance, attr_name)


@register.filter(name="child_group_path")
def child_group_path(parent_path, counter):
    """
    Build "<parent_path>-<counter>" for a nested group-by node's data-group
    attribute. NOT the same as `parent_path|add:"-"|add:counter`: Django's
    `add` filter tries int(value) + int(arg) first, and on a string parent
    path like "6-" that ValueErrors, falls back to value + arg, which then
    TypeErrors on str + int (counter is a real int from forloop.counter) —
    caught and silently swallowed into "". Every nested node below the top
    level ended up with data-group="" this whole time, which collapses
    every child's open/closed state into one shared (wrong) key.
    """
    return f"{parent_path}-{counter}"


@register.filter(name="mul")
def mul(value, arg):
    """
    Multiply value by arg. Used for per-level indentation in nested group-by
    (level * indent-px), where the number of levels is dynamic.
    """
    try:
        return int(value) * int(arg)
    except (TypeError, ValueError):
        return 0


@register.filter(name="elided_page_range")
def elided_page_range(page):
    """
    Returns the current page's elided page range (e.g. 1, 2, 3, "...", 209)
    with the paginator's ellipsis marker normalized to a plain "..." string.
    """
    return [
        "..." if p == page.paginator.ELLIPSIS else p
        for p in page.paginator.get_elided_page_range(
            page.number, on_each_side=1, on_ends=1
        )
    ]
