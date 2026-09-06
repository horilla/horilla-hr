"""
employee/cbv/requests_nav.py

Nav views for shift request tabs inside the unified Requests page.
"""

from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.cbv.shift_request import ShitRequestNav
from horilla_views.cbv_methods import login_required


@method_decorator(login_required, name="dispatch")
class RequestsShiftNav(ShitRequestNav):
    """Shift requests nav for the Requests page (without internal allocated tab)."""

    nav_title = _("Shift Requests")
    template_name = "generic/inline_nav.html"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. ShiftRequestFilter.ajax_fields carries the AJAX-loaded
    # comboboxes this needs.
    modern_filter = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("list-shift-request")


@method_decorator(login_required, name="dispatch")
class RequestsShiftInboxNav(ShitRequestNav):
    """Shift allocations nav for allocated shift requests on the Work Requests page."""

    nav_title = _("Shift Allocations")
    template_name = "generic/inline_nav.html"
    modern_filter = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("allocated-shift-view")
        self.create_attrs = f"""
             hx-get="{reverse_lazy('shift-request-reallocate')}"
             data-toggle="oh-modal-toggle"
             data-target="#genericModal"
             hx-target="#genericModalBody"
         """
