"""
views.py

This module contains the view functions for handling HTTP requests and rendering
responses in pms app.
"""

import datetime
import json
import logging
from itertools import tee
from urllib.parse import parse_qs, urlencode, urlparse

from dateutil.relativedelta import relativedelta
from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.db.utils import IntegrityError
from django.forms import modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from base.methods import (
    closest_numbers,
    eval_validate,
    filtersubordinatesemployeemodel,
    get_key_instances,
    get_pagination,
    is_reportingmanager,
    paginator_qry,
    sortby,
)
from base.models import Company
from employee.models import Employee, EmployeeWorkInformation
from horilla.decorators import (
    check_manager,
    hx_request_required,
    login_required,
    manager_can_enter,
    meeting_manager_can_enter,
    owner_can_enter,
    permission_required,
)
from horilla.group_by import group_by_queryset
from horilla.http.response import HorillaRedirect
from horilla.methods import handle_no_permission
from horilla_auth.models import HorillaUser
from horilla_automations.methods.methods import generate_choices
from horilla_automations.methods.serialize import serialize_form
from notifications.signals import notify
from pms.filters import (
    ActualKeyResultFilter,
    ActualObjectiveFilter,
    AnonymousFeedbackFilter,
    EmployeeObjectiveFilter,
    FeedbackFilter,
    KeyResultFilter,
    MeetingsFilter,
    ObjectiveFilter,
    ObjectiveReGroup,
)
from pms.forms import (
    AddAssigneesForm,
    AnonymousFeedbackForm,
    EmployeeKeyResultForm,
    EmployeeObjectiveCreateForm,
    EmployeeObjectiveForm,
    FeedbackForm,
    KeyResultForm,
    KRForm,
    MeetingsForm,
    ObjectiveCommentForm,
    ObjectiveForm,
    PeriodForm,
    QuestionForm,
    QuestionTemplateForm,
)
from pms.methods import (
    check_duplication,
    check_permission_feedback_detailed_view,
    get_anonymous_feedbacks,
    pms_owner_and_manager_can_enter,
)
from pms.models import (
    AnonymousFeedback,
    Answer,
    BonusPointSetting,
    Comment,
    EmployeeBonusPoint,
    EmployeeKeyResult,
    EmployeeObjective,
    Feedback,
    KeyResult,
    KeyResultFeedback,
    Meetings,
    MeetingsAnswer,
    Objective,
    Period,
    Question,
    QuestionOptions,
    QuestionTemplate,
)

logger = logging.getLogger(__name__)


# objectives
@login_required
def objective_list_view(request):
    """
    This view is used to show all the objectives  and returns some objects.
    Returns:
        Objects based on userlevel.
    """
    employee = request.user.employee_get
    template = "okr/okr_view.html"
    objective_own = EmployeeObjective.objects.filter(
        employee_id=employee, archive=False
    )
    objective_own = objective_own.distinct()
    context = objective_filter_pagination(request, objective_own)
    return render(request, template, context)


def obj_form_save(request, objective_form):
    """
    This view is used to save objective form
    """
    objective = objective_form.save()
    assignees = objective_form.cleaned_data["assignees"]
    start_date = objective_form.cleaned_data["start_date"]
    default_krs = objective_form.cleaned_data["key_result_id"]

    messages.success(request, _("Objective created"))
    if assignees:
        for emp in assignees:
            emp_objective = EmployeeObjective(
                objective_id=objective, employee_id=emp, start_date=start_date
            )
            emp_objective.save()
            # assigning default key result
            if default_krs:
                for key in default_krs:
                    emp_kr = EmployeeKeyResult(
                        employee_objective_id=emp_objective,
                        key_result_id=key,
                        progress_type=key.progress_type,
                        target_value=key.target_value,
                    )
                    emp_kr.save()
            notify.send(
                request.user.employee_get,
                recipient=emp.employee_user_id,
                verb="You got an OKR!.",
                verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                redirect=reverse(
                    "objective-detailed-view", kwargs={"obj_id": objective.id}
                ),
            )


@login_required
@permission_required(perm="pms.add_employeeobjective")
def objective_creation(request):
    """
    This view is for objective creation , and returns a objective form.
    Returns:
        GET:
            objective form, period, department, job position, employee, department
        POST:
            Objective created, and returns to key result creation function
    """
    employee = request.user.employee_get
    objective_form = ObjectiveForm(employee=employee)
    if request.GET.get("key_result_id") is not None:
        objective_form = ObjectiveForm(request.GET)

    if request.method == "POST":
        objective_form = ObjectiveForm(request.POST)
        if objective_form.is_valid():
            obj_form_save(request, objective_form)
            return HorillaRedirect(request)
    context = {
        "objective_form": objective_form,
        "p_form": PeriodForm(),
        "k_form": KRForm(),
    }
    return render(request, "okr/objective_creation.html", context=context)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.change_employeeobjective")
def objective_update(request, obj_id):
    """
    This view takes one arguments, id , and returns a HttpResponse object.,using htmx
    Args:
        id (int): Primary key of EmployeeObjective.
    Returns:
        A HttpResponse object with the content Form errors.
    """
    instance = Objective.objects.get(id=obj_id)
    objective_form = ObjectiveForm(instance=instance)
    if request.GET.get("key_result_id") is not None:
        objective_form = ObjectiveForm(request.GET)
    if request.method == "POST":
        objective_form = ObjectiveForm(request.POST, instance=instance)
        if objective_form.is_valid():
            objective = objective_form.save()
            assignees = objective_form.cleaned_data["assignees"]
            start_date = objective_form.cleaned_data["start_date"]
            default_krs = objective_form.cleaned_data["key_result_id"]
            new_emp = [assignee for assignee in assignees]

            delete_list = []
            if objective.employee_objective.exists():
                emp_objectives = objective.employee_objective.all()
                existing_emp = [emp.employee_id for emp in emp_objectives]
                delete_list = [
                    employee for employee in existing_emp if employee not in new_emp
                ]
            if len(delete_list) > 0:
                for emp in delete_list:
                    EmployeeObjective.objects.filter(
                        employee_id=emp, objective_id=objective
                    ).delete()
            for emp in new_emp:
                if EmployeeObjective.objects.filter(
                    employee_id=emp, objective_id=objective
                ).exists():
                    emp_obj = EmployeeObjective.objects.filter(
                        employee_id=emp, objective_id=objective
                    ).first()
                    emp_obj.start_date = start_date
                else:
                    emp_obj = EmployeeObjective(
                        employee_id=emp, objective_id=objective, start_date=start_date
                    )
                emp_obj.save()
                # assiging default key result
                if default_krs:
                    for key in default_krs:
                        if not EmployeeKeyResult.objects.filter(
                            employee_objective_id=emp_obj, key_result_id=key
                        ).exists():
                            emp_kr = EmployeeKeyResult.objects.create(
                                employee_objective_id=emp_obj,
                                key_result_id=key,
                                progress_type=key.progress_type,
                                target_value=key.target_value,
                            )
                            emp_kr.save()

                notify.send(
                    request.user.employee_get,
                    recipient=emp.employee_user_id,
                    verb="You got an OKR!.",
                    verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                    verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                    verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                    verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                    redirect=reverse(
                        "objective-detailed-view", kwargs={"obj_id": objective.id}
                    ),
                )
            messages.success(
                request,
                _("Objective %(objective)s Updated") % {"objective": instance},
            )
            return HorillaRedirect(request)
    context = {"objective_form": objective_form, "k_form": KRForm(), "update": True}

    return render(request, "okr/objective_creation.html", context)


# key result
@login_required
@permission_required("pms.view_keyresult")
def view_key_result(request):
    """
    This method is used render template to view all the key result instances
    """
    krs = KeyResult.objects.all()
    krs_filter = ActualKeyResultFilter(request.GET)
    krs = paginator_qry(krs, request.GET.get("page"))
    krs_ids = json.dumps([instance.id for instance in krs.object_list])
    context = {
        "krs": krs,
        "f": krs_filter,
        "krs_ids": krs_ids,
    }
    return render(request, "okr/key_result/view_kr.html", context)


@login_required
@hx_request_required
# @permission_required("pms.view_keyresult")
def filter_key_result(request):
    """
    Filter and retrieve a list of key results based on the provided query parameters.
    """
    query_string = request.GET.urlencode()
    krs = ActualKeyResultFilter(request.GET).qs
    template = "okr/key_result/kr_card.html"
    if request.GET.get("view") == "list":
        template = "okr/key_result/kr_list.html"
    krs = sortby(request, krs, "sortby")
    krs = paginator_qry(krs, request.GET.get("page"))
    allowance_ids = json.dumps([instance.id for instance in krs.object_list])
    data_dict = parse_qs(query_string)
    get_key_instances(KeyResult, data_dict)
    return render(
        request,
        template,
        {
            "krs": krs,
            "pd": query_string,
            "filter_dict": data_dict,
            "krs_ids": allowance_ids,
        },
    )


@login_required
@hx_request_required
@permission_required("pms.add_keyresult")
def key_result_create(request):
    """
    This method renders form and template to create key result
    """
    form = KRForm()
    redirect_url = request.GET.get("data")
    dataUrl = request.GET.get("dataUrl")
    if request.method == "POST":
        form = KRForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(
                request,
                _("Key result %(key_result)s created successfully")
                % {"key_result": instance},
            )
            mutable_get = request.GET.copy()

            key_result_ids = mutable_get.getlist("key_result_id", [])
            if "create_new_key_result" in key_result_ids:
                key_result_ids.remove("create_new_key_result")
            key_result_ids.append(str(instance.id))
            mutable_get.setlist("key_result_id", key_result_ids)
            data = mutable_get.urlencode()
            redirect_url = f"/pms/{dataUrl}{data}"
            parsed_url = urlparse(redirect_url)
            query_params = parse_qs(parsed_url.query)
            # Remove the 'dataUrl' parameter
            query_params.pop("dataUrl", None)
            # Reconstruct the URL without 'dataUrl'
            new_query_string = urlencode(query_params, doseq=True)
            redirect_url = f"{parsed_url.path}?{new_query_string}"
        else:
            redirect_url = request.GET.urlencode()

    return render(
        request,
        "okr/key_result/key_result_form.html",
        {"k_form": form, "redirect_url": redirect_url, "dataUrl": dataUrl},
    )


@login_required
@hx_request_required
@permission_required("pms.add_keyresult")
def kr_create_or_update(request, kr_id=None):
    """
    View function for creating or updating a Key Result.

    Parameters:
    - request: HttpRequest object.
    - kr_id: ID of the Key Result to update (optional).

    Returns:
    Renders a form to create or update a Key Result.
    """
    form = KRForm()
    kr = False
    key_result = False
    if kr_id is not None:
        key_result = KeyResult.objects.filter(id=kr_id).first()
        form = KRForm(instance=key_result)
    if request.method == "POST":
        if key_result:
            form = KRForm(request.POST, instance=key_result)
            if form.is_valid():
                instance = form.save()
                messages.success(
                    request,
                    _("Key result %(key_result)s updated successfully")
                    % {"key_result": instance},
                )
                return HorillaRedirect(request)

        else:
            form = KRForm(request.POST)
            if form.is_valid():
                instance = form.save()
                messages.success(
                    request,
                    _("Key result %(key_result)s created successfully")
                    % {"key_result": instance},
                )
                return HorillaRedirect(request)

    return render(request, "okr/key_result/real_kr_form.html", {"form": form})


@login_required
@permission_required("pms.change_keyresult")
def archive_key_result(request, pk):
    """
    This view is used to archive and unarchive the key result,
    Args:
        meet_id(int) : primarykey of the key result.
        employee_id(int) : primarykey of the employee
    Returns:
    """
    key_result = KeyResult.find(pk)
    if not key_result:
        return HorillaRedirect(
            request, message=_("No Key Result found matching the query.")
        )

    key_result.is_active = not key_result.is_active
    key_result.save()
    message = (
        _("Key reuslt unarchived successfully")
        if key_result.is_active
        else _("Key reuslt archived successfully")
    )
    messages.success(request, message)
    return HttpResponse("")


@login_required
@hx_request_required
def add_assignees(request, obj_id):
    """
    this function is used to add assigneesto the objective
        args:
            obj_id(int) : pimarykey of Objective
        return:
            redirect to add assignees form
    """
    objective = Objective.objects.get(id=obj_id)
    form = AddAssigneesForm(instance=objective)
    if request.method == "POST":
        form = AddAssigneesForm(request.POST, instance=objective)
        if form.is_valid():
            objective = form.save(commit=False)
            assignees = form.cleaned_data["assignees"]
            start_date = form.cleaned_data["start_date"]
            for emp in assignees:
                objective.assignees.add(emp)
                if not EmployeeObjective.objects.filter(
                    employee_id=emp, objective_id=objective
                ).exists():
                    emp_obj = EmployeeObjective(
                        employee_id=emp, objective_id=objective, start_date=start_date
                    )
                emp_obj.save()
                # assiging default key result
                default_krs = objective.key_result_id.all()
                if default_krs:
                    for key_result in default_krs:
                        if not EmployeeKeyResult.objects.filter(
                            employee_objective_id=emp_obj, key_result_id=key_result
                        ).exists():
                            emp_kr = EmployeeKeyResult.objects.create(
                                employee_objective_id=emp_obj,
                                key_result_id=key_result,
                                progress_type=key_result.progress_type,
                                target_value=key_result.target_value,
                                start_date=start_date,
                            )
                notify.send(
                    request.user.employee_get,
                    recipient=emp.employee_user_id,
                    verb="You got an OKR!.",
                    verb_ar="لقد حققت هدفًا ونتيجة رئيسية!",
                    verb_de="Du hast ein Ziel-Key-Ergebnis erreicht!",
                    verb_es="¡Has logrado un Resultado Clave de Objetivo!",
                    verb_fr="Vous avez atteint un Résultat Clé d'Objectif !",
                    redirect=reverse(
                        "objective-detailed-view", kwargs={"obj_id": objective.id}
                    ),
                )
            objective.save()
            messages.success(
                request,
                _("Objective %(objective)s Updated") % {"objective": objective},
            )
            return HorillaRedirect(request)

    context = {
        "form": form,
        "objective": objective,
    }
    return render(request, "okr/add_assignees.html", context)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.delete_employeeobjective")
def objective_delete(request, obj_id):
    """
    This view takes one arguments, id and returns redirecting to a view.
    Args:
        id (int) : primarykey of the EmployeeObjective.
    Returns:
        Redirect to Objective_list_view".
    """
    try:
        objective = Objective.objects.get(id=obj_id)
        if not objective.employee_objective.exists():
            objective.delete()
            messages.success(
                request,
                _("Objective %(objective)s deleted") % {"objective": objective},
            )
        else:
            messages.warning(
                request,
                _("You can't delete objective %(objective)s,related entries exists")
                % {"objective": objective},
            )
    except Objective.DoesNotExist:
        messages.error(request, _("No Objective found matching the query."))
    return HttpResponse(
        "<script> $('.reload-record').click(); $('#reloadMessagesButton').click();</script>"
    )


@login_required
@permission_required("pms.change_objective")
def objective_manager_remove(request, obj_id, manager_id):
    """
    Removes a manager from an objective.

    Parameters:
    - request: HttpRequest object.
    - obj_id: ID of the Objective from which to remove the manager.
    - manager_id: ID of the manager to be removed.

    Returns:
    HttpResponse indicating success.
    """
    objective = get_object_or_404(Objective, id=obj_id)
    objective.managers.remove(manager_id)
    messages.success(request, _("Manger removed successfully."))
    return HttpResponse(
        "<script> $('.reload-record').click(); $('#reloadMessagesButton').click();</script>"
    )


