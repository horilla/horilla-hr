"""
views.py

This module contains the view functions for handling HTTP requests and rendering
responses in your application.

Each view function corresponds to a specific URL route and performs the necessary
actions to handle the request, process data, and generate a response.

This module is part of the recruitment project and is intended to
provide the main entry points for interacting with the application's functionality.
"""

import contextlib
import json
import logging
import os
import random
import secrets
from urllib.parse import parse_qs

from django import template
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage, send_mail
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as __
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from base.backends import ConfiguredEmailBackend
from base.methods import (
    closest_numbers,
    generate_pdf,
    get_key_instances,
    get_pagination,
    sanitize_mail_template_body,
    sortby,
)
from base.models import HorillaMailTemplate, JobPosition
from employee.models import Employee, EmployeeBankDetails, EmployeeWorkInformation
from horilla import settings
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.group_by import group_by_queryset as general_group_by
from horilla.http.response import HorillaRedirect
from horilla_auth.models import HorillaUser
from horilla_documents.models import Document
from notifications.signals import notify
from onboarding.decorators import (
    all_manager_can_enter,
    recruitment_manager_can_enter,
    stage_manager_can_enter,
)
from onboarding.filters import OnboardingCandidateFilter, OnboardingStageFilter
from onboarding.forms import (
    BankDetailsCreationForm,
    EmployeeCreationForm,
    OnboardingCandidateForm,
    OnboardingTaskForm,
    OnboardingViewStageForm,
    OnboardingViewTaskForm,
    UserCreationForm,
)
from onboarding.models import (
    CandidateStage,
    CandidateTask,
    OnboardingPortal,
    OnboardingStage,
    OnboardingTask,
)
from recruitment.filters import CandidateFilter, CandidateReGroup, RecruitmentFilter
from recruitment.forms import RejectedCandidateForm
from recruitment.models import Candidate, Recruitment, RejectedCandidate
from recruitment.pipeline_grouper import group_by_queryset

logger = logging.getLogger(__name__)


@login_required
@hx_request_required
@recruitment_manager_can_enter("onboarding.add_onboardingstage")
def stage_creation(request, obj_id):
    """
    function used to create onboarding stage.

    Parameters:
    request (HttpRequest): The HTTP request object.
    obj_id : recruitment id

    Returns:
    GET : return onboarding stage creation form template
    POST : return stage save function
    """
    form = OnboardingViewStageForm()
    if request.method == "POST":
        recruitment = Recruitment.objects.get(id=obj_id)
        form = OnboardingViewStageForm(request.POST)
        if form.is_valid():
            stage_obj = form.save()
            stage_obj.employee_id.set(
                Employee.objects.filter(id__in=form.data.getlist("employee_id"))
            )
            return stage_save(form, recruitment, request, obj_id)
    return render(request, "onboarding/stage_form.html", {"form": form, "id": obj_id})


def stage_save(form, recruitment, request, rec_id):
    """
    function used to save onboarding stage.

    Parameters:
    request (HttpRequest): The HTTP request object.
    recruitment : recruitment object
    rec_id : recruitment id

    Returns:
    GET : return onboarding view
    """
    stage = form.save(commit=False)
    stage.recruitment_id = recruitment
    stage.save()
    messages.success(request, _("New stage created successfully.."))
    users = [employee.employee_user_id for employee in stage.employee_id.all()]
    notify.send(
        request.user.employee_get,
        recipient=users,
        verb="You are chosen as onboarding stage manager",
        verb_ar="لقد تم اختيارك كمدير مرحلة التدريب.",
        verb_de="Sie wurden als Onboarding-Stage-Manager ausgewählt.",
        verb_es="Ha sido seleccionado/a como responsable de etapa de incorporación.",
        verb_fr="Vous avez été choisi(e) en tant que responsable de l'étape d'intégration.",
        icon="people-circle",
        redirect=reverse("onboarding-view"),
    )
    response = render(
        request, "onboarding/stage_form.html", {"form": form, "id": rec_id}
    )
    return HttpResponse(
        response.content.decode("utf-8") + "<script>location.reload();</script>"
    )


@login_required
@hx_request_required
@recruitment_manager_can_enter("onboarding.change_onboardingstage")
def stage_update(request, stage_id, recruitment_id):
    """
    function used to update onboarding stage.

    Parameters:
    request (HttpRequest): The HTTP request object.
    stage_id : stage id
    recruitment_id : recruitment id

    Returns:
    GET : return onboarding stage update form template
    POST : return onboarding view
    """
    onboarding_stage = OnboardingStage.objects.get(id=stage_id)
    form = OnboardingViewStageForm(instance=onboarding_stage)
    if request.method == "POST":
        form = OnboardingViewStageForm(request.POST, instance=onboarding_stage)
        if form.is_valid():
            stage = form.save()
            stage.employee_id.set(
                Employee.objects.filter(id__in=form.data.getlist("employee_id"))
            )
            messages.success(request, _("Stage is updated successfully.."))
            users = [employee.employee_user_id for employee in stage.employee_id.all()]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are chosen as onboarding stage manager",
                verb_ar="لقد تم اختيارك كمدير مرحلة التدريب.",
                verb_de="Sie wurden als Onboarding-Stage-Manager ausgewählt.",
                verb_es="Ha sido seleccionado/a como responsable de etapa de incorporación.",
                verb_fr="Vous avez été choisi(e) en tant que responsable de l'étape d'intégration.",
                icon="people-circle",
                redirect=reverse("onboarding-view"),
            )
            if request.META.get("HTTP_HX_REQUEST") == "true":
                return HttpResponse(
                    """
                    <script>
                      (function () {
                        const activeTab = document.querySelector(".oh-tabs__tab--active");
                        const target = activeTab ? activeTab.getAttribute("data-target") : null;
                        if (target && window.htmx) {
                          htmx.ajax("GET", window.location.href, {
                            target: target,
                            swap: "outerHTML",
                            select: target
                          });
                        }
                        $("#reloadMessagesButton").click();
                        $("#genericModal").removeClass("oh-modal--show");
                      })();
                    </script>
                    """
                )
            return HorillaRedirect(request)
    return render(
        request,
        "onboarding/stage_update.html",
        {"form": form, "stage_id": stage_id, "recruitment_id": recruitment_id},
    )


@login_required
@recruitment_manager_can_enter("onboarding.change_onboardingstage")
def update_stage_order(request, pk):
    """
    This method is used to update the stage sequence of the onboarding
    """
    recruitment = Recruitment.find(pk)
    if not recruitment:
        return HorillaRedirect(request, message=_("Recruitment not found."))

    if request.method == "POST":
        try:
            order = json.loads(request.POST.get("order", "[]"))
            for index, stage_id in enumerate(order):
                stage = recruitment.onboarding_stage.get(id=stage_id)
                stage.sequence = index + 1
                stage.save()
            messages.success(request, _("Sequence Updated Successfully"))
            return JsonResponse({"status": "success"})
        except Exception as e:
            messages.error(request, _("Error Updating Sequence.."))
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    stages = recruitment.onboarding_stage.order_by("sequence")

    return render(
        request,
        "cbv/pipeline/onboarding/stage_order.html",
        {
            "stages": stages,
            "recruitment": recruitment,
        },
    )


@login_required
@permission_required("onboarding.delete_onboardingstage")
@recruitment_manager_can_enter("onboarding.delete_onboardingstage")
def stage_delete(request, stage_id):
    """
    function used to delete onboarding stage.

    Parameters:
    request (HttpRequest): The HTTP request object.
    stage_id : stage id

    Returns:
    GET : return onboarding view
    """
    try:
        OnboardingStage.objects.get(id=stage_id).delete()
        messages.success(request, _("The stage deleted successfully..."))

    except OnboardingStage.DoesNotExist:
        messages.error(request, _("Stage not found."))
    except ProtectedError:
        messages.error(request, _("There are candidates in this stage..."))
    return HorillaRedirect(request)


