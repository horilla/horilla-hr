"""
This page handles the cbv methods for recruitment survey page
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from recruitment.filters import SurveyFilter, SurveyTemplateFilter
from recruitment.forms import QuestionForm, TemplateForm
from recruitment.models import RecruitmentSurvey, SurveyTemplate


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("recruitment.add_recruitmentsurvey"), name="dispatch"
)
class QuestionFormView(HorillaFormView):
    """
    form view for create button
    """

    form_class = QuestionForm
    model = RecruitmentSurvey
    new_display_title = _("Survey Questions")
    template_name = "cbv/recruitment_survey/survey_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Survey Questions")
        return context

    def form_valid(self, form: QuestionForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Survey question updated.")
            else:
                message = _("New survey question created.")
            instance = form.save(commit=False)
            instance.save()
            instance.recruitment_ids.set(form.recruitment)
            instance.template_id.set(form.cleaned_data["template_id"])
            messages.success(self.request, _(message))
            return self.HttpResponse(
                targets_to_reload=["#questionTabRoot .filterButton", ".reload-record"]
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("recruitment.add_recruitmentsurvey"), name="dispatch"
)
class QuestionDuplicateFormView(HorillaFormView):
    """
    form view for create duplicate for asset
    """

    form_class = QuestionForm
    model = RecruitmentSurvey
    new_display_title = _("Duplicate Survey Questions")
    template_name = "cbv/recruitment_survey/survey_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not RecruitmentSurvey.objects.filter(id=kwargs.get("obj_id")).exists():
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = RecruitmentSurvey.objects.get(id=self.kwargs["obj_id"])
        form = self.form_class(instance=original_object)
        for field_name, field in form.fields.items():
            if isinstance(field, forms.CharField):
                if field.initial:
                    initial_value = field.initial
                else:
                    initial_value = f"{form.initial.get(field_name, '')} (copy)"
                form.initial[field_name] = initial_value
                form.fields[field_name].initial = initial_value
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate")
        return context

    def form_valid(self, form: QuestionForm) -> HttpResponse:
        if form.is_valid():
            message = _("New survey question created.")
            instance = form.save(commit=False)
            instance.save()
            instance.recruitment_ids.set(form.recruitment)
            instance.template_id.set(form.cleaned_data["template_id"])
            messages.success(self.request, _(message))
            return self.HttpResponse(
                targets_to_reload=["#questionTabRoot .filterButton", ".reload-record"]
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("recruitment.add_surveytemplate"), name="dispatch"
)
class SurveyTemplateFormView(HorillaFormView):
    """
    form view for create and edit survey templates
    """

    form_class = TemplateForm
    model = SurveyTemplate

    def get_form(self, form_class=None):
        title = self.request.GET.get("title")
        instance = SurveyTemplate.objects.filter(title=title).first()

        if not self.request.POST:
            self.form = self.form_class(instance=instance)
        else:
            self.form = self.form_class(self.request.POST, instance=instance)
        return self.form

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: TemplateForm) -> HttpResponse:
        if form.is_valid():
            message = _("Template saved")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse(
                targets_to_reload=["#templateTabRoot .filterButton", ".reload-record"]
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class RecruitmentSurveyDetailView(HorillaDetailedView):
    """
    detail view of the page
    """

    model = RecruitmentSurvey
    title = _("Details")
    body = [
        (_("Question"), "question"),
        (_("Question Type"), "get_question_type"),
        (_("Sequence"), "sequence"),
        (_("Recruitment"), "recruitment_col"),
        (_("Options"), "options_col", True),
    ]

    header = {"title": "question", "subtitle": "", "avatar": ""}

    cols = {"question": 12}
    action_method = "detail_actions"

    # actions = [
    #     {
    #         "action": _("Edit"),
    #         "icon": "create-outline",
    #         "attrs": """
    #                  class="oh-btn oh-btn--info w-50"
    #                  hx-get="{get_edit_url}"
    #                  hx-target ="#genericModalBody"
    #                  data-target = "#genericModal"
    #                  data-toggle ="oh-modal-toggle"
    #                  """,
    #     },
    #     {
    #         "action": _("Delete"),
    #         "icon": "trash-outline",
    #         "attrs": """
    #                 class="oh-btn oh-btn--danger w-50"
    #                 href ="{get_delete_url}"
    #                 onclick="return confirm(' Are you sure want to delete?')"
    #                 """,
    #     },
    # ]


