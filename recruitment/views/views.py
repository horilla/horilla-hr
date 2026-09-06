"""
views.py

This module contains the view functions for handling HTTP requests and rendering
responses in your application.

Each view function corresponds to a specific URL route and performs the necessary
actions to handle the request, process data, and generate a response.

This module is part of the recruitment project and is intended to
provide the main entry points for interacting with the application's functionality.
"""

import ast
import contextlib
import io
import json
import os
import random
import re
from datetime import date, datetime
from itertools import chain
from urllib.parse import parse_qs

import phonenumbers
import pycountry
import pymupdf  # type: ignore
import spacy
from dateutil import parser as dateutil_parser
from django import template
from django.contrib import messages
from django.core import serializers
from django.core.cache import cache as CACHE
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, ProtectedError, Q, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from rapidfuzz import fuzz

from base.backends import ConfiguredEmailBackend
from base.context_processors import check_candidate_self_tracking
from base.countries import country_arr, s_a, states
from base.forms import MailTemplateForm
from base.methods import (
    build_safe_template_request,
    eval_validate,
    export_data,
    generate_pdf,
    get_key_instances,
    sanitize_mail_template_body,
    sortby,
)
from base.models import EmailLog, HorillaMailTemplate, JobPosition, clear_messages
from employee.models import Employee, EmployeeWorkInformation
from employee.views import get_content_type
from horilla import settings
from horilla.decorators import (
    any_permission_required,
    hx_request_required,
    logger,
    login_required,
    permission_required,
)
from horilla.group_by import group_by_queryset
from horilla.http import HorillaRedirect
from horilla_auth.models import HorillaUser
from horilla_documents.models import Document
from notifications.signals import notify
from recruitment.auth import CandidateAuthenticationBackend
from recruitment.decorators import (
    all_manager_can_enter,
    candidate_login_required,
    manager_can_enter,
    recruitment_manager_can_enter,
)
from recruitment.filters import (
    CandidateFilter,
    CandidateReGroup,
    InterviewFilter,
    RecruitmentFilter,
    SkillZoneCandFilter,
    SkillZoneFilter,
    StageFilter,
)
from recruitment.forms import (
    AddCandidateForm,
    CandidateCreationForm,
    CandidateDocumentForm,
    CandidateDocumentRejectForm,
    CandidateDocumentRequestForm,
    CandidateDocumentUpdateForm,
    CandidateExportForm,
    RecruitmentCreationForm,
    RejectReasonForm,
    ResumeForm,
    ScheduleInterviewForm,
    SkillsForm,
    SkillZoneCandidateForm,
    SkillZoneCreateForm,
    StageCreationForm,
    StageNoteForm,
    StageNoteUpdateForm,
    ToSkillZoneForm,
)
from recruitment.methods import recruitment_manages
from recruitment.models import (
    Candidate,
    CandidateDocument,
    CandidateRating,
    InterviewSchedule,
    LinkedInAccount,
    Recruitment,
    RecruitmentGeneralSetting,
    RecruitmentSurvey,
    RecruitmentSurveyAnswer,
    RejectedCandidate,
    RejectReason,
    Resume,
    Skill,
    SkillZone,
    SkillZoneCandidate,
    Stage,
    StageFiles,
    StageNote,
)
from recruitment.views.linkedin import delete_post, post_recruitment_in_linkedin
from recruitment.views.paginator_qry import paginator_qry


def is_stagemanager(request, stage_id=False):
    """
    This method is used to identify the employee is a stage manager or
    not, if stage_id is passed through args, method will
    check the employee is manager to the corresponding stage, return
    tuple with boolean and all stages that employee is manager.
    if called this method without stage_id args it will return boolean
     with all the stage that the employee is stage manager
    Args:
        request : django http request
        stage_id : stage instance id
    """
    user = request.user
    employee = user.employee_get
    if not stage_id:
        return (
            employee.stage_set.exists() or user.is_superuser,
            employee.stage_set.all(),
        )
    stage_obj = Stage.objects.get(id=stage_id)
    return (
        employee in stage_obj.stage_managers.all()
        or user.is_superuser
        or is_recruitmentmanager(request, rec_id=stage_obj.recruitment_id.id)[0],
        employee.stage_set.all(),
    )


def is_recruitmentmanager(request, rec_id=False):
    """
    This method is used to identify the employee is a recruitment
    manager or not, if rec_id is passed through args, method will
    check the employee is manager to the corresponding recruitment,
    return tuple with boolean and all recruitment that employee is manager.
    if called this method without recruitment args it will return
    boolean with all the recruitment that the employee is recruitment manager
    Args:
        request : django http request
        rec_id : recruitment instance id
    """
    user = request.user
    employee = user.employee_get
    if not rec_id:
        return (
            employee.recruitment_set.exists() or user.is_superuser,
            employee.recruitment_set.all(),
        )
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    return (
        employee in recruitment_obj.recruitment_managers.all() or user.is_superuser,
        employee.recruitment_set.all(),
    )


def pipeline_grouper(request, recruitments):
    groups = []
    for rec in recruitments:
        stages_qs = StageFilter(request.GET, queryset=rec.stage_set.all()).qs.order_by(
            "sequence"
        )
        stages = list(stages_qs)
        all_stages_grouper = []
        data = {"recruitment": rec, "stages": []}
        for stage in stages:
            all_stages_grouper.append({"grouper": stage, "list": []})
            stage_candidates = CandidateFilter(
                request.GET,
                stage.candidate_set.filter(
                    is_active=True,
                ),
            ).qs.order_by("sequence")

            page_name = "page" + stage.stage + str(rec.id)
            grouper = group_by_queryset(
                stage_candidates,
                "stage_id",
                request.GET.get(page_name),
                page_name,
            ).object_list
            data["stages"] = data["stages"] + grouper

        ordered_data = []

        # combining un used groups in to the grouper
        groupers = data["stages"]
        for stage in stages:
            found = False
            for grouper in groupers:
                if grouper["grouper"] == stage:
                    ordered_data.append(grouper)
                    found = True
                    break
            if not found:
                ordered_data.append({"grouper": stage})
        data = {
            "recruitment": rec,
            "stages": ordered_data,
        }
        groups.append(data)
    return groups


@login_required
@hx_request_required
@permission_required(perm="recruitment.add_recruitment")
def recruitment(request):
    """
    This method is used to create recruitment, when create recruitment this method
    add  recruitment view,create candidate, change stage sequence and so on, some of
    the permission is checking manually instead of using django permission permission
    to the  recruitment managers
    """
    form = RecruitmentCreationForm()
    if request.GET:
        form = RecruitmentCreationForm(initial=request.GET.dict())
    dynamic = (
        request.GET.get("dynamic") if request.GET.get("dynamic") != "None" else None
    )
    if request.method == "POST":
        form = RecruitmentCreationForm(request.POST)
        if form.is_valid():
            recruitment_obj = form.save()
            recruitment_obj.recruitment_managers.set(
                Employee.objects.filter(
                    id__in=form.data.getlist("recruitment_managers")
                )
            )
            recruitment_obj.open_positions.set(
                JobPosition.objects.filter(id__in=form.data.getlist("open_positions"))
            )
            if (
                recruitment_obj.publish_in_linkedin
                and recruitment_obj.linkedin_account_id
            ):
                post_recruitment_in_linkedin(
                    request, recruitment_obj, recruitment_obj.linkedin_account_id
                )
            for survey in form.cleaned_data["survey_templates"]:
                for sur in survey.recruitmentsurvey_set.all():
                    sur.recruitment_ids.add(recruitment_obj)
            messages.success(request, _("Recruitment added."))
            with contextlib.suppress(Exception):
                managers = recruitment_obj.recruitment_managers.select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb="You are chosen as one of recruitment manager",
                    verb_ar="تم اختيارك كأحد مديري التوظيف",
                    verb_de="Sie wurden als einer der Personalvermittler ausgewählt",
                    verb_es="Has sido elegido/a como uno de los gerentes de contratación",
                    verb_fr="Vous êtes choisi(e) comme l'un des responsables du recrutement",
                    icon="people-circle",
                    redirect=reverse("pipeline"),
                )
            return HorillaRedirect(request)
    return render(
        request, "recruitment/recruitment_form.html", {"form": form, "dynamic": dynamic}
    )


@login_required
@permission_required(perm="recruitment.view_recruitment")
def recruitment_view(request):
    """
    This method is used to  render all recruitment to view
    """
    if not request.GET:
        request.GET.copy().update({"is_active": "on"})
    queryset = Recruitment.objects.filter(is_active=True)
    if Recruitment.objects.all():
        template = "recruitment/recruitment_view.html"
    else:
        template = "recruitment/recruitment_empty.html"
    initial_tag = {}
    if request.GET.get("closed") == "false":
        queryset = queryset.filter(closed=True)
        initial_tag["closed"] = ["true"]
    else:
        queryset = queryset.filter(closed=False)
        initial_tag["closed"] = ["false"]

    filter_obj = RecruitmentFilter(request.GET, queryset)
    filter_dict = request.GET.copy()
    for key, value in initial_tag.items():
        filter_dict[key] = value

    return render(
        request,
        template,
        {
            "data": paginator_qry(filter_obj.qs, request.GET.get("page")),
            "f": filter_obj,
            "filter_dict": filter_dict,
            "pd": request.GET.urlencode() + "&closed=false",
        },
    )


@login_required
@permission_required(perm="recruitment.change_recruitment")
@hx_request_required
def recruitment_update(request, rec_id):
    """
    This method is used to update the recruitment, when updating the recruitment,
    any changes in manager is exists then permissions also assigned to the manager
    Args:
        id : recruitment_id
    """
    recruitment_obj = Recruitment.find(rec_id)
    if not recruitment_obj:
        messages.error(
            request, _("The recruitment entry you are trying to edit does not exist.")
        )
        return HorillaRedirect(request)
    survey_template_list = []
    survey_templates = RecruitmentSurvey.objects.filter(
        recruitment_ids=rec_id
    ).distinct()
    for survey in survey_templates:
        survey_template_list.append(survey.template_id.all())
    form = RecruitmentCreationForm(instance=recruitment_obj)
    if request.GET:
        form = RecruitmentCreationForm(request.GET)
    dynamic = (
        request.GET.get("dynamic") if request.GET.get("dynamic") != "None" else None
    )
    if request.method == "POST":
        form = RecruitmentCreationForm(request.POST, instance=recruitment_obj)
        if form.is_valid():
            recruitment_obj = form.save()
            for survey in form.cleaned_data["survey_templates"]:
                for sur in survey.recruitmentsurvey_set.all():
                    sur.recruitment_ids.add(recruitment_obj)
            recruitment_obj.save()
            if len(form.changed_data) > 0:
                if (
                    recruitment_obj.publish_in_linkedin
                    and recruitment_obj.linkedin_account_id
                ):
                    delete_post(recruitment_obj)
                    post_recruitment_in_linkedin(
                        request, recruitment_obj, recruitment_obj.linkedin_account_id
                    )
            messages.success(request, _("Recruitment Updated."))
            response = render(
                request, "recruitment/recruitment_form.html", {"form": form}
            )
            with contextlib.suppress(Exception):
                managers = recruitment_obj.recruitment_managers.select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb=f"{recruitment_obj} is updated, You are chosen as one of the managers",
                    verb_ar=f"{recruitment_obj} تم تحديثه، تم اختيارك كأحد المديرين",
                    verb_de=f"{recruitment_obj} wurde aktualisiert. Sie wurden als\
                            einer der Manager ausgewählt",
                    verb_es=f"{recruitment_obj} ha sido actualizado/a. Has sido elegido\
                            a como uno de los gerentes",
                    verb_fr=f"{recruitment_obj} a été mis(e) à jour. Vous êtes choisi(e) comme\
                            l'un des responsables",
                    icon="people-circle",
                    redirect=reverse("pipeline"),
                )

            return HttpResponse(
                response.content.decode("utf-8") + "<script>location.reload();</script>"
            )
    return render(
        request,
        "recruitment/recruitment_update_form.html",
        {"form": form, "dynamic": dynamic},
    )


def paginator_qry_recruitment_limited(qryset, page_number):
    """
    This method is used to generate common paginator limit.
    """
    paginator = Paginator(qryset, 4)
    qryset = paginator.get_page(page_number)
    return qryset