@login_required
@permission_required("pms.delete_keyresult")
def key_result_remove(request, obj_id, kr_id):
    """
    Removes a Key Result from an objective.

    Parameters:
    - request: HttpRequest object.
    - obj_id: ID of the Objective from which to remove the Key Result.
    - kr_id: ID of the Key Result to be removed.

    Returns:
    HttpResponse indicating success.
    """
    objective = get_object_or_404(Objective, id=obj_id)
    objective.key_result_id.remove(kr_id)
    messages.success(request, _("Key result removed successfully."))
    return HttpResponse(
        "<script> $('.reload-record').click(); $('#reloadMessagesButton').click();</script>"
    )


@login_required
@manager_can_enter("pms.delete_employeeobjective")
def assignees_remove(request, obj_id, emp_id):
    """
    Removes an assignee from an objective.

    Parameters:
    - request: HttpRequest object.
    - obj_id: ID of the Objective from which to remove the assignee.
    - emp_id: ID of the employee to be removed as an assignee.

    Returns:
    HttpResponse indicating success.
    """
    objective = get_object_or_404(Objective, id=obj_id)
    get_object_or_404(
        EmployeeObjective, employee_id=emp_id, objective_id=obj_id
    ).delete()
    objective.assignees.remove(emp_id)
    messages.success(request, _("Assignee removed successfully."))
    return HttpResponse(
        "<script>$('.reload-record').click();$('#reloadMessagesButton').click();</script>"
    )


def objective_filter_pagination(request, objective_own):
    """
    This view takes two arguments, all_objective,own_objecitve and returns some objects.
    Args:
        all_objective (queryset) : Queryset of objectives
        own_objective (queryset) : Queryset of objectives
    Returns:
        All the filtered and paginated object will return.
    """
    previous_data = request.GET.urlencode()
    initial_data = {"archive": False}  # set initial value of archive filter to False
    field = request.GET.get("field")

    objective_filter_own = ObjectiveFilter(
        request.GET or initial_data, queryset=objective_own
    ).qs.order_by("-id")

    employee = request.user.employee_get
    manager = False

    sub_employees = filtersubordinatesemployeemodel(
        request,
        queryset=Employee.objects.filter(is_active=True),
    )
    sub_obj_ids = (
        EmployeeObjective.objects.filter(employee_id__in=sub_employees)
        .values_list("objective_id", flat=True)
        .distinct()
    )

    objectives = Objective.objects.filter(
        Q(managers=employee) | Q(assignees=employee) | Q(id__in=sub_obj_ids)
    ).distinct()
    if request.user.has_perm("pms.view_objective"):
        objectives = Objective.objects.all()
        manager = True
    elif Objective.objects.filter(managers=employee).exists() or is_reportingmanager(
        request
    ):
        manager = True
    objectives = ActualObjectiveFilter(
        request.GET or initial_data, queryset=objectives
    ).qs
    objectives = Paginator(objectives, get_pagination())
    objective_paginator_own = Paginator(objective_filter_own, get_pagination())
    own_page = request.GET.get("page")
    all_page = request.GET.get("all_page")
    objectives_own = objective_paginator_own.get_page(own_page)
    objectives = objectives.get_page(all_page)

    now = datetime.datetime.now()
    data_dict = parse_qs(previous_data)
    get_key_instances(EmployeeObjective, data_dict)
    context = {
        "manager": manager,
        "superuser": "true",
        "objectives": objectives,
        "own_objectives": objectives_own,
        "objective_filer_form": ActualObjectiveFilter().form,
        "pg": previous_data,
        "current_date": now,
        "filter_dict": data_dict,
        "gp_fields": ObjectiveReGroup.fields,
        "field": field,
    }
    return context


@login_required
@hx_request_required
def objective_list_search(request):
    """
    This view is used to to search objective,  returns searched and filtered objects.
    Returns:
        All the filtered and searched object will based on userlevel.
    """
    search_val = request.GET.get("search")
    if search_val is None:
        search_val = ""
    employee = request.user.employee_get

    objective_own = EmployeeObjective.objects.filter(employee_id=employee)
    context = objective_filter_pagination(request, objective_own)
    template = "okr/okr_list.html"
    if request.GET.get("field") != "" and request.GET.get("field") is not None:
        template = "okr/group_by.html"
    return render(request, template, context)


@login_required
# @hx_request_required
def objective_dashboard_view(request):
    """
    This view is used to to search objective,  returns searched and filtered objects.
    Returns:
        All the filtered and searched object will based on userlevel.
    """
    emp_objectives = EmployeeObjectiveFilter(request.GET).qs
    return render(
        request,
        "okr/emp_objective/emp_objective_dashboard_view.html",
        {"emp_objectives": emp_objectives},
    )


def objective_history(emp_obj_id):
    """
    This view is used to get history of EmployeeObjective,  return objects.
    Args:
        id (int): Primarykey of EmployeeObjective.
    Returns:
        All the history of EmployeeObjective.
    """

    def pair_history(iterable):
        """this function return two history pair"""
        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)

    changed_key_results = []

    def key_result_history(key_result):
        """key result history"""
        key_result_iterator = (
            key_result.history.all().order_by("history_date").iterator()
        )
        for record_pair in pair_history(key_result_iterator):
            old_record, new_record = record_pair
            delta = new_record.diff_against(old_record)
            history_user_id = delta.new_record.history_user
            history_change_date = delta.new_record.history_date
            employee = Employee.objects.filter(employee_user_id=history_user_id).first()
            key_result = delta.new_record.key_result_id
            changed_key_results.append(
                {
                    "delta": delta,
                    "changed_user": employee,
                    "changed_date": history_change_date,
                    "k_r": key_result,
                }
            )

    obj_objective = EmployeeObjective.objects.get(id=emp_obj_id)
    all_key_results = EmployeeKeyResult.objects.filter(
        employee_objective_id=obj_objective
    )

    for key_result in all_key_results:
        # loop each key result and generate it's history
        key_result_history(key_result)
    changed_key_results.reverse()
    return changed_key_results


@login_required
def objective_detailed_view(request, obj_id, **kwargs):
    """
    this function is used to update the key result of objectives
        args:
            obj_id(int) : pimarykey of EmployeeObjective
        return:
            objects to objective_detailed_view
    """
    objective = Objective.find(obj_id)
    if not objective:
        return HorillaRedirect(
            request, message=_("No Objective found matching the query.")
        )

    emp_objectives = EmployeeObjective.objects.filter(
        objective_id=objective, archive=False
    )
    if not (
        request.user.employee_get in objective.managers.all()
        or request.user.has_perm("pms.view_employeeobjective")
        or emp_objectives.filter(employee_id=request.user.employee_get).exists()
    ):
        messages.info(request, _("You dont have permission."))
        return redirect("objective-list-view")

    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    now = datetime.datetime.now()
    context = {
        "emp_objectives": emp_objectives,
        "pd": previous_data,
        "filter_dict": data_dict,
        "objective": objective,
        "key_result_form": KeyResultForm,
        "objective_key_result_status": EmployeeKeyResult.STATUS_CHOICES,
        "comment_form": ObjectiveCommentForm,
        "current_date": now,
        "emp_obj_form": EmployeeObjectiveFilter(),
        "back_url": reverse("tab-objectives-view"),
        "objective_list_url": reverse("objective-list-view"),
    }
    if request.headers.get("HX-Request"):
        return render(request, "okr/okr_detailed_view_fragment.html", context)
    return render(request, "okr/okr_detailed_view.html", context)


@login_required
@hx_request_required
def objective_detailed_view_activity(request, id):
    """
    This view is used to show objective activity template ,using htmx
    Args:
        id (int): Primary key of EmployeeObjective.
    Returns:
        it will return history,comment object to objective_detailed_view_activity.
    """

    objective = EmployeeObjective.objects.get(id=id)
    if (
        request.user.employee_get == objective.employee_id
        or request.user.employee_get in objective.objective_id.managers.all()
        or request.user.has_perm("pms.view_comment")
    ):
        key_result_history = objective_history(id)
        history = objective.tracking()
        comments = Comment.objects.filter(employee_objective_id=objective)
        activity_list = []
        for hist in history:
            hist["date"] = hist["pair"][0].history_date
            activity_list.append(hist)
        for com in comments:
            comment = {
                "type": "comment",
                "comment": com,
                "date": com.created_at,
            }
            activity_list.append(comment)

        for key in key_result_history:
            key_result = {
                "type": "key_result",
                "key_result": key,
                "date": key["changed_date"],
            }
            activity_list.append(key_result)

        activity_list = sorted(activity_list, key=lambda x: x["date"], reverse=True)

        context = {
            "objective": objective,
            "historys": history,
            "comments": comments,
            "activity_list": activity_list,
        }
        return render(request, "okr/objective_detailed_view_activity.html", context)
    else:
        messages.info(request, _("You dont have permission."))
        return HorillaRedirect(request)


@login_required
@hx_request_required
def objective_detailed_view_comment(request, id):
    """
    This view is used to create comment object for objective activity, using htmx
    Args:
        id (int): Primary key of EmployeeObjective.
    Returns:
        it will redirect to objective_detailed_view_activity.
    """
    comment_form = ObjectiveCommentForm(request.POST)
    if comment_form.is_valid():
        objective = EmployeeObjective.objects.get(id=id)
        form = comment_form.save(commit=False)
        form.employee_id = request.user.employee_get
        form.employee_objective_id = objective
        form.save()

        return redirect(objective_detailed_view_activity, id)
    return redirect(objective_detailed_view_activity, id)


@login_required
@hx_request_required
def emp_objective_search(request, obj_id):
    """
    This view is used to to search employee objective,returns searched and filtered objects.
    Returns:
        All the filtered and searched object will based on userlevel.
    """
    objective = Objective.objects.get(id=obj_id)
    emp_objectives = objective.employee_objective.all()
    search_val = request.GET.get("search")
    if search_val is None:
        search_val = ""
    emp_objectives = EmployeeObjectiveFilter(request.GET, emp_objectives).qs.distinct()
    if not request.GET.get("archive") == "true":
        emp_objectives = emp_objectives.filter(archive=False)
    previous_data = request.GET.urlencode()
    emp_objectives = Paginator(emp_objectives, get_pagination())
    page = request.GET.get("page")
    emp_objectives = emp_objectives.get_page(page)
    data_dict = parse_qs(previous_data)
    get_key_instances(EmployeeObjective, data_dict)
    context = {
        "emp_objectives": emp_objectives,
        "filter_dict": data_dict,
        "pg": previous_data,
        "objective": objective,
    }
    template = "okr/emp_objective/emp_objective_list.html"
    if request.GET.get("field") != "" and request.GET.get("field") is not None:
        template = "okr/group_by.html"
    return render(request, template, context)


@login_required
@hx_request_required
def kr_table_view(request, emp_objective_id):
    """
    Renders a table view of Key Results associated with an employee objective.

    Parameters:
    - request: HttpRequest object.
    - emp_objective_id: ID of the EmployeeObjective to display Key Results for.

    Returns:
    Renders the 'okr/kr_list.html' template with Key Results associated with the specified EmployeeObjective.
    """
    emp_objective = EmployeeObjective.objects.get(id=emp_objective_id)
    krs = emp_objective.employee_key_result.all()
    krs = KeyResultFilter(request.GET, queryset=krs).qs.distinct()
    krs = Paginator(krs, get_pagination())
    krs_page = request.GET.get("krs_page")
    krs = krs.get_page(krs_page)
    previous_data = request.GET.urlencode()
    context = {
        "krs": krs,
        "key_result_status": EmployeeKeyResult.STATUS_CHOICES,
        "emp_objective": emp_objective,
        "pd": previous_data,
        "today": datetime.datetime.today().date(),
    }
    template = "okr/kr_list.html"
    return render(request, template, context)


@login_required
@hx_request_required
@owner_can_enter("pms.change_employeeobjective", EmployeeObjective)
def objective_detailed_view_objective_status(request, id):
    """
    This view is used to  update status of objective in objective detailed view,
    redirect to objective_detailed_view_activity. using htmx
    Args:
        obj_id (int): Primary key of EmployeeObjective.
    Returns:
        All the filtered and searched object will based on userlevel.
    """

    objective = EmployeeObjective.objects.get(id=id)
    status = request.POST.get("objective_status")
    objective.status = status
    objective.save()
    messages.info(
        request,
        _("Objective %(objective)s status updated")
        % {"objective": objective.objective},
    )
    return redirect(objective_detailed_view_activity, id)


@login_required
@hx_request_required
@owner_can_enter("pms.change_employeekeyresult", EmployeeObjective)
def objective_detailed_view_key_result_status(request, obj_id, kr_id):
    """
    This view is used to  update status of key result in objective detailed view,
    redirect to objective_detailed_view_activity. using htmx
    Args:
        obj_id (int): Primarykey of EmployeeObjective.
        kr_id (int): Primarykey of EmployeeKeyResult.
    Returns:
        All the filtered and searched object will based on userlevel.
    """

    status = request.POST.get("key_result_status")
    employee_key_result = EmployeeKeyResult.objects.get(id=kr_id)

    current_value = employee_key_result.current_value
    target_value = employee_key_result.target_value

    if current_value >= target_value:
        employee_key_result.status = "Closed"
    else:
        employee_key_result.status = status
    employee_key_result.save()
    messages.info(request, _("Status has been updated"))
    # return redirect(objective_detailed_view_activity, id=obj_id)
    response = redirect(objective_detailed_view_activity, id=obj_id)
    return HttpResponse(
        response.content.decode("utf-8") + "<script>location.reload();</script>"
    )


@login_required
@hx_request_required
def objective_detailed_view_current_value(request, kr_id):
    """
    This view is used to update current value of key result,  return redirect to view . using htmx
    Args:
        kr_id (int): Primarykey of EmployeeKeyresult.
    Returns:
        All the history of EmployeeObjective.
    """
    if request.method == "POST":
        current_value = request.POST.get("current_value")
        employee_key_result = EmployeeKeyResult.objects.get(id=kr_id)
        objective = employee_key_result.employee_objective_id
        employee = request.user.employee_get
        if not (
            request.user.has_perm("pms.change_employeekeyresult")
            or objective.employee_id == employee
            or check_manager(employee, objective.employee_id)
        ):
            return render(request, "no_perm.html")
        target_value = employee_key_result.target_value
        objective_id = employee_key_result.employee_objective_id.id
        if int(current_value) < target_value:
            employee_key_result.current_value = current_value
            employee_key_result.save()
            messages.info(
                request,
                _("Current value of %(employee_key_result)s updated")
                % {"employee_key_result": employee_key_result},
            )
            return redirect(objective_detailed_view_activity, objective_id)

        elif int(current_value) == target_value:
            employee_key_result.current_value = current_value
            employee_key_result.status = "Closed"
            employee_key_result.save()
            messages.info(
                request,
                _("Current value of %(employee_key_result)s updated")
                % {"employee_key_result": employee_key_result},
            )
            # return redirect(objective_detailed_view_activity, objective_id)
            response = redirect(objective_detailed_view_activity, objective_id)
            return HttpResponse(
                response.content.decode("utf-8") + "<script>location.reload();</script>"
            )

        elif int(current_value) > target_value:
            messages.warning(request, _("Current value is greater than target value"))
            return redirect(objective_detailed_view_activity, objective_id)
        messages.error(request, _("Error occurred during current value updation"))
        return redirect(objective_detailed_view_activity, objective_id)


