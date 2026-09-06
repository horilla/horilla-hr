"""
recruitment/cbv/pipeline.py
"""

from typing import Any

from django.contrib import messages
from django.core.cache import cache as CACHE
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _

from horilla.decorators import hx_request_required
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.kanban import HorillaKanbanView
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
    get_short_uuid,
)
from horilla_views.models import ActiveView
from recruitment import filters, forms, models
from recruitment.cbv_decorators import manager_can_enter
from recruitment.templatetags.recruitmentfilters import (
    recruitment_manages,
    stage_manages,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class PipelineView(TemplateView):
    """
    PipelineView
    """

    template_name = "cbv/pipeline/pipeline.html"


def recruitment_pipeline_actions(request, rec):
    """
    Recruitment-level actions (Add Stage/Edit/Resume Shortlisting/Manage
    Stage Order/Close-Reopen/Delete) for the given recruitment - shared
    between RecruitmentTabView (which used to put these in the tab bar's
    kebab) and RecruitmentPipelineContentShell (which renders them inline
    in the pipeline content's own header instead). Each RecruitmentTabView
    tab is a distinct recruitment record, so these are naturally scoped to
    that specific record, not to "whichever tab happens to be open" - there
    is no page-level Actions button that could mean that.
    """
    change_perm = request.user.has_perm("recruitment.change_recruitment")
    add_cand_perm = request.user.has_perm("recruitment.add_candidate")
    delete_perm = request.user.has_perm("recruitment.delete_recruitment")
    add_stage_perm = request.user.has_perm("recruitment.add_stage")
    rec_manager_perm = recruitment_manages(request.user, rec)

    actions = []
    if not (rec_manager_perm or change_perm):
        return actions

    if add_stage_perm or rec_manager_perm or change_perm:
        actions.append(
            {
                "action": _("Add Stage"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse('rec-stage-create')}?recruitment_id={rec.pk}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            },
        )

    if change_perm or rec_manager_perm:
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
            },
        )

    if add_cand_perm or rec_manager_perm or change_perm:
        actions.append(
            {
                "action": _("Resume Shortlisting"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#bulkResumeUpload"
                    hx-get="{reverse('view-bulk-resume')}?rec_id={rec.pk}"
                    hx-target="#bulkResumeUploadBody"
                    style="cursor: pointer;"
                """,
            },
        )

    if add_stage_perm or rec_manager_perm or change_perm:
        actions.append(
            {
                "action": _("Manage Stage Order"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    hx-get="{reverse("rec-update-stage-seq", kwargs={"pk": rec.pk})}"
                    hx-target="#genericModalBody"
                    style="cursor: pointer;"
                """,
            }
        )

    if change_perm or rec_manager_perm:
        if rec.closed:
            actions.append(
                {
                    "action": _("Reopen"),
                    "attrs": f"""
                        href="{reverse("recruitment-reopen-pipeline", kwargs={"rec_id": rec.pk})}"
                        style="cursor: pointer;"
                        onclick="return confirm('Are you sure you want to reopen this recruitment?');"
                    """,
                },
            )
        else:
            actions.append(
                {
                    "action": _("Close"),
                    "attrs": f"""
                        href="{reverse("recruitment-close-pipeline", kwargs={"rec_id": rec.pk})}"
                        style="cursor: pointer;"
                        onclick="return confirm('Are you sure you want to close this recruitment?');"
                    """,
                },
            )

    if delete_perm:
        actions.append(
            {
                "action": _("Delete"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#deleteConfirmation"
                    hx-get="{reverse('generic-delete')}?model=recruitment.Recruitment&pk={rec.pk}"
                    hx-target="#deleteConfirmationBody"
                    style="cursor: pointer;"
                """,
            }
        )
    return actions


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentTabView(HorillaTabView):
    """
    RecruitmentTabView
    """

    filter_class = filters.RecruitmentFilter

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        recruitments = self.filter_class(self.request.GET).qs.filter(
            is_active=True, closed=False
        )
        view_type = self.request.GET.get("view")
        if not view_type and self.request.user and self.request.user.is_authenticated:
            active_view = (
                ActiveView.objects.filter(created_by=self.request.user)
                .filter(Q(path=self.request.path) | Q(path=reverse("cbv-pipeline")))
                .first()
            )
            if active_view and active_view.type:
                view_type = active_view.type
        if not view_type:
            view_type = "card"
        CACHE.set(
            self.request.session.session_key + "pipeline",
            {
                "stages": GetStages.filter_class(self.request.GET).qs.order_by(
                    "sequence"
                ),
                "recruitments": recruitments,
                "candidates": False,
            },
            timeout=600,
        )
        self.tabs = []
        view_perm = self.request.user.has_perm("recruitment.view_recruitment")
        stage_qs = GetStages.filter_class(self.request.GET).qs
        for rec in recruitments:
            stage_manage_perm = stage_manages(self.request.user, rec)
            tab = {}
            tab["title"] = rec
            url = reverse("recruitment-pipeline-shell", kwargs={"rec_id": rec.pk})

            if view_type == "list":
                url += f"?view={view_type}"
            tab["url"] = url

            self.query_params["view"] = view_type
            tab["badge_label"] = _("Stages")
            tab["badge"] = stage_qs.filter(recruitment_id=rec.pk).count()
            if stage_manage_perm or view_perm:
                self.tabs.append(tab)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_filter_tags"] = True

        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentPipelineContentShell(TemplateView):
    """
    Shell rendered for a single recruitment's pipeline tab - shows the
    recruitment-level actions (previously the tab bar's own kebab) above
    an htmx-loaded embed of the existing list/kanban content, so the tab
    bar itself can drop its per-tab actions dropdown.
    """

    template_name = "cbv/pipeline/recruitment_pipeline_shell.html"

    def dispatch(self, request, *args, **kwargs):
        rec_id = kwargs.get("rec_id")
        if not models.Recruitment.objects.entire().filter(id=rec_id).exists():
            return HorillaRedirect(
                request, message=_("No recruitment found matching the query.")
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rec = models.Recruitment.objects.entire().get(pk=self.kwargs.get("rec_id"))
        view_type = self.request.GET.get("view")
        content_url = reverse("candidate-card-cbv", kwargs={"pk": rec.pk})
        if view_type == "list":
            content_url = (
                reverse("get-stages-recruitment", kwargs={"rec_id": rec.pk})
                + f"?view={view_type}"
            )
        context["actions"] = recruitment_pipeline_actions(self.request, rec)
        context["content_url"] = content_url
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class GetStages(TemplateView):
    """
    GetStages
    """

    filter_class = filters.StageFilter

    template_name = "cbv/pipeline/stages.html"
    stages = None

    def get(self, request, *args, **kwargs):
        """
        get method
        """
        rec_id = kwargs["rec_id"]
        cache = CACHE.get(request.session.session_key + "pipeline")
        if cache is None:
            cache = {
                "stages": self.filter_class(request.GET).qs.order_by("sequence"),
                "candidates": False,
            }
            CACHE.set(request.session.session_key + "pipeline", cache, timeout=600)
        if not cache.get("candidates"):
            cache["candidates"] = CandidateList.filter_class(
                self.request.GET
            ).qs.filter(is_active=True)
            # Same 600s as the write above: re-setting without it made the
            # entry immortal.
            CACHE.set(request.session.session_key + "pipeline", cache, timeout=600)

        self.stages = cache["stages"].filter(recruitment_id=rec_id)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stages_list = list(self.stages)
        cache_key = self.request.session.session_key + "pipeline"
        cache = CACHE.get(cache_key) or {}
        candidates_qs = cache.get("candidates")
        if candidates_qs is False or candidates_qs is None:
            candidates_qs = CandidateList.filter_class(self.request.GET).qs.filter(
                is_active=True
            )

        from django.db.models import Count

        counts = (
            candidates_qs.filter(stage_id__in=[s.id for s in stages_list])
            .values("stage_id")
            .annotate(total=Count("id"))
        )
        count_map = {item["stage_id"]: item["total"] for item in counts}
        for stage in stages_list:
            stage.candidate_count = count_map.get(stage.id, 0)

        context["stages"] = stages_list
        context["total_candidates"] = sum(
            stage.candidate_count for stage in stages_list
        )
        context["view_id"] = get_short_uuid(6, "hsv")
        context["rec_id"] = kwargs["rec_id"]
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidateList(HorillaListView):
    """
    CandidateList
    """

    model = models.Candidate
    filter_class = filters.CandidateFilter
    filter_selected = False
    quick_export = False
    next_prev = False
    show_filter_tags = True
    filter_keys_to_remove = ["rec_id", "obj_id"]
    records_per_page = 10
    records_count_in_tab = False

    custom_empty_template = "cbv/pipeline/empty.html"
    header_attrs = {
        "mobile": """ style="width:100px;" """,
        "Stage": """ style="width:100px;" """,
        "get_interview_count": """ style="width:200px;" """,
        "option": """ style="width:280px !important" """,
    }
    columns = [
        (_("Name"), "candidate_name", "get_avatar"),
        (_("Email"), "mail_indication"),
        (_("Stage"), "stage_drop_down"),
        (_("Rating"), "rating_bar"),
        (_("Hired Date"), "hired_date"),
        (_("Scheduled Interview"), "get_interview_count"),
        (_("Job Position"), "job_position_id__job_position"),
        (_("Contact"), "mobile"),
    ]

    export_columns = [
        (_("Name"), "candidate_name", "get_avatar"),
        (_("Email"), "mail_indication"),
        (_("Stage"), "stage_id"),
        (_("Rating"), "get_avg_rating"),
        (_("Hired Date"), "hired_date"),
        (_("Scheduled Interview"), "get_total_interview"),
        (_("Job Position"), "job_position_id__job_position"),
        (_("Contact"), "mobile"),
    ]

    default_columns = [
        (_("Name"), "candidate_name", "get_avatar"),
        (_("Email"), "mail_indication"),
        (_("Stage"), "stage_drop_down"),
    ]

    bulk_update_fields = [
        "stage_id",
        "hired_date",
    ]

    row_attrs = """
        class="cursor-pointer"
        onclick="window.location.href = '{get_profile_url}?next=' + encodeURIComponent(window.location.pathname + window.location.search)"
    """

    actions = [
        {
            "action": _("Schedule Interview"),
            "icon": "time-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                hx-get = "{get_schedule_interview}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
            """,
        },
        {
            "action": _("Send Mail"),
            "icon": "mail-open-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                hx-get = "{get_send_mail}"
                data-toggle="oh-modal-toggle"
                data-target="#objectDetailsModal"
                hx-target="#objectDetailsModalTarget"
            """,
        },
        {
            "action": _("Add to Talent Pool"),
            "icon": "heart-circle-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm disabled"
                data-toggle="oh-modal-toggle"
                hx-get="{get_skill_zone_url}"
                data-target="#genericModal"
                hx-target="#genericModalBody"
            """,
        },
        {
            "action": _("Reject Candidate"),
            "icon": "thumbs-down-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                data-toggle="oh-modal-toggle"
                hx-get="{get_rejected_candidate_url}"
                {rejected_candidate_class}
                data-target="#genericModal"
                hx-target="#genericModalBody"
            """,
        },
        {
            "action": _("View Note"),
            "icon": "newspaper-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm oh-activity-sidebar__open"
                hx-get="{get_view_note_url}"
                data-target="#activitySidebar"
                hx-target="#activitySidebar"
                onclick="$('#activitySidebar').addClass('oh-activity-sidebar--show')"
            """,
        },
        {
            "action": _("Document Request"),
            "icon": "document-attach-outline",
            "attrs": """
                hx-get="{get_document_request}"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                data-toggle="oh-modal-toggle"
            """,
        },
        {
            "action": _("Resume"),
            "icon": "document-outline",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                href="{get_resume_url}" target="_blank"
            """,
        },
    ]

    def get_bulk_form(self):
        form = super().get_bulk_form()
        form.fields["stage_id"].queryset = form.fields["stage_id"].queryset.filter(
            recruitment_id=self.kwargs["rec_id"]
        )
        return form

    def bulk_update_accessibility(self):
        """
        Bulk Update accessiblity
        """
        if not self.kwargs.get("stage_id"):
            return super().bulk_update_accessibility()
        first_cand_in_stage = self.queryset.first()
        return super().bulk_update_accessibility() or (
            first_cand_in_stage
            and (
                self.request.user.employee_get
                in first_cand_in_stage.stage_id.stage_managers.all()
                or self.request.user.employee_get
                in first_cand_in_stage.recruitment_id.recruitment_managers.all()
            )
        )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = self.request.path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.bulk_update_accessibility():
            context["actions"] = []
        return context

    def get(self, request, *args, **kwargs):
        self.selected_instances_key_id = f"selectedCandidateRecords{kwargs['stage_id']}"
        return super().get(request, *args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        if self.queryset is None:
            cache_key = self.request.session.session_key + "pipeline"
            cache = CACHE.get(cache_key)
            if cache is None:
                cache = {
                    "stages": filters.StageFilter(self.request.GET).qs.order_by(
                        "sequence"
                    ),
                    "candidates": False,
                }
            if not cache.get("candidates"):
                cache["candidates"] = self.filter_class(self.request.GET).qs.filter(
                    is_active=True
                )
            CACHE.set(cache_key, cache, timeout=600)

            queryset = cache["candidates"].filter(stage_id=self.kwargs["stage_id"])
            super().get_queryset(queryset=queryset, filtered=True)

        return self.queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidateCard(HorillaKanbanView):
    model = models.Candidate
    filter_class = filters.CandidateFilter
    group_filter_class = filters.StageFilter
    group_key = "stage_id"
    records_per_page = 10
    filter_keys_to_remove = ["rec_id", "obj_id"]
    group_label_key = "stage"

    kanban_attrs = """
        onclick="window.location.href = '{get_profile_url}?next=' + encodeURIComponent(window.location.pathname + window.location.search)"
    """

    details = {
        "image_src": "{get_avatar}",
        "title": "{get_full_name}",
        "email": "{email}",
        "position": "{job_position_id__job_position}",
    }

    group_actions = [
        {
            "action": _("Add Candidate"),
            "accessibility": "recruitment.accessibility.add_candidate_accessibility",
            "attrs": """
                hx-target="#objectCreateModalTarget"
                hx-get="{get_add_candidate_url}"
                data-toggle="oh-modal-toggle"
                data-target="#objectCreateModal"
            """,
        },
        {
            "action": _("Edit"),
            "accessibility": "recruitment.accessibility.edit_stage_accessibility",
            "attrs": """
                hx-target="#genericModalBody"
                hx-get="{get_stage_update_url}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
            """,
        },
        {
            "action": _("Bulk Mail"),
            "accessibility": "recruitment.accessibility.edit_stage_accessibility",
            "attrs": """
                hx-target="#objectCreateModalTarget"
                hx-get="{get_send_email_url}"
                data-toggle="oh-modal-toggle"
                data-target="#objectCreateModal"
            """,
        },
        {
            "action": _("Delete"),
            "accessibility": "recruitment.accessibility.delete_stage_accessibility",
            "attrs": """
                hx-target="#deleteConfirmationBody"
                hx-get="{get_delete_url}"
                data-toggle="oh-modal-toggle"
                data-target="#deleteConfirmation"
            """,
        },
    ]

    actions = [
        {
            "action": _("Schedule Interview"),
            "attrs": """
                hx-get = "{get_schedule_interview}"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
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
            "action": "Add to Talent Pool",
            "accessibility": "recruitment.cbv.accessibility.add_skill_zone",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_skill}"
                hx-target="#genericModalBody"
                class="oh-dropdown__link"

            """,
        },
        {
            "action": "View candidate self tracking",
            "accessibility": "recruitment.cbv.accessibility.check_candidate_self_tracking",
            "attrs": """
                href="{get_self_tracking_url}"
                class="oh-dropdown__link"
            """,
        },
        {
            "action": "Request Document",
            "accessibility": "recruitment.cbv.accessibility.request_document",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_document_request_doc}"
                hx-target="#genericModalBody"
                class="oh-dropdown__link"
            """,
        },
        {
            "action": "Add to Rejected",
            "accessibility": "recruitment.cbv.accessibility.add_reject",
            "attrs": """
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_reject}"
                class="oh-dropdown__link"
            """,
        },
        {
            "action": "Edit Rejected Candidate",
            "accessibility": "recruitment.cbv.accessibility.edit_reject",
            "attrs": """
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_reject}"
                class="oh-dropdown__link"
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
            "action": _("Resume"),
            "attrs": """
                href="{get_resume_url}" target="_blank"
            """,
        },
        {
            "action": "archive_status",
            "attrs": """
                class="oh-dropdown__link"
                onclick="archiveCandidate({get_archive_url});"
            """,
        },
        {
            "action": "Delete",
            "attrs": """
                class="oh-dropdown__link oh-dropdown__link--danger"
                onclick="event.stopPropagation();
                deleteCandidate('{get_delete_url}'); "
            """,
        },
    ]

    def get_related_groups(self, *args, **kwargs):
        related_groups = super().get_related_groups(*args, **kwargs)
        rec_id = self.kwargs.get("pk")
        if rec_id:
            related_groups = related_groups.filter(recruitment_id=rec_id)

        return related_groups


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class PipelineNav(HorillaNavView):
    """
    HorillaNavView
    """

    search_url = reverse_lazy("cbv-pipeline-tab")
    nav_title = _("Pipeline")
    search_swap_target = "#pipelineContainer"
    filter_body_template = "cbv/pipeline/pipeline_filter.html"
    filter_instance = filters.RecruitmentFilter()
    filter_form_context_name = "form"
    apply_first_filter = False
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. The three underlying filters
    # (RecruitmentFilter/StageFilter/CandidateFilter) each carry their own
    # ajax_fields for the FK/M2M pickers this combined panel renders.
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.request.user.has_perm("recruitment.add_recruitment"):
            self.create_attrs = f"""
                hx-get="{reverse_lazy('recruitment-create')}?{urlencode({'pipeline': 'true'})}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """
        else:
            self.create_attrs = None

        rec_id = self.request.GET.get("obj_id", "")
        id_suffix = f"&obj_id={rec_id}" if rec_id else ""
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse_lazy("cbv-pipeline-tab")}?view=list{id_suffix}',
                "attrs": f"""
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse_lazy("cbv-pipeline-tab")}?view=card{id_suffix}',
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
        stage_filter_obj = GetStages.filter_class()
        candidate_filter_obj = CandidateList.filter_class()
        context["stage_filter_obj"] = stage_filter_obj
        context["candidate_filter_obj"] = candidate_filter_obj
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class ChangeStage(HorillaFormView):
    """
    Change Candidate stage
    """

    model = models.Candidate
    form_class = forms.StageChangeForm

    def form_valid(self, form):
        if form.is_valid():
            messages.success(self.request, _("Stage Updated"))
            form.save()
            return self.HttpResponse()
        messages.info(self.request, _("Stage not updated"))

        return self.HttpResponse()
