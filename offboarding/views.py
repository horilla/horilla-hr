import json
import logging
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from django.apps import apps
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.utils import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.context_processors import intial_notice_period
from base.methods import closest_numbers, eval_validate, paginator_qry, sortby
from base.models import Department, JobPosition
from base.views import general_settings
from employee.models import Employee
from horilla import horilla_middlewares
from horilla.decorators import (
    hx_request_required,
    login_required,
    manager_can_enter,
    owner_can_enter,
    permission_required,
)
from horilla.group_by import group_by_queryset as group_by
from horilla.http.response import HorillaRedirect
from horilla.methods import get_horilla_model_class
from horilla_auth.models import HorillaUser
from horilla_views.generic.cbv.views import HorillaFormView
from notifications.signals import notify
from offboarding.decorators import (
    any_manager_can_enter,
    check_feature_enabled,
    offboarding_manager_can_enter,
    offboarding_or_stage_manager_can_enter,
)
from offboarding.filters import (
    LetterFilter,
    LetterReGroup,
    PipelineEmployeeFilter,
    PipelineFilter,
    PipelineStageFilter,
)
from offboarding.forms import (
    NoteForm,
    OffboardingEmployeeForm,
    OffboardingForm,
    OffboardingStageForm,
    ResignationLetterForm,
    StageSelectForm,
    TaskForm,
)
from offboarding.models import (
    EmployeeTask,
    Offboarding,
    OffboardingEmployee,
    OffboardingGeneralSetting,
    OffboardingNote,
    OffboardingStage,
    OffboardingStageMultipleFile,
    OffboardingTask,
    ResignationLetter,
)

logger = logging.getLogger(__name__)


def any_manager(employee: Employee):
    """
    This method is used to check the employee is in managers
    employee: Employee model instance
    """
    return (
        Offboarding.objects.filter(managers=employee).exists()
        | OffboardingStage.objects.filter(managers=employee).exists()
        | OffboardingTask.objects.filter(managers=employee).exists()
    )


def pipeline_grouper(filters={}, offboardings=[]):
    groups = []
    request = getattr(horilla_middlewares._thread_locals, "request", None)
    for offboarding in offboardings:
        employees = []
        stages = PipelineStageFilter(
            filters, queryset=offboarding.offboardingstage_set.all()
        ).qs.order_by("id")
        all_stages_grouper = []
        data = {"offboarding": offboarding, "stages": [], "employees": []}
        for stage in stages:
            all_stages_grouper.append({"grouper": stage, "list": []})
            stage_employees = PipelineEmployeeFilter(
                filters,
                OffboardingEmployee.objects.filter(stage_id=stage),
            ).qs.order_by("stage_id__id")

            if request and not (
                request.user.has_perm("offboarding.view_offboarding")
                or any_manager(request.user.employee_get)
            ):
                stage_employees = stage_employees.filter(
                    employee_id=request.user.employee_get
                )

            page_name = "page" + stage.title + str(offboarding.id)
            employee_grouper = group_by(
                stage_employees,
                "stage_id",
                filters.get(page_name),
                page_name,
            ).object_list
            employees = employees + [
                employee.id for employee in stage.offboardingemployee_set.all()
            ]
            data["stages"] = data["stages"] + employee_grouper

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
            "offboarding": offboarding,
            "stages": ordered_data,
            "employee_ids": employees,
        }
        groups.append(data)

    return groups


def paginator_qry_offboarding_limited(qryset, page_number):
    """
    This method is used to generate common paginator limit.
    """
    paginator = Paginator(qryset, 3)
    qryset = paginator.get_page(page_number)
    return qryset


@login_required
@any_manager_can_enter(
    "offboarding.view_offboarding", offboarding_employee_can_enter=True
)
def pipeline(request):
    """
    Offboarding pipeline view
    """
    # Apply filters and pagination
    offboardings = PipelineFilter().qs
    paginated_offboardings = paginator_qry_offboarding_limited(
        offboardings, request.GET.get("page")
    )

    # Group data after pagination
    groups = pipeline_grouper({}, paginated_offboardings)

    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])

    stage_forms = {}
    for offboarding in paginated_offboardings:
        stage_forms[str(offboarding.id)] = StageSelectForm(offboarding=offboarding)

    filter_dict = parse_qs(request.GET.urlencode())

    return render(
        request,
        "offboarding/pipeline/pipeline.html",
        {
            "offboardings": groups,  # Grouped data
            "paginated_offboardings": paginated_offboardings,  # Original paginated object
            "employee_filter": PipelineEmployeeFilter(),
            "pipeline_filter": PipelineFilter(),
            "stage_filter": PipelineStageFilter(),
            "stage_forms": stage_forms,
            "filter_dict": filter_dict,
            "today": datetime.today().date(),
        },
    )


@login_required
@hx_request_required
@any_manager_can_enter(
    "offboarding.view_offboarding", offboarding_employee_can_enter=True
)
def filter_pipeline(request):
    """
    This method is used filter offboarding process
    """
    offboardings = PipelineFilter(request.GET).qs
    paginated_offboardings = paginator_qry_offboarding_limited(
        offboardings, request.GET.get("page")
    )

    groups = pipeline_grouper(request.GET, paginated_offboardings)
    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])
    stage_forms = {}
    for offboarding in paginated_offboardings:
        stage_forms[str(offboarding.id)] = StageSelectForm(offboarding=offboarding)
    return render(
        request,
        "offboarding/pipeline/offboardings.html",
        {
            "offboardings": groups,
            "paginated_offboardings": paginated_offboardings,
            "stage_forms": stage_forms,
            "filter_dict": parse_qs(request.GET.urlencode()),
        },
    )


