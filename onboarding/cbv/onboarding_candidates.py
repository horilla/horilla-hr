"""
Onboarding candidate view.
"""

from typing import Any

from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.models import HorillaMailTemplate
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from recruitment.filters import CandidateFilter
from recruitment.models import Candidate


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_candidate"), name="dispatch"
)
class OnboardingCandidatesView(TemplateView):
    """
    onboarding candidates view
    """

    template_name = "cbv/onboarding_candidates/onboarding_candidates.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        hired_candidates = Candidate.objects.filter(
            is_active=True,
            recruitment_id__closed=False,
        ).filter(Q(hired=True) | Q(stage_id__stage_type="hired"))
        mail_templates = HorillaMailTemplate.objects.all()
        context["mail_templates"] = mail_templates
        context["hired_candidates"] = hired_candidates
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_candidate"), name="dispatch"
)
class OnboardingCandidatesList(HorillaListView):
    """
    List view
    """

    bulk_update_fields = [
        "joining_date",
        "probation_end",
        "job_position_id",
        "recruitment_id",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("onboarding-candidates-list")

    def get_queryset(self):
        if not getattr(self, "queryset"):
            queryset = super().get_queryset()
            self.queryset = (
                queryset.filter(
                    is_active=True,
                    recruitment_id__closed=False,
                )
                .filter(Q(hired=True) | Q(stage_id__stage_type="hired"))
                .distinct()
            ).order_by("-id")

        return self.queryset

    model = Candidate
    filter_class = CandidateFilter

    columns = [
        (_("Candidate"), "name", "get_avatar"),
        (_("Email"), "last_email"),
        (_("Date of joining"), "date_of_joining"),
        (_("Probation ends"), "probation_date"),
        (_("Job position"), "job_position_id"),
        (_("Recruitment"), "recruitment_id"),
        (_("Offer letter"), "offer_letter"),
    ]
    header_attrs = {
        "date_of_joining": "style='width: 190px;'",
        "probation_date": "style='width: 190px;'",
        "action": "style='width: 260px;'",
    }

    action_method = "actions"

    row_status_indications = [
        (
            "joining--dot",
            _("Joining Set"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=joining_set]').val('true');
                $('[name=portal_sent]').val('unknown').change();
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "not-joining--dot",
            _("Joining Not-Set"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=joining_set]').val('false');
                $('[name=portal_sent]').val('unknown').change();
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "not-portal--dot",
            _("Portal Not-Sent"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=portal_sent]').val('false');
                $('[name=joining_set]').val('unknown').change();
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "portal--dot",
            _("Portal Send"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=portal_sent]').val('true');
                $('[name=joining_set]').val('unknown').change();
                $('#applyFilter').click();

            "
            """,
        ),
    ]

    sortby_mapping = [
        (_("Candidate"), "name"),
        (_("Email"), "last_email"),
        (_("Date of joining"), "date_of_joining"),
        (_("Job position"), "job_position_id__job_position"),
        (_("Recruitment"), "recruitment_id__title"),
        (_("Probation ends"), "probation_date"),
    ]

    row_attrs = """
                onclick="
                    try {{ sessionStorage.setItem('candidateProfileFrom', 'onboarding'); }} catch (e) {{}}
                "
                hx-get="{get_profile_url}?from=onboarding&instance_ids={ordered_ids}"
                hx-target="#listContainer"
                hx-swap="innerHTML"
                hx-push-url="{get_individual_url}"
                class="cursor-pointer"
                """

    # Mirrors OnboardingCandidatesNav.nested_group_by_fields below -- List
    # and Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Talent Pool"
    # (skillzonecandidate_set__skill_zone_id) is deliberately left out,
    # same as the recruitment Candidates page: it's a reverse FK/to-many
    # relation, and the nested engine's `values(*fields).annotate(Count
    # ("pk"))` aggregate would fan out one row per related
    # SkillZoneCandidate, double-counting candidates in more than one
    # talent pool.
    nested_group_by_fields = [
        ("recruitment_id", _("Recruitment")),
        ("job_position_id", _("Job position")),
        ("country", _("Country")),
        ("stage_id", _("Stage")),
        ("joining_date", _("Joining Date")),
        ("probation_end", _("Probation End")),
        ("offer_letter_status", _("Offer Letter Status")),
        ("rejected_candidate__reject_reason_id", _("Rejected Reason")),
        ("job_position_id__department_id", _("Department")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_candidate"), name="dispatch"
)
class OnboardingCandidatesNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("onboarding-candidates-list")
        self.create_attrs = f"""
                                href="{reverse_lazy('candidate-create')}?onboarding=True"
                                """
        self.filter_instance = CandidateFilter()

    nav_title = _("Hired Candidates")
    filter_body_template = "cbv/onboarding_candidates/filter.html"
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. recruitment.filters.CandidateFilter.ajax_fields
    # already covers Recruitment/Job Position/Rejection Reason from the
    # recruitment Candidates panel work.
    modern_filter = True

    group_by_fields = [
        ("recruitment_id", _("Recruitment")),
        ("job_position_id", _("Job position")),
        ("country", _("Country")),
        ("stage_id", _("Stage")),
        ("joining_date", _("Joining Date")),
        ("probation_end", _("Probation End")),
        ("offer_letter_status", _("Offer Letter Status")),
        ("rejected_candidate__reject_reason_id", _("Rejected Reason")),
        ("skillzonecandidate_set__skill_zone_id", _("Talent Pool")),
    ]

    # Mirrors OnboardingCandidatesList.nested_group_by_fields
    nested_group_by_fields = [
        ("recruitment_id", _("Recruitment")),
        ("job_position_id", _("Job position")),
        ("country", _("Country")),
        ("stage_id", _("Stage")),
        ("joining_date", _("Joining Date")),
        ("probation_end", _("Probation End")),
        ("offer_letter_status", _("Offer Letter Status")),
        ("rejected_candidate__reject_reason_id", _("Rejected Reason")),
        ("job_position_id__department_id", _("Department")),
    ]

    actions = [
        {
            "action": _("Send Portal"),
            "attrs": """

                    data-target="#addAttachments"
                    data-toggle="oh-modal-toggle"
                    id="send-port"
                    """,
        }
    ]
