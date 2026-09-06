"""
surveys.py

This module is used to write views related to the survey features
"""

import json
import os
from datetime import datetime
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.methods import closest_numbers
from horilla.decorators import (
    hx_request_required,
    is_recruitment_manager,
    login_required,
    permission_required,
)
from horilla.http import HorillaRedirect
from recruitment.filters import SurveyFilter
from recruitment.forms import (
    AddQuestionForm,
    ApplicationForm,
    QuestionForm,
    SurveyForm,
    SurveyPreviewForm,
    TemplateForm,
)
from recruitment.models import (
    Candidate,
    JobPosition,
    Recruitment,
    RecruitmentSurvey,
    RecruitmentSurveyAnswer,
    Resume,
    Stage,
    SurveyTemplate,
)
from recruitment.pipeline_grouper import group_by_queryset
from recruitment.views.paginator_qry import paginator_qry


@login_required
@is_recruitment_manager(perm="recruitment.add_recruitmentsurvey")
def survey_form(request):
    """
    This method is used to render survey wform
    """
    recruitment_id = request.GET.get("recId")
    recruitment = Recruitment.find(recruitment_id)
    if not recruitment_id or not recruitment:
        message = (
            _("Missing Recruitment ID")
            if not recruitment_id
            else _("No Recruitment found matching the query.")
        )
        return HorillaRedirect(request, message=message)

    form = SurveyForm(recruitment=recruitment).form
    return render(request, "survey/form.html", {"form": form})


@login_required
@is_recruitment_manager(perm="recruitment.add_recruitmentsurvey")
def survey_preview(request, pk=None):
    """
    Used to render survey form to the candidate
    """
    title = request.GET.get("title")
    template = SurveyTemplate.objects.filter(title=title).first()
    if not title or not template:
        message = (
            _("Missing Survey Template Title")
            if not title
            else _("No Survey Template found matching the query.")
        )
        return HorillaRedirect(request, message=message)

    form = SurveyPreviewForm(template=template).form
    preview_template = "survey/survey_preview.html"
    if request.META.get("HTTP_HX_REQUEST") == "true":
        preview_template = "survey/survey_preview_container.html"
    return render(
        request,
        preview_template,
        {"form": form, "template": template},
    )


@login_required
def question_order_update(request):
    if request.method == "POST":
        # Extract data from the request
        question_id = request.POST.get("question_id")
        new_position = int(request.POST.get("new_position"))
        qs = RecruitmentSurvey.objects.get(id=question_id)

        if qs.sequence > new_position:
            new_position = new_position
        if qs.sequence <= new_position:
            new_position = new_position - 1

        old_qs = RecruitmentSurvey.objects.filter(sequence=new_position)
        for i in old_qs:

            i.sequence = new_position + 1
            i.save()
        qs.sequence = int(new_position)
        qs.save()
        return JsonResponse(
            {"success": True, "message": "Question order updated successfully"}
        )

    return JsonResponse({"error": "Invalid request method"}, status=405)


