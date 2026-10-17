"""
provisioning.py

The only place identity-provider code (SCIM today, SAML/OIDC just-in-time
later) creates, changes, deactivates or removes employees.

Why a service instead of calling Employee.save() from each protocol:

- ``Employee.save()`` creates the login with ``is_new_employee=True`` (forces
  /change-password/) and a username that silently falls back to five random
  letters on collision. IdP-managed accounts need the username the IdP sent
  and no forced password change, so the user is created here first.
- Deactivation is two flags (``HorillaUser.is_active`` gates login,
  ``Employee.is_active`` hides the person), and ``Employee.save()`` quietly
  re-activates an employee who still manages others. Cutting login must not
  depend on that, so it is done on the user row directly.
- Superusers are never managed by an IdP. They are the break-glass accounts
  that keep working when the IdP is misconfigured.

Every function raises ``ProvisioningError`` for a refusal the caller should
report; the SCIM layer maps ``code`` to a SCIM error.
"""

import logging

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext_noop

from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.methods import generate_random_password
from horilla_auth.models import HorillaUser

logger = logging.getLogger(__name__)

# Work-info fields the provisioning layer is allowed to set.
WORK_INFO_FIELDS = (
    "email",
    "department_id",
    "job_position_id",
    "shift_id",
    "employee_type_id",
    "work_type_id",
    "reporting_manager_id",
)


class ProvisioningError(Exception):
    UNIQUENESS = "uniqueness"
    FORBIDDEN = "forbidden"
    INVALID = "invalid"
    PROTECTED = "protected"

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _check_not_superuser(employee):
    user = employee.employee_user_id
    if user is not None and user.is_superuser:
        raise ProvisioningError(
            ProvisioningError.FORBIDDEN,
            "Superuser accounts cannot be managed by an identity provider.",
        )


def _check_unique(username=None, email=None, badge_id=None, exclude_employee=None):
    employees = Employee.objects.entire()
    users = HorillaUser.objects.all()
    if exclude_employee is not None:
        employees = employees.exclude(pk=exclude_employee.pk)
        users = users.exclude(pk=exclude_employee.employee_user_id_id)
    if email and employees.filter(email__iexact=email).exists():
        raise ProvisioningError(
            ProvisioningError.UNIQUENESS, "An employee with this e-mail already exists."
        )
    if username and users.filter(username__iexact=username).exists():
        raise ProvisioningError(
            ProvisioningError.UNIQUENESS, "A user with this userName already exists."
        )
    if badge_id and employees.filter(badge_id=badge_id).exists():
        raise ProvisioningError(
            ProvisioningError.UNIQUENESS,
            "An employee with this employee number already exists.",
        )


def _apply_work_info(employee, company, work_info):
    info = EmployeeWorkInformation.objects.entire().filter(employee_id=employee).first()
    if info is None:
        info = EmployeeWorkInformation(employee_id=employee)
    if company is not None:
        info.company_id = company
    for field, value in work_info.items():
        if field not in WORK_INFO_FIELDS:
            raise ValueError(f"Unsupported work-info field: {field}")
        setattr(info, field, value)
    # save() rather than update() so the post_save hooks the UI path relies
    # on (payroll contract creation, accessibility cache) still run.
    info.save()


@transaction.atomic
def create_employee(
    *,
    company,
    username,
    email,
    first_name,
    last_name="",
    phone="",
    badge_id=None,
    work_info=None,
):
    """
    Create a login and its employee in ``company``.

    The password is random and never shown: IdP users sign in through SSO,
    or set one through an invitation e-mail. (An unusable password would
    also block that invitation, because the reset form skips such users.)
    """
    username = username.strip().lower()
    email = email.strip().lower()
    _check_unique(username=username, email=email, badge_id=badge_id)

    user = HorillaUser.objects.create_user(
        username=username,
        email=email,
        password=generate_random_password(),
        is_new_employee=False,
    )
    # Employee.save() only grants these when it creates the user itself.
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=["view_ownprofile", "change_ownprofile"]
        )
    )

    employee = Employee(
        employee_user_id=user,
        employee_first_name=first_name,
        employee_last_name=last_name or "",
        email=email,
        phone=phone or "",
        badge_id=badge_id or None,
    )
    employee.save()
    _apply_work_info(employee, company, work_info or {})
    return Employee.objects.entire().get(pk=employee.pk)