@login_required
@owner_can_enter("pms.change_employeeobjective", EmployeeObjective)
def objective_archive(request, id):
    """
    this function is used to archive the objective
        args:
            id(int) : pimarykey of EmployeeObjective
        return:
            redirect to objective_list_view
    """
    objective = Objective.find(id)
    if not objective:
        return HorillaRedirect(
            request, message=_("No Objective found matching the query.")
        )

    if objective.archive:
        objective.archive = False
        objective.save()
        messages.info(request, _("Objective un-archived successfully!."))
    elif not objective.archive:
        objective.archive = True
        objective.save()
        messages.info(request, _("Objective archived successfully!."))
    return HttpResponse(
        "<script> $('.reload-record').click(); $('#reloadMessagesButton').click();</script>"
    )


@login_required
@hx_request_required
@pms_owner_and_manager_can_enter(perm="pms.view_employeeobjective")
def view_employee_objective(request, emp_obj_id):
    """
    This function is used to render individual view of the employee objective
        args:
            emp_obj_id(int) : pimarykey of EmployeeObjective
        return:
            redirect to individual view of employee objective
    """
    emp_objective = EmployeeObjective.objects.get(id=emp_obj_id)
    context = {
        "instance": emp_objective,
        "objective_key_result_status": EmployeeObjective.STATUS_CHOICES,
    }
    return render(request, "okr/emp_obj_single.html", context)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.add_employeeobjective")
def create_employee_objective(request):
    """
    This function is used to create the employee objective
        args:
            emp_obj_id(int) : pimarykey of EmployeeObjective
        return:
            redirect to form of employee objective
    """
    data = request.GET.copy()
    # Convert QueryDict to a regular dictionary
    cleaned_data = {
        key: value if len(value) > 1 else value[0] for key, value in data.lists()
    }
    form = EmployeeObjectiveCreateForm(initial=cleaned_data)
    if request.method == "POST":
        form = EmployeeObjectiveCreateForm(request.POST)
        if form.is_valid():
            # get key result on form
            krs = list(form.cleaned_data["key_result_id"])
            emp_obj = form.save(commit=False)
            obj = emp_obj.objective_id
            # Add this employee as assignee
            obj.assignees.add(emp_obj.employee_id)
            # krs.extend([key_result for key_result in obj.key_result_id.all()])
            set_krs = set(krs)
            emp_obj.save()
            # Add all key results
            for kr in set_krs:
                emp_obj.key_result_id.add(kr)
                if not EmployeeKeyResult.objects.filter(
                    employee_objective_id=emp_obj, key_result_id=kr
                ).exists():
                    emp_kr = EmployeeKeyResult.objects.create(
                        employee_objective_id=emp_obj,
                        key_result_id=kr,
                        progress_type=kr.progress_type,
                        target_value=kr.target_value,
                        start_date=emp_obj.start_date,
                    )
            messages.success(request, _("Employee objective created successfully"))
            return HorillaRedirect(request)
    context = {"form": form, "k_form": KRForm(), "emp_obj": True}
    return render(
        request, "okr/emp_objective/emp_objective_create_form.html", context=context
    )


@login_required
def get_objective_keyresults(request):
    obj_id = request.GET.get("objective_id")
    objective = Objective.find(obj_id)
    if not objective:

        return HorillaRedirect(
            request, message=_("No Objective found matching the query.")
        )

    keyresults = objective.key_result_id.all()
    form = EmployeeObjectiveCreateForm(initial={"key_result_id": keyresults})
    context = {"form": form, "k_form": KRForm(), "emp_obj": True}
    return render(
        request, "okr/emp_objective/emp_objective_create_form.html", context=context
    )


@login_required
@hx_request_required
def update_employee_objective(request, emp_obj_id):
    """
    This function is used to update the employee objective
        args:
            emp_obj_id(int) : pimarykey of EmployeeObjective
        return:
            redirect to form of employee objective
    """
    emp_objective = EmployeeObjective.objects.get(id=emp_obj_id)
    if (
        request.user.employee_get == emp_objective.employee_id
        or request.user.employee_get in emp_objective.objective_id.managers.all()
        or request.user.has_perm("pms.change_employeeobjective")
    ):
        form = EmployeeObjectiveForm(instance=emp_objective)
        if request.method == "POST":
            form = EmployeeObjectiveForm(request.POST, instance=emp_objective)
            if form.is_valid():
                emp_obj = form.save(commit=False)
                emp_obj.save()
                messages.success(request, _("Employee objective Updated successfully"))
                return HorillaRedirect(request)
        context = {"form": form, "k_form": KRForm()}
        return render(request, "okr/emp_objective_form.html", context=context)
    else:
        messages.info(request, _("You don't have permission."))
        return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="pms.delete_employeeobjective")
def archive_employee_objective(request, emp_obj_id):
    """
    This function is used to archive or unarchive the employee objective
        args:
            emp_obj_id(int) : pimarykey of EmployeeObjective
        return:
            redirect to detailed of employee objective
    """
    emp_objective = EmployeeObjective.find(emp_obj_id)
    if not emp_objective:
        return HorillaRedirect(
            request, message=_("No Employee Objective found matching the query.")
        )

    if emp_objective.archive:
        emp_objective.archive = False
        emp_objective.save()
        messages.success(request, _("Objective un-archived successfully!."))
    elif not emp_objective.archive:
        emp_objective.archive = True
        emp_objective.save()
        messages.success(request, _("Objective archived successfully!."))
    if request.GET.get("detail_view"):
        return HttpResponse(
            "<script> $('.reload-record').click(); $('#reloadMessagesButton').click();</script>"
        )
    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="pms.delete_employeeobjective")
def delete_employee_objective(request, emp_obj_id):
    """
    This function is used to delete the employee objective
        args:
            emp_obj_id(int) : pimarykey of EmployeeObjective
        return:
            redirect to detailed of employee objective
    """
    emp_objective = EmployeeObjective.find(emp_obj_id)
    if not emp_objective:
        return HorillaRedirect(
            request, message=_("No Employee Objective found matching the query.")
        )

    single_view = request.GET.get("single_view")
    if emp_objective.employee_key_result.exists():
        messages.warning(
            request, _("You can't delete this objective,related entries exists")
        )
    else:
        employee = emp_objective.employee_id
        objective = emp_objective.objective_id
        emp_objective.delete()
        objective.assignees.remove(employee)
        messages.success(request, _("Objective deleted successfully!."))
    return HorillaRedirect(request)


@login_required
@hx_request_required
def change_employee_objective_status(request):
    """
    This function is used to change status of the employee objective
        args:
            hx-request
        return:
            a message
    """
    emp_obj = request.GET.get("empObjId")
    emp_objective = EmployeeObjective.objects.filter(id=emp_obj).first()
    if not emp_objective:
        messages.error(request, _("Employee objective not found."))
        return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")
    if not (
        request.user.has_perm("pms.change_objective")
        or request.user.has_perm("pms.change_employeeobjective")
        or request.user.has_perm("pms.change_employeekeyresult")
        or request.user.employee_get in emp_objective.objective_id.managers.all()
        or (
            emp_objective.objective_id.self_employee_progress_update
            and (emp_objective.employee_id == request.user.employee_get)
        )
    ):
        messages.info(request, _("You dont have permission"))
        return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")

    status = request.GET.get("status")
    if not (
        request.user.has_perm("pms.change_objective")
        or request.user.has_perm("pms.change_employeeobjective")
        or request.user.has_perm("pms.change_employeekeyresult")
        or request.user.employee_get in emp_objective.objective_id.managers.all()
        or (
            emp_objective.objective_id.self_employee_progress_update
            and (emp_objective.employee_id == request.user.employee_get)
        )
    ):
        messages.info(request, _("You dont have permission."))
    else:
        if emp_objective.status != status:
            emp_objective.status = status
            emp_objective.save()
            messages.success(
                request,
                _(
                    f"The status of the objective '{emp_objective.objective_id}'\
                    has been changed to {emp_objective.status}."
                ),
            )
            notify.send(
                request.user.employee_get,
                recipient=emp_objective.employee_id.employee_user_id,
                verb=f"The status of the objective '{emp_objective.objective_id}'\
                    has been changed to {emp_objective.status}.",
                verb_ar=f"تم تغيير حالة الهدف '{emp_objective.objective_id}'\
                    إلى {emp_objective.status}.",
                verb_de=f"Der Status des Ziels '{emp_objective.objective_id}'\
                    wurde zu {emp_objective.status} geändert.",
                verb_es=f"El estado del objetivo '{emp_objective.objective_id}'\
                    ha sido cambiado a {emp_objective.status}.",
                verb_fr=f"Le statut de l'objectif '{emp_objective.objective_id}'\
                    a été changé à {emp_objective.status}.",
                redirect=reverse(
                    "objective-detailed-view",
                    kwargs={"obj_id": emp_objective.objective_id.id},
                ),
            )
        else:
            messages.info(
                request, _("The status of the objective is the same as selected.")
            )
    return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")


@login_required
@manager_can_enter(perm="pms.add_employeekeyresult")
def key_result_view(request):
    """
    This view is used to view key result,
    Args:
        request: Request object.
    Returns:
        if errorr occur it will return errorr message.
    """
    krs = KeyResultFilter(request.GET).qs
    krs = group_by_queryset(
        krs, "employee_objective_id__employee_id", request.GET.get("page"), "page"
    )
    context = {
        "krs": krs,
        "key_result_status": EmployeeKeyResult.STATUS_CHOICES,
    }
    return render(request, "okr/key_result/kr_dashboard_view.html", context=context)


@login_required
@manager_can_enter(perm="pms.add_employeekeyresult")
def key_result_creation(request, obj_id, obj_type):
    """
    This view is used to create key result,
    Args:
        id (int): Primarykey of EmployeeObjective.
        obj_type (str): type  of objecitve
    Returns:
        if errorr occur it will return errorr message .
    """

    employee = request.user.employee_get
    if obj_type == "individual":
        objective = EmployeeObjective.objects.filter(id=int(obj_id))
        start_date = None
        end_date = None
        for obj in objective:
            start_date = obj.start_date
            end_date = obj.end_date
        key_result_form = KeyResultForm(
            employee=employee, initial={"start_date": start_date, "end_date": end_date}
        )
    elif obj_type == "multiple":
        objective_ids = json.loads(obj_id)
        for objective_id in objective_ids:
            objective = EmployeeObjective.objects.filter(id=objective_id).first()
            start_date = objective.start_date
            end_date = objective.end_date
        key_result_form = KeyResultForm(
            employee=employee, initial={"start_date": start_date, "end_date": end_date}
        )
    else:
        return HorillaRedirect(request, message=_("Invalid parameters"))
    context = {
        "key_result_form": key_result_form,
        "objective_id": obj_id,
        "objective_type": obj_type,
    }
    if obj_type == "multiple":
        # for job position or department  the context should have all the related object ids
        value = context.pop("objective_id")
        context["objective_ids"] = value
    if request.method == "POST":
        if obj_type == "individual":
            employee_objective_id = EmployeeObjective.objects.get(id=int(obj_id))
            form_key_result = KeyResultForm(
                request.POST, initial={"employee_objective_id": employee_objective_id}
            )
            if form_key_result.is_valid():
                form = form_key_result.save(commit=False)
                form.start_value = form.current_value
                form.employee_objective_id = employee_objective_id
                form.save()
                messages.success(request, _("Key result created"))
                return redirect(objective_detailed_view, obj_id)
            else:
                context["key_result_form"] = form_key_result

        elif obj_type == "multiple":
            # If the objective is for job postion or department
            # The id will be list of objective id
            objective_ids = json.loads(obj_id)
            for objective_id in objective_ids:
                objective = EmployeeObjective.objects.filter(id=objective_id).first()
                form_key_result = KeyResultForm(
                    request.POST, initial={"employee_objective_id": objective}
                )
                if form_key_result.is_valid():
                    form = form_key_result.save(commit=False)
                    form.start_value = form.current_value
                    form.employee_id = objective.employee_id
                    form.employee_objective_id = objective
                    form.save()
                else:
                    context["key_result_form"] = form_key_result
                    return render(
                        request, "okr/key_result/key_result_creation.html", context
                    )
            messages.success(request, _("Key results created"))
            return redirect(objective_list_view)
    return render(request, "okr/key_result/key_result_creation.html", context)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.add_employeekeyresult")
def key_result_creation_htmx(request, id):
    """
    This view is used to create key result in objective detailed view,  using htmx
    Args:
        id (int): Primarykey of EmployeeObjective.
        obj_type (str): type  of objecitve
    Returns:
        if errorr occure it will return errorr message .
    """
    object = EmployeeObjective.objects.filter(id=id)
    start_date = None
    end_date = None
    for obj in object:
        start_date = obj.start_date
        end_date = obj.end_date
    key_result_form = KeyResultForm(
        initial={"start_date": start_date, "end_date": end_date}
    )
    context = {"key_result_form": key_result_form, "objecitve_id": id}
    objective = EmployeeObjective.objects.get(id=id)
    if request.method == "POST":
        initial_data = {"employee_objective_id": objective}
        form_key_result = KeyResultForm(request.POST, initial=initial_data)
        if form_key_result.is_valid():
            form = form_key_result.save(commit=False)
            form.start_value = form.current_value
            form.employee_objective_id = objective
            form.save()
            messages.success(request, _("Key result created"))
            return HorillaRedirect(request)
        context["key_result_form"] = form_key_result
    return render(request, "okr/key_result/key_result_creation_htmx.html", context)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.update_employeekeyresult")
def key_result_update(request, id):
    """
    This view is used to update key result, using htmx
    Args:
        id (int): Primarykey of EmployeeKeyResult.
    Returns:
        success or errors message.
    """

    key_result = EmployeeKeyResult.objects.get(id=id)
    key_result_form = KeyResultForm(instance=key_result)
    context = {"key_result_form": key_result_form, "key_result_id": key_result.id}
    if request.method == "POST":
        key_result_form = KeyResultForm(request.POST, instance=key_result)
        key_result_form.initial["employee_objective_id"] = (
            key_result.employee_objective_id
        )  # adding intial objective value to the form
        if key_result_form.is_valid():
            key_result_form.save()
            messages.info(request, _("Key result updated"))
            return HorillaRedirect(request)
        else:
            context["key_result_form"] = key_result_form
    return render(request, "okr/key_result/key_result_update.html", context)


# feedback section
def send_feedback_notifications(request, feedback):
    # Send notification to employee
    if feedback.employee_id:
        employee = feedback.employee_id
        notify.send(
            request.user.employee_get,
            recipient=employee.employee_user_id,
            verb="You have received feedback!",
            verb_ar="لقد تلقيت ملاحظات!",
            verb_de="Sie haben Feedback erhalten!",
            verb_es="¡Has recibido retroalimentación!",
            verb_fr="Vous avez reçu des commentaires !",
            redirect=reverse("feedback-detailed-view", kwargs={"id": feedback.id}),
            icon="chatbox-ellipses",
        )
    all_employees = feedback.requested_employees()
    for employee in all_employees:
        notify.send(
            request.user.employee_get,
            recipient=employee.employee_user_id,
            verb="You have been requested to provide feedback!",
            verb_ar="لقد طُلب منك تقديم ملاحظات!",
            verb_de="Sie wurden gebeten, Feedback zu geben!",
            verb_es="Se le ha solicitado que proporcione comentarios.",
            verb_fr="Il vous a été demandé de fournir des commentaires.",
            redirect=reverse("feedback-detailed-view", kwargs={"id": feedback.id}),
            icon="chatbox-ellipses",
        )


