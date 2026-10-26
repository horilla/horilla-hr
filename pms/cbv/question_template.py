"""
Question Template page
"""

from typing import Any

from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.decorators import manager_can_enter
from base.methods import is_reportingmanager
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from pms.filters import QuestionFilter, QuestionTemplateFilter
from pms.forms import QuestionModalForm, QuestionTemplateForm
from pms.models import Feedback, Question, QuestionOptions, QuestionTemplate


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.view_questiontemplate"), name="dispatch")
class QuestionTemplateView(TemplateView):
    """
    for question template page
    """

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        context["form"] = QuestionTemplateForm
        return context

    template_name = "cbv/question_template/question_template.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.view_questiontemplate"), name="dispatch")
class QuestionTemplateList(HorillaListView):
    """
    List view of the question template page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("question-template-hx-view")
        self.action_method = "action_col"
        self.view_id = "questionTemplateList"

    model = QuestionTemplate
    filter_class = QuestionTemplateFilter

    columns = [
        (_("Title"), "question_template", "get_avatar"),
        (_("Company"), "get_company_display"),
        (_("Total Questions"), "question_count"),
    ]

    header_attrs = {
        "action": """
                    style="width:110px !important"
                   """
    }

    sortby_mapping = [
        (_("Total Questions"), "question_count"),
    ]

    row_attrs = """
                onclick="window.location.href='{get_detail_url}'"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.view_questiontemplate"), name="dispatch")
class QuestionTemplateNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("question-template-hx-view")
        if self.request.user.has_perm(
            "pms.add_questiontemplate"
        ) or is_reportingmanager(self.request):
            self.create_attrs = f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            hx-get="{reverse('question-template-creation')}"
                            """

    nav_title = _("Question Templates")
    filter_instance = QuestionTemplateFilter()
    search_swap_target = "#listContainer"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.add_questiontemplate"), name="dispatch")
class QuestionTemplateFormView(HorillaFormView):
    """
    Form view
    """

    model = QuestionTemplate
    form_class = QuestionTemplateForm

    new_display_title = _("Add Question Template")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit Question Template")
        return context

    def form_valid(self, form: QuestionTemplateForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Question Template Updated Successfully")
                form.save()
                messages.success(self.request, _(message))
                return self.HttpResponse()
            else:
                message = _("Question Template Created Successfully")
                form.save()
                messages.success(self.request, _(message))
                detail_url = form.instance.get_detail_url()
                return self.HttpResponse(
                    f'<script>window.location.href="{detail_url}"</script>'
                )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.view_questiontemplate"), name="dispatch")
class QuestionListView(HorillaListView):
    """
    List view of the questions of a question template
    """

    model = Question
    filter_class = QuestionFilter
    view_id = "questionList"
    action_method = "action_col"
    bulk_select_option = False

    columns = [
        (_("Question Type"), "get_question_type_display"),
        (_("Question"), "get_question_col"),
    ]

    header_attrs = {
        "get_question_col": """
                    style="width:70% !important"
                    """,
        "get_question_type_display": """
                    style="width:160px !important"
                    """,
        "action": """
                    style="width:110px !important"
                    """,
    }

    sortby_mapping = [
        (_("Question"), "question"),
        (_("Question Type"), "question_type"),
    ]

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        self.queryset = (
            super()
            .get_queryset(queryset, filtered, *args, **kwargs)
            .filter(template_id=self.kwargs["template_id"])
            .prefetch_related(
                Prefetch("question_options", to_attr="prefetched_options")
            )
            .order_by("-id")
        )
        return self.queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("pms.view_questiontemplate"), name="dispatch")
class QuestionListNav(HorillaNavView):
    """
    Nav bar of the questions list
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        template_id = kwargs.get("template_id")
        question_template = QuestionTemplate.objects.filter(pk=template_id).first()
        self.nav_title = _("Questions")
        if question_template:
            self.nav_title = f"{_('Questions')} - {question_template.question_template}"
        self.search_url = reverse(
            "question-list-view", kwargs={"template_id": template_id}
        )
        if self.request.user.has_perm("pms.add_question") or is_reportingmanager(
            self.request
        ):
            self.create_attrs = f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            hx-get="{reverse('question-form-create', kwargs={'template_id': template_id})}"
                            """

    create_label = _("Add Question")
    filter_instance = QuestionFilter()
    search_swap_target = "#listContainer"
    template_name = "generic/inline_nav.html"


@method_decorator(login_required, name="dispatch")
class QuestionFormView(HorillaFormView):
    """
    Create and edit form of a question
    """

    model = Question
    form_class = QuestionModalForm
    new_display_title = _("Add Question")
    view_id = "questionForm"

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        perm = "pms.change_question" if pk else "pms.add_question"
        if not (request.user.has_perm(perm) or is_reportingmanager(request)):
            messages.info(request, _("You don't have permission."))
            return HorillaRedirect(request)

        if pk:
            question = (
                Question.objects.filter(pk=pk).select_related("template_id").first()
            )
            self.question_template = question.template_id if question else None
        else:
            self.question_template = QuestionTemplate.objects.filter(
                pk=kwargs.get("template_id")
            ).first()
        if not self.question_template:
            messages.error(request, _("Question template does not exist"))
            return HorillaRedirect(request)

        if (
            not pk
            and Feedback.objects.filter(
                question_template_id=self.question_template
            ).exists()
        ):
            messages.info(request, _("Question template is used in feedback."))
            return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Question")
        return context

    def form_valid(self, form: QuestionModalForm) -> HttpResponse:
        if form.is_valid():
            question = form.save(commit=False)
            is_update = bool(question.pk)
            if not is_update:
                question.template_id = self.question_template
            question.save()

            if question.question_type == "4":
                options, created = QuestionOptions.objects.get_or_create(
                    question_id=question
                )
                options.option_a = form.cleaned_data["option_a"]
                options.option_b = form.cleaned_data["option_b"]
                options.option_c = form.cleaned_data["option_c"]
                options.option_d = form.cleaned_data["option_d"]
                options.save()
            else:
                QuestionOptions.objects.filter(question_id=question).delete()

            messages.success(
                self.request,
                (
                    _("Question updated successfully.")
                    if is_update
                    else _("Question created successfully.")
                ),
            )
            return self.HttpResponse()
        return super().form_valid(form)
