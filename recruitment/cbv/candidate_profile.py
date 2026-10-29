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
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import HorillaListView, HorillaProfileView
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

    def get_queryset(self):
        return Candidate.objects.get_queryset()

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["send_mail_url"] = reverse(
            "send-mail", kwargs={"cand_id": self.kwargs.get("pk")}
        )
        context["send_mail_modal"] = "#genericModal"
        context["send_mail_target"] = "#genericModalBody"
        return context

    def get_status_ribbon(self, instance):
        if instance.canceled:
            return {"label": _("Rejected"), "variant": "danger"}
        if not instance.is_active:
            return {"label": _("Archived"), "variant": "secondary"}

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
        {
            "title": _("Convert to Employee"),
            "accessibility": "recruitment.cbv.accessibility.profile_convert_emp",
            "attrs": """
                onclick="return confirm('Are you sure you want to convert this candidate into an employee?')"
                href="{get_convert_to_emp}"
                class="oh-dropdown__link"
            """,
        },
        {
            "title": _("Send Mail"),
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_send_mail_url}"
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                class="oh-dropdown__link"
            """,
        },
        {
            "title": _("Add to Talent Pool"),
            "accessibility": "recruitment.cbv.accessibility.profile_add_skill_zone",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_skill}"
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                class="oh-dropdown__link"
            """,
        },
        {
            "title": _("Request Document"),
            "accessibility": "recruitment.cbv.accessibility.request_document",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_document_request_doc}"
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                class="oh-dropdown__link"
            """,
        },
        {
            "title": _("Add to Rejected"),
            "accessibility": "recruitment.cbv.accessibility.add_reject",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_reject}"
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                class="oh-dropdown__link"
            """,
        },
        {
            "title": _("Edit Rejected Candidate"),
            "accessibility": "recruitment.cbv.accessibility.edit_reject",
            "attrs": """
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{get_add_to_reject}"
                hx-target="#genericModalBody"
                hx-swap="innerHTML"
                class="oh-dropdown__link"
            """,
        },
        {"divider": True},
        {
            "title": _("Archive"),
            "variant": "danger",
            "accessibility": "recruitment.cbv.accessibility.archive_perm",
            "attrs": """
                hx-post="{get_archive_action_url}"
                hx-swap="none"
                hx-confirm="Do you want to archive this candidate?"
                hx-on::after-request="window.location.reload()"
            """,
        },
        {
            "title": _("Un-archive"),
            "variant": "danger",
            "accessibility": "recruitment.cbv.accessibility.unarchive_perm",
            "attrs": """
                hx-post="{get_archive_action_url}"
                hx-swap="none"
                hx-confirm="Do you want to un-archive this candidate?"
                hx-on::after-request="window.location.reload()"
            """,
        },
        {
            "title": _("Delete"),
            "variant": "danger",
            "accessibility": "recruitment.cbv.accessibility.delete_candidate_perm",
            "attrs": """
                hx-post="{get_delete_url}"
                hx-swap="none"
                hx-confirm="Are you sure you want to delete this candidate?"
                hx-on::after-request="window.location.href='{get_list_url}'"
            """,
        },
    ]


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