@login_required
@manager_can_enter(perm="pms.add_feedback")
def feedback_creation(request):
    """
    This view is used to create feedback object.
    Returns:
        it will return feedback creation html.
    """
    form = FeedbackForm()
    form.fields["manager_id"].required = False
    context = {
        "feedback_form": form,
    }
    is_htmx = request.headers.get("HX-Request") is not None
    if request.method == "POST":
        form = FeedbackForm(request.POST)
        form.fields["manager_id"].required = False
        if form.is_valid():
            employees = form.data.getlist("subordinate_id")
            if key_result_ids := request.POST.getlist("employee_key_results_id"):
                for key_result_id in key_result_ids:
                    key_result = EmployeeKeyResult.objects.filter(
                        id=key_result_id
                    ).first()
                    feedback_form = form.save()
                    feedback_form.employee_key_results_id.add(key_result)
            instance = form.save()
            instance.subordinate_id.set(employees)

            messages.success(request, _("Feedback created successfully."))
            send_feedback_notifications(request, feedback=instance)
            if is_htmx:
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = json.dumps(
                    {"reloadFeedbackContainer": {"target": "body"}}
                )
                return response
            return redirect(reverse("feedback-view"))
        else:
            context["feedback_form"] = form
            if is_htmx:
                return render(
                    request,
                    "cbv/360_feedback/form/feedback_creation_fragment.html",
                    context,
                )
    if is_htmx:
        return render(
            request, "cbv/360_feedback/form/feedback_creation_fragment.html", context
        )
    return render(request, "cbv/360_feedback/feedback_home.html", context)


# @login_required
# @manager_can_enter(perm="pms.add_feedback")
# def feedback_creation_ajax(request):
#     """
#     This view is used to create feedback object.
#     Returns:
#         it will return feedback creation html.
#     """
#     # this ajax request is used to get the Key result and manager of the choosen employee
#     is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
#     if is_ajax:
#         if request.method == "POST":
#             employee_id = request.POST.get("employee_id")
#             key_results = EmployeeKeyResult.objects.filter(
#                 employee_objective_id__employee_id=employee_id
#             ).values()
#             employee_work_info = EmployeeWorkInformation.objects.filter(
#                 employee_id__id=employee_id
#             ).first()
#             reporting_manager_id = employee_work_info.reporting_manager_id
#             if reporting_manager_id:
#                 reporting_manager = {
#                     "id": reporting_manager_id.id or None,
#                     "employee_first_name": reporting_manager_id.employee_first_name
#                     or None,
#                     "employee_last_name": reporting_manager_id.employee_last_name
#                     or None,
#                 }
#             else:
#                 reporting_manager = None
#             return JsonResponse(
#                 {
#                     "key_results": list(key_results),
#                     "reporting_manager": reporting_manager,
#                 }
#             )
#         return JsonResponse({"status": "Invalid request"}, status=400)


@login_required
@hx_request_required
@permission_required(perm="pms.change_feedback")
def feedback_update(request, id):
    """
    This view is used to  update the feedback.
    Args:
        id(int) : primarykey of the feedback.
    Returns:
        it will redirect to  feedback_detailed_view.
    """

    feedback = Feedback.objects.get(id=id)
    form = FeedbackForm(instance=feedback)
    feedback_started = Answer.objects.filter(feedback_id=feedback)
    context = {"feedback_form": form}
    if feedback_started:
        return HorillaRedirect(request, message=_("Ongoing feedback is not editable!."))

    if request.method == "POST":
        form = FeedbackForm(request.POST, instance=feedback)
        if form.is_valid():
            employees = form.data.getlist("subordinate_id")
            if key_result_ids := request.POST.getlist("employee_key_results_id"):
                for key_result_id in key_result_ids:
                    key_result = EmployeeKeyResult.objects.filter(
                        id=key_result_id
                    ).first()
                    feedback_form = form.save()
                    feedback_form.employee_key_results_id.add(key_result)
            instance = form.save()
            instance.subordinate_id.set(employees)
            other_employees = check_duplication(
                form.instance, form.instance.others_id.all()
            )
            form.cleaned_data["others_id"] = other_employees
            feedback = form.save()
            messages.info(request, _("Feedback updated successfully!."))
            send_feedback_notifications(request, feedback)
            return HorillaRedirect(request)
        else:
            context["feedback_form"] = form
    return render(request, "feedback/feedback_update.html", context)


@login_required
def filter_pagination_feedback(
    request, self_feedback, requested_feedback, all_feedback, anonymous_feedback
):
    """
    This view is used to filter or search the feedback object  ,

    Args:
        self_feedback (queryset): self feedback filtered queryset.
        requested_feedback (queryset): requested feedback filtered queryset.
        all_feedback (queryset): all feedback filtered queryset.

    Returns:
        it will return the filtered and searched object.

    """
    previous_data = request.GET.urlencode()
    initial_data = {"archive": False}  # set initial value of archive filter to False
    feedback_filter_own = FeedbackFilter(
        request.GET or initial_data, queryset=self_feedback
    )
    feedback_filter_requested = FeedbackFilter(
        request.GET or initial_data, queryset=requested_feedback
    )
    feedback_filter_all = FeedbackFilter(
        request.GET or initial_data, queryset=all_feedback
    )
    anonymous_feedback = AnonymousFeedbackFilter(
        request.GET, queryset=anonymous_feedback
    ).qs
    feedback_paginator_own = Paginator(feedback_filter_own.qs, get_pagination())
    feedback_paginator_requested = Paginator(
        feedback_filter_requested.qs, get_pagination()
    )
    feedback_paginator_all = Paginator(feedback_filter_all.qs, get_pagination())
    page_number = request.GET.get("page")

    feedbacks_own = feedback_paginator_own.get_page(page_number)
    feedbacks_requested = feedback_paginator_requested.get_page(page_number)
    feedbacks_all = feedback_paginator_all.get_page(page_number)
    now = datetime.datetime.today().date()
    data_dict = parse_qs(previous_data)
    get_key_instances(Feedback, data_dict)
    context = {
        "superuser": "true",
        "self_feedback": feedbacks_own,
        "requested_feedback": feedbacks_requested,
        "anonymous_feedback": anonymous_feedback,
        "all_feedbacks": feedbacks_all,
        "feedback_filter_form": feedback_filter_own.form,
        "pg": previous_data,
        "current_date": now,
        "filter_dict": data_dict,
    }
    return context


@login_required
@hx_request_required
def feedback_list_search(request):
    """
    This view is used to filter or search the feedback object  ,
    Args:
    Returns:
        it will return the filtered and searched object.
    """
    feedback = request.GET.get("search")  # if the search is none the filter will works
    if feedback is None:
        feedback = ""
    employee_id = Employee.objects.get(employee_user_id=request.user)
    self_feedback = Feedback.objects.filter(employee_id=employee_id).filter(
        review_cycle__icontains=feedback
    )
    requested_feedback_ids = []
    requested_feedback_ids.extend(
        [i.id for i in Feedback.objects.filter(manager_id=employee_id)]
    )
    requested_feedback_ids.extend(
        [i.id for i in Feedback.objects.filter(colleague_id=employee_id)]
    )
    requested_feedback_ids.extend(
        [i.id for i in Feedback.objects.filter(subordinate_id=employee_id)]
    )
    requested_feedback_ids.extend(
        [i.id for i in Feedback.objects.filter(others_id=employee_id)]
    )
    requested_feedback = Feedback.objects.filter(
        pk__in=requested_feedback_ids,
        review_cycle__icontains=feedback,
        start_date__lte=datetime.date.today(),
        end_date__gte=datetime.date.today(),
    )
    all_feedback = Feedback.objects.none()
    if request.user.has_perm("pms.view_feedback"):
        all_feedback = Feedback.objects.all().filter(review_cycle__icontains=feedback)
    else:
        # feedbacks to review if employee is a manager
        all_feedback = Feedback.objects.filter(manager_id=employee_id).filter(
            review_cycle__icontains=feedback
        )
    # Anonymous feedbacks
    anonymous_feedback = (
        AnonymousFeedback.objects.filter(
            anonymous_feedback_id=request.user.id, archive=False
        )
        if not request.user.has_perm("pms.view_feedback")
        else AnonymousFeedback.objects.filter(archive=False)
    )
    related_anonymous_feedbacks = get_anonymous_feedbacks(employee_id)
    anonymous_feedback = (related_anonymous_feedbacks | anonymous_feedback).distinct()

    context = filter_pagination_feedback(
        request, self_feedback, requested_feedback, all_feedback, anonymous_feedback
    )

    return render(request, "feedback/feedback_list.html", context)


@login_required
def feedback_list_view(request):
    """
    This view is used to filter or search the feedback object  ,
    Args:
    Returns:
        it will return the filtered and searched object.
    """
    user = request.user
    employee = user.employee_get
    # filter own feedbacks (self feedbacks)
    feedback_own = Feedback.objects.filter(
        employee_id=employee,
        archive=False,
    )
    # feedbacks to answer
    feedback_requested = Feedback.objects.filter(
        Q(manager_id=employee)
        | Q(colleague_id=employee)
        | Q(subordinate_id=employee)
        | Q(others_id=employee),
        start_date__lte=datetime.date.today(),
        end_date__gte=datetime.date.today(),
    ).distinct()
    if user.has_perm("pms.view_feedback"):
        feedback_all = Feedback.objects.filter(archive=False)
    else:
        # feedbacks to review if employee is a manager
        feedback_all = Feedback.objects.filter(manager_id=employee, archive=False)
    # Anonymous feedbacks
    anonymous_feedback = (
        AnonymousFeedback.objects.filter(
            anonymous_feedback_id=request.user.id, archive=False
        )
        if not request.user.has_perm("pms.view_feedback")
        else AnonymousFeedback.objects.filter(archive=False)
    )
    related_anonymous_feedbacks = get_anonymous_feedbacks(employee)
    anonymous_feedback = (
        related_anonymous_feedbacks.filter(archive=False) | anonymous_feedback
    ).distinct()
    context = filter_pagination_feedback(
        request, feedback_own, feedback_requested, feedback_all, anonymous_feedback
    )
    # checking condition for empty page
    if Feedback.objects.all().exists():
        template = "feedback/feedback_list_view.html"
    else:
        template = "feedback/feedback_empty.html"
    return render(request, template, context)


@login_required
def feedback_detailed_view(request, id, **kwargs):
    """
    This view is used to for detailed view of feedback,
    Args:
        id(int) : primarykey of the feedback
    Returns:
        it will return the feedback object to feedback_detailed_view template .
    """
    feedback = Feedback.find(id)
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Feedback found matching the query.")
        )

    is_have_perm = check_permission_feedback_detailed_view(
        request, feedback, "pms.view_feedback"
    )
    if is_have_perm:
        feedback_started = Answer.objects.filter(feedback_id=id)
        employees = feedback.requested_employees()
        yes = []
        no = []
        for employee in employees:
            if Answer.objects.filter(
                feedback_id=feedback, employee_id=employee
            ).exists():
                yes.append(employee)
            else:
                no.append(employee)
        employee_statics = {"yes": yes, "no": no}
        context = {
            "feedback": feedback,
            "feedback_started": feedback_started,
            "feedback_status": Feedback.STATUS_CHOICES,
            "employee_statics": employee_statics,
            "today": datetime.datetime.today().date(),
        }
        return render(request, "feedback/feedback_detailed_view.html", context)
    return handle_no_permission(request)


@login_required
def feedback_detailed_view_answer(request, id, emp_id):
    """
    This view is used show  answer ,
    Args:
        id(int) : primarykey of the feedback.
        emp_id(int) : primarykey of the Employee.
    Returns:
        it will return the answers .
    """
    feedback = Feedback.find(id)
    employee = Employee.objects.filter(id=emp_id).first()
    if not feedback or not employee:
        return HorillaRedirect(
            request,
            message=_("No %(class_name)s found matching the query.")
            % {"class_name": "Feedback" if not feedback else "Employee"},
        )

    is_have_perm = check_permission_feedback_detailed_view(
        request, feedback, "pms.view_feedback"
    )
    kr_feedbacks = KeyResultFeedback.objects.filter(
        feedback_id=feedback, employee_id=employee
    )
    if is_have_perm:
        answers = Answer.objects.filter(employee_id=employee, feedback_id=feedback)
        context = {
            "answers": answers,
            "kr_feedbacks": kr_feedbacks,
        }
        return render(request, "feedback/feedback_detailed_view_answer.html", context)
    return handle_no_permission(request)


@login_required
def feedback_answer_get(request, id, **kwargs):
    """
    This view is used to render the feedback questions ,
    Args:
        id(int) : primarykey of the feedback.
    Returns:
        it will redirect to feedaback_answer.html .
    """

    feedback = Feedback.find(id)
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Feedback found matching the query.")
        )

    # check if the feedback start_date is not started yet
    if feedback.start_date > datetime.date.today():
        messages.info(request, _("Feedback not started yet"))
        return redirect(reverse("feedback-view"))

    # check if the feedback end_date is not over
    if feedback.end_date and feedback.end_date < datetime.date.today():
        messages.info(request, _("Feedback is due/closed"))
        return redirect(reverse("feedback-view"))
    user = request.user
    employee = Employee.objects.filter(employee_user_id=user).first()
    answer = Answer.objects.filter(feedback_id=feedback, employee_id=employee)
    question_template = feedback.question_template_id
    questions = question_template.question.all()
    options = QuestionOptions.objects.all()
    feedback_employees = (
        [feedback.employee_id]
        + [feedback.manager_id]
        + list(feedback.colleague_id.all())
        + list(feedback.subordinate_id.all())
        + list(feedback.others_id.all())
    )
    if not employee in feedback_employees:
        messages.info(request, _("You are not allowed to answer"))
        return redirect(reverse("feedback-view"))

    # Employee does not have an answer object
    for employee in feedback_employees:
        has_answer = Answer.objects.filter(
            employee_id=employee, feedback_id=feedback
        ).exists()
    if has_answer:
        feedback.status = "Closed"
        feedback.save()

    # Check if the feedback has already been answered
    if answer:
        messages.info(request, _("Feedback already answered"))
        return redirect(reverse("feedback-view"))

    context = {
        "questions": questions,
        "options": options,
        "feedback": feedback,
    }

    return render(request, "feedback/answer/feedback_answer.html", context)


@login_required
def feedback_answer_post(request, id):
    """
    This view is used to create feedback answer ,
    Args:
        id(int) : primarykey of the feedback.
    Returns:
        it will redirect to feedback_list_view if the form was success full.
    """
    feedback = Feedback.find(id)
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Feedback found matching the query.")
        )

    user = request.user
    employee = Employee.objects.filter(employee_user_id=user).first()
    question_template = feedback.question_template_id
    questions = question_template.question.all()

    if request.method == "POST":
        for question in questions:
            if request.POST.get(f"answer{question.id}"):
                answer = request.POST.get(f"answer{question.id}")
                Answer.objects.get_or_create(
                    answer={"answer": answer},
                    question_id=question,
                    feedback_id=feedback,
                    employee_id=employee,
                )
                feedback.status = "On Track"
                feedback.save()
        for key_result in feedback.employee_key_results_id.all():
            if request.POST.get(f"key_result{key_result.id}"):
                answer = request.POST.get(f"key_result{key_result.id}")
                keyresult, create = KeyResultFeedback.objects.get_or_create(
                    answer={"answer": answer},
                    key_result_id=key_result,
                    feedback_id=feedback,
                    employee_id=request.user.employee_get,
                )
        messages.success(
            request,
            _("Feedback %(review_cycle)s has been answered successfully!.")
            % {"review_cycle": feedback.review_cycle},
        )
        return redirect(reverse("feedback-view"))