@method_decorator(login_required, name="dispatch")
class SurveyTemplateSettingsView(TemplateView):
    """
    page for survey templates (Template / Questions tabs)
    """

    template_name = "survey/view_question_templates.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitmentsurvey"), name="dispatch"
)
class SurveyTemplateTabView(HorillaTabView):
    """
    tab view for survey templates, shows template and questions as tabs
    """

    view_id = "surveyTemplateSettingsTab"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tabs = [
            {
                "title": _("Template"),
                "url": reverse("survey-template-tab"),
                "badge": SurveyTemplate.objects.count(),
            },
            {
                "title": _("Questions"),
                "url": reverse("survey-question-tab"),
                "badge": RecruitmentSurvey.objects.count(),
            },
        ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitmentsurvey"), name="dispatch"
)
class SurveyTemplateNavView(HorillaNavView):
    """
    navbar of the Template tab
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-survey-templates")
        if self.request.user.has_perm("recruitment.add_surveytemplate"):
            self.create_attrs = f"""
                                hx-get="{reverse('survey-template-create')}"
                                hx-target="#genericModalBody"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                """

    nav_title = _(" Survey Template")
    filter_instance = SurveyFilter()
    filter_form_context_name = "form"
    filter_body_template = "survey/filter.html"
    search_swap_target = "#view-container"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitmentsurvey"), name="dispatch"
)
class SurveyQuestionNavView(HorillaNavView):
    """
    navbar of the Questions tab
    """

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-survey-questions")
        if self.request.user.has_perm("recruitment.add_recruitmentsurvey"):
            self.create_attrs = f"""
                                hx-get="{reverse('recruitment-survey-question-template-create')}"
                                hx-target="#genericModalBody"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                """

    nav_title = _("Survey Questions")
    filter_instance = SurveyFilter()
    filter_form_context_name = "form"
    filter_body_template = "survey/filter.html"
    search_swap_target = "#questionViewContainer"


def _recruitment_survey_queryset_for(request):
    """
    Same access rule used across this feature: full queryset for users with
    view_recruitmentsurvey, otherwise only questions belonging to
    recruitments the user manages.
    """
    queryset = RecruitmentSurvey.objects.all()
    if not request.user.has_perm("recruitment.view_recruitmentsurvey"):
        queryset = queryset.filter(
            recruitment_ids__recruitment_managers=request.user.employee_get
        ).distinct()
    return queryset


@method_decorator(login_required, name="dispatch")
class SurveyTemplateQuestionsTab(HorillaTabView):
    """
    Tab View for the Survey Templates page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "survey-templates"
        self.tabs = [
            {
                "title": _("Templates"),
                "url": f"{reverse('survey-template-tab-shell')}",
                "badge": SurveyTemplate.objects.count(),
            },
            {
                "title": _("Questions"),
                "url": f"{reverse('survey-question-tab-shell')}",
                "badge": _recruitment_survey_queryset_for(self.request).count(),
            },
        ]


@method_decorator(login_required, name="dispatch")
class SurveyTemplateList(HorillaListView):
    """
    List view of the Templates tab
    """

    model = SurveyTemplate
    filter_class = SurveyTemplateFilter
    template_name = "cbv/recruitment_survey_template/template_accordion.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-survey-templates")
        self.view_id = "survey-templates-container"


@method_decorator(login_required, name="dispatch")
class SurveyQuestionList(HorillaListView):
    """
    List view of the Questions tab
    """

    model = RecruitmentSurvey
    filter_class = SurveyFilter
    template_name = "cbv/recruitment_survey/survey_card.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-survey-questions")
        self.view_id = "survey-questions-container"

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.has_perm("recruitment.view_recruitmentsurvey"):
            queryset = queryset.filter(
                recruitment_ids__recruitment_managers=self.request.user.employee_get
            ).distinct()
        return queryset


class SurveyTemplateTabShell(AttendanceTabContentShell):
    nav_url_name = "survey-template-nav"
    container_id = "surveyTemplatesListContainer"
    tabs_root_id = "survey-templates"


class SurveyQuestionTabShell(AttendanceTabContentShell):
    nav_url_name = "survey-question-nav"
    container_id = "surveyQuestionsListContainer"
    tabs_root_id = "survey-templates"
