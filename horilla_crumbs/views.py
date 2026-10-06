import copy
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def breadcrumbs_fragment(request):
    """
    The breadcrumb bar for a page that was opened by an in-place (HTMX) swap.

    Such a swap does not re-render the header, and the request it made was for
    a fragment URL, not for the address the browser now shows. ``path`` is that
    address: its own crumb is added to the stored trail, and the bar is handed
    back for the page to swap in.
    """
    # Imported here: the module appends to urlpatterns, which the root URLconf
    # (that imports this view) is still defining.
    from horilla_crumbs.context_processors import _is_sibling_page, build_breadcrumbs

    trail = request.session.get("breadcrumbs")
    trail = trail if isinstance(trail, list) and trail else []

    path = urlparse(request.GET.get("path") or "").path
    if path:
        shown = copy.copy(request)
        shown.path = shown.path_info = path
        local = build_breadcrumbs(shown)
        leaf = local[-1]
        here = path.rstrip("/")
        back_to = next(
            (
                position
                for position, crumb in enumerate(trail)
                if urlparse(crumb.get("url") or "").path.rstrip("/") == here
            ),
            None,
        )
        if len(local) <= 1 or not trail:
            trail = local
        elif back_to is not None:
            # Going back to a page already in the trail: one direction only,
            # so what came after it is dropped.
            trail = trail[: back_to + 1]
        elif _is_sibling_page(trail[-1], leaf):
            trail = trail[:-1] + [leaf]
        elif trail[-1].get("name") != leaf["name"]:
            trail = trail + [leaf]
        request.session["breadcrumbs"] = trail

    return render(
        request,
        "base/navbar_components/breadcrumbs_view.html",
        {"breadcrumbs": trail},
    )
