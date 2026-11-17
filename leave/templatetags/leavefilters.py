from django import template

from employee.models import Employee
from leave.models import LeaveGeneralSetting, LeaveRequest, LeaveType

register = template.Library()


@register.filter(name="is_compensatory")
def is_compensatory(user):
    if LeaveGeneralSetting.objects.exists():
        return LeaveGeneralSetting.objects.first().compensatory_leave
    else:
        return False


@register.simple_tag
def carryforward_in_use():
    """
    {% carryforward_in_use as show_carryforward %}: whether balance screens
    show the Carryforward and Total Leave Days figures.
    """
    return LeaveType.carryforward_in_use()