@login_required
@hx_request_required
@stage_manager_can_enter("onboarding.add_onboardingtask")
def task_creation(request):
    """
    function used to create onboarding task.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return onboarding task creation form template
    POST : return onboarding view
    """
    stage_id = request.GET.get("stage_id")
    stage = OnboardingStage.objects.get(id=stage_id)
    form = OnboardingViewTaskForm(initial={"stage_id": stage})

    if request.method == "POST":
        form_data = OnboardingViewTaskForm(request.POST, initial={"stage_id": stage})
        if form_data.is_valid():
            candidates = form_data.cleaned_data["candidates"]
            stage_id = form_data.cleaned_data["stage_id"]
            managers = form_data.cleaned_data["managers"]
            title = form_data.cleaned_data["task_title"]
            is_required = form_data.cleaned_data["is_required"]
            onboarding_task = OnboardingTask(
                task_title=title, stage_id=stage_id, is_required=is_required
            )
            onboarding_task.save()
            onboarding_task.employee_id.set(managers)
            onboarding_task.candidates.set(candidates)
            if candidates:
                for cand in candidates:
                    task = CandidateTask(
                        candidate_id=cand,
                        stage_id=stage_id,
                        onboarding_task_id=onboarding_task,
                    )
                    task.save()
            users = [
                manager.employee_user_id
                for manager in onboarding_task.employee_id.all()
            ]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are chosen as an onboarding task manager",
                verb_ar="لقد تم اختيارك كمدير مهام التدريب.",
                verb_de="Sie wurden als Onboarding-Aufgabenmanager ausgewählt.",
                verb_es="Ha sido seleccionado/a como responsable de tareas de incorporación.",
                verb_fr="Vous avez été choisi(e) en tant que responsable des tâches d'intégration.",
                icon="people-circle",
                redirect=reverse("onboarding-view"),
            )
            messages.success(request, _("New task created successfully..."))
            return HorillaRedirect(request)
    return render(
        request, "onboarding/task_form.html", {"form": form, "stage_id": stage_id}
    )


@login_required
@hx_request_required
@stage_manager_can_enter("onboarding.change_onboardingtask")
def task_update(
    request,
    task_id,
):
    """
    function used to update onboarding task.

    Parameters:
    request (HttpRequest): The HTTP request object.
    task_id : task id

    Returns:
    GET : return onboarding task update form template
    POST : return onboarding view
    """
    onboarding_task = OnboardingTask.objects.get(id=task_id)
    form = OnboardingTaskForm(instance=onboarding_task)
    if request.method == "POST":
        form = OnboardingTaskForm(request.POST, instance=onboarding_task)
        if form.is_valid():
            task = form.save()
            task.employee_id.set(
                Employee.objects.filter(id__in=form.data.getlist("employee_id"))
            )
            for cand_task in onboarding_task.candidatetask_set.all():
                if cand_task.candidate_id not in task.candidates.all():
                    cand_task.delete()
                else:
                    cand_task.stage_id = task.stage_id
            messages.success(request, _("Task updated successfully.."))
            users = [employee.employee_user_id for employee in task.employee_id.all()]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are chosen as an onboarding task manager",
                verb_ar="لقد تم اختيارك كمدير مهام التدريب.",
                verb_de="Sie wurden als Onboarding-Aufgabenmanager ausgewählt.",
                verb_es="Ha sido seleccionado/a como responsable de tareas de incorporación.",
                verb_fr="Vous avez été choisi(e) en tant que responsable des tâches d'intégration.",
                icon="people-circle",
                redirect=reverse("onboarding-view"),
            )
            return HorillaRedirect(request)
    return render(
        request,
        "onboarding/task_update.html",
        {
            "form": form,
            "task_id": task_id,
        },
    )


@login_required
@permission_required("onboarding.delete_onboardingtask")
@stage_manager_can_enter("onboarding.delete_onboardingtask")
def task_delete(request, task_id):
    """
    function used to delete onboarding task.

    Parameters:
    request (HttpRequest): The HTTP request object.
    task_id : task id


    Returns:
    GET : return onboarding view
    """
    try:
        OnboardingTask.objects.get(id=task_id).delete()
        messages.success(request, _("The task deleted successfully..."))
    except OnboardingTask.DoesNotExist:
        messages.error(request, _("Task not found."))
    except ProtectedError:
        messages.error(
            request,
            _(
                "You cannot delete this task because some candidates are associated with it."
            ),
        )
    return redirect(onboarding_view)


@login_required
@permission_required("recruitment.add_candidate")
def candidate_creation(request):
    """
    function used to create hired candidates .

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return candidate creation form template
    POST : return candidate view
    """
    form = OnboardingCandidateForm()
    if request.method == "POST":
        form = OnboardingCandidateForm(request.POST, request.FILES)
        if form.is_valid():
            candidate = form.save()
            candidate.hired = True
            candidate.save()
            messages.success(request, _("New candidate created successfully.."))
            return redirect(candidates_view)
    return render(request, "onboarding/candidate_creation.html", {"form": form})


@login_required
@permission_required("recruitment.change_candidate")
def candidate_update(request, obj_id):
    """
    function used to update hired candidates .

    Parameters:
    request (HttpRequest): The HTTP request object.
    obj_id : recruitment id

    Returns:
    GET : return candidate update form template
    POST : return candidate view
    """
    candidate = Candidate.find(obj_id)
    if not candidate:
        return HorillaRedirect(request, message=_("Candidate not found."))
    form = OnboardingCandidateForm(instance=candidate)
    if request.method == "POST":
        form = OnboardingCandidateForm(request.POST, request.FILES, instance=candidate)
        if form.is_valid():
            form.save()
            messages.success(request, _("Candidate detail is updated successfully.."))
            return redirect(candidates_view)
    return render(request, "onboarding/candidate_update.html", {"form": form})


@login_required
@permission_required("onboarding.delete_onboardingcandidate")
def candidate_delete(request, obj_id):
    """
    function used to delete hired candidates .

    Parameters:
    request (HttpRequest): The HTTP request object.
    obj_id : candidate id

    Returns:
    GET : return candidate view
    """
    try:
        Candidate.objects.get(id=obj_id).delete()
        messages.success(request, _("Candidate deleted successfully.."))
    except Candidate.DoesNotExist:
        messages.error(request, _("Candidate not found."))
    except ProtectedError as e:
        models_verbose_name_sets = set()
        for obj in e.protected_objects:
            models_verbose_name_sets.add(__(obj._meta.verbose_name))
        models_verbose_name_str = (", ").join(models_verbose_name_sets)
        messages.error(
            request,
            _(
                "You cannot delete this candidate. The candidate is included in the {}".format(
                    models_verbose_name_str
                )
            ),
        )
    if request.META.get("HTTP_HX_REQUEST"):
        return HttpResponse(status=204)
    return redirect(reverse("candidates-view"))


@login_required
@hx_request_required
@all_manager_can_enter("onboarding.view_candidatestage")
def candidates_single_view(request, id, **kwargs):
    """
    Candidate individual view for the onboarding candidates
    """
    candidate = Candidate.objects.get(id=id)
    if not CandidateStage.objects.filter(candidate_id=candidate).exists():
        try:
            onboarding_stage = OnboardingStage.objects.filter(
                recruitment_id=candidate.recruitment_id
            ).order_by("sequence")[0]
            CandidateStage(
                candidate_id=candidate, onboarding_stage_id=onboarding_stage
            ).save()
        except Exception:
            messages.error(
                request,
                _("%(recruitment)s has no stage..")
                % {"recruitment": candidate.recruitment_id},
            )
        # OnboardingTask lost its own recruitment_id when tasks moved under
        # stages, so filtering on it raises FieldError for any recruitment that
        # has tasks. Reach the recruitment through the task's stage instead.
        if tasks := OnboardingTask.objects.filter(
            stage_id__recruitment_id=candidate.recruitment_id
        ):
            for task in tasks:
                if not CandidateTask.objects.filter(
                    candidate_id=candidate, onboarding_task_id=task
                ).exists():
                    CandidateTask(
                        candidate_id=candidate,
                        stage_id=task.stage_id,
                        onboarding_task_id=task,
                    ).save()

    recruitment = candidate.recruitment_id
    choices = CandidateTask.choice
    context = {
        "recruitment": recruitment,
        "choices": choices,
        "candidate": candidate,
        "single_view": True,
    }

    requests_ids_json = request.GET.get("requests_ids")
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, id)
        context["requests_ids"] = requests_ids_json
        context["previous"] = previous_id
        context["next"] = next_id
    return render(
        request,
        "onboarding/single_view.html",
        context,
    )