@login_required
def feedback_answer_view(request, id, **kwargs):
    """
    This view is used to  view the feedback for employee.
    Args:
        id(int) : primarykey of the feedback.
    Returns:
        it will return feedback answer object to feedback_answer_view.
    """

    feedback = Feedback.find(id)
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Feedback found matching the query.")
        )

    user = request.user
    employee = Employee.objects.filter(employee_user_id=user).first()
    answers = Answer.objects.filter(feedback_id=feedback, employee_id=employee)
    key_result_feedback = KeyResultFeedback.objects.filter(
        feedback_id=feedback, employee_id=employee
    )

    if not answers:
        messages.info(request, _("Feedback is not answered yet"))
        return redirect(reverse("feedback-view"))

    context = {
        "answers": answers,
        "feedback_id": feedback,
        "key_result_feedback": key_result_feedback,
    }
    return render(request, "feedback/answer/feedback_answer_view.html", context)


@login_required
@permission_required(perm="pms.delete_feedback")
def feedback_delete(request, id):
    """
    This view is used to  delete the feedback.
    Args:
        id(int) : primarykey of the feedback.
    Returns:
        it will redirect to  feedback_list_view.
    """
    error_message = None
    try:
        feedback = Feedback.objects.get(id=id)
        answered = Answer.objects.filter(feedback_id=feedback).first()
        if (
            feedback.status == "Closed"
            or feedback.status == "Not Started"
            and not answered
        ):
            feedback.delete()
            messages.success(
                request,
                _("Feedback %(review_cycle)s deleted successfully!")
                % {"review_cycle": feedback.review_cycle},
            )
            if request.headers.get("HX-Request"):
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = json.dumps(
                    {"reloadFeedbackContainer": {"target": "body"}}
                )
                return response
            return redirect(reverse("feedback-view"))

        else:
            messages.warning(
                request,
                _("You can't delete feedback %(review_cycle)s with status %(status)s")
                % {"review_cycle": feedback.review_cycle, "status": feedback.status},
            )
            if request.headers.get("HX-Request"):
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = json.dumps(
                    {"reloadFeedbackContainer": {"target": "body"}}
                )
                return response
            return redirect(reverse("feedback-view"))

    except Feedback.DoesNotExist:
        error_message = _("No Feedback found matching the query.")
    except ProtectedError:
        error_message = _("Related entries exists")
    if request.headers.get("HX-Request"):
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(
            {"reloadFeedbackContainer": {"target": "body"}}
        )
        return response
    return HorillaRedirect(request, message=error_message)


@login_required
@hx_request_required
def feedback_detailed_view_status(request, id):
    """
    This view is used to  update status of feedback.
    Args:
        obj_id (int): Primarykey of feedback.
    Returns:
         message to the view
    """
    status = request.POST.get("feedback_status")
    feedback = get_object_or_404(Feedback, id=id)
    answer = Answer.objects.filter(feedback_id=feedback)
    if status == "Not Started" and answer:
        messages.warning(request, _("Feedback is already started"))
        return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")

    feedback.status = status
    feedback.save()
    if (feedback.status) == status:
        messages.success(
            request, _("Feedback status updated to  %(status)s") % {"status": _(status)}
        )
        return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")

    messages.info(
        request,
        _("Error occurred during status update to %(status)s") % {"status": _(status)},
    )
    return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")


@login_required
def get_feedback_overview(request, obj_id):
    """
    overview of feedback
    """
    feedback = Feedback.objects.filter(id=obj_id).first() if obj_id else None
    if feedback and check_permission_feedback_detailed_view(
        request, feedback, perm="pms.view_feedback"
    ):
        question_template = feedback.question_template_id
        questions = question_template.question.all()
        feedback_answers = feedback.feedback_answer.all()
        kr_feedbacks = feedback.feedback_key_result.all()
        feedback_overview = {}
        for question in questions:
            answer_list = []
            for answer in feedback_answers:
                if answer.question_id == question:
                    answer_list.append(
                        {
                            answer.employee_id: [
                                answer.answer,
                                {"type": answer.question_id.question_type},
                            ]
                        }
                    )
            feedback_overview[question] = answer_list
        for kr_feedback in kr_feedbacks:
            answer_list = []
            answer_list.append(
                {kr_feedback.employee_id: [kr_feedback.answer, {"type": "6"}]}
            )
            feedback_overview[
                f"Feedback about keyresult: {kr_feedback.key_result_id.key_result_id}"
            ] = answer_list

        return render(
            request,
            "feedback/feedback_overview.html",
            context={"feedback_overview": feedback_overview},
        )
    if feedback:
        messages.info(request, _("You dont have permission."))
    else:
        messages.info(request, _("Feedback does not exist."))
    return HorillaRedirect(request)


@login_required
@manager_can_enter(perm="pms.delete_feedback")
def feedback_archive(request, id):
    """
    this function is used to archive the feedback for employee
    args:
        id(int): primarykey of feedback
    """

    feedback = Feedback.find(id)
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Feedback found matching the query.")
        )

    if feedback.archive:
        feedback.archive = False
        feedback.save()
        messages.info(request, _("Feedback un-archived successfully!."))
    elif not feedback.archive:
        feedback.archive = True
        feedback.save()
        messages.info(request, _("Feedback archived successfully!."))
    if request.headers.get("HX-Request"):
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(
            {"reloadFeedbackContainer": {"target": "body"}}
        )
        return response
    return redirect(reverse("feedback-view"))


@login_required
def get_collegues(request):
    """
    Get collegues and subordinates for the manager.
    """
    try:
        employee_id = request.GET.get("employee_id")
        employee = Employee.objects.get(id=int(employee_id)) if employee_id else None
        employees_queryset = Employee.objects.none()
        reporting_manager = (
            employee.employee_work_info.reporting_manager_id
            if employee and employee.employee_work_info
            else None
        )
        if request.GET.get("data") == "keyresults":
            employees_queryset = EmployeeKeyResult.objects.filter(
                employee_objective_id__employee_id=employee
            )
        else:
            if employee and employee.employee_work_info:
                if request.GET.get("data") == "colleagues":
                    department = employee.get_department()
                    # employee ids to exclude from collegue list
                    exclude_ids = [employee.id]
                    if reporting_manager:
                        exclude_ids.append(reporting_manager.id)

                    # Get employees in the same department as the employee
                    employees_queryset = Employee.objects.filter(
                        is_active=True, employee_work_info__department_id=department
                    ).exclude(id__in=exclude_ids)
                elif request.GET.get("data") == "manager":
                    if reporting_manager:
                        employees_queryset = Employee.objects.filter(
                            id=reporting_manager.id
                        )
                elif request.GET.get("data") == "subordinates":
                    employees_queryset = Employee.objects.filter(
                        is_active=True,
                        employee_work_info__reporting_manager_id=employee,
                    )

        # Convert QuerySets to a list
        employees = [(employee.id, employee) for employee in employees_queryset]
        context = {"employees": employees}
        employee_html = render_to_string("employee/employees_select.html", context)
        return HttpResponse(employee_html)
    except (ValueError, TypeError, Employee.DoesNotExist):
        # A non-numeric or unknown employee_id in the query string. Rendering
        # an empty list is the right response to that, but it was previously
        # a bare except covering all forty lines above -- so any genuine
        # error in the colleague/manager/subordinate branches produced the
        # same empty list with nothing logged, and looked to the user like an
        # employee with no colleagues.
        logger.warning(
            "employee select: no employees for employee_id=%r data=%r",
            request.GET.get("employee_id"),
            request.GET.get("data"),
        )
        context = {"employees": []}
        employee_html = render_to_string("employee/employees_select.html", context)
        return HttpResponse(employee_html)


@login_required
def feedback_status(request):
    """this function is used to un-archive the feedback
    args:
        id(int): primarykey of feedback
        emp_id(int): primarykey of feedback
    """

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        if request.method == "POST":
            employee_id = request.POST.get("employee_id")
            feedback_id = request.POST.get("feedback_id")
            feedback = Feedback.objects.get(id=feedback_id)
            employee = Employee.objects.filter(id=employee_id).first()
            answer = Answer.objects.filter(employee_id=employee, feedback_id=feedback)
            status = _("Completed") if answer else _("Not-completed")
            return JsonResponse({"status": status})
    return JsonResponse({"status": "Invalid request"}, status=400)


@login_required
@manager_can_enter(perm="pms.add_question")
@require_http_methods(["POST"])
def question_creation(request, id):
    """
    This view is used to  create  question object.
    Args:
        id(int) : primarykey of the question template.

    Returns:
        it will redirect to  question_template_detailed_view.
    """
    if request.method == "POST":
        form = QuestionForm(request.POST)
        question_template = QuestionTemplate.objects.get(id=id)
        feedback_ongoing = Feedback.objects.filter(
            question_template_id=question_template
        ).first()
        if feedback_ongoing:
            messages.info(request, _("Question template is used in feedback."))
            return redirect(question_template_detailed_view, id)
        if form.is_valid():
            obj_question = form.save(commit=False)
            obj_question.template_id = question_template
            obj_question.save()

            if obj_question.question_type == "4":
                # checking the question type is multichoice
                option_a = form.cleaned_data["option_a"]
                option_b = form.cleaned_data["option_b"]
                option_c = form.cleaned_data["option_c"]
                option_d = form.cleaned_data["option_d"]
                QuestionOptions(
                    question_id=obj_question,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                ).save()
                messages.success(request, _("Question created successfully."))
                return redirect(question_template_detailed_view, id)
            messages.success(request, _("Question created successfully."))
            return redirect(question_template_detailed_view, id)
        else:
            messages.error(request, _("Error occurred during question creation!"))
            return redirect(question_template_detailed_view, id)


@login_required
def question_view(request, id):
    """
    This view is used to  view  question object.
    Args:
        id(int) : primarykey of the question template.
    Returns:
        it will redirect to  question_template_detailed_view.
    """
    question_template = QuestionTemplate.find(id)
    if not question_template:
        return HorillaRedirect(
            request, message=_("No Question Template found matching the query.")
        )

    question_formset = modelformset_factory(Question, form=QuestionForm, extra=0)

    questions = question_template.question.all()
    formset = question_formset(queryset=questions)
    options = []
    question_types = ["text", "ratings", "boolean", "Multi-choices", "likert"]

    for question in questions:
        question_options = QuestionOptions.objects.filter(question_id=question)
        options.extend(question_options)
    context = {
        "question_template": question_template,
        "questions": questions,
        "question_options": options,
        "question_types": question_types,
        "formset": formset,
    }
    return render(
        request,
        "feedback/question_template/question_template_detailed_view.html",
        context,
    )


@login_required
@manager_can_enter(perm="pms.change_question")
@require_http_methods(["POST"])
def question_update(request, temp_id, q_id):
    """
    This view is used to  update  question object.
    Args:
        id (int): primarykey of question
        temp_id (int): primarykey of question_template
    Returns:
        it will redirect to  question_template_detailed_view.

    """
    if request.method == "POST":
        question = Question.objects.get(id=q_id)
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            question_type = form.cleaned_data["question_type"]
            if question_type == "4":
                # if question is Multi-choices
                option_a = form.cleaned_data["option_a"]
                option_b = form.cleaned_data["option_b"]
                option_c = form.cleaned_data["option_c"]
                option_d = form.cleaned_data["option_d"]
                options, created = QuestionOptions.objects.get_or_create(
                    question_id=question
                )
                options.option_a = option_a
                options.option_b = option_b
                options.option_c = option_c
                options.option_d = option_d
                options.save()
                form.save()
                messages.info(request, _("Question updated successfully."))
                return redirect(question_template_detailed_view, temp_id)
            else:
                form.save()
                question_options = QuestionOptions.objects.filter(question_id=question)
                if question_options:
                    question_options.delete()
                messages.info(request, _("Question updated successfully."))
                return redirect(question_template_detailed_view, temp_id)
        else:
            # Form submission had errors
            messages.error(
                request,
                "\n".join(
                    [
                        f"{field}: {error}"
                        for field, errors in form.errors.items()
                        for error in errors
                    ]
                ),
            )
        return redirect(question_template_detailed_view, temp_id)


@login_required
@manager_can_enter(perm="pms.delete_question")
def question_delete(request, id):
    """
    This view is used to  delete  question object.
    Args:
        id (int): primarykey of question
    Returns:
        it will redirect to  question_template_detailed_view.
    """

    try:
        # Code that may trigger the FOREIGN KEY constraint failed error
        question = Question.objects.filter(id=id).first()
        temp_id = question.template_id.id
        QuestionOptions.objects.filter(question_id=question).delete()
        question.delete()
        messages.success(request, _("Question deleted successfully!"))
        return HttpResponse("<script>reloadMessage();</script>")

    except Question.DoesNotExist:
        error_msg = _("Question not found.")
    except IntegrityError:
        error_msg = _("Failed to delete question: Question template is in use.")
    except ProtectedError:
        error_msg = _("Related entries exist.")
    except Exception as e:
        error_msg = _(f"Unexpected error: {str(e)}")

    return HorillaRedirect(request, message=error_msg)


@login_required
@manager_can_enter(perm="pms.add_questiontemplate")
def question_template_creation(request):
    """
    This view is used to create a question template object.
    Args:
    Returns:
        It will redirect to question_template_detailed_view.
    """
    form = QuestionTemplateForm()
    if request.method == "POST":
        form = QuestionTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Question template created successfully!"))
    return render(
        request,
        "feedback/question_template/question_template_form.html",
        {"form": form},
    )


@login_required
@manager_can_enter(perm="pms.view_questiontemplate")
def question_template_view(request):
    """
    This view is used to  view  question template  object.
    Returns:
        it will redirect to  question_template_detailed_view.
    """
    question_templates = QuestionTemplate.objects.all()
    context = {"form": QuestionTemplateForm, "question_templates": question_templates}
    return render(
        request, "feedback/question_template/question_template_view.html", context
    )


@login_required
@hx_request_required
@manager_can_enter(perm="pms.view_questiontemplate")
def question_template_hx_view(request):
    """
    This view is used to  view  question template  object in htmx.
    """
    question_templates = QuestionTemplate.objects.all()
    context = {"question_templates": question_templates}
    return render(
        request, "feedback/question_template/question_template_list.html", context
    )


@login_required
@manager_can_enter(perm="pms.view_questiontemplate")
def question_template_detailed_view(request, template_id, **kwargs):
    """
    This view is used to  view question template object.
    Args:
        id (int): primarykey of question template
        temp_id (int): primarykey of question_template
    Returns:
        it will redirect to  question_template_detailed_view.
    """

    question_template = QuestionTemplate.objects.filter(id=template_id).first()
    if not question_template:
        messages.error(request, _("Question template does not exist"))
        return redirect("question-template-view")
    questions = question_template.question.all().order_by("-id")
    question_types = ["text", "ratings", "boolean", "multi-choices", "likert"]
    options = QuestionOptions.objects.filter(question_id__in=questions)

    # passing individual form
    question_form_list = [QuestionForm(instance=question) for question in questions]
    context = {
        "question_template": question_template,
        "questions": questions,
        "question_options": options,
        "question_types": question_types,
        "form": QuestionForm,
        "form_list": question_form_list,
    }
    return render(
        request,
        "feedback/question_template/question_template_detailed_view.html",
        context,
    )


