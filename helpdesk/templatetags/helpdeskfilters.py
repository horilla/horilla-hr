from django import template

from helpdesk.models import ClaimRequest, DepartmentManager

register = template.Library()


@register.filter(name="claim_request_exists")
def claim_request_exists(ticket, employee):
    return ClaimRequest.objects.filter(ticket_id=ticket, employee_id=employee).exists()


@register.filter(name="is_department_manager")
def is_department_manager(employee, ticket):
    """
    Check requested user is a department manger or not
    """
    if ticket.assigning_type == "job_position":
        job_position = ticket.get_raised_on_object()
        department = job_position.department_id
    elif ticket.assigning_type == "department":
        department = ticket.get_raised_on_object()
    else:
        return False
    return DepartmentManager.objects.filter(
        manager=employee, department=department
    ).exists()
