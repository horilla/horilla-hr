"""
onboarding/cbv/pipeline.py
"""

import json
import re
from typing import Any

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from base.methods import eval_validate
from horilla.horilla_middlewares import _thread_locals
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    render_template,
)
from horilla_views.generic.cbv.kanban import HorillaKanbanView
from horilla_views.generic.cbv.pipeline import Pipeline
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
)
from horilla_views.models import ActiveView
from onboarding import filters as onboarding_filters
from onboarding import forms
from onboarding import models as onboarding_models
from onboarding.cbv_decorators import all_manager_can_enter, stage_manager_can_enter
from onboarding.templatetags.onboardingfilters import stage_manages
from recruitment import models as recruitment_models
from recruitment.cbv.candidates import CandidateDetail
from recruitment.methods import recruitment_manages


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class PipelineView(TemplateView):
    """
    PipelineView
    """

    template_name = "cbv/pipeline/onboarding/pipeline.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class PipelineNav(HorillaNavView):
    """
    HorillaNavView
    """

    search_url = reverse_lazy("cbv-pipeline-tab-onboarding")
    nav_title = _("Onboarding Tasks")
    search_swap_target = "#pipelineContainer"
    apply_first_filter = False
    filter_body_template = "cbv/pipeline/onboarding/filters.html"
    filter_instance = onboarding_filters.RecruitmentFilter()
    # filter_instance_context_name = "filter"
    filter_form_context_name = "form"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. onboarding_filters.RecruitmentFilter inherits
    # recruitment.filters.RecruitmentFilter.ajax_fields (Managers,
    # Company); OnboardingStageFilter/OnboardingCandidateFilter each
    # carry their own ajax_fields for the Stage Manager/Tasks pickers
    # this combined panel renders.
    modern_filter = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse_lazy("cbv-pipeline-tab-onboarding")}',
                "attrs": f"""
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse_lazy("cbv-pipeline-tab-onboarding")}?view=card',
                "attrs": f"""
                    title ='Card'
                """,
            },
        ]

    def get_context_data(self, **kwargs):
        """
        context data
        """
        context = super().get_context_data(**kwargs)
        stage_filter_obj = onboarding_filters.OnboardingStageFilter()
        candidate_filter_obj = onboarding_filters.OnboardingCandidateFilter()
        context["stage_filter_obj"] = stage_filter_obj
        context["candidate_filter_obj"] = candidate_filter_obj
        return context


def recruitment_pipeline_actions_onboarding(request, rec):
    """
    Recruitment-level actions (Add Stage/Manage Stage Order/Edit/Delete)
    for the given recruitment's onboarding pipeline - shared between
    RecruitmentTabView (which used to put these in the tab bar's kebab)
    and RecruitmentPipelineContentShell (which renders them inline in the
    pipeline content's own header instead).
    """
    actions = []
    if request.user.has_perm("onboarding.add_onboardingstage") or recruitment_manages(
        request, rec
    ):
        actions.append(
            {
                "action": _("Add Stage"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("stage-creation", kwargs={"obj_id": rec.pk})}"
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
                    hx-get="{reverse("onboarding-stage-sequence-update", kwargs={"pk": rec.pk})}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )
    if request.user.has_perm("recruitment.change_recruitment"):
        actions.append(
            {
                "action": _("Edit"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("recruitment-update-pipeline", kwargs={"pk": rec.pk})}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )
    if request.user.has_perm("recruitment.delete_recruitment"):
        actions.append(
            {
                "action": _("Delete"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#deleteConfirmation"
                    hx-get="{reverse('generic-delete')}?model=recruitment.Recruitment&pk={rec.pk}&reload_target=%23applyFilter"
                    hx-target="#deleteConfirmationBody"
                    style="cursor: pointer;"
                """,
            }
        )
    return actions


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentTabView(HorillaTabView):
    """
    RecruitmentTabView
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        recruitments = onboarding_filters.RecruitmentFilter(self.request.GET).qs.filter(
            is_active=True
        )
        view_type = self.request.GET.get("view", "list")
        # Carry over any other query params (e.g. ?task_status=stuck from the
        # dashboard's Stuck Tasks tile) down into each tab's shell, which in
        # turn forwards them to the actual board content request -- "view"
        # is excluded since it's already handled by the view_type/url logic
        # below, not meant to be a board-content filter itself.
        extra_params = self.request.GET.copy()
        extra_params.pop("view", None)
        extra_qs = extra_params.urlencode()
        self.tabs = []
        # Candidates on each job's board (one stage row per candidate), not
        # how many stages it has.
        candidate_stage_qs = onboarding_models.CandidateStage.objects.filter(
            onboarding_stage_id__recruitment_id__in=recruitments.values_list(
                "pk", flat=True
            ),
            onboarding_stage_id__is_active=True,
        )
        # The card/kanban board sets records_count_in_tab = False precisely so
        # this tab badge counts candidates, not columns -- but unlike the list
        # board's own stage badges (CandidatePipeline.get_queryset), nothing
        # ever patches this one from the client side, so a task_status filter
        # left unapplied here stuck permanently at the unfiltered total: the
        # dashboard's Stuck Tasks tile landed on a tab badge that kept showing
        # every candidate, never the stuck ones, no matter what the board
        # underneath it correctly rendered.
        task_status = self.request.GET.get("task_status")
        if task_status:
            candidate_stage_qs = candidate_stage_qs.filter(
                candidate_id__candidate_task__status=task_status
            )
        candidate_counts = dict(
            candidate_stage_qs.values("onboarding_stage_id__recruitment_id")
            .annotate(total=Count("candidate_id", distinct=True))
            .values_list("onboarding_stage_id__recruitment_id", "total")
        )
        for rec in recruitments:
            tab = {}
            tab["title"] = rec
            url = reverse("onboarding-pipeline-shell", kwargs={"rec_id": rec.pk})
            query_parts = []
            if view_type != "list":
                query_parts.append(f"view={view_type}")
            if extra_qs:
                query_parts.append(extra_qs)
            if query_parts:
                url += "?" + "&".join(query_parts)
            tab["url"] = url

            tab["badge_label"] = _("Candidates")
            tab["badge"] = candidate_counts.get(rec.pk, 0)
            self.tabs.append(tab)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentCandidateNav(HorillaNavView):
    """
    Per-job-tab Search+Filter for the Onboarding pipeline page, mirroring
    recruitment.cbv.pipeline.RecruitmentCandidateNav: one instance per job
    tab, searching/filtering that job's own onboarding candidates
    (PipelineCandidateFilter) rather than the page-level RecruitmentFilter
    (which decides which RECRUITMENTS show up as tabs at all).
    """

    filter_form_context_name = "form"
    filter_body_template = "cbv/pipeline/onboarding/candidate_filter.html"
    apply_first_filter = True
    template_name = "generic/inline_nav.html"
    nav_title = _("Pipeline")
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as the page-level
    # PipelineNav/filters.html and the sibling recruitment/offboarding
    # per-tab panels. PipelineCandidateFilter is now a HorillaFilterSet
    # subclass so it gets the Advanced "+ Add filter" builder too.
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        rec_id = self.request.resolver_match.kwargs.get("rec_id")
        view_type = self.request.GET.get("view")
        if view_type == "card":
            self.search_url = reverse(
                "candidate-card-cbv-onboarding", kwargs={"pk": rec_id}
            )
        else:
            self.search_url = reverse(
                "get-stages-onboarding", kwargs={"recruitment_id": rec_id}
            )
        self.search_swap_target = f"#pipelineTabContent{rec_id}"
        self.filter_instance = onboarding_filters.PipelineCandidateFilter()

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse(
                    "get-stages-onboarding", kwargs={"recruitment_id": rec_id}
                ),
                "attrs": """
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("candidate-card-cbv-onboarding", kwargs={"pk": rec_id})
                + "?view=card",
                "attrs": """
                    title ='Card'
                """,
            },
        ]

        rec = recruitment_models.Recruitment.objects.filter(pk=rec_id).first()
        if rec:
            self.actions = recruitment_pipeline_actions_onboarding(self.request, rec)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentPipelineContentShell(TemplateView):
    """
    Shell rendered for a single recruitment's onboarding pipeline tab -
    wraps this tab's own Nav (RecruitmentCandidateNav, which carries the
    Search+Filter and job-level Actions) and an htmx-loaded embed of the
    existing list/kanban content.
    """

    template_name = "cbv/pipeline/onboarding/recruitment_pipeline_shell.html"

    def saved_view_type(self, rec_id):
        """
        The list/card choice this user last made, for this job's tab.
        """
        user = self.request.user
        if not (user and user.is_authenticated):
            return None
        active_view = (
            ActiveView.objects.filter(created_by=user)
            .filter(
                Q(
                    path=reverse(
                        "onboarding-pipeline-tab-nav", kwargs={"rec_id": rec_id}
                    )
                )
            )
            .order_by("-path")
            .first()
        )
        return active_view.type if active_view else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rec = get_object_or_404(
            recruitment_models.Recruitment, pk=self.kwargs.get("rec_id")
        )
        # Falls back to "list" (not just None) when neither this request nor
        # a saved ActiveView row picked a view - content_url below already
        # defaults to the list endpoint in that case, so the Nav's view-type
        # toggle must resolve to the same "list" here too. Passing a falsy
        # view_type through left nav_url without a `?view=`, so on a user's
        # very first visit (no saved choice yet) HorillaNavView never marked
        # either toggle button active even though list content was already
        # on screen - and inline_nav.html's onload script then read "no
        # button active" as "no filter has run yet" and fired an extra,
        # redundant full-board resubmit right behind the first load.
        view_type = (
            self.request.GET.get("view") or self.saved_view_type(rec.pk) or "list"
        )
        content_url = reverse(
            "get-stages-onboarding", kwargs={"recruitment_id": rec.pk}
        )
        if view_type == "card":
            content_url = reverse(
                "candidate-card-cbv-onboarding", kwargs={"pk": rec.pk}
            )
        # Forward any extra query params (e.g. ?task_status=stuck) through to
        # the actual board content request -- "view" is excluded since it
        # only picks which endpoint above, not a board-content filter itself.
        extra_params = self.request.GET.copy()
        extra_params.pop("view", None)
        extra_qs = extra_params.urlencode()
        if extra_qs:
            content_url += f"?{extra_qs}"
        context["content_url"] = content_url
        context["rec_id"] = rec.pk
        context["nav_url"] = (
            reverse("onboarding-pipeline-tab-nav", kwargs={"rec_id": rec.pk})
            + f"?view={view_type}"
        )
        return context


