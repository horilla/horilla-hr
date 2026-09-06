from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render

from employee.models import EmployeeWorkInformation
from horilla.methods import handle_no_permission
from pms.models import AnonymousFeedback, EmployeeObjective, Objective

decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


@decorator_with_arguments
def pms_manager_can_enter(function, perm):
    """
    This method is used to check permission to employee for enter to the function if the employee
    do not have permission also checks, has reporting manager or manager of respective objective.
    """

    def _function(request, *args, **kwargs):
        user = request.user
        employee = user.employee_get
        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()
        is_objective_manager = Objective.objects.filter(managers=employee).exists()
        if user.has_perm(perm) or is_manager or is_objective_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


@decorator_with_arguments
def pms_owner_and_manager_can_enter(function, perm):
    """
    This method is used to check permission to employee for enter to the function if the employee
    do not have permission also checks, has reporting manager or manager of respective objective.
    """

    def _function(request, *args, **kwargs):
        user = request.user
        employee = user.employee_get
        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()
        is_objective_owner = EmployeeObjective.objects.filter(
            employee_id=employee
        ).exists()
        is_objective_manager = Objective.objects.filter(managers=employee).exists()
        if (
            user.has_perm(perm)
            or is_manager
            or is_objective_manager
            or is_objective_owner
        ):
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


def check_permission_feedback_detailed_view(request, feedback, perm):
    """
    Checks if the user has permission to view the detailed view of feedback.

    The user is allowed if they:
    - Have the required permission
    - Are the owner of the feedback
    - Are the reporting manager of the feedback owner
    - Are the feedback manager

    Args:
        request: The HTTP request object containing the user.
        feedback: The feedback object being accessed.
        perm: The specific permission required.

    Returns:
        bool: True if the user has permission, False otherwise.
    """
    user = request.user
    employee = user.employee_get

    # Check if the user is the reporting manager of the feedback owner
    is_manager = EmployeeWorkInformation.objects.filter(
        reporting_manager_id=employee, employee_id=feedback.employee_id
    ).exists()

    # Check for permission, if the user is the feedback manager, reporting manager, or the feedback owner
    has_permission = (
        user.has_perm(perm)
        or feedback.manager_id == employee
        or is_manager
        or feedback.employee_id == employee
    )

    return has_permission


def get_anonymous_feedbacks(employee):
    department = employee.get_department()
    job_position = employee.get_job_position()
    anonymous_feedbacks = (
        AnonymousFeedback.objects.filter(department_id=department)
        | AnonymousFeedback.objects.filter(job_position_id=job_position)
        | AnonymousFeedback.objects.filter(employee_id=employee)
    )
    return anonymous_feedbacks


def check_duplication(feedback, other_employees):
    """Remove already existing employee from feedback request and return updated employees"""
    req_employees = set(feedback.subordinate_id.all())
    req_employees.update(feedback.colleague_id.all())
    if feedback.manager_id:
        req_employees.add(feedback.manager_id)
    if feedback.employee_id:
        req_employees.add(feedback.employee_id)
    # Remove already requested employees from others_id
    updated_employees = [emp for emp in other_employees if emp not in req_employees]
    return updated_employees
