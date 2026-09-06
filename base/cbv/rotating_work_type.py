"""
this page is handling the cbv methods of  rotating work request page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.cbv.settings_rotatingwork import DynamicRotatingWorkTypeCreate
from base.decorators import manager_can_enter
from base.filters import RotatingWorkTypeAssignFilter
from base.forms import RotatingWorkTypeAssignExportForm, RotatingWorkTypeAssignForm
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from base.models import RotatingWorkTypeAssign
from employee.models import Employee
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("base.view_rotatingworktypeassign"), name="dispatch"
)
@method_decorator(login_required, name="dispatch")
class RotatingWorkRequestView(TemplateView):
    """
    for page view
    """

    template_name = "cbv/rotating_work_type/rotating_work_home.html"


@method_decorator(login_required, name="dispatch")
class GeneralParent(HorillaListView):
    """
    main parent class for list view
    """

    template_name = "cbv/rotating_work_type/extended_rotating_work.html"
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("rotating-list-view")
        self.view_id = "rotating-work-container"
        if (
            self.request.user.has_perm("base.change_rotatingworktypeassign")
            or self.request.user.has_perm("base.delete_rotatingworktypeassign")
            or is_reportingmanager(self.request)
        ):
            self.action_method = "get_actions"
        else:
            self.action_method = None

    filter_class = RotatingWorkTypeAssignFilter
    model = RotatingWorkTypeAssign
    # filter_keys_to_remove = ["deleted"]

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Rotating Work Type"), "rotating_work_type_id"),
        (_("Based On"), "get_based_on_display"),
        (_("Rotate"), "rotate_data"),
        (_("Start Date"), "start_date"),
        (_("Current Work Type"), "current_work_type"),
        (_("Next Switch"), "next_change_date"),
        (_("Next Work Type"), "next_work_type"),
    ]

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Rotating Work Type"), "rotating_work_type_id__name"),
        (_("Based On"), "get_based_on_display"),
        (_("Rotate"), "rotate_data"),
        (_("Start Date"), "start_date"),
        (_("Current Work Type"), "current_work_type__work_type"),
        (_("Next Switch"), "next_change_date"),
        (_("Next Work Type"), "next_work_type__work_type"),
    ]
    row_attrs = """
                hx-get='{work_rotate_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("base.view_rotatingworktypeassign"), name="dispatch"
)
class RotatingWorkListView(GeneralParent):
    """
    list view of the rotating work assign page
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = filtersubordinates(
            self.request, queryset, "base.view_rotatingworktypeassign"
        )

        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)

        return queryset

    bulk_update_fields = [
        "rotating_work_type_id",
        "start_date",
        # "based_on"
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("base.view_rotatingworktypeassign"), name="dispatch"
)
class RotatingWorkNavView(HorillaNavView):
    """
    Nav view of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("rotating-list-view")
        self.actions = []
        if self.request.user.has_perm(
            "base.change_rotatingworktypeassign"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Archive"),
                    "attrs": """
                id="archiveWorkRotateNav"
                style="cursor: pointer;"
                """,
                }
            )
            self.actions.append(
                {
                    "action": _("Un-Archive"),
                    "attrs": """
                        onclick="
                        UnarchiveWorkRotateNav();
                        "
                        style="cursor: pointer;"
                        """,
                },
            )
        if self.request.user.has_perm(
            "base.delete_rotatingworktypeassign"
        ) or is_reportingmanager(self.request):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                        onclick="
                        deleteWorkRotateNav();
                        "
                        data-action ="delete"
                        style="cursor: pointer; color:red !important"
                        """,
                }
            )

        if has_export_access(self.request, RotatingWorkTypeAssign):
            self.actions.insert(
                0,
                {
                    "action": _("Export"),
                    "attrs": f"""
                    data-toggle = "oh-modal-toggle"
                    data-target = "#genericModal"
                    hx-target="#genericModalBody"
                    hx-get ="{reverse('rotating-action-export')}"
                    hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                    style="cursor: pointer;"
                """,
                },
            )
        if self.request.user.has_perm(
            "base.add_rotatingworktypeassign"
        ) or is_reportingmanager(self.request):
            self.create_attrs = f"""
                hx-get="{reverse_lazy("rotating-work-type-assign-add")}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """

    nav_title = _("Rotating Work Type Assign")
    template_name = "generic/inline_nav.html"
    filter_body_template = "cbv/rotating_work_type/filter_work_rotate.html"
    filter_instance = RotatingWorkTypeAssignFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. RotatingWorkTypeAssignFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("rotating_work_type_id", _("Rotating Work Type")),
        ("current_work_type", _("Current Work Type")),
        ("based_on", _("Based On")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Role")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("base.view_rotatingworktypeassign"), name="dispatch"
)
class RotatingWorkDetailView(HorillaDetailedView):
    """
    Detail view of page
    """

    model = RotatingWorkTypeAssign

    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "work_rotate_detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    body = [
        (_("Title"), "rotating_work_type_id"),
        (_("Based On"), "get_based_on_display"),
        (_("Rotate"), "rotate_data"),
        (_("Start Date"), "start_date"),
        (_("Current Work Type"), "current_work_type"),
        (_("Next Switch"), "next_change_date"),
        (_("Next Work Type"), "next_work_type"),
        (_("Status"), "detail_is_active"),
    ]
    action_method = "get_detail_view_actions"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = context.get("object")
        if instance is None:
            # No matching row (e.g. a stale/invalid pk) -- the parent's own
            # get_context_data already skips setting instance_ids for this
            # case, and its get() renders empty_template / redirects with
            # "No record found" once this returns, so there's nothing to
            # attach ordered_ids to here.
            return context
        instance.ordered_ids = context.get("instance_ids", [])
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    manager_can_enter("base.view_rotatingworktypeassign"), name="dispatch"
)
class RotatingWorkExport(TemplateView):
    """
    To add export action in the navbar
    """

    template_name = "cbv/rotating_work_type/rotating_action_export.html"

    def get_context_data(self, **kwargs: Any):
        """
        get data for export
        """
        candidates = RotatingWorkTypeAssign.objects.all()
        export_columns = RotatingWorkTypeAssignExportForm
        export_filter = RotatingWorkTypeAssignFilter(queryset=candidates)
        context = super().get_context_data(**kwargs)
        context["export_columns"] = export_columns
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.add_rotatingworktypeassign"), name="dispatch")
class RotatingWorkTypeFormView(HorillaFormView):
    """
    form view
    """

    model = RotatingWorkTypeAssign
    form_class = RotatingWorkTypeAssignForm

    new_display_title = _("Rotating Work Type Assign")
    dynamic_create_fields = [("rotating_work_type_id", DynamicRotatingWorkTypeCreate)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET.get("emp_id"):
            employee = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].initial = employee
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=employee
            )
        if self.form.instance.pk:
            form = self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request, self.form, "base.add_rotatingworktypeassign"
        )
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Rotating Work Type Assign")

        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Rotating Work Type Assign")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: RotatingWorkTypeAssignForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Rotating Work Assign Updated Successfully")
            else:
                message = _("Rotating Work Assigned")
                employee_ids = self.request.POST.getlist("employee_id")
                employees = Employee.objects.filter(id__in=employee_ids).select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in employees]
                notify.send(
                    self.request.user.employee_get,
                    recipient=users,
                    verb="You are added to rotating work type",
                    verb_ar="تمت إضافتك إلى نوع العمل المتناوب",
                    verb_de="Sie werden zum rotierenden Arbeitstyp hinzugefügt",
                    verb_es="Se le agrega al tipo de trabajo rotativo",
                    verb_fr="Vous êtes ajouté au type de travail rotatif",
                    icon="infinite",
                    redirect=reverse("employee-profile"),
                )
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("base.add_rotatingworktypeassign"), name="dispatch")
class RotatingWorkTypeDuplicateForm(HorillaFormView):
    """
    duplicate from view
    """

    model = RotatingWorkTypeAssign
    form_class = RotatingWorkTypeAssignForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = RotatingWorkTypeAssign.objects.get(id=self.kwargs["pk"])
        form = self.form_class(instance=original_object)

        context["form"] = form
        self.form_class.verbose_name = _("Rotating Work Type Assign")
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        # form = self.form_class(self.request.POST)
        if not form.is_valid():
            if self.form.instance.pk:
                self.form_class.verbose_name = _("Rotating Work Type Assign")
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: RotatingWorkTypeAssignForm) -> HttpResponse:
        form = self.form_class(self.request.POST)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Rotating Work Type Assign")
        if form.is_valid():
            message = _("Rotating Work Assign Created")
            messages.success(self.request, message)
            form.save()
            return HorillaRedirect(self.request)

        return self.form_invalid(form)
