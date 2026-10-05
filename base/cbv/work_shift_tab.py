"""
This page is handling the cbv methods of work type and shift tab in employee profile page.
"""

from typing import Any

from django.db.models import Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from base.cbv.rotating_shift_assign import (
    RotatingShiftDetailview,
    RotatingShiftListParent,
)
from base.cbv.rotating_work_type import GeneralParent, RotatingWorkDetailView
from base.cbv.shift_request import AllocatedShift, ShiftRequestList
from base.cbv.work_type_request import WorkRequestListView
from base.methods import filtersubordinates, is_reportingmanager
from base.models import (
    RotatingShiftAssign,
    RotatingWorkTypeAssign,
    ShiftRequest,
    WorkTypeRequest,
)
from employee.models import Employee
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import HorillaNavView, HorillaTabView


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class ProfileTabShellView(TemplateView):
    """
    Minimal placeholder shown when a profile-nested sub-tab is first
    opened: loads its companion Nav (which carries the Create button) via
    htmx, which then auto-loads the actual list into the placeholder
    below it. Mirrors the "Employee Configuration" page's own tab
    mechanism (e.g. employee_settings_shift_tab.html), which is why the
    shell's own container id must differ from the list view's internal
    view_id - the shell id is a stable swap target that the list's own
    render (a *different* id) gets swapped into, without ever being
    included in what comes back on a reload.
    """

    template_name = "cbv/work_shift_tab/profile_tab_shell.html"
    shell_target_id: str = ""
    nav_url_name: str = ""

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        context["emp_id"] = self.kwargs.get("pk")
        context["shell_target_id"] = self.shell_target_id
        context["nav_url_name"] = self.nav_url_name
        return context


class WorkAndShiftTabView(HorillaTabView):
    """
    generic tab view for work type and shift
    """

    template_name = "cbv/work_shift_tab/extended_work-shift.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "work-shift"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        context["emp_id"] = pk
        employee = Employee.objects.get(id=pk)
        context["employee"] = employee
        # Each sub-tab's own badge count is only otherwise filled in once
        # that tab's content has actually loaded (client-side, from its
        # list view's data-total-count) - horilla_tabs.html only ever
        # auto-loads the ACTIVE sub-tab on first render, so every other
        # sub-tab's badge was stuck at its server-rendered default (0)
        # until the user clicked it, even when it had real records.
        # Computing the count here up front, scoped the same way each
        # sub-tab's own queryset is, keeps every badge accurate from the
        # first paint.
        context["tabs"] = [
            {
                "title": _("Work Type Request"),
                "url": f"{reverse('employee-worktype-tab-shell',kwargs={'pk': pk})}",
                "badge": WorkTypeRequest.objects.filter(employee_id=pk).count(),
            },
            {
                "title": _("Rotating Work Type"),
                "url": f"{reverse('employee-rotating-work-tab-shell',kwargs={'pk': pk})}",
                "badge": RotatingWorkTypeAssign.objects.filter(employee_id=pk).count(),
            },
            {
                "title": _("Shift Request"),
                "url": f"{reverse('shift-request-individual-tab-shell',kwargs={'pk': pk})}",
                # Matches ShiftRequestIndividualTabView.get_queryset(), which
                # replaces the base ShiftRequestList queryset entirely with a
                # plain employee_id filter - no reallocate_to exclusion.
                "badge": ShiftRequest.objects.filter(employee_id=pk).count(),
            },
            {
                "title": _("Shift Allocation"),
                "url": f"{reverse('shift-allocation-individual-tab-shell',kwargs={'pk': pk})}",
                "badge": ShiftRequest.objects.filter(
                    Q(employee_id=pk) | Q(reallocate_to=pk),
                    reallocate_to__isnull=False,
                ).count(),
            },
            {
                "title": _("Rotating Shift"),
                "url": f"{reverse('rotating-shift-individual-tab-shell',kwargs={'pk': pk})}",
                "badge": RotatingShiftAssign.objects.filter(employee_id=pk).count(),
            },
        ]
        return context


class WorkTypeIndividualTabList(WorkRequestListView):
    """
    List view for work type tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-worktype-tab-list", kwargs={"pk": pk})
        self.view_id = "work_target"

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset

    columns = [col for col in WorkRequestListView.columns if col[1] != "comment_note"]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class WorkTypeIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Work type request profile tab.
    """

    shell_target_id = "work-type-shell"
    nav_url_name = "employee-worktype-tab-nav"


@method_decorator(login_required, name="dispatch")
class WorkTypeIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Work type request profile tab.
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-worktype-tab-list", kwargs={"pk": pk})
        self.search_swap_target = "#work-type-shell"
        self.create_attrs = f"""
            hx-get="{reverse('work-type-request')}?emp_id={pk}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """

    nav_title = _("Work Type Request")


class ShiftRequestIndividualTabView(ShiftRequestList):
    """
    List view for shift request tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "shift-reques-individual-div"
        self.selected_instances_key_id = "shiftselectedInstancesIndividual"
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "shift-request-individual-tab-view", kwargs={"pk": pk}
        )

    columns = [column for column in ShiftRequestList.columns if column[1] != "comment"]

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset


class ShiftRequestIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Shift request profile tab.
    """

    shell_target_id = "shift-request-shell"
    nav_url_name = "shift-request-individual-tab-nav"


