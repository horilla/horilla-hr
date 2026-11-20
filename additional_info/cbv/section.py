"""The read-only Additional Information section of the About tab; values are edited on the employee form."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from additional_info import services
from base.methods import employees_in_scope
from employee.models import Employee
from horilla.decorators import hx_request_required, login_required, owner_can_enter
from horilla.http.response import HorillaRedirect


def can_edit(request, employee):
    """Who may change it: HR with the change permission, and the reporting managers. The employee only views."""
    return employees_in_scope(request, [employee.pk], "employee.change_employee")


def _render_section(request, employee):
    """The read-only section, or nothing at all when no field has been set up so About looks unchanged."""
    rows = services.rows_for(employee)
    if not rows:
        return HttpResponse("")
    return render(
        request,
        "additional_info/section.html",
        {"employee": employee, "rows": rows},
    )


def _initial(employee, fields):
    """Prefill values; a Yes / No becomes the 'yes' or 'no' the select uses."""
    initial = services.initial_for(employee, fields)
    for field in fields:
        if field.field_type == "yes_no" and field.key in initial:
            initial[field.key] = "yes" if initial[field.key] else "no"
        elif field.field_type == "number" and initial.get(field.key) is not None:
            # 5.500000 reads as 5.5 and 3.000000 as 3 in the input
            initial[field.key] = format(initial[field.key].normalize(), "f")
    return initial


@login_required
@hx_request_required
@owner_can_enter("employee.view_employee", Employee)
def additional_info_section(request, pk):
    """The section: every active field and what this employee has for it."""
    employee = Employee.objects.filter(id=pk).first()
    if not employee:
        messages.error(request, _("Employee not found."))
        return HorillaRedirect(request)
    return _render_section(request, employee)
