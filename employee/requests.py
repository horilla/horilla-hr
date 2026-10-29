"""
employee/requests.py

Requests landing page with tabbed shift, inbox, work type, and document sections.
"""

from django.shortcuts import render

from horilla.decorators import hx_request_required, login_required

REQUEST_TABS = ("shift-request", "shift-inbox", "work-type", "document")


@login_required
def requests_view(request):
    """
    Requests landing page with tabbed shift, inbox, work type, and document sections.
    """
    # Deep links (e.g. dashboard KPI cards) pick a tab with ?tab=<id> and pass
    # the remaining query string on as the filters for that tab's list.
    query = request.GET.copy()
    initial_tab = query.pop("tab", [""])[-1]
    # ?open_tab=<1-based index> is accepted too, matching the other tabbed pages.
    open_tab = query.pop("open_tab", [""])[-1]
    if (
        not initial_tab
        and open_tab.isdigit()
        and 0 < int(open_tab) <= len(REQUEST_TABS)
    ):
        initial_tab = REQUEST_TABS[int(open_tab) - 1]
    if initial_tab not in REQUEST_TABS:
        initial_tab = ""
    return render(
        request,
        "requests/requests.html",
        {"initial_tab": initial_tab, "initial_query": query.urlencode()},
    )


@login_required
@hx_request_required
def requests_shift_request_tab(request):
    """
    HTMX tab body for shift requests under requests.
    """
    return render(request, "requests/requests_shift_request_tab.html")


@login_required
@hx_request_required
def requests_shift_inbox_tab(request):
    """
    HTMX tab body for shift inbox (allocated shifts) under requests.
    """
    return render(request, "requests/requests_shift_inbox_tab.html")


@login_required
@hx_request_required
def requests_work_type_tab(request):
    """
    HTMX tab body for work type requests under requests.
    """
    return render(request, "requests/requests_work_type_tab.html")


@login_required
@hx_request_required
def requests_document_tab(request):
    """
    HTMX tab body for document requests under requests.
    """
    return render(request, "requests/requests_document_tab.html")