@login_required
@hx_request_required
@permission_required("offboarding.add_offboarding")
def create_offboarding(request):
    """
    Create offboarding view
    """
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    if instance_id and isinstance(instance_id, int):
        instance = Offboarding.objects.filter(id=instance_id).first()
    form = OffboardingForm(instance=instance)
    if request.method == "POST":
        form = OffboardingForm(request.POST, instance=instance)
        if form.is_valid():
            off_boarding = form.save()
            messages.success(request, _("Offboarding saved"))
            users = [
                employee.employee_user_id for employee in off_boarding.managers.all()
            ]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are chosen as an offboarding manager",
                verb_ar="لقد تم اختيارك كمدير عملية المغادرة",
                verb_de="Sie wurden als Offboarding-Manager ausgewählt",
                verb_es="Has sido elegido como gerente de offboarding",
                verb_fr="Vous avez été choisi comme responsable du processus de départ",
                icon="people-circle",
                redirect=reverse("offboarding-pipeline"),
            )

            return HorillaRedirect(request)

    return render(
        request,
        "offboarding/pipeline/form.html",
        {
            "form": form,
        },
    )


@login_required
@permission_required("offboarding.delete_offboarding")
def delete_offboarding(request, id):
    """
    This method is used to delete offboardings
    """
    try:
        offboarding = Offboarding.objects.get(id=id)
        offboarding.delete()
        messages.success(request, _("Offboarding deleted"))
    except (Offboarding.DoesNotExist, OverflowError):
        messages.error(request, _("Offboarding not found"))
    return redirect(filter_pipeline)


@login_required
@offboarding_manager_can_enter("offboarding.add_offboardingstage")
def create_stage(request):
    """
    This method is used to create stages for offboardings
    """
    offboarding_id = request.GET["offboarding_id"]
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    if instance_id and isinstance(instance_id, int):
        instance = OffboardingStage.objects.get(id=instance_id)
    offboarding = Offboarding.objects.get(id=offboarding_id)
    form = OffboardingStageForm(instance=instance)
    form.instance.offboarding_id = offboarding
    if request.method == "POST":
        form = OffboardingStageForm(request.POST, instance=instance)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.offboarding_id = offboarding
            instance.save()
            instance.managers.set(form.data.getlist("managers"))
            messages.success(request, _("Stage saved"))
            users = [employee.employee_user_id for employee in instance.managers.all()]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are chosen as offboarding stage manager",
                verb_ar="لقد تم اختيارك كمدير لمرحلة عملية المغادرة",
                verb_de="Sie wurden als Manager der Offboarding-Phase ausgewählt",
                verb_es="Has sido elegido como gerente de la etapa de offboarding",
                verb_fr="Vous avez été choisi comme responsable de l'étape de départ",
                icon="people-circle",
                redirect=reverse("offboarding-pipeline"),
            )
            return HorillaRedirect(request)

    return render(request, "offboarding/stage/form.html", {"form": form})


@login_required
@offboarding_manager_can_enter("offboarding.change_offboardingstage")
def update_stage_order(request, pk):
    """
    This method is used to update the stage sequence of the offboarding
    """
    offboarding = Offboarding.find(pk)
    if not offboarding:
        return HorillaRedirect(request, message=_("Offboarding not found"))

    if request.method == "POST":
        try:
            order = json.loads(request.POST.get("order", "[]"))
            for index, stage_id in enumerate(order):
                stage = offboarding.offboardingstage_set.get(id=stage_id)
                stage.sequence = index + 1
                stage.save()
            messages.success(request, _("Sequence Updated Successfully"))
            return JsonResponse({"status": "success"})
        except Exception as e:
            messages.error(request, _("Error Updating Sequence.."))
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    stages = offboarding.offboardingstage_set.order_by("sequence")

    return render(
        request,
        "cbv/exit_process/stage_order.html",
        {
            "stages": stages,
            "offboarding": offboarding,
        },
    )


@login_required
@any_manager_can_enter("offboarding.add_offboardingemployee")
def add_employee(request):
    """
    This method is used to add employee to the stage
    """
    default_notice_period = (
        intial_notice_period(request)["get_initial_notice_period"]
        if intial_notice_period(request)["get_initial_notice_period"]
        else 0
    )
    end_date = datetime.today() + timedelta(days=default_notice_period)
    stage_id = request.GET["stage_id"]
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    if instance_id and isinstance(instance_id, int):
        instance = OffboardingEmployee.objects.get(id=instance_id)
    stage = OffboardingStage.objects.get(id=stage_id)
    form = OffboardingEmployeeForm(
        initial={"stage_id": stage, "notice_period_ends": end_date}, instance=instance
    )
    form.instance.stage_id = stage
    if request.method == "POST":
        form = OffboardingEmployeeForm(request.POST, instance=instance)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.stage_id = stage
            instance.save()
            messages.success(request, _("Employee saved"))
            if not instance_id:
                notify.send(
                    request.user.employee_get,
                    recipient=instance.employee_id.employee_user_id,
                    verb=f"You have been added to the {stage} of {stage.offboarding_id}",
                    verb_ar=f"لقد تمت إضافتك إلى {stage} من {stage.offboarding_id}",
                    verb_de=f"Du wurdest zu {stage} von {stage.offboarding_id} hinzugefügt",
                    verb_es=f"Has sido añadido a {stage} de {stage.offboarding_id}",
                    verb_fr=f"Vous avez été ajouté à {stage} de {stage.offboarding_id}",
                    redirect=reverse("offboarding-pipeline"),
                    icon="information",
                )
            return HorillaRedirect(request)

    return render(request, "offboarding/employee/form.html", {"form": form})