@login_required
@manager_can_enter(perm="pms.view_questiontemplate")
def question_template_related_view(request, template_id, **kwargs):
    """
    Read-only detail view for a question template, showing each question's
    type, text, and options (for multiple-choice questions). Used when the
    template is opened via a related-object link (see
    horilla_views/related_link_registry.py), so it renders as a modal
    fragment without the question-creation form or edit/delete actions.
    """

    question_template = QuestionTemplate.objects.filter(id=template_id).first()
    if not question_template:
        messages.error(request, _("Question template does not exist"))
        return redirect("question-template-view")
    questions = question_template.question.all().order_by("-id")
    question_form_list = [QuestionForm(instance=question) for question in questions]
    context = {
        "question_template": question_template,
        "form_list": question_form_list,
    }
    return render(
        request,
        "feedback/question_template/question_template_related_view.html",
        context,
    )


@login_required
@hx_request_required
@manager_can_enter(perm="pms.change_questiontemplate")
def question_template_update(request, template_id):
    """
    This view is used to  update  question template object.
    Args:
        id (int): primarykey of question template
    Returns:
        it will redirect to  question_template_view.

    """
    question_template = QuestionTemplate.objects.filter(id=template_id).first()
    form = QuestionTemplateForm(instance=question_template)
    context = {"form": form}
    if request.method == "POST":
        form = QuestionTemplateForm(request.POST, instance=question_template)
        if form.is_valid():
            form.save()
            messages.success(request, _("Question template updated"))
        context["form"] = form
    return render(
        request, "feedback/question_template/question_template_form.html", context
    )