def paginator_qry(qryset, page_number):
    """
    function used to paginate query set
    """
    paginator = Paginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


@login_required
@permission_required(perm="onboarding.view_onboardingcandidate")
def candidates_view(request):
    """
    function used to view hired candidates .

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return candidate view  template
    """
    queryset = Candidate.objects.filter(
        is_active=True,
        hired=True,
        recruitment_id__closed=False,
    )
    candidate_filter_obj = CandidateFilter(request.GET, queryset)
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    page_obj = paginator_qry(candidate_filter_obj.qs, page_number)
    mail_templates = HorillaMailTemplate.objects.all()
    data_dict = parse_qs(previous_data)
    get_key_instances(Candidate, data_dict)
    return render(
        request,
        "onboarding/candidates_view.html",
        {
            "candidates": page_obj,
            "form": candidate_filter_obj.form,
            "pd": previous_data,
            "gp_fields": CandidateReGroup.fields,
            "mail_templates": mail_templates,
            "hired_candidates": queryset,
            "filter_dict": data_dict,
        },
    )


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_candidate")
def hired_candidate_view(request):
    previous_data = request.GET.urlencode()
    candidates = Candidate.objects.filter(
        hired=True,
        recruitment_id__closed=False,
    )
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
@hx_request_required
@permission_required(perm="onboarding.view_onboardingcandidate")
def candidate_filter(request):
    """
    function used to filter hired candidates .

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return candidate view template
    """
    queryset = Candidate.objects.filter(
        is_active=True,
        hired=True,
        recruitment_id__closed=False,
    )
    candidates = CandidateFilter(request.GET, queryset).qs
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    data_dict = parse_qs(previous_data)
    get_key_instances(Candidate, data_dict)
    candidates = sortby(request, candidates, "orderby")
    field = request.GET.get("field")
    template = "onboarding/candidates.html"
    if field != "" and field is not None:
        template = "onboarding/group_by.html"
        candidates = general_group_by(
            candidates, field, request.GET.get("page"), "page"
        )
    page_obj = paginator_qry(candidates, page_number)
    return render(
        request,
        template,
        {"candidates": page_obj, "pd": previous_data, "filter_dict": data_dict},
    )


# @login_required
# @all_manager_can_enter("recruitment.view_recruitment")
# def email_send(request):
#     """
#     function used to send onboarding portal for hired candidates .

#     Parameters:
#     request (HttpRequest): The HTTP request object.

#     Returns:
#     GET : return json response
#     """
#     host = request.get_host()
#     protocol = "https" if request.is_secure() else "http"
#     candidates = request.POST.getlist("ids")
#     other_attachments = request.FILES.getlist("other_attachments")
#     template_attachment_ids = request.POST.getlist("template_attachment_ids")
#     email_backend = ConfiguredEmailBackend()
#     if not candidates:
#         messages.info(request, _("Please choose candidates"))
#         return HttpResponse("<script>window.location.reload()</script>")

#     bodys = list(
#         HorillaMailTemplate.objects.filter(id__in=template_attachment_ids).values_list(
#             "body", flat=True
#         )
#     )

#     attachments_other = []
#     for file in other_attachments:
#         attachments_other.append((file.name, file.read(), file.content_type))
#         file.close()
#     for cand_id in candidates:
#         attachments = list(set(attachments_other) | set([]))
#         candidate = Candidate.objects.get(id=cand_id)
#         if not request.GET.get("no_portal"):
#             if candidate.converted_employee_id:
#                 messages.info(
#                     request, _(f"{candidate} has already been converted to employee.")
#                 )
#                 continue
#             for html in bodys:
#                 # due to not having solid template we first need to pass the context
#                 template_bdy = template.Template(html)
#                 context = template.Context(
#                     {"instance": candidate, "self": request.user.employee_get}
#                 )
#                 render_bdy = template_bdy.render(context)
#                 attachments.append(
#                     (
#                         "Document",
#                         generate_pdf(
#                             render_bdy, {}, path=False, title="Document"
#                         ).content,
#                         "application/pdf",
#                     )
#                 )
#             token = secrets.token_hex(15)
#             existing_portal = OnboardingPortal.objects.filter(candidate_id=candidate)
#             if existing_portal.exists():
#                 new_portal = existing_portal.first()
#                 new_portal.token = token
#                 new_portal.used = False
#                 new_portal.count = 0
#                 new_portal.profile = None
#                 new_portal.save()
#             else:
#                 OnboardingPortal(candidate_id=candidate, token=token).save()
#             html_message = render_to_string(
#                 "onboarding/mail_templates/default.html",
#                 {
#                     "portal": f"{protocol}://{host}/onboarding/user-creation/{token}",
#                     "instance": candidate,
#                     "host": host,
#                     "protocol": protocol,
#                 },
#                 request=request,
#             )
#             email = EmailMessage(
#                 subject=f"Hello {candidate.name}, Congratulations on your selection!",
#                 body=html_message,
#                 to=[candidate.email],
#             )
#             email.content_subtype = "html"
#             email.attachments = attachments
#             try:
#                 email.send()
#                 # to check ajax or not
#                 messages.success(request, _("Portal link sent to the candidate"))
#             except Exception as e:
#                 logger.error(e)
#                 messages.error(request, _("Mail not send to %(candidate_name)s") % {"candidate_name": candidate.name})
#             candidate.start_onboard = True
#             candidate.save()
#         try:
#             onboarding_candidate = CandidateStage()
#             onboarding_candidate.onboarding_stage_id = (
#                 candidate.recruitment_id.onboarding_stage.first()
#             )
#             onboarding_candidate.candidate_id = candidate
#             onboarding_candidate.save()
#             messages.success(request, _("Candidate Added to Onboarding Stage"))
#         except Exception as e:
#             logger.error(e)

#     return HttpResponse("<script>window.location.reload()</script>")


import logging
from email.mime.image import MIMEImage

from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