def edit_stage_path(self):
    """
    Edit stage path
    """
    return reverse(
        "stage-update", kwargs={"pk": self.pk, "obj_id": self.recruitment_id.pk}
    )


def generic_delete_path(self):
    """
    Generic delete
    """
    return f"{reverse('generic-delete')}?model=onboarding.OnboardingStage&pk={self.pk}"


def bulk_send_mail_path(self):
    """
    bulk_send_mail
    """
    return f"{reverse_lazy('send-mail')}?onboarding_stage_id={self.pk}"


def allocation_path(self):
    """
    allocate path
    """
    return f'{reverse("allocation-view",kwargs={"pk":self.candidate_id.pk})}?model=recruitment.models.Candidate'


onboarding_models.CandidateStage.allocation_path = allocation_path

onboarding_models.OnboardingStage.edit_stage_path = edit_stage_path
onboarding_models.OnboardingStage.generic_delete_path = generic_delete_path
onboarding_models.OnboardingStage.bulk_send_mail_path = bulk_send_mail_path


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidatePipeline(Pipeline):
    """
    CandidatePipeline
    """

    model = onboarding_models.CandidateStage
    filter_class = onboarding_filters.OnboardingCandidateFilter
    grouper = "onboarding_stage_id"
    selected_instances_key_name = "selectedCandidateRecords"
    template_name = "cbv/pipeline/onboarding/stages_v2.html"
    allowed_fields = [
        {
            "field": "onboarding_stage_id",
            "model": onboarding_models.OnboardingStage,
            "filter": onboarding_filters.OnboardingStageFilter,
            "url": reverse_lazy("candidate-lists-cbv-onboarding"),
            "parameters": [
                "onboarding_stage_id={pk}",
                "recruitment_id={recruitment_id__pk}",
            ],
            "actions": [
                {
                    "action": _("Edit"),
                    "accessibility": "onboarding.cbv.accessibility.edit_stage_accessibility",
                    "attrs": """
                    hx-target="#genericModalBody"
                    hx-get="{edit_stage_path}"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                """,
                },
                {
                    "action": _("Bulk Mail"),
                    "attrs": """
                    hx-target="#objectCreateModalTarget"
                    hx-get="{bulk_send_mail_path}"
                    data-toggle="oh-modal-toggle"
                    data-target="#objectCreateModal"
                """,
                },
                {
                    "action": _("Delete"),
                    "accessibility": "onboarding.cbv.accessibility.delete_stage_accessibility",
                    "attrs": """
                    data-target="#deleteConfirmation"
                    data-toggle="oh-modal-toggle"
                    hx-get="{generic_delete_path}"
                    hx-target="#deleteConfirmationBody"
                """,
                },
            ],
        },
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        # OnboardingStageFilter (this grouper's own field_filter_class) has no
        # task_status field, so a deep link like the dashboard's Stuck Tasks
        # tile (?task_status=stuck) never touched this count: every stage kept
        # showing its total candidate count regardless, and a stage with zero
        # *matching* candidates stayed expanded instead of auto-collapsing,
        # since that decision reads this same number. The nested candidate
        # list a few lines of HTML down does filter correctly (via
        # PipelineCandidateFilter), so the badge looked wrong only until its
        # own JS later patched it from that list's real count.
        task_status = self.request.GET.get("task_status")
        count_filter = (
            Q(candidate__candidate_id__candidate_task__status=task_status)
            if task_status
            else Q()
        )
        queryset = queryset.annotate(
            candidate_count=Count("candidate", filter=count_filter, distinct=True)
        )
        self.queryset = queryset.order_by("sequence")
        return self.queryset


def stage_drop_down(self):
    """
    Stage drop down
    """
    request = getattr(_thread_locals, "request", None)
    all_onboarding_stages = getattr(request, "all_onboarding_stages", {})
    if all_onboarding_stages.get(self.onboarding_stage_id.recruitment_id.pk) is None:
        stages = onboarding_models.OnboardingStage.objects.filter(
            recruitment_id=self.onboarding_stage_id.recruitment_id
        )
        all_onboarding_stages[self.onboarding_stage_id.recruitment_id.pk] = stages
        request.all_onboarding_stages = all_onboarding_stages
    return render_template(
        path="cbv/pipeline/onboarding/stage_drop_down.html",
        context={
            "instance": self,
            "stages": request.all_onboarding_stages[
                self.onboarding_stage_id.recruitment_id.pk
            ],
        },
    )


onboarding_models.CandidateStage.stage_drop_down = stage_drop_down


def get_detail_url_pipeline(self):
    """
    Get detail url pipeline
    """
    return reverse("onboarding-cand-detail-view", kwargs={"pk": self.candidate_id.pk})


onboarding_models.CandidateStage.get_detail_url_pipeline = get_detail_url_pipeline


def task_fetch(self):
    """
    task fetch
    """
    return f"""
        <div id="selectedInstanceIds" data-ids="[]"></div>
        <div
            hx-get="{reverse('get-cand-task',kwargs={"pk":self.pk})}?field=stage_id"
            hx-trigger="load"
        ></div>
    """


recruitment_models.Candidate.task_fetch = task_fetch


class CandidateOnboardingDetail(CandidateDetail):
    """
    Extended candidate detail view
    """

    body = [
        (_("Gender"), "gender"),
        (_("Phone"), "mobile"),
        (_("Stage"), "stage_drop_down"),
        (_("Rating"), "rating_bar"),
        (_("Recruitment"), "recruitment_id"),
        (_("Job Position"), "job_position_id__job_position"),
        (_("Tasks"), "task_fetch", True),
    ]

    cols = {"task_fetch": 12}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance and instance.onboarding_stage:
            self.ordered_ids_key = f"ordered_ids_{self.model.__name__.lower()}{instance.onboarding_stage.onboarding_stage_id.pk}"
        response = super().get(request, *args, **kwargs)
        return response


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidateList(HorillaListView):
    """
    CandidateList
    """

    model = onboarding_models.CandidateStage
    filter_class = onboarding_filters.PipelineCandidateFilter
    filter_selected = False
    quick_export = False
    next_prev = False
    records_per_page = 10
    filter_keys_to_remove = ["onboarding_stage_id", "rec_id", "recruitment_id"]
    template_name = "cbv/pipeline/onboarding/candidate_list.html"
    custom_empty_template = "cbv/pipeline/empty.html"
    header_attrs = {
        "action": "style='width:120px;'",
        "stage_drop_down": "style='width:100px;'",
        "add_task_action": "style='width:110px;'",
    }
    columns = [
        (_("Name"), "candidate_id__candidate_name", "candidate_id__get_avatar"),
        (_("Email"), "candidate_id__mail_indication"),
        (_("Contact"), "candidate_id__mobile"),
        (_("Stage"), "stage_drop_down"),
        (_("Rating"), "candidate_id__rating_bar"),
        (_("Job Position"), "candidate_id__job_position_id__job_position"),
    ]

    default_columns = [
        (_("Name"), "candidate_id__candidate_name", "candidate_id__get_avatar"),
        (_("Email"), "candidate_id__mail_indication"),
        (_("Stage"), "stage_drop_down"),
    ]

    bulk_update_fields = [
        "onboarding_stage_id",
    ]

    row_attrs = """
                hx-get='{get_detail_url_pipeline}'
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                """

    actions = [
        {
            "action": _("Allocations"),
            "icon": "clipboard-outline",
            "attrs": """
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    hx-get = "{allocation_path}"
                    data-toggle="oh-modal-toggle"
                    data-target="#allocationModal"
                    hx-target="#allocationModalBody"
                """,
        },
        {
            "action": _("Send Mail"),
            "icon": "mail-open-outline",
            "attrs": """
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    hx-get = "{candidate_id__get_send_mail}"
                    data-toggle="oh-modal-toggle"
                    data-target="#objectDetailsModal"
                    hx-target="#objectDetailsModalTarget"
                """,
        },
        {
            "action": _("View Note"),
            "icon": "newspaper-outline",
            "attrs": """
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm oh-activity-sidebar__open"
                    hx-get="{candidate_id__get_view_note_url}"
                    data-target="#activitySidebar"
                    hx-target="#activitySidebar"
                    onclick="$('#activitySidebar').addClass('oh-activity-sidebar--show')"
                """,
        },
        # {
        #     "action": _("Document Request"),
        #     "icon": "document-attach-outline",
        #     "attrs": """
        #             hx-get="{candidate_id__get_document_request}"
        #             data-target="#genericModal"
        #             hx-target="#genericModalBody"
        #             class="oh-btn oh-btn--danger-outline oh-btn--light-bkg w-100"
        #             data-toggle="oh-modal-toggle"
        #         """,
        # },
    ]
    records_count_in_tab = False

    def get(self, request, *args, **kwargs):
        self.selected_instances_key_id = (
            f"selectedCandidateRecords{self.request.GET.get('onboarding_stage_id')}"
        )
        return super().get(request, *args, **kwargs)

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        queryset = super().get_queryset(queryset, filtered, *args, **kwargs)
        return queryset

    def bulk_update_accessibility(self):
        """
        Check has perm to update candidate stage
        """
        if self.request.method == "GET":
            return True
        return (
            self.request.user.has_perm("onboarding.change_candidatestage")
            or self.request.user.has_perm("recruitment.change_recruitment")
            or recruitment_manages(
                self.request,
                onboarding_models.Recruitment.objects.get(
                    pk=self.request.GET["recruitment_id"]
                ),
            )
            or stage_manages(
                self.request.user,
                onboarding_models.OnboardingStage.objects.get(
                    pk=self.request.GET["onboarding_stage_id"]
                ),
            )
        )

    def get_bulk_form(self):
        form = super().get_bulk_form()
        recruitment_id = self.request.GET["recruitment_id"]
        stage_id = self.request.GET["onboarding_stage_id"]
        form.fields["onboarding_stage_id"].queryset = form.fields[
            "onboarding_stage_id"
        ].queryset.filter(recruitment_id=recruitment_id)
        tasks = onboarding_models.OnboardingTask.objects.filter(stage_id__pk=stage_id)

        for task in tasks:
            form.fields[f"bulk_task_status_{task.pk}"] = forms.forms.ChoiceField(
                choices=[
                    ("", "----------"),
                ]
                + list(onboarding_models.CandidateTask.choice),
                label=task.task_title,
                required=False,
                widget=forms.forms.Select(
                    attrs={"class": "oh-select oh-select-2 w-100"}
                ),
            )
        if not self.bulk_update_accessibility():
            del form["onboarding_stage_id"]
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
            onboarding_models.CandidateTask.objects.filter(
                candidate_id__onboarding_stage__in=instance_ids, onboarding_task_id=pk
            ).update(status=status)
        return response

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.managing_onboarding_tasks = []
        self.managing_onboarding_stages = []
        self.managing_recruitments = []

    def dispatch(self, request, *args, **kwargs):

        if not request.user.is_authenticated:
            messages.error(request, _("You are not logged in."))
            return HorillaRedirect(request)

        self.ordered_ids_key = (
            f"ordered_ids_{recruitment_models.Candidate.__name__.lower()}"
            f"{request.GET.get('onboarding_stage_id')}"
        )
        self.search_url = request.path

        self.managing_onboarding_tasks = (
            onboarding_models.OnboardingTask.objects.filter(
                employee_id__employee_user_id=request.user
            ).values_list("pk", flat=True)
        )
        request.managing_onboarding_tasks = self.managing_onboarding_tasks

        self.managing_onboarding_stages = (
            onboarding_models.OnboardingStage.objects.filter(
                employee_id__employee_user_id=request.user
            ).values_list("pk", flat=True)
        )
        request.managing_onboarding_stages = self.managing_onboarding_stages

        self.managing_recruitments = recruitment_models.Recruitment.objects.filter(
            recruitment_managers__employee_user_id=request.user
        ).values_list("pk", flat=True)
        request.managing_recruitments = self.managing_recruitments

        stage_id = request.GET.get("onboarding_stage_id")

        if not stage_id:
            return HorillaRedirect(
                request, message=_("No stage found matching the query.")
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        stage_id = self.request.GET["onboarding_stage_id"]
        tasks = onboarding_models.OnboardingTask.objects.filter(stage_id=stage_id)

        # Per-stage task columns (one per OnboardingTask, plus "+ Task")
        # used to be appended straight onto context["columns"] AFTER
        # super().get_context_data() had already built self.toggle_form
        # from the static `columns` list above -- so they never got a
        # checkbox in the "Columns" show/hide panel, and (since they were
        # added after self.visible_column's hidden-column filtering too)
        # couldn't be hidden even if they had one. Building these tuples
        # and folding them into self.columns/self.default_columns BEFORE
        # calling super() makes the base HorillaListView machinery treat
        # them exactly like any other column, `columns` is a plain class
        # attribute (not a queryset), and ListView.as_view() gives each
        # request its own view instance, so this reassignment is
        # request-local and never leaks between requests.
        dynamic_columns = []
        dynamic_toggle_labels = {}
        dynamic_header_attrs = {}
        for task in tasks:
            col_key = f"get_{task.pk}_task"
            dynamic_toggle_labels[col_key] = task.task_title
            col_width = max(150, len(task.task_title) * 7 + 130)
            dynamic_header_attrs[col_key] = f'style="width:{col_width}px !important;"'
            dynamic_columns.append(
                (
                    f"""
                        <div class="group w-full flex items-center justify-between transition duration-300">
                            <span class="px-2 py-1 text-xs">
                                {task.task_title}
                            </span>
                            <div class="flex items-center transition duration-300 gap-1 p-1 rounded z-10 bg-white"
                                onclick="event.stopPropagation()"
                            >
                                <button
                                    hx-get="{reverse("task-update",kwargs={"pk":task.pk})}"
                                    hx-target="#genericModalBody"
                                    data-toggle="oh-modal-toggle"
                                    data-target="#genericModal"
                                    class="oh-hover-btn__small"
                                    title="{_('Edit')}"
                                >
                                    <ion-icon name="create-outline"></ion-icon>
                                </button>
                                <a
                                    hx-get="{reverse("generic-delete")}?model=onboarding.OnboardingTask&pk={task.id}"
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
                    col_key,
                )
            )
        dynamic_columns.append(
            (
                f"""
                    <button
                        class="px-3 py-1.5 bg-primary-100 text-primary-600 text-xs font-medium rounded-md inline-flex items-center gap-1 hover:bg-primary-600 hover:text-white transition duration-300"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-get="{reverse('task-creation',kwargs={'obj_id':stage_id})}"
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
        dynamic_toggle_labels["add_task_action"] = _("Add Task")
        self.columns = self.columns + dynamic_columns
        self.default_columns = self.default_columns + dynamic_columns
        self.toggle_labels = {**self.toggle_labels, **dynamic_toggle_labels}
        self.header_attrs = {**self.header_attrs, **dynamic_header_attrs}

        context = super().get_context_data(**kwargs)
        context["stage"] = onboarding_models.OnboardingStage.objects.filter(
            pk=stage_id
        ).first()
        self.request.session[self.ordered_ids_key] = list(
            self.queryset.values_list("candidate_id__pk", flat=True)
        )
        return context


@method_decorator(login_required, name="dispatch")
class CandidateKanbanView(HorillaKanbanView):
    """
    CandidateKanbanView
    """

    model = onboarding_models.OnboardingCandidate
    group_key = "onboarding_stage__onboarding_stage_id"
    records_per_page = 10
    show_kanban_confirmation = False
    # The tab badge counts candidates (set server-side), not stage columns
    records_count_in_tab = False
    filter_keys_to_remove = ["onboarding_stage_id", "rec_id", "recruitment_id"]
    filter_class = onboarding_filters.KanbanCandidateFilter
    group_filter_class = onboarding_filters.OnboardingStageFilter
    instance_order_by = "onboarding_stage__sequence"
    group_label_key = "stage_title"
    empty_group_label = _("stages")
    pre_move_check_url = reverse_lazy("onboarding-kanban-required-task-check")

    details = {
        "image_src": "{get_avatar}",
        "title": "{get_full_name}",
        "Email": "{email}",
        "Phone Number": "{phone}",
    }

    kanban_attrs = """
        hx-get='{get_detail_url_pipeline}'
        data-toggle="oh-modal-toggle"
        data-target="#genericModal"
        hx-target="#genericModalBody"
    """

    actions = [
        {
            "action": _("Allocations"),
            "attrs": """
                hx-get = "{onboarding_stage__allocation_path}"
                data-toggle="oh-modal-toggle"
                data-target="#allocationModal"
                hx-target="#allocationModalBody"
            """,
        },
        {
            "action": _("Send Mail"),
            "attrs": """
                hx-get = "{get_send_mail}"
                data-toggle="oh-modal-toggle"
                data-target="#objectDetailsModal"
                hx-target="#objectDetailsModalTarget"
            """,
        },
        {
            "action": _("View Note"),
            "attrs": """
                hx-get="{get_view_note_url}"
                data-target="#activitySidebar"
                hx-target="#activitySidebar"
                onclick="$('#activitySidebar').addClass('oh-activity-sidebar--show')"
            """,
        },
        {
            "action": _("Document Request"),
            "attrs": """
                hx-get="{get_document_request}"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                data-toggle="oh-modal-toggle"
            """,
        },
    ]

    group_actions = [
        {
            "action": "Edit",
            "accessibility": "onboarding.cbv.accessibility.edit_stage_accessibility",
            "attrs": """
                hx-target="#genericModalBody"
                hx-get="{edit_stage_path}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
            """,
        },
        {
            "action": "Bulk Mail",
            "attrs": """
                hx-target="#objectCreateModalTarget"
                hx-get="{bulk_send_mail_path}"
                data-toggle="oh-modal-toggle"
                data-target="#objectCreateModal"
            """,
        },
        {
            "action": "Delete",
            "accessibility": "onboarding.cbv.accessibility.delete_stage_accessibility",
            "attrs": """
                data-target="#deleteConfirmation"
                data-toggle="oh-modal-toggle"
                hx-get="{generic_delete_path}"
                hx-target="#deleteConfirmationBody"
            """,
        },
    ]

    def get_related_groups(self, *args, **kwargs):
        related_groups = super().get_related_groups(*args, **kwargs)
        onboarding_id = self.kwargs.get("pk")
        if onboarding_id:
            related_groups = related_groups.filter(recruitment_id=onboarding_id)

        return related_groups


@method_decorator(login_required, name="dispatch")
@method_decorator(
    stage_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class ChangeStage(HorillaFormView):
    """
    Change Candidate stage
    """

    model = onboarding_models.CandidateStage
    form_class = forms.StageChangeForm

    def form_valid(self, form):
        if form.is_valid():
            messages.success(self.request, _("Stage Updated"))
            form.save()
            return self.HttpResponse()
        messages.info(self.request, _("Stage not updated"))

        return self.HttpResponse()

    def form_invalid(self, form):
        error_message = " ".join(
            message for field_errors in form.errors.values() for message in field_errors
        )
        messages.info(self.request, _("Stage not updated"))
        return self.HttpResponse(
            script=(
                "Swal.fire({"
                f"icon: 'error', title: {json.dumps(str(_('Cannot Change Stage')))}, "
                f"text: {json.dumps(error_message)}"
                "});"
            )
        )


@method_decorator(login_required, name="dispatch")
class KanbanRequiredTaskCheck(View):
    """
    Pre-move check for the onboarding kanban drag-and-drop: blocks forward
    stage moves while required tasks in the candidate's current stage are
    incomplete. Wired up generically via CandidateKanbanView.pre_move_check_url.
    """

    def get(self, request, *args, **kwargs):
        candidate_id = request.GET.get("objectId")
        target_stage_id = request.GET.get("groupId")
        candidate_stage = onboarding_models.CandidateStage.objects.filter(
            candidate_id=candidate_id
        ).first()
        target_stage = onboarding_models.OnboardingStage.objects.filter(
            pk=target_stage_id
        ).first()
        if not candidate_stage or not target_stage:
            return JsonResponse({"blocked": False})

        current_stage = candidate_stage.onboarding_stage_id
        if current_stage.sequence is None or target_stage.sequence is None:
            return JsonResponse({"blocked": False})

        pending_tasks = candidate_stage.pending_required_tasks(current_stage)
        if pending_tasks.exists():
            task_titles = ", ".join(pending_tasks.values_list("task_title", flat=True))
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
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class AssignTask(View):
    """
    AssignTask
    """

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except ObjectDoesNotExist:
            messages.error(request, _("Requested object does not exist"))
            return HorillaRedirect(
                request, message=_("Requested object does not exist")
            )

    def get(self, *args, **kwargs):
        """
        get
        """
        task = onboarding_models.OnboardingTask.objects.get(pk=kwargs["task_id"])
        candidate = onboarding_models.CandidateStage.objects.get(
            candidate_id__id=kwargs["cand_id"]
        )
        task.candidates.add(candidate.candidate_id)
        candidate_task = onboarding_models.CandidateTask()
        candidate_task.candidate_id = candidate.candidate_id
        candidate_task.stage_id = candidate.onboarding_stage_id
        candidate_task.onboarding_task_id = task
        candidate_task.save()
        messages.success(self.request, _("Task Allocated"))

        return HttpResponse(
            f"""
            <div id="taskHidden{candidate_task.pk}"></div>
            <script>$('#taskHidden{candidate_task.pk}').closest('.hlv-container').find(".reload-record").click();</script>
            <script>$('#reloadMessagesButton').click();</script>
            """
        )

    def post(self, *args, **kwargs):
        """
        post
        """
        candidate = onboarding_models.CandidateStage.objects.get(
            candidate_id__id=kwargs["cand_id"]
        )
        candidate_task = onboarding_models.CandidateTask.objects.get(
            pk=kwargs["cand_task_id"]
        )
        status = self.request.POST["status"]
        candidate_task.status = status
        candidate_task.save()

        messages.success(self.request, _("Status updated"))

        # Re-render just this cell instead of clicking `.reload-record`
        # (which re-fetches and outerHTML-swaps the *entire* candidate
        # list): that full-table swap is what caused the visible flicker
        # on every status change, and this dropdown's own hx-target
        # already scopes the response to `#taskContainer{task_id}{cand_pk}`.
        # `#reloadMessagesButton` is unrelated to the list table (it just
        # refreshes the messages panel), so it's kept to still surface the
        # "Status updated" toast.
        cell = render_template(
            "cbv/pipeline/onboarding/tasks.html",
            {
                "instance": candidate,
                "task": candidate_task,
                "task_id": kwargs["task_id"],
            },
        )
        return HttpResponse(
            cell + "<script>$('#reloadMessagesButton').click();</script>"
        )
