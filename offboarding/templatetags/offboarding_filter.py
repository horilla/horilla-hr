"""
offboarding_filter.py

This page is used to write custom template filters.
"""

from django import template

from employee.models import Employee
from offboarding.models import (
    EmployeeTask,
    Offboarding,
    OffboardingEmployee,
    OffboardingStage,
    OffboardingTask,
)

register = template.Library()


@register.filter(name="stages")
def stages(stages_dict: dict, stage: OffboardingStage):
    """
    This method will return stage drop accordingly to the offboarding
    """
    form = stages_dict[str(stage.offboarding_id.id)]
    attrs = form.fields["stage_id"].widget.attrs
    attrs["id"] = "stage" + str(stage.id) + str(stage.offboarding_id.id)
    attrs["data-initial-stage"] = stage.id
    form.fields["stage_id"].widget.attrs.update(attrs)
    return form


@register.filter(name="individual_view_stages")
def individual_view_stages(stages_dict: dict, stage: OffboardingStage):
    """
    This method will return stage drop accordingly to the offboarding
    """
    form = stages_dict[str(stage.offboarding_id.id)]
    attrs = form.fields["stage_id"].widget.attrs
    attrs["id"] = "stage" + str(stage.id) + str(stage.offboarding_id.id)
    attrs["data-selected-stage"] = stage.id
    attrs["onchange"] = "myFunction($(this).val())"
    form.fields["stage_id"].widget.attrs.update(attrs)
    return form


@register.filter(name="have_task")
def have_task(task: OffboardingTask, employee: Employee):
    """
    used to check the task is for the employee
    """
    return EmployeeTask.objects.filter(employee_id=employee, task_id=task).exists()


@register.filter(name="get_assigned_task")
def get_assigned_tak(employee: Employee, task: OffboardingTask):
    """
    This method is used to filterout the assigned task
    """
    # retun like list to access it in varialbe when first iteration of the loop
    return [
        EmployeeTask.objects.filter(employee_id=employee, task_id=task).first(),
    ]


@register.filter(name="any_manager")
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


@register.filter(name="is_offboarding_manager")
def is_offboarding_manager(employee: Employee):
    """
    This method is used to check the employee is manager of any offboarding
    """
    return Offboarding.objects.filter(managers=employee).exists()


@register.filter(name="is_offboarding_employee")
def is_offboarding_employee(employee: Employee):
    """
    This method is used to check the employee is in offboarding employee
    """
    return OffboardingEmployee.objects.filter(employee_id=employee).exists()


@register.filter("is_in_managers")
def is_in_managers(employee: Employee, instance: object):
    """
    This method is used to check the employee in the managers or not
    """
    is_in_managers = False
    if isinstance(instance, (Offboarding, OffboardingStage)):
        # checking in offboarding managers
        is_in_managers = instance.managers.filter(employee_id=employee).exists()
    if isinstance(instance, OffboardingEmployee):
        # also checking in the offboarding employee
        is_in_managers = is_in_managers | (employee == instance.employee_id)
    return is_in_managers


@register.filter("is_in_offboarding")
def is_in_offboarding(employee: Employee, offboarding: Offboarding):
    """
    This method is used to check the employee in the offboarding or not
    """
    return (
        (employee in offboarding.managers.all())
        or OffboardingStage.objects.filter(
            offboarding_id=offboarding, managers=employee
        ).exists()
        or OffboardingEmployee.objects.filter(
            stage_id__offboarding_id=offboarding, employee_id=employee
        ).exists()
    )


@register.filter("is_any_stage_manager")
def is_any_stage_manager(employee):
    """
    This method is used to to check any stage manager
    """
    return (
        OffboardingStage.objects.filter(managers=employee).exists()
        | Offboarding.objects.filter(managers=employee).exists()
    )


@register.filter("is_stage_manager")
def is_stage_manager(employee, stage: OffboardingStage):
    """
    This method is used to check if an employee is a stage manager
    """
    current_stage = OffboardingStage.objects.filter(title=stage)
    for stag in current_stage:
        if employee in stag.managers.all():
            is_manager = True
        else:
            is_manager = False

    return is_manager


@register.filter("is_task_manager")
def is_task_manager(employee, task: OffboardingTask):
    """
    This method is used to check if an employee is a stage manager
    """
    current_task = OffboardingTask.objects.filter(title=task)
    for tas in current_task:
        if employee in tas.managers.all():
            is_manager = True
        else:
            is_manager = False

    return is_manager


@register.filter("completed_tasks")
def completed_tasks(tasks):
    """
    This method is used to to check any stage manager
    """
    return tasks.filter(status="completed").count()


@register.filter("is_employee_tasks")
def is_employee_tasks(employee_tasks, task):
    """
    This method is used to to check any stage manager
    """
    try:
        if task.title in employee_tasks.values_list("task_id__title", flat=True):
            return True
        return False
    except:
        return False


@register.filter("is_manager_for_any_task")
def is_manager_for_any_task(employee, tasks):
    """
    Returns True if the employee is a manager for any task in the list of tasks.
    """
    for task in tasks:
        if employee in task.managers.all():
            is_manager = True
        else:
            is_manager = False
    return is_manager
