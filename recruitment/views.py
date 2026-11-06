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

from django.contrib import messages
from django.contrib.auth.models import Permission
from django.core import serializers
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_http_methods

from base.backends import ConfiguredEmailBackend
from base.methods import sortby
from employee.models import Employee
from horilla import settings
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http import HorillaRedirect
from notifications.signals import notify
from recruitment.decorators import manager_can_enter, recruitment_manager_can_enter
from recruitment.filters import CandidateFilter, RecruitmentFilter, StageFilter
from recruitment.forms import (
    ApplicationForm,
    CandidateCreationForm,
    CandidateDropDownForm,
    RecruitmentCreationForm,
    RecruitmentDropDownForm,
    StageCreationForm,
    StageDropDownForm,
    StageNoteForm,
)
from recruitment.methods import recruitment_manages
from recruitment.models import Candidate, Recruitment, Stage, StageNote

logger = logging.getLogger(__name__)


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


def paginator_qry(qryset, page_number):
    """
    This method is used to generate common paginator limit.
    """
    paginator = Paginator(qryset, 50)
    qryset = paginator.get_page(page_number)
    return qryset


@login_required
@permission_required(perm="recruitment.add_recruitment")
def recruitment(request):
    """
    This method is used to create recruitment, when create recruitment this method
    add  recruitment view,create candidate, change stage sequence and so on, some of
    the permission is checking manually instead of using django permission permission
    to the  recruitment managers
    """
    form = RecruitmentCreationForm()
    if request.method == "POST":
        form = RecruitmentCreationForm(request.POST)
        if form.is_valid():
            recruitment_obj = form.save()
            messages.success(request, _("Recruitment added."))
            with contextlib.suppress(Exception):
                managers = recruitment_obj.recruitment_managers.select_related(
                    "employee_user_id"
                )
                users = [employee.employee_user_id for employee in managers]
                notify.send(
                    request.user.employee_get,
                    recipient=users,
                    verb=gettext_noop("You are chosen as one of recruitment manager"),
                    icon="people-circle",
                    redirect=reverse("cbv-pipeline"),
                )
            response = render(
                request, "recruitment/recruitment_form.html", {"form": form}
            )
            return HorillaRedirect(request)
    return render(request, "recruitment/recruitment_form.html", {"form": form})


@login_required
@permission_required(perm="recruitment.change_recruitment")
@require_http_methods(["POST"])
def remove_recruitment_manager(request, mid, rid):
    """
    This method is used to remove selected manager from the recruitment,
    when remove the manager permissions also removed if the employee is not
    exists in more stage manager or recruitment manager

     Args:
        mid : employee manager_id in the recruitment
        rid : recruitment_id
    """
    recruitment_obj = Recruitment.objects.get(id=rid)
    manager = Employee.objects.get(id=mid)
    recruitment_obj.recruitment_managers.remove(manager)
    messages.success(request, _("Recruitment manager removed successfully."))
    notify.send(
        request.user.employee_get,
        recipient=manager.employee_user_id,
        verb=gettext_noop(
            "You are removed from recruitment manager from %(recruitment_obj)s"
        ),
        verb_params={"recruitment_obj": str(recruitment_obj)},
        icon="person-remove",
        redirect="",
    )
    recruitment_queryset = Recruitment.objects.all()
    previous_data = request.environ["QUERY_STRING"]
    return render(
        request,
        "recruitment/recruitment_component.html",
        {
            "data": paginator_qry(recruitment_queryset, request.GET.get("page")),
            "pd": previous_data,
        },
    )


@login_required
@permission_required(perm="recruitment.view_recruitment")
def recruitment_view(request):
    """
    This method is used to  render all recruitment to view
    """
    if not request.GET:
        request.GET.copy().update({"is_active": "on"})
    form = RecruitmentCreationForm()
    filter_obj = RecruitmentFilter(request.GET, queryset=Recruitment.objects.all())
    return render(
        request,
        "recruitment/recruitment_view.html",
        {
            "data": paginator_qry(filter_obj.qs, request.GET.get("page")),
            "f": filter_obj,
            "form": form,
        },
    )


