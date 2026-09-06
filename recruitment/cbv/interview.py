"""
this page handles cbv of interview page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import resolve, reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify
from recruitment.decorators import manager_can_enter, recruitment_manager_can_enter
from recruitment.filters import InterviewFilter
from recruitment.forms import ScheduleInterviewForm
from recruitment.models import Candidate, InterviewSchedule


@method_decorator(login_required, name="dispatch")
@method_decorator(
    recruitment_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class InterviewViewPage(TemplateView):
    """
    for interview page
    """

    template_name = "cbv/interview/interview_home_view.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    recruitment_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class InterviewNavView(HorillaNavView):
    """
    nav bar of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("interview-list-view")

        if self.request.user.has_perm("recruitment.add_interviewschedule"):
            self.create_attrs = f"""
                hx-get="{reverse_lazy("create-interview-schedule")}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """
        else:
            self.create_attrs = None

    nav_title = _("Scheduled Interviews")
    filter_instance = InterviewFilter()
    filter_body_template = "cbv/interview/interview_filter.html"
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. InterviewFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    # Mirrors InterviewLIstView.nested_group_by_fields
    nested_group_by_fields = [
        ("candidate_id", _("Candidate")),
        ("interview_date", _("Interview Date")),
        ("interview_time", _("Interview Time")),
        ("completed", _("Is Interview Completed")),
        ("candidate_id__recruitment_id", _("Recruitment")),
        ("candidate_id__job_position_id", _("Job Position")),
        ("candidate_id__job_position_id__department_id", _("Department")),
        ("candidate_id__stage_id", _("Stage")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    recruitment_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class InterviewLIstView(HorillaListView):
    """
    list view of the page
    """

    bulk_update_fields = ["employee_id", "interview_date", "interview_time"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("interview-list-view")
        self.view_id = "interviewdelete"

    def get_queryset(self):
        """
        Override queryset based on user permissions.

        Returns:
            queryset: Filtered queryset based on user permissions and employee ID.
        """
        queryset = super().get_queryset()
        if self.request.user.has_perm("recruitment.view_interviewschedule"):
            queryset = queryset.all().order_by("-interview_date")
        else:
            queryset = queryset.filter(
                employee_id=self.request.user.employee_get.id
            ).order_by("-interview_date")

        return queryset

    filter_class = InterviewFilter
    model = InterviewSchedule
    template_name = "cbv/interview/inherit_script.html"

    columns = [
        (_("Candidate"), "candidate_custom_col"),
        (_("Interviewer"), "interviewer_custom_col"),
        (_("Interview Date"), "interview_date"),
        (_("Interview Time"), "interview_time"),
        (_("Description"), "get_description"),
        (_("Status"), "status_custom_col"),
    ]
    header_attrs = {
        "candidate_custom_col": """
                                style="width:200px !important;"
                                """
    }

    sortby_mapping = [
        (_("Interview Date"), "interview_date"),
        (_("Interview Time"), "interview_time"),
    ]
    action_method = "custom_action_col"

    row_attrs = """
                {custom_color}
                class="oh-permission-table--collapsed"
                hx-get='{detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    # Mirrors InterviewNavView.nested_group_by_fields below -- List and
    # Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Interviewer"
    # (employee_id) is deliberately left out: it's a ManyToManyField, and
    # the nested engine's `values(*fields).annotate(Count("pk"))`
    # aggregate would fan out one row per interviewer, double-counting
    # interviews with more than one interviewer assigned.
    nested_group_by_fields = [
        ("candidate_id", _("Candidate")),
        ("interview_date", _("Interview Date")),
        ("interview_time", _("Interview Time")),
        ("completed", _("Is Interview Completed")),
        ("candidate_id__recruitment_id", _("Recruitment")),
        ("candidate_id__job_position_id", _("Job Position")),
        ("candidate_id__job_position_id__department_id", _("Department")),
        ("candidate_id__stage_id", _("Stage")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    recruitment_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class InterviewDetailView(HorillaDetailedView):
    """
    detailed view
    """

    model = InterviewSchedule
    title = _("Details")
    header = {
        "title": "candidate_id__get_full_name",
        "subtitle": "detail_subtitle",
        "avatar": "candidate_id__get_avatar",
    }
    body = [
        (_("Candidate"), "candidate_id"),
        (_("Interviewer"), "interviewer_detail"),
        (_("Interview Date"), "interview_date"),
        (_("Interview Time"), "interview_time"),
        (_("Description"), "get_description"),
        (_("Status"), "status_custom_col"),
    ]
    action_method = "detail_view_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="recruitment.add_interviewschedule"), name="dispatch"
)
class InterviewForm(HorillaFormView):
    """
    form view
    """

    form_class = ScheduleInterviewForm
    model = InterviewSchedule
    new_display_title = _("Schedule Interview")

    def get_context_data(self, **kwargs):
        """
        Override to add custom context data.
        """
        context = super().get_context_data(**kwargs)
        resolved = resolve(self.request.path_info)
        cand_id = resolved.kwargs.get("cand_id")
        if cand_id:
            self.form.fields["candidate_id"].queryset = Candidate.objects.filter(
                id=cand_id
            )
            self.form.fields["candidate_id"].initial = cand_id
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Schedule Interview")
        context["form"] = self.form
        context["view_id"] = "InterviewCreate"
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Schedule Interview")
        if not form.is_valid():
            context = self.get_context_data(form=form)
            context["errors"] = form.errors.as_data()
            return render(self.request, self.template_name, context)
        return super().form_invalid(form)

    def form_valid(self, form: ScheduleInterviewForm) -> HttpResponse:
        """
        Handle form submission when the form is valid.

        Args:
            form (ScheduleInterviewForm): The validated form object.

        Returns:
            HttpResponse: Redirect response or HTTP response.
        """
        if form.is_valid():
            emp_ids = self.form.cleaned_data["employee_id"]
            cand_id = self.form.cleaned_data["candidate_id"]
            interview_date = self.form.cleaned_data["interview_date"]
            interview_time = self.form.cleaned_data["interview_time"]
            users = [employee.employee_user_id for employee in emp_ids]
            notify.send(
                self.request.user.employee_get,
                recipient=users,
                verb=f"You are scheduled as an interviewer for an interview with {cand_id.name} on {interview_date} at {interview_time}.",
                verb_ar=f"أنت مجدول كمقابلة مع {cand_id.name} يوم {interview_date} في توقيت {interview_time}.",
                verb_de=f"Sie sind als Interviewer für ein Interview mit {cand_id.name} am {interview_date} um {interview_time} eingeplant.",
                verb_es=f"Estás programado como entrevistador para una entrevista con {cand_id.name} el {interview_date} a las {interview_time}.",
                verb_fr=f"Vous êtes programmé en tant qu'intervieweur pour un entretien avec {cand_id.name} le {interview_date} à {interview_time}.",
                icon="people-circle",
                redirect=reverse("interview-view"),
            )
            if form.instance.pk:
                messages.success(self.request, _("Interview Updated Successfully"))
            else:
                messages.success(self.request, _("Interview Scheduled successfully."))
            form.save()
            return HttpResponse(
                "<script>"
                "$('#genericModal').removeClass('oh-modal--show');"
                "$('#applyFilter').click();"
                "$('#reloadMessagesButton').click();"
                "</script>"
            )
        return super().form_valid(form)