user_recruitments = {}


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def recruitment_pipeline(request):
    """
    This method is used to filter out candidate through pipeline structure
    """
    filter_obj = RecruitmentFilter(
        request.GET,
    )
    if filter_obj.qs.exists():
        template = "pipeline/pipeline.html"
    else:
        template = "pipeline/pipeline_empty.html"
    stage_filter = StageFilter(request.GET)
    candidate_filter = CandidateFilter(request.GET)
    recruitments = paginator_qry_recruitment_limited(
        filter_obj.qs, request.GET.get("page")
    )

    now = timezone.now()

    return render(
        request,
        template,
        {
            "rec_filter_obj": filter_obj,
            "recruitment": recruitments,
            "stage_filter_obj": stage_filter,
            "candidate_filter_obj": candidate_filter,
            "now": now,
        },
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.view_recruitment")
def filter_pipeline(request):
    """
    This method is used to search/filter from pipeline
    """
    filter_obj = RecruitmentFilter(request.GET)
    stage_filter = StageFilter(request.GET)
    candidate_filter = CandidateFilter(request.GET)
    view = request.GET.get("view")
    recruitments = filter_obj.qs.filter(is_active=True)
    if not request.user.has_perm("recruitment.view_recruitment"):
        recruitments = recruitments.filter(
            Q(recruitment_managers=request.user.employee_get)
        )
        stage_recruitment_ids = (
            stage_filter.qs.filter(stage_managers=request.user.employee_get)
            .values_list("recruitment_id", flat=True)
            .distinct()
        )
        recruitments = recruitments | filter_obj.qs.filter(id__in=stage_recruitment_ids)
        recruitments = recruitments.filter(is_active=True).distinct()

    closed = request.GET.get("closed")
    filter_dict = parse_qs(request.GET.urlencode())
    filter_dict = get_key_instances(Recruitment, filter_dict)

    CACHE.set(
        request.session.session_key + "pipeline",
        {
            "candidates": candidate_filter.qs.filter(is_active=True).order_by(
                "sequence"
            ),
            "stages": stage_filter.qs.order_by("sequence"),
            "recruitments": recruitments,
            "filter_dict": filter_dict,
            "filter_query": request.GET,
        },
    )

    previous_data = request.GET.urlencode()
    paginator = Paginator(recruitments, 4)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    template = "pipeline/components/pipeline_search_components.html"
    if request.GET.get("view") == "card":
        template = "pipeline/kanban_components/kanban.html"
    return render(
        request,
        template,
        {
            "recruitment": page_obj,
            "stage_filter_obj": stage_filter,
            "candidate_filter_obj": candidate_filter,
            "filter_dict": filter_dict,
            "status": closed,
            "view": view,
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("recruitment.view_recruitment")
def get_stage_badge_count(request):
    """
    Method to update stage badge count
    """
    stage_id = request.GET.get("stage_id")
    stage = Stage.find(stage_id)
    count = stage.candidate_set.filter(is_active=True).count() if stage else 0
    return HttpResponse(count)


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def stage_component(request, view: str = "list"):
    """
    This method will stage tab contents
    """
    recruitment_id = request.GET.get("rec_id")
    if not recruitment_id or not (recruitment := Recruitment.find(recruitment_id)):
        return HorillaRedirect(
            request,
            message=(
                _("Recruitment ID missing.")
                if not recruitment_id
                else _("No Recruitment found matching the query.")
            ),
        )

    cache_key = request.session.session_key + "pipeline"
    pipeline_cache = CACHE.get(cache_key)
    if pipeline_cache is None:
        pipeline_cache = {
            "stages": StageFilter(request.GET).qs.order_by("sequence"),
            "filter_dict": get_key_instances(
                Recruitment, parse_qs(request.GET.urlencode())
            ),
        }
        CACHE.set(cache_key, pipeline_cache)

    ordered_stages = pipeline_cache["stages"].filter(recruitment_id__id=recruitment_id)
    template = "pipeline/components/stages_tab_content.html"
    if view == "card":
        template = "pipeline/kanban_components/kanban_stage_components.html"
    return render(
        request,
        template,
        {
            "rec": recruitment,
            "ordered_stages": ordered_stages,
            "filter_dict": pipeline_cache.get("filter_dict"),
        },
    )


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def update_candidate_stage_and_sequence(request):
    """Update candidate sequence"""

    order_list = request.GET.getlist("order")
    stage_id = request.GET.get("stage_id")

    pipeline_cache = CACHE.get(request.session.session_key + "pipeline")
    if not pipeline_cache:
        return JsonResponse({"message": _("Pipeline cache expired.")})

    stage = pipeline_cache["stages"].filter(id=stage_id).first()
    if not stage:
        return JsonResponse({"message": _("Stage not found.")})

    context = {}

    for index, cand_id in enumerate(order_list):
        pipeline_cache["candidates"].filter(id=cand_id).update(
            sequence=index, stage_id=stage
        )

    if stage.stage_type == "hired" and stage.recruitment_id.is_vacancy_filled():
        context["message"] = _("Vacancy is filled")
        context["vacancy"] = stage.recruitment_id.vacancy

    return JsonResponse(context)


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def update_candidate_sequence(request):
    """Update candidate sequence"""

    order_list = request.GET.getlist("order")
    stage_id = request.GET.get("stage_id")

    pipeline_cache = CACHE.get(request.session.session_key + "pipeline")
    if not pipeline_cache:
        return JsonResponse({"message": _("Pipeline cache expired.")})

    stage = pipeline_cache["stages"].filter(id=stage_id).first()
    if not stage:
        return JsonResponse({"message": _("Stage not found.")})

    for index, cand_id in enumerate(order_list):
        pipeline_cache["candidates"].filter(id=cand_id).update(
            sequence=index,
            stage_id=stage,
            hired=(stage.stage_type == "hired"),
        )

    return JsonResponse({})


def limited_paginator_qry(queryset, page):
    """
    Limited pagination
    """
    paginator = Paginator(queryset, 10)
    queryset = paginator.get_page(page)
    return queryset


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.view_recruitment")
def candidate_component(request):
    """
    Candidate component
    """
    stage_id = request.GET.get("stage_id")
    cache_key = request.session.session_key + "pipeline"
    cache = CACHE.get(cache_key)
    if cache is None:
        cache = {
            "stages": StageFilter(request.GET).qs.order_by("sequence"),
            "candidates": False,
        }
    if not cache.get("candidates"):
        cache["candidates"] = CandidateFilter(request.GET).qs.filter(is_active=True)
    CACHE.set(cache_key, cache, timeout=600)

    stage = cache["stages"].filter(id=stage_id).first()
    candidates = cache["candidates"].filter(stage_id=stage)

    template = "pipeline/components/candidate_stage_component.html"
    if request.GET.get("view") == "card":
        template = "pipeline/kanban_components/candidate_kanban_components.html"

    now = timezone.now()
    return render(
        request,
        template,
        {
            "candidates": limited_paginator_qry(
                candidates, request.GET.get("candidate_page")
            ),
            "stage": stage,
            "rec": getattr(candidates.first(), "recruitment_id", {}),
            "now": now,
        },
    )


@login_required
@manager_can_enter("recruitment.change_candidate")
def change_candidate_stage(request):
    """
    This method is used to update candidates stage
    """
    if request.method == "POST":
        canIds = request.POST["canIds"]
        stage_id = request.POST["stageId"]
        context = {}
        if request.GET.get("bulk") == "True":
            canIds = json.loads(canIds)
            for cand_id in canIds:
                try:
                    candidate = Candidate.objects.get(id=cand_id)
                    stage = Stage.objects.filter(
                        recruitment_id=candidate.recruitment_id, id=stage_id
                    ).first()
                    if stage:
                        candidate.stage_id = stage
                        candidate.save()
                        if stage.stage_type == "hired":
                            if stage.recruitment_id.is_vacancy_filled():
                                context["message"] = _("Vaccancy is filled")
                                context["vacancy"] = stage.recruitment_id.vacancy
                        messages.success(request, _("Candidate stage updated"))
                except Candidate.DoesNotExist:
                    messages.error(request, _("Candidate not found."))
        else:
            try:
                candidate = Candidate.objects.get(id=canIds)
                stage = Stage.objects.filter(
                    recruitment_id=candidate.recruitment_id, id=stage_id
                ).first()
                if stage:
                    candidate.stage_id = stage
                    candidate.save()
                    if stage.stage_type == "hired":
                        if stage.recruitment_id.is_vacancy_filled():
                            context["message"] = _("Vaccancy is filled")
                            context["vacancy"] = stage.recruitment_id.vacancy
                    candidate.stage_id = stage
                    candidate.save()
                    messages.success(request, _("Candidate stage updated"))
            except Candidate.DoesNotExist:
                messages.error(request, _("Candidate not found."))
        return JsonResponse(context)
    stage_id = request.GET.get("stage_id")
    candidate_id = request.GET.get("candidate_id")
    candidate = Candidate.find(candidate_id)
    if not candidate:
        return HorillaRedirect(
            request, message=_("No Candidate found matching the query.")
        )

    stage = Stage.objects.filter(
        recruitment_id=candidate.recruitment_id, id=stage_id
    ).first()
    if stage:
        candidate.stage_id = stage
        candidate.save()
        messages.success(request, _("Candidate stage updated"))
    return stage_component(request)


@login_required
@permission_required(perm="recruitment.view_recruitment")
def recruitment_pipeline_card(request):
    """
    This method is used to render pipeline card structure.
    """
    search = request.GET.get("search")
    search = search if search is not None else ""
    recruitment_obj = Recruitment.objects.all()
    candidates = Candidate.objects.filter(name__icontains=search, is_active=True)
    stages = Stage.objects.all()
    return render(
        request,
        "pipeline/pipeline_components/pipeline_card_view.html",
        {"recruitment": recruitment_obj, "candidates": candidates, "stages": stages},
    )


@login_required
@permission_required(perm="recruitment.delete_recruitment")
def recruitment_archive(request, rec_id):
    """
    This method is used to archive and unarchive the recruitment
    args:
        rec_id: The id of the Recruitment
    """
    try:
        recruitment = Recruitment.objects.get(id=rec_id)
        if recruitment.is_active:
            recruitment.is_active = False
            messages.success(request, _("Recruitment archived successfully."))
        else:
            recruitment.is_active = True
            messages.success(request, _("Recruitment un-archived successfully."))
        recruitment.save()
    except (Recruitment.DoesNotExist, OverflowError):
        messages.error(request, _("Recruitment Does not exists.."))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponse(
            "<script>"
            "$('#applyFilter').click();"
            "$('#reloadMessagesButton').click();"
            "</script>"
        )
    return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_stage")
def stage_update_pipeline(request, stage_id):
    """
    This method is used to update stage from pipeline view
    """
    stage_obj = Stage.objects.get(id=stage_id)
    form = StageCreationForm(instance=stage_obj)
    if request.POST:
        form = StageCreationForm(request.POST, instance=stage_obj)
        if form.is_valid():
            stage_obj = form.save()
            messages.success(request, _("Stage updated."))
            with contextlib.suppress(Exception):
                managers = stage_obj.stage_managers.select_related("employee_user_id")
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb=f"{stage_obj.stage} stage in recruitment {stage_obj.recruitment_id}\
                            is updated, You are chosen as one of the managers",
                    verb_ar=f"تم تحديث مرحلة {stage_obj.stage} في التوظيف {stage_obj.recruitment_id}\
                            ، تم اختيارك كأحد المديرين",
                    verb_de=f"Die Stufe {stage_obj.stage} in der Rekrutierung {stage_obj.recruitment_id}\
                            wurde aktualisiert. Sie wurden als einer der Manager ausgewählt",
                    verb_es=f"Se ha actualizado la etapa {stage_obj.stage} en la contratación\
                          {stage_obj.recruitment_id}.Has sido elegido/a como uno de los gerentes",
                    verb_fr=f"L'étape {stage_obj.stage} dans le recrutement {stage_obj.recruitment_id}\
                          a été mise à jour.Vous avez été choisi(e) comme l'un des responsables",
                    icon="people-circle",
                    redirect=reverse("pipeline"),
                )

            return HorillaRedirect(request)

    return render(request, "pipeline/form/stage_update.html", {"form": form})


@login_required
@hx_request_required
@recruitment_manager_can_enter(perm="recruitment.change_recruitment")
def recruitment_update_pipeline(request, rec_id):
    """
    This method is used to update recruitment from pipeline view
    """
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    form = RecruitmentCreationForm(instance=recruitment_obj)
    if request.POST:
        form = RecruitmentCreationForm(request.POST, instance=recruitment_obj)
        if form.is_valid():
            recruitment_obj = form.save()
            messages.success(request, _("Recruitment updated."))
            with contextlib.suppress(Exception):
                managers = recruitment_obj.recruitment_managers.select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb=f"{recruitment_obj} is updated, You are chosen as one of the managers",
                    verb_ar=f"تم تحديث {recruitment_obj}، تم اختيارك كأحد المديرين",
                    verb_de=f"{recruitment_obj} wurde aktualisiert.\
                          Sie wurden als einer der Manager ausgewählt",
                    verb_es=f"{recruitment_obj} ha sido actualizado/a. Has sido elegido\
                            a como uno de los gerentes",
                    verb_fr=f"{recruitment_obj} a été mis(e) à jour. Vous avez été\
                            choisi(e) comme l'un des responsables",
                    icon="people-circle",
                    redirect=reverse("pipeline"),
                )

            return HorillaRedirect(request)
    return render(request, "pipeline/form/recruitment_update.html", {"form": form})


@login_required
@recruitment_manager_can_enter(perm="recruitment.change_recruitment")
def recruitment_close_pipeline(request, rec_id):
    """
    This method is used to close recruitment from pipeline view
    """
    try:
        recruitment_obj = Recruitment.objects.get(id=rec_id)
        recruitment_obj.closed = True
        recruitment_obj.save()
        messages.success(request, _("Recruitment closed successfully"))
    except (Recruitment.DoesNotExist, OverflowError):
        messages.error(request, _("Recruitment Does not exists.."))
    return HorillaRedirect(request)


@login_required
@recruitment_manager_can_enter(perm="recruitment.change_recruitment")
def recruitment_reopen_pipeline(request, rec_id):
    """
    This method is used to reopen recruitment from pipeline view
    """
    recruitment_obj = Recruitment.find(rec_id)
    if not recruitment_obj:
        return HorillaRedirect(
            request, message=_("No Recruitment found matching the query.")
        )

    recruitment_obj.closed = False
    recruitment_obj.save()
    messages.success(request, _("Recruitment reopend successfully"))
    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def candidate_stage_update(request, cand_id):
    """
    This method is a ajax method used to update candidate stage when drag and drop
    the candidate from one stage to another on the pipeline template
    Args:
        id : candidate_id
    """
    stage_id = request.POST.get("stageId")
    candidate_obj = Candidate.find(cand_id)
    if not candidate_obj:
        return JsonResponse(
            {"type": "error", "message": _("No Candidate found matching the query.")}
        )

    history_queryset = candidate_obj.history_set.all().first()
    stage_obj = Stage.objects.get(id=stage_id)
    if candidate_obj.stage_id == stage_obj:
        return JsonResponse({"type": "noChange", "message": _("No change detected.")})
    # Here set the last updated schedule date on this stage if schedule exists in history
    history_queryset = candidate_obj.history_set.filter(stage_id=stage_obj)
    schedule_date = None
    if history_queryset.exists():
        # this condition is executed when a candidate dropped back to any previous
        # stage, if there any scheduled date then set it back
        schedule_date = history_queryset.first().schedule_date
    stage_manager_on_this_recruitment = (
        is_stagemanager(request)[1]
        .filter(recruitment_id=stage_obj.recruitment_id)
        .exists()
    )
    if (
        stage_manager_on_this_recruitment
        or request.user.is_superuser
        or is_recruitmentmanager(rec_id=stage_obj.recruitment_id.id)[0]
    ):
        candidate_obj.stage_id = stage_obj
        candidate_obj.hired = stage_obj.stage_type == "hired"
        candidate_obj.canceled = stage_obj.stage_type == "cancelled"
        candidate_obj.schedule_date = schedule_date
        candidate_obj.start_onboard = False
        candidate_obj.save()
        with contextlib.suppress(Exception):
            managers = stage_obj.stage_managers.select_related("employee_user_id")
            users = [employee.employee_user_id for employee in managers]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb=f"New candidate arrived on stage {stage_obj.stage}",
                verb_ar=f"وصل مرشح جديد إلى المرحلة {stage_obj.stage}",
                verb_de=f"Neuer Kandidat ist auf der Stufe {stage_obj.stage} angekommen",
                verb_es=f"Nuevo candidato llegó a la etapa {stage_obj.stage}",
                verb_fr=f"Nouveau candidat arrivé à l'étape {stage_obj.stage}",
                icon="person-add",
                redirect=reverse("pipeline"),
            )

        return JsonResponse(
            {"type": "success", "message": _("Candidate stage updated")}
        )
    return JsonResponse(
        {"type": "danger", "message": _("Something went wrong, Try agian.")}
    )


