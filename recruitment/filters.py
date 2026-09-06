"""
filters.py

This page is used to register filter for recruitment models

"""

import ast
import uuid

import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


def _filter_has_referral(qs, name, value):
    if value:
        return qs.filter(referral__isnull=False)
    return qs.filter(referral__isnull=True)


def _filter_source_not_set(qs, name, value):
    if value:
        return qs.filter(Q(source__isnull=True) | Q(source=""), referral__isnull=True)
    return qs


def _filter_recruitment_by_obj_id(qs, name, value):
    try:
        return qs.filter(id=int(value))
    except (ValueError, TypeError):
        return qs


from base.filters import FilterSet
from base.models import Company, Department, JobPosition
from employee.models import Employee
from horilla.filters import HorillaFilterSet, filter_by_name
from recruitment.models import (
    Candidate,
    CandidateDocument,
    InterviewSchedule,
    LinkedInAccount,
    Recruitment,
    RecruitmentSurvey,
    RecruitmentSurveyAnswer,
    RejectReason,
    Skill,
    SkillZone,
    SkillZoneCandidate,
    Stage,
    SurveyTemplate,
)

# from django.forms.widgets import Boo


class CandidateFilter(HorillaFilterSet):
    """
    Filter set class for Candidate model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    search = django_filters.CharFilter(method="search_by_name", lookup_expr="icontains")
    has_referral = django_filters.BooleanFilter(
        method=_filter_has_referral,
        widget=django_filters.widgets.BooleanWidget(),
    )
    source_not_set = django_filters.BooleanFilter(
        method=_filter_source_not_set,
        widget=django_filters.widgets.BooleanWidget(),
    )

    # start_onboard = django_filters.CharFilter(
    #     method="start_onboard_method", lookup_expr="icontains"
    # )

    candidate = django_filters.ModelMultipleChoiceFilter(
        queryset=Candidate.objects.all(),
        field_name="name",
    )

    candidate_name = django_filters.CharFilter(
        method="pipeline_search", lookup_expr="icontains"
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
    hired_date = django_filters.DateFilter(
        field_name="hired_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    joining_date_from = django_filters.DateFilter(
        field_name="joining_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    joining_date_till = django_filters.DateFilter(
        field_name="joining_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    created_at_from = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    created_at_till = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    onboarding_end_date_from = django_filters.DateFilter(
        field_name="onboarding_stage__onboarding_end_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    onboarding_end_date_till = django_filters.DateFilter(
        field_name="onboarding_stage__onboarding_end_date",
        lookup_expr="lte",
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

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Job Position, Department, and Rejection Reason opt into
    # AJAX-searched comboboxes instead of pre-rendering their whole
    # queryset as <option> tags.
    ajax_fields = {
        "job_position_id": {
            "key": "pipeline-candidate-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "job_position_id__department_id": {
            "key": "pipeline-candidate-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "rejected_candidate__reject_reason_id": {
            "key": "pipeline-candidate-reject-reason",
            "queryset_fn": lambda request: RejectReason.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select rejection reason..."),
        },
        # The remaining fields below are only rendered on the standalone
        # Candidates page's filter panel (cbv/candidates/filter.html),
        # not the combined Pipeline panel above -- kept in the same
        # ajax_fields dict since both share this one CandidateFilter class.
        "recruitment_id": {
            "key": "candidate-recruitment",
            "queryset_fn": lambda request: Recruitment.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select recruitment..."),
        },
        "stage_id": {
            "key": "candidate-stage",
            "queryset_fn": lambda request: Stage.objects.select_related(
                "recruitment_id"
            ).all(),
            "display_fn": lambda obj: f"{obj.stage} ({obj.recruitment_id.title})",
            "search_fields": ["stage", "recruitment_id__title"],
            "placeholder": _("Select stage..."),
        },
        "stage_id__stage_managers": {
            "key": "candidate-stage-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "recruitment_id__company_id": {
            "key": "candidate-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "recruitment_id__recruitment_managers": {
            "key": "candidate-recruitment-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "skillzonecandidate_set__skill_zone_id": {
            "key": "candidate-talent-pool",
            "queryset_fn": lambda request: SkillZone.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select talent pool..."),
        },
    }

    def pipeline_search(self, queryset, _, value):
        """
        This method is used to include the candidates when they in the recruitment/stages
        """
        queryset = (
            queryset.filter(name__icontains=value)
            | queryset.filter(stage_id__stage__icontains=value)
            | queryset.filter(stage_id__recruitment_id__title__icontains=value)
        ).distinct()
        return queryset

    def search_by_name(self, queryset, _, value):
        """
        search by name method
        """
        queryset = (
            queryset.filter(name__icontains=value)
            | queryset.filter(stage_id__stage__icontains=value)
            | queryset.filter(stage_id__recruitment_id__title__icontains=value)
        )
        return queryset.distinct()

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Candidate
        fields = [
            "recruitment",
            "recruitment_id",
            "stage_id",
            "schedule_date",
            "candidate_interview__interview_date",
            "email",
            "mobile",
            "country",
            "state",
            "city",
            "zip",
            "gender",
            "start_onboard",
            "hired",
            "converted",
            "canceled",
            "is_active",
            "recruitment_id__company_id",
            "job_position_id",
            "recruitment_id__closed",
            "recruitment_id__is_active",
            "job_position_id__department_id",
            "recruitment_id__recruitment_managers",
            "stage_id__stage_managers",
            "stage_id__stage_type",
            "joining_date",
            "skillzonecandidate_set__skill_zone_id",
            "skillzonecandidate_set__candidate_id",
            "portal_sent",
            "joining_set",
            "rejected_candidate__reject_reason_id",
            "offer_letter_status",
            "candidate_rating__rating",
            "candidate_interview__employee_id",
            "source",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        form_fields = self.form.fields
        form_fields["is_active"].initial = True

        for field in form_fields:
            form_fields[field].widget.attrs["id"] = str(uuid.uuid4())

        self._update_field_labels(form_fields)
        choices = []
        try:
            survey_answers = RecruitmentSurveyAnswer.objects.all()
            for survey in survey_answers:
                candidate = survey.candidate_id
                answer_json = survey.answer_json

                # Parse JSON if stored as string
                if isinstance(answer_json, str):
                    try:
                        answer_json = ast.literal_eval(answer_json)
                    except Exception:
                        continue

                # Extract questions & answers
                for question, answer_list in answer_json.items():
                    if question == "csrfmiddlewaretoken":
                        continue

                    answer = (
                        ", ".join(answer_list)
                        if isinstance(answer_list, list)
                        else str(answer_list)
                    )

                    choices.append(
                        (
                            candidate.pk,
                            f"Q: {question} || Ans: {answer} || {candidate.get_full_name()}",
                        )
                    )
        except:
            pass

        # Add filter dynamically
        survey_answer_by = django_filters.MultipleChoiceFilter(
            choices=choices,
            field_name="recruitmentsurveyanswer__candidate_id",
            label=_("Survey Answer By"),
        )
        self.filters["survey_answer_by"] = survey_answer_by
        self.form.fields["survey_answer_by"] = survey_answer_by.field
        self.form.fields["survey_answer_by"].widget.attrs.update(
            {
                "data-placeholder": _("Select survey answers..."),
                # Was "survey-select" -- that class was never targeted by
                # any select2 init handler (horilla_theme's htmxSelect2.js
                # only auto-initializes ".oh-select"/".oh-select-ajax"),
                # so this field always rendered as a bare unstyled
                # <select multiple> regardless of how many choices it had.
                "class": "oh-select w-100",
                "style": "width:100% !important;",
            }
        )

    def _update_field_labels(self, form_fields):
        """Helper method to update field labels from model verbose names"""

        models = {
            "recruitment": Recruitment(),
            "interview": InterviewSchedule(),
            "skill_zone": SkillZoneCandidate(),
        }

        interview_date_label = (
            models["interview"]._meta.get_field("interview_date").verbose_name
        )

        field_label_map = {
            "interview_date": interview_date_label,
            "scheduled_from": f"{interview_date_label} From",
            "scheduled_till": f"{interview_date_label} Till",
            "rejected_candidate__reject_reason_id": _("Rejection Reason"),
            "job_position_id__department_id": _("Department"),
            "stage_id__stage_type": _("Stage Type"),
            "stage_id__stage_managers": _("Stage Managers"),
            "skillzonecandidate_set__skill_zone_id": models["skill_zone"]
            ._meta.get_field("skill_zone_id")
            .verbose_name,
            "start_date": models["recruitment"]
            ._meta.get_field("start_date")
            .verbose_name,
            "end_date": models["recruitment"]._meta.get_field("end_date").verbose_name,
            "recruitment_id__company_id": models["recruitment"]
            ._meta.get_field("company_id")
            .verbose_name,
            "recruitment_id__closed": models["recruitment"]
            ._meta.get_field("closed")
            .verbose_name,
            "recruitment_id__recruitment_managers": models["recruitment"]
            ._meta.get_field("recruitment_managers")
            .verbose_name,
        }

        for field_name, label in field_label_map.items():
            if field_name in form_fields:
                form_fields[field_name].label = label

    def filter_mail_sent(self, queryset, name, value):
        return queryset.filter(onboarding_portal__isnull=(not value))

    def filter_joining_set(self, queryset, name, value):
        return queryset.filter(joining_date__isnull=(not value))

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. This model already has several
        DateFilters declared (probation_end_from/till, joining_date_
        from/till, created_at_from/till, onboarding_end_date_from/
        till...) that were never actually rendered anywhere in the
        template -- rather than adding yet more fixed inputs for each,
        this exposes the underlying plain field+lookup shape directly,
        offering the full gte/lte/gt/lt/exact set per field instead of
        each one's previously-unreachable fixed direction.
        """
        fields = [
            {
                "key": "interview_date",
                "field": "candidate_interview__interview_date",
                "label": str(_("Interview Date")),
                "type": "date_range",
            },
            {
                "key": "probation_end",
                "field": "probation_end",
                "label": str(_("Probation End")),
                "type": "date_range",
            },
            {
                "key": "schedule_date",
                "field": "schedule_date",
                "label": str(_("Schedule Date")),
                "type": "date_range",
            },
            {
                "key": "joining_date",
                "field": "joining_date",
                "label": str(_("Joining Date")),
                "type": "date_range",
            },
            {
                "key": "onboarding_end_date",
                "field": "onboarding_stage__onboarding_end_date",
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
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class CandidateDocumentFilter(HorillaFilterSet):
    """
    Filter set class for CandidateDocument model
    """

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = CandidateDocument
        fields = ["title", "status"]


class SkillZoneCandidateFilter(HorillaFilterSet):
    """
    Filter set class for SkillZoneCandidate model
    """

    search = django_filters.CharFilter(field_name="reason", lookup_expr="icontains")

    class Meta:
        model = SkillZoneCandidate
        fields = ["skill_zone_id", "candidate_id", "reason"]


BOOLEAN_CHOICES = (
    ("", ""),
    ("false", "False"),
    ("true", "True"),
)


class RecruitmentFilter(HorillaFilterSet):
    """
    Filter set class for Recruitment model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    candidate_name = django_filters.CharFilter(
        field_name="title", method="pipeline_search"
    )
    search_onboarding = django_filters.CharFilter(
        field_name="title", method="onboarding_search"
    )
    description = django_filters.CharFilter(lookup_expr="icontains")
    start_from = django_filters.DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_till = django_filters.DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    search = django_filters.CharFilter(method="filter_by_name")
    is_active = django_filters.ChoiceFilter(
        choices=[
            (True, "Yes"),
            (False, "No"),
        ]
    )
    obj_id = django_filters.CharFilter(method=_filter_recruitment_by_obj_id)

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see horilla.filters.HorillaFilterSet for the full explanation) --
    # Recruitment Managers and Company opt into AJAX-searched comboboxes
    # instead of pre-rendering their whole queryset as <option> tags.
    ajax_fields = {
        "recruitment_managers": {
            "key": "pipeline-recruitment-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "company_id": {
            "key": "pipeline-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Recruitment
        fields = [
            "recruitment_managers",
            "company_id",
            "title",
            "is_event_based",
            "closed",
            "is_active",
            "is_published",
            "job_position_id",
            "open_positions",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        start_date_verbose = self.Meta.model._meta.get_field("start_date").verbose_name
        end_date_verbose = self.Meta.model._meta.get_field("end_date").verbose_name
        self.form.fields["start_from"].label = f"{start_date_verbose} From"
        self.form.fields["end_till"].label = f"{end_date_verbose} Till"

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
            | queryset.filter(stage_set__stage__icontains=value)
            | queryset.filter(stage_set__candidate__name__icontains=value)
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

    def pipeline_search(self, queryset, _, value):
        """
        This method is used to search recruitment
        """
        queryset = (
            queryset.filter(title__icontains=value)
            | queryset.filter(stage_set__stage__icontains=value)
            | queryset.filter(candidate__name__icontains=value)
        )
        return queryset.distinct()

    def onboarding_search(self, queryset, _, value):
        """
        This method is used to search recruitment
        """
        queryset = (
            queryset.filter(title__icontains=value)
            | queryset.filter(onboarding_stage__stage_title__icontains=value)
            | queryset.filter(
                candidate__onboarding_stage__candidate_id__name__icontains=value
            )
        )
        return queryset.distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Start Date/End Date used to each
        have their own single-direction fixed input (start_from's gte
        on start_date, end_till's lte on end_date) -- replaced with the
        full gte/lte/gt/lt/exact set per field, plus Created At.
        """
        fields = [
            {
                "key": "start_date",
                "field": "start_date",
                "label": str(_("Start Date")),
                "type": "date_range",
            },
            {
                "key": "end_date",
                "field": "end_date",
                "label": str(_("End Date")),
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
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class SkillsFilter(FilterSet):

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = Skill
        fields = [
            "title",
        ]


class RejectReasonFilter(FilterSet):

    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = RejectReason
        fields = [
            "title",
        ]

    def filter_search(self, queryset, _, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )


class StageFilter(HorillaFilterSet):
    """
    Filter set class for Stage model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    search = django_filters.CharFilter(method="filter_by_name")
    candidate_name = django_filters.CharFilter(method="pipeline_search")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Recruitment and Stage Managers opt into AJAX-searched comboboxes
    # instead of pre-rendering their whole queryset as <option> tags.
    ajax_fields = {
        "recruitment_id": {
            "key": "pipeline-stage-recruitment",
            "queryset_fn": lambda request: Recruitment.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select recruitment..."),
        },
        "stage_managers": {
            "key": "pipeline-stage-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        # The four below are only rendered on the Stages configuration
        # tab's own filter panel (cbv/stages/filter.html), not the
        # combined Pipeline panel above -- kept in the same ajax_fields
        # dict since both share this one StageFilter class.
        "recruitment_id__recruitment_managers": {
            "key": "stage-recruitment-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "recruitment_id__job_position_id__department_id": {
            "key": "stage-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "recruitment_id__company_id": {
            "key": "stage-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "recruitment_id__job_position_id": {
            "key": "stage-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Stage
        fields = [
            "recruitment_id",
            "recruitment_id__job_position_id",
            "recruitment_id__job_position_id__department_id",
            "recruitment_id__company_id",
            "recruitment_id__recruitment_managers",
            "stage_managers",
            "stage_type",
        ]

    def filter_by_name(self, queryset, _, value):
        """
        Filter queryset by stage title, recruitment title, managers, or candidates.
        """
        from django.db.models import Q

        value = (value or "").strip()
        if not value:
            return queryset

        parts = value.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        query = (
            Q(stage__icontains=value)
            | Q(recruitment_id__title__icontains=value)
            | Q(candidate__name__icontains=value)
        )
        if first_name and last_name:
            query |= Q(
                stage_managers__employee_first_name__icontains=first_name,
                stage_managers__employee_last_name__icontains=last_name,
            )
        elif first_name:
            query |= Q(stage_managers__employee_first_name__icontains=first_name)

        return queryset.filter(query).distinct()

    def pipeline_search(self, queryset, _, value):
        """
        This method is used to search recruitment
        """
        queryset = (
            queryset.filter(stage__icontains=value)
            | queryset.filter(candidate__name__icontains=value)
            | queryset.filter(recruitment_id__title__icontains=value)
        )
        return queryset.distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Created At is the only real date
        column on this model, so it's the sole entry.
        """
        fields = [
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
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class SurveyFilter(HorillaFilterSet):
    """
    SurveyFIlter
    """

    options = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Options",
        field_name="options",
    )

    question = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Question",
        field_name="question",
    )

    search = django_filters.CharFilter(
        lookup_expr="icontains",
        field_name="question",
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Recruitment opts into an AJAX-searched combobox instead of
    # pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "recruitment_ids": {
            "key": "survey-recruitment",
            "queryset_fn": lambda request: Recruitment.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select recruitment..."),
        },
    }

    class Meta:
        """
        class Meta for additional options
        """

        model = RecruitmentSurvey
        fields = "__all__"
        exclude = [
            "sequence",
        ]


class SurveyTemplateFilter(django_filters.FilterSet):
    """
    SurveyTemplateFilter
    """

    search = django_filters.CharFilter(
        lookup_expr="icontains",
        label="Title",
        field_name="title",
    )

    class Meta:
        model = SurveyTemplate
        fields = "__all__"


class CandidateReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "select"),
        ("recruitment_id", "Recruitment"),
        ("job_position_id", "Job Position"),
        ("hired", "Hired"),
        ("country", "Country"),
        ("stage_id", "Stage"),
        ("joining_date", "Date Joining"),
        ("probation_end", "Probation End"),
        ("offer_letter_status", "Offer Letter Status"),
        ("rejected_candidate__reject_reason_id", "Rejection Reason"),
        ("skillzonecandidate_set__skill_zone_id", "Talent Pool"),
    ]