@login_required
@permission_required("offboarding.delete_offboardingemployee")
def delete_employee(request):
    """
    This method is used to delete the offboarding employee
    """
    employee_ids = request.GET.getlist("employee_ids")
    instances = OffboardingEmployee.objects.filter(id__in=employee_ids)
    if instances:
        instances.delete()
        messages.success(request, _("Offboarding employee deleted"))
        notify.send(
            request.user.employee_get,
            recipient=HorillaUser.objects.filter(
                id__in=instances.values_list("employee_id__employee_user_id", flat=True)
            ),
            verb=f"You have been removed from the offboarding",
            verb_ar=f"لقد تمت إزالتك من إنهاء الخدمة",
            verb_de=f"Du wurdest aus dem Offboarding entfernt",
            verb_es=f"Has sido eliminado del offboarding",
            verb_fr=f"Vous avez été retiré de l'offboarding",
            redirect=reverse("offboarding-pipeline"),
            icon="information",
        )
    else:
        messages.error(request, _("Employees not found"))
    return redirect(filter_pipeline)


@login_required
@permission_required("offboarding.delete_offboardingstage")
def delete_stage(request):
    """
    This method  is used to delete the offboarding stage
    """
    ids = request.GET.getlist("ids")
    try:
        instances = OffboardingStage.objects.filter(id__in=ids)
        if instances:
            instances.delete()
            messages.success(request, _("Stage deleted"))
        else:
            messages.error(request, _("Stage not found"))
    except OverflowError:
        messages.error(request, _("Stage not found"))
    return HorillaRedirect(request)


def _blocked_required_tasks_message(employees, stage):
    """
    Returns an error message if moving any of ``employees`` forward to
    ``stage`` is blocked by required tasks that are not yet completed in
    their current stage. Returns None if the move is allowed.
    """
    if stage.sequence is None:
        return None
    blocked_lines = []
    for employee in employees:
        current_stage = employee.stage_id
        if not current_stage or current_stage.sequence is None:
            continue
        pending_tasks = employee.pending_required_tasks(current_stage)
        if pending_tasks.exists():
            task_titles = ", ".join(pending_tasks.values_list("title", flat=True))
            blocked_lines.append(f"{employee}: {task_titles}")
    if not blocked_lines:
        return None
    return str(
        _(
            "Complete the following required task(s) before moving to "
            "the next stage: %(details)s"
        )
        % {"details": "; ".join(blocked_lines)}
    )


def _swal_error_script(message):
    """
    A SweetAlert2 error script snippet for the given message.
    """
    return (
        "<script>Swal.fire({"
        f"icon: 'error', title: {json.dumps(str(_('Cannot Change Stage')))}, "
        f"text: {json.dumps(message)}"
        "});</script>"
    )


@login_required
@hx_request_required
@any_manager_can_enter("offboarding.change_offboarding")
def change_stage(request):
    """
    This method is used to update the stages of the employee
    """
    employee_ids = request.GET.getlist("employee_ids")
    stage_id = request.GET["stage_id"]
    employees = OffboardingEmployee.objects.filter(id__in=employee_ids)
    stage = OffboardingStage.objects.get(id=stage_id)

    blocked_message = _blocked_required_tasks_message(employees, stage)
    if blocked_message:
        stage_forms = {}
        stage_forms[str(stage.offboarding_id.id)] = StageSelectForm(
            offboarding=stage.offboarding_id
        )
        groups = pipeline_grouper({}, [stage.offboarding_id])
        for item in groups:
            setattr(item["offboarding"], "stages", item["stages"])
        response = render(
            request,
            "offboarding/stage/offboarding_body.html",
            {
                "offboarding": groups[0],
                "stage_forms": stage_forms,
                "today": datetime.today().date(),
            },
        )
        response.content += _swal_error_script(blocked_message).encode()
        return response

    # This wont trigger the save method inside the offboarding employee
    # employees.update(stage_id=stage)
    for employee in employees:
        employee.stage_id = stage
        employee.save()

    target_state = False if stage.type == "archived" else True
    employee_ids = employees.values_list("employee_id__id", flat=True)
    Employee.objects.filter(
        id__in=employee_ids,
        is_active=not target_state,  # Only update if is_active differs
    ).update(is_active=target_state)

    stage_forms = {}
    stage_forms[str(stage.offboarding_id.id)] = StageSelectForm(
        offboarding=stage.offboarding_id
    )
    notify.send(
        request.user.employee_get,
        recipient=HorillaUser.objects.filter(
            id__in=employees.values_list("employee_id__employee_user_id", flat=True)
        ),
        verb=f"Offboarding stage has been changed",
        verb_ar=f"تم تغيير مرحلة إنهاء الخدمة",
        verb_de=f"Die Offboarding-Stufe wurde geändert",
        verb_es=f"Se ha cambiado la etapa de offboarding",
        verb_fr=f"L'étape d'offboarding a été changée",
        redirect=reverse("offboarding-pipeline"),
        icon="information",
    )
    groups = pipeline_grouper({}, [stage.offboarding_id])
    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])
    return render(
        request,
        "offboarding/stage/offboarding_body.html",
        {
            "offboarding": groups[0],
            "stage_forms": stage_forms,
            "response_message": _("stage changed successfully."),
            "today": datetime.today().date(),
        },
    )