def candidate_survey(request):
    """
    Used to render survey form to the candidate
    """
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB in bytes
    if not request.session.get("candidate"):
        return HorillaRedirect(
            request, message=_("No candidate found matching the query.")
        )
    candidate_json = request.session["candidate"]
    candidate_dict = json.loads(candidate_json)
    rec_id = candidate_dict[0]["fields"]["recruitment_id"]
    job_id = candidate_dict[0]["fields"]["job_position_id"]
    job = JobPosition.objects.get(id=job_id)
    recruitment = Recruitment.objects.get(id=rec_id)
    stage_id = candidate_dict[0]["fields"]["stage_id"]
    created_by = candidate_dict[0]["fields"].get("created_by")
    modified_by = candidate_dict[0]["fields"].get("modified_by")
    candidate_dict[0]["fields"]["recruitment_id"] = recruitment
    candidate_dict[0]["fields"]["job_position_id"] = job
    candidate_dict[0]["fields"]["stage_id"] = Stage.objects.get(id=stage_id)
    UserModel = get_user_model()
    if created_by:
        candidate_dict[0]["fields"]["created_by"] = UserModel(id=created_by)
    if modified_by:
        candidate_dict[0]["fields"]["modified_by"] = UserModel(id=modified_by)
    candidate = Candidate(**candidate_dict[0]["fields"])
    form = SurveyForm(recruitment=recruitment).form
    if request.method == "POST":
        if not Candidate.objects.filter(
            email=candidate.email, recruitment_id=candidate.recruitment_id
        ).exists():
            candidate.save()
        else:
            candidate = Candidate.objects.filter(
                email=candidate.email, recruitment_id=candidate.recruitment_id
            ).first()
        answer = (
            RecruitmentSurveyAnswer()
            if candidate.recruitmentsurveyanswer_set.first() is None
            else candidate.recruitmentsurveyanswer_set.first()
        )
        answer.candidate_id = candidate

        # Process the POST data to properly handle multiple values
        answer_data = {}
        for key, value in request.POST.items():
            if key.startswith("multiple_choices_"):
                parts = key.split("_", 2)
                question_text = parts[2]
                selected_choices = request.POST.getlist(key)
                answer_data[question_text] = selected_choices
            elif key.startswith("date_"):
                parts = key.split("_", 1)
                question_text = parts[1]
                selected_choices = request.POST.getlist(key)
                if selected_choices and selected_choices[0] != "":
                    formatted_dates = [
                        datetime.strptime(date, "%Y-%m-%d").strftime("%d-%m-%Y")
                        for date in selected_choices
                    ]
                    answer_data[question_text] = formatted_dates
            else:
                answer_data[key] = [value]
        for key, value in request.FILES.items():
            attachment = request.FILES[key]
            if attachment.size > MAX_FILE_SIZE:
                messages.error(
                    request, _("File size exceeds the limit. Maximum size is 5 MB")
                )
                return render(
                    request,
                    "survey/candidate_survey_form.html",
                    {"form": form, "candidate": candidate},
                )
            attachment_path = f"recruitment_attachment/{attachment.name}"
            attachment_dir = os.path.dirname(default_storage.path(attachment_path))
            if not os.path.exists(attachment_dir):
                os.makedirs(attachment_dir)
            with default_storage.open(attachment_path, "wb+") as destination:
                for chunk in attachment.chunks():
                    destination.write(chunk)
            answer.attachment = attachment_path
            answer_data[key] = [attachment_path]
        answer.answer_json = json.dumps(answer_data)
        answer.save()
        messages.success(request, _("Your answers are submitted."))
        return render(
            request,
            "candidate/success.html",
            {"candidate": candidate, "recruitment": recruitment},
        )
    return render(
        request,
        "survey/candidate_survey_form.html",
        {"form": form, "candidate": candidate},
    )