class SkillZoneFilter(FilterSet):
    """
    Skillzone Filter
    """

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        """
        class Meta for additional options
        """

        model = SkillZone
        fields = [
            "is_active",
            "skillzonecandidate_set__candidate_id",
            "skillzonecandidate_set__candidate_id__recruitment_id",
            "skillzonecandidate_set__candidate_id__job_position_id",
            "skillzonecandidate_set__candidate_id__stage_id__stage_type",
        ]


class SkillZoneCandFilter(HorillaFilterSet):
    """
    Skillzone Candidate FIlter
    """

    search = django_filters.CharFilter(
        field_name="candidate_id__name", method="cand_search"
    )
    start_date = django_filters.DateFilter(
        field_name="candidate__id__recruitment_id__start_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = django_filters.DateFilter(
        field_name="candidate__id__recruitment_id__end_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_from = django_filters.DateFilter(
        field_name="candidate__id__joining_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Joining From"),
    )
    probation_end = django_filters.DateFilter(
        field_name="candidate__id__probation_end",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    probation_end_till = django_filters.DateFilter(
        field_name="candidate__id__probation_end",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Probation Till"),
    )
    probation_end_from = django_filters.DateFilter(
        field_name="candidate__id__probation_end",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Probation From"),
    )
    schedule_date = django_filters.DateFilter(
        field_name="candidate__id__schedule_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_till = django_filters.DateFilter(
        field_name="candidate__id__joining_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Joining Till"),
    )
    recruitment = django_filters.CharFilter(
        field_name="candidate__id__recruitment_id__title", lookup_expr="icontains"
    )

    portal_sent = django_filters.BooleanFilter(
        field_name="candidate__id__onboarding_portal",
        method="filter_mail_sent",
        widget=django_filters.widgets.BooleanWidget(),
        label=_("Portal Sent"),
    )
    joining_set = django_filters.BooleanFilter(
        field_name="candidate__id__joining_date",
        method="filter_joining_set",
        widget=django_filters.widgets.BooleanWidget(),
        label=_("Joining Set"),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Candidate, Recruitment, Job Position, and Rejection Reason opt
    # into AJAX-searched comboboxes instead of pre-rendering their whole
    # queryset as <option> tags.
    ajax_fields = {
        "candidate_id": {
            "key": "talent-pool-candidate",
            "queryset_fn": lambda request: Candidate.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": _("Search candidate..."),
        },
        "candidate_id__recruitment_id": {
            "key": "talent-pool-recruitment",
            "queryset_fn": lambda request: Recruitment.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select recruitment..."),
        },
        "candidate_id__job_position_id": {
            "key": "talent-pool-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "candidate_id__rejected_candidate__reject_reason_id": {
            "key": "talent-pool-reject-reason",
            "queryset_fn": lambda request: RejectReason.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select rejection reason..."),
        },
    }

    class Meta:
        """
        class Meta for additional options
        """

        model = SkillZoneCandidate
        fields = [
            "is_active",
            "candidate_id",
            "candidate_id__recruitment_id",
            "candidate_id__stage_id",
            "candidate_id__schedule_date",
            "candidate_id__email",
            "candidate_id__mobile",
            "candidate_id__country",
            "candidate_id__state",
            "candidate_id__city",
            "candidate_id__zip",
            "candidate_id__gender",
            "candidate_id__start_onboard",
            "candidate_id__hired",
            "candidate_id__canceled",
            "candidate_id__is_active",
            "candidate_id__recruitment_id__company_id",
            "candidate_id__job_position_id",
            "candidate_id__recruitment_id__closed",
            "candidate_id__recruitment_id__is_active",
            "candidate_id__job_position_id__department_id",
            "candidate_id__recruitment_id__recruitment_managers",
            "candidate_id__stage_id__stage_managers",
            "candidate_id__stage_id__stage_type",
            "candidate_id__joining_date",
            "candidate_id__skillzonecandidate_set__skill_zone_id",
            "candidate_id__skillzonecandidate_set__candidate_id",
            "candidate_id__rejected_candidate__reject_reason_id",
            "candidate_id__offer_letter_status",
            "candidate_id__candidate_rating__rating",
        ]
        exclude = [
            "reason",
            "objects",
        ]

    def cand_search(self, queryset, _, value):
        """
        This method to include candidate when search talent pool
        """
        return (
            queryset.filter(candidate_id__name__icontains=value)
            | queryset.filter(skill_zone_id__title__icontains=value)
        ).distinct()


class InterviewFilter(HorillaFilterSet):
    """
    Filter set class for Candidate model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    search = django_filters.CharFilter(
        field_name="candidate_id__name", lookup_expr="icontains"
    )

    scheduled_from = django_filters.DateFilter(
        field_name="interview_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    scheduled_till = django_filters.DateFilter(
        field_name="interview_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Candidate and Interviewer opt into AJAX-searched comboboxes
    # instead of pre-rendering their whole queryset as <option> tags.
    ajax_fields = {
        "candidate_id": {
            "key": "interview-candidate",
            "queryset_fn": lambda request: Candidate.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": _("Search candidate..."),
        },
        "employee_id": {
            "key": "interview-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = InterviewSchedule
        fields = [
            "candidate_id",
            "employee_id",
            "interview_date",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form["scheduled_from"].label = (
            f"{self.Meta.model()._meta.get_field('interview_date').verbose_name} From"
        )
        self.form["scheduled_till"].label = (
            f"{self.Meta.model()._meta.get_field('interview_date').verbose_name} Till"
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Interview Date is a plain DateField
        column, so the plain field+lookup shape applies directly,
        offering the full gte/lte/gt/lt/exact set instead of the fixed
        gte/lte scheduled_from/scheduled_till pair. Created At is
        included too.
        """
        fields = [
            {
                "key": "interview_date",
                "field": "interview_date",
                "label": str(_("Interview Date")),
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
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class LinkedInAccountFilter(FilterSet):
    """LinkedInAccount filter"""

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = LinkedInAccount
        fields = ["username", "email", "company_id"]

    def search_method(self, queryset, _, value: str):
        """Method is used to search through LinkedInAccount"""
        values = value.split(" ")
        empty = queryset.model.objects.none()
        for split in values:
            empty = (
                empty
                | (queryset.filter(username__icontains=split))
                | (queryset.filter(email__icontains=split))
            )
        return empty.distinct()
