"""
attendancefilters.py

This module is used to write custom template filters.

"""

import base64
from datetime import date, datetime, timedelta
from itertools import groupby

from django import template
from django.forms.widgets import SelectMultiple, Textarea
from django.template import TemplateSyntaxError

from attendance.models import Attendance, AttendanceValidationCondition
from attendance.views.views import strtime_seconds
from base.models import EmployeeShiftSchedule
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals

register = template.Library()


@register.filter(name="is_string")
def is_string(value):
    return isinstance(value, str)


@register.filter(name="checkminimumot")
def checkminimumot(ot=None):
    """
    This filter method is used to check minimum overtime from
    the attendance validation condition
    """
    if ot is not None:
        condition = AttendanceValidationCondition.objects.all()
        if condition.exists():
            minimum_overtime_to_approve = condition[0].minimum_overtime_to_approve
            overtime_second = strtime_seconds(ot)
            minimum_ot_approve_seconds = strtime_seconds(minimum_overtime_to_approve)
            if overtime_second > minimum_ot_approve_seconds:
                return True
        return False


@register.filter(name="checkmanager")
def checkmanager(user, employee):
    """
    This filter method is used to check request user is manager of the employee
    args:
        user        : request.user
        employee    : employee instance

    """

    employee_user = user.employee_get
    employee_manager = employee.employee_work_info.reporting_manager_id
    return bool(
        employee_user == employee_manager
        or user.is_superuser
        or user.has_perm("attendance.change_attendance")
    )


@register.filter(name="is_clocked_in")
def is_clocked_in(user):
    """
    This filter method is used to check the user is clocked in or not
    args:
        user    : request.user
    """

    try:
        employee = user.employee_get
    except:
        return False
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_attendance = (
        employee.employee_attendances.filter(attendance_date__in=[yesterday, today])
        .order_by("attendance_date", "id")
        .last()
    )
    if last_attendance is not None:
        last_activity = (
            employee.employee_attendance_activities.filter(
                attendance_date=last_attendance.attendance_date
            )
            .order_by("id")
            .last()
        )
        return False if last_activity is None else last_activity.clock_out is None
    return False


class DynamicRegroupNode(template.Node):
    """
    DynamicRegroupNode
    """

    def __init__(self, target, parser, expression, var_name):
        self.target = target
        self.expression = template.Variable(expression)
        self.var_name = var_name
        self.parser = parser

    def render(self, context):
        obj_list = self.target.resolve(context, True)
        if obj_list is None:
            # target variable wasn't found in context; fail silently.
            context[self.var_name] = []
            return ""
        # List of dictionaries in the format:
        # {'grouper': 'key', 'list': [list of contents]}.

        # ----
        # Try to resolve the filter expression from the template context.
        # If the variable doesn't exist, accept the value that passed to the
        # template tag and convert it to a string
        # ----
        try:
            exp = self.expression.resolve(context)
        except template.VariableDoesNotExist:
            exp = str(self.expression)

        filter_exp = self.parser.compile_filter(exp)

        context[self.var_name] = [
            {"grouper": key, "list": list(val)}
            for key, val in groupby(
                obj_list, lambda v, f=filter_exp.resolve: f(v, True)
            )
        ]

        return ""


@register.tag
def dynamic_regroup(parser, token):
    """
    A template tag that allows dynamic grouping of objects based on a provided attribute.

    Usage: {% dynamic_regroup target by expression as var_name %}

    :param parser: The template parser.
    :param token: The tokenized tag contents.
    :return: A DynamicRegroupNode object.
    :raises TemplateSyntaxError: If the tag is not properly formatted.
    """
    firstbits = token.contents.split(None, 3)
    if len(firstbits) != 4:
        raise TemplateSyntaxError("'regroup' tag takes five arguments")
    target = parser.compile_filter(firstbits[1])
    if firstbits[2] != "by":
        raise TemplateSyntaxError("second argument to 'regroup' tag must be 'by'")
    lastbits_reversed = firstbits[3][::-1].split(None, 2)
    if lastbits_reversed[1][::-1] != "as":
        raise TemplateSyntaxError(
            "next-to-last argument to 'regroup' tag must" " be 'as'"
        )

    # ---
    # Django expects the value of `expression` to be an attribute available on
    # your objects. The value you pass to the template tag gets converted into a
    # FilterExpression object from the literal.

    # Sometimes we need the attribute to group on to be dynamic. So, instead
    # of converting the value to a FilterExpression here, we're going to pass the
    # value as-is and convert it in the Node.
    # ----
    expression = lastbits_reversed[2][::-1]
    var_name = lastbits_reversed[0][::-1]

    # ----
    # We also need to hand the parser to the node in order to convert the value
    # for `expression` to a FilterExpression.
    # ----
    return DynamicRegroupNode(target, parser, expression, var_name)


@register.filter(name="any_permission")
def any_permission(user, app_label):
    """
    This method is used to check any on the module

    Args:
        user (obj): Django user model instance
        app_label (str): app label

    Returns:
        bool: True if any permission on the module
    """
    return user.has_module_perms(app_label)


@register.filter
def is_select_multiple(widget):
    """
    Custom template filter to check if a widget is an instance of SelectMultiple.

    Usage:
    {% load custom_filters %}

    {% if field.field.widget|is_select_multiple %}
        <!-- Your code here -->
    {% endif %}
    """
    return isinstance(widget, SelectMultiple)


@register.filter
def is_text_area(widget):
    """
    Custom template filter to check if a widget is an instance of SelectMultiple.

    Usage:
    {% load custom_filters %}

    {% if field.field.widget|Textarea %}
        <!-- Your code here -->
    {% endif %}
    """
    return isinstance(widget, Textarea)


@register.filter
def base64_encode(value):
    try:
        return base64.b64encode(value).decode("utf-8")
    except:
        pass


@register.filter(name="current_month_record")
def current_month_record(queryset):
    current_month_start_date = datetime.now().replace(day=1)
    next_month_start_date = current_month_start_date + timedelta(days=31)

    return queryset.filter(
        start_datetime__gte=current_month_start_date,
        start_datetime__lt=next_month_start_date,
    ).order_by("start_datetime")


@register.filter
def get_item(list, i):
    try:
        return list[i]
    except:
        return None


@register.filter
def get_employee_specific_holidays(specific_holiday_dict, employee_pk):
    return specific_holiday_dict.get(employee_pk, set())
