from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from horilla.decorators import login_required
from horilla_widgets.generic_ajax import (
    build_ajax_choices_response,
    get_ajax_field_config,
)
from horilla_widgets.widgets.select_widgets import (
    ALL_INSTANCES,
    HorillaMultiSelectWidget,
)

# Create your views here.

# urls.py
# path("employee-widget-filter",views.widget_filter,name="employee-widget-filter")

# views.py
# @login_required
# def widget_filter(request):
#     """
#     This method is used to return all the ids of the employees
#     """
#     ids = EmployeeFilter(request.GET).qs.values_list("id", flat=True)
#     return JsonResponse({'ids':list(ids)})


@login_required
def get_filter_form(request):
    """
    This method will return filtering from
    """
    widget_instance = ALL_INSTANCES.get(str(request.user.id))
    if widget_instance is None:
        return HttpResponse()
    template_path = request.GET.get("template_path")
    if not template_path:
        return HttpResponse()
    return render(request, template_path, {"f": widget_instance.filter_class()})


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