@login_required
@all_manager_can_enter("recruitment.view_recruitment")
def email_send(request):
    host = request.get_host()
    protocol = "https" if request.is_secure() else "http"
    no_portal = request.GET.get("no_portal") == "True"

    candidates = request.POST.getlist("ids")
    other_attachments = request.FILES.getlist("other_attachments")
    template_attachment_ids = request.POST.getlist("template_attachment_ids")

    email_backend = ConfiguredEmailBackend()
    display_email_name = email_backend.dynamic_from_email_with_display_name

    if not candidates:
        messages.info(request, _("Please choose candidates"))
        return HorillaRedirect(request)

    # Fetch PDF templates
    bodys = list(
        HorillaMailTemplate.objects.filter(id__in=template_attachment_ids).values_list(
            "body", flat=True
        )
    )

    # Collect uploaded attachments
    attachments_other = []
    for file in other_attachments:
        attachments_other.append((file.name, file.read(), file.content_type))
        file.close()

    for cand_id in candidates:
        candidate = Candidate.objects.get(id=cand_id)
        attachments = list(attachments_other)

        # Prevent duplicate onboarding
        if candidate.converted_employee_id:
            messages.info(
                request,
                _("%(candidate)s has already been converted to employee.")
                % {"candidate": candidate},
            )
            continue

        # Generate PDFs
        for html in bodys:
            template_bdy = template.Template(sanitize_mail_template_body(html))
            context = template.Context(
                {"instance": candidate, "self": request.user.employee_get}
            )
            render_bdy = template_bdy.render(context)

            attachments.append(
                (
                    "Document.pdf",
                    generate_pdf(render_bdy, {}, path=False, title="Document").content,
                    "application/pdf",
                )
            )

        # Create / reset portal
        token = secrets.token_hex(15)
        portal, _createdcreated = OnboardingPortal.objects.get_or_create(
            candidate_id=candidate
        )
        portal.token = token
        portal.used = False
        portal.count = 0
        portal.profile = None
        portal.save()

        # Render email HTML
        html_message = render_to_string(
            "onboarding/mail_templates/default.html",
            {
                "portal": f"{protocol}://{host}/onboarding/user-creation/{token}",
                "instance": candidate,
                "host": host,
                "protocol": protocol,
                "use_cid_logo": True,
            },
            request=request,
        )

        # ✅ Use EmailMultiAlternatives (IMPORTANT)
        email = EmailMultiAlternatives(
            subject=f"Hello {candidate.name}, Congratulations on your selection!",
            body=html_message,
            from_email=display_email_name,
            to=[candidate.email],
            reply_to=[display_email_name],
        )

        email.attach_alternative(html_message, "text/html")

        # Attach files
        for attachment in attachments:
            email.attach(*attachment)

        # ✅ Attach company logo INLINE
        try:
            company = candidate.recruitment_id.company_id
            if company and company.icon and os.path.exists(company.icon.path):
                image_path = company.icon.path
            else:
                image_path = finders.find("images/ui/horilla-sticker-round.png")

            if image_path:
                with open(image_path, "rb") as f:
                    logo = MIMEImage(f.read())
                    logo.add_header("Content-ID", "<company_logo>")
                    logo.add_header(
                        "Content-Disposition",
                        "inline",
                        filename=os.path.basename(image_path),
                    )
                    email.attach(logo)
        except Exception as e:
            logger.error(f"Company logo attach failed: {e}")

        # Send mail, unless the caller only wants onboarding started. The
        # "Start Onboarding" action posts ?no_portal=True for exactly this.
        if no_portal:
            messages.success(
                request,
                _("%(candidate)s added to onboarding") % {"candidate": candidate.name},
            )
        else:
            try:
                email.send()
                messages.success(request, _("Portal link sent to the candidate"))
            except Exception as e:
                logger.error(e)
                messages.error(
                    request,
                    _("Mail not sent to %(candidate_name)s")
                    % {"candidate_name": candidate.name},
                )
                # continue

        # Mark onboarding started without triggering Candidate.save() validation
        # (which can fail with "Choose valid choice" on job_position_id when the
        # candidate's job position has been removed from recruitment.open_positions).
        Candidate.objects.filter(pk=candidate.pk).update(start_onboard=True)
        candidate.start_onboard = True

        # ✅ SAFE onboarding stage insert
        try:
            stage = candidate.recruitment_id.onboarding_stage.first()
            CandidateStage.objects.get_or_create(
                candidate_id=candidate,
                defaults={"onboarding_stage_id": stage},
            )
        except Exception as e:
            logger.error(e)

    return HorillaRedirect(request)


def onboarding_query_grouper(request, queryset):
    """
    This method is used to make group of the onboarding records
    """
    groups = []
    for rec in queryset:
        employees = []
        stages = OnboardingStageFilter(
            request.GET, queryset=rec.onboarding_stage.all()
        ).qs.order_by("sequence")
        all_stages_grouper = []
        data = {"recruitment": rec, "stages": []}
        for stage in stages:
            all_stages_grouper.append({"grouper": stage, "list": []})
            stage_candidates = OnboardingCandidateFilter(
                request.GET,
                stage.candidate.filter(
                    candidate_id__is_active=True,
                ),
            ).qs.order_by("sequence")

            page_name = "page" + stage.stage_title + str(rec.id)
            grouper = group_by_queryset(
                stage_candidates,
                "onboarding_stage_id",
                request.GET.get(page_name),
                page_name,
            ).object_list
            data["stages"] = data["stages"] + grouper
            employees = employees + [
                employee.candidate_id.id for employee in stage.candidate.all()
            ]
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
            "employee_ids": employees,
        }
        groups.append(data)
    return groups


@login_required
@all_manager_can_enter("onboarding.view_onboardingstage")
def onboarding_view(request):
    """
    function used to view onboarding main view.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return onboarding view template
    """
    filter_obj = RecruitmentFilter(request.GET)
    # is active filteration not providing on pipeline
    recruitments = filter_obj.qs
    if not request.user.has_perm("onboarding.view_onboardingstage"):
        recruitments = recruitments.filter(
            is_active=True, recruitment_managers__in=[request.user.employee_get]
        ) | recruitments.filter(
            onboarding_stage__employee_id__in=[request.user.employee_get]
        )
    employee_tasks = request.user.employee_get.onboarding_task.all()
    for task in employee_tasks:
        if task.stage_id and task.stage_id.recruitment_id not in recruitments:
            recruitments = recruitments | filter_obj.qs.filter(
                id=task.stage_id.recruitment_id.id
            )
    recruitments = recruitments.filter(is_active=True).distinct()
    status = request.GET.get("closed")
    if not status:
        recruitments = recruitments.filter(closed=False)

    onboarding_stages = OnboardingStage.objects.all()
    choices = CandidateTask.choice
    previous_data = request.GET.urlencode()
    paginator = Paginator(recruitments.order_by("id"), 4)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    groups = onboarding_query_grouper(request, page_obj)
    for item in groups:
        setattr(item["recruitment"], "stages", item["stages"])
        setattr(item["recruitment"], "employee_ids", item["employee_ids"])
    filter_dict = parse_qs(request.GET.urlencode())
    for key, val in filter_dict.copy().items():
        if val[0] == "unknown" or key == "view":
            del filter_dict[key]
    return render(
        request,
        "onboarding/onboarding_view.html",
        {
            "recruitments": page_obj,
            "rec_filter_obj": filter_obj,
            "onboarding_stages": onboarding_stages,
            "choices": choices,
            "filter_dict": filter_dict,
            "status": status,
            "pd": previous_data,
        },
    )


@login_required
@all_manager_can_enter("onboarding.view_onboardingstage")
def kanban_view(request):
    # filter_obj = RecruitmentFilter(request.GET)
    # # is active filteration not providing on pipeline
    # recruitments = filter_obj.qs.filter(is_active=True)
    filter_obj = RecruitmentFilter(request.GET)
    # is active filteration not providing on pipeline
    recruitments = filter_obj.qs
    if not request.user.has_perm("onboarding.view_onboardingstage"):
        recruitments = recruitments.filter(
            is_active=True, recruitment_managers__in=[request.user.employee_get]
        ) | recruitments.filter(
            onboarding_stage__employee_id__in=[request.user.employee_get]
        )
    employee_tasks = request.user.employee_get.onboarding_task.all()
    for task in employee_tasks:
        if task.stage_id and task.stage_id.recruitment_id not in recruitments:
            recruitments = recruitments | filter_obj.qs.filter(
                id=task.stage_id.recruitment_id.id
            )
    recruitments = recruitments.filter(is_active=True).distinct()

    status = request.GET.get("closed")
    if not status:
        recruitments = recruitments.filter(closed=False)

    onboarding_stages = OnboardingStage.objects.all()
    choices = CandidateTask.choice
    stage_form = OnboardingViewStageForm()

    previous_data = request.GET.urlencode()

    filter_obj = RecruitmentFilter(request.GET, queryset=recruitments)
    paginator = Paginator(recruitments, 4)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    groups = onboarding_query_grouper(request, page_obj)

    for item in groups:
        setattr(item["recruitment"], "stages", item["stages"])
    filter_dict = parse_qs(request.GET.urlencode())
    for key, val in filter_dict.copy().items():
        if val[0] == "unknown" or key == "view":
            del filter_dict[key]

    return render(
        request,
        "onboarding/kanban/kanban.html",
        {
            "recruitments": page_obj,
            "rec_filter_obj": filter_obj,
            "onboarding_stages": onboarding_stages,
            "choices": choices,
            "filter_dict": filter_dict,
            "stage_form": stage_form,
            "status": status,
            "pd": previous_data,
            "card": True,
        },
    )