@login_required
@permission_required(perm="recruitment.view_recruitment")
def recruitment_search(request):
    """
    This method is used to search recruitment
    """
    filter_obj = RecruitmentFilter(request.GET)
    previous_data = request.environ["QUERY_STRING"]
    recruitment_obj = sortby(request, filter_obj.qs, "orderby")
    return render(
        request,
        "recruitment/recruitment_component.html",
        {
            "data": paginator_qry(recruitment_obj, request.GET.get("page")),
            "pd": previous_data,
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
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    form = RecruitmentCreationForm(instance=recruitment_obj)
    if request.method == "POST":
        form = RecruitmentCreationForm(request.POST, instance=recruitment_obj)
        if form.is_valid():
            recruitment_obj = form.save()
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
                    verb=gettext_noop(
                        "%(recruitment_obj)s is updated. You are chosen as one of the managers."
                    ),
                    verb_params={"recruitment_obj": str(recruitment_obj)},
                    icon="people-circle",
                    redirect=reverse("cbv-pipeline"),
                )

            return HttpResponse(
                response.content.decode("utf-8") + "<script>location.reload();</script>"
            )
    return render(request, "recruitment/recruitment_update_form.html", {"form": form})


@login_required
@permission_required(perm="recruitment.delete_recruitment")
@require_http_methods(["POST"])
def recruitment_delete(request, rec_id):
    """
    This method is used to permanently delete the recruitment
    Args:
        id : recruitment_id
    """
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    recruitment_mangers = recruitment_obj.recruitment_managers.all()
    all_stage_permissions = Permission.objects.filter(
        content_type__app_label="recruitment", content_type__model="stage"
    )
    all_candidate_permissions = Permission.objects.filter(
        content_type__app_label="recruitment", content_type__model="candidate"
    )
    for manager in recruitment_mangers:
        all_this_manger = manager.recruitment_set.all()
        if len(all_this_manger) == 1:
            for stage_permission in all_candidate_permissions:
                manager.employee_user_id.user_permissions.remove(stage_permission.id)
            for candidate_permission in all_stage_permissions:
                manager.employee_user_id.user_permissions.remove(
                    candidate_permission.id
                )
    try:
        recruitment_obj.delete()
        messages.success(request, _("Recruitment deleted successfully."))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("You cannot delete this recruitment"))
    recruitment_obj = Recruitment.objects.all()
    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def recruitment_pipeline(request):
    """
    This method is used to filter out candidate through pipeline structure
    """
    view = request.GET.get("view")
    template = "pipeline/pipeline.html"
    if view == "card":
        template = "pipeline/pipeline_card.html"
    recruitment_form = RecruitmentDropDownForm()
    stage_form = StageDropDownForm()
    candidate_form = CandidateDropDownForm()
    recruitment_obj = Recruitment.objects.filter(is_active=True, closed=False)
    if request.method == "POST":
        if request.POST.get(
            "recruitment_managers"
        ) is not None and request.user.has_perm("recruitment.add_recruitment"):
            recruitment_form = RecruitmentDropDownForm(request.POST)
            if recruitment_form.is_valid():
                recruitment_obj = recruitment_form.save()
                recruitment_form = RecruitmentDropDownForm()
                messages.success(request, _("Recruitment added."))
                with contextlib.suppress(Exception):
                    managers = recruitment_obj.recruitment_managers.select_related(
                        "employee_user_id"
                    )
                    users = [employee.employee_user_id for employee in managers]
                    notify.send(
                        request.user.employee_get,
                        recipient=users,
                        verb=gettext_noop(
                            "You are chosen as recruitment manager for the recruitment %(recruitment_obj)s"
                        ),
                        verb_params={"recruitment_obj": str(recruitment_obj)},
                        icon="people-circle",
                        redirect=reverse("cbv-pipeline"),
                    )

                return HorillaRedirect(request)
        elif request.FILES.get("resume") is not None:
            if request.user.has_perm("recruitment.add_candidate") or is_stagemanager(
                request,
            ):
                candidate_form = CandidateDropDownForm(request.POST, request.FILES)
                if candidate_form.is_valid():
                    candidate_obj = candidate_form.save()
                    candidate_form = CandidateDropDownForm()
                    with contextlib.suppress(Exception):
                        managers = candidate_obj.stage_id.stage_managers.select_related(
                            "employee_user_id"
                        )
                        users = [employee.employee_user_id for employee in managers]
                        notify.send(
                            request.user.employee_get,
                            recipient=users,
                            verb=gettext_noop(
                                "New candidate arrived on stage %(stage)s"
                            ),
                            verb_params={"stage": str(candidate_obj.stage_id.stage)},
                            icon="person-add",
                            redirect=reverse("cbv-pipeline"),
                        )

                    messages.success(request, _("Candidate added."))
                    return HorillaRedirect(request)
        elif request.POST.get("stage_managers") and request.user.has_perm(
            "recruitment.add_stage"
        ):
            stage_form = StageDropDownForm(request.POST)
            if stage_form.is_valid():
                if recruitment_manages(
                    request, stage_form.instance.recruitment_id
                ) or request.user.has_perm("recruitment.add_stage"):
                    stage_obj = stage_form.save()
                    stage_form = StageDropDownForm()
                    messages.success(request, _("Stage added."))
                    with contextlib.suppress(Exception):
                        managers = stage_obj.stage_managers.select_related(
                            "employee_user_id"
                        )
                        users = [employee.employee_user_id for employee in managers]
                        notify.send(
                            request.user.employee_get,
                            recipient=users,
                            verb=gettext_noop(
                                "You are chosen as a stage manager on the stage %(stage)s in recruitment %(recruitment_id)s"
                            ),
                            verb_params={
                                "stage": str(stage_obj.stage),
                                "recruitment_id": str(stage_obj.recruitment_id),
                            },
                            icon="people-circle",
                            redirect=reverse("cbv-pipeline"),
                        )

                    return HorillaRedirect(request)
                messages.info(request, _("You don't have access"))
    return render(
        request,
        template,
        {
            "recruitment": recruitment_obj,
            "recruitment_form": recruitment_form,
            "stage_form": stage_form,
            "candidate_form": candidate_form,
        },
    )


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
@recruitment_manager_can_enter(perm="recruitment.change_stage")
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
                    verb=gettext_noop(
                        "%(stage)s stage in recruitment %(recruitment_id)s is updated. You are chosen as one of the managers."
                    ),
                    verb_params={
                        "stage": str(stage_obj.stage),
                        "recruitment_id": str(stage_obj.recruitment_id),
                    },
                    icon="people-circle",
                    redirect=reverse("cbv-pipeline"),
                )

            return HorillaRedirect(request)

    return render(request, "pipeline/form/stage_update.html", {"form": form})


