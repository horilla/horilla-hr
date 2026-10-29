"""
horilla_tour/views.py

Two surfaces:

1. Authenticated JSON API consumed by ``static/build/js/tourController.js``
   - ``tour-active``   : tours that apply to the current page + user, with steps
   - ``tour-progress`` : record start / completion / skip (replaces /driver-viewed)

2. Settings admin CRUD (permission-gated) to author tours and their ordered
   steps, following the HorillaSectionView + HorillaNavView + HorillaListView +
   HorillaFormView pattern used elsewhere in Settings.
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from horilla.decorators import login_required as auth_login_required
from horilla.decorators import permission_required
from horilla_tour.filters import TourFilter
from horilla_tour.forms import TourForm, TourStepForm
from horilla_tour.models import Tour, TourProgress, TourStep
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _audiences_for(user):
    """Audience keys the given user qualifies for."""
    audiences = {"all"}
    if user.is_superuser:
        audiences.update(["admins", "managers", "employees"])
        return audiences

    employee = getattr(user, "employee_get", None)
    if employee is not None:
        audiences.add("employees")
        try:
            from employee.models import EmployeeWorkInformation

            if EmployeeWorkInformation.objects.filter(
                reporting_manager_id=employee
            ).exists():
                audiences.add("managers")
        except Exception:
            pass
    return audiences


def _tour_matches_page(tour, page, path):
    """Does this tour apply to the requested page (URL name) / path?"""
    if not tour.page_match:
        return True
    if tour.match_type == "url_name":
        effective_page = page
        # After HTMX navigation the JS passes path="" page="" — resolve it.
        if not effective_page and path:
            try:
                from django.urls import resolve

                effective_page = resolve(path).url_name or ""
            except Exception:
                pass
        return tour.page_match == effective_page
    return bool(path) and path.startswith(tour.page_match)


def _serialize_steps(tour, page):
    """Steps for the current page, ordered, as driver.js-ready dicts."""
    steps = []
    for step in tour.steps.all():
        if step.page_match and step.page_match != page:
            continue
        steps.append(
            {
                "title": step.title,
                "description": step.description,
                "element": step.element_selector or None,
                "side": step.side,
                "align": step.align,
            }
        )
    return steps


# ---------------------------------------------------------------------------
# Public JSON API (consumed by tourController.js)
# ---------------------------------------------------------------------------


@auth_login_required
@require_GET
def tour_active(request):
    """Return published tours that apply to the current page + user."""
    page = request.GET.get("page", "")
    path = request.GET.get("path", "")
    user = request.user

    audiences = list(_audiences_for(user))
    tours = Tour.objects.filter(
        is_active=True, is_published=True, audience__in=audiences
    ).prefetch_related("steps")

    progress_map = {
        p.tour_id: p for p in TourProgress.objects.filter(user=user, tour__in=tours)
    }

    payload = []
    for tour in tours:
        if not _tour_matches_page(tour, page, path):
            continue
        steps = _serialize_steps(tour, page)
        if not steps:
            continue
        progress = progress_map.get(tour.id)
        status = progress.status if progress else None
        auto_start = tour.trigger == "auto_once" and status not in (
            "completed",
            "skipped",
        )
        payload.append(
            {
                "id": tour.id,
                "slug": tour.slug,
                "title": tour.title,
                "description": tour.description,
                "icon": tour.icon or "map-outline",
                "auto_start": auto_start,
                "show_progress": tour.show_progress,
                "allow_close": tour.allow_close,
                "status": status,
                "steps": steps,
            }
        )

    return JsonResponse({"tours": payload})


@auth_login_required
@require_POST
def tour_progress(request):
    """Upsert the current user's progress for a tour (start/complete/skip)."""
    tour_id = request.POST.get("tour_id")
    status = request.POST.get("status", "in_progress")
    last_step = request.POST.get("last_step")

    # Tour.objects is company-scoped, so a user can never write progress for
    # another tenant's tour.
    tour = Tour.objects.filter(id=tour_id, is_active=True).first()
    if not tour:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    if status not in dict(TourProgress.STATUS_CHOICES):
        status = "in_progress"

    progress, _created = TourProgress.objects.get_or_create(
        tour=tour, user=request.user
    )
    step_index = int(last_step) if (last_step and str(last_step).isdigit()) else None
    progress.mark(status, step_index)
    return JsonResponse({"ok": True, "status": progress.status})


# ---------------------------------------------------------------------------
# Settings admin — Tours CRUD
# ---------------------------------------------------------------------------


