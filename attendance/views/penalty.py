"""
attendance/views/penalty.py

This module is used to write late come early out penatly methods
"""

from django.apps import apps
from django.contrib import messages
from django.db.models.query import QuerySet
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from attendance.models import AttendanceLateComeEarlyOut
from base.forms import PenaltyAccountForm
from base.models import PenaltyAccounts
from horilla.decorators import hx_request_required, login_required, manager_can_enter
from horilla.methods import get_horilla_model_class


@login_required
@hx_request_required
@manager_can_enter("leave.change_availableleave")
def cut_available_leave(request, instance_id):
    """
    This method is used to create the penalties
    """
    late_in_early_out_ids = (
        request.GET.get("instances_ids", None)
        if request.GET.get("instances_ids") != "None"
        else None
    )
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    instance = AttendanceLateComeEarlyOut.objects.filter(id=instance_id).first()
    if not instance:
        return HttpResponse()
    form = PenaltyAccountForm(employee=instance.employee_id)
    if apps.is_installed("leave"):
        AvailableLeave = get_horilla_model_class(
            app_label="leave", model="availableleave"
        )
        available = AvailableLeave.objects.filter(employee_id=instance.employee_id)
    else:
        available = QuerySet().none()
    if request.method == "POST":
        form = PenaltyAccountForm(request.POST, employee=instance.employee_id)
        if form.is_valid():
            penalty_instance = form.instance
            penalty = PenaltyAccounts()
            penalty.employee_id = instance.employee_id
            penalty.late_early_id = instance
            penalty.penalty_amount = penalty_instance.penalty_amount
            if apps.is_installed("leave"):
                penalty.leave_type_id = penalty_instance.leave_type_id
                penalty.minus_leaves = penalty_instance.minus_leaves
                penalty.deduct_from_carry_forward = (
                    penalty_instance.deduct_from_carry_forward
                )

            penalty.save()
            messages.success(request, _("Penalty/Fine added"))
            form = PenaltyAccountForm(employee=instance.employee_id)
    return render(
        request,
        "attendance/penalty/form.html",
        {
            "available": available,
            "late_in_early_out_ids": late_in_early_out_ids,
            "form": form,
            "instance": instance,
            "pd": previous_data,
        },
    )
