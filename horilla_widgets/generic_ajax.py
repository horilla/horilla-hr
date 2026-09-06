"""
generic_ajax.py

Generic, reusable building block for AJAX-backed select widgets (see
horilla_widgets.widgets.select_widgets.HorillaAjaxSelectWidget). An app view
scopes/permission-checks its own queryset as usual, then hands it to
build_ajax_choices_response() to get back a Select2-format JSON response --
so every field's search endpoint stays a few lines of app-specific code
(the scoping/permission part, which genuinely differs per field) without
re-implementing search/pagination/response-shape each time.
"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse

DEFAULT_PAGE_SIZE = 20

# Populated only from FilterSet class bodies at import time (see
# horilla.filters.HorillaFilterSet.ajax_fields / __init_subclass__), never
# from client input -- horilla_widgets.views.ajax_select_choices looks up
# a client-supplied "key" here, so a key that was never registered here
# simply can't resolve to a queryset, regardless of what a client sends.
_AJAX_FIELD_REGISTRY = {}


def register_ajax_field(key, queryset_fn, display_fn, search_fields, permission=None):
    """
    Registers one AJAX-searchable field for the generic ajax_select_choices
    endpoint to serve.

    - key: unique across the whole app; what the client's ajax_url embeds
      and the endpoint looks this registry up by.
    - queryset_fn: callable(request) -> queryset, called per-request (not
      cached) so it can apply request-time scoping (company, permission-
      filtered subordinates, etc.) the same way any other view would.
    - display_fn / search_fields: forwarded to build_ajax_choices_response.
    - permission: an "app_label.codename" string checked via
      request.user.has_perm before the search runs; None means any
      authenticated user (the endpoint itself still requires login).
    """
    _AJAX_FIELD_REGISTRY[key] = {
        "queryset_fn": queryset_fn,
        "display_fn": display_fn,
        "search_fields": search_fields,
        "permission": permission,
    }


def get_ajax_field_config(key):
    """Returns the registered config dict for `key`, or None if unregistered."""
    return _AJAX_FIELD_REGISTRY.get(key)


def build_ajax_choices_response(
    request, queryset, display_fn, search_fields=None, page_size=DEFAULT_PAGE_SIZE
):
    """
    Build a Select2-format JSON response for an AJAX-backed select field.

    - queryset: already permission/company scoped by the caller.
    - display_fn: callable(instance) -> str, the label shown to the user.
    - search_fields: ORM lookup paths (e.g. "department") to icontains
      against the "q" query param. Skipped (no filtering) if falsy.
    - page_size: results per page; "page" query param drives pagination.
    """
    query = request.GET.get("q", "").strip()
    try:
        page_number = int(request.GET.get("page") or 1)
    except ValueError:
        page_number = 1

    if query and search_fields:
        term_filter = Q()
        for field in search_fields:
            term_filter |= Q(**{f"{field}__icontains": query})
        queryset = queryset.filter(term_filter)

    if not queryset.query.order_by:
        queryset = queryset.order_by("pk")
    paginator = Paginator(queryset.distinct(), page_size)
    page = paginator.get_page(page_number)

    return JsonResponse(
        {
            "results": [{"id": obj.pk, "text": display_fn(obj)} for obj in page],
            "pagination": {"more": page.has_next()},
        }
    )
