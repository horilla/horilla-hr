"""
decorators.py

Custom decorators for permission and manager checks in the application.
"""

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla.config import logger
from horilla.methods import handle_no_permission
from recruitment.models import Candidate, Recruitment, Stage


def decorator_with_arguments(decorator):
    """
    Decorator that allows decorators to accept arguments and keyword arguments.

    Args:
        decorator (function): The decorator function to be wrapped.

    Returns:
        function: The wrapper function.

    """

    def wrapper(*args, **kwargs):
        """
        Wrapper function that captures the arguments and keyword arguments.

        Args:
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            function: The inner wrapper function.

        """

        def inner_wrapper(func):
            """
            Inner wrapper function that applies the decorator to the function.

            Args:
                func (function): The function to be decorated.

            Returns:
                function: The decorated function.

            """
            return decorator(func, *args, **kwargs)

        return inner_wrapper

    return wrapper


@decorator_with_arguments
def manager_can_enter(function, perm=None, perms=None):
    """
    Decorator that checks if the user has the specified permission(s) or is a manager.

    Args:
        perm (str): A single permission string.
        perms (list): A list of permission strings.

    Returns:
        function: The decorated view.
    """

    def _function(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            login_url = reverse("login")
            params = urlencode(request.GET)
            url = f"{login_url}?next={request.path}"
            if params:
                url += f"&{params}"
            return redirect(url)
        employee = Employee.objects.filter(employee_user_id=user).first()

        is_manager = (
            Stage.objects.filter(stage_managers=employee).exists()
            or Recruitment.objects.filter(recruitment_managers=employee).exists()
        )

        # Combine perm and perms into one list to check
        all_perms = []
        if perm:
            all_perms.append(perm)
        if perms:
            all_perms.extend(perms)

        has_required_perm = any(user.has_perm(p) for p in all_perms)

        if has_required_perm or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


@decorator_with_arguments
def all_manager_can_enter(function, perm):
    """
    Decorator that checks if the user has the specified permission or is a manager.

    Args:
        perm (str): The permission to check.

    Returns:
        function: The decorated function.

    Raises:
        None

    """

    def _function(request, *args, **kwargs):
        """
        Inner function that performs the permission and manager check.

        Args:
            request (HttpRequest): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            HttpResponse: The response from the decorated function.

        """
        user = request.user
        employee = Employee.objects.filter(employee_user_id=user).first()
        is_manager = (
            Stage.objects.filter(stage_managers=employee).exists()
            or Recruitment.objects.filter(recruitment_managers=employee).exists()
            or request.user.employee_get.onboardingstage_set.exists()
            or request.user.employee_get.onboarding_task.exists()
        )
        if user.has_perm(perm) or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


@decorator_with_arguments
def recruitment_manager_can_enter(function, perm):
    """
    Decorator that checks if the user has the specified permission or is a recruitment manager.

    Args:
        perm (str): The permission to check.

    Returns:
        function: The decorated function.

    Raises:
        None

    """

    def _function(request, *args, **kwargs):
        """
        Inner function that performs the permission and manager check.

        Args:
            request (HttpRequest): The request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            HttpResponse: The response from the decorated function.
        """
        user = request.user
        employee = Employee.objects.filter(employee_user_id=user).first()
        is_manager = Recruitment.objects.filter(recruitment_managers=employee).exists()
        if user.has_perm(perm) or is_manager:
            return function(request, *args, **kwargs)

        return handle_no_permission(request)

    return _function


def candidate_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):

        allow_func = False
        if request.user.has_perm("recruitment.view_candidate"):
            allow_func = True
        if request.user:
            if request.user.is_authenticated:
                if (
                    request.user.employee_get.stage_set.exists()
                    or request.user.employee_get.recruitment_set.exists()
                ):
                    allow_func = True

        staff_allowed = allow_func
        if "candidate_id" in request.session:
            allow_func = True

        # A candidate who was archived after logging in loses portal access
        # at once. Staff previewing a candidate's page are unaffected.
        if not staff_allowed and "candidate_id" in request.session:
            session_candidate = (
                Candidate.objects.select_related("recruitment_id")
                .filter(pk=request.session.get("candidate_id"))
                .first()
            )
            if session_candidate is None or not session_candidate.has_portal_access:
                request.session.pop("candidate_id", None)
                request.session.pop("candidate_email", None)
                return redirect(reverse("candidate-login") + "?disabled=1")

        if allow_func:
            try:
                func = view_func(request, *args, **kwargs)
            except KeyError:
                raise
            except Exception as e:
                logger.error(e)
                if not settings.DEBUG:
                    messages.error(request, str(e))
                    return render(request, "went_wrong.html", status=404)
                raise e
            return func
        return redirect("candidate-login/")

    return _wrapped_view
