import logging
import os
from functools import wraps
from urllib.parse import urlencode

from django.apps import apps
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from horilla import settings
from horilla.http import HorillaRedirect
from horilla.methods import handle_no_permission
from horilla.settings import BASE_DIR, TEMPLATES

logger = logging.getLogger(__name__)

TEMPLATES[0]["DIRS"] = [os.path.join(BASE_DIR, "templates")]

decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


def check_manager(employee, instance):
    from employee.models import Employee

    try:
        if isinstance(instance, Employee):
            return instance.employee_work_info.reporting_manager_id == employee
        return employee == instance.employee_id.employee_work_info.reporting_manager_id
    except:
        return False


@decorator_with_arguments
def permission_required(function, perm):
    def _function(request, *args, **kwargs):
        if request.user.has_perm(perm):
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    # Accumulate perms so login_required's @wraps propagates them automatically.
    _function._required_perms = getattr(function, "_required_perms", []) + [perm]
    return _function


def superuser_required(function):
    """Allow only Django superusers (superadmin) to enter the view."""

    def _function(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return function(request, *args, **kwargs)
        return handle_no_permission(request)

    return _function


@decorator_with_arguments
def any_permission_required(function, perms):
    def _function(request, *args, **kwargs):
        if any(request.user.has_perm(perm) for perm in perms):
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


@decorator_with_arguments
def delete_permission(function):
    from employee.models import EmployeeWorkInformation

    def _function(request, *args, **kwargs):
        user = request.user
        employee = user.employee_get
        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()
        if (
            request.user.has_perm(
                kwargs["model"]._meta.app_label
                + ".delete_"
                + kwargs["model"]._meta.model_name
            )
            or is_manager
        ):
            return function(request, *args, **kwargs)

        return handle_no_permission(
            request, message=_("You dont have permission for delete.")
        )

    return _function


decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


@decorator_with_arguments
def duplicate_permission(function):
    from employee.models import EmployeeWorkInformation

    def _function(request, *args, **kwargs):
        user = request.user
        employee = user.employee_get
        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()

        app_label = kwargs["model"]._meta.app_label
        model_name = kwargs["model"]._meta.model_name
        try:
            obj_id = kwargs["obj_id"]
            object_instance = kwargs["model"].objects.filter(pk=obj_id).first()
            if object_instance.employee_id == employee:
                return function(request, *args, **kwargs)
        except:
            pass
        permission = f"{app_label}.add_{model_name}"
        if request.user.has_perm(permission) or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(
            request, message=_("You dont have permission for duplicate action.")
        )

    return _function


decorator_with_arguments = (
    lambda decorator: lambda *args, **kwargs: lambda func: decorator(
        func, *args, **kwargs
    )
)


@decorator_with_arguments
def manager_can_enter(function, perm):
    from base.models import MultipleApprovalManagers
    from employee.models import EmployeeWorkInformation

    """
    This method is used to check permission to employee for enter to the function if the employee
    do not have permission also checks, has reporting manager.
    """

    @wraps(function)
    def _function(request, *args, **kwargs):
        leave_perm = [
            "leave.view_leaverequest",
            "leave.change_leaverequest",
            "leave.delete_leaverequest",
        ]
        user = request.user
        employee = user.employee_get
        if perm in leave_perm:
            is_approval_manager = MultipleApprovalManagers.objects.filter(
                employee_id=employee.id
            ).exists()
            if is_approval_manager:
                return function(request, *args, **kwargs)
        is_manager = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee
        ).exists()
        if user.has_perm(perm) or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


