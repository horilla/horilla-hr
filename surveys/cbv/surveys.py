"""The Surveys page (nav, list, cards), a survey's tabs and audience list,
the create/edit forms, and the library (nav, cards, list, detail, forms)."""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from horilla.decorators import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
)
from surveys.access import can_manage, can_view_results
from surveys.filters import QuestionnaireFilter, SurveyFilter
from surveys.forms import (
    QuestionnaireForm,
    SaveToLibraryForm,
    SurveyForm,
    SurveyQuestionForm,
)
from surveys.models import Questionnaire, Survey, SurveyInvitation, SurveyQuestion

CLOSE_MODAL = (
    "<script>$('.oh-modal--show').removeClass('oh-modal--show');"
    "$('#reloadMessagesButton').click();</script>"
)


def _status_filter_attr(status):
    """onclick that sets the status filter and applies it."""
    return (
        "onclick=\"$('#applyFilter').closest('form').find('[name=status]')"
        f".val('{status}');$('#applyFilter').click();\" "
    )


STATUS_INDICATIONS = [
    ("survey-open--dot", _("Open"), _status_filter_attr("open")),
    ("survey-draft--dot", _("Draft"), _status_filter_attr("draft")),
    ("survey-closed--dot", _("Closed"), _status_filter_attr("closed")),
]


def _modal(url_attr):
    """The attributes that open `url_attr` in the generic modal."""
    return (
        f'hx-get="{url_attr}" hx-target="#genericModalBody" '
        'data-target="#genericModal" data-toggle="oh-modal-toggle"'
    )


def _delete_modal(url_attr):
    """The attributes that open the generic delete confirmation of `url_attr`."""
    return (
        f'hx-get="{url_attr}" hx-target="#deleteConfirmationBody" '
        'data-target="#deleteConfirmation" data-toggle="oh-modal-toggle"'
    )


def _view_types(list_url, card_url, default="list"):
    """The list/card switch of a nav, the default first."""
    types = [
        {
            "type": "list",
            "icon": "list-outline",
            "url": list_url,
            "attrs": f'title="{_("List")}"',
        },
        {
            "type": "card",
            "icon": "grid-outline",
            "url": card_url,
            "attrs": f'title="{_("Card")}"',
        },
    ]
    return types if default == "list" else types[::-1]


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
        self.view_types = _view_types(reverse("surveys-list"), reverse("surveys-card"))
        if self.request.user.has_perm("surveys.add_survey"):
            self.create_attrs = _modal(reverse_lazy("survey-create"))


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
    row_status_indications = STATUS_INDICATIONS

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-list")
        self.action_method = "row_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class SurveysCard(HorillaCardView):
    model = Survey
    filter_class = SurveyFilter
    details = {
        "title": "{title}",
        "subtitle": format_lazy(
            "{}: {}<br>{}: {}<br>{}: {}",
            _("Audience"),
            "{audience_label}",
            _("Answered"),
            "{answered_label}",
            _("Closes at"),
            "{closes_label}",
        ),
    }
    card_attrs = "onclick=\"window.location.href='{get_detail_url}'\""
    card_status_class = "survey-{status}"
    card_status_indications = STATUS_INDICATIONS

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-card")
        user = self.request.user
        self.actions = [
            {
                "action": _("Open"),
                "attrs": 'class="oh-dropdown__link" href="{get_detail_url}"',
            }
        ]
        if user.has_perm("surveys.change_survey"):
            self.actions.append(
                {
                    "action": _("Edit"),
                    "attrs": 'class="oh-dropdown__link" ' + _modal("{get_update_url}"),
                }
            )
        if user.has_perm("surveys.delete_survey"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": 'class="oh-dropdown__link" '
                    + _delete_modal("{get_delete_url}"),
                }
            )


@method_decorator(login_required, name="dispatch")
class SurveyTabs(HorillaTabView):
    """The tabs of a survey's page: its questions, its audience, its results."""

    share_saved_filters_across_tabs = False

    def get(self, request, *args, **kwargs):
        self.survey = get_object_or_404(Survey, pk=kwargs.get("pk"))
        if not (
            request.user.has_perm("surveys.view_survey")
            or can_manage(request.user, self.survey)
        ):
            return HttpResponseForbidden()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        survey = self.survey
        self.view_id = f"surveyTabs{survey.pk}"
        self.tabs = [
            {
                "title": _("Questions"),
                "url": reverse("survey-questions-tab", args=[survey.pk]),
                "badge": survey.questions.count(),
                "badge_label": _("Questions"),
            },
            {
                "title": _("Audience"),
                "url": reverse("survey-audience-tab", args=[survey.pk]),
                "badge": survey.invited_count(),
                "badge_label": _("Invited"),
            },
        ]
        if can_view_results(self.request.user, survey):
            self.tabs.append(
                {
                    "title": _("Results"),
                    "url": reverse("survey-results-tab", args=[survey.pk]),
                    "badge": survey.answered_count(),
                    "badge_label": _("Answered"),
                }
            )
        return super().get_context_data(**kwargs)


