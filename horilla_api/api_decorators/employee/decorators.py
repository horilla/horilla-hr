from functools import wraps

from django.http import HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response

from accessibility.methods import check_is_accessible
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_accessibility_cache_key
from horilla_views.cbv_methods import decorator_with_arguments


def or_condition(*decorators):
    """
    Combines multiple decorators with OR logic.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Check if any of the decorators allow access
            for dec in decorators:
                if dec(view_func)(request, *args, **kwargs):
                    return view_func(request, *args, **kwargs)
            # If none of the decorators allow access, return forbidden response
            return HttpResponseForbidden(
                _("You don't have permission to access this page.")
            )

        return _wrapped_view

    return decorator


@decorator_with_arguments
def enter_if_accessible(function, feature, perm=None, method=None):
    """
    Accessibility check decorator for API views (DRF APIView)
    Returns proper API responses instead of redirects
    """

    def check_accessible(self, *args, **kwargs):
        """
        Check accessible
        """
        request = getattr(_thread_locals, "request")
        if not getattr(self, "request", None):
            self.request = request

        accessible = False
        cache_key = get_accessibility_cache_key(request)
        employee = getattr(request.user, "employee_get", None)
        if employee:
            accessible = check_is_accessible(feature, cache_key, employee)
        has_perm = True
        if perm:
            has_perm = request.user.has_perm(perm)

        method_result = False
        if method:
            try:
                method_result = method(request, *args, **kwargs)
            except Exception:
                method_result = False

        if accessible or has_perm or method_result:
            return function(self, *args, **kwargs)

        return Response(
            {"error": _("You don't have access to the feature")},
            status=status.HTTP_403_FORBIDDEN,
        )

    return check_accessible