@login_required
@hx_request_required
@any_manager_can_enter("offboarding.change_offboarding")
def change_offboarding_stage(request):
    """
    This method is used to update the stages of the employee
    """
    employee_ids = request.GET.getlist("employee_ids")
    stage_id = request.GET["stage_id"]
    employees = OffboardingEmployee.objects.filter(id__in=employee_ids)
    stage = OffboardingStage.objects.get(id=stage_id)

    blocked_message = _blocked_required_tasks_message(employees, stage)
    if blocked_message:
        return HorillaFormView.HttpResponse(
            script=(
                "Swal.fire({"
                f"icon: 'error', title: {json.dumps(str(_('Cannot Change Stage')))}, "
                f"text: {json.dumps(blocked_message)}"
                "});"
            )
        )

    # This wont trigger the save method inside the offboarding employee
    # employees.update(stage_id=stage)
    for employee in employees:
        employee.stage_id = stage
        employee.save()
    if stage.type == "archived":
        Employee.objects.filter(
            id__in=employees.values_list("employee_id__id", flat=True)
        ).update(is_active=False)
    stage_forms = {}
    stage_forms[str(stage.offboarding_id.id)] = StageSelectForm(
        offboarding=stage.offboarding_id
    )
    notify.send(
        request.user.employee_get,
        recipient=HorillaUser.objects.filter(
            id__in=employees.values_list("employee_id__employee_user_id", flat=True)
        ),
        verb=f"Offboarding stage has been changed",
        verb_ar=f"تم تغيير مرحلة إنهاء الخدمة",
        verb_de=f"Die Offboarding-Stufe wurde geändert",
        verb_es=f"Se ha cambiado la etapa de offboarding",
        verb_fr=f"L'étape d'offboarding a été changée",
        redirect=reverse("offboarding-pipeline"),
        icon="information",
    )
    groups = pipeline_grouper({}, [stage.offboarding_id])
    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])

    return HorillaFormView.HttpResponse()


@login_required
@hx_request_required
@owner_can_enter("view_offboardingnote", OffboardingNote)
@any_manager_can_enter(
    "offboarding.view_offboardingnote", offboarding_employee_can_enter=True
)
def view_notes(request, employee_id=None):
    """
    This method is used to render all the notes of the employee
    """
    if request.FILES:
        files = request.FILES.getlist("files")
        note_id = request.GET["note_id"]
        note = OffboardingNote.objects.get(id=note_id)
        attachments = []
        for file in files:
            attachment = OffboardingStageMultipleFile()
            attachment.attachment = file
            attachment.save()
            attachments.append(attachment)
        note.attachments.add(*attachments)
    offboarding_employee_id = employee_id
    employee = OffboardingEmployee.objects.get(id=offboarding_employee_id)

    return render(
        request,
        "offboarding/note/view_notes.html",
        {
            "employee": employee,
        },
    )


@login_required
@owner_can_enter("add_offboardingnote", OffboardingNote)
# @any_manager_can_enter("offboarding.add_offboardingnote")
def add_note(request):
    """
    This method is used to create note for the offboarding employee
    """
    employee_id = request.GET.get("employee_id")
    if not employee_id:
        return HorillaRedirect(request, message=_("Missing required parameter."))
    employee = OffboardingEmployee.find(employee_id)
    if not employee:
        return HorillaRedirect(request, message=_("Employee not found."))
    form = NoteForm()
    if request.method == "POST":
        form = NoteForm(request.POST, request.FILES)
        form.instance.employee_id = employee
        if form.is_valid():
            form.save()
            messages.success(request, _("Note added successfully"))
            return redirect("view-offboarding-note", employee_id=employee.id)
    return render(
        request,
        "offboarding/note/view_notes.html",
        {
            "form": form,
            "employee": employee,
        },
    )


@login_required
@manager_can_enter(perm="offboarding.delete_offboardingnote")
def offboarding_note_delete(request, note_id):
    """
    This method is used to delete the offboarding note
    """
    script = ""
    try:
        note = OffboardingNote.objects.get(id=note_id)
        note.delete()
        messages.success(request, _("The note has been successfully deleted."))
    except OffboardingNote.DoesNotExist:
        return HorillaRedirect(request, message=_("Note not found."))
    return HttpResponse(script)


@login_required
@hx_request_required
@permission_required("offboarding.delete_offboardingnote")
def delete_attachment(request):
    """
    Used to delete attachment
    """
    script = ""
    ids = request.GET.getlist("ids")
    OffboardingStageMultipleFile.objects.filter(id__in=ids).delete()
    messages.success(request, _("File deleted successfully"))
    return HttpResponse(script)


@login_required
@offboarding_or_stage_manager_can_enter("offboarding.add_offboardingtask")
def add_task(request):
    """
    This method is used to add offboarding tasks
    """
    stage_id = request.GET.get("stage_id")
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    employees = OffboardingEmployee.objects.filter(stage_id=stage_id)
    instance = None
    if instance_id:
        instance = OffboardingTask.objects.filter(id=instance_id).first()
    form = TaskForm(
        initial={
            "stage_id": stage_id,
            "tasks_to": employees,
        },
        instance=instance,
    )
    if request.method == "POST":
        form = TaskForm(
            request.POST,
            instance=instance,
            initial={
                "stage_id": stage_id,
            },
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Task Added"))
    return render(
        request,
        "offboarding/task/form.html",
        {
            "form": form,
        },
    )


@login_required
@any_manager_can_enter(
    "offboarding.change_employeetask", offboarding_employee_can_enter=True
)
def update_task_status(request, *args, **kwargs):
    """
    This method is used to update the assigned tasks status
    """
    stage_id = request.GET.get("stage_id")
    employee_ids = request.GET.getlist("employee_ids")
    task_id = request.GET.get("task_id")
    status = request.GET.get("task_status")
    if not task_id or not status or not stage_id or not employee_ids:
        return HorillaRedirect(request, message=_("Missing required parameters."))
    employee_task = EmployeeTask.objects.filter(
        employee_id__id__in=employee_ids, task_id__id=task_id
    )
    employee_task.update(status=status)
    messages.success(request, _("Task status updated successfully..."))
    notify.send(
        request.user.employee_get,
        recipient=HorillaUser.objects.filter(
            id__in=employee_task.values_list(
                "task_id__managers__employee_user_id", flat=True
            )
        ),
        verb=f"Offboarding Task status has been updated",
        verb_ar=f"تم تحديث حالة مهمة إنهاء الخدمة",
        verb_de=f"Der Status der Offboarding-Aufgabe wurde aktualisiert",
        verb_es=f"Se ha actualizado el estado de la tarea de offboarding",
        verb_fr=f"Le statut de la tâche d'offboarding a été mis à jour",
        redirect=reverse("offboarding-pipeline"),
        icon="information",
    )
    stage = OffboardingStage.find(stage_id)
    if not stage:
        return HorillaRedirect(request, message=_("Stage not found"))
    stage_forms = {}
    stage_forms[str(stage.offboarding_id.id)] = StageSelectForm(
        offboarding=stage.offboarding_id
    )
    groups = pipeline_grouper({}, [stage.offboarding_id])
    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])
    return render(
        request,
        "offboarding/stage/offboarding_body.html",
        {
            "offboarding": groups[0],
            "stage_forms": stage_forms,
            "response_message": _("Task status changed successfully."),
        },
    )


