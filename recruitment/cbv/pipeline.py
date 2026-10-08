"""
recruitment/cbv/pipeline.py
"""

from typing import Any

from django.contrib import messages
from django.core.cache import cache as CACHE
from django.db.models import Count, Q
from django.http import HttpResponse as DjangoHttpResponse
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


def stage_cache_version(rec_id):
    """
    Return the cache version number for a recruitment's stages, creating it
    on first use.
    """
    key = f"stage_cache_version{rec_id}"
    version = CACHE.get(key)
    if version is None:
        version = 1
        CACHE.set(key, version, timeout=None)
    return version


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
    Return the actions (Add Stage, Edit, Resume Shortlisting, Manage Stage
    Order, Close/Reopen, Delete) the user is allowed to perform on the
    given recruitment.
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
        delete_query = urlencode(
            {
                "model": "recruitment.Recruitment",
                "pk": rec.pk,
                "redirect_url": reverse("cbv-pipeline"),
            }
        )
        actions.append(
            {
                "action": _("Delete"),
                "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#deleteConfirmation"
                    hx-get="{reverse('generic-delete')}?{delete_query}"
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
    template_name = "cbv/pipeline/recruitment_tabs.html"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        recruitments = (
            self.filter_class(self.request.GET)
            .qs.filter(is_active=True, closed=False)
            .order_by("-id")
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

        # Candidates on each recruitment's board (the same set the stage
        # columns list), not how many stages it has.
        candidate_counts = dict(
            filters.CandidateFilter(self.request.GET)
            .qs.filter(
                is_active=True,
                stage_id__recruitment_id__in=recruitments.values_list("pk", flat=True),
            )
            .values("stage_id__recruitment_id")
            .annotate(total=Count("id", distinct=True))
            .values_list("stage_id__recruitment_id", "total")
        )
        employee = getattr(self.request.user, "employee_get", None)
        if employee:
            recruitment_manager_ids = set(
                recruitments.model.recruitment_managers.through.objects.filter(
                    employee_id=employee.id,
                    recruitment_id__in=recruitments.values_list("pk", flat=True),
                ).values_list("recruitment_id", flat=True)
            )
            stage_manager_recruitment_ids = set(
                models.Stage.stage_managers.through.objects.filter(
                    employee_id=employee.id,
                    stage__recruitment_id__in=recruitments.values_list("pk", flat=True),
                ).values_list("stage__recruitment_id", flat=True)
            )
        else:
            recruitment_manager_ids = set()
            stage_manager_recruitment_ids = set()

        for rec in recruitments:
            stage_manage_perm = (
                rec.pk in stage_manager_recruitment_ids
                or rec.pk in recruitment_manager_ids
            )
            tab = {}
            tab["title"] = rec
            url = reverse("recruitment-pipeline-shell", kwargs={"rec_id": rec.pk})

            if view_type == "list":
                url += f"?view={view_type}"
            tab["url"] = url

            self.query_params["view"] = view_type
            tab["badge_label"] = _("Candidates")
            tab["badge"] = candidate_counts.get(rec.pk, 0)
            if stage_manage_perm or view_perm:
                self.tabs.append(tab)

    show_filter_tags = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.has_perm("recruitment.add_recruitment"):
            context["tab_create_label"] = _("Create")
            context[
                "tab_create_attrs"
            ] = f"""
                hx-get="{reverse_lazy('recruitment-create')}?{urlencode({'pipeline': 'true'})}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentPipelineContentShell(TemplateView):
    """
    Render the pipeline tab of a single recruitment: its navigation bar
    and the candidate list or kanban content.
    """

    template_name = "cbv/pipeline/recruitment_pipeline_shell.html"

    def dispatch(self, request, *args, **kwargs):
        rec_id = kwargs.get("rec_id")
        if not models.Recruitment.objects.entire().filter(id=rec_id).exists():
            return HorillaRedirect(
                request, message=_("No recruitment found matching the query.")
            )
        return super().dispatch(request, *args, **kwargs)

    def saved_view_type(self, rec_id):
        """
        Return the list/card view type the user last chose for this
        recruitment, or None if there is none.
        """
        user = self.request.user
        if not (user and user.is_authenticated):
            return None
        active_view = (
            ActiveView.objects.filter(created_by=user)
            .filter(
                Q(
                    path=reverse(
                        "recruitment-pipeline-tab-nav", kwargs={"rec_id": rec_id}
                    )
                )
                | Q(path=reverse("cbv-pipeline-nav"))
            )
            .order_by("-path")
            .first()
        )
        return active_view.type if active_view else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rec = models.Recruitment.objects.entire().get(pk=self.kwargs.get("rec_id"))
        view_type = (
            self.request.GET.get("view") or self.saved_view_type(rec.pk) or "card"
        )
        content_url = reverse("candidate-card-cbv", kwargs={"pk": rec.pk})
        if view_type == "list":
            content_url = (
                reverse("get-stages-recruitment", kwargs={"rec_id": rec.pk})
                + f"?view={view_type}"
            )
        context["content_url"] = content_url
        context["rec_id"] = rec.pk
        context["nav_url"] = (
            reverse("recruitment-pipeline-tab-nav", kwargs={"rec_id": rec.pk})
            + f"?view={view_type}"
        )
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentCandidateNav(HorillaNavView):
    """
    Navigation bar of a recruitment's pipeline tab, with search, filter,
    list/card toggle, the Add candidate button and the recruitment actions.
    """

    filter_form_context_name = "form"
    filter_body_template = "cbv/candidates/filter.html"
    modern_filter = True
    apply_first_filter = True
    template_name = "generic/inline_nav.html"
    nav_title = _("Pipeline")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        rec_id = self.request.resolver_match.kwargs.get("rec_id")
        view_type = self.request.GET.get("view")
        if view_type == "list":
            self.search_url = (
                reverse("get-stages-recruitment", kwargs={"rec_id": rec_id})
                + f"?view={view_type}"
            )
        else:
            self.search_url = reverse("candidate-card-cbv", kwargs={"pk": rec_id})
        self.search_swap_target = f"#pipelineTabContent{rec_id}"
        self.filter_instance = filters.CandidateFilter()

        rec = models.Recruitment.objects.filter(pk=rec_id).first()
        if rec and (
            self.request.user.has_perm("recruitment.add_candidate")
            or self.request.user.has_perm("recruitment.change_recruitment")
            or recruitment_manages(self.request.user, rec)
        ):
            self.create_label = _("Add")
            self.create_attrs = f"""
                hx-get="{reverse_lazy('add-candidate-to-stage')}?{urlencode({'rec_id': rec_id})}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": (
                    reverse("get-stages-recruitment", kwargs={"rec_id": rec_id})
                    + "?view=list"
                ),
                "attrs": """
                    title ='List'
                """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("candidate-card-cbv", kwargs={"pk": rec_id}),
                "attrs": """
                    title ='Card'
                """,
            },
        ]

        if rec:
            self.actions = recruitment_pipeline_actions(self.request, rec)


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

    @staticmethod
    def cache_key_for(session_key, rec_id, querystring=""):
        """
        Return the cache key for one recruitment's stages, built from the
        session, recruitment id, query string and stage cache version.
        """
        return (
            f"{session_key}pipeline{rec_id}{querystring}"
            f"v{stage_cache_version(rec_id)}"
        )

    def get(self, request, *args, **kwargs):
        """
        get method
        """
        rec_id = kwargs["rec_id"]
        cache_key = self.cache_key_for(
            request.session.session_key, rec_id, request.GET.urlencode()
        )
        cache = CACHE.get(cache_key)
        if cache is None:
            cache = {
                "stages": self.filter_class(request.GET).qs.order_by("sequence"),
                "candidates": False,
            }
            CACHE.set(cache_key, cache, timeout=600)
        if not cache.get("candidates"):
            cache["candidates"] = CandidateList.filter_class(
                self.request.GET
            ).qs.filter(is_active=True)
            CACHE.set(cache_key, cache, timeout=600)

        self.stages = cache["stages"].filter(recruitment_id=rec_id)
        self._candidates_qs = cache.get("candidates")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stages_list = list(self.stages)
        candidates_qs = getattr(self, "_candidates_qs", None)
        if candidates_qs is False or candidates_qs is None:
            candidates_qs = CandidateList.filter_class(self.request.GET).qs.filter(
                is_active=True
            )

        stage_ids = [s.id for s in stages_list]
        counts = (
            candidates_qs.filter(stage_id__in=stage_ids)
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
    template_name = "cbv/pipeline/candidate_list.html"

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
        context["stage"] = models.Stage.objects.filter(
            pk=self.kwargs.get("stage_id")
        ).first()
        if hasattr(context["queryset"], "object_list"):
            context["queryset"].object_list = list(context["queryset"].object_list)
            self._attach_last_sent_mail(context["queryset"].object_list)
        else:
            self._attach_last_sent_mail(list(context["queryset"]))
        return context

    @staticmethod
    def _attach_last_sent_mail(candidates: list) -> None:
        """
        Attach the latest sent email log to each candidate, using a single
        query for all of them.
        """
        from base.models import EmailLog

        if not candidates:
            return
        emails = {candidate.email for candidate in candidates if candidate.email}
        if not emails:
            return
        email_q = Q()
        for email in emails:
            email_q |= Q(to__icontains=email)
        logs_newest_first = EmailLog.objects.filter(email_q).order_by("-created_at")
        latest_by_email = {}
        for log in logs_newest_first:
            for email in emails:
                if email in latest_by_email:
                    continue
                if email in log.to:
                    latest_by_email[email] = log
        for candidate in candidates:
            candidate.get_last_sent_mail = latest_by_email.get(candidate.email)

    def get(self, request, *args, **kwargs):
        self.selected_instances_key_id = f"selectedCandidateRecords{kwargs['stage_id']}"
        return super().get(request, *args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        if self.queryset is None:
            rec_id = self.kwargs.get("rec_id")
            cache_key = (
                GetStages.cache_key_for(
                    self.request.session.session_key,
                    rec_id,
                    self.request.GET.urlencode(),
                )
                if rec_id
                else self.request.session.session_key + "pipeline"
            )
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

            queryset = (
                cache["candidates"]
                .filter(stage_id=self.kwargs["stage_id"])
                .select_related(
                    "stage_id",
                    "stage_id__recruitment_id",
                    "recruitment_id",
                    "job_position_id",
                )
                .annotate(interview_count=Count("candidate_interview", distinct=True))
            )
            super().get_queryset(queryset=queryset, filtered=True)

        return self.queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidateCard(HorillaKanbanView):
    model = models.Candidate
    # The tab badge counts candidates (set server-side), not stage columns
    records_count_in_tab = False
    filter_class = filters.CandidateFilter
    group_filter_class = filters.StageFilter
    group_key = "stage_id"
    records_per_page = 10
    filter_keys_to_remove = ["rec_id", "obj_id"]
    group_label_key = "stage"
    empty_group_label = _("stages")

    kanban_attrs = """
        onclick="window.location.href = '{get_profile_url}?next=' + encodeURIComponent(window.location.pathname + window.location.search)"
    """

    details = {
        "image_src": "{get_avatar}",
        "title": "{get_full_name}",
        "email": "{email}",
        "position": "{job_position_id__job_position}",
    }

    group_actions = []

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

    nav_title = _("Pipeline")
    search_swap_target = "#pipelineContainer"
    filter_body_template = "cbv/pipeline/pipeline_filter.html"
    filter_instance = filters.RecruitmentFilter()
    filter_form_context_name = "form"
    apply_first_filter = False
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
        if not form.is_valid():
            messages.info(self.request, _("Stage not updated"))
            return self.HttpResponse()

        messages.success(self.request, _("Stage Updated"))
        previous_stage_id = (
            models.Candidate.objects.filter(pk=form.instance.pk)
            .values_list("stage_id", flat=True)
            .first()
        )
        candidate = form.save()
        return self.reload_stages_response({previous_stage_id, candidate.stage_id_id})

    def reload_stages_response(self, stage_ids):
        """
        Build the response returned after a candidate's stage is changed.

        The response script reloads the candidate tables of the given stages,
        refreshes the messages area and closes the open modal.

        Args:
            stage_ids: ids of the stages whose candidate lists changed
                (the one the candidate left and the one it moved to).
        """
        selectors = ",".join(
            f'[data-list-path*="/candidate-lists-cbv/{stage_id}/"]'
            for stage_id in sorted(filter(None, stage_ids))
        )
        script_id = get_short_uuid(4, "chgstage")
        reload_scoped = (
            f"$('{selectors}').find('.reload-record').click();" if selectors else ""
        )
        return DjangoHttpResponse(
            f"<script id='{script_id}'>"
            "$('#reloadMessagesButton').click();"
            f"$('#{script_id}').closest('.oh-modal--show').first()"
            ".removeClass('oh-modal--show');"
            f"{reload_scoped}"
            "</script>"
        )