@method_decorator(login_required, name="dispatch")
class ShiftRequestIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Shift request profile tab.
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "shift-request-individual-tab-view", kwargs={"pk": pk}
        )
        self.search_swap_target = "#shift-request-shell"
        self.create_attrs = f"""
            hx-get="{reverse('shift-request')}?emp_id={pk}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """

    nav_title = _("Shift Request")


@method_decorator(login_required, name="dispatch")
class ShiftAllocationIndividualTabView(AllocatedShift):
    """
    List view for the Shift Allocation profile tab - scoped to this
    specific employee (as requester or reallocation target), unlike the
    standalone Allocated Shift Requests list this view is based on.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "shift-allocation-individual-div"
        self.selected_instances_key_id = "allocatedselectedInstancesIndividual"
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "shift-allocation-individual-tab-view", kwargs={"pk": pk}
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = queryset.filter(Q(employee_id=pk) | Q(reallocate_to=pk))
        return queryset


class ShiftAllocationIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Shift Allocation profile tab.
    """

    shell_target_id = "shift-allocation-shell"
    nav_url_name = "shift-allocation-individual-tab-nav"


@method_decorator(login_required, name="dispatch")
class ShiftAllocationIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Shift Allocation profile tab.
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "shift-allocation-individual-tab-view", kwargs={"pk": pk}
        )
        self.search_swap_target = "#shift-allocation-shell"
        self.create_attrs = f"""
            hx-get="{reverse('shift-request-reallocate')}?emp_id={pk}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """

    nav_title = _("Shift Allocation")


class RotatingShiftAssignIndividualView(RotatingShiftListParent):
    """
    List view for Rotating shift request tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "rotating-shift-individual-tab-view", kwargs={"pk": pk}
        )
        self.view_id = "rotating-div"

    columns = RotatingShiftListParent.columns + [
        (_("Status"), "check_active"),
    ]

    row_attrs = """
                hx-get='{rotating_shift_individual_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset


class RotatingShiftIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Rotating Shift profile tab.
    """

    shell_target_id = "rotating-shift-shell"
    nav_url_name = "rotating-shift-individual-tab-nav"


@method_decorator(login_required, name="dispatch")
class RotatingShiftIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Rotating Shift profile tab.
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "rotating-shift-individual-tab-view", kwargs={"pk": pk}
        )
        self.search_swap_target = "#rotating-shift-shell"
        self.create_attrs = f"""
            hx-get="{reverse('rotating-shift-assign-add')}?emp_id={pk}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """

    nav_title = _("Rotating Shift")


class RotatingWorkIndividualTab(GeneralParent):
    """
    List view for rotating work type tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-rotating-work-tab-list", kwargs={"pk": pk})
        self.view_id = "rotating-work-div"

    columns = GeneralParent.columns + [
        (_("Status"), "detail_is_active"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset

    row_attrs = """
                hx-get='{individual_tab_work_rotate_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class RotatingWorkIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Rotating work type profile tab.
    """

    shell_target_id = "rotating-work-shell"
    nav_url_name = "employee-rotating-work-tab-nav"


@method_decorator(login_required, name="dispatch")
class RotatingWorkIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Rotating work type profile tab.
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-rotating-work-tab-list", kwargs={"pk": pk})
        self.search_swap_target = "#rotating-work-shell"
        self.create_attrs = f"""
            hx-get="{reverse('rotating-work-type-assign-add')}?emp_id={pk}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """

    nav_title = _("Rotating Work Type")


# @method_decorator(login_required, name="dispatch")
# class DetailViewChild(RotatingWorkDetailView):
#     """
#     parent for detail view
#     """

#     @method_decorator(login_required, name="dispatch")
#     def dispatch(self, *args, **kwargs):
#         return super(RotatingWorkDetailView, self).dispatch(*args, **kwargs)

#     def get_queryset(self):
#         queryset = super().get_queryset()
#         pk = self.kwargs.get("pk")
#         queryset = queryset.filter(pk=pk)
#         return queryset


class RotatingShiftAssignIndividualDetailView(RotatingShiftDetailview):
    """
    Individual rotating shift assign detail view
    """

    @method_decorator(login_required, name="dispatch")
    def dispatch(self, *args, **kwargs):
        return super(RotatingShiftDetailview, self).dispatch(*args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        obj = queryset.get(pk=pk)
        employee_id = obj.employee_id
        if is_reportingmanager(self.request):
            queryset = filtersubordinates(
                self.request, queryset, "base.view_rotatingshiftassign"
            ) | queryset.filter(employee_id=self.request.user.employee_get)
        elif self.request.user.has_perm("base.view_rotatingshiftassign"):
            queryset = queryset.filter(employee_id=employee_id)
        else:
            queryset = queryset.filter(employee_id=self.request.user.employee_get)
        return queryset


@method_decorator(login_required, name="dispatch")
class DetailViewChild(RotatingWorkDetailView):
    """
    parent for detail view
    """

    @method_decorator(login_required, name="dispatch")
    def dispatch(self, *args, **kwargs):
        return super(RotatingWorkDetailView, self).dispatch(*args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        obj = queryset.get(pk=pk)
        emp_id = obj.employee_id
        # queryset = queryset.filter(employee_id=emp_id)
        if is_reportingmanager(self.request):
            queryset = filtersubordinates(
                self.request, queryset, "base.view_rotatingworktypeassign"
            ) | queryset.filter(employee_id=self.request.user.employee_get)
        elif self.request.user.has_perm("base.view_rotatingworktypeassign"):
            queryset = queryset.filter(employee_id=emp_id)
        else:
            queryset = queryset.filter(employee_id=self.request.user.employee_get)

        return queryset