@login_required
@any_manager_can_enter("offboarding.add_employeetask")
def task_assign(request):
    """
    This method is used to assign task to employees
    """
    employee_ids = request.GET.getlist("employee_ids")
    task_id = request.GET.get("task_id")
    employees = OffboardingEmployee.objects.filter(id__in=employee_ids)
    task = OffboardingTask.find(task_id)
    if not task:
        return HorillaRedirect(request, message=_("Task not found"))
    failed = []
    for employee in employees:
        try:
            assigned_task = EmployeeTask()
            assigned_task.employee_id = employee
            assigned_task.task_id = task
            assigned_task.save()
        except (IntegrityError, ValidationError) as error:
            # The employee already has this task, or the row fails model
            # validation. Skipping that employee is right, but this was a
            # bare except inside the loop, so every other failure was also
            # silent and the caller still saw a success page.
            failed.append(employee)
            logger.warning(
                "task %s not assigned to %s: %s", task.pk, employee.pk, error
            )
    if failed:
        messages.warning(
            request,
            _("Task could not be assigned to %(count)s employee(s).")
            % {"count": len(failed)},
        )
    offboarding = employees.first().stage_id.offboarding_id
    stage_forms = {}
    stage_forms[str(offboarding.id)] = StageSelectForm(offboarding=offboarding)
    groups = pipeline_grouper({}, [task.stage_id.offboarding_id])
    for item in groups:
        setattr(item["offboarding"], "stages", item["stages"])
    return render(
        request,
        "offboarding/stage/offboarding_body.html",
        {
            "offboarding": groups[0],
            "stage_forms": stage_forms,
            "response_message": _("Task Assigned"),
            "today": datetime.today().date(),
        },
    )


@login_required
@offboarding_or_stage_manager_can_enter("offboarding.delete_offboardingtask")
def delete_task(request):
    """
    This method is used to delete the task
    """
    task_ids = request.GET.getlist("task_ids")
    tasks = OffboardingTask.objects.filter(id__in=task_ids)
    if tasks:
        tasks.delete()
        messages.success(request, _("Task deleted"))
    else:
        messages.error(request, _("Task not found"))
    return redirect(filter_pipeline)


@login_required
@hx_request_required
@owner_can_enter("view_employeetask", EmployeeTask)
def offboarding_individual_view(request, emp_id):
    """
    This method is used to get the individual view of the offboarding employees
    parameters:
        emp_id(int): the id of the offboarding employee
    """
    employee = OffboardingEmployee.objects.get(id=emp_id)
    tasks = EmployeeTask.objects.filter(employee_id=emp_id)
    stage_forms = {}
    offboarding_stages = OffboardingStage.objects.filter(
        offboarding_id=employee.stage_id.offboarding_id
    )
    stage_forms[str(employee.stage_id.offboarding_id.id)] = StageSelectForm(
        offboarding=employee.stage_id.offboarding_id
    )
    context = {
        "employee": employee,
        "tasks": tasks,
        "choices": EmployeeTask.statuses,
        "offboarding_stages": offboarding_stages,
        "stage_forms": stage_forms,
    }

    requests_ids_json = request.GET.get("requests_ids")
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, emp_id)
        context["requests_ids"] = requests_ids_json
        context["previous"] = previous_id
        context["next"] = next_id
    return render(request, "offboarding/pipeline/individual_view.html", context)


@login_required
@permission_required("offboarding.view_resignationletter")
@check_feature_enabled("resignation_request")
def request_view(request):
    """
    This method is used to view the resignation request
    """
    default_filter = {"status": "requested"}
    filter_instance = LetterFilter(default_filter)
    letters = ResignationLetter.objects.all()
    offboardings = Offboarding.objects.all()

    return render(
        request,
        "offboarding/resignation/requests_view.html",
        {
            "letters": paginator_qry(letters, request.GET.get("page")),
            "f": filter_instance,
            "filter_dict": {"status": ["Requested"]},
            "offboardings": offboardings,
            "gp_fields": LetterReGroup.fields,
        },
    )


@login_required
@owner_can_enter("view_resignationletter", ResignationLetter)
@permission_required("offboarding.view_resignationletter")
def request_single_view(request, id):
    letter = ResignationLetter.find(id)
    if not letter:
        return HorillaRedirect(request, message=_("Resignation letter not found"))
    context = {
        "letter": letter,
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
        "offboarding/resignation/request_single_view.html",
        context,
    )