@login_required
@manager_can_enter(perm="pms.delete_questiontemplate")
def question_template_delete(request, template_id):
    """
    This view is used to  delete  question template object.
    Args:
        id (int): primarykey of question template
    Returns:
        it will redirect to  question_template_view.
    """
    try:
        question_template = QuestionTemplate.objects.get(id=template_id)
        if Feedback.objects.filter(question_template_id=question_template):
            messages.info(request, _("This template is using in a feedback"))
        else:
            question_template.delete()
            messages.success(
                request, _("The question template is deleted successfully !.")
            )
    except QuestionTemplate.DoesNotExist:
        messages.error(request, _("question template not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    return redirect("question-template-hx-view")


@login_required
@manager_can_enter(perm="pms.view_period")
def period_view(request):
    """
    This view is used to view period objects.
    Returns:
        it will return to period_view.
    """

    periods = Period.objects.all()
    context = {
        "periods": periods,
    }
    return render(request, "period/period_view.html", context)


@login_required
@manager_can_enter(perm="pms.view_period")
@hx_request_required
def period_hx_view(request):
    """
    Renders a view displaying periods used for tracking Key Results' completion time.

    Parameters:
    - request: HttpRequest object.

    Returns:
    Renders the 'period/period_list.html' template with a list of historical periods used for tracking Key Results.
    """
    periods = Period.objects.all()
    context = {
        "periods": periods,
    }
    return render(request, "period/period_list.html", context=context)


@login_required
@manager_can_enter(perm="pms.add_period")
@hx_request_required
def period_create(request):
    """
    This view is used to create period objects.
    Returns:
        it will redirect to period_view.
    """
    context = {"form": PeriodForm()}
    if request.method == "POST":
        form = PeriodForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Period creation was Successful "))
        else:
            context["form"] = form
    return render(request, "period/period_create.html", context)


@login_required
@manager_can_enter(perm="pms.change_period")
def period_update(request, period_id):
    """
    This view is used to update period objects.
    Args:
        id (int): primarykey of period
    Returns:
        it will redirect to period_view.
    """

    period = Period.objects.filter(id=period_id).first()
    form = PeriodForm(instance=period)
    context = {"form": form}
    if request.method == "POST":
        form = PeriodForm(request.POST, instance=period)
        if form.is_valid():
            form.save()
            messages.success(request, _("Period updated  Successfully. "))
        else:
            context["form"] = form
    return render(request, "period/period_update.html", context)


@login_required
@manager_can_enter(perm="pms.delete_period")
def period_delete(request, period_id):
    """
    This view is used to delete period objects.
    Args:
        id (int): primarykey of period
    Returns:
        it will redirect to period_view.
    """
    target = request.META.get("HTTP_HX_TARGET")
    try:
        obj_period = Period.objects.get(id=period_id)
        obj_period.delete()
        messages.success(request, _("Period deleted successfully."))
    except Period.DoesNotExist:
        messages.error(request, _("Period not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    if target == "listContainer":
        return HorillaRedirect(request)
    return redirect("period-hx-view")


@login_required
def period_change(request):
    """
    this function is used to detect the period change and
    return the start and end date of that period
    """
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        if request.method == "POST":
            data = json.load(request)
            period_obj = Period.objects.get(id=data)
            start_date = (
                period_obj.start_date.strftime("%Y-%m-%d")
                if period_obj.start_date
                else ""
            )
            end_date = (
                period_obj.end_date.strftime("%Y-%m-%d") if period_obj.end_date else ""
            )
            return JsonResponse({"start_date": start_date, "end_date": end_date})
        return JsonResponse({"failed": "failed"})
    return HttpResponse(status=204)


@login_required
def dashboard_view(request):
    """
    This view is used to view dashboard.
    Returns:
        it will redirect to dashboard.
    """
    user = request.user
    employee = Employee.objects.filter(employee_user_id=user).first()
    is_manager = Employee.objects.filter(
        employee_work_info__reporting_manager_id=employee
    )
    count_key_result = KeyResult.objects.all().count()

    if user.has_perm("pms.view_employeeobjective") and user.has_perm(
        "pms.view_feedback"
    ):
        count_objective = EmployeeObjective.objects.all().count()
        count_feedback = Feedback.objects.all().count()
        okr_at_risk = EmployeeObjective.objects.filter(status="At Risk")
    elif is_manager:
        employees_ids = [employee.id for employee in is_manager]
        count_objective = EmployeeObjective.objects.filter(
            employee_id__in=employees_ids
        ).count()
        count_feedback = Feedback.objects.filter(employee_id__in=employees_ids).count()
        okr_at_risk = EmployeeObjective.objects.filter(
            employee_id__in=employees_ids
        ).filter(status="At Risk")
    else:
        count_objective = EmployeeObjective.objects.filter(employee_id=employee).count()
        count_key_result = EmployeeKeyResult.objects.filter(
            employee_objective_id__employee_id=employee
        ).count()
        count_feedback = Feedback.objects.filter(employee_id=employee).count()
        okr_at_risk = EmployeeObjective.objects.filter(employee_id=employee).filter(
            status="At Risk"
        )
    context = {
        "count_objective": count_objective,
        "count_key_result": count_key_result,
        "count_feedback": count_feedback,
        "okr_at_risk": okr_at_risk,
    }
    return render(request, "dashboard/pms_dashboard.html", context)


@login_required
def dashboard_objective_status(request):
    """objective dashboard data"""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    data = {"message": _("No records available at the moment.")}
    if is_ajax and request.method == "GET":
        objective_status = EmployeeObjective.STATUS_CHOICES
        for status in objective_status:
            objectives = EmployeeObjective.objects.filter(
                status=status[0], archive=False
            )
            objectives_count = filtersubordinates(
                request, queryset=objectives, perm="pms.view_employeeobjective"
            ).count()
            if objectives_count:
                data.setdefault("objective_label", []).append(status[1])
                data.setdefault("objective_value", []).append(objectives_count)
    return JsonResponse(data)


@login_required
def dashboard_key_result_status(request):
    """key result dashboard data"""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    data = {"message": _("No records available at the moment.")}
    if is_ajax and request.method == "GET":
        key_result_status = EmployeeKeyResult.STATUS_CHOICES
        for i in key_result_status:
            key_results = EmployeeKeyResult.objects.filter(status=i[0])
            key_results_count = filtersubordinates(
                request,
                queryset=key_results,
                perm="pms.view_employeekeyresult",
                field="employee_objective_id__employee_id",
            ).count()
            if key_results_count:
                data.setdefault("key_result_label", []).append(i[1])
                data.setdefault("key_result_value", []).append(key_results_count)
    return JsonResponse(data)


@login_required
def dashboard_feedback_status(request):
    """feedback dashboard data"""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    data = {"message": _("No records available at the moment.")}
    if is_ajax and request.method == "GET":
        feedback_status = Feedback.STATUS_CHOICES
        for i in feedback_status:
            feedbacks = Feedback.objects.filter(status=i[0])
            feedback_count = filtersubordinates(
                request, queryset=feedbacks, perm="pms.view_feedback"
            ).count()
            if feedback_count:
                data.setdefault("feedback_label", []).append(i[1])
                data.setdefault("feedback_value", []).append(feedback_count)
    return JsonResponse(data)


def filtersubordinates(request, queryset, perm=None, field=None):
    """
    This method is used to filter out subordinates queryset element.
    """
    user = request.user
    if user.has_perm(perm):
        return queryset
    manager = Employee.objects.filter(employee_user_id=user).first()
    if manager:
        if field is not None:
            queryset = queryset.filter(
                **{f"{field}__employee_work_info__reporting_manager_id": manager}
            ) | queryset.filter(**{field: manager})
        else:
            queryset = queryset.filter(
                employee_id__employee_work_info__reporting_manager_id=manager
            ) | queryset.filter(employee_id=manager)
        return queryset
    else:
        queryset = queryset.filter(employee_id=user.employee_get)
        return queryset


@login_required
def create_period(request):
    """
    This is an ajax method to return json response to create stage related
    to the project in the task-all form fields
    """
    company_id = request.session.get("selected_company")
    companies = (
        Company.objects.filter(id=company_id)
        if company_id != "all"
        else Company.objects.all()
    )

    if request.method == "GET":
        form = PeriodForm(initial={"company_id": companies})
    if request.method == "POST":
        data = request.POST.copy()
        data.setlist("company_id", list(companies.values_list("id", flat=True)))
        form = PeriodForm(data)
        if form.is_valid():
            instance = form.save()
            return JsonResponse(
                {
                    "id": instance.id,
                    "name": instance.period_name,
                    "start_date": instance.start_date,
                    "end_date": instance.end_date,
                }
            )
        errors = form.errors.as_json()
        return JsonResponse({"errors": errors})
    return render(request, "okr/create_period.html", context={"form": form})


@login_required
def objective_bulk_archive(request):
    """
    This method is used to archive/un-archive bulk objectivs
    """
    ids = request.POST.get("ids", "[]")
    ids = json.loads(ids)
    is_active = False
    message = _("un-archived")
    if request.GET.get("is_active") == "False":
        is_active = True
        message = _("archived")
    for objective_id in ids:
        objective_obj = EmployeeObjective.objects.get(id=objective_id)
        objective_obj.archive = is_active
        objective_obj.save()
        messages.success(
            request,
            _("{objective} is {message}").format(
                objective=objective_obj, message=message
            ),
        )
    return JsonResponse({"message": "Success"})


@login_required
@manager_can_enter(perm="pms.delete_employeeobjective")
def objective_bulk_delete(request):
    """
    This method is used to bulk delete objective
    """
    ids = request.POST.get("ids", "[]")
    ids = json.loads(ids)
    for objective_id in ids:
        try:
            objective = EmployeeObjective.objects.get(id=objective_id)
            if objective.status == "Not Started" or objective.status == "Closed":
                objective.delete()
                messages.success(
                    request,
                    _("%(employee)s's %(objective)s deleted")
                    % {
                        "objective": objective.objective,
                        "employee": objective.employee_id,
                    },
                )
            else:
                messages.warning(
                    request,
                    _("You can't delete objective %(objective)s with status %(status)s")
                    % {"objective": objective.objective, "status": objective.status},
                )
        except EmployeeObjective.DoesNotExist:
            messages.error(request, _("Objective not found."))

    return JsonResponse({"message": "Success"})


@login_required
def feedback_bulk_archive(request):
    """
    This method is used to archive/un-archive bulk feedbacks
    """

    ids = request.POST.get("ids", "[]")
    announy_ids = request.POST.get("announy_ids", "[]")
    ids = json.loads(ids)
    announy_ids = json.loads(announy_ids)
    is_active = False
    message = _("un-archived")
    if request.GET.get("is_active") == "False":
        is_active = True
        message = _("archived")
    for feedback_id in ids:
        feedback_id = Feedback.objects.get(id=feedback_id)
        feedback_id.archive = is_active
        feedback_id.save()
        messages.success(
            request,
            _("{feedback} is {message}").format(feedback=feedback_id, message=message),
        )

    for feedback_id in announy_ids:
        feedback_id = AnonymousFeedback.objects.get(id=feedback_id)
        feedback_id.archive = is_active
        feedback_id.save()
        messages.success(
            request,
            _("{feedback} is {message}").format(
                feedback=feedback_id.feedback_subject, message=message
            ),
        )
    return JsonResponse({"message": "Success"})


@login_required
@manager_can_enter(perm="pms.delete_feedback")
def feedback_bulk_delete(request):
    """
    This method is used to bulk delete feedbacks
    """
    ids = request.POST.get("ids", "[]")
    announy_ids = request.POST.get("announy_ids", "[]")
    ids = json.loads(ids)
    announy_ids = json.loads(announy_ids)
    for feedback_id in ids:
        try:
            feedback = Feedback.objects.get(id=feedback_id)
            if feedback.status == "Closed" or feedback.status == "Not Started":
                feedback.delete()
                messages.success(
                    request,
                    _("Feedback %(review_cycle)s deleted successfully!")
                    % {"review_cycle": feedback.review_cycle},
                )
            else:
                messages.warning(
                    request,
                    _(
                        "You can't delete feedback %(review_cycle)s with status %(status)s"
                    )
                    % {
                        "review_cycle": feedback.review_cycle,
                        "status": feedback.status,
                    },
                )

        except Feedback.DoesNotExist:
            messages.error(request, _("Feedback not found."))
    for feedback_id in announy_ids:
        feedback_id = AnonymousFeedback.objects.get(id=feedback_id)
        message = _("Deleted")
        # feedback_id.archive = is_active
        feedback_id.delete()
        messages.success(
            request,
            _("{feedback} is {message}").format(
                feedback=feedback_id.feedback_subject, message=message
            ),
        )
    return JsonResponse({"message": "Success"})


@login_required
def objective_select(request):
    """
    This method is used to return all the id of the employees to select the employee row
    """
    page_number = request.GET.get("page")
    table = request.GET.get("tableName")
    user = request.user.employee_get
    employees = EmployeeObjective.objects.filter(employee_id=user, archive=False)
    if page_number == "all":
        if table == "all":
            if request.user.has_perm("pms.view_employeeobjective"):
                employees = EmployeeObjective.objects.filter(archive=False)
            else:
                employees = EmployeeObjective.objects.filter(
                    employee_id__employee_user_id=request.user
                ) | EmployeeObjective.objects.filter(
                    employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
                )
        else:
            employees = EmployeeObjective.objects.filter(
                employee_id=user, archive=False
            )

    employee_ids = [str(emp.id) for emp in employees]
    total_count = employees.count()

    context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def objective_select_filter(request):
    """
    This method is used to return all the ids of the filtered employees
    """
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    table = request.GET.get("tableName")
    user = request.user.employee_get
    context = {}

    employee_filter = ObjectiveFilter(filters, queryset=EmployeeObjective.objects.all())
    if page_number == "all":
        if table == "all":
            if request.user.has_perm("pms.view_employeeobjective"):
                employee_filter = ObjectiveFilter(
                    filters, queryset=EmployeeObjective.objects.all()
                )
            else:
                employee_filter = ObjectiveFilter(
                    filters,
                    queryset=EmployeeObjective.objects.filter(
                        employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
                    ),
                )
        else:
            employee_filter = ObjectiveFilter(
                filters, queryset=EmployeeObjective.objects.filter(employee_id=user)
            )
        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
def anonymous_feedback_add(request):
    """
    View function for adding anonymous feedback.

    Parameters:
    - request: HttpRequest object.

    Returns:
    - If request method is POST and form is valid:
        Saves the submitted feedback and sends a notification if based on an employee.
        Returns a JavaScript snippet to reload the page.
    - If request method is GET or form is invalid:
        Renders the 'anonymous/anonymous_feedback_form.html' template with the feedback form.
    """
    if request.method == "POST":
        form = AnonymousFeedbackForm(request.POST)
        anonymous_id = request.user.id

        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.anonymous_feedback_id = anonymous_id
            feedback.save()
            if feedback.based_on == "employee":
                try:
                    notify.send(
                        HorillaUser.objects.filter(username="Horilla Bot").first(),
                        recipient=feedback.employee_id.employee_user_id,
                        verb="You received an anonymous feedback!",
                        verb_ar="لقد تلقيت تقييمًا مجهولًا!",
                        verb_de="Sie haben anonymes Feedback erhalten!",
                        verb_es="¡Has recibido un comentario anónimo!",
                        verb_fr="Vous avez reçu un feedback anonyme!",
                        redirect=reverse("feedback-view"),
                        icon="bag-check",
                    )
                except:
                    pass
            return HorillaRedirect(request)
    else:
        form = AnonymousFeedbackForm()

    context = {"form": form, "create": True}
    return render(request, "anonymous/anonymous_feedback_form.html", context)


@login_required
@hx_request_required
def edit_anonymous_feedback(request, obj_id):
    """
    View function for editing anonymous feedback.

    Parameters:
    - request: HttpRequest object.
    - id: ID of the AnonymousFeedback instance to be edited.

    Returns:
    - If request method is POST and form is valid:
        Saves the edited feedback.
        Returns a JavaScript snippet to reload the page.
    - If request method is GET or form is invalid:
        Renders the 'anonymous/anonymous_feedback_form.html' template with the feedback form pre-filled with existing data.
    """
    feedback = AnonymousFeedback.objects.get(id=obj_id)
    # checking feedback owner
    if str(request.user.id) == feedback.anonymous_feedback_id or request.user.has_perm(
        "pms.change_anonymousfeedback"
    ):
        form = AnonymousFeedbackForm(instance=feedback)
        anonymous_id = request.user.id
        if request.method == "POST":
            form = AnonymousFeedbackForm(request.POST, instance=feedback)
            if form.is_valid():
                feedback = form.save(commit=False)
                feedback.anonymous_feedback_id = anonymous_id
                feedback.save()
                return HorillaRedirect(request)
        context = {"form": form, "create": False}
        return render(request, "anonymous/anonymous_feedback_form.html", context)
    else:
        messages.info(request, _("You are don't have permissions."))
        return HorillaRedirect(request)


@login_required
def archive_anonymous_feedback(request, obj_id):
    """
    this function is used to archive the feedback for employee
    args:
        id(int): primarykey of feedback
    """

    feedback = AnonymousFeedback.objects.filter(id=obj_id).first()
    if not feedback:
        return HorillaRedirect(
            request, message=_("No Anonymous Feedback found matching the query.")
        )

    # checking feedback owner
    if str(request.user.id) == feedback.anonymous_feedback_id or request.user.has_perm(
        "pms.anonymousfeedback"
    ):
        if feedback.archive:
            feedback.archive = False
            feedback.save()
            messages.info(request, _("Feedback un-archived successfully!."))
        elif not feedback.archive:
            feedback.archive = True
            feedback.save()
            messages.info(request, _("Feedback archived successfully!."))

    else:
        messages.info(request, _("You are don't have permissions."))
    return redirect(reverse("feedback-view"))


@login_required
@permission_required("pms.delete_anonymousfeedback")
def delete_anonymous_feedback(request, obj_id):
    """
    Deletes an anonymous feedback entry.

    Parameters:
    - request: HttpRequest object.
    - id: ID of the AnonymousFeedback instance to be deleted.

    Returns:
    Redirects to the feedback list view after deleting the feedback.
    """
    try:
        feedback = AnonymousFeedback.objects.get(id=obj_id)
        feedback.delete()
        messages.success(request, _("Feedback deleted successfully!"))

    except IntegrityError:
        messages.error(
            request, _("Failed to delete feedback: Feedback template is in use.")
        )

    except AnonymousFeedback.DoesNotExist:
        messages.error(request, _("Feedback not found."))

    except ProtectedError:
        messages.error(request, _("Related entries exists"))

    return redirect(reverse("feedback-view"))


@login_required
@hx_request_required
def view_single_anonymous_feedback(request, obj_id):
    """
    Renders a view to display a single anonymous feedback entry.

    Parameters:
    - request: HttpRequest object.
    - id: ID of the AnonymousFeedback instance to be displayed.

    Returns:
    Renders the 'anonymous/single_view.html' template with the details of the specified anonymous feedback.
    """
    feedback = AnonymousFeedback.objects.get(id=obj_id)
    return render(request, "anonymous/single_view.html", {"feedback": feedback})


@login_required
@hx_request_required
def employee_keyresult_creation(request, emp_obj_id):
    """
    This view is for employee keyresult creation , and returns a employee keyresult form.
    Returns:
        GET:
            employee keyresult form
        POST:
            employee keyresult created, and returnes to employee objective details view
    """
    emp_objective = EmployeeObjective.objects.get(id=emp_obj_id)
    if (
        request.user.employee_get in emp_objective.objective_id.managers.all()
        or request.user.has_perm("pms.add_employeekeyresult")
    ):
        employee = emp_objective.employee_id
        data = request.GET.copy()
        # Convert QueryDict to a regular dictionary
        cleaned_data = {
            key: value if len(value) > 1 else value[0] for key, value in data.lists()
        }
        if not cleaned_data.get("employee_objective_id"):
            cleaned_data["employee_objective_id"] = emp_obj_id
        emp_key_result = EmployeeKeyResultForm(initial=cleaned_data)
        if request.method == "POST":
            emp_key_result = EmployeeKeyResultForm(request.POST)
            if emp_key_result.is_valid():
                emp_key_result.save()
                emp_objective.update_objective_progress()
                key_result = emp_key_result.cleaned_data["key_result_id"]

                emp_objective.key_result_id.add(key_result)
                # assignees = emp_key_result.cleaned_data['assignees']
                # start_date =emp_key_result.cleaned_data['start_date']

                messages.success(request, _("Key result assigned sucessfully."))

                notify.send(
                    request.user.employee_get,
                    recipient=employee.employee_user_id,
                    verb="You got an Key Result!.",
                    verb_ar="لقد حصلت على نتيجة رئيسية!",
                    verb_de="Du hast ein Schlüsselergebnis erreicht!",
                    verb_es="¡Has conseguido un Resultado Clave!",
                    verb_fr="Vous avez obtenu un Résultat Clé!",
                    redirect=reverse(
                        "objective-detailed-view",
                        kwargs={"obj_id": emp_objective.objective_id.id},
                    ),
                )
                return HorillaRedirect(request)
        context = {
            "form": emp_key_result,
            "emp_objective": emp_objective,
        }
        return render(request, "okr/key_result/kr_form.html", context=context)
    else:
        messages.info(request, _("You are don't have permissions."))
        return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter(perm="pms.add_employeekeyresult")
def employee_keyresult_update(request, kr_id):
    """
    This function is for update employee keyresult, and returns a employee keyresult form.
    Returns:
        GET:
            employee keyresult form
        POST:
            employee keyresult updated, and returnes to employee objective details view
    """
    emp_kr = EmployeeKeyResult.objects.get(id=kr_id)
    employee = emp_kr.employee_objective_id.employee_id
    data = request.GET.copy()
    if len(data) > 1:
        # Convert QueryDict to a regular dictionary
        cleaned_data = {
            key: value if len(value) > 1 else value[0] for key, value in data.lists()
        }
        emp_key_result = EmployeeKeyResultForm(initial=cleaned_data, instance=emp_kr)
    else:
        emp_key_result = EmployeeKeyResultForm(instance=emp_kr)
    if request.method == "POST":
        emp_key_result = EmployeeKeyResultForm(request.POST, instance=emp_kr)
        if emp_key_result.is_valid():
            emp_key_result.save()
            emp_kr.employee_objective_id.update_objective_progress()
            messages.success(request, _("Key result Updated sucessfully."))
            notify.send(
                request.user.employee_get,
                recipient=employee.employee_user_id,
                verb="Your Key Result updated.",
                verb_ar="تم تحديث نتيجتك الرئيسية.",
                verb_de="Ihr Schlüsselergebnis wurde aktualisiert.",
                verb_es="Se ha actualizado su Resultado Clave.",
                verb_fr="Votre Résultat Clé a été mis à jour.",
                redirect=reverse(
                    "objective-detailed-view",
                    kwargs={"obj_id": emp_kr.employee_objective_id.objective_id.id},
                ),
            )
            return HorillaRedirect(request)

    context = {
        "form": emp_key_result,
        "update": True,
    }
    return render(request, "okr/key_result/kr_form.html", context=context)


@login_required
def delete_employee_keyresult(request, kr_id):
    """
    This function is used to delete the employee key result
        args:
            kr_id(int) : pimarykey of EmployeeKeyResult
        return:
            redirect to detailed of employee objective
    """
    emp_kr = EmployeeKeyResult.objects.filter(id=kr_id).first()
    if not emp_kr:
        return HorillaRedirect(
            request, message=_("No Employee Key Result found matching the query.")
        )

    # employee = emp_kr.employee_id
    objective = emp_kr.employee_objective_id.objective_id
    if not (
        request.user.has_perm("pms.delete_objective")
        or request.user.has_perm("pms.delete_employeeobjective")
        or request.user.has_perm("pms.delete_employeekeyresult")
        or request.user.employee_get in objective.managers.all()
    ):
        messages.info(request, _("You dont have permission"))
        return HorillaRedirect(request)

    emp_objective = emp_kr.employee_objective_id
    emp_kr.delete()
    emp_objective.update_objective_progress()
    # objective.assignees.remove(employee)
    messages.success(request, _("Objective deleted successfully!."))
    if request.GET.get("dashboard"):
        return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")
    return redirect(f"/pms/objective-detailed-view/{objective.id}")


@login_required
def employee_keyresult_update_status(request, kr_id):
    """
    This function is used to delete the employee key result
        args:
            kr_id(int) : pimarykey of EmployeeKeyResult
        return:
            redirect to detailed of employee objective
    """
    emp_kr = EmployeeKeyResult.objects.filter(id=kr_id).first()
    if not emp_kr:

        return HorillaRedirect(
            request, message=_("No Employee Key Result found matching the query.")
        )

    if (
        request.user.has_perm("pms.change_objective")
        or request.user.has_perm("pms.change_employeeobjective")
        or request.user.has_perm("pms.change_employeekeyresult")
        or request.user.employee_get
        in emp_kr.employee_objective_id.objective_id.managers.all()
        or (
            emp_kr.employee_objective_id.objective_id.self_employee_progress_update
            and (emp_kr.employee_objective_id.employee_id == request.user.employee_get)
        )
    ):
        status = request.POST.get("key_result_status")
        emp_kr.status = status
        emp_kr.save()
        messages.success(request, _("Key result sattus changed to {}.").format(status))
        return redirect(
            f"/pms/kr-table-view/{emp_kr.employee_objective_id.id}?&objective_id={emp_kr.employee_objective_id.objective_id.id}"
        )

    messages.info(request, _("You dont have permission"))
    return HorillaRedirect(request)


@login_required
def key_result_current_value_update(request):
    """
    This method is used to update keyresult current value
    """
    try:
        current_value = eval_validate(request.POST.get("current_value"))
        emp_kr_id = eval_validate(request.POST.get("emp_key_result_id"))
        emp_kr = EmployeeKeyResult.objects.get(id=emp_kr_id)
        if (
            request.user.has_perm("pms.change_objective")
            or request.user.has_perm("pms.change_employeeobjective")
            or request.user.has_perm("pms.change_employeekeyresult")
            or request.user.employee_get
            in emp_kr.employee_objective_id.objective_id.managers.all()
            or (
                emp_kr.employee_objective_id.objective_id.self_employee_progress_update
                and (
                    emp_kr.employee_objective_id.employee_id
                    == request.user.employee_get
                )
            )
        ):
            current_value = max(0, current_value)
            emp_kr.current_value = current_value
            emp_kr.save()
            emp_kr.employee_objective_id.update_objective_progress()
            messages.success(request, _("Value updated"))
        else:
            messages.info(
                request, _("You dont have permission to update the current value")
            )
        # Return JSON response with updated progress
        return JsonResponse(
            {
                "type": "sucess",
                "progress": int(emp_kr.employee_objective_id.progress_percentage),
                "kr_progress": int(emp_kr.progress_percentage),
                "pk": emp_kr.employee_objective_id.pk,
            }
        )
    except Exception as e:
        print(e)
        return JsonResponse({"type": "error"})


@login_required
def get_keyresult_data(request):
    """
    Function to get the data of keyresult and return to the form.
    """
    key_id = (
        request.GET.get("key_result_id") if request.GET.get("key_result_id") else None
    )
    key_result = KeyResult.objects.filter(id=key_id).first()
    if key_result:
        if request.GET.get("data-update") == "target_value":
            return HttpResponse(
                f'<input type="number" name="target_value" value="{key_result.target_value}" class="oh-input w-100 form-control test test" placeholder="Target Value" id="id_target_value">'
            )
        if request.GET.get("data-update") == "end_date":
            start_date = datetime.datetime.strptime(
                request.GET.get("start_date"), "%Y-%m-%d"
            )
            end_date = (start_date + relativedelta(days=key_result.duration)).date()
            return HttpResponse(
                f'<input type="date" name="end_date" value="{end_date}" class="oh-input w-100 form-control" placeholder="End Date" id="id_end_date">'
            )
    else:
        if request.GET.get("data-update") == "target_value":
            return HttpResponse(
                f'<input type="number" name="target_value" value="" class="oh-input w-100 form-control test test" placeholder="Target Value" id="id_target_value">'
            )
        if request.GET.get("data-update") == "end_date":
            return HttpResponse(
                f'<input type="date" name="end_date" value="" class="oh-input w-100 form-control" placeholder="End Date" id="id_end_date">'
            )
    return HttpResponse("")


@login_required
def view_meetings(request):
    """
    This view is used to view the meeting ,
    Returns:
        it will redirect to view_meetings.html .
    """
    previous_data = request.GET.urlencode()
    meetings = Meetings.objects.filter(is_active=True)
    if not request.user.has_perm("pms.view_meetings"):
        employee_id = request.user.employee_get
        meetings = meetings.filter(
            Q(employee_id=employee_id) | Q(manager=employee_id)
        ).distinct()
    meetings = meetings.order_by("-id")
    filter_form = MeetingsFilter()

    meetings = paginator_qry(meetings, request.GET.get("page"))
    requests_ids = json.dumps([instance.id for instance in meetings.object_list])
    data_dict = parse_qs(previous_data)
    get_key_instances(Meetings, data_dict)
    all_meetings = Meetings.objects.filter()

    context = {
        "all_meetings": all_meetings,
        "meetings": meetings,
        "filter_form": filter_form.form,
        "requests_ids": requests_ids,
    }
    return render(request, "meetings/view_meetings.html", context)


@login_required
@hx_request_required
def create_meetings(request):
    """
    This view is used to create the meeting ,
    Returns:
        Get:
            it renders form.html to create the meeting.
        Post:
            it will redirect to view_meetings.html .
    """
    instance_id = eval_validate(str(request.GET.get("instance_id")))
    instance = None
    initial = {"manager": request.user.employee_get, "employee_id": None}
    if instance_id and isinstance(instance_id, int):
        instance = Meetings.objects.filter(id=instance_id).first()
        initial = {}
    form = MeetingsForm(instance=instance, initial=initial)
    if request.method == "POST":
        form = MeetingsForm(request.POST, instance=instance)
        if form.is_valid():
            is_create = instance is None
            instance = form.save()
            managers = [
                manager.employee_user_id for manager in form.cleaned_data["manager"]
            ]
            answer_employees = [
                answer_emp.employee_user_id
                for answer_emp in form.cleaned_data["answer_employees"]
            ]
            employees = form.cleaned_data["employee_id"]
            employees = [
                employee.employee_user_id
                for employee in employees.exclude(
                    id__in=form.cleaned_data["answer_employees"]
                )
            ]

            if is_create:
                try:
                    notify.send(
                        request.user.employee_get,
                        recipient=answer_employees,
                        verb=f"You have been added as an answerable employee for the meeting {instance.title}",
                        verb_ar=f"لقد تمت إضافتك كموظف مسؤول عن الاجتماع {instance.title}",
                        verb_de=f"Du wurden als Mitarbeiter zum Ausfüllen für das {instance.title}-Meeting hinzugefügt",
                        verb_es=f"Se le ha agregado como empleado responsable de la reunión {instance.title}",
                        verb_fr=f"Vous avez été ajouté en tant que employé responsable pour la réunion {instance.title}",
                        icon="information",
                        redirect=reverse("view-meetings") + f"?search={instance.title}",
                    )
                except Exception:
                    pass

                try:
                    notify.send(
                        request.user.employee_get,
                        recipient=employees,
                        verb=f"You have been added to the meeting {instance.title}",
                        verb_ar=f"لقد تمت إضافتك إلى اجتماع {instance.title}.",
                        verb_de=f"Sie wurden zur {instance.title} Besprechung hinzugefügt",
                        verb_es=f"Te han agregado a la reunión {instance.title}",
                        verb_fr=f"Vous avez été ajouté à la réunion {instance.title}",
                        icon="information",
                        redirect=reverse("view-meetings") + f"?search={instance.title}",
                    )
                except Exception:
                    pass

                try:
                    notify.send(
                        request.user.employee_get,
                        recipient=managers,
                        verb=f"You have been added as a manager for the meeting {instance.title}",
                        verb_ar=f"لقد تمت إضافتك كمدير للاجتماع {instance.title}",
                        verb_de=f"Sie wurden als Manager für das Meeting {instance.title} hinzugefügt",
                        verb_es=f"Se le ha agregado como administrador de la reunión {instance.title}",
                        verb_fr=f"Vous avez été ajouté en tant que responsable de réunion {instance.title}",
                        icon="information",
                        redirect=reverse("view-meetings") + f"?search={instance.title}",
                    )
                except Exception:
                    pass

            messages.success(request, _("Meeting added successfully"))
    return render(
        request,
        "meetings/form.html",
        {
            "form": form,
        },
    )


@login_required
@hx_request_required
@permission_required("pms.change_meetings")
def archive_meetings(request, obj_id):
    """
    This view is used to archive and unarchive the meeting ,
    Args:
        meet_id(int) : primarykey of the meeting.
        employee_id(int) : primarykey of the employee
    Returns:
        it will redirect to view_meetings.html .
    """
    meeting = Meetings.find(obj_id)
    if not meeting:

        return HorillaRedirect(
            request, message=_("No Meetings found matching the query.")
        )

    meeting.is_active = not meeting.is_active
    meeting.save()
    message = (
        _("Meeting unarchived successfully")
        if meeting.is_active
        else _("Meeting archived successfully")
    )
    messages.success(request, message)
    return HttpResponse("")


@login_required
@hx_request_required
@permission_required("pms.change_meetings")
def meeting_manager_remove(request, meet_id, manager_id):
    """
    This view is used to remove the manager from the meeting ,
    Args:
        meet_id(int) : primarykey of the meeting.
        employee_id(int) : primarykey of the employee
    Returns:
        it will redirect to view_meetings.html .
    """
    meeting = Meetings.find(meet_id)
    if not meeting:

        return HorillaRedirect(
            request, message=_("No Meetings found matching the query.")
        )

    meeting.manager.remove(manager_id)
    meeting.save()
    messages.success(
        request, _("Manager has been successfully removed from the meeting.")
    )
    return HttpResponse("")


@login_required
@hx_request_required
@permission_required("pms.change_meetings")
def meeting_employee_remove(request, meet_id, employee_id):
    """
    This view is used to remove the employees from the meeting ,
    Args:
        meet_id(int) : primarykey of the meeting.
        employee_id(int) : primarykey of the employee
    Returns:
        it will redirect to view_meetings.html .
    """
    meeting = Meetings.find(meet_id)
    if not meeting:

        return HorillaRedirect(
            request, message=_("No Meetings found matching the query.")
        )

    meeting.employee_id.remove(employee_id)
    meeting.save()
    messages.success(
        request, _("Employee has been successfully removed from the meeting.")
    )
    return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")


@login_required
@hx_request_required
def filter_meetings(request):
    """
    This view is used to filter the meeting ,
    Returns:
        it will render to meeting_list.html .
    """
    previous_data = request.GET.urlencode()
    filter_obj = MeetingsFilter(request.GET).qs

    if not request.user.has_perm("pms.view_meetings"):
        employee_id = request.user.employee_get
        filter_obj = filter_obj.filter(
            Q(employee_id=employee_id) | Q(manager=employee_id)
        ).distinct()
    if (
        request.GET.get("is_active") is None
        or request.GET.get("is_active") == "unknown"
    ):
        filter_obj = filter_obj.filter(is_active=True)
    filter_obj = filter_obj.order_by("-id")

    filter_obj = sortby(request, filter_obj, "sortby")
    filter_obj = paginator_qry(filter_obj, request.GET.get("page"))
    requests_ids = json.dumps([instance.id for instance in filter_obj.object_list])

    data_dict = parse_qs(previous_data)
    get_key_instances(EmployeeObjective, data_dict)

    return render(
        request,
        "meetings/meetings_list.html",
        {
            "meetings": filter_obj,
            "pd": previous_data,
            "filter_dict": data_dict,
            "requests_ids": requests_ids,
        },
    )


@login_required
@meeting_manager_can_enter("pms.change_meetings")
def add_response(request, obj_id):
    """
    This view is used to add the MoM to the meeting ,
    Args:
        id(int) : primarykey of the meeting.
    Returns:
        it will redirect to view_meetings.html .
    """
    meeting = Meetings.find(obj_id)
    if request.method == "POST":
        response = request.POST.get("response")
        meeting.response = response
        meeting.save()
        messages.success(
            request, _("Minutes of Meeting (MoM) have been created successfully")
        )
    return render(request, "meetings/mom_form.html", {"meeting": meeting})


@login_required
@hx_request_required
@meeting_manager_can_enter("pms.change_meetings", answerable=True)
def meeting_answer_get(request, id, **kwargs):
    """
    This view is used to render the Meeting questions ,
    Args:
        id(int) : primarykey of the meeting.
    Returns:
        it will redirect to meeting_answer.html .
    """

    employee = request.user.employee_get
    if employee_id := request.GET.get("emp_id"):
        employee = Employee.objects.filter(id=employee_id).first()
    meeting = Meetings.objects.get(id=id)
    answer = MeetingsAnswer.objects.filter(meeting_id=meeting, employee_id=employee)
    questions = meeting.question_template.question.all()
    options = QuestionOptions.objects.all()
    meeting_employees = meeting.manager.all() | meeting.employee_id.all()

    if answer or request.GET.get("emp_id"):
        return redirect("meeting-answer-view", id=meeting.id, emp_id=employee.id)

    if not employee in meeting_employees:
        messages.info(request, _("You are not allowed to answer"))
        return redirect(view_meetings)

    context = {
        "questions": questions,
        "options": options,
        "meeting": meeting,
    }

    return render(request, "meetings/meeting_answer.html", context)


@login_required
@meeting_manager_can_enter("pms.change_meetings", answerable=True)
def meeting_answer_post(request, id):
    """
    This view is used to create meeting answer ,
    Args:
        id(int) : primarykey of the meeting.
    Returns:
        it will redirect to view_meeting if the form was success full.
    """

    meeting = Meetings.find(id)
    if not meeting:
        return HorillaRedirect(
            request, message=_("No Meetings found matching the query.")
        )

    employee = request.user.employee_get
    question_template = meeting.question_template.question.all()

    if request.method == "POST":
        for question in question_template:
            if request.POST.get(f"answer{question.id}"):
                answer = request.POST.get(f"answer{question.id}")
                MeetingsAnswer.objects.get_or_create(
                    answer={"answer": answer},
                    question_id=question,
                    meeting_id=meeting,
                    employee_id=employee,
                )
        messages.success(
            request,
            _("Questions for meeting %(meeting)s has been answered successfully!.")
            % {"meeting": meeting.title},
        )
        return redirect(reverse("view-meetings"))


@login_required
@meeting_manager_can_enter("pms.change_meetings", answerable=True)
def meeting_answer_view(request, id, emp_id, **kwargs):
    """
    This view is used to view the meeting for employee.
    Args:
        id(int) : primarykey of the meeting.
        emp_id(int) : id of the employee
    Returns:
        it will return meeting answer object to meeting_answer_view.
    """

    meeting = Meetings.find(id)
    employee = Employee.objects.filter(id=emp_id).first()
    if not meeting or not employee:
        return HorillaRedirect(
            request,
            message=_("No %(class_name)s found matching the query.")
            % {"class_name": "Meetings" if not meeting else "Employee"},
        )

    answers = MeetingsAnswer.objects.filter(meeting_id=meeting, employee_id=employee)

    context = {
        "answers": answers,
        "meeting": meeting,
    }
    return render(request, "meetings/meeting_answer_view.html", context)


@login_required
@hx_request_required
@meeting_manager_can_enter("pms.change_meetings", answerable=True)
def meeting_question_template_view(request, meet_id):
    """
    This view is used to view the activity sidebar page for employee.
    Args:
        id(int) : primarykey of the meeting.
    Returns:
        it will return meeting answer object to meeting_question_template_view.
    """
    employee = request.user.employee_get
    meeting = Meetings.objects.get(id=meet_id)
    answer = MeetingsAnswer.objects.filter(meeting_id=meeting, employee_id=employee)
    is_answered = False
    if answer:
        is_answered = True
    context = {
        "is_answered": is_answered,
        "meeting": meeting,
    }
    return render(request, "meetings/meeting_question_template_view.html", context)


@login_required
def meeting_single_view(request, id):
    meeting = Meetings.find(id)
    if not meeting:
        return HorillaRedirect(
            request, message=_("No Meetings found matching the query.")
        )

    context = {"meeting": meeting}
    requests_ids_json = request.GET.get("requests_ids")
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, id)
        context["requests_ids"] = requests_ids_json
        context["previous"] = previous_id
        context["next"] = next_id
    return render(request, "meetings/meeting_single_view.html", context)


@login_required
@hx_request_required
@owner_can_enter("pms.view_feedback", Employee)
def performance_tab(request, pk):
    """
    This function is used to view performance tab of an employee in employee individual
    & profile view.

    Parameters:
    request (HttpRequest): The HTTP request object.
    emp_id (int): The id of the employee.

    Returns: return performance-tab template

    """
    feedback_own = Feedback.objects.filter(employee_id=pk, archive=False)

    today = datetime.datetime.today()
    context = {
        "self_feedback": feedback_own,
        "current_date": today,
    }
    return render(request, "tabs/performance-tab.html", context=context)


@login_required
def dashboard_feedback_answer(request):
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    employee = request.user.employee_get
    feedback_requested = Feedback.objects.filter(
        Q(manager_id=employee, manager_id__is_active=True)
        | Q(colleague_id=employee, colleague_id__is_active=True)
        | Q(subordinate_id=employee, subordinate_id__is_active=True)
    ).distinct()
    feedbacks = feedback_requested.exclude(feedback_answer__employee_id=employee)
    feedbacks = paginator_qry(feedbacks, page_number)

    return render(
        request,
        "dashboard/feedback_answer.html",
        {
            "feedbacks": feedbacks,
            "pd": previous_data,
            "current_date": datetime.date.today(),
        },
    )


@login_required
@permission_required("pms.delete_bonuspointsetting")
def delete_bonus_point_setting(request, pk):
    """
    Delete bonus point setting
    """
    try:
        BonusPointSetting.objects.get(id=pk).delete()
        messages.success(request, _("Bonus Point Setting deleted"))
    except Exception as e:
        logger.error(e)
        messages.error(request, _("Something went wrong"))
    return redirect(reverse("bonus-point-setting-list-view"))


@login_required
@permission_required("pms.delete_employeebonuspoint")
def delete_employee_bonus_point(request, pk):
    """
    Automation delete view
    """
    try:
        bonus = EmployeeBonusPoint.objects.get(id=pk)
        bonus.delete()
        messages.success(request, _(f"{bonus} deleted"))
    except Exception as e:
        logger.error(e)
        messages.error(request, _("Something went wrong"))
    return redirect(reverse("employee-bonus-point-list-view"))


@login_required
def bonus_setting_form_values(request):
    """
    This method is to render `mail to` fields
    """
    model_path = request.GET.get("model")
    if model_path is None:
        return JsonResponse(
            {
                "choices": [],
                "mail_details_choice": [],
                "serialized_form": {},
            }
        )
    to_fields, mail_details_choice, model_class = generate_choices(model_path)

    class InstantModelForm(forms.ModelForm):
        """
        InstantModelForm
        """

        class Meta:
            model = model_class
            fields = "__all__"

    serialized_form = serialize_form(InstantModelForm(), "automation_multiple_")

    return JsonResponse(
        {
            "choices": to_fields,
            "mail_details_choice": mail_details_choice,
            "serialized_form": serialized_form,
        }
    )


@login_required
@hx_request_required
@permission_required("pms.update_bonuspointsetting")
def update_isactive_bonuspoint_setting(request, obj_id):
    """
    htmx function to update is active field in BonusPointSetting.
    Args:
    - is_active: Boolean value representing the state of BonusPointSetting,
    - obj_id: Id of BonusPointSetting object.
    """
    bonus_point_setting = BonusPointSetting.objects.filter(id=obj_id).first()
    if not bonus_point_setting:
        return HorillaRedirect(
            request, message=_("No Bonus Point Setting found matching the query.")
        )

    is_active = request.POST.get("is_active")
    if is_active == "on":
        bonus_point_setting.is_active = True
        messages.success(request, _("Bonus point setting activated successfully."))
    else:
        bonus_point_setting.is_active = False
        messages.success(request, _("Bonus point setting deactivated successfully."))
    bonus_point_setting.save()

    return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")
