"""
Accessiblility
"""

from django.apps import apps
from django.contrib.auth.context_processors import PermWrapper

from base.methods import check_manager
from employee.models import Employee
from horilla_audit.models import AccountBlockUnblock


def edit_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To access edit
    """
    # employee = Employee.objects.get(id=instance.pk)
    if (
        (request.user.has_perm("employee.change_employee"))
        or check_manager(request.user.employee_get, instance)
        or request.user == instance.employee_user_id
    ):
        return True
    return False


def password_reset_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To password  reset
    """
    # employee = Employee.objects.get(id=instance.pk)
    if (
        (request.user.has_perm("employee.add_employee"))
        or check_manager(request.user.employee_get, instance)
        or request.user == instance.employee_user_id
    ):
        return True
    return False


def block_account_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To block  account
    """
    enabled_block_unblock = (
        AccountBlockUnblock.objects.exists()
        and AccountBlockUnblock.objects.first().is_enabled
    )
    if (
        enabled_block_unblock
        and request.user.has_perm("employee.change_employee")
        and instance.employee_user_id.is_active
    ):
        return True
    return False


def un_block_account_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To block  account
    """
    enabled_block_unblock = (
        AccountBlockUnblock.objects.exists()
        and AccountBlockUnblock.objects.first().is_enabled
    )
    if (
        enabled_block_unblock
        and request.user.has_perm("employee.change_employee")
        and not instance.employee_user_id.is_active
    ):
        return True
    return False


def action_accessible(request, instance, user_perms):
    """
    To access archive and delete functionalities

    """

    if request.user.has_perm("employee.change_employee"):
        return True


def can_view_employee_permissions(request, employee) -> bool:
    """
    Groups & Permissions visible to: the employee, their reporting manager,
    and superadmins.
    """
    if not employee or not request.user.is_authenticated:
        return False
    user = request.user
    if user.is_superuser:
        return True
    if getattr(employee, "employee_user_id", None) == user:
        return True
    try:
        return check_manager(user.employee_get, employee)
    except Exception:
        return False


def can_edit_employee_permissions(request, employee) -> bool:
    """
    Who may change an employee's groups/permissions from the profile:
    superadmin only. Reporting managers and the employee get view access.
    """
    if not employee or not request.user.is_authenticated:
        return False
    return bool(request.user.is_superuser)


def permission_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    Groups & Permissions tab: visible to the employee themselves,
    their reporting manager, and superadmins.
    """
    return can_view_employee_permissions(request, instance)


def note_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    accessibility for note tab
    """
    if instance.employee_user_id != request.user or request.user.is_superuser:
        if request.user.has_perm("employee.view_employeenote") or check_manager(
            request.user.employee_get, instance
        ):
            return True
    return False


def document_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    accessibility for document tab
    """
    employee = Employee.objects.get(id=instance.pk)
    if (
        request.user.has_perm("horilla_documents.view_document")
        or request.user == employee.employee_user_id
    ):
        return True
    return False


def workshift_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    permission for work type and shift tab in employee profile
    """
    employee = Employee.objects.get(id=instance.pk)
    check_manages = check_manager(request.user.employee_get, instance)
    if (
        request.user == employee.employee_user_id
        or check_manages
        or request.user.has_perm("base.view_worktyperequest")
        or request.user.has_perm("base.view_shiftrequest")
    ):
        return True
    return False


def mail_log_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    permission for mail log tab
    """

    employee = Employee.objects.get(id=instance.pk)
    return bool(
        request.user.has_perm("employee.view_employee")
        or request.user == employee.employee_user_id
        or check_manager(request.user.employee_get, employee)
    )


def history_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    accessibility for history tab
    """
    if request.user.has_perm(
        "employee.view_historicalemployeeworkinformation"
    ) or check_manager(request.user.employee_get, instance):
        return True
    return False


def onboarding_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    Onboarding tab on the employee profile. For an employee converted from a
    candidate it is shown to the employee themselves and to those who can see
    that candidate's onboarding tab, otherwise only to users who can view
    onboarding tasks.

    Parameters:
    request (HttpRequest): The HTTP request object.
    instance : Employee whose profile is being viewed.

    Returns:
    bool : True if the tab should be shown.
    """
    if not (
        apps.is_installed("onboarding")
        and apps.is_installed("recruitment")
        and instance
    ):
        return False
    from recruitment.cbv.accessibility import (
        onboarding_accessibility as candidate_onboarding_accessibility,
    )

    candidate = instance.candidate_get.first()
    if not candidate:
        return request.user.has_perm("onboarding.view_onboardingtask")
    if request.user == instance.employee_user_id:
        return True
    return candidate_onboarding_accessibility(request, candidate)


def allocation_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    Allocations page: visible to the instance's reporting manager, the
    recruitment manager or onboarding stage/task manager of the candidate
    behind it (if any), or users with explicit permission.

    ``instance`` may be an Employee or (pre-conversion) a recruitment
    Candidate, matching what AllocationView resolves before this runs.
    """
    if not instance or not request.user.is_authenticated:
        return False
    if request.user.has_perm("recruitment.view_recruitment"):
        return True

    employee = getattr(request.user, "employee_get", None)
    if not employee:
        return False

    Candidate = (
        apps.get_model("recruitment", "Candidate")
        if apps.is_installed("recruitment")
        else None
    )

    if Candidate and isinstance(instance, Candidate):
        candidate = instance
    elif isinstance(instance, Employee):
        if check_manager(employee, instance):
            return True
        candidate = instance.candidate_get.first() if Candidate else None
    else:
        return False

    if not candidate:
        return False

    recruitment = candidate.recruitment_id
    if recruitment and recruitment.recruitment_managers.filter(pk=employee.pk).exists():
        return True

    if apps.is_installed("onboarding"):
        CandidateStage = apps.get_model("onboarding", "CandidateStage")
        stage_link = CandidateStage.objects.filter(candidate_id=candidate).first()
        if (
            stage_link
            and stage_link.onboarding_stage_id.employee_id.filter(
                pk=employee.pk
            ).exists()
        ):
            return True

        OnboardingTask = apps.get_model("onboarding", "OnboardingTask")
        if OnboardingTask.objects.filter(
            candidatetask__candidate_id=candidate, employee_id=employee
        ).exists():
            return True

    return False


def project_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    permission for work type and shift tab in employee profile
    """
    employee = Employee.objects.get(id=instance.pk)
    check_manages = check_manager(request.user.employee_get, instance)
    if (
        request.user == employee.employee_user_id
        or check_manages
        or request.user.has_perm("project.view_project")
    ):
        return True
    return False


def export_data_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To export individual employee data
    """
    return any(apps.is_installed(app) for app in ("leave", "payroll", "attendance"))


def allocations_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To view employee allocations
    """
    return request.user.has_perm("employee.change_employee") or check_manager(
        request.user.employee_get, instance
    )


def send_mail_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To send mail to the employee
    """
    return True


def admin_reset_password_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To reset password / send invitation as admin
    """
    return request.user.has_perm("employee.change_employee")


def archive_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To archive an active employee
    """
    return request.user.has_perm("employee.delete_employee") and instance.is_active


def un_archive_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To un-archive an archived employee
    """
    return request.user.has_perm("employee.delete_employee") and not instance.is_active


def delete_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    To delete the employee
    """
    return request.user.has_perm("employee.delete_employee")
