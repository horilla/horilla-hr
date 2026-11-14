import re
from collections import defaultdict

from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Window
from django.db.models.fields.related_descriptors import ForwardManyToOneDescriptor
from django.db.models.functions import RowNumber
from django.utils.translation import gettext as _

from horilla.group_by import _page_from_list, _page_of_groupers, _resolve_fk_groupers
from horilla.horilla_middlewares import _thread_locals


def _ordered_keep_none(values):
    """
    Like horilla.group_by._ordered_unique, but keeps None as its own
    grouper instead of dropping it. A record with no value for the group
    field (e.g. work_type_id left unset) is still a real group -- dropping
    it here silently excluded those rows from every level below the one
    where they went missing, while the parent's own count kept including
    them, so the tree's numbers stopped adding up with no visible group to
    account for the gap.
    """
    return list(dict.fromkeys(values))


# Several models (e.g. JobPosition) render their str() as "Name - (Parent)"
# for disambiguation in flat dropdowns. Nested under that same parent group,
# repeating it on every child header is redundant noise -- strip it there.
_PARENTHETICAL_CONTEXT_RE = re.compile(r"\s*-\s*\([^)]*\)\s*$")


def _strip_redundant_context(value):
    text = str(value)
    stripped = _PARENTHETICAL_CONTEXT_RE.sub("", text).strip()
    return stripped or text


def _related_model_for_field(model, group_field):
    """
    Resolve the target model class for a (possibly dotted) FK field path,
    or None if group_field is a plain scalar field.
    """
    fields_split = group_field.split("__")
    is_fk_field = isinstance(
        getattr(model, group_field, None), ForwardManyToOneDescriptor
    )
    if len(fields_split) == 1 and not is_fk_field:
        return None
    model_copy = model
    for field in fields_split:
        field_obj = model_copy._meta.get_field(field)
        model_copy = field_obj.related_model
    return model_copy


def _display_map_for_field(model, group_field, values):
    """Map each raw value of a non-FK field to its display label."""
    display_method = f"get_{group_field}_display"
    if not hasattr(model, display_method):
        return {value: value for value in values}
    return {
        value: getattr(model(**{group_field: value}), display_method)()
        for value in values
    }


def _window_order(queryset):
    """
    Build the ordering used to number rows inside each group.

    Parameters:
        queryset (QuerySet): The queryset being grouped.

    Returns:
        list: Order-by expressions from the queryset's ordering, ending in pk.
    """
    ordering = list(queryset.query.order_by) or (
        list(queryset.model._meta.ordering) if queryset.query.default_ordering else []
    )
    expressions = []
    for item in ordering:
        if isinstance(item, str):
            expressions.append(
                F(item[1:]).desc() if item.startswith("-") else F(item).asc()
            )
        else:
            expressions.append(item)
    expressions.append(F("pk").asc())
    return expressions


def _leaf_dynamic_name(key):
    """
    Build the pagination GET parameter name of the leaf group a key points to.

    Parameters:
        key (tuple): The group value at every level, outermost first.

    Returns:
        str: The parameter name build_level assigns to that leaf.
    """
    prefix = "ngb"
    name = None
    for value in key:
        name = f"dynamic_page_{prefix}_{value}".replace(" ", "_")
        prefix = f"{prefix}_{value}"
    return name