@method_decorator(login_required, name="dispatch")
class InvitationsList(HorillaListView):
    """Who a survey went to and who has answered (the Audience tab)."""

    model = SurveyInvitation
    columns = [
        (_("Employee"), "employee", "employee__get_avatar"),
        (_("Department"), "department_label"),
        (_("Status"), "status_badge"),
        (_("Invited"), "sent_label"),
        (_("Reminded"), "reminded_label"),
        (_("Answered"), "submitted_label"),
    ]
    sortby_mapping = [
        (_("Employee"), "employee__employee_first_name"),
        (_("Status"), "status"),
        (_("Invited"), "sent_at"),
        (_("Answered"), "submitted_at"),
    ]
    show_toggle_form = False
    show_filter_tags = False
    bulk_select_option = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "surveyInvitations"
        self.search_url = reverse("survey-invitations", args=[kwargs.get("pk")])

    def dispatch(self, request, *args, **kwargs):
        survey = get_object_or_404(Survey, pk=kwargs.get("pk"))
        if not (
            request.user.has_perm("surveys.view_survey")
            or can_manage(request.user, survey)
        ):
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        queryset = SurveyInvitation.objects.filter(
            survey_id=self.kwargs.get("pk")
        ).select_related("employee")
        return super().get_queryset(queryset, filtered, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class SurveyFormView(HorillaFormView):
    model = Survey
    form_class = SurveyForm
    new_display_title = _("Create survey")
    template_name = "surveys/survey_form.html"

    def dispatch(self, request, *args, **kwargs):
        perm = "surveys.change_survey" if kwargs.get("pk") else "surveys.add_survey"
        if not request.user.has_perm(perm):
            messages.error(request, _("You do not have permission for this."))
            return HttpResponse(
                "<script>$('.oh-modal--show').removeClass('oh-modal--show');$('#reloadMessagesButton').click();</script>"
            )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """ "Use" in the library opens this form filled in from the questionnaire."""
        initial = super().get_initial()
        questionnaire = Questionnaire.objects.filter(
            pk=self.request.GET.get("questionnaire") or None
        ).first()
        if questionnaire and not self.kwargs.get("pk"):
            initial.update(
                questionnaire=str(questionnaire.pk),
                title=questionnaire.title,
                description=questionnaire.description,
                is_anonymous=questionnaire.is_anonymous,
            )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit survey")
        return context

    def form_valid(self, form: SurveyForm) -> HttpResponse:
        if form.is_valid():
            new = not form.instance.pk
            questionnaire = form.cleaned_data.get("questionnaire") if new else None
            survey = form.save(commit=False)
            if new:
                survey.company_id = self.request.user.employee_get.get_company()
            survey.save()
            form.save_m2m()
            if questionnaire:
                questionnaire.copy_questions_to(survey)
            if new:
                messages.success(
                    self.request,
                    (
                        _("Survey created from the library - check its questions.")
                        if questionnaire
                        else _("Survey created - now add its questions.")
                    ),
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
    template_name = "surveys/question_form.html"

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


# --- the library -------------------------------------------------------------


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class LibraryView(TemplateView):
    template_name = "surveys/library/library.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class LibraryNav(HorillaNavView):
    nav_title = _("Library")
    filter_instance = QuestionnaireFilter()
    filter_form_context_name = "form"
    filter_body_template = "surveys/library/filter.html"
    search_swap_target = "#listContainer"
    apply_first_filter = False
    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-library-cards")
        self.view_types = _view_types(
            reverse("surveys-library-list"),
            reverse("surveys-library-cards"),
            default="card",
        )
        # A questionnaire is made from a survey (Save to library on its page),
        # so the library has no Create; the standard ones are an action.
        if self.request.user.has_perm("surveys.add_questionnaire"):
            self.actions = [
                {
                    "action": _("Load standard questionnaires"),
                    "attrs": f"""
                        hx-post="{reverse('surveys-library-load-standard')}"
                        hx-target="#libraryActionTarget"
                        style="cursor:pointer"
                    """,
                }
            ]


def _questionnaire_actions(user):
    """The dropdown of a library card, as far as `user` may use it."""
    actions = []
    if user.has_perm("surveys.add_survey"):
        actions.append(
            {
                "action": _("Use"),
                "attrs": 'class="oh-dropdown__link" ' + _modal("{get_use_url}"),
            }
        )
    if user.has_perm("surveys.change_questionnaire"):
        actions.append(
            {
                "action": _("Edit"),
                "attrs": 'class="oh-dropdown__link" ' + _modal("{get_update_url}"),
            }
        )
    if user.has_perm("surveys.delete_questionnaire"):
        actions.append(
            {
                "action": _("Delete"),
                "attrs": 'class="oh-dropdown__link" '
                + _delete_modal("{get_delete_url}"),
            }
        )
    return actions


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class QuestionnaireCards(HorillaCardView):
    model = Questionnaire
    filter_class = QuestionnaireFilter
    details = {
        "title": "{title}",
        "subtitle": "{question_count_label}<br>{anonymity_label}",
    }
    card_attrs = _modal("{get_detail_url}")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-library-cards")
        self.actions = _questionnaire_actions(self.request.user)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class QuestionnaireList(HorillaListView):
    model = Questionnaire
    filter_class = QuestionnaireFilter
    columns = [
        (_("Title"), "title"),
        (_("Questions"), "question_count"),
        (_("Anonymous"), "anonymity_label"),
    ]
    sortby_mapping = [(_("Title"), "title")]
    row_attrs = _modal("{get_detail_url}") + ' style="cursor:pointer"'
    bulk_select_option = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("surveys-library-list")
        self.action_method = "row_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.view_survey"), name="dispatch")