@decorator_with_arguments
def is_recruitment_manager(function, perm):
    from recruitment.models import Recruitment

    """
    This method is used to check permission to employee for enter to the function if the employee
    do not have permission also checks, has manager of any recruitment.
    """

    def _function(request, *args, **kwargs):

        user = request.user
        perm = "recruitment.view_recruitmentsurvey"
        is_manager = False
        recs = Recruitment.objects.all()
        for i in recs:
            for manager in i.recruitment_managers.all():
                if request.user.employee_get == manager:
                    is_manager = True

        if user.has_perm(perm) or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        path = request.path
        res = path.split("/", 2)[1].capitalize().replace("-", " ").upper()
        if res == "PMS":
            res = "Performance"
        request.session["title"] = res
        if path == "" or path == "/":
            request.session["title"] = "Dashboard".upper()

        login_url = reverse("login")
        try:
            query_string = urlencode(request.GET)
        except:
            query_string = None
        redirect_url = f"{login_url}?next={request.path}"
        if query_string:
            redirect_url += f"&{query_string}"

        employee = getattr(request.user, "employee_get", None)

        if (
            not request.user.is_authenticated
            or not request.user.is_active
            or not employee
            or not employee.is_active
        ):
            if request.headers.get("HX-Request"):
                return HttpResponse(status=204, headers={"HX-Refresh": "true"})
            return redirect(redirect_url)
        try:
            func = view_func(request, *args, **kwargs)
        except KeyError:
            raise
        except Exception as e:
            logger.error(e)
            if (
                "notifications_notification" in str(e)
                and request.headers.get("X-Requested-With") != "XMLHttpRequest"
            ):
                messages.warning(request, str(e))
                referer = request.META.get("HTTP_REFERER", "/")
                # Prevent open redirect + XSS
                if not url_has_allowed_host_and_scheme(
                    referer,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    referer = "/"

                return redirect(referer)

            if not settings.DEBUG:
                messages.error(request, str(e))
                return render(request, "went_wrong.html", status=404)
            raise e
        return func

    return wrapped_view


def hx_request_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        key = "HTTP_HX_REQUEST"
        if key not in request.META.keys():
            return render(request, "405.html", status=405)
        return view_func(request, *args, **kwargs)

    return wrapped_view


def database_init_required(view_func):
    """Allow the wizard's user creation step only before setup, and only after the DB_INIT_PASSWORD was verified."""

    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        from base.views import initialize_database_condition

        if not initialize_database_condition():
            messages.warning(request, _("The database is already initialized."))
            return redirect("login")
        if not request.session.get("db_init_verified"):
            messages.warning(
                request,
                _("Verify the database initialization password to continue."),
            )
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return wrapped_view


@decorator_with_arguments
def owner_can_enter(
    function,
    perm: str,
    model: object,
    manager_access=False,
    employee_field="employee_id",
):
    from employee.models import Employee, EmployeeWorkInformation

    """
    Only the users with permission, or the owner, or employees manager can enter,
    If manager_access:True then all the managers can enter
    """

    def _function(request, *args, **kwargs):
        if kwargs:
            instance_id = kwargs[list(kwargs.keys())[0]]
        else:
            instance_id = request.GET.get("employee_id") or request.POST.get(
                "employee_id"
            )
        if model == Employee:
            employee = Employee.objects.filter(id=instance_id).first()
        else:
            try:
                obj = model.objects.filter(id=instance_id).first()
                employee = getattr(obj, employee_field, None) if obj else None
            except:
                messages.error(request, _("Sorry, something went wrong!"))
                return HorillaRedirect(request)
        can_enter = (
            request.user.employee_get == employee
            or request.user.has_perm(perm)
            or check_manager(request.user.employee_get, employee)
            or (
                EmployeeWorkInformation.objects.filter(
                    reporting_manager_id__employee_user_id=request.user
                ).exists()
                if manager_access
                else False
            )
        )
        if can_enter or not employee:
            return function(request, *args, **kwargs)
        return render(request, "no_perm.html")

    return _function


def install_required(function):
    from base.models import BiometricAttendance, Company, TrackLateComeEarlyOut

    def _function(request, *args, **kwargs):
        if request.path_info.endswith("late-come-early-out-view/"):
            selected_company = request.session.get("selected_company")
            if selected_company == "all":
                company = None
            else:
                company = Company.objects.filter(id=selected_company).first()

            object, created = TrackLateComeEarlyOut.objects.get_or_create(
                company_id=company
            )
            if not object or object.is_enable:
                return function(request, *args, **kwargs)
            else:
                messages.info(
                    request,
                    _(
                        "Please enable the Track Late Arrival & Early Departure from settings"
                    ),
                )
                return HorillaRedirect(request)
        selected_company = request.session.get("selected_company")
        if selected_company == "all":
            biometric_company = None
        else:
            biometric_company = Company.objects.filter(id=selected_company).first()
        object = BiometricAttendance.objects.filter(
            company_id=biometric_company
        ).first()
        if not object or object.is_installed:
            return function(request, *args, **kwargs)
        else:
            messages.info(
                request,
                _(
                    "Please activate the biometric attendance feature in the settings menu."
                ),
            )
            return HorillaRedirect(request)

    return _function


@decorator_with_arguments
def meeting_manager_can_enter(function, perm, answerable=False):
    from employee.models import Employee

    def _function(request, *args, **kwargs):

        user = request.user
        employee = user.employee_get
        is_answer_employee = False

        is_manager = (
            Employee.objects.filter(
                meeting_manager__isnull=False,
            )
            .filter(id=employee.id)
            .exists()
        )

        if answerable:
            is_answer_employee = (
                Employee.objects.filter(
                    meeting_answer_employees__isnull=False,
                )
                .filter(id=employee.id)
                .exists()
            )

        if user.has_perm(perm) or is_manager or is_answer_employee:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


DECORATOR_MAP = {
    "login_required": login_required,
    "permission_required": permission_required,
    "superuser_required": superuser_required,
    "delete_permission": delete_permission,
    "duplicate_permission": duplicate_permission,
    "manager_can_enter": manager_can_enter,
    "is_recruitment_manager": is_recruitment_manager,
    "hx_request_required": hx_request_required,
    "owner_can_enter": owner_can_enter,
    "install_required": install_required,
    "meeting_manager_can_enter": meeting_manager_can_enter,
}


def get_decorator(decorator_string, args=None):
    decorator = DECORATOR_MAP.get(decorator_string)
    if decorator:
        if args is not None:
            if isinstance(args, (list, tuple)):
                return decorator(*args)
            else:
                return decorator(args)
        else:
            return decorator
    return None


def apply_decorators(decorators):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            decorated_func = func
            for decorator_item in decorators:
                if isinstance(decorator_item, str):
                    decorator = get_decorator(decorator_item)
                elif (
                    isinstance(decorator_item, (list, tuple))
                    and len(decorator_item) == 2
                ):
                    decorator_string, decorator_args = decorator_item
                    decorator = get_decorator(decorator_string, decorator_args)
                else:
                    print(f"Warning: Invalid decorator format: {decorator_item}")
                    continue

                if decorator:
                    if callable(decorator):
                        decorated_func = decorator(decorated_func)
                    else:
                        # For decorators returned by decorator_with_arguments
                        decorated_func = decorator(decorated_func)
                else:
                    print(f"Warning: Decorator '{decorator_item}' not found or invalid")
            return decorated_func(*args, **kwargs)

        return wrapper

    return decorator


@decorator_with_arguments
def check_integration_enabled(func, app_name):
    """
    Decorator to check if the integration app is installed and enabled.
    """
    from base.models import IntegrationApps

    @wraps(func)
    def wrapper(request=None, *args, **kwargs):
        if not IntegrationApps.objects.filter(
            app_label=app_name, is_enabled=True
        ).exists():
            if request:
                try:
                    app_config = apps.get_app_config(app_name)
                    app_verbose_name = app_config.verbose_name
                except LookupError:
                    app_verbose_name = app_name

                return handle_no_permission(
                    request, message=f"Access to '{app_verbose_name}' is disabled."
                )

            return None

        return func(request, *args, **kwargs)

    return wrapper