@login_required
@hx_request_required
@check_feature_enabled("resignation_request")
def search_resignation_request(request):
    """
    This method is used to search/filter the letter
    """
    if request.user.has_perm("offboarding.view_resignationletter"):
        letters = LetterFilter(request.GET).qs
    else:
        letters = ResignationLetter.objects.filter(
            employee_id__employee_user_id=request.user
        )
    field = request.GET.get("field")
    data_dict = parse_qs(request.GET.urlencode())
    template = "offboarding/resignation/request_cards.html"
    if request.GET.get("view") == "list":
        template = "offboarding/resignation/request_list.html"

    if request.GET.get("sortby"):
        letters = sortby(request, letters, "sortby")
        data_dict.pop("sortby")

    if field != "" and field is not None:
        letters = group_by(letters, field, request.GET.get("page"), "page")
        list_values = [entry["list"] for entry in letters]
        id_list = []
        for value in list_values:
            for instance in value.object_list:
                id_list.append(instance.id)

        requests_ids = json.dumps(list(id_list))
        template = "offboarding/resignation/group_by.html"

    else:
        letters = paginator_qry(letters, request.GET.get("page"))
        requests_ids = json.dumps([instance.id for instance in letters.object_list])

    if request.GET.get("view"):
        data_dict.pop("view")
    pagination = (
        False
        if request.META.get("HTTP_REFERER")
        and request.META.get("HTTP_REFERER").endswith("employee-profile/")
        else True
    )
    return render(
        request,
        template,
        {
            "letters": letters,
            "filter_dict": data_dict,
            "pd": request.GET.urlencode(),
            "pagination": pagination,
            "requests_ids": requests_ids,
            "field": field,
        },
    )


@login_required
@hx_request_required
@check_feature_enabled("resignation_request")
def resignation_tab(request, pk):

    letters = ResignationLetter.objects.filter(employee_id=pk)
    employee = Employee.objects.get(id=pk)
    return render(
        request,
        "cbv/resignation/resignation_tab.html",
        {"letters": letters, "employee": employee},
    )


def resignation_list_swap_response(original_request):
    """
    Render the resignation list CBV fragment for hx-target=\"#listContainer\" swaps.
    Subrequest keeps session (Horilla CACHE filters) without relying on client-side JS reload.
    """
    from django.test import RequestFactory

    from offboarding.cbv.resignation import ResignationListView

    list_path = reverse("list-resignation-request")
    qs = ""
    hx_cur = original_request.headers.get("HX-Current-URL", "")
    if hx_cur:
        p = urlparse(hx_cur)
        if "list-resignation-requests" in (p.path or ""):
            qs = p.query or ""

    try:
        rf = RequestFactory()
        path = f"{list_path}?{qs}" if qs else list_path
        sub = rf.get(
            path,
            HTTP_HX_REQUEST="true",
            HTTP_COOKIE=original_request.META.get("HTTP_COOKIE", ""),
            HTTP_HOST=original_request.META.get("HTTP_HOST", ""),
        )
        sub.user = getattr(original_request, "user", None)
        sub.session = original_request.session
        resp = ResignationListView.as_view()(sub)
        if hasattr(resp, "render") and callable(resp.render):
            resp = resp.render()
        return resp
    except Exception:
        return HttpResponse(" ", content_type="text/html")


@login_required
@check_feature_enabled("resignation_request")
def delete_resignation_request(request):
    """
    This method is used to delete resignation letter instance
    """
    ids = request.GET.getlist("letter_ids")
    if request.user.has_perm("offboarding.delete_resignationletter"):
        ResignationLetter.objects.filter(id__in=ids).delete()
    else:
        ResignationLetter.objects.filter(
            id__in=ids, employee_id__employee_user_id=request.user
        ).delete()
    messages.success(request, _("Resignation letter deleted"))
    if request.META.get("HTTP_REFERER") and request.META.get("HTTP_REFERER").endswith(
        "employee-profile/"
    ):
        return redirect("/employee/employee-profile/")
    if request.headers.get("HX-Request"):
        return resignation_list_swap_response(request)
    return redirect("resignation-request-view")


@login_required
@hx_request_required
def create_resignation_request(request):
    """
    This method is used to render form to create resignation requests
    """
    Selected_company = request.session.get("selected_company")
    company_id = None
    if Selected_company and Selected_company != "all":
        company_id = Selected_company
        general_setting = OffboardingGeneralSetting.objects.filter(
            company_id=company_id
        ).first()
    else:
        general_setting = OffboardingGeneralSetting.objects.filter(
            company_id__isnull=True
        ).first()
    feature_enabled = getattr(general_setting, "resignation_request", False)
    if not feature_enabled and not request.user.is_superuser:
        can_create = False
    else:
        can_create = (
            feature_enabled
            or request.user.is_superuser
            or request.user.has_perm("offboarding.add_resignationletter")
        )
    if not can_create:
        messages.info(request, _("Feature is not enabled on the settings"))
        return render(request, "decorator_404.html")
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    if instance_id:
        instance = ResignationLetter.objects.get(id=instance_id)
        if instance.status == "rejected":
            messages.error(
                request,
                _(
                    "A rejected resignation letter cannot be modified. Only deletion is allowed."
                ),
            )
            return HorillaRedirect(request)
        if not (
            request.user.has_perm("offboarding.change_resignationletter")
            or instance.employee_id == request.user.employee_get
        ):
            return render(request, "no_perm.html")
    form = ResignationLetterForm(instance=instance)
    if request.method == "POST":
        form = ResignationLetterForm(request.POST, instance=instance)
        if form.is_valid():
            if form.save() is not None:
                messages.success(request, _("Resignation letter saved"))
            return HorillaRedirect(request)

    return render(request, "offboarding/resignation/form.html", {"form": form})