@login_required
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
                    verb=gettext_noop(
                        "%(recruitment_obj)s is updated. You are chosen as one of the managers."
                    ),
                    verb_params={"recruitment_obj": str(recruitment_obj)},
                    icon="people-circle",
                    redirect=reverse("cbv-pipeline"),
                )

            return HorillaRedirect(request)
    return render(request, "pipeline/form/recruitment_update.html", {"form": form})


@login_required
@permission_required(perm="recruitment.delete_recruitment")
@require_http_methods(["POST"])
def recruitment_delete_pipeline(request, rec_id):
    """This method is used to delete the recruitment instance

    Args:
        id: recruitment instance id
    Returns:
        HorillaRedirect: Used to refresh the page
    """
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    try:
        recruitment_obj.delete()
        messages.success(request, _("Recruitment deleted."))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("Recruitment already in use."))
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
    stage_id = request.POST["stageId"]
    candidate_obj = Candidate.objects.get(id=cand_id)
    history_queryset = candidate_obj.candidate_history.all().first()
    stage_obj = Stage.objects.get(id=stage_id)
    previous_stage = history_queryset.stage_id
    if previous_stage == stage_obj:
        return JsonResponse({"type": "info", "message": _("Sequence updated.")})
    # Here set the last updated schedule date on this stage if schedule exists in history
    history_queryset = candidate_obj.candidate_history.filter(stage_id=stage_obj)
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
        candidate_obj.schedule_date = None
        candidate_obj.hired = stage_obj.stage_type == "shortlisted"
        candidate_obj.schedule_date = schedule_date
        candidate_obj.start_onboard = False
        candidate_obj.save()
        with contextlib.suppress(Exception):
            managers = stage_obj.stage_managers.select_related("employee_user_id")
            users = [employee.employee_user_id for employee in managers]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb=gettext_noop("New candidate arrived on stage %(stage)s"),
                verb_params={"stage": str(stage_obj.stage)},
                icon="person-add",
                redirect=reverse("cbv-pipeline"),
            )

        return JsonResponse(
            {"type": "success", "message": _("Candidate stage updated")}
        )
    return JsonResponse(
        {"type": "danger", "message": _("Something went wrong, Try again.")}
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.add_stagenote")
def add_note(request, cand_id=None):
    """
    This method renders template component to add candidate remark
    """
    form = StageNoteForm(initial={"candidate_id": cand_id})
    if request.method == "POST":
        form = StageNoteForm(
            request.POST,
        )
        if form.is_valid():
            note = form.save(commit=False)
            note.stage_id = note.candidate_id.stage_id
            note.updated_by = request.user.employee_get
            note.save()
            messages.success(request, _("Note added successfully.."))
            return HorillaRedirect(request)
    return render(
        request,
        "pipeline/pipeline_components/add_note.html",
        {
            "note_form": form,
        },
    )


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.view_stagenote")
def view_note(request, cand_id):
    """
    This method renders a template components to view candidate remark or note
    Args:
        id : candidate instance id
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    return render(
        request, "pipeline/pipeline_components/view_note.html", {"cand": candidate_obj}
    )


@login_required
@permission_required(perm="recruitment.change_stagenote")
def note_update(request, note_id):
    """
    This method is used to update the stage not
    Args:
        id : stage note instance id
    """
    note = StageNote.objects.get(id=note_id)
    form = StageNoteForm(instance=note)
    if request.POST:
        form = StageNoteForm(request.POST, instance=note)
        if form.is_valid():
            form.save()
            messages.success(request, _("Note updated successfully..."))
            return HorillaRedirect(request)
    return render(
        request, "pipeline/pipeline_components/update_note.html", {"form": form}
    )


@login_required
@permission_required(perm="recruitment.delete_stagenote")
def note_delete(request, note_id):
    """
    This method is used to delete the stage note
    """
    note = StageNote.objects.get(id=note_id)
    candidate_obj = note.candidate_id
    try:
        note.delete()
        messages.success(request, _("Note deleted"))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("You cannot delete this note."))
    return render(
        request, "pipeline/pipeline_components/view_note.html", {"cand": candidate_obj}
    )


@login_required
@require_http_methods(["DELETE"])
@permission_required(perm="recruitment.delete_stagenote")
def candidate_remark_delete(request, note_id):
    """
    This method is used to delete the candidate stage note
    Args:
        id : stage note instance id
    """
    stage_note = StageNote.objects.get(id=note_id)
    candidate_obj = stage_note.candidate_note_id.candidate_id
    try:
        stage_note.delete()
        messages.success(request, _("Note deleted"))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("You cannot delete this note."))
    return render(
        request,
        "pipeline/pipeline_components/candidate_remark_view.html",
        {"cand": candidate_obj},
    )


@login_required
@permission_required(perm="recruitment.change_candidate")
def candidate_schedule_date_update(request):
    """
    This is a an ajax method to update schedule date for a candidate
    """
    candidate_id = request.POST["candidateId"]
    schedule_date = request.POST["date"]
    candidate_obj = Candidate.objects.get(id=candidate_id)
    candidate_obj.schedule_date = schedule_date
    candidate_obj.save()
    return JsonResponse({"message": "congratulations"})


@login_required
@permission_required(perm="recruitment.add_stage")
def stage(request):
    """
    This method is used to create stages, also several permission assigned to the stage managers
    """
    form = StageCreationForm()
    if request.method == "POST":
        form = StageCreationForm(request.POST)
        if form.is_valid():
            stage_obj = form.save()
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
                    verb=gettext_noop(
                        "Stage %(stage_obj)s is updated on recruitment %(recruitment_id)s. You are chosen as one of the managers."
                    ),
                    verb_params={
                        "stage_obj": str(stage_obj),
                        "recruitment_id": str(stage_obj.recruitment_id),
                    },
                    icon="people-circle",
                    redirect=reverse("cbv-pipeline"),
                )

            return HorillaRedirect(request)
    return render(request, "stage/stage_form.html", {"form": form})


@login_required
@permission_required(perm="recruitment.view_stage")
def stage_view(request):
    """
    This method is used to render all stages to a template
    """
    stages = Stage.objects.filter()
    filter_obj = StageFilter()
    form = StageCreationForm()
    return render(
        request,
        "stage/stage_view.html",
        {
            "data": paginator_qry(stages, request.GET.get("page")),
            "form": form,
            "f": filter_obj,
        },
    )


@login_required
@permission_required(perm="recruitment.view_stage")
def stage_search(request):
    """
    This method is used to search stage
    """
    stages = StageFilter(request.GET).qs
    previous_data = request.environ["QUERY_STRING"]
    stages = sortby(request, stages, "orderby")
    return render(
        request,
        "stage/stage_component.html",
        {"data": paginator_qry(stages, request.GET.get("page")), "pd": previous_data},
    )


@login_required
@permission_required(perm="recruitment.change_stage")
def remove_stage_manager(request, mid, sid):
    """
    This method is used to remove selected stage manager and also removing the  given
    permission if the employee is not exists in more stage manager or recruitment manager
    Args:
        mid : manager_id in the stage
        sid : stage_id
    """
    stage_obj = Stage.objects.get(id=sid)
    manager = Employee.objects.get(id=mid)
    notify.send(
        request.user.employee_get,
        recipient=manager.employee_user_id,
        verb=gettext_noop(
            "You are removed from stage managers from stage %(stage_obj)s"
        ),
        verb_params={"stage_obj": str(stage_obj)},
        icon="person-remove",
        redirect="",
    )
    stage_obj.stage_managers.remove(manager)
    messages.success(request, _("Stage manager removed successfully."))
    stages = Stage.objects.all()
    previous_data = request.environ["QUERY_STRING"]
    return render(
        request,
        "stage/stage_component.html",
        {"data": paginator_qry(stages, request.GET.get("page")), "pd": previous_data},
    )


@login_required
@permission_required(perm="recruitment.change_stage")
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
@require_http_methods(["POST"])
@hx_request_required
def stage_name_update(request, stage_id):
    """
    This method is used to update the name of recruitment stage
    """
    stage_obj = Stage.objects.get(id=stage_id)
    stage_obj.stage = request.POST["stage"]
    stage_obj.save()
    return HttpResponse({"message": "success"})


@login_required
@permission_required(perm="recruitment.delete_stage")
@require_http_methods(["POST", "DELETE"])
def stage_delete(request, stage_id):
    """
    This method is used to delete stage permanently
    Args:
        id : stage_id
    """
    stage_obj = Stage.objects.get(id=stage_id)
    stage_managers = stage_obj.stage_managers.all()
    for manager in stage_managers:
        all_this_manger = manager.stage_set.all()
        if len(all_this_manger) == 1:
            view_recruitment = Permission.objects.get(codename="view_recruitment")
            manager.employee_user_id.user_permissions.remove(view_recruitment.id)
        initial_stage_manager = all_this_manger.filter(stage_type="initial")
        if len(initial_stage_manager) == 1:
            add_candidate = Permission.objects.get(codename="recruitment.add_candidate")
            change_candidate = Permission.objects.get(codename="change_candidate")
            manager.employee_user_id.user_permissions.remove(add_candidate.id)
            manager.employee_user_id.user_permissions.remove(change_candidate.id)
        stage_obj.stage_managers.remove(manager)
    try:
        stage_obj.delete()
        messages.success(request, _("Stage deleted successfully."))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("You cannot delete this stage"))
    return HorillaRedirect(request)


@login_required
@permission_required(perm="recruitment.add_candidate")
def candidate(request):
    """
    This method used to create candidate
    """
    form = CandidateCreationForm()
    open_recruitment = Recruitment.objects.filter(closed=False, is_active=True)
    path = "/recruitment/candidate-view"
    if request.method == "POST":
        form = CandidateCreationForm(request.POST, request.FILES)
        if form.is_valid():
            candidate_obj = form.save(commit=False)
            candidate_obj.start_onboard = False
            if candidate_obj.stage_id is None:
                candidate_obj.stage_id = Stage.objects.filter(
                    recruitment_id=candidate_obj.recruitment_id, stage_type="initial"
                ).first()
            # when creating new candidate from onboarding view
            if request.GET.get("onboarding") == "True":
                candidate_obj.hired = True
                path = "/onboarding/candidates-view"
            candidate_obj.save()
            messages.success(request, _("Candidate added."))
            return redirect(path)

    return render(
        request,
        "candidate/candidate_create_form.html",
        {"form": form, "open_recruitment": open_recruitment},
    )


@login_required
@permission_required(perm="recruitment.add_candidate")
def recruitment_stage_get(_, rec_id):
    """
    This method returns all stages as json
    Args:
        id: recruitment_id
    """
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    all_stages = recruitment_obj.stage_set.all()
    all_stage_json = serializers.serialize("json", all_stages)
    return JsonResponse({"stages": all_stage_json})


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_view(request):
    """
    This method render all candidate to the template
    """
    previous_data = request.environ["QUERY_STRING"]
    candidates = Candidate.objects.filter(is_active=True)
    filter_obj = CandidateFilter(queryset=candidates)
    return render(
        request,
        "candidate/candidate_view.html",
        {
            "data": paginator_qry(filter_obj.qs, request.GET.get("page")),
            "pd": previous_data,
            "f": filter_obj,
        },
    )


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_filter_view(request):
    """
    This method is used for filter,pagination and search candidate.
    """
    previous_data = request.environ["QUERY_STRING"]
    filter_obj = CandidateFilter(
        request.GET, queryset=Candidate.objects.filter(is_active=True)
    )
    paginator = Paginator(filter_obj.qs, 24)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "candidate/candidate_card.html",
        {"data": page_obj, "pd": previous_data},
    )


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_search(request):
    """
    This method is used to search candidate model and return matching objects
    """
    previous_data = request.environ["QUERY_STRING"]
    search = request.GET.get("search")
    if search is None:
        search = ""
    candidates = Candidate.objects.filter(name__icontains=search)
    candidates = CandidateFilter(request.GET, queryset=candidates).qs
    template = "candidate/candidate_card.html"
    if request.GET.get("view") == "list":
        template = "candidate/candidate_list.html"
    candidates = sortby(request, candidates, "orderby")
    candidates = paginator_qry(candidates, request.GET.get("page"))
    return render(request, template, {"data": candidates, "pd": previous_data})


@login_required
@permission_required(perm="recruitment.view_candidate")
def candidate_view_list(request):
    """
    This method renders all candidate on candidate_list.html template
    """
    previous_data = request.environ["QUERY_STRING"]
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
@permission_required(perm="recruitment.view_candidate")
def candidate_view_card(request):
    """
    This method renders all candidate on candidate_card.html template
    """
    previous_data = request.environ["QUERY_STRING"]
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
@permission_required(perm="recruitment.view_candidate")
def candidate_view_individual(request, cand_id):
    """
    This method is used to view profile of candidate.
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    return render(request, "candidate/individual.html", {"candidate": candidate_obj})


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def candidate_update(request, cand_id):
    """
    Used to update or change the candidate
    Args:
        id : candidate_id
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    form = CandidateCreationForm(instance=candidate_obj)
    path = "/recruitment/candidate-view"
    if request.method == "POST":
        form = CandidateCreationForm(
            request.POST, request.FILES, instance=candidate_obj
        )
        if form.is_valid():
            candidate_obj = form.save()
            if candidate_obj.stage_id is None:
                candidate_obj.stage_id = Stage.objects.filter(
                    recruitment_id=candidate_obj.recruitment_id, stage_type="initial"
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
            if request.GET.get("onboarding") == "True":
                candidate_obj.hired = True
                path = "/onboarding/candidates-view"
            candidate_obj.save()
            messages.success(request, _("Candidate Updated Successfully."))
            return redirect(path)
    return render(request, "candidate/candidate_create_form.html", {"form": form})


@login_required
@permission_required(perm="recruitment.delete_candidate")
@require_http_methods(["DELETE", "POST"])
def candidate_delete(request, cand_id):
    """
    This method is used to delete candidate permanently
    Args:
        id : candidate_id
    """
    try:
        Candidate.objects.get(id=cand_id).delete()
        messages.success(request, _("Candidate deleted successfully."))
    except Exception as error:
        messages.error(request, error)
        messages.error(request, _("You cannot delete this candidate"))
    return HorillaRedirect(request)


@login_required
@permission_required(perm="recruitment.delete_candidate")
def candidate_archive(request, cand_id):
    """
    This method is used to archive or un-archive candidates
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    candidate_obj.is_active = not candidate_obj.is_active
    candidate_obj.save()
    return HorillaRedirect(request)


@login_required
@permission_required(perm="recruitment.delete_candidate")
@require_http_methods(["POST"])
def candidate_bulk_delete(request):
    """
    This method is used to bulk delete candidates
    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    for cand_id in ids:
        candidate_obj = Candidate.objects.get(id=cand_id)
        try:
            candidate_obj.delete()
            messages.success(
                request, _("%(candidate_obj)s deleted.") % {"candidate": candidate_obj}
            )
        except Exception as error:
            messages.error(
                request,
                _("You cannot delete %(candidate_obj)s") % {"candidate": candidate_obj},
            )
            messages.error(request, error)
    return JsonResponse({"message": "Success"})


@login_required
@permission_required(perm="recruitment.delete_candidate")
@require_http_methods(["POST"])
def candidate_bulk_archive(request):
    """
    This method is used to archive/un-archive bulk candidates
    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    is_active = True
    message = "un-archived"
    if request.GET.get("is_active") == "False":
        is_active = False
        message = "archived"
    for cand_id in ids:
        candidate_obj = Candidate.objects.get(id=cand_id)
        candidate_obj.is_active = is_active
        candidate_obj.save()
        messages.success(
            request,
            _("%(candidate_obj)s is %(message)s")
            % {"candidate_obj": candidate_obj, "message": message},
        )
    return JsonResponse({"message": "Success"})


@login_required
@permission_required(perm="recruitment.view_history")
def candidate_history(request, cand_id):
    """
    This method is used to view candidate stage changes
    Args:
        id : candidate_id
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    candidate_history_queryset = candidate_obj.history.all()
    return render(
        request,
        "candidate/candidate_history.html",
        {"history": candidate_history_queryset},
    )


def application_form(request):
    """
    This method renders candidate form to create candidate
    """
    form = ApplicationForm()
    if request.POST:
        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            candidate_obj = form.save(commit=False)
            recruitment_obj = candidate_obj.recruitment_id
            stages = recruitment_obj.stage_set.all()
            if stages.filter(stage_type="applied").exists():
                candidate_obj.stage_id = stages.filter(stage_type="applied").first()
            else:
                candidate_obj.stage_id = stages.order_by("sequence").first()
            candidate_obj.save()
            messages.success(request, _("Application saved."))
            return render(request, "candidate/success.html")
        form.fields["job_position_id"].queryset = (
            form.instance.recruitment_id.open_positions.all()
        )
    return render(request, "candidate/application_form.html", {"form": form})


@login_required
@hx_request_required
@manager_can_enter(perm="recruitment.change_candidate")
def form_send_mail(request, cand_id):
    """
    This method is used to render the bootstrap modal content body form
    """
    candidate_obj = Candidate.objects.get(id=cand_id)
    return render(
        request, "pipeline/pipeline_components/send_mail.html", {"cand": candidate_obj}
    )


@login_required
@manager_can_enter(perm="recruitment.change_candidate")
def send_acknowledgement(request):
    """
    This method is used to send acknowledgement mail to the candidate
    """
    with contextlib.suppress(Exception):
        send_to = request.POST.get("to")
        subject = request.POST.get("subject")
        bdy = request.POST.get("body")
        email_backend = ConfiguredEmailBackend()
        display_email_name = email_backend.dynamic_from_email_with_display_name
        if request:
            try:
                display_email_name = f"{request.user.employee_get.get_full_name()} <{request.user.employee_get.email}>"
            except:
                logger.error(Exception)

        res = send_mail(
            subject, bdy, display_email_name, [send_to], fail_silently=False
        )
        if res == 1:
            return HttpResponse(
                """
            <div class="oh-alert-container">
                <div class="oh-alert oh-alert--animated oh-alert--success"> Mail sent.</div>
            </div>
            """
            )
    return HttpResponse(
        """
        <div class="oh-alert-container">
            <div class="oh-alert oh-alert--animated oh-alert--danger">Sorry,\
                Something went wrong.</div>
        </div>
        """
    )


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard(request):
    """
    This method is used to render individual dashboard for recruitment module
    """
    candidates = Candidate.objects.all()
    hired_candidates = candidates.filter(hired=True)
    total_candidates = len(candidates)
    total_hired_candidates = len(hired_candidates)
    hire_ratio = 0
    if total_candidates != 0:
        hire_ratio = f"{((total_hired_candidates / total_candidates) * 100):.1f}"
    return render(
        request,
        "dashboard/dashboard.html",
        {
            "total_candidates": total_candidates,
            "total_hired_candidates": total_hired_candidates,
            "hire_ratio": hire_ratio,
            "onboard_candidates": hired_candidates.filter(start_onboard=True),
        },
    )


def stage_type_candidate_count(rec, stage_type):
    """
    This method is used find the count of candidate in recruitment
    """
    candidates_count = 0
    for stage_obj in rec.stage_set.filter(stage_type=stage_type):
        candidates_count = candidates_count + len(
            stage_obj.candidate_set.filter(is_active=True)
        )
    return candidates_count


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard_pipeline(_):
    """
    This method is used generate recruitment dataset for the dashboard
    """
    recruitment_obj = Recruitment.objects.filter(closed=False)
    data_set = []
    labels = [type[1] for type in Stage.stage_types]
    for rec in recruitment_obj:
        data = [stage_type_candidate_count(rec, type[0]) for type in Stage.stage_types]
        data_set.append(
            {
                "label": (
                    rec.title
                    if rec.title is not None
                    else f"""{rec.job_position_id}
                 {rec.start_date}"""
                ),
                "data": data,
            }
        )
    return JsonResponse({"dataSet": data_set, "labels": labels})


def get_open_position(request):
    """
    This is an ajax method to render the open position to the recruitment

    Returns:
        obj: it returns the list of job positions
    """
    rec_id = request.GET["recId"]
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    queryset = recruitment_obj.open_positions.all()
    job_info = serializers.serialize("json", queryset)
    rec_info = serializers.serialize("json", [recruitment_obj])
    return JsonResponse({"openPositions": job_info, "recruitmentInfo": rec_info})


@login_required
@manager_can_enter("recruitment.change_candidate")
def candidate_sequence_update(request):
    """
    This method is used to update the sequence of candidate
    """
    sequence_data = json.loads(request.POST["sequenceData"])
    for cand_id, seq in sequence_data.items():
        cand = Candidate.objects.get(id=cand_id)
        cand.sequence = seq
        cand.save()

    return JsonResponse({"message": "Sequence updated", "type": "info"})


@login_required
@recruitment_manager_can_enter("recruitment.change_stage")
def stage_sequence_update(request):
    """
    This method is used to update the sequence of the stages
    """
    sequence_data = json.loads(request.POST["sequence"])
    for stage_id, seq in sequence_data.items():
        stage = Stage.objects.get(id=stage_id)
        stage.sequence = seq
        stage.save()
    return JsonResponse({"type": "success", "message": "Stage sequence updated"})
