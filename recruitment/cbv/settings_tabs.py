"""
this page is handling the cbv methods for the recruitment settings page,
which lists reject reason and skill as tabs
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import HorillaTabView, TemplateView
from recruitment.models import RejectReason, Skill


@method_decorator(login_required, name="dispatch")
class RecruitmentSettingsView(TemplateView):
    """
    page for recruitment settings (Rejection Reason / Skill tabs)
    """

    template_name = "cbv/recruitment_settings/recruitment_settings_main.html"


@method_decorator(login_required, name="dispatch")
class RecruitmentSettingsTabView(HorillaTabView):
    """
    tab view for recruitment settings, shows reject reason and skill as tabs
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tabs = [
            {
                "title": _("Rejection Reasons"),
                "url": f"{reverse('recruitment-settings-reject-reason-tab')}",
                "badge": RejectReason.objects.count(),
            },
            {
                "title": _("Skills"),
                "url": f"{reverse('recruitment-settings-skill-tab')}",
                "badge": Skill.objects.count(),
            },
        ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class RecruitmentSettingsRejectReasonTab(TemplateView):
    """
    reject reason tab content, embeds the existing reject reason nav + list
    """

    template_name = "cbv/recruitment_settings/reject_reason_tab.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class RecruitmentSettingsSkillTab(TemplateView):
    """
    skill tab content, embeds the existing skills nav + list
    """

    template_name = "cbv/recruitment_settings/skill_tab.html"