@login_required
@check_feature_enabled("resignation_request")
@permission_required("offboarding.change_resignationletter")
def update_status(request):
    """
    This method is used to update the status of resignation letter
    """
    ids = request.GET.getlist("letter_ids")
    status = request.GET.get("status")
    employee_id = request.GET.get("employee_id")
    offboarding_id = request.GET.get("offboarding_id")
    contract_notice_end_date = (
        get_horilla_model_class(app_label="payroll", model="contract")
        .objects.filter(employee_id=employee_id, contract_status="active")
        .first()
        if apps.is_installed("payroll")
        else None
    )

    if offboarding_id:
        offboarding = Offboarding.objects.get(id=offboarding_id)
        notice_period_starts = request.GET.get("notice_period_starts")
        notice_period_ends = request.GET.get("notice_period_ends", None)
        if notice_period_starts:
            notice_period_starts = datetime.strptime(
                notice_period_starts, "%Y-%m-%d"
            ).date()
        today = datetime.today()
        if notice_period_ends:
            notice_period_ends = datetime.strptime(
                notice_period_ends, "%Y-%m-%d"
            ).date()
        else:
            if contract_notice_end_date:
                notice_period_ends = notice_period_starts + timedelta(
                    days=contract_notice_end_date.notice_period_in_days
                )
            else:
                notice_period_ends = None

        if not notice_period_starts:
            notice_period_starts = today

    letters = ResignationLetter.objects.filter(id__in=ids)
    # if use update method instead of save then save method will not trigger
    if status in ["approved", "rejected"]:
        for letter in letters:
            if letter.status == "rejected":
                messages.error(
                    request,
                    _(
                        "%(name)s's resignation letter is already rejected and cannot be modified."
                    )
                    % {"name": letter.employee_id.get_full_name()},
                )
                continue
            letter.status = status
            letter.save()
            if status == "approved":
                letter.to_offboarding_employee(
                    offboarding, notice_period_starts, notice_period_ends
                )
            messages.success(
                request,
                _("Resignation request has been %(status)s")
                % {"status": letter.get_status_display()},
            )
            notify.send(
                request.user.employee_get,
                recipient=letter.employee_id.employee_user_id,
                verb=f"Resignation request has been {letter.get_status_display()}",
                verb_ar=f"تم {letter.get_status_display()} طلب الاستقالة",
                verb_de=f"Der Rücktrittsantrag wurde {letter.get_status_display()}",
                verb_es=f"La solicitud de renuncia ha sido {letter.get_status_display()}",
                verb_fr=f"La demande de démission a été {letter.get_status_display()}",
                redirect="#",
                icon="information",
            )
    if request.headers.get("HX-Request"):
        return resignation_list_swap_response(request)
    return redirect(reverse("resignation-request-view"))


@login_required
@hx_request_required
@permission_required("offboarding.add_offboardinggeneralsetting")
def enable_resignation_request(request):
    """
    Enable disable resignation letter feature
    """
    selected_company = request.session.get("selected_company")

    if selected_company and selected_company != "all":
        resignation_request_feature = OffboardingGeneralSetting.objects.filter(
            company_id=selected_company
        ).first()
        if not resignation_request_feature:
            resignation_request_feature = OffboardingGeneralSetting(
                company_id_id=selected_company
            )
    else:
        resignation_request_feature = OffboardingGeneralSetting.objects.first()
        if not resignation_request_feature:
            resignation_request_feature = OffboardingGeneralSetting()

    resignation_request_feature.resignation_request = (
        "resignation_request" in request.GET.keys()
    )
    resignation_request_feature.save()
    message_text = (
        "enabled" if resignation_request_feature.resignation_request else "disabled"
    )
    messages.success(
        request,
        _("Resignation Request setting has been {} successfully.").format(message_text),
    )
    if request.META.get("HTTP_HX_REQUEST"):
        return HttpResponse(
            """
                            <span hx-trigger="load"
                            hx-get="/"
                            hx-swap="outerHTML"
                            hx-select="#offboardingGenericNav"
                            hx-target="#offboardingGenericNav">
                            </span>
                            """
        )
    return redirect(general_settings)


@login_required
def offboarding_rules_settings_view(request):
    """
    Merged "Offboarding Rules" settings page that groups the Resignation
    Request toggle and the Notice Period setting under a single header. Each
    section reuses its existing toggle/save endpoint; the current state is
    provided by the global context processors (enabled_resignation_request and
    get_initial_notice_period).
    """
    return render(request, "offboarding/settings/offboarding_rules.html")


@login_required
@hx_request_required
@permission_required("offboarding.add_offboardingemployee")
def get_notice_period(request):
    """
    This method is used to get initial details for notice period
    """
    employee_id = request.GET.get("employee_id")
    if apps.is_installed("payroll"):
        Contract = get_horilla_model_class(app_label="payroll", model="contract")
        employee_contract = (
            (
                Contract.objects.order_by("-id")
                .filter(employee_id__id=employee_id)
                .first()
            )
            if Contract.objects.filter(
                employee_id__id=employee_id, contract_status="active"
            ).first()
            else Contract.objects.filter(
                employee_id__id=employee_id, contract_status="active"
            ).first()
        )
    else:
        employee_contract = None

    response = {
        "notice_period": intial_notice_period(request)["get_initial_notice_period"],
        "unit": "month",
        "notice_period_starts": str(datetime.today().date()),
    }
    if employee_contract:
        response["notice_period"] = employee_contract.notice_period_in_days
    return JsonResponse(response)


@login_required
@hx_request_required
def get_notice_period_end_date(request):
    """
    Calculates and returns the end date of the notice period based on the provided start date.
    """
    start_date = request.GET.get("start_date")
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        start_date = datetime.today().date()
    notice_period = intial_notice_period(request)["get_initial_notice_period"]
    end_date = start_date + timedelta(days=notice_period)
    response = {
        "end_date": end_date,
    }
    return JsonResponse(response)


