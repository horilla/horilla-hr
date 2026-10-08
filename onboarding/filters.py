"""
filters.py
Used to register filter for onboarding models
"""

import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _
from django_filters import filters

from base.filters import FilterSet
from base.models import Company
from employee.models import Employee
from horilla.filters import HorillaFilterSet
from onboarding.models import (
    CandidateStage,
    CandidateTask,
    OnboardingCandidate,
    OnboardingStage,
    OnboardingTask,
)
from recruitment.filters import RecruitmentFilter as rec_filter
from recruitment.models import Candidate, Recruitment


class CandidateTaskFilter(HorillaFilterSet):
    """
    Task filter class
    """

    class Meta:
        """
        Meta
        """

        model = CandidateTask
        fields = "__all__"


class CandidateTaskListFilter(HorillaFilterSet):
    """
    Filter for the standalone onboarding task list page
    """

    search = django_filters.CharFilter(method="search_method")
    onboarding_task_id = django_filters.NumberFilter(field_name="onboarding_task_id")
    task = django_filters.CharFilter(
        field_name="onboarding_task_id__task_title", lookup_expr="icontains"
    )
    stage = django_filters.CharFilter(
        field_name="stage_id__stage_title", lookup_expr="icontains"
    )
    recruitment = django_filters.CharFilter(
        field_name="candidate_id__recruitment_id__title", lookup_expr="icontains"
    )
    task_manager = django_filters.ModelChoiceFilter(
        field_name="onboarding_task_id__employee_id",
        queryset=Employee.objects.all(),
        label=_("Task Manager"),
    )

    ajax_fields = {
        "task_manager": {
            "key": "onboarding-task-list-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = CandidateTask
        fields = ["status"]

    def search_method(self, queryset, _, value):
        """
        Search by candidate, task, stage or recruitment
        """
        return (
            queryset.filter(candidate_id__name__icontains=value)
            | queryset.filter(onboarding_task_id__task_title__icontains=value)
            | queryset.filter(stage_id__stage_title__icontains=value)
            | queryset.filter(candidate_id__recruitment_id__title__icontains=value)
        ).distinct()


class RecruitmentFilter(rec_filter):
    """
    RecruitmentFilter
    """

    search = django_filters.CharFilter(method="filter_by_name")

    class Meta:
        """
        Meta
        """

        model = Recruitment
        fields = "__all__"
        exclude = ["start_date", "end_date"]

    def filter_by_name(self, queryset, _, value):
        """
        Filter queryset by first name or last name.
        """
        # Split the search value into first name and last name
        parts = value.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        job_queryset = (
            queryset.filter(open_positions__job_position__icontains=value)
            | queryset.filter(title__icontains=value)
            | queryset.filter(onboarding_stage__stage_title__icontains=value)
            | queryset.filter(
                onboarding_stage__candidate__candidate_id__name__icontains=value
            )
        )
        if first_name and last_name:
            queryset = queryset.filter(
                recruitment_managers__employee_first_name__icontains=first_name,
                recruitment_managers__employee_last_name__icontains=last_name,
            )
        elif first_name:
            queryset = queryset.filter(
                recruitment_managers__employee_first_name__icontains=first_name
            )
        elif last_name:
            queryset = queryset.filter(
                recruitment_managers__employee_last_name__icontains=last_name
            )

        queryset = queryset | job_queryset
        return queryset.distinct()


class PipelineCandidateFilter(HorillaFilterSet):
    """
    FilterSet class for Candidate model
    """

    search = django_filters.CharFilter(method="search_by_name", lookup_expr="icontains")
    tasks = filters.ModelMultipleChoiceFilter(
        field_name="candidate_id__candidate_task__onboarding_task_id",
        queryset=OnboardingTask.objects.all(),
    )
    # status lives on CandidateTask itself, not on the OnboardingTask it
    # points to -- onboarding_task_id__status doesn't exist on that model.
    task_status = filters.ChoiceFilter(
        field_name="candidate_id__candidate_task__status",
        choices=CandidateTask.choice,
    )
    candidate = django_filters.ModelMultipleChoiceFilter(
        queryset=Candidate.objects.all(),
        field_name="name",
    )

    start_date = django_filters.DateFilter(
        field_name="candidate_id__recruitment_id__start_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = django_filters.DateFilter(
        field_name="candidate_id__recruitment_id__end_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_from = django_filters.DateFilter(
        field_name="candidate_id__candidate_interview__interview_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end = django_filters.DateFilter(
        field_name="candidate_id__probation_end",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end_till = django_filters.DateFilter(
        field_name="candidate_id__probation_end",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end_from = django_filters.DateFilter(
        field_name="candidate_id__probation_end",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    schedule_date = django_filters.DateFilter(
        field_name="candidate_id__schedule_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    interview_date = django_filters.DateFilter(
        field_name="candidate_id__candidate_interview__interview_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_till = django_filters.DateFilter(
        field_name="candidate_id__candidate_interview__interview_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    recruitment = django_filters.CharFilter(
        field_name="candidate_id__recruitment_id__title", lookup_expr="icontains"
    )

    portal_sent = django_filters.BooleanFilter(
        field_name="onboarding_portal",
        method="filter_mail_sent",
        widget=django_filters.widgets.BooleanWidget(),
    )
    joining_set = django_filters.BooleanFilter(
        field_name="joining_date",
        method="filter_joining_set",
        widget=django_filters.widgets.BooleanWidget(),
    )

    class Meta:
        """
        Meta class to add some additional options
        """

        model = CandidateStage
        fields = "__all__"

    def search_by_name(self, queryset, _, value):
        """
        Search by name
        """
        queryset = (
            queryset.filter(candidate_id__name__icontains=value)
            | queryset.filter(onboarding_stage_id__stage_title__icontains=value)
            | queryset.filter(candidate_id__recruitment_id__title__icontains=value)
        )
        return queryset.distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring for
        the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by recruitment.filters.
        CandidateFilter, which this class mirrors. Exposes the full
        gte/lte/gt/lt/exact set for the date fields already declared
        above (probation_end, schedule_date, start_date, end_date,
        interview_date) instead of each one's fixed direction, plus
        Onboarding End Date/Created At which had no fixed input at all.
        """
        fields = [
            {
                "key": "interview_date",
                "field": "candidate_id__candidate_interview__interview_date",
                "label": str(_("Interview Date")),
                "type": "date_range",
            },
            {
                "key": "probation_end",
                "field": "candidate_id__probation_end",
                "label": str(_("Probation End")),
                "type": "date_range",
            },
            {
                "key": "schedule_date",
                "field": "candidate_id__schedule_date",
                "label": str(_("Schedule Date")),
                "type": "date_range",
            },
            {
                "key": "start_date",
                "field": "candidate_id__recruitment_id__start_date",
                "label": str(_("Start Date")),
                "type": "date_range",
            },
            {
                "key": "end_date",
                "field": "candidate_id__recruitment_id__end_date",
                "label": str(_("End Date")),
                "type": "date_range",
            },
            {
                "key": "onboarding_end_date",
                "field": "onboarding_end_date",
                "label": str(_("Onboarding End Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as CandidateFilter/PipelineEmployeeFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class KanbanCandidateFilter(FilterSet):
    """
    FilterSet class for Candidate model
    """

    search = django_filters.CharFilter(method="search_by_name", lookup_expr="icontains")
    tasks = filters.ModelMultipleChoiceFilter(
        field_name="candidate_task__onboarding_task_id",
        queryset=OnboardingTask.objects.all(),
    )
    # status lives on CandidateTask itself, not on the OnboardingTask it
    # points to -- onboarding_task_id__status doesn't exist on that model.
    task_status = filters.ChoiceFilter(
        field_name="candidate_task__status",
        choices=CandidateTask.choice,
    )
    candidate = django_filters.ModelMultipleChoiceFilter(
        queryset=Candidate.objects.all(),
        field_name="name",
    )

    start_date = django_filters.DateFilter(
        field_name="recruitment_id__start_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = django_filters.DateFilter(
        field_name="recruitment_id__end_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_from = django_filters.DateFilter(
        field_name="candidate_interview__interview_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end = django_filters.DateFilter(
        field_name="probation_end",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end_till = django_filters.DateFilter(
        field_name="probation_end",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end_from = django_filters.DateFilter(
        field_name="probation_end",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    schedule_date = django_filters.DateFilter(
        field_name="schedule_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    interview_date = django_filters.DateFilter(
        field_name="candidate_interview__interview_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_till = django_filters.DateFilter(
        field_name="candidate_interview__interview_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    recruitment = django_filters.CharFilter(
        field_name="recruitment_id__title", lookup_expr="icontains"
    )

    portal_sent = django_filters.BooleanFilter(
        field_name="onboarding_portal",
        method="filter_mail_sent",
        widget=django_filters.widgets.BooleanWidget(),
    )
    joining_set = django_filters.BooleanFilter(
        field_name="joining_date",
        method="filter_joining_set",
        widget=django_filters.widgets.BooleanWidget(),
    )

    class Meta:
        """
        Meta class to add some additional options
        """

        model = OnboardingCandidate
        fields = [
            field.name
            for field in OnboardingCandidate._meta.fields
            if field.name not in ["profile", "resume"]
        ]

    def search_by_name(self, queryset, _, value):
        """
        Search by name
        """
        queryset = (
            queryset.filter(name__icontains=value)
            | queryset.filter(
                onboarding_stage__onboarding_stage_id__stage_title__icontains=value
            )
            | queryset.filter(recruitment_id__title__icontains=value)
        )
        return queryset.distinct()


class CandidateFilter(FilterSet):
    """
    FilterSet class for Candidate model
    """

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        """
        Meta class to add some additional options
        """

        model = Candidate
        fields = {}


class OnboardingStageFilter(HorillaFilterSet):
    """
    OnboardingStageFilter
    """

    search_onboarding = filters.CharFilter(
        field_name="stage_title", method="pipeline_search"
    )
    search = filters.CharFilter(
        method="search_method",
    )

    employee_id = filters.ModelChoiceFilter(
        queryset=Employee.objects.all(), label="Stage Manager"
    )

    onboarding_task__task_title = filters.CharFilter(
        field_name="onboarding_task__task_title", lookup_expr="icontains", label="Task"
    )

    onboarding_task__employee_id = filters.ModelChoiceFilter(
        field_name="onboarding_task__employee_id",
        queryset=Employee.objects.all(),
        label="Task Manager",
    )

    recruitment_id__company_id = filters.ModelChoiceFilter(
        field_name="recruitment_id__company_id",
        queryset=Company.objects.all(),
        label="Company",
    )

    onboarding_task__candidates = filters.ModelChoiceFilter(
        field_name="onboarding_task__candidates",
        queryset=Candidate.objects.all(),
        label="Candidates",
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Stage Manager opts into an AJAX-searched combobox instead of
    # pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "onboarding-stage-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = OnboardingStage
        fields = [
            "recruitment_id",
            "stage_title",
            "employee_id",
            "sequence",
            "is_final_stage",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form.fields["employee_id"].widget.attrs.update({"style": "width:100%;"})

    def search_method(self, queryset, _, value):
        """
        Search by name
        """
        parts = value.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        recruitment_query = (
            queryset.filter(recruitment_id__title__icontains=value)
            | queryset.filter(candidate__candidate_id__name__icontains=value)
            | queryset.filter(
                recruitment_id__onboarding_stage__candidate__candidate_id__name__icontains=value
            )
        )
        # Filter the queryset by first name and last name
        stage_queryset = queryset.filter(stage_title__icontains=value)
        if first_name and last_name:
            queryset = queryset.filter(
                employee_id__employee_first_name__icontains=first_name,
                employee_id__employee_last_name__icontains=last_name,
            )
        elif first_name:
            queryset = queryset.filter(
                employee_id__employee_first_name__icontains=first_name
            )
        elif last_name:
            queryset = queryset.filter(
                employee_id__employee_last_name__icontains=last_name
            )

        queryset = queryset | stage_queryset | recruitment_query
        return queryset.distinct()

    def pipeline_search(self, queryset, _, value):
        """
        This method is used to search recruitment
        """
        queryset = queryset.filter(stage_title__icontains=value) | queryset.filter(
            candidate__candidate_id__name__icontains=value
        )
        return queryset.distinct()


class OnboardingCandidateFilter(HorillaFilterSet):
    """
    OnboardingStageFilter
    """

    search_onboarding = filters.CharFilter(
        field_name="candidate_id__name", lookup_expr="icontains"
    )
    stage_id = filters.CharFilter(field_name="onboarding_stage_id")
    country = filters.CharFilter(field_name="candidate_id___country")
    state = filters.CharFilter(field_name="candidate_id___state")
    tasks = filters.ModelMultipleChoiceFilter(
        field_name="candidate_id__candidate_task__onboarding_task_id",
        queryset=OnboardingTask.objects.all(),
    )
    task_status = filters.ChoiceFilter(
        field_name="candidate_id__candidate_task__status",
        choices=CandidateTask.choice,
    )
    onboarding_end_date__gte = django_filters.DateFilter(
        field_name="onboarding_end_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    onboarding_end_date__lte = django_filters.DateFilter(
        field_name="onboarding_end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Tasks opts into an AJAX-searched combobox instead of
    # pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "tasks": {
            "key": "onboarding-candidate-tasks",
            "queryset_fn": lambda request: OnboardingTask.objects.all(),
            "display_fn": lambda obj: obj.task_title,
            "search_fields": ["task_title"],
            "placeholder": _("Select task..."),
        },
    }

    class Meta:
        model = CandidateStage
        fields = "__all__"

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data, queryset, request=request, prefix=prefix)
        self.form.fields["tasks"].widget.attrs.update({"style": "width:100%;"})


class OnboardingTaskFilter(FilterSet):
    """
    Onboarding task filter
    """

    search_onboarding = filters.CharFilter(
        field_name="task_title", lookup_expr="icontains"
    )

    class Meta:
        model = OnboardingTask
        fields = "__all__"