portal_user = {}


def user_creation(request, token):
    """
    function used to create user account in onboarding portal.

    Parameters:
    request (HttpRequest): The HTTP request object.
    token : random generated onboarding portal token

    Returns:
    GET : return user creation form template
    POST : return user_save function
    """
    try:
        onboarding_portal = OnboardingPortal.objects.get(token=token)
        if not onboarding_portal or onboarding_portal.used is True:
            return render(request, "404.html")
        if onboarding_portal.count == 3:
            return redirect("employee-bank-details", token)
        candidate = onboarding_portal.candidate_id
        user = HorillaUser.objects.filter(username=candidate.email).first()
        form = UserCreationForm(instance=user)
        try:
            if request.method == "POST":
                form = UserCreationForm(request.POST, instance=user)
                if form.is_valid():
                    return user_save(form, onboarding_portal, request, token)
        except Exception:
            messages.error(request, _("User with email-id already exists.."))
        return render(
            request,
            "onboarding/user_creation.html",
            {
                "form": form,
                "company": onboarding_portal.candidate_id.recruitment_id.company_id,
            },
        )
    except Exception as error:
        return HttpResponse(error)


def user_save(form, onboarding_portal, request, token):
    """
    function used to save user.

    Parameters:
    request (HttpRequest): The HTTP request object.
    onboarding_portal : onboarding portal object
    token : random generated onboarding portal token

    Returns:
    GET : return profile view
    """
    user = form.save(commit=False)
    user.username = onboarding_portal.candidate_id.email
    session_key = request.session.session_key
    portal_user[session_key] = user
    onboarding_portal.count = 1
    onboarding_portal.save()
    messages.success(request, _("Account created successfully.."))
    return redirect("profile-view", token)


def profile_view(request, token):
    """
    function used to view user profile.

    Parameters:
    request (HttpRequest): The HTTP request object.
    token : random generated onboarding portal token

    Returns:
    GET : return user profile template
    POST : update profile image of the user
    """
    onboarding_portal = OnboardingPortal.objects.filter(token=token).first()
    if onboarding_portal is None:
        return render(request, "404.html")
    candidate = onboarding_portal.candidate_id
    if request.method == "POST":
        profile = request.FILES.get("profile")
        if profile is not None:
            candidate.profile = profile
            candidate.save()
            onboarding_portal.profile = profile
            onboarding_portal.count = 2
            onboarding_portal.save()
            messages.success(request, _("Profile picture updated successfully.."))
    return render(
        request,
        "onboarding/profile_view.html",
        {
            "candidate": candidate,
            "profile": onboarding_portal.profile,
            "token": token,
            "company": candidate.recruitment_id.company_id,
        },
    )


def employee_creation(request, token):
    """
    function used to create employee.

    Parameters:
    request (HttpRequest): The HTTP request object.
    token : random generated onboarding portal token.

    Returns:
    GET : return employee creation profile template.
    POST : return employee bank detail creation template.
    """
    onboarding_portal = OnboardingPortal.objects.filter(token=token).first()
    if onboarding_portal is None:
        return render(request, "404.html")
    candidate = onboarding_portal.candidate_id
    initial = {
        "employee_first_name": candidate.name,
        "phone": candidate.mobile,
        "address": candidate.address,
        "dob": candidate.dob,
    }
    session_key = request.session.session_key
    user = portal_user.get(session_key)
    if user is None:
        # Fallback for direct/opened links where in-memory portal state is absent.
        user = HorillaUser.objects.filter(username=candidate.email).first()
    elif not getattr(user, "pk", None):
        # Related filters require a saved instance; resolve persisted user by email/username.
        user = HorillaUser.objects.filter(username=candidate.email).first() or user

    if user is None:
        messages.error(
            request,
            _("Please create your account first before continuing employee creation."),
        )
        return redirect("user-creation", token)

    user_email = getattr(user, "email", None) or candidate.email
    if Employee.objects.filter(email=user_email).exists():
        messages.success(request, _("Employee with email id already exists."))
        return redirect("login/")
    employee_qs = (
        Employee.objects.filter(employee_user_id=user)
        if getattr(user, "pk", None)
        else Employee.objects.none()
    )
    if employee_qs.first() is not None:
        employee = employee_qs.first()
        if employee.employee_bank_details:
            messages.success(request, _("Employee already exists.."))
            return redirect("login/")
        initial = employee.__dict__

    form = EmployeeCreationForm(
        initial=initial,
    )
    # form.errors.clear()
    if request.method == "POST":
        instance = employee_qs.first() if getattr(user, "pk", None) else None
        form = EmployeeCreationForm(
            request.POST,
            instance=instance,
        )
        if form.is_valid():
            if user is None:
                messages.error(
                    request,
                    _(
                        "User account was not found. Please complete account creation and try again."
                    ),
                )
                return redirect("user-creation", token)
            if not getattr(user, "pk", None):
                user.save()
            login(request, user)
            employee_personal_info = form.save(commit=False)
            employee_personal_info.employee_user_id = user
            employee_personal_info.email = candidate.email
            if candidate.profile and candidate.profile.storage.exists(
                candidate.profile.name
            ):  # 896
                filename = os.path.basename(candidate.profile.name)
                employee_personal_info.employee_profile.save(
                    filename, ContentFile(candidate.profile.read()), save=False
                )

            employee_personal_info.is_from_onboarding = True
            employee_personal_info.save()

            EmployeeWorkInformation.objects.update_or_create(
                employee_id=employee_personal_info,
                defaults={
                    "department_id": candidate.job_position_id.department_id,
                    "job_position_id": candidate.job_position_id,
                    "company_id": candidate.recruitment_id.company_id,
                    "date_joining": candidate.joining_date,
                    "email": candidate.email,
                },
            )

            Document.objects.bulk_create(
                [
                    Document(
                        title=doc.title,
                        employee_id=employee_personal_info,
                        document=doc.document,
                        status=doc.status,
                        reject_reason=doc.reject_reason,
                    )
                    for doc in candidate.candidatedocument_set.all()
                ]
            )

            onboarding_portal.count = 3
            onboarding_portal.save()
            messages.success(
                request, _("Employee personal details created successfully..")
            )
            return redirect("employee-bank-details", token)
    return render(
        request,
        "onboarding/employee_creation.html",
        {"form": form, "employee": candidate.recruitment_id.company_id},
    )


def employee_bank_details(request, token):
    """
    function used to create employee bank details creation.

    Parameters:
    request (HttpRequest): The HTTP request object.
    token : random generated onboarding portal token

    Returns:
    GET : return bank details creation template
    POST : return employee_bank_details_save function
    """
    onboarding_portal = OnboardingPortal.objects.filter(token=token).first()
    if not onboarding_portal:
        return HorillaRedirect(request, message=_("Onboarding portal not found."))

    user = HorillaUser.objects.filter(
        username=onboarding_portal.candidate_id.email
    ).first()
    employee = Employee.objects.filter(employee_user_id=user).first()
    bank_info = EmployeeBankDetails.objects.filter(employee_id=employee).first()
    form = BankDetailsCreationForm(instance=bank_info)
    if request.method == "POST":
        form = BankDetailsCreationForm(
            request.POST,
            instance=bank_info,
        )
        if form.is_valid():
            return employee_bank_details_save(form, request, onboarding_portal)
        return redirect(welcome_aboard)
    return render(
        request,
        "onboarding/employee_bank_details.html",
        {
            "form": form,
            "company": onboarding_portal.candidate_id.recruitment_id.company_id,
        },
    )


def employee_bank_details_save(form, request, onboarding_portal):
    """
    function used to save employee bank details.

    Parameters:
    request (HttpRequest): The HTTP request object.
    form : Form object.
    onboarding_portal : Onboarding portal object.

    Returns:
    GET : return welcome onboard view
    """
    employee_bank_detail = form.save(commit=False)
    employee = Employee.objects.get(employee_user_id=request.user)
    employee_bank_detail.employee_id = employee
    candidate = onboarding_portal.candidate_id
    candidate.converted_employee_id = employee
    candidate.save()
    employee_bank_detail.save()
    onboarding_portal.count = 4
    onboarding_portal.used = True
    onboarding_portal.save()
    messages.success(request, _("Employee bank details created successfully.."))
    return redirect(welcome_aboard)


