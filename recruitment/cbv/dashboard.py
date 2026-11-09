"""
Dashboard of recruitment
"""

from typing import Any

from django.db.models import Count, Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import JobRoleFilter
from base.models import JobPosition
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import HorillaListView
from recruitment.cbv_decorators import manager_can_enter
from recruitment.filters import CandidateFilter, RecruitmentFilter, SkillZoneFilter
from recruitment.models import Candidate, Recruitment, SkillZone


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class SkillZoneStatusList(HorillaListView):
    """
    List view for talent pool status in recruitment dashboard
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("skill-zone-status-dashboard")

    model = SkillZone
    filter_class = SkillZoneFilter
    columns = [
        (_("Talent Pool"), "title", "get_avatar"),
        (_("No. of Candidates"), "candidate_count_display"),
    ]
    bulk_select_option = False
    show_toggle_form = False

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(is_active=True)
        return queryset

    row_attrs = """
                onclick = "window.location.href='{get_skill_zone_url}'"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CandidateOnOnboardList(HorillaListView):
    """
    List view for candidate on onboard in recruitment dashboard
    """

    model = Candidate
    filter_class = CandidateFilter
    bulk_select_option = False
    show_toggle_form = False

    columns = [
        (_("Candidates"), "name", "get_avatar"),
        (_("Job Position"), "job_position_id"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(start_onboard=True)
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("candidate-on-onboard-dashboard")


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class CurrentHiringList(HorillaListView):
    """
    List view for hiring in each job position in dashboard
    """

    model = JobPosition
    filter_class = JobRoleFilter
    bulk_select_option = False
    records_per_page = 10

    columns = [
        (_("Job Positions"), "job_position"),
        (_("Initial"), "initial_count"),
        (_("Test"), "test_count"),
        (_("Interview"), "interview_count"),
        (_("Hired"), "hired_count"),
        (_("Cancelled"), "cancelled_count"),
    ]

    header_attrs = {
        "job_position": """ style = "width:100px !important " """,
        "initial_count": """ style = "width:55px !important" """,
        "test_count": """ style = "width:55px !important;" """,
        "interview_count": """ style = "width:60px !important" """,
        "hired_count": """ style = "width:55px !important" """,
        "cancelled_count": """ style = "width:65px !important" """,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.annotate(
            initial_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="initial")
            ),
            test_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="test")
            ),
            interview_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="interview")
            ),
            hired_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="shortlisted")
            ),
            cancelled_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="cancelled")
            ),
        )
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("current-hiring-pipeline-dashboard")


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class OnGoingRecruitmentList(HorillaListView):
    """
    List view for ongoing recruitment and its managers in  dashboard
    """

    model = Recruitment
    filter_class = RecruitmentFilter
    bulk_select_option = False
    show_toggle_form = False

    columns = [
        (_("Recruitment"), "title"),
        (_("Managers"), "managers"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(closed=False)
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("ongoing-recruitment-dashboard")
