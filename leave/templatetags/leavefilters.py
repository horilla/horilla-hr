from django import template

from employee.models import Employee
from leave.models import LeaveGeneralSetting, LeaveRequest

register = template.Library()


@register.filter(name="is_compensatory")
def is_compensatory(user):
    if LeaveGeneralSetting.objects.exists():
        return LeaveGeneralSetting.objects.first().compensatory_leave
    else:
        return False
