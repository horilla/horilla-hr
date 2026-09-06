"""
This page handles the cbv methods for canidate profile page
"""

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from employee.cbv.employee_profile import EmployeeProfileView
from horilla import settings
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import HorillaListView, HorillaProfileView
from onboarding.filters import CandidateTaskFilter
from onboarding.models import CandidateTask
from recruitment.cbv import skill_zone
from recruitment.cbv.candidate_document import CandidateDocumentListView
from recruitment.cbv.candidate_mail_log import CandidateMailLogTabList
from recruitment.cbv_decorators import all_manager_can_enter
from recruitment.filters import CandidateFilter
from recruitment.models import Candidate
from recruitment.views import views


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_candidate"), name="dispatch"
)
class CandidateProfileView(HorillaProfileView):
    """
    Candidate ProfileView
    """

    model = Candidate
    filter_class = CandidateFilter
    push_url = "candidate-view-individual"
    key_name = "cand_id"

    def dispatch(self, request, *args, **kwargs):
        # This endpoint returns only the profile fragment; direct browser opens should
        # land on the full candidate page that loads this fragment via HTMX.
        if request.META.get("HTTP_HX_REQUEST") != "true":
            candidate_id = kwargs.get("pk")
            redirect_url = reverse(
                "candidate-view-individual", kwargs={"cand_id": candidate_id}
            )
            query_string = request.GET.urlencode()
            if query_string:
                redirect_url = f"{redirect_url}?{query_string}"
            return redirect(redirect_url)
        return super().dispatch(request, *args, **kwargs)

    actions = [
        {
            "title": _("Edit"),
            "src": f"/{settings.STATIC_URL}images/ui/edit_btn.png",
            "attrs": """
                        onclick="
                        event.preventDefault();
                        window.location.href='{get_update_url}' "
                    """,
        },
        {
            "title": _("View candidate self tracking"),
            "src": f"/{settings.STATIC_URL}images/ui/exit-outline.svg",
            "accessibility": "recruitment.cbv.accessibility.view_candidate_self_tracking",
            "attrs": """
                href="{get_self_tracking_url}"
                class="oh-dropdown__link"
            """,
        },
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_candidate"), name="dispatch"
)
class CandidateProfileTasks(HorillaListView):
    """
    CandidateProfileTasks
    """

    custom_empty_template = "onboarding/empty_task.html"
    model = CandidateTask
    template_name = "cbv/candidates/onboarding_tasks_tab.html"
    show_filter_tags = False
    filter_class = CandidateTaskFilter
    filter_selected = False
    selected_instances_key_id = "selectedInstanceIds"
    bulk_update_fields = [
        "status",
    ]

    def dispatch(self, request, *args, **kwargs):
        # No matching candidate (e.g. a stale/invalid pk) -- render nothing
        # rather than a "None's Onboarding Tasks" page with the raw,
        # unstyled list+export+column-picker fragment underneath it.
        if not Candidate.objects.filter(id=kwargs.get("pk")).exists():
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def bulk_update_accessibility(self):
        return (
            super().bulk_update_accessibility()
            or self.request.user.employee_get.onboardingstage_set.filter(
                candidate__candidate_id__pk=self.kwargs["pk"]
            ).exists()
        )

    columns = [
        (_("Task"), "onboarding_task_id__task_title"),
        (_("Status"), "status_col"),
        (
            _("Modified By"),
            "modified_by__employee_get__get_full_name",
            "modified_by__employee_get__get_avatar",
        ),
    ]

    sortby_mapping = [
        (_("Task"), "onboarding_task_id__task_title"),
        (_("Status"), "status"),
        (_("Modified By"), "modified_by__employee_get__get_full_name"),
    ]

    header_attrs = {
        "status_col": """
        style="width:180px!important;"
"""
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = self.request.path
        # Fixed (not auto-random) so pagination/sort/search requests - which
        # all hx-target="#{{view_id}}" from generic/horilla_list_table.html -
        # can be recognized in get_template_names() below and answered with
        # just that fragment. Without this, every such request re-renders the
        # full tab (title header included) and htmx's outerHTML swap dumps
        # that whole response in place of the table, duplicating the header
        # on each page/sort/search click.
        self.view_id = "candidateOnboardingTaskList"

    def get_template_names(self):
        if self.request.headers.get("HX-Target") == self.view_id:
            return ["generic/horilla_list_table.html"]
        return [self.template_name]

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        self.queryset = (
            super()
            .get_queryset(queryset, filtered, *args, **kwargs)
            .filter(candidate_id__pk=self.kwargs["pk"])
        )
        return self.queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["candidate"] = Candidate.objects.filter(
            id=self.kwargs.get("pk")
        ).first()
        return context


CandidateProfileView.add_tab(
    tabs=[
        {
            "title": _("About"),
            "view": views.candidate_about_tab,
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Resume"),
            "view": views.candidate_resume_tab,
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Survey"),
            "view": views.candidate_survey_tab,
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Documents"),
            "view": CandidateDocumentListView.as_view(),
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Notes"),
            "view": views.add_note,
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("History"),
            "view": views.candidate_history_tab,
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Rating"),
            "view": views.candidate_rating_tab,
            "accessibility": "recruitment.cbv.accessibility.rating_accessibility",
        },
        {
            "title": _("Onboarding"),
            "view": CandidateProfileTasks.as_view(),
            "accessibility": "recruitment.cbv.accessibility.onboarding_accessibility",
        },
        {
            "title": _("Mail Log"),
            # "view": views.get_mail_log
            "view": CandidateMailLogTabList.as_view(),
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
        {
            "title": _("Scheduled Interviews"),
            "view": views.candidate_interview_tab,
            "accessibility": "recruitment.cbv.accessibility.empl_scheduled_interview_accessibility",
        },
        {
            "title": _("Talent Pool"),
            "view": skill_zone.SkillZoneProfileListView.as_view(),
            "accessibility": "recruitment.cbv.accessibility.if_manager_accessibility",
        },
    ]
)


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Scheduled Interviews"),
            "view": views.scheduled_interview_tab,
            "accessibility": "recruitment.cbv.accessibility.empl_scheduled_interview_accessibility",
        },
    ]
)