@login_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def view_question_template(request):
    """
    This method is used to view the question template
    """
    recs = Recruitment.objects.all()
    ids = []
    for i in recs:
        for manager in i.recruitment_managers.all():
            if request.user.employee_get == manager:
                ids.append(i.id)
    if request.user.has_perm("recruitment.view_recruitmentsurvey"):
        questions = RecruitmentSurvey.objects.all()
    else:
        questions = RecruitmentSurvey.objects.filter(recruitment_ids__in=ids)
    # See the matching fix/comment in recruitment/views/search.py's
    # filter_survey() - group_by_queryset() already paginates correctly, but
    # the unused (0-question) templates it can't see get appended afterward
    # and the combined list gets paginated a second time on the same
    # "template_page" param, so page 2+ silently lost has_previous. Fetch
    # every templates-with-questions group here (unpaginated) and paginate
    # the merged list exactly once below instead.
    templates = group_by_queryset(
        questions.filter(template_id__isnull=False).distinct(),
        "template_id__title",
        page=1,
        page_name="template_page",
        records_per_page=1000000,
    )
    all_template_object_list = []
    for template in templates:
        all_template_object_list.append(template)

    survey_templates = SurveyTemplate.objects.all()
    all_templates = survey_templates.values_list("title", flat=True)
    used_templates = questions.values_list("template_id__title", flat=True)

    unused_templates = list(set(all_templates) - set(used_templates))
    unused_groups = []
    for template_name in unused_templates:
        unused_groups.append(
            {
                "grouper": template_name,
                "list": [],
                "dynamic_name": "",
            }
        )
    all_template_object_list = all_template_object_list + unused_groups

    templates = paginator_qry(
        all_template_object_list, request.GET.get("template_page")
    )
    survey_templates = paginator_qry(
        survey_templates, request.GET.get("survey_template_page")
    )
    filter_obj = SurveyFilter()
    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                questions, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        "survey/view_question_templates.html",
        {
            "questions": paginator_qry(questions, request.GET.get("page")),
            "templates": templates,
            "survey_templates": survey_templates,
            "f": filter_obj,
            "requests_ids": requests_ids,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.change_recruitmentsurvey")
def update_question_template(request, survey_id):
    """
    This view method is used to update question template
    """
    instance = RecruitmentSurvey.objects.get(id=survey_id)
    form = QuestionForm(
        instance=instance,
    )
    if request.method == "POST":
        form = QuestionForm(request.POST, instance=instance)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.save()
            instance.template_id.set(form.cleaned_data["template_id"])
            instance.recruitment_ids.set(form.recruitment)
            # instance.job_position_ids.set(form.job_positions)
            messages.success(request, _("New survey question updated."))
            return HorillaRedirect(request)
    return render(request, "survey/template_update_form.html", {"form": form})


@login_required
@hx_request_required
@permission_required(perm="recruitment.add_recruitmentsurvey")
def create_question_template(request):
    """
    This view method is used to create question template
    """
    form = QuestionForm()
    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.save()
            instance.recruitment_ids.set(form.recruitment)
            instance.template_id.set(form.cleaned_data["template_id"])
            # instance.job_position_ids.set(form.job_positions)
            messages.success(request, _("New survey question created."))
            return HorillaRedirect(request)
    return render(request, "survey/template_form.html", {"form": form})


@login_required
@hx_request_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def survey_template_tab(request):
    """
    Root of the Template tab: loads its own navbar, then its own list
    container.
    """
    return render(request, "survey/template_tab_root.html", {})


@login_required
@hx_request_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def survey_template_tab_list(request):
    """
    Template accordion content for the Template tab, and the hx-get target
    for that tab's own navbar (recruitment.cbv.recruitment_survey.SurveyTemplateNavView)
    search box and pagination.
    """
    survey_templates = SurveyTemplate.objects.all()
    search = request.GET.get("search", "").strip()
    if search:
        survey_templates = survey_templates.filter(title__icontains=search)
    questions = SurveyFilter(request.GET, RecruitmentSurvey.objects.all()).qs

    previous_data = request.GET.urlencode()
    templates = group_by_queryset(
        questions.filter(template_id__isnull=False).distinct(),
        "template_id__title",
        page=1,
        page_name="template_page",
        records_per_page=1000000,
    )
    all_template_object_list = list(templates)

    all_templates = survey_templates.values_list("title", flat=True)
    used_templates = questions.values_list("template_id__title", flat=True)
    unused_templates = list(set(all_templates) - set(used_templates))
    for template_name in unused_templates:
        all_template_object_list.append(
            {"grouper": template_name, "list": [], "dynamic_name": ""}
        )

    templates = paginator_qry(
        all_template_object_list, request.GET.get("template_page")
    )
    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                questions, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        "survey/template_accordion.html",
        {
            "templates": templates,
            "pd": previous_data,
            "requests_ids": requests_ids,
        },
    )


@login_required
@hx_request_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def survey_question_tab(request):
    """
    Root of the Questions tab: loads its own navbar, then its own list
    container.
    """
    return render(request, "survey/question_tab_root.html", {})


@login_required
@hx_request_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def survey_question_tab_list(request):
    """
    Question grid content for the Questions tab, and the hx-get target for
    that tab's own navbar (recruitment.cbv.recruitment_survey.SurveyQuestionNavView)
    search box and pagination.
    """
    if request.user.has_perm("recruitment.view_recruitmentsurvey"):
        questions = RecruitmentSurvey.objects.all()
    else:
        ids = []
        for recruitment in Recruitment.objects.all():
            for manager in recruitment.recruitment_managers.all():
                if request.user.employee_get == manager:
                    ids.append(recruitment.id)
        questions = RecruitmentSurvey.objects.filter(recruitment_ids__in=ids)

    questions = SurveyFilter(request.GET, questions).qs

    previous_data = request.GET.urlencode()
    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                questions, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        "survey/question_card.html",
        {
            "questions": paginator_qry(questions, request.GET.get("page")),
            "pd": previous_data,
            "requests_ids": requests_ids,
        },
    )


