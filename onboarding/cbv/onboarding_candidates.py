"""
Onboarding candidate view.
"""

from typing import Any

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.models import HorillaMailTemplate
from employee.cbv.employee_profile import EmployeeProfileView
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from onboarding.filters import CandidateTaskFilter
from onboarding.models import CandidateTask
from recruitment.cbv.candidate_profile import CandidateProfileView
from recruitment.cbv_decorators import all_manager_can_enter
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
        ).filter(Q(hired=True) | Q(stage_id__stage_type="shortlisted"))
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
                .filter(Q(hired=True) | Q(stage_id__stage_type="shortlisted"))
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

    nav_title = _("Shortlisted Candidates")
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
                    id="send-port"
                    """,
        }
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
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
    show_toggle_form = False

    def dispatch(self, request, *args, **kwargs):
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
    {
        "title": _("Onboarding"),
        "view": CandidateProfileTasks.as_view(),
        "accessibility": "recruitment.cbv.accessibility.onboarding_accessibility",
    },
)


class EmployeeOnboardingTasks(CandidateProfileTasks):
    """
    Onboarding tasks tab on the employee profile, resolved through the candidate
    the employee was converted from.
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Swap the employee pk in the URL for the linked candidate's pk.

        Parameters:
        request (HttpRequest): The HTTP request object.
        kwargs : URL kwargs carrying the employee pk.

        Returns:
        HttpResponse : the candidate tasks list, or an empty page if the employee has no linked candidate.
        """
        candidate = Candidate.objects.filter(
            converted_employee_id__pk=kwargs.get("pk")
        ).first()
        if not candidate:
            return render(request, "onboarding/employee_no_onboarding.html")
        kwargs["pk"] = candidate.pk
        self.kwargs["pk"] = candidate.pk
        if request.user == candidate.converted_employee_id.employee_user_id:
            return super(CandidateProfileTasks, self).dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


EmployeeProfileView.add_tab(
    {
        "title": _("Onboarding"),
        "view": EmployeeOnboardingTasks.as_view(),
        "accessibility": "employee.cbv.accessibility.onboarding_accessibility",
    },
)