@login_required
def welcome_aboard(request):
    """
    function used to view welcome aboard.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return welcome onboard view
    """
    return render(request, "onboarding/welcome_aboard.html")


@login_required
@require_http_methods(["POST"])
@all_manager_can_enter("onboarding.change_candidatetask")
def candidate_task_update(request, taskId):
    """
    function used to update candidate task.

    Parameters:
    request (HttpRequest): The HTTP request object.
    obj_id : candidate task id

    Returns:
    POST : return candidate task template
    """
    status = request.POST.get("status")
    if request.POST.get("single_view"):
        candidate_task = CandidateTask.objects.get(id=taskId)
    else:
        canId = request.POST.get("candId")
        onboarding_task = OnboardingTask.objects.get(id=taskId)
        candidate = Candidate.objects.get(id=canId)
        candidate_task = CandidateTask.objects.filter(
            candidate_id=candidate, onboarding_task_id=onboarding_task
        ).first()
    candidate_task.status = status
    candidate_task.save()
    users = [
        employee.employee_user_id
        for employee in candidate_task.onboarding_task_id.employee_id.all()
    ]
    notify.send(
        request.user.employee_get,
        recipient=users,
        verb=f"The task {candidate_task.onboarding_task_id} of\
            {candidate_task.candidate_id} was updated to {candidate_task.status}.",
        verb_ar=f"تم تحديث المهمة {candidate_task.onboarding_task_id} للمرشح {candidate_task.candidate_id} إلى {candidate_task.status}.",
        verb_de=f"Die Aufgabe {candidate_task.onboarding_task_id} des Kandidaten {candidate_task.candidate_id} wurde auf {candidate_task.status} aktualisiert.",
        verb_es=f"La tarea {candidate_task.onboarding_task_id} del candidato {candidate_task.candidate_id} se ha actualizado a {candidate_task.status}.",
        verb_fr=f"La tâche {candidate_task.onboarding_task_id} du candidat {candidate_task.candidate_id} a été mise à jour à {candidate_task.status}.",
        icon="people-circle",
        redirect=reverse("onboarding-view"),
    )
    return JsonResponse(
        {"message": _("Candidate onboarding task updated"), "type": "success"}
    )


@login_required
def get_status(request, task_id):
    """
    htmx function that return the status of candidate task

    Parameters:
    request (HttpRequest): The HTTP request object.
    task_id : Onboarding task id

    Returns:
    POST : return candidate task template
    """
    cand_id = request.GET.get("cand_id")
    cand_stage = request.GET.get("cand_stage")
    if not cand_id or not cand_stage:
        return HorillaRedirect(request, message=_("Missing required parameters."))
    cand_stage_obj = CandidateStage.find(cand_stage)
    onboarding_task = OnboardingTask.find(task_id)
    candidate = Candidate.find(cand_id)
    candidate_task = CandidateTask.objects.filter(
        candidate_id=candidate, onboarding_task_id=onboarding_task
    ).first()
    if not cand_stage_obj or not onboarding_task or not candidate or not candidate_task:
        return HorillaRedirect(request, message=_("Object not found."))
    status = candidate_task.status

    return render(
        request,
        "onboarding/candidate_task.html",
        {
            "status": status,
            "task": onboarding_task,
            "candidate": cand_stage_obj,
            "second_load": True,
            "choices": CandidateTask.choice,
        },
    )


@login_required
@all_manager_can_enter("onboarding.change_candidatetask")
def assign_task(request, task_id):
    """
    htmx function that used to assign a onboarding task to candidate

    Parameters:
    request (HttpRequest): The HTTP request object.
    task_id : Onboarding task id

    Returns:
    POST : return candidate task template
    """
    stage_id = request.GET.get("stage_id")
    cand_id = request.GET.get("cand_id")
    cand_stage = request.GET.get("cand_stage")
    if not stage_id or not cand_id or not cand_stage:
        return HorillaRedirect(request, message=_("Missing required parameters."))
    cand_stage_obj = CandidateStage.find(cand_stage)
    onboarding_task = OnboardingTask.find(task_id)
    candidate = Candidate.find(cand_id)
    onboarding_stage = OnboardingStage.find(stage_id)
    if (
        not cand_stage_obj
        or not onboarding_task
        or not candidate
        or not onboarding_stage
    ):
        return HorillaRedirect(request, message=_("Object not found."))

    cand_task, created = CandidateTask.objects.get_or_create(
        candidate_id=candidate,
        stage_id=onboarding_stage,
        onboarding_task_id=onboarding_task,
    )
    cand_task.save()
    onboarding_task.candidates.add(candidate)
    return render(
        request,
        "onboarding/candidate_task.html",
        {
            "status": cand_task.status,
            "task": onboarding_task,
            "candidate": cand_stage_obj,
            "second_load": True,
            "choices": CandidateTask.choice,
        },
    )


@login_required
@require_http_methods(["POST"])
@stage_manager_can_enter("onboarding.change_candidatestage")
def candidate_stage_update(request, candidate_id, recruitment_id):
    """
    function used to update candidate stage.

    Parameters:
    request (HttpRequest): The HTTP request object.
    candidate_id : Candidate id
    recruitment_id : Recruitment id

    Returns:
    POST : return candidate task template
    """
    stage_id = request.POST.get("stage")
    recruitments = Recruitment.objects.filter(id=recruitment_id)
    stage = OnboardingStage.objects.get(id=stage_id)
    candidate = Candidate.objects.get(id=candidate_id)
    candidate_stage = CandidateStage.objects.get(candidate_id=candidate)
    candidate_stage.onboarding_stage_id = stage
    candidate_stage.save()
    onboarding_stages = OnboardingStage.objects.all()
    choices = CandidateTask.choice
    users = [
        employee.employee_user_id
        for employee in candidate_stage.onboarding_stage_id.employee_id.all()
    ]
    if request.POST.get("is_ajax") is None:
        notify.send(
            request.user.employee_get,
            recipient=users,
            verb=f"The stage of {candidate_stage.candidate_id} \
                was updated to {candidate_stage.onboarding_stage_id}.",
            verb_ar=f"تم تحديث مرحلة المرشح {candidate_stage.candidate_id} إلى {candidate_stage.onboarding_stage_id}.",
            verb_de=f"Die Phase des Kandidaten {candidate_stage.candidate_id} wurde auf {candidate_stage.onboarding_stage_id} aktualisiert.",
            verb_es=f"La etapa del candidato {candidate_stage.candidate_id} se ha actualizado a {candidate_stage.onboarding_stage_id}.",
            verb_fr=f"L'étape du candidat {candidate_stage.candidate_id} a été mise à jour à {candidate_stage.onboarding_stage_id}.",
            icon="people-circle",
            redirect=reverse("onboarding-view"),
        )
    groups = onboarding_query_grouper(request, recruitments)
    for item in groups:
        setattr(item["recruitment"], "stages", item["stages"])
        return render(
            request,
            "onboarding/onboarding_table.html",
            {
                "recruitment": groups[0]["recruitment"],
                "onboarding_stages": onboarding_stages,
                "choices": choices,
            },
        )
    return JsonResponse(
        {"message": _("Candidate onboarding stage updated"), "type": "success"}
    )