@login_required
@permission_required(perm="recruitment.delete_recruitmentsurvey")
def delete_survey_question(request, survey_id):
    """
    This method is used to delete the survey instance
    """
    try:
        RecruitmentSurvey.objects.get(id=survey_id).delete()
        messages.success(request, _("Question was deleted successfully"))
    except RecruitmentSurvey.DoesNotExist:
        messages.error(request, _("Question not found."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this question"))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        # Reached from two different places sharing this one delete route -
        # a question row nested inside the Templates accordion, and a
        # question card on the Questions tab - each targeting its own list
        # container. Redirect back to whichever list actually asked, so
        # only that container is refreshed.
        hx_target = request.META.get("HTTP_HX_TARGET")
        if hx_target == "survey-templates-container":
            return redirect(reverse("list-survey-templates"))
        # Restored previous implementation's containers (view_question_templates.html)
        if hx_target == "view-container":
            return redirect(reverse("survey-template-tab-list"))
        if hx_target == "questionViewContainer":
            return redirect(reverse("survey-question-tab-list"))
        return redirect(reverse("list-survey-questions"))
    return redirect("recruitment-survey-question-template-view")


def application_form(request):
    """
    This method renders candidate form to create candidate
    """
    recruitment = None
    recruitment_id = request.GET.get("recruitmentId")
    resume_id = request.GET.get("resumeId")
    # Scoped to the recruitment being applied to. This page is public and
    # unauthenticated, and the POST branch below reads this file and attaches
    # it to the submitted application -- so an unscoped lookup let anyone
    # harvest any CV in the database, in any company, by walking sequential
    # ids. Resume has no company_id of its own, so the recruitment is what
    # scopes it.
    resume_obj = (
        Resume.objects.filter(id=resume_id, recruitment_id=recruitment_id).first()
        if resume_id and recruitment_id
        else None
    )

    if request.method == "GET" and not recruitment_id:
        messages.error(request, _("Recruitment ID is missing"))
        return redirect("open-recruitments")

    try:
        recruitment = Recruitment.objects.filter(
            id=recruitment_id, is_published=True
        ).first()  # Only create applications for published recruitments.
        if not recruitment:
            messages.error(request, _("Recruitment not found"))
            return redirect("open-recruitments")
    except (ValueError, OverflowError):
        messages.error(request, _("Invalid Recruitment ID"))
        return redirect("open-recruitments")

    if request.POST:
        if "resume" not in request.FILES and resume_id:
            if resume_obj and resume_obj.file:
                file_content = resume_obj.file.read()
                pdf_file = SimpleUploadedFile(
                    resume_obj.file.name, file_content, content_type="application/pdf"
                )
                request.FILES["resume"] = pdf_file

        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            candidate_obj = form.save(commit=False)
            # Mirrors the internal "add candidate" form always tagging
            # itself "software" (recruitment/views/views.py) -- without
            # this, every public career-page applicant leaves `source`
            # NULL, which is why "Source of Hire" on the dashboard only
            # ever had a "Not Specified" slice to show.
            candidate_obj.source = "application"
            recruitment_obj = candidate_obj.recruitment_id
            stages = recruitment_obj.stage_set.all()
            if stages.filter(stage_type="applied").exists():
                candidate_obj.stage_id = stages.filter(stage_type="applied").first()
            else:
                candidate_obj.stage_id = stages.order_by("sequence").first()
            messages.success(request, _("Application saved."))
            candidate_obj.save()  # 945
            request.session["candidate"] = serializers.serialize(
                "json", [candidate_obj]
            )
            has_direct_survey = RecruitmentSurvey.objects.filter(
                recruitment_ids=recruitment_id
            ).exists()
            has_template_survey = RecruitmentSurvey.objects.filter(
                template_id__in=recruitment.survey_templates.all()
            ).exists()
            if has_direct_survey or has_template_survey:
                return redirect(candidate_survey)
            candidate_obj.save()

            if resume_obj:
                resume_obj.is_candidate = True
                resume_obj.save()

            return render(
                request,
                "candidate/success.html",
                {"candidate": candidate_obj, "recruitment": recruitment_obj},
            )
        for field_name, field_errors in form.errors.items():
            if field_name == "__all__":
                for error in field_errors:
                    messages.error(request, error)
            else:
                field_label = (
                    form.fields.get(field_name).label
                    if form.fields.get(field_name)
                    else field_name
                )
                for error in field_errors:
                    messages.error(
                        request,
                        _("%(field_label)s: %(error)s")
                        % {"field_label": field_label, "error": error},
                    )
        recruitment_for_job_position = form.data.get("recruitment_id") or recruitment_id
        if recruitment_for_job_position:
            recruitment_for_job_position = Recruitment.objects.filter(
                id=recruitment_for_job_position
            ).first()
            if recruitment_for_job_position:
                form.fields["job_position_id"].queryset = (
                    recruitment_for_job_position.open_positions.all()
                )
    else:
        # 811
        initial_data = {"resume": resume_obj.file.url} if resume_obj else {}
        form = ApplicationForm(initial=initial_data)

    return render(
        request,
        "candidate/application_form.html",
        {"form": form, "recruitment": recruitment, "resume": resume_obj},
    )


@login_required
@hx_request_required
@is_recruitment_manager(perm="recruitment.view_recruitmentsurvey")
def single_survey(request, survey_id):
    """
    This view method is used to single view of question template
    """
    question = RecruitmentSurvey.objects.get(id=survey_id)
    requests_ids_json = request.GET.get("instances_ids")
    context = {"question": question}
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, survey_id)
        context["previous"] = previous_id
        context["next"] = next_id
        context["requests_ids"] = requests_ids_json
    return render(request, "survey/view_single_template.html", context)


@login_required
@hx_request_required
def create_template(request):
    """
    Create question template views
    """
    # Check if the user has any of the two permissions
    if not (
        request.user.has_perm("recruitment.add_surveytemplate")
        or request.user.has_perm("recruitment.change_surveytemplate")
    ):
        messages.info(request, _("You dont have permission."))
        return HorillaRedirect(request)

    title = request.GET.get("title")
    instance = None
    if title:
        instance = SurveyTemplate.objects.filter(title=title).first()
    form = TemplateForm(instance=instance)
    if request.method == "POST":
        form = TemplateForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Template saved"))
            return HorillaRedirect(request)
    return render(request, "survey/main_form.html", {"form": form})


@login_required
@permission_required("recruitment.delete_surveytemplate")
def delete_template(request):
    """
    This method is used to delete the survey template group
    """
    title = request.GET.get("title")
    SurveyTemplate.objects.filter(title=str(title)).delete()
    if title == "None":
        messages.info(request, _("This template group cannot be deleted"))
    else:
        messages.success(request, _("Template group deleted"))

    if request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponse(
            "<script>$('#templateTabRoot .filterButton').click();</script>"
        )
    return HorillaRedirect(request)


@login_required
@permission_required("recruitment.delete_surveytemplate")
def delete_survey_template(request, pk):
    """
    This method is used to delete a single survey template by its pk, used
    by the Survey Templates page's Templates accordion.
    """
    template = SurveyTemplate.objects.filter(pk=pk).first()
    if template is None:
        messages.error(request, _("Template not found."))
    elif template.is_general_template:
        messages.info(request, _("This template group cannot be deleted"))
    else:
        template.delete()
        messages.success(request, _("Template group deleted"))

    if request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponse(
            "<script>$('#templateTabRoot .filterButton').click();</script>"
        )
    return HorillaRedirect(request)


@login_required
@hx_request_required
@permission_required("recruitment.change_surveytemplate")
def question_add(request):
    """
    This method is used to add survey question to the templates
    """
    template = None
    title = request.GET.get("title")
    if title:
        template = SurveyTemplate.objects.filter(title=title).first()

    form = AddQuestionForm(initial={"template_ids": template})
    if request.method == "POST":
        form = AddQuestionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Question added"))
            if request.META.get("HTTP_HX_REQUEST") == "true":
                return HttpResponse(
                    "<script>"
                    "$('#genericModal').removeClass('oh-modal--show');"
                    "$('#reloadMessagesButton').click();"
                    "$('.reload-record').click();"
                    "</script>"
                )
            return HorillaRedirect(request)
    return render(request, "survey/add_form.html", {"form": form})