@transaction.atomic
def update_employee(
    employee,
    *,
    username=None,
    email=None,
    first_name=None,
    last_name=None,
    phone=None,
    badge_id=None,
    work_info=None,
):
    """Change only the attributes that are passed (None means "leave as is")."""
    _check_not_superuser(employee)
    username = username.strip().lower() if username else None
    email = email.strip().lower() if email else None
    _check_unique(
        username=username, email=email, badge_id=badge_id, exclude_employee=employee
    )

    user = employee.employee_user_id
    if username is not None and user.username != username:
        user.username = username
        user.save(update_fields=["username"])
    if email is not None:
        if user.email != email:
            user.email = email
            user.save(update_fields=["email"])
        employee.email = email
    if first_name is not None:
        employee.employee_first_name = first_name
    if last_name is not None:
        employee.employee_last_name = last_name
    if phone is not None:
        employee.phone = phone
    if badge_id is not None:
        employee.badge_id = badge_id or None
    employee.save()
    if work_info:
        _apply_work_info(employee, None, work_info)
    return employee


@transaction.atomic
def deactivate_employee(employee):
    """
    Cut login immediately; archive the employee when nothing depends on them.

    Returns True when the employee was archived, False when only the login
    was cut because they still manage people or own recruitment/onboarding
    steps. HR is notified in that case so they can reassign and archive.
    """
    _check_not_superuser(employee)
    user = employee.employee_user_id
    if user is not None:
        # A direct update, independent of Employee.save(), so the login is
        # cut even when the employee itself cannot be archived. Existing
        # sessions die with it: login_required re-checks user.is_active on
        # every request, and simplejwt refuses tokens of inactive users.
        HorillaUser.objects.filter(pk=user.pk).update(is_active=False)
        user.is_active = False

    if not employee.is_active:
        return True
    if employee.get_archive_condition() is False:
        employee.is_active = False
        employee.save()
        return True

    _notify_admins_pending_offboarding(employee)
    return False


@transaction.atomic
def reactivate_employee(employee):
    _check_not_superuser(employee)
    if not employee.is_active:
        employee.is_active = True
        employee.save()
    user = employee.employee_user_id
    if user is not None and not user.is_active:
        HorillaUser.objects.filter(pk=user.pk).update(is_active=True)
        user.is_active = True
    return employee


@transaction.atomic
def delete_employee(employee):
    """
    Permanently delete the employee and their login.

    Mirrors employee_delete (employee/views.py): drops non-active contracts,
    then deletes the user, which cascades to the employee. Raises PROTECTED
    when other records still point at the employee.
    """
    _check_not_superuser(employee)
    if apps.is_installed("payroll"):
        for contract in employee.contract_set.all():
            if contract.contract_status != "active":
                contract.delete()
    try:
        if employee.employee_user_id is not None:
            employee.employee_user_id.delete()
        else:
            employee.delete()
    except ProtectedError as exc:
        names = sorted({obj._meta.verbose_name for obj in exc.protected_objects})
        raise ProvisioningError(
            ProvisioningError.PROTECTED,
            "Employee is still referenced by: " + ", ".join(map(str, names)),
        ) from exc


def _notify_admins_pending_offboarding(employee):
    from notifications.signals import notify

    recipients = HorillaUser.objects.filter(is_superuser=True, is_active=True)
    if not recipients.exists():
        return
    try:
        notify.send(
            employee,
            recipient=recipients,
            verb=gettext_noop(
                "was deactivated by the identity provider but still manages "
                "people or processes. Their login is disabled; reassign their "
                "responsibilities and archive them."
            ),
            redirect=f"/employee/employee-view/{employee.pk}/",
            icon="person-remove",
        )
    except Exception:
        # A failed notification must never undo the deactivation.
        logger.exception("Could not notify admins about employee %s", employee.pk)