@login_required
@require_http_methods(["POST"])
@stage_manager_can_enter("onboarding.change_candidatestage")
def candidate_stage_bulk_update(request):
    candiate_ids = request.POST["ids"]
    recrutment_id = request.POST["recruitment"]
    candidate_id_list = json.loads(candiate_ids)
    stage = request.POST["stage"]
    onboarding_stages = OnboardingStage.objects.all()
    recruitments = Recruitment.objects.filter(id=int(recrutment_id))

    choices = CandidateTask.choice

    CandidateStage.objects.filter(candidate_id__id__in=candidate_id_list).update(
        onboarding_stage_id=stage
    )
    type = "info"
    message = "No candidates selected"
    if candidate_id_list:
        type = "success"
        message = "Candidate stage updated successfully"
    groups = onboarding_query_grouper(request, recruitments)
    for item in groups:
        setattr(item["recruitment"], "stages", item["stages"])
    response = render(
        request,
        "onboarding/onboarding_table.html",
        {
            "recruitment": groups[0]["recruitment"],
            "onboarding_stages": onboarding_stages,
            "choices": choices,
        },
    )

    return HttpResponse(
        response.content.decode("utf-8")
        + f'<div><div class="oh-alert-container"><div class="oh-alert oh-alert--animated oh-alert--{type}">{message}</div> </div></div>'
    )


@login_required
@require_http_methods(["POST"])
@all_manager_can_enter("onboarding.change_candidatetask")
def candidate_task_bulk_update(request):
    candiate_ids = request.POST["ids"]
    candidate_id_list = json.loads(candiate_ids)
    task = request.POST["task"]
    status = request.POST["status"]

    count = CandidateTask.objects.filter(
        candidate_id__id__in=candidate_id_list, onboarding_task_id=task
    ).update(status=status)
    # messages.success(request, _("%(count)s candidate's task status updated successfully") % {"count": count})

    return JsonResponse(
        {"message": _("Candidate onboarding stage updated"), "type": "success"}
    )