def nested_group_by_queryset(
    queryset, group_fields, page=None, page_name="page", records_per_page=None
):
    """
    Hierarchical group-by, 1 or more levels deep (e.g. Department, or
    Department -> Job Position).

    Naively recursing group_by_queryset per outer group would issue a fresh
    query burst for every visible top-level group (N+1 across nesting
    levels). Instead this resolves every (level0, level1, ..., count)
    combination that actually occurs in ONE SQL GROUP BY query, then only
    fetches label objects for the current top-level page and, for each leaf
    group, only the rows of the page it is showing — query cost and row
    loading stay flat regardless of table size or group count.
    """
    from base.methods import get_pagination

    if not records_per_page:
        records_per_page = get_pagination(default=10)

    if len(group_fields) < 1:
        raise ValueError("nested_group_by_queryset requires at least 1 group_field")

    model = queryset.model
    request = getattr(_thread_locals, "request", None)

    # One SQL GROUP BY query for every combination that actually occurs.
    combos = list(
        queryset.values(*group_fields).annotate(_n=Count("pk")).order_by(*group_fields)
    )

    level0_field = group_fields[0]
    level0_keys = _ordered_keep_none(c[level0_field] for c in combos)
    page_obj, page_keys = _page_of_groupers(level0_keys, page, records_per_page)
    page_keys_set = set(page_keys)
    page_combos = [c for c in combos if c[level0_field] in page_keys_set]

    leaf_ranges = {}
    for combo in page_combos:
        key = tuple(combo[f] for f in group_fields)
        requested = request.GET.get(_leaf_dynamic_name(key)) if request else None
        number = (
            Paginator(range(combo["_n"]), records_per_page).get_page(requested).number
        )
        leaf_ranges[key] = ((number - 1) * records_per_page, number * records_per_page)

    # A plain `__in` lookup never matches NULL rows even when None is
    # explicitly in the list (SQL's `IN (NULL)` never matches), so a
    # None grouper needs its own explicit isnull=True branch or that
    # whole top-level group's rows silently never get fetched.
    non_null_page_keys = [k for k in page_keys if k is not None]
    level0_filter = Q(**{f"{level0_field}__in": non_null_page_keys})
    if None in page_keys_set:
        level0_filter |= Q(**{f"{level0_field}__isnull": True})
    numbered_rows = (
        queryset.filter(level0_filter)
        .annotate(
            _row_number=Window(
                RowNumber(),
                partition_by=[F(f) for f in group_fields],
                order_by=_window_order(queryset),
            )
        )
        .values("pk", "_row_number", *group_fields)
    )
    ranked_pks = defaultdict(list)
    for row in numbered_rows:
        key = tuple(row[f] for f in group_fields)
        ranked_pks[key].append((row["_row_number"], row["pk"]))
    pks_by_key = {
        key: [pk for _, pk in sorted(rows)] for key, rows in ranked_pks.items()
    }
    page_pks_by_key = {
        key: pks[slice(*leaf_ranges.get(key, (0, 0)))]
        for key, pks in pks_by_key.items()
    }
    objects_by_pk = {
        obj.pk: obj
        for obj in queryset.filter(
            pk__in=[pk for pks in page_pks_by_key.values() for pk in pks]
        )
    }
    rows_by_key = {
        key: [objects_by_pk[pk] for pk in pks if pk in objects_by_pk]
        for key, pks in page_pks_by_key.items()
    }

    # Label objects resolved only for values occurring under the current
    # page of top-level groups, not the whole table.
    label_cache = {}
    for level, field in enumerate(group_fields):
        related_model = _related_model_for_field(model, field)
        distinct_values = _ordered_keep_none(c[field] for c in page_combos)
        fk_values = [v for v in distinct_values if v is not None]
        if related_model and fk_values:
            resolved = _resolve_fk_groupers(related_model, fk_values)
            if level > 0:
                resolved = [_strip_redundant_context(r) for r in resolved]
            label_cache[field] = dict(zip(fk_values, resolved))
        else:
            label_cache[field] = _display_map_for_field(model, field, fk_values)
        if None in distinct_values:
            label_cache[field][None] = _("Not specified")

    def build_level(prefix_key, combos_here, level, dynamic_prefix):
        field = group_fields[level]
        ordered_values = _ordered_keep_none(c[field] for c in combos_here)
        nodes = []
        for value in ordered_values:
            key = prefix_key + (value,)
            child_combos = [c for c in combos_here if c[field] == value]
            # dynamic_name is the *actual* GET param name for this node's
            # pagination (mirrors horilla/group_by.py's convention, where
            # dynamic_name already includes the "dynamic_page_" prefix and
            # is passed to _page_from_list verbatim) — templates read/write
            # this same string, so it must never diverge from what
            # _page_from_list is told to look for below.
            dynamic_name = f"dynamic_page_{dynamic_prefix}_{value}".replace(" ", "_")
            node = {
                "grouper": label_cache[field].get(value, value),
                "count": sum(c["_n"] for c in child_combos),
                "level": level,
                "dynamic_name": dynamic_name,
            }
            if level + 1 < len(group_fields):
                node["children"] = build_level(
                    key, child_combos, level + 1, f"{dynamic_prefix}_{value}"
                )
                node["list"] = None
            else:
                node["children"] = None
                node["list"] = _page_from_list(
                    rows_by_key.get(key, []),
                    dynamic_name,
                    request,
                    records_per_page,
                    total_count=node["count"],
                )
                node["list"].all_pks = pks_by_key.get(key, [])
            nodes.append(node)
        return nodes

    tree = build_level((), page_combos, 0, "ngb")

    # Keep paginator metadata (count/num_pages) for all top-level groupers
    # while only materializing the current page of group payloads.
    page_obj.object_list = tree
    return page_obj
