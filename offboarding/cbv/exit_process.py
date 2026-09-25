"""
This page handles the cbv methods for existing process
"""

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse

from django import forms
from django.apps import apps
from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import escapejs
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django.views import View

from base.context_processors import intial_notice_period
from base.methods import eval_validate
from horilla.http.response import HorillaRedirect
from horilla.methods import get_horilla_model_class
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.kanban import HorillaKanbanView
from horilla_views.generic.cbv.pipeline import Pipeline
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaSectionView,
    HorillaTabView,
    TemplateView,
)
from notifications.signals import notify
from offboarding.cbv_decorators import (
    any_manager_can_enter,
    offboarding_manager_can_enter,
    offboarding_or_stage_manager_can_enter,
)
from offboarding.filters import (
    PipelineEmployeeFilter,
    PipelineFilter,
    PipelineStageFilter,
)
from offboarding.forms import (
    OffboardingEmployeeForm,
    OffboardingForm,
    OffboardingStageForm,
    TaskForm,
)
from offboarding.models import (
    EmployeeTask,
    Offboarding,
    OffboardingEmployee,
    OffboardingStage,
    OffboardingTask,
)
from offboarding.templatetags.offboarding_filter import (
    any_manager,
    is_offboarding_manager,
)


def offboarding_pipeline_modal_success_response(request) -> HttpResponse:
    """
    Close modals and refresh the Exit Process pipeline area without a full-page reload.

    Uses the pipeline nav filter form's apply button when present (preserves filters
    and active list/card view); otherwise falls back to HTMX-loading the tabs view.
    """
    qs = urlparse(request.headers.get("HX-Current-URL", "") or "").query
    tab_url = reverse("get-offboarding-tab")
    if qs:
        tab_url = f"{tab_url}?{qs}"

    # json.dumps escapes quotes but NOT "</script>", so a crafted value
    # could close the script block that this literal is embedded in.
    # escapejs encodes angle brackets as \u003C/\u003E.
    tab_url_lit = f'"{escapejs(tab_url)}"'

    snippet = rf"""
<script>
(function () {{
  document.querySelectorAll(".oh-modal--show").forEach(function (el) {{
    el.classList.remove("oh-modal--show");
  }});
  var applyBtn =
    document.querySelector("#filterForm button#applyFilter") ||
    document.querySelector("#filterForm #applyFilter") ||
    document.getElementById("applyFilter");
  if (applyBtn) {{
    applyBtn.click();
  }} else if (typeof htmx !== "undefined") {{
    htmx.ajax("GET", {tab_url_lit}, {{ target: "#pipelineContainer", swap: "innerHTML" }});
  }}
  var msgBtn = document.getElementById("reloadMessagesButton");
  if (msgBtn) {{
    msgBtn.click();
  }}
}})();
</script>
"""
    return HttpResponse(snippet)


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    offboarding_manager_can_enter("offboarding.add_offboardingstage"), name="dispatch"
)
class OffboardingStageFormView(HorillaFormView):
    """
    form view for create button
    """

    form_class = OffboardingStageForm
    model = OffboardingStage
    new_display_title = _("Create Offboarding Stage")

    def dispatch(self, request, *args, **kwargs):
        # Creating a new stage requires knowing which offboarding process it
        # belongs to; with no pk (editing an existing stage) and no
        # offboarding_id, there's nothing sensible to show.
        if (
            request.method == "GET"
            and not kwargs.get("pk")
            and not request.GET.get("offboarding_id")
        ):
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        offboarding_id = self.request.GET.get("offboarding_id")
        if offboarding_id:
            self.form.fields["offboarding_id"].initial = offboarding_id
        self.form.fields["offboarding_id"].widget = forms.HiddenInput()
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Offboarding Stage")
        return context

    def form_valid(self, form: OffboardingStageForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Offboarding Stage Updated Successfully")
            else:
                message = _("Offboarding Stage Created Successfully")
            form.save()

            messages.success(self.request, message)
            return offboarding_pipeline_modal_success_response(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter("offboarding.add_offboardingemployee"), name="dispatch"
)
class OffboardingStageAddEmployeeForm(HorillaFormView):
    """
    form view for create button
    """

    form_class = OffboardingEmployeeForm
    model = OffboardingEmployee
    new_display_title = _("Add Employee")

    def dispatch(self, request, *args, **kwargs):
        # Adding a new employee requires knowing which stage to add them to;
        # with no pk (editing an existing entry) and no stage_id, there's
        # nothing sensible to show.
        if (
            request.method == "GET"
            and not kwargs.get("pk")
            and not request.GET.get("stage_id")
        ):
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        default_notice_period = (
            intial_notice_period(self.request)["get_initial_notice_period"]
            if intial_notice_period(self.request)["get_initial_notice_period"]
            else 0
        )
        end_date = datetime.today() + timedelta(days=default_notice_period)
        stage_id = self.request.GET["stage_id"]
        self.form.fields["stage_id"].initial = stage_id
        self.form.fields["notice_period_ends"].initial = end_date
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Employee")
        return context

    def form_valid(self, form: OffboardingEmployeeForm) -> HttpResponse:
        stage_id = self.request.GET["stage_id"]
        stage = OffboardingStage.objects.get(id=stage_id)
        if form.is_valid():
            if form.instance.pk:
                message = _("Updated Employee")
            else:
                message = _("Added Employee")
                instance = form.save()
                notify.send(
                    self.request.user.employee_get,
                    recipient=instance.employee_id.employee_user_id,
                    verb=gettext_noop(
                        "You have been added to the %(stage)s of %(offboarding_id)s"
                    ),
                    verb_params={
                        "stage": str(stage),
                        "offboarding_id": str(stage.offboarding_id),
                    },
                    redirect=reverse("offboarding-pipeline"),
                    icon="information",
                )
            form.save()
            messages.success(self.request, message)
            return offboarding_pipeline_modal_success_response(self.request)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("offboarding.add_offboarding"), name="dispatch")
