"""
What the employee create and edit pages need from additional info.

The employee views import this only when the app is installed, so the employee app does not depend on it.
"""

from django.core.exceptions import ValidationError

from additional_info import services
from additional_info.cbv.section import _initial, can_edit
from additional_info.forms import build_values_form


def has_step(request, employee=None):
    """True when the pages should show an Additional Information step: a field exists and the user may edit it."""
    if not services.active_fields():
        return False
    return employee is None or can_edit(request, employee)


def edit_form(request, employee):
    """The values form for the edit page's Additional Information step, or None when there is no step."""
    if not has_step(request, employee):
        return None
    fields = services.active_fields()
    return build_values_form(fields)(initial=_initial(employee, fields))


def save_form(request, employee):
    """
    Handle the step's submit: returns ``(form, saved)``.

    The form is bound, so its errors show on the page; ``form`` is None when there is nothing to save.
    """
    if not has_step(request, employee):
        return None, False
    fields = services.active_fields()
    form = build_values_form(fields)(
        request.POST, request.FILES, initial=_initial(employee, fields)
    )
    if not form.is_valid():
        return form, False
    try:
        services.set_values(employee, fields, form.cleaned_data)
    except ValidationError as error:
        form.add_error(None, "; ".join(error.messages))
        return form, False
    return form, True
