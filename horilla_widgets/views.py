from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from horilla.decorators import login_required
from horilla_widgets.filters import EmployeePickerFilter
from horilla_widgets.generic_ajax import (
    build_ajax_choices_response,
    get_ajax_field_config,
    load_queryset,
)
from horilla_widgets.widgets.select_widgets import employee_avatar_url

PICKER_PAGE_SIZE = 50
PICKER_LABEL_BATCH = 200


@login_required
def ajax_select_choices(request, field_key):
    """
    Single, generic search endpoint backing every HorillaAjaxSelectWidget
    field in the app -- see horilla.filters.HorillaFilterSet.ajax_fields
    for how a FilterSet opts a field into this (declaratively; no new
    view or URL needed for a new field, in this app or any other).

    field_key is looked up in the server-side registry (populated only
    from FilterSet class bodies at import time, via
    HorillaFilterSet.__init_subclass__ -- never from client input), so a
    client can't point this at an arbitrary model/field by guessing a
    different key. An unregistered key, or a registered one whose
    optional `permission` this user lacks, both just return an empty
    result set rather than erroring, same as Select2 finding no matches.

    Not htmx-triggered (Select2's own $.ajax call won't carry the
    HX-Request header), so no @hx_request_required here.
    """
    config = get_ajax_field_config(field_key)
    if config is None:
        return JsonResponse({"results": []})
    if config["permission"] and not request.user.has_perm(config["permission"]):
        return JsonResponse({"results": []})
    queryset = config["queryset_fn"](request)
    return build_ajax_choices_response(
        request,
        queryset,
        display_fn=config["display_fn"],
        search_fields=config["search_fields"],
    )


def _filtered_picker_queryset(request):
    """Return ``(queryset, None)`` for the token and filters, or ``(None, error_response)``."""
    try:
        queryset = load_queryset(request.POST.get("token", ""))
    except ValueError as error:
        return None, JsonResponse({"errors": str(error)}, status=400)
    picker_filter = EmployeePickerFilter(
        data=request.POST, queryset=queryset, request=request
    )
    if not picker_filter.is_valid():
        return None, JsonResponse({"errors": picker_filter.errors}, status=400)
    return picker_filter.qs, None


@login_required
@require_POST
def employee_picker_ids(request):
    """Return the ids of the field's employees that match the picker modal's filters."""
    queryset, error = _filtered_picker_queryset(request)
    if error:
        return error
    return JsonResponse({"ids": list(queryset.values_list("id", flat=True))})


@login_required
@require_POST
def employee_picker_rows(request):
    """Return one page of the field's employees that match the picker modal's filters."""
    queryset, error = _filtered_picker_queryset(request)
    if error:
        return error
    requested_ids = [
        int(value)
        for value in request.POST.get("ids", "").split(",")[:PICKER_LABEL_BATCH]
        if value.isdigit()
    ]
    if requested_ids:
        employees = queryset.filter(pk__in=requested_ids)
        return JsonResponse(
            {"results": [_picker_row(employee) for employee in employees]}
        )
    if not queryset.ordered:
        queryset = queryset.order_by("pk")
    paginator = Paginator(queryset, PICKER_PAGE_SIZE)
    page = paginator.get_page(request.POST.get("page"))
    return JsonResponse(
        {
            "results": [_picker_row(employee) for employee in page],
            "total": paginator.count,
            "has_more": page.has_next(),
        }
    )


def _picker_row(employee):
    return {
        "id": employee.pk,
        "label": str(employee),
        "avatar": employee_avatar_url(employee),
    }
