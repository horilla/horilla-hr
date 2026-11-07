"""The Surveys page: nav, list, create/edit forms."""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from horilla.decorators import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)
from surveys.access import can_manage
from surveys.filters import SurveyFilter
from surveys.forms import SurveyForm, SurveyQuestionForm
from surveys.models import Survey, SurveyQuestion


def _status_filter_attr(status):
    """onclick that sets the status filter and applies it."""
    return (
        "onclick=\"$('#applyFilter').closest('form').find('[name=status]')"
        f".val('{status}');$('#applyFilter').click();\" "
    )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class SurveysView(TemplateView):
    template_name = "surveys/surveys.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class SurveysNav(HorillaNavView):
    nav_title = _("Surveys")
    filter_instance = SurveyFilter()
    filter_form_context_name = "form"
    filter_body_template = "surveys/filter.html"
    search_swap_target = "#listContainer"
    apply_first_filter = False
    modern_filter = True
    group_by_fields = [
        ("status", _("Status")),
        ("audience", _("Audience")),
        ("created_by", _("Created by")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-list")
        if self.request.user.has_perm("surveys.add_survey"):
            self.create_attrs = f"""
                hx-get="{reverse_lazy('survey-create')}"
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
            """


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class SurveysList(HorillaListView):
    model = Survey
    filter_class = SurveyFilter
    columns = [
        (_("Title"), "title"),
        (_("Status"), "status_badge"),
        (_("Audience"), "audience_label"),
        (_("Invited"), "invited_count"),
        (_("Answered"), "answered_label"),
        (_("Closes at"), "closes_label"),
    ]
    sortby_mapping = [
        (_("Title"), "title"),
        (_("Status"), "status"),
        (_("Closes at"), "closes_at"),
    ]
    row_attrs = (
        'href="{get_detail_url}" style="cursor:pointer" '
        "onclick=\"window.location.href=this.getAttribute('href')\" "
    )
    row_status_class = "survey-{status}"
    row_status_indications = [
        (
            "survey-open--dot",
            _("Open"),
            _status_filter_attr("open"),
        ),
        (
            "survey-draft--dot",
            _("Draft"),
            _status_filter_attr("draft"),
        ),
        (
            "survey-closed--dot",
            _("Closed"),
            _status_filter_attr("closed"),
        ),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-list")
        self.action_method = "row_actions"


@method_decorator(login_required, name="dispatch")
class SurveyFormView(HorillaFormView):
    model = Survey
    form_class = SurveyForm
    new_display_title = _("Create survey")

    def dispatch(self, request, *args, **kwargs):
        perm = "surveys.change_survey" if kwargs.get("pk") else "surveys.add_survey"
        if not request.user.has_perm(perm):
            messages.error(request, _("You do not have permission for this."))
            return HttpResponse(
                "<script>$('.oh-modal--show').removeClass('oh-modal--show');$('#reloadMessagesButton').click();</script>"
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit survey")
        return context

    def form_valid(self, form: SurveyForm) -> HttpResponse:
        if form.is_valid():
            new = not form.instance.pk
            survey = form.save(commit=False)
            if new:
                survey.company_id = self.request.user.employee_get.get_company()
            survey.save()
            form.save_m2m()
            if new:
                messages.success(
                    self.request, _("Survey created - now add its questions.")
                )
                return self.HttpResponse(
                    f'<script>window.location.href="{survey.get_detail_url()}"</script>'
                )
            messages.success(self.request, _("Survey updated."))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class SurveyQuestionFormView(HorillaFormView):
    """Add or edit one question of a survey (survey pk in ?survey=)."""

    model = SurveyQuestion
    form_class = SurveyQuestionForm
    new_display_title = _("Add question")

    def dispatch(self, request, *args, **kwargs):
        survey_pk = request.GET.get("survey")
        if kwargs.get("pk"):
            question = SurveyQuestion.objects.filter(pk=kwargs["pk"]).first()
            self.survey = question.survey if question else None
        else:
            self.survey = Survey.objects.filter(pk=survey_pk).first()
        if self.survey is None or not can_manage(request.user, self.survey):
            messages.error(request, _("You do not have permission for this."))
            return HttpResponse(
                "<script>$('.oh-modal--show').removeClass('oh-modal--show');$('#reloadMessagesButton').click();</script>"
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit question")
        return context

    def form_valid(self, form: SurveyQuestionForm) -> HttpResponse:
        if form.is_valid():
            question = form.save(commit=False)
            if not question.pk:
                question.survey = self.survey
                last = (
                    self.survey.questions.order_by("-sequence")
                    .values_list("sequence", flat=True)
                    .first()
                )
                question.sequence = (last or 0) + 1
            question.save()
            messages.success(self.request, _("Question saved."))
            return self.HttpResponse(targets_to_reload=["#reloadQuestions"])
        return super().form_valid(form)