class QuestionnaireDetail(HorillaDetailedView):
    """A questionnaire's questions, and the buttons to use or change it."""

    model = Questionnaire
    title = _("Questionnaire")
    header = {"title": "title", "subtitle": "question_count_label", "avatar": ""}
    body = [
        (_("Description"), "description"),
        (_("Anonymous"), "anonymity_label"),
        (_("Questions"), "questions_html", True),
    ]
    cols = {"description": 12, "anonymity_label": 12, "questions_html": 12}
    action_method = "detail_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("surveys.change_questionnaire"), name="dispatch")
class QuestionnaireFormView(HorillaFormView):
    """Rename a questionnaire of the library or change its description."""

    model = Questionnaire
    form_class = QuestionnaireForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form_class.verbose_name = _("Edit questionnaire")
        return context

    def form_valid(self, form: QuestionnaireForm) -> HttpResponse:
        if form.is_valid():
            form.save()
            messages.success(self.request, _("Questionnaire updated."))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class SaveToLibraryView(HorillaFormView):
    """Keep a survey's questions in the library (survey pk in the URL)."""

    model = Questionnaire
    form_class = SaveToLibraryForm
    new_display_title = _("Save to library")

    def dispatch(self, request, *args, **kwargs):
        self.survey = Survey.objects.filter(pk=kwargs.get("survey_pk")).first()
        allowed = (
            self.survey is not None
            and request.user.has_perm("surveys.add_questionnaire")
            and (
                request.user.has_perm("surveys.view_survey")
                or can_manage(request.user, self.survey)
            )
        )
        if not allowed:
            messages.error(request, _("You do not have permission for this."))
            return HttpResponse(CLOSE_MODAL)
        if not self.survey.questions.exists():
            messages.error(request, _("The survey has no questions to save."))
            return HttpResponse(CLOSE_MODAL)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return None  # always a new form; "replace" picks the one to overwrite

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            title=self.survey.title,
            description=self.survey.description,
            is_anonymous=self.survey.is_anonymous,
        )
        return initial

    def form_valid(self, form: SaveToLibraryForm) -> HttpResponse:
        if form.is_valid():
            questionnaire = form.cleaned_data.get("replace") or Questionnaire(
                company_id=self.survey.company_id
            )
            for field in ("title", "description", "is_anonymous"):
                setattr(questionnaire, field, form.cleaned_data[field])
            questionnaire.questions = Questionnaire.questions_of(self.survey)
            questionnaire.save()
            messages.success(self.request, _("Saved to the library."))
            return self.HttpResponse()
        return super().form_valid(form)