@auth_login_required
@permission_required("horilla_tour.view_tour")
def tour_settings_page(request):
    """Render the Tour Management page inside the Settings shell."""
    return render(request, "horilla_tour/tour_settings.html")


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("horilla_tour.view_tour"), name="dispatch")
class TourNav(HorillaNavView):
    """Search bar + Create button for tours."""

    nav_title = _("Product Tours")
    search_swap_target = "#listContainer"
    filter_instance = TourFilter()
    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("tour-list")
        if self.request.user.has_perm("horilla_tour.add_tour"):
            self.create_attrs = f"""
                onclick="event.stopPropagation();"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('tour-create-form')}"
            """


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("horilla_tour.view_tour"), name="dispatch")
class TourList(HorillaListView):
    """Tours list with Edit / Steps / Delete row actions."""

    model = Tour
    filter_class = TourFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("tour-list")
        steps_url = reverse("tour-steps")
        self.actions = [
            {
                "action": _("Steps"),
                "icon": "list-outline",
                "attrs": f"""
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    hx-get="{steps_url}?tour_id={{pk}}"
                    hx-target="#genericModalBody"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                """,
            }
        ]
        if self.request.user.has_perm("horilla_tour.change_tour"):
            self.actions.insert(
                0,
                {
                    "action": _("Edit"),
                    "icon": "create-outline",
                    "attrs": """
                        class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                        hx-get="{get_update_url}"
                        hx-target="#genericModalBody"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                    """,
                },
            )
        if self.request.user.has_perm("horilla_tour.delete_tour"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "icon": "trash-outline",
                    "attrs": """
                        class="oh-btn oh-btn--danger oh-btn--sq-sm"
                        hx-get="{get_delete_url}?model=horilla_tour.tour&pk={pk}"
                        data-toggle="oh-modal-toggle"
                        data-target="#deleteConfirmation"
                        hx-target="#deleteConfirmationBody"
                    """,
                }
            )

    row_attrs = """ id="tourTr{get_delete_instance}" """

    header_attrs = {
        "action": """ style="width:180px !important" """,
    }

    columns = [
        (_("Title"), "title"),
        (_("Key"), "slug"),
        (_("Audience"), "get_audience_display"),
        (_("Page"), "page_match"),
        (_("Trigger"), "get_trigger_display"),
        (_("Steps"), "step_count"),
        (_("Published"), "is_published"),
    ]

    sortby_mapping = [
        (_("Title"), "title"),
        (_("Audience"), "audience"),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("horilla_tour.add_tour"), name="dispatch")
class TourFormView(HorillaFormView):
    """Create / edit a tour (modal)."""

    model = Tour
    form_class = TourForm
    new_display_title = _("Create Tour")
    is_dynamic_create_view = False

    def form_valid(self, form: TourForm) -> HttpResponse:
        if form.is_valid():
            is_update = bool(form.instance.pk)
            form.save()
            messages.success(
                self.request,
                _("Tour updated") if is_update else _("Tour created"),
            )
            return self.HttpResponse()
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Settings admin — Steps (ordered children, managed inside a modal)
# ---------------------------------------------------------------------------


def _render_steps_panel(request, tour):
    return render(
        request,
        "horilla_tour/steps_panel.html",
        {
            "tour": tour,
            "steps": tour.steps.all(),
            "can_edit": request.user.has_perm("horilla_tour.change_tour"),
        },
    )


@auth_login_required
@permission_required("horilla_tour.view_tour")
def tour_steps(request):
    """Steps-management panel for a tour (list + add/edit/delete via HTMX)."""
    tour = get_object_or_404(Tour, pk=request.GET.get("tour_id"))
    return _render_steps_panel(request, tour)


@auth_login_required
@permission_required("horilla_tour.change_tour")
def tour_step_form(request):
    """Create or edit a single step; re-renders the panel on success."""
    tour = get_object_or_404(Tour, pk=request.GET.get("tour_id"))
    step = None
    step_id = request.GET.get("step_id")
    if step_id:
        step = get_object_or_404(TourStep, pk=step_id, tour=tour)

    if request.method == "POST":
        form = TourStepForm(request.POST, instance=step)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tour = tour
            obj.save()
            messages.success(request, _("Step updated") if step else _("Step added"))
            # Success replaces the whole panel (form clears, list refreshes).
            return _render_steps_panel(request, tour)
        # Invalid: re-render the form into its slot only (keep the panel).
        resp = render(
            request,
            "horilla_tour/step_form.html",
            {"form": form, "tour": tour, "step": step},
        )
        resp["HX-Retarget"] = "#tourStepFormSlot"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    initial = {}
    if step is None:
        last = tour.steps.order_by("-sequence").first()
        initial["sequence"] = (last.sequence + 1) if last else 1
    form = TourStepForm(instance=step, initial=initial)
    return render(
        request,
        "horilla_tour/step_form.html",
        {"form": form, "tour": tour, "step": step},
    )


@auth_login_required
@permission_required("horilla_tour.change_tour")
@require_POST
def tour_step_delete(request):
    """Delete a step and re-render the panel."""
    step = get_object_or_404(TourStep, pk=request.POST.get("step_id"))
    tour = step.tour
    step.delete()
    messages.success(request, _("Step deleted"))
    return _render_steps_panel(request, tour)