@login_required
def onboard_candidate_chart(request):
    """
    function used to show onboard started candidates in recruitments.

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
        labels.append(recruitment.title)
        data.append(recruitment.candidate.filter(start_onboard=True).count())
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
@permission_required("candidate.change_candidate")
@require_POST
def update_joining(request):
    """
    Ajax method to update joining date of candidate
    """
    cand_id = request.POST.get("candId")
    date_value = request.POST.get("date")

    if not cand_id:
        messages.error(request, _("Missing candidate ID."))
        return JsonResponse({"type": "danger"}, status=400)

    if date_value is None:
        messages.error(request, _("Missing date of joining."))
        return JsonResponse({"type": "danger"}, status=400)

    if date_value == "":
        date_value = None

    candidate_obj = Candidate.find(cand_id)
    if not candidate_obj:
        messages.error(request, _("Candidate not found"))
        return JsonResponse({"type": "danger"}, status=400)

    candidate_obj.joining_date = date_value
    candidate_obj.save()
    messages.success(
        request,
        _("{candidate}'s Date of joining updated successfully").format(
            candidate=candidate_obj.name
        ),
    )
    return JsonResponse({"type": "success"})


@login_required
@permission_required(perm="recruitment.view_candidate")
def view_dashboard(request):
    recruitment = Recruitment.objects.all().values_list("title", flat=True)
    candidates = Candidate.objects.all()
    hired = candidates.filter(start_onboard=True)
    onboard_candidates = Candidate.objects.filter(start_onboard=True)
    job_positions = onboard_candidates.values_list(
        "job_position_id__job_position", flat=True
    )

    context = {
        "recruitment": list(recruitment),
        "candidates": candidates,
        "hired": hired,
        "onboard_candidates": onboard_candidates,
        "job_positions": list(set(job_positions)),
    }
    return render(request, "onboarding/dashboard.html", context=context)


@login_required
@hx_request_required
@permission_required(perm="recruitment.view_candidate")
def dashboard_stage_chart(request):
    recruitment = request.GET.get("recruitment")
    labels = OnboardingStage.objects.filter(
        recruitment_id__title=recruitment
    ).values_list("stage_title", flat=True)
    labels = list(labels)
    candidate_counts = []
    border_color = []
    background_color = []
    for label in labels:
        red = random.randint(0, 255)
        green = random.randint(0, 255)
        blue = random.randint(0, 255)
        background_color.append(f"rgba({red}, {green}, {blue}, 0.3")
        border_color.append(f"rgb({red}, {green}, {blue})")
        count = CandidateStage.objects.filter(
            onboarding_stage_id__stage_title=label,
            onboarding_stage_id__recruitment_id__title=recruitment,
        ).count()
        candidate_counts.append(count)

    response = {
        "labels": labels,
        "data": candidate_counts,
        "recruitment": recruitment,
        "background_color": background_color,
        "border_color": border_color,
        "message": _("No candidates started onboarding...."),
    }
    return JsonResponse(response)


@login_required
@stage_manager_can_enter("recruitment.change_candidate")
def candidate_sequence_update(request):
    """
    This method is used to update the sequence of candidate
    """
    seq_data = request.POST.get("sequenceData")
    if not seq_data:
        messages.error(request, _("Missing required parameter: sequenceData."))
        return JsonResponse(
            {"error": "Missing required parameter: sequenceData"}, status=400
        )
    sequence_data = json.loads(request.POST.get("sequenceData"))
    updated = False
    for cand_id, seq in sequence_data.items():
        cand = CandidateStage.find(cand_id)
        if not cand:
            continue
        if cand.sequence != seq:
            cand.sequence = seq
            cand.save()
            updated = True
    if updated:
        return JsonResponse(
            {"message": _("Candidate sequence updated"), "type": "info"}
        )
    return JsonResponse({"type": "fail"})


@login_required
@stage_manager_can_enter("recruitment.change_stage")
def stage_sequence_update(request):
    """
    This method is used to update the sequence of the stages
    """
    seq_data = request.POST.get("sequenceData")
    if not seq_data:
        messages.error(request, _("Missing required parameter: sequenceData."))
        return JsonResponse(
            {"error": "Missing required parameter: sequenceData"}, status=400
        )
    sequence_data = json.loads(request.POST.get("sequenceData"))
    updated = False

    for stage_id, seq in sequence_data.items():
        stage = OnboardingStage.find(stage_id)
        if not stage:
            continue
        if stage.sequence != seq:
            stage.sequence = seq
            stage.save()
            updated = True

    if updated:
        return JsonResponse({"type": "success", "message": _("Stage sequence updated")})
    return JsonResponse({"type": "fail"})


@login_required
@require_http_methods(["POST"])
@hx_request_required
def stage_name_update(request, stage_id):
    """
    This method is used to update the name of recruitment stage
    """
    stage_obj = OnboardingStage.objects.get(id=stage_id)
    stage_obj.stage_title = request.POST["stage"]
    stage_obj.save()
    message = _("The stage title has been updated successfully")
    return HttpResponse(
        f'<div class="oh-alert-container"><div class="oh-alert oh-alert--animated oh-alert--success">{message}</div></div>'
    )


@login_required
@hx_request_required
@stage_manager_can_enter("recruitment.change_candidate")
def onboarding_send_mail(request, candidate_id):
    """
    This method is used to send mail to the candidate from onboarding view
    """
    candidate = Candidate.objects.get(id=candidate_id)
    candidate_mail = candidate.email
    response = render(
        request, "onboarding/send_mail_form.html", {"candidate": candidate}
    )
    email_backend = ConfiguredEmailBackend()
    display_email_name = email_backend.dynamic_from_email_with_display_name
    if request:
        try:
            display_email_name = f"{request.user.employee_get.get_full_name()} <{request.user.employee_get.email}>"
        except:
            logger.error(Exception)

    if request.method == "POST":
        subject = request.POST["subject"]
        body = request.POST["body"]
        with contextlib.suppress(Exception):
            res = send_mail(
                subject,
                body,
                display_email_name,
                [candidate_mail],
                fail_silently=False,
            )
            if res == 1:
                messages.success(request, _("Mail sent successfully"))
            else:
                messages.error(request, _("Something went wrong"))
        return HttpResponse(
            response.content.decode("utf-8") + "<script>location.reload();</script>"
        )

    return response


@login_required
@stage_manager_can_enter("recruitment.change_stage")
@require_POST
def update_probation_end(request):
    """
    Updates the probation end date for a candidate.
    """
    candidate_id = request.POST.get("candidate_id")
    probation_end = request.POST.get("probation_end")

    if not candidate_id:
        messages.error(request, _("Missing candidate ID."))
        return JsonResponse({"type": "danger"}, status=400)

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        messages.error(request, _("Candidate not found."))
        return JsonResponse({"type": "danger"}, status=404)

    if probation_end == "":
        probation_end = None

    candidate.probation_end = probation_end
    candidate.save()
    messages.success(request, _("Probation end date updated"))
    return JsonResponse({"type": "success"})


@login_required
@hx_request_required
@all_manager_can_enter("onboarding.change_onboardingtask")
def task_report(request):
    """
    This method is used to show the task report.
    """
    employee_id = request.GET.get("employee_id")
    if not employee_id:
        employee_id = request.user.employee_get.id
    my_tasks = OnboardingTask.objects.filter(
        employee_id__id=employee_id,
        candidates__is_active=True,
        candidates__recruitment_id__closed=False,
    ).distinct()
    tasks = []
    for task in my_tasks:
        tasks.append(
            {
                "task": task,
                "total_candidates": task.candidatetask_set.count(),
                "todo": task.candidatetask_set.filter(status="todo").count(),
                "scheduled": task.candidatetask_set.filter(status="scheduled").count(),
                "ongoing": task.candidatetask_set.filter(status="ongoing").count(),
                "stuck": task.candidatetask_set.filter(status="stuck").count(),
                "done": task.candidatetask_set.filter(status="done").count(),
            }
        )
    return render(request, "onboarding/dashboard/task_report.html", {"tasks": tasks})


@login_required
@all_manager_can_enter("onboarding.view_candidatetask")
def candidate_tasks_status(request):
    """
    This method is used to render template to show the onboarding tasks
    """
    task_id = request.GET["task_id"]
    candidate_tasks = CandidateTask.objects.filter(onboarding_task_id__id=task_id)
    return render(
        request,
        "onboarding/dashboard/status_list.html",
        {"candidate_tasks": candidate_tasks},
    )


@login_required
@all_manager_can_enter("onboarding.change_candidatetask")
def change_task_status(request):
    """
    This method is to update the candidate task
    """
    task_id = request.GET.get("task_id")
    status = request.GET.get("status")
    if not task_id or not status:
        return HorillaRedirect(request, message=_("Task ID or status is missing"))
    candidate_task = CandidateTask.find(task_id)
    if not candidate_task:
        return HorillaRedirect(request, message=_("Candidate task not found"))
    if status in [
        "todo",
        "scheduled",
        "ongoing",
        "stuck",
        "done",
    ]:
        candidate_task.status = status
        candidate_task.save()
        messages.success(request, _("Task status updated successfully."))

    return HttpResponse(
        "<script>$('#reloadMessagesButton').click(); $('#myOnboardingReload').click(); </script>"
    )


@login_required
@permission_required("recruitment.change_recruitment")
def update_offer_letter_status(request):
    """
    This method is used to update the offer letter status
    """
    candidate_id = request.GET.get("candidate_id")
    status = request.GET.get("status")
    candidate = None
    if not candidate_id or not status:
        messages.error(request, _("candidate or status is missing"))
        return redirect("/onboarding/candidates-view/")
    if not status in ["not_sent", "sent", "accepted", "rejected", "joined"]:
        messages.error(request, _("Please Pass valid status"))
        return redirect("/onboarding/candidates-view/")
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        messages.error(request, _("Candidate not found"))
        return redirect("/onboarding/candidates-view/")
    if status in ["not_sent", "sent", "accepted", "rejected", "joined"]:
        candidate.offer_letter_status = status
        candidate.save()
    messages.success(request, _("Status of offer letter updated successfully"))
    url = "/onboarding/candidates-view/"
    return HttpResponse(
        f"""
                <script>
                window.location.href="{url}"
                </script>
                """
    )


@login_required
@hx_request_required
@permission_required("recruitment.add_rejectedcandidate")
def add_to_rejected_candidates(request):
    """
    This method is used to add candidates to rejected candidates
    """
    candidate_id = request.GET.get("candidate_id")
    instance = None
    if candidate_id:
        instance = RejectedCandidate.objects.filter(candidate_id=candidate_id).first()
    form = RejectedCandidateForm(
        initial={"candidate_id": candidate_id}, instance=instance
    )
    if request.method == "POST":
        form = RejectedCandidateForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            form = RejectedCandidateForm()
            messages.success(request, _("Candidate reject reason saved"))
            return HorillaRedirect(request)
    return render(request, "onboarding/rejection/form.html", {"form": form})


@login_required
@permission_required("recruitment.change_candidate")
@require_http_methods(["POST"])
def undo_rejected_candidate(request, candidate_id):
    """
    Remove candidate from rejected list.
    """
    deleted_count, __ = RejectedCandidate.objects.filter(
        candidate_id=candidate_id
    ).delete()
    if deleted_count:
        messages.success(request, _("Candidate removed from rejected list"))
    else:
        messages.info(request, _("Candidate is not in rejected list"))

    if request.META.get("HTTP_HX_REQUEST") == "true":
        response = HttpResponse(
            "<script>"
            "$('#applyFilter').click();"
            "$('#reloadMessagesButton').click();"
            "</script>"
        )
        # Also trigger via HX-Trigger header so listeners (#applyFilter / #reloadMessagesButton)
        # fire even when the button uses hx-swap="none" (which discards the response body).
        response["HX-Trigger"] = "reloadCandidatesList"
        return response
    return HorillaRedirect(request)


@login_required
@hx_request_required
def candidate_select(request):
    """
    This method is used for select all in candidate
    """
    page_number = request.GET.get("page")

    employees = queryset = Candidate.objects.filter(
        hired=True,
        recruitment_id__closed=False,
        is_active=True,
    )

    employee_ids = [str(emp.id) for emp in employees]
    total_count = employees.count()

    context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@permission_required("recruitment.view_candidate")
def candidate_select_filter(request):
    """
    This method is used to select all filtered candidates
    """
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}

    if page_number == "all":
        candidate_filter = CandidateFilter(
            filters,
            queryset=Candidate.objects.filter(
                hired=True,
                recruitment_id__closed=False,
                is_active=True,
            ),
        )

        # Get the filtered queryset
        filtered_candidates = candidate_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_candidates]
        total_count = filtered_candidates.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

        return JsonResponse(context)
    else:
        messages.error(request, _("Invalid page number"))
        return JsonResponse(
            {"message": _("Invalid page number")}, status=400, safe=False
        )


@login_required
@permission_required("recruitment.change_candidate")
def offer_letter_bulk_status_update(request):
    """
    This function is used to bulk update the offerletter status
    """
    letter_ids = request.GET.get("ids")

    if not letter_ids:
        messages.error(request, _("No offer letters selected for status update."))
        return JsonResponse("Missing required parameter: ids", safe=False, status=400)

    ids = json.loads(letter_ids)
    status = request.GET.get("status")
    for id in ids:
        try:
            candidate = Candidate.objects.filter(id=int(id)).first()
            if candidate.offer_letter_status != status:
                candidate.offer_letter_status = status
                candidate.save()
                messages.success(request, _("offer letter status updated successfully"))
            else:
                messages.error(request, _("Status already in {} status").format(status))
        except:
            messages.error(request, _("Candidate doesnot exist"))

    return JsonResponse("success", safe=False)


@login_required
@permission_required("recruitment.delete_candidate")
def onboarding_candidate_bulk_delete(request):
    """
    This function is used to bulk delete onboarding candidates
    """

    cand_ids = request.GET.get("ids")
    if not cand_ids:
        messages.error(request, _("No candidates selected for deletion."))
        return JsonResponse("Missing required parameter: ids", safe=False, status=400)

    ids = json.loads(cand_ids)
    for id in ids:
        try:
            candidate = Candidate.objects.filter(id=int(id)).first()
            candidate.delete()
            messages.success(request, _("candidate deleted successfully"))
        except:
            messages.error(request, _("Candidate doesnot exist"))

    return JsonResponse("success", safe=False)