@login_required
@any_manager_can_enter(
    perm=[
        "offboarding.view_offboarding",
        "offboarding.view_offboardingtask",
        "offboarding.view_offboardingemployee",
    ]
)
def offboarding_dashboard(request):
    """
    This method is used to render the offboarding dashboard page.
    """

    onboarding_employees = []
    if apps.is_installed("recruitment"):
        Candidate = get_horilla_model_class("recruitment", "candidate")
        onboarding_employees = Candidate.objects.filter(
            onboarding_stage__isnull=False, converted_employee_id__isnull=True
        )

    employees = Employee.objects.entire()
    offboarding_employees = OffboardingEmployee.objects.entire()
    archived_employees = offboarding_employees.filter(stage_id__type="archived")
    resigning_employees = employees.filter(resignationletter__isnull=False).exclude(
        offboardingemployee__stage_id__type="archived"
    )

    exit_ratio = (
        (archived_employees.count() / employees.count()) if employees.count() > 0 else 0
    )

    context = {
        "exit_ratio": round(exit_ratio, 4),
        "employees": employees,
        "archived_employees": archived_employees,
        "resigning_employees": resigning_employees,
        "onboarding_employees": len(onboarding_employees),
    }
    return render(request, "offboarding/dashboard/dashboard.html", context)


@login_required
@hx_request_required
@any_manager_can_enter(
    ["offboarding.view_offboarding", "offboarding.view_offboardingtask"]
)
def dashboard_task_table(request):
    """
    This method is used to render the employee task table page in the dashboard.
    """

    employees = OffboardingEmployee.objects.entire()
    return render(
        request,
        "offboarding/dashboard/employee_task_table.html",
        {
            "employees": employees,
        },
    )


if apps.is_installed("asset"):

    @login_required
    @hx_request_required
    @any_manager_can_enter(["offboarding.view_offboarding"])
    def dashboard_asset_table(request):
        """
        This method is used to render the employee assets table page in the dashboard.
        """
        AssetAssignment = get_horilla_model_class(
            app_label="asset", model="assetassignment"
        )

        offboarding_employees = OffboardingEmployee.objects.entire().values_list(
            "employee_id__id", flat=True
        )
        assets = AssetAssignment.objects.entire().filter(
            return_status__isnull=True,
            assigned_to_employee_id__in=offboarding_employees,
        )
        return render(
            request,
            "offboarding/dashboard/asset_returned_table.html",
            {"assets": assets},
        )


if apps.is_installed("pms"):

    @login_required
    @hx_request_required
    @any_manager_can_enter("offboarding.view_offboarding")
    def dashboard_feedback_table(request):
        """
        This method is used to render the employee assets table page in the dashboard.
        """

        Feedback = get_horilla_model_class(app_label="pms", model="feedback")

        offboarding_employees = OffboardingEmployee.objects.entire().values_list(
            "employee_id__id", "notice_period_starts"
        )

        if offboarding_employees:
            id_list, date_list = map(list, zip(*offboarding_employees))
        else:
            id_list, date_list = [], []

        feedbacks = (
            Feedback.objects.entire()
            .filter(employee_id__in=id_list)
            .exclude(status="Closed")
        )
        return render(
            request,
            "offboarding/dashboard/employee_feedback_table.html",
            {"feedbacks": feedbacks},
        )


@login_required
@any_manager_can_enter("offboarding.view_offboarding")
def dashboard_join_chart(request):
    """
    This method is used to render the joining - offboarding chart.
    """

    employees = Employee.objects.entire()
    offboarding_employees = OffboardingEmployee.objects.entire()
    archived_employees = offboarding_employees.filter(stage_id__type="archived")
    resigning_employees = employees.filter(resignationletter__isnull=False).exclude(
        offboardingemployee__stage_id__type="archived"
    )

    labels = ["resigning", "archived"]
    items = [
        resigning_employees.count(),
        archived_employees.count(),
    ]
    if apps.is_installed("recruitment"):
        Candidate = get_horilla_model_class(app_label="recruitment", model="candidate")
        onboarding_employees = Candidate.objects.filter(
            onboarding_stage__isnull=False, converted_employee_id__isnull=True
        )
        labels.append("New")
        items.append(onboarding_employees.count())

    response = {
        "labels": labels,
        "items": items,
    }
    return JsonResponse(response)


@login_required
@any_manager_can_enter("offboarding.view_offboarding")
def department_job_postion_chart(request):
    """
    This method is used to render the department - job position chart.
    """

    departments = Department.objects.all()
    offboarding_employees = OffboardingEmployee.objects.entire()

    selected_departments = [
        dept
        for dept in departments
        if offboarding_employees.filter(
            employee_id__employee_work_info__department_id=dept.id
        ).exists()
    ]

    job_positions = JobPosition.objects.filter(
        id__in=offboarding_employees.values(
            "employee_id__employee_work_info__job_position_id"
        ).distinct()
    )

    labels = [dept.department for dept in selected_departments]

    datasets = []
    for job in job_positions:
        job_dept = job.department_id
        if job_dept not in selected_departments:
            continue

        data = [0] * len(selected_departments)
        dept_index = labels.index(job_dept.department)

        count = offboarding_employees.filter(
            employee_id__employee_work_info__job_position_id=job.id
        ).count()
        data[dept_index] = count

        datasets.append(
            {
                "label": f"{job.job_position} ({job_dept.department})",
                "data": data,
                "backgroundColor": f"hsl({hash(job.job_position) % 360}, 70%, 50%, 0.6)",
            }
        )

    return JsonResponse({"labels": labels, "datasets": datasets})