class OffboardingCreateFormView(HorillaFormView):
    """
    form view for create and edit offboarding
    """

    form_class = OffboardingForm
    model = Offboarding
    new_display_title = _("Create Offboarding")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Offboarding")

        return context

    def form_valid(self, form: OffboardingForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Offboarding Updated")
            else:
                message = _("Offboarding saved")
            form.save()

            messages.success(self.request, message)
            return offboarding_pipeline_modal_success_response(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    offboarding_or_stage_manager_can_enter("offboarding.add_offboardingtask"),
    name="dispatch",
)
class OffboardingTaskFormView(HorillaFormView):
    """
    form view for create and edit offboarding tasks
    """

    model = OffboardingTask
    form_class = TaskForm
    new_display_title = _("Create Task")

    def dispatch(self, request, *args, **kwargs):
        # This endpoint returns only the modal form fragment; a genuine
        # top-level browser navigation/reload should land on the real
        # Offboarding Pipeline page instead of showing the raw fragment.
        if request.headers.get("Sec-Fetch-Mode") == "navigate":
            return redirect(reverse("offboarding-pipeline"))
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict:
        initial = super().get_initial()
        stage_id = self.request.GET.get("stage_id")
        employees = OffboardingEmployee.objects.filter(stage_id=stage_id)
        if stage_id:
            initial["stage_id"] = stage_id
            initial["tasks_to"] = employees
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stage_id = self.request.GET.get("stage_id")
        employees = OffboardingEmployee.objects.filter(stage_id=stage_id)
        if self.form.instance.pk:
            self.form.fields["stage_id"].initial = stage_id
            self.form.fields["tasks_to"].initial = employees
            self.form.fields["tasks_to"].queryset = employees

            self.form_class.verbose_name = _("Update Task")

        return context

    def form_valid(self, form: TaskForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Task Updated")
            else:
                message = _("Task Added")
            form.save()

            messages.success(self.request, message)
            return offboarding_pipeline_modal_success_response(self.request)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class ExitProcessDetailView(HorillaDetailedView):
    """
    detail view
    """

    model = OffboardingEmployee
    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    empty_template = "cbv/exit_process/detailed_page_empty.html"
    action_method = "detail_action_col"
    body = [
        (_("Email"), "employee_id__employee_work_info__email"),
        (_("Job Position"), "employee_id__employee_work_info__job_position_id"),
        (_("Contact"), "employee_id__phone"),
        (_("Notice Period start Date"), "notice_period_starts"),
        (_("Notice Period end Date"), "notice_period_ends"),
        (_("Stage"), "get_stage_col"),
        (_("Tasks"), "detail_view_task_custom", "custom_template"),
    ]
    cols = {
        "detail_view_task_custom": 12,
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter(
        "offboarding.view_offboarding", offboarding_employee_can_enter=True
    ),
    name="dispatch",
)
class OffboardingPipelineView(HorillaSectionView):
    """
    Offboarding Pipeline View
    """

    template_name = "cbv/exit_process/pipeline_view.html"
    view_url = reverse_lazy("get-offboarding-tab")
    view_container_id = "pipelineContainer"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter(
        "offboarding.view_offboarding", offboarding_employee_can_enter=True
    ),
    name="dispatch",
)
class OffboardingPipelineNav(HorillaNavView):
    """
    Offboarding Pipeline Navigation View

    No longer rendered by the Pipeline page itself, which now follows the
    Recruitment pipeline and shows its tab view alone - each offboarding
    tab's own OffboardingPipelineTabNav carries the title, Create button,
    view-type toggles, Search+Filter and Actions. Kept only because
    `offboarding-pipeline-nav` is still routed.
    """

    nav_title = _("Exit Process")
    search_swap_target = "#pipelineContainer"
    search_url = reverse_lazy("get-offboarding-tab")
    filter_body_template = "cbv/exit_process/pipeline_filter.html"
    apply_first_filter = False
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. PipelineEmployeeFilter/PipelineFilter/
    # PipelineStageFilter each carry their own ajax_fields for the FK
    # pickers this combined panel renders.
    modern_filter = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.request.user.has_perm("offboarding.create_offboarding"):
            self.create_attrs = f"""
                class="oh-btn oh-btn--secondary"
                hx-get="{reverse_lazy("create-offboarding")}"
                hx-target="#objectDetailsModalTarget"
                data-toggle="oh-modal-toggle"
                data-target="#objectDetailsModal"
            """

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse_lazy("get-offboarding-tab")}',
                "attrs": f"""
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse_lazy("get-offboarding-tab")}?view=card',
                "attrs": f"""
                    title ='Card'
                """,
            },
        ]

    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)
        # Bound to self.request.GET: this form's own hx-trigger="load"
        # auto-submits it on every load (see horilla_nav.html), serializing
        # its current field values as the query string. Left unbound, every
        # field (including "Stage > Status") always renders blank, so that
        # auto-submit silently wipes out any filter (e.g. ?type=archived)
        # that arrived via a deep link before the page ever settles.
        employee_filter = PipelineEmployeeFilter(self.request.GET)
        pipeline_filter = PipelineFilter(self.request.GET)
        stage_filter = PipelineStageFilter(self.request.GET)
        context["employee_filter"] = employee_filter
        context["pipeline_filter"] = pipeline_filter
        context["stage_filter"] = stage_filter

        # This Nav has no single filter_instance of its own (all three
        # filtersets above are combined into one panel), so the generic
        # custom_filter_fields/custom_filter_rows context
        # (HorillaNavView.get_context_data) is never populated -- expose
        # each filterset's own registry/restore-rows under its own key
        # instead, matching the namespaced builder each accordion uses
        # in the template.
        context["employee_custom_filter_fields"] = getattr(
            employee_filter, "custom_filter_fields", []
        )
        context["employee_custom_filter_rows"] = getattr(
            employee_filter, "custom_filter_rows", []
        )
        context["pipeline_custom_filter_fields"] = getattr(
            pipeline_filter, "custom_filter_fields", []
        )
        context["pipeline_custom_filter_rows"] = getattr(
            pipeline_filter, "custom_filter_rows", []
        )
        context["stage_custom_filter_fields"] = getattr(
            stage_filter, "custom_filter_fields", []
        )
        context["stage_custom_filter_rows"] = getattr(
            stage_filter, "custom_filter_rows", []
        )

        return context


def offboarding_pipeline_actions(request, offboarding):
    """
    Offboarding-level actions (Add Stage/Manage Stage Order/Edit/Delete)
    for the given offboarding - shared between PipeLineTabView (which used
    to put these in the tab bar's kebab) and OffboardingPipelineContentShell
    (which renders them inline in the pipeline content's own header instead).
    """
    actions = []
    if request.user.has_perm(
        "offboarding.add_offboardingstage"
    ) or is_offboarding_manager(request.user.employee_get):
        actions.append(
            {
                "action": _("Add Stage"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("create-offboarding-stage")}?offboarding_id={offboarding.pk}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )
        actions.append(
            {
                "action": _("Manage Stage Order"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("update-stage-sequence",kwargs={"pk": offboarding.pk})}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )
    if request.user.has_perm(
        "offboarding.change_offboarding"
    ) or is_offboarding_manager(request.user.employee_get):
        actions.append(
            {
                "action": _("Edit"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("update-offboarding", kwargs={"pk": offboarding.pk})}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )
    if request.user.has_perm("offboarding.delete_offboarding"):
        actions.append(
            {
                "action": _("Delete"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#deleteConfirmation"
                    hx-get="{reverse('generic-delete')}?{urlencode({
                        'model': 'offboarding.Offboarding',
                        'pk': str(offboarding.pk),
                        'reload_target': '#applyFilter',
                    })}"
                    hx-target="#deleteConfirmationBody"
                    style="cursor: pointer;"
                """,
            }
        )
    return actions


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter(
        "offboarding.view_offboarding", offboarding_employee_can_enter=True
    ),
    name="dispatch",
)
class PipeLineTabView(HorillaTabView):
    """
    Pipeline Tab View
    """

    filter_class = PipelineFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        offboardings = self.filter_class(self.request.GET).qs.filter(is_active=True)
        self.tabs = []
        for offboarding in offboardings:
            tab = {}
            tab["title"] = offboarding.title
            url = reverse("offboarding-pipeline-shell", kwargs={"pk": offboarding.pk})

            if self.request.GET:
                url = f"{url}?{self.request.GET.urlencode()}"

            tab["url"] = url

            tab["badge_label"] = _("Stages")
            tab["badge"] = offboarding.offboardingstage_set.filter(
                is_active=True
            ).count()
            self.tabs.append(tab)

        context["tabs"] = self.tabs
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter(
        "offboarding.view_offboarding", offboarding_employee_can_enter=True
    ),
    name="dispatch",
)
class OffboardingPipelineContentShell(TemplateView):
    """
    Shell rendered for a single offboarding's pipeline tab - shows the
    offboarding-level actions (previously the tab bar's own kebab) above
    an htmx-loaded embed of the existing list/kanban content.
    """

    template_name = "cbv/exit_process/offboarding_pipeline_shell.html"

    def dispatch(self, request, *args, **kwargs):
        if not Offboarding.objects.filter(pk=kwargs.get("pk")).exists():
            messages.error(request, _("No Offboarding found matching the query."))
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        offboarding = Offboarding.objects.filter(pk=self.kwargs.get("pk")).first()
        view_type = self.request.GET.get("view", "list")
        content_url = reverse(
            "get-offboarding-stage", kwargs={"offboarding_id": offboarding.pk}
        )
        if view_type != "list":
            content_url = reverse(
                "get-offboarding-kanban-stage", kwargs={"pk": offboarding.pk}
            )
        extra_params = self.request.GET.copy()
        extra_params.pop("view", None)
        if extra_params:
            content_url = f"{content_url}?{extra_params.urlencode()}"
        context["content_url"] = content_url
        context["offboarding"] = offboarding
        # Always pass the resolved view_type through, not just when ?view=
        # was explicitly on this shell's own request - HorillaNavView only
        # marks a view-type button active (oh-view-btn--active) when its
        # own request carries ?view=, and inline_nav.html's onload script
        # fires an extra full-board resubmit whenever no button is active.
        # Checking self.request.GET.get("view") here (truthy only on an
        # explicit toggle click) left every first visit without an active
        # button, so the whole board re-fetched itself a second time right
        # after its first load - doubling load time for large stages.
        nav_url = reverse("offboarding-pipeline-tab-nav", kwargs={"pk": offboarding.pk})
        nav_params = self.request.GET.copy()
        nav_params["view"] = view_type
        context["nav_url"] = f"{nav_url}?{nav_params.urlencode()}"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    any_manager_can_enter(
        "offboarding.view_offboarding", offboarding_employee_can_enter=True
    ),
    name="dispatch",
)
class OffboardingPipelineTabNav(HorillaNavView):
    """
    Per-offboarding-tab Search+Filter for the Exit Process pipeline.

    The page-level OffboardingPipelineNav's Search+Filter searched/filtered
    which OFFBOARDINGS show up as tabs - it said nothing about any one
    offboarding's own employees, and was shared/common across every tab.
    This Nav is the opposite: one instance per offboarding tab, searching/
    filtering that offboarding's own employees (PipelineEmployeeFilter),
    so switching stage/list vs kanban and searching one offboarding's
    pipeline doesn't touch any other tab. Mirrors
    recruitment.cbv.pipeline.RecruitmentCandidateNav.
    """

    filter_form_context_name = "form"
    filter_body_template = "cbv/exit_process/pipeline_tab_filter.html"
    filter_instance = PipelineEmployeeFilter()
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as the page-level
    # OffboardingPipelineNav/pipeline_filter.html. PipelineEmployeeFilter
    # already carries ajax_fields for the FK pickers this panel renders.
    modern_filter = True
    # The shell already fetches this tab's board into
    # #pipelineTabContent<pk> on its own load, so this Nav must not fire a
    # second `load` fetch at the same target (see
    # RecruitmentCandidateNav for the failure mode this avoids).
    apply_first_filter = True
    template_name = "generic/inline_nav.html"
    nav_title = _("Pipeline")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        offboarding_id = self.request.resolver_match.kwargs.get("pk")
        view_type = self.request.GET.get("view")
        if view_type == "list":
            self.search_url = reverse(
                "get-offboarding-stage", kwargs={"offboarding_id": offboarding_id}
            )
        else:
            self.search_url = reverse(
                "get-offboarding-kanban-stage", kwargs={"pk": offboarding_id}
            )
        self.search_swap_target = f"#pipelineTabContent{offboarding_id}"

        if self.request.user.has_perm(
            "offboarding.add_offboardingemployee"
        ) or is_offboarding_manager(self.request.user.employee_get):
            first_stage = (
                OffboardingStage.objects.filter(
                    offboarding_id=offboarding_id, is_active=True
                )
                .order_by("sequence")
                .first()
            )
            if first_stage:
                self.create_attrs = f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{first_stage.get_add_employee_url()}"
                    hx-target="#genericModalBody"
                """

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse(
                    "get-offboarding-stage",
                    kwargs={"offboarding_id": offboarding_id},
                ),
                "attrs": """
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse(
                    "get-offboarding-kanban-stage", kwargs={"pk": offboarding_id}
                ),
                "attrs": """
                    title ='Card'
                """,
            },
        ]

        offboarding = Offboarding.objects.filter(pk=offboarding_id).first()
        if offboarding:
            self.actions = offboarding_pipeline_actions(self.request, offboarding)


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class OffboardingPipelineStage(Pipeline):
    """
    Offboarding Pipeline Stage
    """

    model = OffboardingEmployee
    filter_class = PipelineEmployeeFilter
    grouper = "stage_id"
    selected_instances_key_name = "OffboardingEmployeeRecords"
    template_name = "cbv/exit_process/stages.html"
    allowed_fields = [
        {
            "field": "stage_id",
            "model": OffboardingStage,
            "filter": PipelineStageFilter,
            "url": reverse_lazy("get-offboarding-employees-cbv"),
            "parameters": [
                "offboarding_stage_id={pk}",
                "offboarding_id={offboarding_id__pk}",
            ],
            "actions": [
                {
                    "action": _("Add Employee"),
                    "accessibility": "offboarding.cbv.accessibility.add_employee_accessibility",
                    "attrs": """
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-get="{get_add_employee_url}"
                        hx-target="#genericModalBody"
                        class="oh-dropdown__link"
                    """,
                },
                {
                    "action": _("Edit"),
                    "accessibility": "offboarding.cbv.accessibility.edit_stage_accessibility",
                    "attrs": """
                        hx-target="#genericModalBody"
                        hx-get="{get_update_url}"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                    """,
                },
                {
                    "action": _("Delete"),
                    "accessibility": "offboarding.cbv.accessibility.delete_stage_accessibility",
                    "attrs": """
                        data-target="#deleteConfirmation"
                        data-toggle="oh-modal-toggle"
                        hx-get="{get_delete_url}"
                        hx-target="#deleteConfirmationBody"
                    """,
                },
            ],
        }
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.annotate(
            employee_count=Count("offboardingemployee", distinct=True)
        )
        self.queryset = queryset.order_by("sequence")
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Deep links (dashboard cards/charts/notice-tracker rows, or this
        # tab's own Employee/Advanced filter panel) narrow which employees
        # match via PipelineEmployeeFilter -- when one of those is active,
        # only the stage(s) that actually contain a match should render
        # open, instead of every stage auto-expanding like a plain,
        # unfiltered visit does.
        is_filtered = bool(self.request.GET.get("custom_field")) or any(
            self.request.GET.get(name) for name in PipelineEmployeeFilter.base_filters
        )
        for stage in context["groups"]:
            stage.pipeline_open = (
                not is_filtered
                or PipelineEmployeeFilter(
                    self.request.GET,
                    queryset=OffboardingEmployee.objects.filter(stage_id=stage.pk),
                ).qs.exists()
            )
        return context


@method_decorator(login_required, name="dispatch")
class OffboardingKanbanView(HorillaKanbanView):
    """
    Offboarding Kanban View
    """

    model = OffboardingEmployee
    filter_class = PipelineEmployeeFilter
    group_filter_class = PipelineStageFilter
    group_key = "stage_id"
    records_per_page = 10
    show_kanban_confirmation = False
    pre_move_check_url = reverse_lazy("offboarding-kanban-required-task-check")

    kanban_attrs = """
        hx-get='{get_individual_url}'
        hx-target='#genericModalBody'
        data-toggle = 'oh-modal-toggle'
        data-target="#genericModal"
        data-group-order='{ordered_group_json}'
    """

    group_actions = [
        {
            "action": "Add Employee",
            "accessibility": "offboarding.cbv.accessibility.add_employee_accessibility",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_employee_url}"
                hx-target="#genericModalBody"
                class="oh-dropdown__link"
            """,
        },
        {
            "action": "Edit",
            "accessibility": "offboarding.cbv.accessibility.edit_stage_accessibility",
            "attrs": """
                hx-target="#genericModalBody"
                hx-get="{get_update_url}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
            """,
        },
        {
            "action": "Delete",
            "accessibility": "offboarding.cbv.accessibility.delete_stage_accessibility",
            "attrs": """
                data-target="#deleteConfirmation"
                data-toggle="oh-modal-toggle"
                hx-get="{get_delete_url}"
                hx-target="#deleteConfirmationBody"
            """,
        },
    ]

    details = {
        "image_src": "{employee_id__get_avatar}",
        "title": "{employee_id__get_full_name}",
        "Notice period start": "{notice_period_starts}",
        "Notice period end": "{notice_period_ends}",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.actions = [
            {
                "action": "Send Mail",
                "accessibility": "offboarding.cbv.accessibility.add_employee_accessibility",
                "attrs": """
                    data-target="#sendMailModal"
                    data-toggle="oh-modal-toggle"
                    hx-get="{get_mail_send_url}"
                    hx-target="#mail-content"
                """,
            },
            {
                "action": "Notes",
                "attrs": """
                    data-target="#genericSidebar"
                    data-toggle="oh-modal-toggle"
                    hx-get="{get_notes_url}"
                    hx-target="#genericOffCanvas"
                    onclick="$('#genericSidebar').addClass('oh-activity-sidebar--show')"
                """,
            },
            {
                "action": "get_archive_title",
                "accessibility": "offboarding.cbv.accessibility.archive_employee_accessibility",
                "attrs": """
                    data-target="#objectDetailsModal"
                    data-toggle="oh-modal-toggle"
                    hx-get="{get_archive_url}"
                    hx-target="#objectDetailsModalTarget"
                """,
            },
            {
                "action": "Edit",
                "accessibility": "offboarding.cbv.accessibility.edit_employee_accessibility",
                "attrs": """
                    data-target="#objectDetailsModal"
                    data-toggle="oh-modal-toggle"
                    hx-get="{get_edit_url}"
                    hx-target="#objectDetailsModalTarget"
                """,
            },
            {
                "action": "managing records",
                "accessibility": "offboarding.cbv.accessibility.edit_employee_accessibility",
                "attrs": """
                    data-target="#objectDetailsModal"
                    data-toggle="oh-modal-toggle"
                    hx-get="{get_managing_record_url}"
                    hx-target="#objectDetailsModalTarget"
                """,
            },
        ]

        if self.request.user.has_perm("offboarding.delete_offboardingemployee"):
            self.actions.append(
                {
                    "action": "Delete",
                    "accessibility": "offboarding.cbv.accessibility.add_employee_accessibility",
                    "attrs": f"""
                        hx-confirm="Do you want to delete this offboarding user?"
                        hx-post="{{get_delete_url}}"
                        hx-swap="none"
                        hx-on-htmx-after-request = "$(`#{self.view_id}`).find('.reload-record').click()"
                    """,
                },
            )

    def get_related_groups(self, *args, **kwargs):
        related_groups = super().get_related_groups(*args, **kwargs)
        off_id = self.kwargs.get("pk")
        if off_id:
            related_groups = related_groups.filter(offboarding_id=off_id)

        return related_groups


@method_decorator(login_required, name="dispatch")
class OffboardingKanbanRequiredTaskCheck(View):
    """
    Pre-move check for the offboarding kanban drag-and-drop: blocks forward
    stage moves while required tasks in the employee's current stage are
    incomplete. Wired up generically via OffboardingKanbanView.pre_move_check_url.
    """

    def get(self, request, *args, **kwargs):
        employee_pk = request.GET.get("objectId")
        target_stage_id = request.GET.get("groupId")
        offboarding_employee = OffboardingEmployee.objects.filter(
            pk=employee_pk
        ).first()
        target_stage = OffboardingStage.objects.filter(pk=target_stage_id).first()
        if not offboarding_employee or not target_stage:
            return JsonResponse({"blocked": False})

        current_stage = offboarding_employee.stage_id
        if (
            not current_stage
            or current_stage.sequence is None
            or target_stage.sequence is None
        ):
            return JsonResponse({"blocked": False})

        pending_tasks = offboarding_employee.pending_required_tasks(current_stage)
        if pending_tasks.exists():
            task_titles = ", ".join(pending_tasks.values_list("title", flat=True))
            message = str(
                _(
                    "Complete the following required task(s) before "
                    "moving to the next stage: %(tasks)s"
                )
                % {"tasks": task_titles}
            )
            return JsonResponse({"blocked": True, "message": message})

        return JsonResponse({"blocked": False})


@method_decorator(login_required, name="dispatch")
class OffboardingEmployeeList(HorillaListView):
    """
    Offboarding Employee List View
    """

    model = OffboardingEmployee
    filter_class = PipelineEmployeeFilter
    filter_keys_to_remove = ["offboarding_stage_id", "offboarding_id"]
    next_prev = False
    quick_export = False
    filter_selected = False
    records_per_page = 10
    records_count_in_tab = False
    template_name = "cbv/exit_process/employee_list.html"
    custom_empty_template = "cbv/pipeline/empty.html"
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Notice Period"), "get_notice_period_col"),
        (_("Start Date"), "notice_period_starts"),
        (_("End Date"), "notice_period_ends"),
        (_("Stage"), "get_stage_col"),
        (_("Created At"), "get_created_at_date"),
        (_("Task Status"), "get_task_status_col"),
    ]

    action_method = """get_action_col"""

    header_attrs = {
        "action": """ style="width:180px !important;" """,
        "add_task_action": """ style="width:110px !important;" """,
    }

    row_attrs = """
        class = "fw-bold"
        hx-get='{get_individual_url}'
        hx-target='#genericModalBody'
        data-toggle = 'oh-modal-toggle'
        data-target="#genericModal"
    """
    bulk_update_fields = ["stage_id"]

    def dispatch(self, request, *args, **kwargs):
        # This endpoint returns only the pipeline's list/export fragment; a
        # genuine top-level browser navigation/reload should land on the
        # real Offboarding Pipeline page instead of showing the raw fragment.
        if request.headers.get("Sec-Fetch-Mode") == "navigate":
            return redirect(reverse("offboarding-pipeline"))
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.selected_instances_key_id = (
            f"OffboardingEmployeeRecords{self.request.GET.get('offboarding_stage_id')}"
        )
        return super().get(request, *args, **kwargs)

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        if not getattr(self, "queryset", None):
            qs = OffboardingEmployee.objects.entire()
            queryset = super().get_queryset(qs, filtered, *args, **kwargs)
            if not (
                self.request.user.has_perm("offboarding.view_offboarding")
                or any_manager(self.request.user.employee_get)
            ):
                queryset = queryset.filter(employee_id=self.request.user.employee_get)
            self.queryset = queryset
        return self.queryset

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.view_id = (
            f"offboardingStageContainer{self.request.GET.get('offboarding_stage_id')}"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        self.managing_offboarding_tasks = OffboardingTask.objects.filter(
            managers__employee_user_id=self.request.user
        ).values_list("pk", flat=True)
        self.request.managing_offboarding_tasks = self.managing_offboarding_tasks

        self.managing_offboarding_stages = OffboardingStage.objects.filter(
            managers__employee_user_id=self.request.user
        ).values_list("pk", flat=True)
        self.request.managing_offboarding_stages = self.managing_offboarding_stages

        self.managing_offboardings = Offboarding.objects.filter(
            managers__employee_user_id=self.request.user
        ).values_list("pk", flat=True)
        self.request.managing_offboardings = self.managing_offboardings

        stage_id = self.request.GET.get("offboarding_stage_id")
        context["stage"] = (
            OffboardingStage.objects.filter(pk=stage_id).first() if stage_id else None
        )
        tasks = (
            OffboardingTask.objects.filter(stage_id=stage_id)
            if stage_id
            else OffboardingTask.objects.none()
        )
        for task in tasks:
            context["columns"].append(
                (
                    f"""
                        <div class="group w-full flex items-center justify-between transition duration-300">
                          <span class="px-2 py-1 text-xs">
                            {task.title}
                          </span>
                          <div class="hidden group-hover:flex items-center transition duration-300 gap-1 p-1 rounded z-10 bg-white"
                               onclick="event.stopPropagation()">
                            <button
                              hx-get="{reverse("offboarding-update-task",kwargs={"pk":task.pk})}"
                              hx-target="#genericModalBody"
                              data-toggle="oh-modal-toggle"
                              data-target="#genericModal"
                              class="oh-hover-btn__small"
                              title="{_('Edit')}"
                            >
                              <ion-icon name="create-outline"></ion-icon>
                            </button>
                            <a
                              hx-get="{reverse("generic-delete")}?model=offboarding.OffboardingTask&pk={task.id}"
                              hx-target="#deleteConfirmationBody"
                              data-target="#deleteConfirmation"
                              data-toggle="oh-modal-toggle"
                              class="oh-hover-btn__small"
                              title="{_('Delete')}"
                            >
                              <ion-icon name="trash-outline"></ion-icon>
                            </a>
                          </div>
                        </div>
                    """,
                    f"get_{task.pk}_task",
                )
            )
        if self.request.user.has_perm(
            "perms.offboarding.add_offboardingtask"
        ) or any_manager(self.request.user.employee_get):
            context["columns"].append(
                (
                    f"""
                        <button
                            class="px-3 py-1.5 bg-primary-100 text-primary-600 text-xs font-medium rounded-md inline-flex items-center gap-1 hover:bg-primary-600 hover:text-white transition duration-300"
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-get="{reverse('offboarding-add-task')}?stage_id={stage_id}"
                            hx-target="#genericModalBody"
                            >
                            <ion-icon name="add-outline"></ion-icon>
                            {_('Task')}
                        </button>
                        <script>
                            (function() {{
                                var span = document.currentScript.closest('span.w-max');
                                if (span) {{
                                    span.style.width = '100%';
                                    span.style.justifyContent = 'center';
                                }}
                            }})();
                        </script>
                        """,
                    "add_task_action",
                )
            )
        return context

    def bulk_update_accessibility(self):
        return (
            self.request.user.has_perm("offboarding.change_offboardingstage")
            or self.request.user.has_perm("offboarding.change_offboarding")
            or any_manager(self.request.user.employee_get)
        )

    def get_bulk_form(self):
        form = super().get_bulk_form()
        offboarding_id = self.request.GET.get("offboarding_id")
        offboarding_stage_id = self.request.GET.get("offboarding_stage_id")
        form.fields.get("stage_id").queryset = form.fields.get(
            "stage_id"
        ).queryset.filter(offboarding_id=offboarding_id)

        tasks = OffboardingTask.objects.filter(stage_id=offboarding_stage_id)
        for task in tasks:
            form.fields[f"bulk_task_status_{task.pk}"] = forms.ChoiceField(
                choices=[
                    ("", "----------"),
                ]
                + list(EmployeeTask.statuses),
                label=task.title,
                required=False,
                widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
            )

        if not self.bulk_update_accessibility():
            del form["stage_id"]

        return form

    def handle_bulk_submission(self, request):
        response = super().handle_bulk_submission(request)
        mapped_data = {
            int(re.search(r"bulk_task_status_(\d+)", key).group(1)): value
            for key, value in request.POST.items()
            if re.search(r"bulk_task_status_(\d+)", key)
        }
        instance_ids = request.POST.get("instance_ids", "[]")
        instance_ids = eval_validate(instance_ids)
        for pk, status in mapped_data.items():
            EmployeeTask.objects.filter(
                employee_id__in=instance_ids, task_id=pk
            ).update(status=status)
        return response


@method_decorator(login_required, name="dispatch")
class DashboardTaskListview(HorillaListView):
    """
    For dashboard task status table
    """

    # view_id = "view-container"

    model = OffboardingEmployee
    filter_class = PipelineEmployeeFilter
    bulk_select_option = False
    view_id = "dashboard_task_status"
    show_toggle_form = False

    def get_queryset(self):
        """
        Returns a filtered queryset of records assigned to a specific employee
        """

        qs = OffboardingEmployee.objects.entire()
        queryset = super().get_queryset(queryset=qs)
        return queryset

    columns = [
        ("Employee", "employee_id", "employee_id__get_avatar"),
        ("Stage", "stage_id"),
        ("Task Status", "get_task_status_col"),
    ]


if apps.is_installed("asset"):

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        any_manager_can_enter("offboarding.view_offboarding"), name="dispatch"
    )
    class DashboardNotReturndAsssets(HorillaListView):
        """
        For dashboard task status table
        """

        bulk_select_option = False
        view_id = "dashboard_task_status"
        show_toggle_form = False

        def __init__(self, *args, **kwargs):
            AssetAssignment = get_horilla_model_class(
                app_label="asset", model="assetassignment"
            )
            self.model = AssetAssignment  # 809
            super().__init__(*args, **kwargs)

        def get_queryset(self):
            """
            Returns a filtered queryset of records assigned to a specific employee
            """

            offboarding_employees = OffboardingEmployee.objects.entire().values_list(
                "employee_id__id", flat=True
            )
            qs = self.model.objects.entire().filter(
                return_status__isnull=True,
                assigned_to_employee_id__in=offboarding_employees,
            )
            queryset = (
                super().get_queryset().filter(id__in=qs.values_list("id", flat=True))
            )
            return queryset

        columns = [
            (
                "Employee",
                "assigned_to_employee_id__get_full_name",
                "assigned_to_employee_id__get_avatar",
            ),
            ("Asset", "asset_id__asset_name"),
            ("Reminder", "get_send_mail_employee_link"),
        ]

        row_attrs = """
                    onclick="
                    localStorage.setItem('activeTabAsset','#tab_2');
                    window.location.href='{get_asset_of_offboarding_employee}'"
                    """


if apps.is_installed("pms"):

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        any_manager_can_enter("offboarding.view_offboarding"), name="dispatch"
    )
    class DashboardFeedbackView(HorillaListView):
        """
        For dashboard task status table
        """

        bulk_select_option = False
        view_id = "dashboard_task_status"
        show_toggle_form = False

        columns = [
            ("Employee", "employee_id__get_full_name", "employee_id__get_avatar"),
            ("Feedback", "review_cycle"),
            ("Status", "status"),
        ]

        def __init__(self, *args, **kwargs):
            self.Feedback = get_horilla_model_class(app_label="pms", model="feedback")
            self.model = self.Feedback  # 809
            super().__init__(*args, **kwargs)

        def get_queryset(self):
            """
            Returns a filtered queryset of records assigned to a specific employee
            """
            offboarding_employees = OffboardingEmployee.objects.entire().values_list(
                "employee_id__id", "notice_period_starts"
            )
            if offboarding_employees:
                id_list, date_list = map(list, zip(*offboarding_employees))
            else:
                id_list, date_list = [], []

            qs = (
                self.model.objects.entire()
                .filter(employee_id__in=id_list)
                .exclude(status="Closed")
            )
            queryset = (
                super().get_queryset().filter(id__in=qs.values_list("id", flat=True))
            )
            return queryset