@login_required
@hx_request_required
@all_manager_can_enter(perm="recruitment.view_stagenote")
def view_note(request, cand_id):
    """
    This method renders a template components to view candidate remark or note
    Args:
        id : candidate instance id
    """
    candidate_obj = Candidate.objects.filter(id=cand_id).first()
    if not candidate_obj:
        messages.error(request, _("Candidate not found."))
        return HorillaRedirect(request)
    notes = candidate_obj.stagenote_set.all().order_by("-id")
    return render(
        request,
        "pipeline/pipeline_components/view_note.html",
        {"cand": candidate_obj, "notes": notes},
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_stagenote")
def add_note(request, pk=None):
    """
    This method renders template component to add candidate remark
    """
    candidate_obj = Candidate.objects.filter(id=pk).first()
    if not candidate_obj:
        messages.error(request, _("Candidate not found."))
        return HorillaRedirect(request)

    form = StageNoteForm(initial={"candidate_id": pk})
    if request.method == "POST":
        form = StageNoteForm(
            request.POST,
            request.FILES,
        )
        if form.is_valid():
            note, attachment_ids = form.save(commit=False)
            note.candidate_id = candidate_obj
            note.stage_id = candidate_obj.stage_id
            note.updated_by = request.user.employee_get
            note.save()
            note.stage_files.set(attachment_ids)
            messages.success(request, _("Note added successfully.."))
    notes = candidate_obj.stagenote_set.all().order_by("-id")
    notes = paginator_qry(notes, request.GET.get("page"))
    return render(
        request,
        "cbv/candidates/profile_notes_tab.html",
        {
            "candidate": candidate_obj,
            "note_form": form,
            "notes": notes,
        },
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_stagenote")
def create_note(request, cand_id=None):
    """
    This method renders template component to add candidate remark
    """
    candidate_obj = Candidate.objects.filter(id=cand_id).first()
    if not candidate_obj:
        messages.error(request, _("Candidate not found."))
        return HorillaRedirect(request)

    form = StageNoteForm(initial={"candidate_id": cand_id})
    if request.method == "POST":
        form = StageNoteForm(request.POST, request.FILES)
        if form.is_valid():
            note, attachment_ids = form.save(commit=False)
            note.candidate_id = candidate_obj
            note.stage_id = candidate_obj.stage_id
            note.updated_by = request.user.employee_get
            note.save()
            note.stage_files.set(attachment_ids)
            messages.success(request, _("Note added successfully.."))
            return redirect("view-note", cand_id=cand_id)
    notes = candidate_obj.stagenote_set.all().order_by("-id")
    return render(
        request,
        "pipeline/pipeline_components/view_note.html",
        {"note_form": form, "cand": candidate_obj, "notes": notes},
    )


@login_required
@manager_can_enter(perm="recruitment.change_stagenote")
def note_update(request, note_id):
    """
    This method is used to update the stage not
    Args:
        id : stage note instance id
    """
    note = StageNote.find(note_id)
    if not note:
        return HorillaRedirect(
            request, message=_("No Stage Note found matching the query.")
        )

    form = StageNoteUpdateForm(instance=note)
    if request.POST:
        form = StageNoteUpdateForm(request.POST, request.FILES, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, _("Note updated successfully..."))
            cand_id = note.candidate_id.id
            return redirect("view-note", cand_id=cand_id)

    return render(
        request, "pipeline/pipeline_components/update_note.html", {"form": form}
    )


@login_required
@manager_can_enter(perm="recruitment.change_stagenote")
def note_update_individual(request, note_id):
    """
    This method is used to update the stage not
    Args:
        id : stage note instance id
    """
    note = StageNote.find(note_id)
    if not note:
        return HorillaRedirect(
            request, message=_("No Stage Note found matching the query.")
        )

    form = StageNoteForm(instance=note)
    if request.POST:
        form = StageNoteForm(request.POST, request.FILES, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, _("Note updated successfully..."))
            return HorillaRedirect(request)
    return render(
        request,
        "pipeline/pipeline_components/update_note_individual.html",
        {
            "form": form,
        },
    )


@login_required
@hx_request_required
def add_more_files(request, id):
    """
    This method is used to Add more files to the stage candidate note.
    Args:
        id : stage note instance id
    """
    note = StageNote.objects.filter(id=id).first()
    if not note:
        messages.error(request, _("Note not found."))
        return HorillaRedirect(request)
    if request.method == "POST":
        files = request.FILES.getlist("files")
        files_ids = []
        for file in files:
            instance = StageFiles.objects.create(files=file)
            files_ids.append(instance.id)

            note.stage_files.add(instance.id)
    return redirect("view-note", cand_id=note.candidate_id.id)


@login_required
@hx_request_required
def add_more_individual_files(request, id):
    """
    This method is used to Add more files to the stage candidate note.
    Args:
        id : stage note instance id
    """
    note = StageNote.objects.filter(id=id).first()
    if not note:
        messages.error(request, _("Note not found."))
        return HorillaRedirect(request)
    if request.method == "POST":
        files = request.FILES.getlist("files")
        files_ids = []
        for file in files:
            instance = StageFiles.objects.create(files=file)
            files_ids.append(instance.id)
            note.stage_files.add(instance.id)
        messages.success(request, _("Files uploaded successfully"))
    return redirect(f"/recruitment/add-note/{note.candidate_id.id}/")


@login_required
@hx_request_required
def delete_stage_note_file(request, id):
    """
    This method is used to delete the stage note file
    Args:
        id : stage file instance id
    """
    if stage_file := StageFiles.find(id):
        stage_file.delete()
        messages.success(request, _("File deleted successfully"))
    else:
        messages.error(request, _("No Stage Files found matching the query."))

    return HttpResponse("")


@login_required
@hx_request_required
def delete_individual_note_file(request, id):
    """
    This method is used to delete the stage note file
    Args:
        id : stage file instance id
    """
    script = ""
    file = StageFiles.objects.filter(id=id).first()
    if file:
        file.delete()
        messages.success(request, _("File deleted successfully"))
    return HttpResponse(script)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_stagenote")
def candidate_can_view_note(request, id):
    note = StageNote.objects.filter(id=id)
    note_obj = note.first()
    if not note_obj:
        return HorillaRedirect(request, message=_("Note not found."))

    note.update(candidate_can_view=not note_obj.candidate_can_view)

    messages.success(request, _("Candidate view status updated"))
    return redirect("view-note", cand_id=note_obj.candidate_id.id)


@login_required
@permission_required(perm="recruitment.change_candidate")
def candidate_schedule_date_update(request):
    """
    This is a an ajax method to update schedule date for a candidate
    """
    candidate_id = request.POST.get("candidateId")
    schedule_date = request.POST.get("date")
    candidate_obj = Candidate.find(candidate_id)
    message = "Error"
    if candidate_obj:
        candidate_obj.schedule_date = schedule_date
        candidate_obj.save()
        message = "Congratulations"
    return JsonResponse({"message": message})


@login_required
@manager_can_enter(perm="recruitment.add_stage")
def stage(request):
    """
    This method is used to create stages, also several permission assigned to the stage managers
    """
    form = StageCreationForm(
        initial={"recruitment_id": request.GET.get("recruitment_id")}
    )
    if request.method == "POST":
        form = StageCreationForm(request.POST)
        if form.is_valid():
            stage_obj = form.save()
            stage_obj.stage_managers.set(
                Employee.objects.filter(id__in=form.data.getlist("stage_managers"))
            )
            stage_obj.save()
            recruitment_obj = stage_obj.recruitment_id
            rec_stages = (
                Stage.objects.filter(recruitment_id=recruitment_obj, is_active=True)
                .order_by("sequence")
                .last()
            )
            if rec_stages.sequence is None:
                stage_obj.sequence = 1
            else:
                stage_obj.sequence = rec_stages.sequence + 1
            stage_obj.save()
            messages.success(request, _("Stage added."))
            with contextlib.suppress(Exception):
                managers = stage_obj.stage_managers.select_related("employee_user_id")
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb=f"Stage {stage_obj} is updated on recruitment {stage_obj.recruitment_id},\
                          You are chosen as one of the managers",
                    verb_ar=f"تم تحديث المرحلة {stage_obj} في التوظيف\
                          {stage_obj.recruitment_id}، تم اختيارك كأحد المديرين",
                    verb_de=f"Stufe {stage_obj} wurde in der Rekrutierung {stage_obj.recruitment_id}\
                          aktualisiert. Sie wurden als einer der Manager ausgewählt",
                    verb_es=f"La etapa {stage_obj} ha sido actualizada en la contratación\
                          {stage_obj.recruitment_id}. Has sido elegido/a como uno de los gerentes",
                    verb_fr=f"L'étape {stage_obj} a été mise à jour dans le recrutement\
                          {stage_obj.recruitment_id}. Vous avez été choisi(e) comme l'un des responsables",
                    icon="people-circle",
                    redirect=reverse("pipeline"),
                )

            return HorillaRedirect(request)
    return render(request, "stage/stage_form.html", {"form": form})


@login_required
@permission_required(perm="recruitment.view_stage")
def stage_view(request):
    """
    This method is used to render all stages to a template
    """
    stages = Stage.objects.all()
    stages = stages.filter(recruitment_id__is_active=True)
    recruitments = group_by_queryset(
        stages,
        "recruitment_id",
        request.GET.get("rpage"),
    )
    filter_obj = StageFilter()
    form = StageCreationForm()
    if stages.exists():
        template = "stage/stage_view.html"
    else:
        template = "stage/stage_empty.html"
    return render(
        request,
        template,
        {
            "data": paginator_qry(stages, request.GET.get("page")),
            "form": form,
            "f": filter_obj,
            "recruitments": recruitments,
        },
    )


@login_required
@hx_request_required
def stage_data(request, rec_id):
    stages = StageFilter(request.GET).qs.filter(recruitment_id__id=rec_id)
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(Stage, data_dict)

    return render(
        request,
        "stage/stage_component.html",
        {
            "data": paginator_qry(stages, request.GET.get("page")),
            "filter_dict": data_dict,
            "pd": request.GET.urlencode(),
            "hx_target": request.META.get("HTTP_HX_TARGET"),
        },
    )


@login_required
@manager_can_enter(perm="recruitment.change_stage")
@hx_request_required
def stage_update(request, stage_id):
    """
    This method is used to update stage, if the managers changed then\
    permission assigned to new managers also
    Args:
        id : stage_id

    """
    stages = Stage.objects.get(id=stage_id)
    form = StageCreationForm(instance=stages)
    if request.method == "POST":
        form = StageCreationForm(request.POST, instance=stages)
        if form.is_valid():
            form.save()
            messages.success(request, _("Stage updated."))
            response = render(
                request, "recruitment/recruitment_form.html", {"form": form}
            )
            return HttpResponse(
                response.content.decode("utf-8") + "<script>location.reload();</script>"
            )
    return render(request, "stage/stage_update_form.html", {"form": form})


@login_required
@recruitment_manager_can_enter("recruitment.change_stage")
def update_stage_order(request, pk):
    """
    This method is used to update the stage sequence of the onboarding
    """
    recruitment = Recruitment.find(pk)
    if not recruitment:
        return HorillaRedirect(
            request, message=_("No Recruitment found matching the query.")
        )

    if request.method == "POST":
        try:
            order = json.loads(request.POST.get("order", "[]"))
            for index, stage_id in enumerate(order):
                stage = recruitment.stage_set.get(id=stage_id)
                stage.sequence = index + 1
                stage.save()
            messages.success(request, _("Sequence Updated Successfully"))
            return JsonResponse({"status": "success"})
        except Exception as e:
            messages.error(request, _("Error Updating Sequence.."))
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    stages = recruitment.stage_set.order_by("sequence")

    return render(
        request,
        "cbv/pipeline/stage_order.html",
        {
            "stages": stages,
            "recruitment": recruitment,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("recruitment.add_candidate")
def add_candidate(request):
    """
    This method is used to add candidate directly to the stage
    """
    form = AddCandidateForm(initial={"stage_id": request.GET.get("stage_id")})
    if request.POST:
        form = AddCandidateForm(
            request.POST,
            request.FILES,
            initial={"stage_id": request.GET.get("stage_id")},
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Candidate Added"))
            return HorillaRedirect(request)
    return render(request, "pipeline/form/candidate_form.html", {"form": form})


@login_required
@require_http_methods(["POST"])
@hx_request_required
def stage_title_update(request, stage_id):
    """
    This method is used to update the name of recruitment stage
    """
    stage_obj = Stage.objects.get(id=stage_id)
    stage_obj.stage = request.POST["stage"]
    stage_obj.save()
    message = _("The stage title has been updated successfully")
    return HttpResponse(
        f'<div class="oh-alert-container"><div class="oh-alert oh-alert--animated oh-alert--success">{message}</div></div>'
    )


@login_required
@any_permission_required(
    perms=["recruitment.add_candidate", "onboarding.add_onboardingcandidate"]
)
def candidate(request):
    """
    This method used to create candidate
    """
    form = CandidateCreationForm()
    open_recruitment = Recruitment.objects.filter(closed=False, is_active=True)
    path = "/recruitment/candidate-view"
    template_name = "candidate/candidate_create_form.html"
    if request.META.get("HTTP_HX_REQUEST") == "true":
        template_name = "candidate/candidate_create_modal_form.html"
    if request.method == "POST":
        form = CandidateCreationForm(request.POST, request.FILES)
        if form.is_valid():
            candidate_obj = form.save(commit=False)
            candidate_obj.start_onboard = False
            candidate_obj.source = "software"
            if candidate_obj.stage_id is None:
                candidate_obj.stage_id = Stage.objects.filter(
                    recruitment_id=candidate_obj.recruitment_id, stage_type="initial"
                ).first()
            # when creating new candidate from onboarding view
            if request.GET.get("onboarding") == "True":
                candidate_obj.hired = True
                path = "/onboarding/candidates-view"
            if form.data.get("job_position_id"):
                candidate_obj.save()
                messages.success(request, _("Candidate added."))
            else:
                messages.error(request, _("Job position field is required"))
                return render(
                    request,
                    template_name,
                    {"form": form, "open_recruitment": open_recruitment},
                )
            if request.META.get("HTTP_HX_REQUEST") == "true":
                close_modal_script = ""
                if request.GET.get("container") != "true":
                    close_modal_script = (
                        "$('#objectCreateModal').removeClass('oh-modal--show');"
                    )
                container_reload_script = (
                    "$('#candidateMainContainer').html("
                    # The id="candidateListNavBar" wrapper must match the page
                    # template (candidates.html) — syncCandidateListNavBar()
                    # looks it up by id, so rebuilding the container without it
                    # breaks nav-bar hiding on every later edit-form open.
                    '\'<div id="candidateListNavBar"><div hx-get="/recruitment/nav-candidate/?" hx-trigger="load"></div></div>\' + '
                    '\'<div class="oh-checkpoint-badge mb-2" id="selectedInstances" data-ids="[]" data-clicked="" style="display: none"></div>\' + '
                    '\'<div class="oh-wrapper" id="listContainer"></div>\''
                    ");"
                    "htmx.process($('#candidateMainContainer')[0]);"
                )
                if request.GET.get("container") != "true":
                    container_reload_script = "$('#applyFilter').click();"
                return HttpResponse(
                    "<script>"
                    + close_modal_script
                    + container_reload_script
                    + "$('#reloadMessagesButton').click();"
                    + "</script>"
                )
            return redirect(path)

    return render(
        request,
        template_name,
        {"form": form, "open_recruitment": open_recruitment},
    )


@login_required
@permission_required(perm="recruitment.add_candidate")
def recruitment_stage_get(request, rec_id):
    """
    This method returns all stages as json
    """
    recruitment_obj = Recruitment.find(rec_id)

    if not recruitment_obj:
        return JsonResponse(
            {"error": _("No Recruitment found matching the query.")},
            status=404,
        )

    all_stages = recruitment_obj.stage_set.all()
    all_stage_json = serializers.serialize("json", all_stages)

    return JsonResponse({"stages": all_stage_json})


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_view(request):
    """
    This method render all candidate to the template
    """
    view_type = request.GET.get("view")
    previous_data = request.GET.urlencode()
    candidates = Candidate.objects.filter(is_active=True)
    recruitments = Recruitment.objects.filter(closed=False, is_active=True)

    mails = list(Candidate.objects.values_list("email", flat=True))
    # Query the HorillaUser model to check if any email is present
    existing_emails = list(
        HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    )

    filter_obj = CandidateFilter(request.GET, queryset=candidates)
    if Candidate.objects.exists():
        template = "candidate/candidate_view.html"
    else:
        template = "candidate/candidate_empty.html"
    data_dict = parse_qs(previous_data)
    get_key_instances(Candidate, data_dict)

    # Store the candidates in the session
    request.session["filtered_candidates"] = [candidate.id for candidate in candidates]

    return render(
        request,
        template,
        {
            "data": paginator_qry(filter_obj.qs, request.GET.get("page")),
            "pd": previous_data,
            "f": filter_obj,
            "view_type": view_type,
            "filter_dict": data_dict,
            "gp_fields": CandidateReGroup.fields,
            "emp_list": existing_emails,
            "recruitments": recruitments,
        },
    )


@login_required
@hx_request_required
def interview_filter_view(request):
    """
    This method is used to filter Disciplinary Action.
    """

    previous_data = request.GET.urlencode()

    if request.user.has_perm("recruitment.view_interviewschedule"):
        interviews = InterviewSchedule.objects.all().order_by("-interview_date")
    else:
        interviews = InterviewSchedule.objects.filter(
            employee_id=request.user.employee_get.id
        ).order_by("-interview_date")

    if request.GET.get("sortby"):
        interviews = sortby(request, interviews, "sortby")

    dis_filter = InterviewFilter(request.GET, queryset=interviews).qs

    page_number = request.GET.get("page")
    page_obj = paginator_qry(dis_filter, page_number)
    data_dict = parse_qs(previous_data)
    get_key_instances(InterviewSchedule, data_dict)
    now = timezone.now()
    return render(
        request,
        "candidate/interview_list.html",
        {
            "data": page_obj,
            "pd": previous_data,
            "filter_dict": data_dict,
            "now": now,
        },
    )


@login_required
def interview_view(request):
    """
    This method render all interviews to the template
    """
    previous_data = request.GET.urlencode()

    if request.user.has_perm("recruitment.view_interviewschedule"):
        interviews = InterviewSchedule.objects.all().order_by("-interview_date")
    else:
        interviews = InterviewSchedule.objects.filter(
            employee_id=request.user.employee_get.id
        ).order_by("-interview_date")

    form = InterviewFilter(request.GET, queryset=interviews)
    page_number = request.GET.get("page")
    page_obj = paginator_qry(form.qs, page_number)
    previous_data = request.GET.urlencode()
    template = "candidate/interview_view.html"
    now = timezone.now()

    return render(
        request,
        template,
        {
            "data": page_obj,
            "pd": previous_data,
            "f": form,
            "now": now,
        },
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_interviewschedule")
def interview_employee_remove(request, interview_id, employee_id):
    """
    This view is used to remove the employees from the meeting ,
    Args:
        interview_id(int) : primarykey of the interview.
        employee_id(int) : primarykey of the employee
    """
    interview = InterviewSchedule.find(interview_id)
    if not interview:
        return HorillaRedirect(
            request, message=_("No Meeting found matching the query")
        )

    interview.employee_id.remove(employee_id)
    messages.success(request, _("Interviewer removed succesfully."))
    interview.save()
    # return redirect(interview_filter_view)
    return HttpResponse("<script> $('#applyFilter').click();</script>")


@login_required
def candidate_export(request):
    """
    This method is used to Export candidate data
    """
    if request.META.get("HTTP_HX_REQUEST"):
        export_column = CandidateExportForm()
        export_filter = CandidateFilter()
        content = {
            "export_filter": export_filter,
            "export_column": export_column,
        }
        return render(request, "candidate/export_filter.html", context=content)
    return export_data(
        request=request,
        model=Candidate,
        filter_class=CandidateFilter,
        form_class=CandidateExportForm,
        file_name="Candidate_export",
    )


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_view_list(request):
    """
    This method renders all candidate on candidate_list.html template
    """
    previous_data = request.GET.urlencode()
    candidates = Candidate.objects.all()
    if request.GET.get("is_active") is None:
        candidates = candidates.filter(is_active=True)
    candidates = CandidateFilter(request.GET, queryset=candidates).qs
    return render(
        request,
        "candidate/candidate_list.html",
        {
            "data": paginator_qry(candidates, request.GET.get("page")),
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_candidate")
def candidate_view_card(request):
    """
    This method renders all candidate on candidate_card.html template
    """
    previous_data = request.GET.urlencode()
    candidates = Candidate.objects.all()
    if request.GET.get("is_active") is None:
        candidates = candidates.filter(is_active=True)
    candidates = CandidateFilter(request.GET, queryset=candidates).qs
    return render(
        request,
        "candidate/candidate_card.html",
        {
            "data": paginator_qry(candidates, request.GET.get("page")),
            "pd": previous_data,
        },
    )


@login_required
@manager_can_enter(perm="recruitment.view_candidate")
def candidate_about_tab(request, pk, **kwargs):
    """
    method for rendering about tab
    """

    candidate_obj = Candidate.find(pk)
    if not candidate_obj:
        messages.error(request, _("Candidate not found"))
        return HorillaRedirect(request)
    return render(
        request,
        "cbv/candidates/profile_about_tab.html",
        {
            "candidate": candidate_obj,
        },
    )


@login_required
@manager_can_enter(perm="recruitment.view_candidate")
def candidate_resume_tab(request, pk, **kwargs):
    """
    method for rendering resume tab
    """

    candidate_obj = Candidate.find(pk)
    return render(
        request,
        "cbv/candidates/profile_resume_tab.html",
        {
            "candidate": candidate_obj,
        },
    )


@login_required
@manager_can_enter(perm="recruitment.view_candidate")
def candidate_survey_tab(request, pk, **kwargs):
    """
    method for rendering survey tab
    """

    candidate_obj = Candidate.find(pk)
    survey = RecruitmentSurveyAnswer.objects.filter(candidate_id=pk).first()
    return render(
        request,
        "cbv/candidates/profile_survey_tab.html",
        {
            "candidate": candidate_obj,
            "survey": survey,
        },
    )


# @login_required
# @manager_can_enter(perm="recruitment.view_candidate")
# def candidate_notes_tab(request, pk, **kwargs):
#     """
#     method for rendering notes tab
#     """

#     candidate_obj = Candidate.find(pk)
#     return render(
#         request,
#         "candidate/individual_view_note.html",
#         {
#             "candidate": candidate_obj,
#         },
#     )


@login_required
@manager_can_enter(perm="recruitment.view_candidate")
def candidate_history_tab(request, pk, **kwargs):
    """
    method for rendering history tab
    """

    candidate_obj = Candidate.find(pk)
    return render(
        request,
        "candidate/history.html",
        {
            "candidate": candidate_obj,
        },
    )


@login_required
@all_manager_can_enter(perm="recruitment.view_candidate")
def candidate_onboarding_tab(request, pk, **kwargs):
    """
    method for rendering onboarding tab
    """

    candidate_obj = Candidate.find(pk)
    return render(
        request,
        "cbv/candidates/profile_onboarding_tab.html",
        {
            "candidate": candidate_obj,
        },
    )


@login_required
@all_manager_can_enter(perm="recruitment.view_candidate")
def candidate_rating_tab(request, pk, **kwargs):
    """
    method for rendering rating tab
    """

    candidate_obj = Candidate.find(pk)
    if not candidate_obj:
        return HorillaRedirect(request, message=_("Candidate not found."))

    ratings = candidate_obj.candidate_rating.all().order_by("-id")
    ratings = paginator_qry(ratings, request.GET.get("page"))
    return render(
        request,
        "candidate/rating_tab.html",
        {
            "candidate": candidate_obj,
            "ratings": ratings,
        },
    )


@login_required
@manager_can_enter(perm="recruitment.view_candidate")
def candidate_interview_tab(request, pk, **kwargs):
    """
    method for rendering interview tab
    """

    candidate_obj = Candidate.find(pk)
    if not candidate_obj:
        return HorillaRedirect(request, message=_("Candidate not found."))

    interviews = candidate_obj.candidate_interview.all().order_by("-interview_date")
    interviews = paginator_qry(interviews, request.GET.get("page"))
    return render(
        request,
        "cbv/candidates/profile_interview_tab.html",
        {
            "candidate": candidate_obj,
            "interviews": interviews,
        },
    )


def scheduled_interview_tab(request, pk, **kwargs):
    """
    method for rendering interview tab
    """
    employee = Employee.objects.get(id=pk)
    interviews = InterviewSchedule.objects.filter(employee_id=employee).order_by(
        "-interview_date"
    )
    interviews = paginator_qry(interviews, request.GET.get("page"))
    return render(
        request,
        "tabs/scheduled_interview.html",
        {"interviews": interviews, "employee": employee},
    )


@login_required
@all_manager_can_enter(perm="recruitment.view_candidate")
def candidate_view_individual(request, cand_id, **kwargs):
    """
    This method is used to view profile of candidate.
    """
    # candidate_obj = Candidate.find(cand_id)
    # # if not candidate_obj:
    # #     messages.error(request, _("Candidate not found"))
    # #     return HorillaRedirect(request)

    # mails = list(Candidate.objects.values_list("email", flat=True))
    # # Query the HorillaUser model to check if any email is present
    # existing_emails = list(
    #     HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    # )
    # ratings = candidate_obj.candidate_rating.all()
    # documents = CandidateDocument.objects.filter(candidate_id=cand_id)
    # rating_list = []
    # avg_rate = 0
    # for rating in ratings:
    #     rating_list.append(rating.rating)
    # if len(rating_list) != 0:
    #     avg_rate = round(sum(rating_list) / len(rating_list))

    # # Retrieve the filtered candidate from the session
    # filtered_candidate_ids = request.session.get("filtered_candidates", [])

    # # Convert the string to an actual list of integers
    # requests_ids = (
    #     ast.literal_eval(filtered_candidate_ids)
    #     if isinstance(filtered_candidate_ids, str)
    #     else filtered_candidate_ids
    # )

    # next_id = None
    # previous_id = None

    # for index, req_id in enumerate(requests_ids):
    #     if req_id == cand_id:

    #         if index == len(requests_ids) - 1:
    #             next_id = None
    #         else:
    #             next_id = requests_ids[index + 1]
    #         if index == 0:
    #             previous_id = None
    #         else:
    #             previous_id = requests_ids[index - 1]
    #         break

    # now = timezone.now()

    return render(
        request,
        "candidate/individual.html",
        # {
        #     "candidate": candidate_obj,
        #     "previous": previous_id,
        #     "next": next_id,
        #     "requests_ids": requests_ids,
        #     "emp_list": existing_emails,
        #     "average_rate": avg_rate,
        #     "documents": documents,
        #     "now": now,
        # },
    )


def _query_param_truthy(get_dict, key):
    val = get_dict.get(key)
    if val is None:
        return False
    return str(val).lower() in ("true", "1", "yes")


def _onboarding_container_request(request):
    return request.GET.get("container") == "true" and _query_param_truthy(
        request.GET, "onboarding"
    )


@login_required
@manager_can_enter(
    perms=["recruitment.change_candidate", "onboarding.change_onboardingcandidate"]
)
def candidate_update(request, cand_id, **kwargs):
    """
    Used to update or change the candidate
    Args:
        id : candidate_id
    """
    try:
        candidate_obj = Candidate.objects.get(id=cand_id)
        form = CandidateCreationForm(instance=candidate_obj)
        path = "/recruitment/candidate-view"
        template_name = "candidate/candidate_create_form.html"
        if request.META.get("HTTP_HX_REQUEST") == "true":
            template_name = "candidate/candidate_create_modal_form.html"
        if request.method == "POST":
            form = CandidateCreationForm(
                request.POST, request.FILES, instance=candidate_obj
            )
            if form.is_valid():
                candidate_obj = form.save()
                if candidate_obj.stage_id is None:
                    candidate_obj.stage_id = Stage.objects.filter(
                        recruitment_id=candidate_obj.recruitment_id,
                        stage_type="initial",
                    ).first()
                if candidate_obj.stage_id is not None:
                    if (
                        candidate_obj.stage_id.recruitment_id
                        != candidate_obj.recruitment_id
                    ):
                        candidate_obj.stage_id = (
                            candidate_obj.recruitment_id.stage_set.filter(
                                stage_type="initial"
                            ).first()
                        )
                if _query_param_truthy(request.GET, "onboarding"):
                    candidate_obj.hired = True
                    path = "/onboarding/candidates-view"
                candidate_obj.save()
                messages.success(request, _("Candidate Updated Successfully."))
                if request.META.get("HTTP_HX_REQUEST") == "true":
                    close_modal_script = ""
                    if request.GET.get("container") != "true":
                        close_modal_script = (
                            "$('#objectCreateModal').removeClass('oh-modal--show');"
                        )
                    if request.GET.get("container") == "true":
                        if _query_param_truthy(request.GET, "onboarding"):
                            _onboarding_candidates_url = reverse("candidates-view")
                            container_reload_script = (
                                "if (window.history && history.pushState) { "
                                f"history.pushState({{}}, '', '{_onboarding_candidates_url}'); "
                                "}"
                                "document.body.classList.remove('onboarding-list-hide-toolbar');"
                                "var nav = document.getElementById('onboardingCandidatesNavBar');"
                                "if (nav) { nav.style.display = ''; }"
                                "var tagRow = nav && nav.querySelector('#filterTagContainerSectionNav');"
                                "if (tagRow) { tagRow.innerHTML = ''; }"
                                "var list = document.getElementById('listContainer');"
                                "if (list) { list.innerHTML = ''; }"
                                "setTimeout(function () { "
                                "var b = document.getElementById('applyFilter'); "
                                "if (b) { b.click(); } }, 100);"
                            )
                        else:
                            _recruitment_candidates_url = reverse("candidate-view")
                            container_reload_script = (
                                "if (window.history && history.pushState) { "
                                f"history.pushState({{}}, '', '{_recruitment_candidates_url}'); "
                                "}"
                                # Deferred a tick: this response is itself the
                                # htmx swap target's (#candidateMainContainer)
                                # new content, so replacing that same
                                # container's HTML synchronously here races
                                # htmx's own swap/settle bookkeeping on it --
                                # observed as a "removeChild: not a child of
                                # this node" console error. Queuing it as a
                                # separate task lets htmx finish settling the
                                # current swap first.
                                "setTimeout(function () {"
                                "$('#candidateMainContainer').html("
                                # Must match candidates.html's real markup --
                                # missing the id="candidateListNavBar" wrapper
                                # here left that element absent from the DOM
                                # after every save, so syncCandidateListNavBar()
                                # (in candidates.html) could never find it again
                                # to hide it on the next Edit, leaving the
                                # search/filter/Create toolbar visible over
                                # the edit form from the second edit onward.
                                '\'<div id="candidateListNavBar"><div hx-get="/recruitment/nav-candidate/?" hx-trigger="load"></div></div>\' + '
                                '\'<div class="oh-checkpoint-badge mb-2" id="selectedInstances" data-ids="[]" data-clicked="" style="display: none"></div>\' + '
                                '\'<div class="oh-wrapper" id="listContainer"></div>\''
                                ");"
                                "htmx.process($('#candidateMainContainer')[0]);"
                                "}, 0);"
                            )
                    else:
                        container_reload_script = "$('#applyFilter').click();"
                    return HttpResponse(
                        "<script>"
                        + close_modal_script
                        + container_reload_script
                        + "$('#reloadMessagesButton').click();"
                        + "</script>"
                    )
                return redirect(path)
        onboarding_container_mode = _onboarding_container_request(request)
        return render(
            request,
            template_name,
            {
                "form": form,
                "onboarding_container_mode": onboarding_container_mode,
            },
        )
    except (Candidate.DoesNotExist, OverflowError):
        messages.error(request, _("Candidate Does not exists.."))
    return HorillaRedirect(request)


@transaction.atomic
@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def candidate_conversion(request, cand_id, **kwargs):
    container_request = request.GET.get("container") == "true"
    candidate_obj = Candidate.find(cand_id)

    if not candidate_obj:
        messages.error(request, _("Candidate not found"))
        if container_request:
            return JsonResponse({"message": "Candidate not found"}, status=404)
        return HorillaRedirect(request)

    if candidate_obj.converted_employee_id:
        messages.info(request, _("This candidate is already converted to an employee."))
        if container_request:
            return JsonResponse({"message": "Already converted"}, status=200)
        return HorillaRedirect(request)

    user_exists = HorillaUser.objects.filter(username=candidate_obj.email).exists()
    employee_exists = Employee.objects.filter(
        employee_user_id__username=candidate_obj.email
    ).exists()

    if user_exists:
        messages.error(request, _("User instance with this mail already exists"))
    elif not employee_exists:
        try:
            new_employee = Employee(
                employee_first_name=candidate_obj.name,
                email=candidate_obj.email,
                phone=candidate_obj.mobile,
                gender=candidate_obj.gender,
                is_directly_converted=True,
            )
            new_employee.save()

            work_info = new_employee.employee_work_info
            work_info.job_position_id = candidate_obj.job_position_id
            work_info.department_id = candidate_obj.job_position_id.department_id
            work_info.company_id = candidate_obj.recruitment_id.company_id
            work_info.save()

            Document.objects.bulk_create(
                [
                    Document(
                        title=doc.title,
                        employee_id=new_employee,
                        document=doc.document,
                        status=doc.status,
                        reject_reason=doc.reject_reason,
                    )
                    for doc in candidate_obj.candidatedocument_set.all()
                ]
            )

            candidate_obj.converted_employee_id = new_employee
            candidate_obj.save()
            messages.success(
                request,
                _("Candidate has been successfully converted into an employee."),
            )
        except IntegrityError:
            messages.warning(
                request, _("An error occurred while creating employee data.")
            )

    else:
        messages.info(request, _("An employee with this email already exists"))

    if container_request:
        return JsonResponse({"message": "Success"}, status=200)

    if "HTTP_HX_REQUEST" in request.META:
        return HttpResponse(status=204, headers={"HX-Refresh": "true"})

    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def delete_profile_image(request, obj_id):
    """
    This method is used to delete the profile image of the candidate
    Args:
        obj_id : candidate instance id
    """
    candidate_obj = Candidate.find(obj_id)
    if not candidate_obj:
        return HorillaRedirect(
            request, message=_("No Candidate found matching the query.")
        )

    try:
        if candidate_obj.profile:
            file_path = candidate_obj.profile.path
            absolute_path = os.path.join(settings.MEDIA_ROOT, file_path)
            os.remove(absolute_path)
            candidate_obj.profile = None
            candidate_obj.save()
            messages.success(request, _("Profile image removed."))
    except Exception as e:
        pass
    return redirect("rec-candidate-update", cand_id=obj_id)


@login_required
@permission_required(perm="recruitment.view_history")
def candidate_history(request, cand_id):
    """
    This method is used to view candidate stage changes
    Args:
        id : candidate_id
    """
    candidate_obj = Candidate.find(cand_id)
    if not candidate_obj:
        return HorillaRedirect(
            request, message=_("No Candidate found matching the query.")
        )

    candidate_history_queryset = candidate_obj.history.all()
    return render(
        request,
        "candidate/candidate_history.html",
        {"history": candidate_history_queryset},
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_candidate")
def form_send_mail(request, cand_id=None):
    """
    This method is used to render the bootstrap modal content body form
    """
    candidate_obj = None
    stage_id = None
    if request.GET.get("stage_id"):
        stage_id = eval_validate(request.GET.get("stage_id"))
    if cand_id:
        candidate_obj = Candidate.objects.filter(id=cand_id).first()
        if not candidate_obj:
            return HttpResponse()
    candidates = Candidate.objects.all()
    if stage_id and isinstance(stage_id, int):
        candidates = candidates.filter(stage_id__id=stage_id)
    else:
        stage_id = None

    HorillaMailTemplate.objects.get_or_create(
        title="Candidate Portal Login",
        defaults={
            "body": (
                "<div style=\"font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f9; padding: 24px;\">"
                '<div style="max-width: 640px; margin: auto; background: #ffffff; border-radius: 12px; padding: 28px; '
                'box-shadow: 0 4px 14px rgba(0,0,0,0.08); border: 1px solid #eceff3;">'
                '<h2 style="margin: 0 0 18px 0; color: #1f2937; font-size: 22px;">Candidate Portal Login Details</h2>'
                '<p style="font-size: 14px; color: #374151; line-height: 1.7; margin: 0 0 14px 0;">'
                "Hi {{instance.get_full_name}},</p>"
                '<p style="font-size: 14px; color: #374151; line-height: 1.7; margin: 0 0 16px 0;">'
                "You can track your application status from the candidate portal using the credentials below.</p>"
                '<div style="margin: 18px 0; padding: 16px; background: #f9fafb; border-left: 4px solid hsl(8, 77%, 56%); border-radius: 8px;">'
                '<p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;">'
                "<strong>Portal Link:</strong> "
                '<a href="{{ request.scheme }}://{{ request.get_host }}/recruitment/candidate-login/" target="_blank" '
                'style="color: hsl(8, 77%, 56%); text-decoration: none;">'
                "{{ request.scheme }}://{{ request.get_host }}/recruitment/candidate-login/"
                "</a></p>"
                '<p style="margin: 0 0 8px 0; font-size: 14px; color: #111827;"><strong>Username (Email):</strong> {{instance.email}}</p>'
                '<p style="margin: 0; font-size: 14px; color: #111827;"><strong>Password (Mobile Number):</strong> {{instance.mobile}}</p>'
                "</div>"
                '<p style="font-size: 13px; color: #6b7280; margin: 0 0 18px 0;">'
                "For security, please keep these credentials private.</p>"
                '<hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">'
                '<p style="font-size: 13px; color: #6b7280; margin: 0;">Regards,</p>'
                '<p style="font-size: 13px; color: #111827; margin: 6px 0 0 0;"><strong>{{self.get_full_name}} | {{self.get_department}} | {{self.get_company}}</strong></p>'
                "</div></div>"
            )
        },
    )
    templates = HorillaMailTemplate.objects.all()
    return render(
        request,
        "pipeline/pipeline_components/send_mail.html",
        {
            "cand": candidate_obj,
            "templates": templates,
            "candidates": candidates,
            "stage_id": stage_id,
            "searchWords": MailTemplateForm().get_template_language(),
        },
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_interviewschedule")
def interview_schedule(request, cand_id):
    """
    This method is used to Schedule interview to candidate
    Args:
        cand_id : candidate instance id
    """
    candidate = Candidate.objects.get(id=cand_id)
    candidates = Candidate.objects.filter(id=cand_id)
    template = "pipeline/pipeline_components/schedule_interview.html"
    form = ScheduleInterviewForm(initial={"candidate_id": candidate})
    form.fields["candidate_id"].queryset = candidates
    if request.method == "POST":
        form = ScheduleInterviewForm(request.POST)
        if form.is_valid():
            form.save()
            emp_ids = form.cleaned_data["employee_id"]
            cand_id = form.cleaned_data["candidate_id"]
            interview_date = form.cleaned_data["interview_date"]
            interview_time = form.cleaned_data["interview_time"]
            users = [employee.employee_user_id for employee in emp_ids]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb=f"You are scheduled as an interviewer for an interview with {cand_id.name} on {interview_date} at {interview_time}.",
                verb_ar=f"أنت مجدول كمقابلة مع {cand_id.name} يوم {interview_date} في توقيت {interview_time}.",
                verb_de=f"Sie sind als Interviewer für ein Interview mit {cand_id.name} am {interview_date} um {interview_time} eingeplant.",
                verb_es=f"Estás programado como entrevistador para una entrevista con {cand_id.name} el {interview_date} a las {interview_time}.",
                verb_fr=f"Vous êtes programmé en tant qu'intervieweur pour un entretien avec {cand_id.name} le {interview_date} à {interview_time}.",
                icon="people-circle",
                redirect=reverse("interview-view"),
            )

            messages.success(request, _("Interview Scheduled successfully."))
            return HorillaRedirect(request)
    return render(request, template, {"form": form, "cand_id": cand_id})


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_interviewschedule")
def create_interview_schedule(request):
    """
    This method is used to Schedule interview to candidate
    Args:
        cand_id : candidate instance id
    """
    candidates = Candidate.objects.all()
    template = "candidate/interview_form.html"
    form = ScheduleInterviewForm()
    form.fields["candidate_id"].queryset = candidates
    if request.method == "POST":
        form = ScheduleInterviewForm(request.POST)
        if form.is_valid():
            form.save()
            emp_ids = form.cleaned_data["employee_id"]
            cand_id = form.cleaned_data["candidate_id"]
            interview_date = form.cleaned_data["interview_date"]
            interview_time = form.cleaned_data["interview_time"]
            users = [employee.employee_user_id for employee in emp_ids]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb=f"You are scheduled as an interviewer for an interview with {cand_id.name} on {interview_date} at {interview_time}.",
                verb_ar=f"أنت مجدول كمقابلة مع {cand_id.name} يوم {interview_date} في توقيت {interview_time}.",
                verb_de=f"Sie sind als Interviewer für ein Interview mit {cand_id.name} am {interview_date} um {interview_time} eingeplant.",
                verb_es=f"Estás programado como entrevistador para una entrevista con {cand_id.name} el {interview_date} a las {interview_time}.",
                verb_fr=f"Vous êtes programmé en tant qu'intervieweur pour un entretien avec {cand_id.name} le {interview_date} à {interview_time}.",
                icon="people-circle",
                redirect=reverse("interview-view"),
            )

            messages.success(request, _("Interview Scheduled successfully."))
    return render(request, template, {"form": form})


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.delete_interviewschedule")
def interview_delete(request, interview_id):
    """
    Deletes an interview schedule.
    Args:
        interview_id: InterviewSchedule instance ID
    """
    try:
        InterviewSchedule.objects.get(id=interview_id).delete()
        messages.success(request, _("Interview deleted successfully."))
    except:
        messages.error(request, _("Scheduled Interview not found"))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        return HttpResponse(
            "<script>"
            "$('#applyFilter').click();"
            "$('#reloadMessagesButton').click();"
            "</script>"
        )
    return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_interviewschedule")
def interview_edit(request, interview_id):
    """
    This method is used to Edit Schedule interview
    Args:
        interview_id : interview schedule instance id
    """
    interview = InterviewSchedule.objects.get(id=interview_id)
    view = request.GET["view"]
    if view == "true":
        candidates = Candidate.objects.all()
        view = "true"
    else:
        candidates = Candidate.objects.filter(id=interview.candidate_id.id)
        view = "false"
    template = "pipeline/pipeline_components/schedule_interview_update.html"
    form = ScheduleInterviewForm(instance=interview)
    form.fields["candidate_id"].queryset = candidates
    if request.method == "POST":
        form = ScheduleInterviewForm(request.POST, instance=interview)
        if form.is_valid():
            emp_ids = form.cleaned_data["employee_id"]
            cand_id = form.cleaned_data["candidate_id"]
            interview_date = form.cleaned_data["interview_date"]
            interview_time = form.cleaned_data["interview_time"]
            form.save()
            users = [employee.employee_user_id for employee in emp_ids]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb=f"You are scheduled as an interviewer for an interview with {cand_id.name} on {interview_date} at {interview_time}.",
                verb_ar=f"أنت مجدول كمقابلة مع {cand_id.name} يوم {interview_date} في توقيت {interview_time}.",
                verb_de=f"Sie sind als Interviewer für ein Interview mit {cand_id.name} am {interview_date} um {interview_time} eingeplant.",
                verb_es=f"Estás programado como entrevistador para una entrevista con {cand_id.name} el {interview_date} a las {interview_time}.",
                verb_fr=f"Vous êtes programmé en tant qu'intervieweur pour un entretien avec {cand_id.name} le {interview_date} à {interview_time}.",
                icon="people-circle",
                redirect=reverse("interview-view"),
            )
            messages.success(request, _("Interview updated successfully."))
            return HorillaRedirect(request)
    return render(
        request,
        template,
        {
            "form": form,
            "interview_id": interview_id,
            "view": view,
        },
    )


@login_required
def get_interview_managers(request):
    cand_id = request.GET.get("candidate_id")
    form = ScheduleInterviewForm()
    candidate_obj = Candidate.find(cand_id) if cand_id else None
    if candidate_obj:
        recruitment_managers = candidate_obj.recruitment_id.recruitment_managers.all()
        stage_managers = (
            candidate_obj.stage_id.stage_managers.all()
            if candidate_obj.stage_id
            else recruitment_managers.none()
        )
        managers = (recruitment_managers | stage_managers).distinct()
        form.fields["employee_id"].queryset = managers
    else:
        form.fields["employee_id"].queryset = form.fields["employee_id"].queryset.none()
    pk = request.GET.get("pk")
    if pk:
        try:
            interviewer = InterviewSchedule.objects.get(id=pk)
            form.fields["employee_id"].initial = interviewer.employee_id.all()
        except InterviewSchedule.DoesNotExist:
            pass
    return render(
        request,
        "candidate/interview_form.html",
        {"form": form, "CBV": True},
    )


@login_required
def get_managers(request):
    cand_id = request.GET.get("cand_id")
    candidate_obj = Candidate.find(cand_id)
    if not candidate_obj:
        return JsonResponse({"employees": {}})

    stage_obj = Stage.objects.filter(recruitment_id=candidate_obj.recruitment_id.id)

    # Combine the querysets into a single iterable
    all_managers = chain(
        candidate_obj.recruitment_id.recruitment_managers.all(),
        *[stage.stage_managers.all() for stage in stage_obj],
    )

    # Extract unique managers from the combined iterable
    unique_managers = list(set(all_managers))

    # Assuming you have a list of employee objects called 'unique_managers'
    employees_dict = {
        employee.id: employee.get_full_name() for employee in unique_managers
    }
    return JsonResponse({"employees": employees_dict})


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def send_acknowledgement(request):
    """
    This method is used to send acknowledgement mail to the candidate
    """
    candidate_id = request.POST.get("id")
    subject = request.POST.get("subject")
    bdy = request.POST.get("body")
    candidate_ids = request.POST.getlist("candidates")
    candidates = Candidate.objects.filter(id__in=candidate_ids)

    other_attachments = request.FILES.getlist("other_attachments")

    if candidate_id:
        candidate_obj = Candidate.objects.filter(id=candidate_id)
    else:
        candidate_obj = Candidate.objects.none()
    candidates = (candidates | candidate_obj).distinct()

    template_attachment_ids = request.POST.getlist("template_attachments")
    for candidate in candidates:
        attachments = [
            (file.name, file.read(), file.content_type) for file in other_attachments
        ]
        bodys = list(
            HorillaMailTemplate.objects.filter(
                id__in=template_attachment_ids
            ).values_list("body", flat=True)
        )
        for html in bodys:
            # due to not having solid template we first need to pass the context
            template_bdy = template.Template(sanitize_mail_template_body(html))
            context = template.Context(
                {
                    "instance": candidate,
                    "self": request.user.employee_get,
                    "request": build_safe_template_request(request),
                }
            )
            render_bdy = template_bdy.render(context)
            attachments.append(
                (
                    "Document",
                    generate_pdf(render_bdy, {}, path=False, title="Document").content,
                    "application/pdf",
                )
            )

        template_bdy = template.Template(sanitize_mail_template_body(bdy))
        context = template.Context(
            {
                "instance": candidate,
                "self": request.user.employee_get,
                "request": build_safe_template_request(request),
            }
        )
        render_bdy = template_bdy.render(context)
        to = candidate.email
        email = EmailMessage(
            subject=subject,
            body=render_bdy,
            to=[to],
        )
        email.content_subtype = "html"

        email.attachments = attachments
        try:
            email.send()
            messages.success(request, _("Mail sent to candidate"))
        except Exception as e:
            logger.exception(e)
            messages.error(request, _("Something went wrong"))
    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def candidate_sequence_update(request):
    """
    This method is used to update the sequence of candidate
    """
    sequence_data = json.loads(request.POST.get("sequenceData", "{}"))
    for cand_id, seq in sequence_data.items():
        cand = Candidate.objects.get(id=cand_id)
        cand.sequence = seq
        cand.save()

    return JsonResponse({"message": "Sequence updated", "type": "info"})


@login_required
@recruitment_manager_can_enter(perm="recruitment.change_stage")
def stage_sequence_update(request):
    """
    This method is used to update the sequence of the stages
    """
    sequence_data = json.loads(request.POST.get("sequence", "{}"))
    if not sequence_data:
        return JsonResponse({"type": "error", "message": _("Missing Sequence")})

    for stage_id, seq in sequence_data.items():
        stage = Stage.objects.get(id=stage_id)
        stage.sequence = seq
        stage.save()
    return JsonResponse({"type": "success", "message": "Stage sequence updated"})


@login_required
def candidate_select(request):
    """
    This method is used for select all in candidate
    """
    page_number = request.GET.get("page")

    if page_number == "all":
        employees = Candidate.objects.filter(is_active=True)
    else:
        employees = Candidate.objects.all()

    employee_ids = [str(emp.id) for emp in employees]
    total_count = employees.count()

    context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def candidate_select_filter(request):
    """
    This method is used to select all filtered candidates
    """
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        candidate_filter = CandidateFilter(filters, queryset=Candidate.objects.all())

        # Get the filtered queryset
        filtered_candidates = candidate_filter.qs

        candidate_ids = [str(cand.id) for cand in filtered_candidates]
        total_count = filtered_candidates.count()

        context = {"employee_ids": candidate_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
def create_candidate_rating(request, cand_id):
    """
    This method is used to create rating for the candidate
    Args:
        cand_id : candidate instance id
    """
    candidate = Candidate.find(cand_id)
    if candidate:
        employee_id = request.user.employee_get
        rating = request.POST.get("rating")
        CandidateRating.objects.create(
            candidate_id=candidate, rating=rating, employee_id=employee_id
        )
    else:
        messages.error(request, _("No Candidate found matching the query"))

    return redirect(recruitment_pipeline)


# ///////////////////////////////////////////////
# talent pool
# ///////////////////////////////////////////////


@login_required
@manager_can_enter(perm="recruitment.view_skillzone")
def skill_zone_view(request):
    """
    This method is used to show Talent pool view
    """
    candidates = SkillZoneCandFilter(request.GET).qs.filter(is_active=True)
    skill_groups = group_by_queryset(
        candidates,
        "skill_zone_id",
        request.GET.get("page"),
        "page",
    )

    all_zones = []
    for zone in skill_groups:
        all_zones.append(zone["grouper"])

    skill_zone_filtered = SkillZoneFilter(request.GET).qs.filter(is_active=True)
    all_zone_objects = list(skill_zone_filtered)
    unused_skill_zones = list(set(all_zone_objects) - set(all_zones))

    unused_zones = []
    for zone in unused_skill_zones:
        unused_zones.append(
            {
                "grouper": zone,
                "list": [],
                "dynamic_name": "",
            }
        )
    skill_groups = skill_groups.object_list + unused_zones
    skill_groups = paginator_qry(skill_groups, request.GET.get("page"))
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(SkillZone, data_dict)
    if skill_groups.object_list:
        template = "skill_zone/skill_zone_view.html"
    else:
        template = "skill_zone/empty_skill_zone.html"

    context = {
        "pd": previous_data,
        "filter_dict": data_dict,
        "model": SkillZone(),
        "f": SkillZoneCandFilter(),
        "skill_zones": skill_groups,
        "page": request.GET.get("page"),
    }
    return render(request, template, context=context)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_skillzone")
def skill_zone_create(request):
    """
    This method is used to create Talent pool.
    """
    form = SkillZoneCreateForm()
    if request.method == "POST":
        form = SkillZoneCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Talent Pool created successfully."))
            form = SkillZoneCreateForm()

    return render(
        request,
        "skill_zone/skill_zone_form.html",
        {"form": form},
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_skillzone")
def skill_zone_update(request, sz_id):
    """
    This method is used to update Talent pool.
    """
    skill_zone = SkillZone.objects.get(id=sz_id)
    form = SkillZoneCreateForm(instance=skill_zone)
    if request.method == "POST":
        form = SkillZoneCreateForm(request.POST, instance=skill_zone)
        if form.is_valid():
            form.save()
            messages.success(request, _("Talent Pool updated successfully."))
    return render(
        request,
        "skill_zone/skill_zone_form.html",
        {"form": form, "sz_id": sz_id},
    )


@login_required
@manager_can_enter(perm="recruitment.delete_skillzone")
def skill_zone_delete(request, sz_id):
    """
    function used to delete Talent pool.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_id : Talent pool id

    Returns:
    GET : return Talent pool view template
    """
    try:
        skill_zone = SkillZone.find(sz_id)
        if skill_zone:
            skill_zone.delete()
            messages.success(request, _("Talent pool deleted successfully."))
        else:
            messages.error(request, _("Talent pool not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "skillZoneContainerReload"
        return response
    return HttpResponse(
        "<script>$('.filterButton')[0].click();reloadMessage();</script>"
    )


@login_required
@manager_can_enter(perm="recruitment.change_skillzone")
def skill_zone_archive(request, sz_id):
    """
    function used to archive or un-archive Talent pool.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_id : Talent pool id

    Returns:
    GET : return Talent pool view template
    """
    skill_zone = SkillZone.find(sz_id)
    if skill_zone:
        is_active = skill_zone.is_active
        if is_active == True:
            skill_zone.is_active = False
            skill_zone_candidates = SkillZoneCandidate.objects.filter(
                skill_zone_id=sz_id
            )
            for i in skill_zone_candidates:
                i.is_active = False
                i.save()
            messages.success(request, _("Talent pool archived successfully."))
        else:
            skill_zone.is_active = True
            skill_zone_candidates = SkillZoneCandidate.objects.filter(
                skill_zone_id=sz_id
            )
            for i in skill_zone_candidates:
                i.is_active = True
                i.save()
            messages.success(request, _("Talent pool unarchived successfully."))
        skill_zone.save()
    else:
        messages.error(request, _("Talent pool not found."))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "skillZoneContainerReload"
        return response
    return redirect(skill_zone_view)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.view_skillzone")
def skill_zone_filter(request):
    """
    This method is used to filter and show Talent pool view.
    """
    template = "skill_zone/skill_zone_list.html"
    if request.GET.get("view") == "card":
        template = "skill_zone/skill_zone_card.html"

    candidates = SkillZoneCandFilter(request.GET).qs
    skill_zone_filtered = SkillZoneFilter(request.GET).qs
    if request.GET.get("is_active") == "false":
        skill_zone_filtered = SkillZoneFilter(request.GET).qs.filter(is_active=False)
        candidates = SkillZoneCandFilter(request.GET).qs.filter(is_active=False)

    else:
        skill_zone_filtered = SkillZoneFilter(request.GET).qs.filter(is_active=True)
        candidates = SkillZoneCandFilter(request.GET).qs.filter(is_active=True)
    skill_groups = group_by_queryset(
        candidates,
        "skill_zone_id",
        request.GET.get("page"),
        "page",
    )
    all_zones = []
    for zone in skill_groups:
        all_zones.append(zone["grouper"])

    all_zone_objects = list(skill_zone_filtered)
    unused_skill_zones = list(set(all_zone_objects) - set(all_zones))

    unused_zones = []
    for zone in unused_skill_zones:
        unused_zones.append(
            {
                "grouper": zone,
                "list": [],
                "dynamic_name": "",
            }
        )
    skill_groups = skill_groups.object_list + unused_zones
    skill_groups = paginator_qry(skill_groups, request.GET.get("page"))
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(SkillZone, data_dict)
    context = {
        "skill_zones": skill_groups,
        "pd": previous_data,
        "filter_dict": data_dict,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
@manager_can_enter(perm="recruitment.view_skillzonecandidate")
def skill_zone_cand_card_view(request, sz_id):
    """
    This method is used to show Talent pool candidates.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_cand_id : Talent pool id

    Returns:
    GET : return Talent pool candidate view template
    """
    skill_zone = SkillZone.objects.get(id=sz_id)
    template = "skill_zone_cand/skill_zone_cand_view.html"
    sz_candidates = SkillZoneCandidate.objects.filter(
        skill_zone_id=skill_zone, is_active=True
    )
    context = {
        "sz_candidates": paginator_qry(sz_candidates, request.GET.get("page")),
        "pd": request.GET.urlencode(),
        "sz_id": sz_id,
    }
    return render(request, template, context)


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_skillzonecandidate")
def skill_zone_candidate_create(request, sz_id):
    """
    This method is used to add candidates to a Talent pool.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_cand_id : Talent pool id

    Returns:
    GET : return Talent pool candidate create template
    """
    skill_zone = SkillZone.objects.get(id=sz_id)
    template = "skill_zone_cand/skill_zone_cand_form.html"
    form = SkillZoneCandidateForm(initial={"skill_zone_id": skill_zone})
    if request.method == "POST":
        form = SkillZoneCandidateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Candidate added successfully."))
            return HorillaRedirect(request)

    return render(request, template, {"form": form, "sz_id": sz_id})


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_skillzonecandidate")
def skill_zone_cand_edit(request, sz_cand_id):
    """
    This method is used to edit candidates in a Talent pool.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_cand_id : Talent pool candidate id

    Returns:
    GET : return Talent pool candidate edit template
    """
    skill_zone_cand = SkillZoneCandidate.objects.filter(id=sz_cand_id).first()
    template = "skill_zone_cand/skill_zone_cand_form.html"
    form = SkillZoneCandidateForm(instance=skill_zone_cand)
    if request.method == "POST":
        form = SkillZoneCandidateForm(request.POST, instance=skill_zone_cand)
        if form.is_valid():
            form.save()
            messages.success(request, _("Candidate edited successfully."))
            return HorillaRedirect(request)
    return render(request, template, {"form": form, "sz_cand_id": sz_cand_id})


@manager_can_enter(perm="recruitment.view_skillzonecandidate")
def skill_zone_cand_filter(request):
    """
    This method is used to filter the talent pool candidates
    """
    template = "skill_zone_cand/skill_zone_cand_card.html"
    if request.GET.get("view") == "list":
        template = "skill_zone_cand/skill_zone_cand_list.html"

    candidates = SkillZoneCandidate.objects.all()
    candidates_filter = SkillZoneCandFilter(request.GET, queryset=candidates).qs
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(SkillZoneCandidate, data_dict)
    context = {
        "candidates": paginator_qry(candidates_filter, request.GET.get("page")),
        "pd": previous_data,
        "filter_dict": data_dict,
        "f": SkillZoneCandFilter(),
    }
    return render(
        request,
        template,
        context,
    )


@login_required
@manager_can_enter(perm="recruitment.delete_skillzonecandidate")
def skill_zone_cand_archive(request, sz_cand_id):
    """
    function used to archive or un-archive Talent pool candidate.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_cand_id : Talent pool candidate id

    Returns:
    GET : return Talent pool candidate view template
    """
    try:
        skill_zone_cand = SkillZoneCandidate.objects.get(id=sz_cand_id)
        is_active = skill_zone_cand.is_active
        if is_active == True:
            skill_zone_cand.is_active = False
            messages.success(request, _("Candidate archived successfully.."))

        else:
            skill_zone_cand.is_active = True
            messages.success(request, _("Candidate unarchived successfully.."))

        skill_zone_cand.save()
    except SkillZoneCandidate.DoesNotExist:
        messages.error(request, _("No Candidate found matching the query."))
    return redirect(skill_zone_view)


@login_required
@manager_can_enter(perm="recruitment.delete_skillzonecandidate")
def skill_zone_cand_delete(request, sz_cand_id):
    """
    function used to delete Talent pool candidate.

    Parameters:
    request (HttpRequest): The HTTP request object.
    sz_cand_id : Talent pool candidate id

    Returns:
    GET : return Talent pool view template
    """
    try:
        SkillZoneCandidate.objects.get(id=sz_cand_id).delete()
        messages.success(request, _("Candidate deleted successfully.."))
    except SkillZoneCandidate.DoesNotExist:
        messages.error(request, _("Candidate not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    if request.META.get("HTTP_HX_REQUEST") == "true":
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "skillZoneContainerReload"
        return response
    return redirect(skill_zone_view)


@login_required
@hx_request_required
def to_skill_zone(request, cand_id):
    """
    This method is used to Add candidate into talent pool
    Args:
        cand_id : candidate instance id
    """
    if not (
        request.user.has_perm("recruitment.change_candidate")
        or request.user.has_perm("recruitment.add_skillzonecandidate")
    ):
        messages.info(request, _("You dont have permission."))
        return HorillaRedirect(request)

    candidate = Candidate.objects.get(id=cand_id)
    template = "skill_zone_cand/to_skill_zone_form.html"
    form = ToSkillZoneForm(
        initial={
            "candidate_id": candidate,
            "skill_zone_ids": SkillZoneCandidate.objects.filter(
                candidate_id=candidate
            ).values_list("skill_zone_id", flat=True),
        }
    )
    if request.method == "POST":
        form = ToSkillZoneForm(request.POST)
        if form.is_valid():
            skill_zones = form.cleaned_data["skill_zone_ids"]
            for zone in skill_zones:
                if not SkillZoneCandidate.objects.filter(
                    candidate_id=candidate, skill_zone_id=zone
                ).exists():
                    zone_candidate = SkillZoneCandidate()
                    zone_candidate.candidate_id = candidate
                    zone_candidate.skill_zone_id = zone
                    zone_candidate.reason = form.cleaned_data["reason"]
                    zone_candidate.save()
            messages.success(request, _("Candidate added to talent pool successfully"))
            return HorillaRedirect(request)
    return render(request, template, {"form": form, "cand_id": cand_id})


@login_required
def update_candidate_rating(request, cand_id):
    """
    This method is used to update the candidate rating
    Args:
        id : candidate rating instance id
    """
    candidate = Candidate.find(cand_id)
    if candidate:
        employee_id = request.user.employee_get
        rating = request.POST.get("rating")
        rate = CandidateRating.objects.get(
            candidate_id=candidate, employee_id=employee_id
        )
        rate.rating = int(rating)
        rate.save()
    else:
        messages.error(request, _("No Candidate found matching the query"))

    return redirect(recruitment_pipeline)


def open_recruitments(request):
    """
    This method is used to render the open recruitment page
    """
    recruitments = Recruitment.default.filter(
        closed=False, is_published=True, is_active=True
    )
    context = {
        "recruitments": recruitments,
    }
    response = render(request, "recruitment/open_recruitments.html", context)
    response["X-Frame-Options"] = "ALLOW-FROM *"

    return response


@hx_request_required
def recruitment_details(request, id):
    """
    This method is used to render the recruitment details page.

    Public/unauthenticated visitors can view this (it's reached from the
    public open-recruitments page); recruitment_details.html itself gates
    the sensitive applied/capacity numbers behind
    perms.recruitment.view_recruitment.
    """
    recruitment = Recruitment.default.filter(id=id).first()
    if not recruitment:
        messages.error(request, _("Recruitment not found."))
        return HorillaRedirect(request)
    context = {
        "recruitment": recruitment,
    }
    return render(request, "recruitment/recruitment_details.html", context)


@login_required
@manager_can_enter("recruitment.view_candidate")
def get_mail_log(request, pk):
    """
    This method is used to track mails sent along with the status
    """

    candidate_obj = Candidate.find(pk)
    if not candidate_obj:
        return HorillaRedirect(request, message=_("Candidate not found."))

    tracked_mails = EmailLog.objects.filter(to__icontains=candidate_obj.email).order_by(
        "-created_at"
    )
    return render(
        request,
        "candidate/mail_log.html",
        {
            "candidate": candidate_obj,
            "tracked_mails": tracked_mails,
        },
    )


@login_required
@hx_request_required
@permission_required("recruitment.add_recruitmentgeneralsetting")
def candidate_self_tracking(request):
    """
    This method is used to update the recruitment general setting
    """
    selected_company = request.session.get("selected_company")
    company_id = (
        None if not selected_company or selected_company == "all" else selected_company
    )
    settings, created = RecruitmentGeneralSetting.objects.get_or_create(
        company_id_id=company_id
    )
    if request.GET.get("candidate_self_tracking") == "true":
        settings.candidate_self_tracking = True
        message = _("Application Tracking is enabled ")
    else:
        settings.candidate_self_tracking = False
        message = _("Application Tracking is disabled ")
    settings.save()
    messages.success(request, message)
    return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")


@login_required
@hx_request_required
@permission_required("recruitment.add_recruitmentgeneralsetting")
def candidate_self_tracking_rating_option(request):
    """
    This method is used to enable/disable the selt tracking rating field
    """
    selected_company = request.session.get("selected_company")
    company_id = (
        None if not selected_company or selected_company == "all" else selected_company
    )
    settings, created = RecruitmentGeneralSetting.objects.get_or_create(
        company_id_id=company_id
    )
    if request.GET.get("candidate_self_tracking") == "true":
        settings.show_overall_rating = True
        message = _("Rating visibility is enabled ")
    else:
        settings.show_overall_rating = False
        message = _("Rating visibility is disabled ")
    settings.save()
    messages.success(request, message)
    return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")


def candidate_login(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        mobile = request.POST.get("phone", "").strip()

        backend = CandidateAuthenticationBackend()
        candidate = backend.authenticate(request, username=email, password=mobile)

        if candidate is not None:
            request.session["candidate_id"] = candidate.id
            request.session["candidate_email"] = candidate.email
            return redirect("candidate-self-status-tracking")
        else:
            return render(
                request, "candidate/self_login.html", {"error": "Invalid credentials"}
            )

    return render(request, "candidate/self_login.html")


def candidate_logout(request):
    """Logs out the candidate by clearing session data."""

    request.session.pop("candidate_id", None)
    request.session.pop("candidate_email", None)
    messages.success(request, _("You have been logged out."))
    return redirect("candidate_login")


@candidate_login_required
def candidate_self_status_tracking(request):
    """
    This method is accessed by the candidates
    """
    self_tracking_feature = check_candidate_self_tracking(request)[
        "check_candidate_self_tracking"
    ]
    if self_tracking_feature:
        candidate_id = request.session.get("candidate_id")

        if not candidate_id:
            return redirect("candidate-login/")

        candidate = Candidate.objects.get(pk=candidate_id)
        interviews = candidate.candidate_interview.annotate(
            is_today=Case(
                When(interview_date=date.today(), then=0),
                default=1,
                output_field=IntegerField(),
            )
        ).order_by("is_today", "-interview_date", "interview_time")
        return render(
            request,
            "candidate/candidate_self_tracking.html",
            {"candidate": candidate, "interviews": interviews},
        )
    return render(request, "404.html")


@login_required
@manager_can_enter("recruitment.add_candidate")
def candidate_self_status_tracking_managers_view(request, cand_id):
    """
    This method is accessed by the candidates
    """
    self_tracking_feature = check_candidate_self_tracking(request)[
        "check_candidate_self_tracking"
    ]
    if self_tracking_feature:
        candidate_id = request.session.get("candidate_id")
        if (
            request.user.has_perm("recruitment.view_candidate")
            or request.user.employee_get.recruitment_set.filter(
                candidate__id=cand_id
            ).exists()
            or request.user.employee_get.stage_set.filter(candidate=cand_id).exists()
        ):
            request.session["candidate_id"] = cand_id
            candidate_id = cand_id

        if not candidate_id:
            return redirect("candidate-login/")

        candidate = Candidate.objects.get(pk=candidate_id)
        interviews = candidate.candidate_interview.annotate(
            is_today=Case(
                When(interview_date=date.today(), then=0),
                default=1,
                output_field=IntegerField(),
            )
        ).order_by("is_today", "-interview_date", "interview_time")

        return render(
            request,
            "candidate/candidate_self_tracking.html",
            {"candidate": candidate, "interviews": interviews},
        )
    return render(request, "404.html")


@login_required
@hx_request_required
@permission_required("recruitment.add_rejectreason")
def create_reject_reason(request):
    """
    This method is used to create/update the reject reasons
    """
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    if instance_id:
        instance = RejectReason.objects.get(id=instance_id)
    form = RejectReasonForm(instance=instance)
    if request.method == "POST":
        form = RejectReasonForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Reject reason saved"))
            return HorillaRedirect(request)
    return render(request, "settings/reject_reason_form.html", {"form": form})


@login_required
@permission_required("recruitment.view_recruitment")
def self_tracking_feature(request):
    """
    Recruitment optional feature for candidate self tracking
    """
    return render(request, "recruitment/settings/settings.html")


@login_required
@hx_request_required
@permission_required("recruitment.delete_rejectreason")
def delete_reject_reason(request):
    """
    This method is used to delete the reject reasons
    """
    id = request.GET.get("id")
    if not (reason := RejectReason.find(id)):
        messages.error(request, _("No Rejection Reason found matching the query."))
        return HttpResponse("<script>$('.reload-record').click();</script>")

    is_last = RejectReason.objects.count() == 1
    reason.delete()
    messages.success(request, _(f"{reason.title} is deleted."))
    script = (
        "$('.reload-record').click();"
        if is_last
        else "$('#reloadMessagesButton').click();"
    )
    return HttpResponse(f"<script>{script}</script>")


# Loaded once per worker process at import time (spaCy model load is slow;
# never call spacy.load() inside a request-handling function).
_resume_nlp = spacy.load("en_core_web_sm")


def extract_text_with_font_info(pdf):
    """
    This method is used to extract text from the pdf and create a list of dictionaries containing details about the extracted text.
    Args:
        pdf (): pdf file to extract text from
    """
    pdf_bytes = pdf.read()
    pdf_doc = io.BytesIO(pdf_bytes)
    doc = pymupdf.open("pdf", pdf_doc)
    text_info = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            try:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text_info.append(
                            {
                                "text": span["text"],
                                "font_size": span["size"],
                                "capitalization": sum(
                                    1 for c in span["text"] if c.isupper()
                                )
                                / len(span["text"]),
                            }
                        )
            except:
                pass

    return text_info


def rank_text(text_info):
    """
    This method is used to rank the text

    Args:
        text_info: List of dictionary containing the details

    Returns:
        Returns a sorted list
    """
    ranked_text = sorted(
        text_info, key=lambda x: (x["font_size"], x["capitalization"]), reverse=True
    )
    return ranked_text


# --- Legacy implementation (superseded below, kept for reference) ---
# def dob_matching(dob):
#     """
#     This method is used to change the date format to YYYY-MM-DD
#
#     Args:
#         dob: Date
#
#     Returns:
#         Return date in YYYY-MM-DD
#     """
#     date_formats = [
#         "%Y-%m-%d",
#         "%Y/%m/%d",
#         "%d-%m-%Y",
#         "%d/%m/%Y",
#         "%Y.%m.%d",
#         "%d.%m.%Y",
#     ]
#
#     for fmt in date_formats:
#         try:
#             parsed_date = datetime.strptime(dob, fmt)
#             return parsed_date.strftime("%Y-%m-%d")
#         except ValueError:
#             continue
#
#     return dob


def dob_matching(dob):
    """
    This method is used to change the date format to YYYY-MM-DD

    Args:
        dob: Date

    Returns:
        Return date in YYYY-MM-DD
    """
    try:
        parsed_date = dateutil_parser.parse(dob, dayfirst=True, fuzzy=True)
        return parsed_date.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return dob


# --- Legacy implementation (superseded below, kept for reference) ---
# def extract_info(pdf):
#     """
#     This method creates the contact information dictionary from the provided pdf file
#     Args:
#         pdf_file: pdf file
#     """
#     extracted_info = {
#         "full_name": "",
#         "address": "",
#         "country": "",
#         "state": "",
#         "phone_number": "",
#         "dob": "",
#         "email_id": "",
#         "zip": "",
#     }
#     if not pdf:
#         return extracted_info
#
#     text_info = extract_text_with_font_info(pdf)
#     ranked_text = rank_text(text_info)
#
#     phone_pattern = re.compile(r"\b\+?\d{1,2}\s?\d{9,10}\b")
#     dob_pattern = re.compile(
#         r"\b(?:\d{1,2}|\d{4})[-/.,]\d{1,2}[-/.,](?:\d{1,2}|\d{4})\b"
#     )
#     email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
#     zip_code_pattern = re.compile(r"\b\d{5,6}(?:-\d{4})?\b")
#
#     name_candidates = [
#         item["text"]
#         for item in ranked_text
#         if item["font_size"] == max(item["font_size"] for item in ranked_text)
#     ]
#
#     if name_candidates:
#         extracted_info["full_name"] = " ".join(name_candidates)
#
#     for item in ranked_text:
#         text = item["text"]
#
#         if not text:
#             continue
#
#         if not extracted_info["phone_number"]:
#             phone_match = phone_pattern.search(text)
#             if phone_match:
#                 extracted_info["phone_number"] = phone_match.group()
#
#         if not extracted_info["dob"]:
#             dob_match = dob_pattern.search(text)
#             if dob_match:
#                 extracted_info["dob"] = dob_matching(dob_match.group())
#
#         if not extracted_info["zip"]:
#             zip_match = zip_code_pattern.search(text)
#             if zip_match:
#                 extracted_info["zip"] = zip_match.group()
#
#         if not extracted_info["email_id"]:
#             email_match = email_pattern.search(text)
#             if email_match:
#                 extracted_info["email_id"] = email_match.group()
#
#         if "address" in text.lower() and not extracted_info["address"]:
#             extracted_info["address"] = text.replace("Address:", "").strip()
#
#         for item in text.split(" "):
#             if item.capitalize() in country_arr:
#                 extracted_info["country"] = item
#
#         for item in text.split(" "):
#             if item.capitalize() in states:
#                 extracted_info["state"] = item
#
#     return extracted_info


def extract_info(pdf):
    """
    This method creates the contact information dictionary from the provided pdf file
    Args:
        pdf_file: pdf file
    """
    extracted_info = {
        "full_name": "",
        "address": "",
        "country": "",
        "state": "",
        "phone_number": "",
        "dob": "",
        "email_id": "",
        "zip": "",
        "portfolio": "",
    }
    if not pdf:
        return extracted_info

    text_info = extract_text_with_font_info(pdf)
    ranked_text = rank_text(text_info)

    if not ranked_text:
        return extracted_info

    # Use text_info (natural document order), not ranked_text (font-size sorted),
    # since spaCy's NER needs coherent word order to detect entities correctly.
    full_text = "\n".join(item["text"] for item in text_info if item["text"])
    # added: line list, so a spaCy entity's char offset can be mapped back to
    # its source line for the address fallback below.
    lines = [item["text"] for item in text_info if item["text"]]

    dob_pattern = re.compile(
        r"\b(?:\d{1,2}|\d{4})[-/.,]\d{1,2}[-/.,](?:\d{1,2}|\d{4})\b"
    )
    email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    zip_code_pattern = re.compile(r"\b\d{5,6}(?:-\d{4})?\b")
    dob_keyword_pattern = re.compile(r"\b(dob|date\s+of\s+birth|born)\b", re.IGNORECASE)
    url_pattern = re.compile(
        r"\b(?:https?://\S+|www\.\S+"
        r"|(?:github|linkedin|gitlab|behance|dribbble)\.com/\S+)",
        re.IGNORECASE,
    )

    max_font_size = max(item["font_size"] for item in ranked_text)
    top_spans = [item for item in ranked_text if item["font_size"] == max_font_size]
    name_doc = _resume_nlp(" ".join(item["text"] for item in top_spans))
    person_names = [ent.text for ent in name_doc.ents if ent.label_ == "PERSON"]
    if person_names:
        extracted_info["full_name"] = " ".join(person_names)
    else:
        extracted_info["full_name"] = " ".join(item["text"] for item in top_spans)

    # added: fallback address candidate, taken from the resume line containing
    # the matched country/state entity, used only if the "Address:"-keyword
    # pass above found nothing.
    def _line_for_char_offset(offset):
        """Map a spaCy entity's char offset in full_text back to its source line."""
        pos = 0
        for line in lines:
            end = pos + len(line)
            if pos <= offset <= end:
                return line
            pos = end + 1  # account for the "\n" joiner
        return None

    gpe_address_candidate = None

    doc = _resume_nlp(full_text)
    for ent in doc.ents:
        if ent.label_ != "GPE":
            continue
        if not extracted_info["country"]:
            try:
                country_match = pycountry.countries.lookup(ent.text)
                extracted_info["country"] = getattr(
                    country_match, "common_name", country_match.name
                )
                # added: capture the containing line as an address candidate
                if not gpe_address_candidate:
                    candidate_line = _line_for_char_offset(ent.start_char)
                    if (
                        candidate_line
                        and candidate_line.strip().lower() != ent.text.lower()
                    ):
                        gpe_address_candidate = candidate_line.strip()
                continue
            except LookupError:
                pass
        if not extracted_info["state"]:
            try:
                subdivision_match = pycountry.subdivisions.lookup(ent.text)
                extracted_info["state"] = subdivision_match.name
                # added: capture the containing line as an address candidate
                if not gpe_address_candidate:
                    candidate_line = _line_for_char_offset(ent.start_char)
                    if (
                        candidate_line
                        and candidate_line.strip().lower() != ent.text.lower()
                    ):
                        gpe_address_candidate = candidate_line.strip()
            except LookupError:
                pass

    phone_matches = list(phonenumbers.PhoneNumberMatcher(full_text, None))
    if phone_matches:
        extracted_info["phone_number"] = phonenumbers.format_number(
            phone_matches[0].number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )

    for item in ranked_text:
        text = item["text"]

        if not text:
            continue

        if not extracted_info["dob"]:
            dob_match = dob_pattern.search(text)
            if dob_match and dob_keyword_pattern.search(text):
                extracted_info["dob"] = dob_matching(dob_match.group())

        if not extracted_info["zip"]:
            zip_match = zip_code_pattern.search(text)
            if zip_match:
                extracted_info["zip"] = zip_match.group()

        if not extracted_info["email_id"]:
            email_match = email_pattern.search(text)
            if email_match:
                extracted_info["email_id"] = email_match.group()

        if "address" in text.lower() and not extracted_info["address"]:
            extracted_info["address"] = text.replace("Address:", "").strip()

        if not extracted_info["portfolio"]:
            url_match = url_pattern.search(text)
            if url_match:
                extracted_info["portfolio"] = url_match.group()

    # added: fall back to the spaCy-derived address candidate only if the
    # explicit "Address:" keyword pass above found nothing.
    if not extracted_info["address"] and gpe_address_candidate:
        extracted_info["address"] = gpe_address_candidate

    return extracted_info


def resume_completion(request):
    """
    This function is returns the data for completing the candidate creation form
    """
    resume_file = request.FILES.get("resume")
    contact_info = extract_info(resume_file)

    return JsonResponse(contact_info)


def check_vaccancy(request):
    """
    check vaccancy of recruitment
    """
    stage_id = request.GET.get("stageId")
    stage = Stage.objects.get(id=stage_id)
    message = _("No message")
    if stage and stage.recruitment_id.is_vacancy_filled():
        message = _("Vaccancy is filled")
    return JsonResponse({"message": message})


@login_required
def skills_view(request):
    """
    This function is used to view skills page in settings
    """
    skills = Skill.objects.all()
    return render(request, "settings/skills/skills_view.html", {"skills": skills})


@login_required
@hx_request_required
def create_skills(request):
    """
    This method is used to create the skills
    """
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    dynamic = request.GET.get("dynamic")
    hx_vals = request.GET.get("data")
    instance = None
    if instance_id:
        instance = Skill.objects.get(id=instance_id)
    form = SkillsForm(instance=instance)
    if request.method == "POST":
        form = SkillsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Skill created successfully"))

            if request.GET.get("dynamic") == "True":

                url = reverse("recruitment-create")
                instance = Skill.objects.all().last()
                mutable_get = request.GET.copy()
                skills = mutable_get.getlist("skills")
                skills.remove("create")
                skills.append(str(instance.id))
                mutable_get["skills"] = skills[-1]
                skills.pop()
                data = mutable_get.urlencode()
                try:
                    for item in skills:
                        data += f"&skills={item}"
                except:
                    pass
                return redirect(f"{url}?{data}")

            return HttpResponse("<script>window.location.reload()</script>")

    context = {
        "form": form,
        "dynamic": dynamic,
        "hx_vals": hx_vals,
    }

    return render(request, "settings/skills/skills_form.html", context=context)


@login_required
@hx_request_required
@permission_required("recruitment.delete_rejectreason")
def delete_skills(request, id=None):
    """
    This method is used to delete the skills
    """
    ids = request.GET.getlist("ids")

    skills = Skill.objects.filter(id__in=ids)
    titles = list(skills.values_list("title", flat=True))

    count_before = skills.count()
    deleted_count, d = skills.delete()

    for title in titles:
        messages.success(request, _("%(title)s is deleted.") % {"title": title})

    if count_before - deleted_count == 0:
        return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")

    return HttpResponse("<script>$('.reload-record').click()</script>")


@login_required
@hx_request_required
@manager_can_enter("recruitment.add_candidate")
def view_bulk_resumes(request):
    """
    This function returns the bulk_resume.html page to the modal
    """
    rec_id = eval_validate(str(request.GET.get("rec_id")))
    if not rec_id:
        return HttpResponse()
    # Recruitment.objects is company-scoped; Resume is not (it has no
    # company_id of its own), so resolving the recruitment first is what
    # keeps another company's resumes out of this list.
    recruitment = Recruitment.objects.filter(id=rec_id).first()
    if not recruitment:
        return HttpResponse()
    resumes = Resume.objects.filter(recruitment_id=recruitment)

    return render(
        request, "pipeline/bulk_resume.html", {"resumes": resumes, "rec_id": rec_id}
    )


@login_required
@hx_request_required
@manager_can_enter("recruitment.add_candidate")
def add_bulk_resumes(request):
    """
    This function is used to create bulk resume
    """
    rec_id = eval_validate(str(request.GET.get("rec_id")))
    recruitment = Recruitment.objects.filter(id=rec_id).first()
    if not recruitment:
        return HttpResponse()
    if request.method == "POST":
        files = request.FILES.getlist("files")
        for file in files:
            Resume.objects.create(
                file=file,
                recruitment_id=recruitment,
            )
        CACHE.delete(f"matching_resumes_{rec_id}")

        url = reverse("view-bulk-resume")
        query_params = f"?rec_id={rec_id}"

        return redirect(f"{url}{query_params}")


@login_required
@hx_request_required
@manager_can_enter("recruitment.add_candidate")
def delete_resume_file(request):
    """
    Used to delete resume
    """
    ids = request.GET.getlist("ids")
    rec_id = request.GET.get("rec_id")
    # Scope the delete to a recruitment this user can actually reach.
    # manager_can_enter admits any reporting manager, and Resume is not
    # company-scoped, so an unscoped filter let a manager in one company
    # delete another company's resumes by passing their ids.
    recruitment = Recruitment.objects.filter(id=rec_id).first()
    if not recruitment:
        return HttpResponse(status=404)
    Resume.objects.filter(id__in=ids, recruitment_id=recruitment).delete()
    CACHE.delete(f"matching_resumes_{rec_id}")

    url = reverse("view-bulk-resume")
    query_params = f"?rec_id={rec_id}"

    return redirect(f"{url}{query_params}")


# --- Legacy implementation (superseded below, kept for reference) ---
# def extract_words_from_pdf(pdf_file):
#     """
#     This method is used to extract the words from the pdf file into a list.
#     Args:
#         pdf_file: pdf file
#
#     """
#     pdf_document = fitz.open(pdf_file.path)
#
#     words = []
#
#     for page_num in range(len(pdf_document)):
#         page = pdf_document.load_page(page_num)
#         page_text = page.get_text()
#
#         page_words = re.findall(r"\b\w+\b", page_text.lower())
#
#         words.extend(page_words)
#
#     pdf_document.close()
#
#     return words


def extract_words_from_pdf(pdf_file):
    """
    This method is used to extract the raw text content from the pdf file.
    Args:
        pdf_file: pdf file

    """
    pdf_document = pymupdf.open(pdf_file.path)

    text_chunks = []

    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        text_chunks.append(page.get_text())

    pdf_document.close()

    return "\n".join(text_chunks).lower()


def skill_match_count(text, skills, threshold=85):
    """
    This method counts how many of the given skills are present in the resume
    text, using fuzzy matching so multi-word skills and near-variant spellings
    (e.g. "Node.js" vs "NodeJS") are still counted as a match.

    Args:
        text: Full lowercased resume text
        skills: Iterable of skill title strings
        threshold: Minimum rapidfuzz partial_ratio score (0-100) to count as a match
    """
    if not text:
        return 0
    text = text.lower()
    return sum(fuzz.partial_ratio(skill.lower(), text) >= threshold for skill in skills)


@login_required
@hx_request_required
@manager_can_enter("recruitment.add_candidate")
def matching_resumes(request, rec_id):
    """
    This function returns the matching resume table after sorting the resumes according to their scores

    Args:
        rec_id: Recruitment ID

    """
    cache_key = f"matching_resumes_{rec_id}"
    ranked_resumes = CACHE.get(cache_key)
    if ranked_resumes is None:
        recruitment = Recruitment.objects.filter(id=rec_id).first()
        if not recruitment:
            return HttpResponse()
        skills = recruitment.skills.values_list("title", flat=True)
        resumes = recruitment.resume.all()
        is_candidate = resumes.filter(is_candidate=True)
        is_candidate_ids = set(is_candidate.values_list("id", flat=True))

        resume_ranks = []
        for resume in resumes:
            text = extract_words_from_pdf(resume.file)
            matching_skills_count = skill_match_count(text, skills)

            item = {"resume": resume, "matching_skills_count": matching_skills_count}
            if not len(text):
                item["image_pdf"] = True

            resume_ranks.append(item)

        candidate_resumes = [
            rank for rank in resume_ranks if rank["resume"].id in is_candidate_ids
        ]
        non_candidate_resumes = [
            rank for rank in resume_ranks if rank["resume"].id not in is_candidate_ids
        ]

        non_candidate_resumes = sorted(
            non_candidate_resumes,
            key=lambda x: x["matching_skills_count"],
            reverse=True,
        )
        candidate_resumes = sorted(
            candidate_resumes, key=lambda x: x["matching_skills_count"], reverse=True
        )

        ranked_resumes = non_candidate_resumes + candidate_resumes
        # A finite TTL, not timeout=None: the ranking is derived from resume
        # files and the recruitment's skill list, both of which change without
        # every edit path remembering to invalidate this key.
        CACHE.set(cache_key, ranked_resumes, timeout=900)

    return render(
        request,
        "pipeline/matching_resumes.html",
        {
            "matched_resumes": ranked_resumes,
            "rec_id": rec_id,
        },
    )


@login_required
@manager_can_enter("recruitment.add_candidate")
def matching_resume_completion(request):
    """
    This function is returns the data for completing the candidate creation form
    """
    resume_id = request.GET.get("resume_id")
    resume_obj = get_object_or_404(Resume, id=resume_id)
    resume_file = resume_obj.file
    contact_info = extract_info(resume_file)

    return JsonResponse(contact_info)


@login_required
@permission_required("recruitment.view_rejectreason")
def candidate_reject_reasons(request):
    """
    This method is used to view all the reject reasons
    """
    reject_reasons = RejectReason.objects.all()
    return render(
        request, "settings/reject_reasons.html", {"reject_reasons": reject_reasons}
    )


@login_required
def hired_candidate_chart(request):
    """
    function used to show hired candidates in all recruitments.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return Json response labels, data, background_color, border_color.
    """
    labels = []
    data = []
    background_color = []
    border_color = []
    recruitments = Recruitment.objects.filter(closed=False, is_active=True)
    for recruitment in recruitments:
        red = random.randint(0, 255)
        green = random.randint(0, 255)
        blue = random.randint(0, 255)
        background_color.append(f"rgba({red}, {green}, {blue}, 0.2")
        border_color.append(f"rgb({red}, {green}, {blue})")
        labels.append(f"{recruitment}")
        data.append(recruitment.candidate.filter(hired=True).count())
    return JsonResponse(
        {
            "labels": labels,
            "data": data,
            "background_color": background_color,
            "border_color": border_color,
            "message": _("No records available at the moment."),
        },
        safe=False,
    )


@login_required
@hx_request_required
def candidate_document_request(request):
    """
    This function is used to create document requests of an employee in employee requests view.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns: return document_request_create_form template
    """
    candidate_id = (
        request.GET.get("candidate_id") if request.GET.get("candidate_id") else None
    )
    form = CandidateDocumentRequestForm(initial={"candidate_id": candidate_id})
    if request.method == "POST":
        form = CandidateDocumentRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Document request created successfully"))
            return HttpResponse(
                "<script>"
                "$('.oh-modal--show').removeClass('oh-modal--show');"
                "$('#applyFilter').click();"
                "$('#reloadMessagesButton').click();"
                "</script>"
            )

    context = {
        "form": form,
    }
    return render(
        request, "documents/document_request_create_form.html", context=context
    )


@login_required
@hx_request_required
def document_create(request, id):
    """
    This function is used to create documents from employee individual & profile view.

    Parameters:
    request (HttpRequest): The HTTP request object.
    emp_id (int): The id of the employee

    Returns: return document_tab template
    """
    candidate_id = Candidate.objects.filter(id=id).first()
    if not candidate_id:
        return HttpResponse()
    form = CandidateDocumentForm(initial={"candidate_id": candidate_id})
    form.fields["candidate_id"].queryset = Candidate.objects.filter(id=id)
    if request.method == "POST":
        form = CandidateDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, _("Document created successfully."))
            return HorillaRedirect(request)

    context = {
        "form": form,
        "candidate_id": candidate_id,
    }
    return render(request, "candidate/document_create_form.html", context=context)


@login_required
def update_document_title(request, id):
    """
    This function is used to create documents from employee individual & profile view.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns: return document_tab template
    """
    document = get_object_or_404(CandidateDocument, id=id)
    name = request.POST.get("title")
    if request.method == "POST":
        document.title = name
        document.save()

        return JsonResponse(
            {"success": True, "message": "Document title updated successfully"}
        )
    else:
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )


@login_required
@hx_request_required
@manager_can_enter("recruitment.delete_candidatedocument")
def document_delete(request, id):
    """
    Handle the deletion of a document, with permissions and error handling.

    This view function attempts to delete a document specified by its ID.
    If the user does not have the "delete_document" permission, it restricts
    deletion to documents owned by the user. It provides appropriate success
    or error messages based on the outcome. If the document is protected and
    cannot be deleted, it handles the exception and informs the user.
    """
    try:
        document = CandidateDocument.objects.filter(id=id)
        if document:
            document.delete()
            messages.success(
                request,
                _(
                    f"Document request {document.first()} for {document.first().employee_id} deleted successfully"
                ),
            )
        else:
            messages.error(request, _("Document not found"))

    except ProtectedError:
        messages.error(request, _("You cannot delete this document."))

    if "HTTP_HX_TARGET" in request.META and request.META.get(
        "HTTP_HX_TARGET"
    ).startswith("document"):
        clear_messages(request)
        return HttpResponse()
    else:
        return HorillaRedirect(request)


def candidate_documents_visible_to(request):
    """CandidateDocument rows the current requester is allowed to touch.

    `candidate_login_required` only asserts that *some* candidate is logged in
    (`"candidate_id" in request.session`), so a view resolving a document by
    client-supplied id alone serves any candidate's file to any other -- the
    ids are sequential, so one self-registered account can harvest every
    applicant's resume and identity documents. Reported as
    GHSA-p745-9729-g8jw.

    Recruiters keep full access through the model permission; a candidate is
    scoped to their own session id. Mirrors the scoping employee/views.py
    already applies to document_delete.
    """
    queryset = CandidateDocument.objects.all()
    if request.user.is_authenticated and request.user.has_perm(
        "recruitment.view_candidatedocument"
    ):
        return queryset

    candidate_id = request.session.get("candidate_id")
    if candidate_id is None:
        return queryset.none()
    return queryset.filter(candidate_id__id=candidate_id)


@candidate_login_required
@hx_request_required
def file_upload(request, id):
    """
    This function is used to upload documents of an employee in employee individual & profile view.

    Parameters:
    request (HttpRequest): The HTTP request object.
    id (int): The id of the document.

    Returns: return document_form template
    """
    document_item = candidate_documents_visible_to(request).filter(id=id).first()
    if not document_item:
        return HttpResponse()
    form = CandidateDocumentUpdateForm(instance=document_item)
    if request.method == "POST":
        form = CandidateDocumentUpdateForm(
            request.POST, request.FILES, instance=document_item
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Document uploaded successfully"))
            return HorillaRedirect(request)

    context = {
        "form": form,
        "document": document_item,
    }
    return render(request, "candidate/document_form.html", context=context)


@candidate_login_required
@hx_request_required
def view_file(request, id):
    """
    This function used to view the uploaded document in the modal.
    Parameters:

    request (HttpRequest): The HTTP request object.
    id (int): The id of the document.

    Returns: return view_file template
    """
    document_obj = candidate_documents_visible_to(request).filter(id=id).first()
    if not document_obj:
        return HttpResponse()
    context = {
        "document": document_obj,
    }
    if document_obj.document:
        file_path = document_obj.document.path
        file_extension = os.path.splitext(file_path)[1][1:].lower()

        content_type = get_content_type(file_extension)

        try:
            with open(file_path, "rb") as file:
                file_content = file.read()
        except:
            file_content = None

        context["file_content"] = file_content
        context["file_extension"] = file_extension
        context["content_type"] = content_type

    return render(request, "candidate/view_file.html", context)


@login_required
@hx_request_required
@manager_can_enter("recruitment.change_candidatedocument")
def document_approve(request, id):
    """
    This function used to view the approve uploaded document.
    Parameters:

    request (HttpRequest): The HTTP request object.
    id (int): The id of the document.

    Returns:
    """
    document_obj = get_object_or_404(CandidateDocument, id=id)
    if document_obj.document:
        document_obj.status = "approved"
        document_obj.save()
        messages.success(request, _("Document request approved"))
    else:
        messages.error(request, _("No document uploaded"))

    return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter("recruitment.change_candidatedocument")
def document_reject(request, id):
    """
    This function used to view the reject uploaded document.
    Parameters:

    request (HttpRequest): The HTTP request object.
    id (int): The id of the document.

    Returns:
    """
    document_obj = get_object_or_404(CandidateDocument, id=id)
    form = CandidateDocumentRejectForm()
    if document_obj.document:
        if request.method == "POST":
            form = CandidateDocumentRejectForm(request.POST, instance=document_obj)
            if form.is_valid():
                instance = form.save(commit=False)
                document_obj.reject_reason = instance.reject_reason
                document_obj.status = "rejected"
                document_obj.save()
                messages.error(request, _("Document request rejected"))

                return HorillaRedirect(request)
    else:
        messages.error(request, _("No document uploaded"))
        return HorillaRedirect(request)

    return render(
        request,
        "candidate/reject_form.html",
        {"form": form, "document_obj": document_obj},
    )


@candidate_login_required
def candidate_add_notes(request, cand_id):
    """
    This method renders template component to add candidate remark
    """

    candidate = Candidate.find(cand_id)
    if not candidate:
        return HorillaRedirect(
            request, message=_("No Candidate found matching the query.")
        )

    updated_by = request.user.employee_get if request.user.is_authenticated else None
    label = (
        request.user.employee_get.get_full_name()
        if request.user.is_authenticated
        else candidate.name
    )

    form = StageNoteForm(initial={"candidate_id": cand_id})
    if request.method == "POST":
        form = StageNoteForm(
            request.POST,
            request.FILES,
        )
        if form.is_valid():
            note, attachment_ids = form.save(commit=False)
            note.candidate_id = candidate
            note.stage_id = candidate.stage_id
            note.updated_by = updated_by
            note.candidate_can_view = True
            note.save()
            note.stage_files.set(attachment_ids)
            messages.success(request, _("Note added successfully.."))
            with contextlib.suppress(Exception):
                managers = candidate.recruitment_id.recruitment_managers.all()
                stage_managers = candidate.stage_id.stage_managers.all()

                all_managers = managers | stage_managers
                users = [
                    employee.employee_user_id for employee in all_managers.distinct()
                ]

                notify.send(
                    candidate,
                    label=label,
                    recipient=users,
                    verb=f"{label} has added a note on the candidate {candidate}",
                    verb_ar=f"أضاف {label} ملاحظة حول المرشح {candidate}",
                    verb_de=f"{label} hat dem {candidate} eine Notiz hinzugefügt.",
                    verb_es=f"{label} agregó una nota al {candidate}.",
                    verb_fr=f"{label} a ajouté une note à {candidate}.",
                    icon="people-circle",
                    redirect=reverse(
                        "candidate-view-individual", kwargs={"cand_id": cand_id}
                    ),
                )

    return render(
        request,
        "candidate/candidate_self_tracking.html",
        {
            "candidate": candidate,
            "note_form": form,
        },
    )


@login_required
@hx_request_required
def employee_profile_interview_tab(request):
    employee = request.user.employee_get

    interviews = employee.interviewschedule_set.annotate(
        is_today=Case(
            When(interview_date=date.today(), then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by("is_today", "-interview_date", "interview_time")

    return render(request, "tabs/scheduled_interview.html", {"interviews": interviews})


@login_required
@hx_request_required
@permission_required("recruitment.delete_rejectedcandidate")
def delete_candidate_rejection(request, rej_id):
    """
    This method is used to delete candidate rejection
    """
    try:
        instance = RejectedCandidate.objects.filter(id=rej_id).first()
        if instance:
            instance.delete()
            messages.success(request, _("Candidate rejection deleted successfully"))
        else:
            messages.error(request, _("Candidate rejection not found"))
    except Exception as e:
        messages.error(request, _("Error occurred while deleting candidate rejection"))
    return HorillaRedirect(request)
