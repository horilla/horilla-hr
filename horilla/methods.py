import contextlib
import importlib

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from horilla_auth.models import HorillaUser


def get_horilla_model_class(app_label, model):
    """
    Retrieves the model class for the given app label and model name using Django's ContentType framework.

    Args:
        app_label (str): The label of the application where the model is defined.
        model (str): The name of the model to retrieve.

    Returns:
        Model: The Django model class corresponding to the specified app label and model name.

    """
    content_type = ContentType.objects.get_by_natural_key(app_label, model)
    model_class = content_type.model_class()
    return model_class


def get_session_key(request):
    """
    The request's session key, creating and saving the session if it has none.

    Sessions are not created for every request: an API client authenticated
    by token, or a first visit, arrives without one. Use this wherever a
    session key is needed (per-session cache keys and state), so a session
    is only created where it is actually used.
    """
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_accessibility_cache_key(request):
    """
    The cache key for the request's feature accessibility.

    Web requests use the session's key, which the accessibility middleware
    fills. A client authenticated by token that keeps no cookies (the mobile
    app) uses a key derived from its user instead, so it does not create a
    session on every call.
    """
    if not request.session.session_key and request.user.is_authenticated:
        return f"user-{request.user.pk}accessibility_filter"
    return get_session_key(request) + "accessibility_filter"


def dynamic_attr(obj, attribute_path):
    """
    Retrieves the value of a nested attribute from a related object dynamically.

    Args:
        obj: The base object from which to start accessing attributes.
        attribute_path (str): The path of the nested attribute to retrieve, using
        double underscores ('__') to indicate relationship traversal.

    Returns:
        The value of the nested attribute if it exists, or None if it doesn't exist.
    """
    attributes = attribute_path.split("__")

    for attr in attributes:
        with contextlib.suppress(Exception):
            Contract = get_horilla_model_class(app_label="payroll", model="contract")
            if isinstance(obj.first(), Contract):
                obj = obj.filter(is_active=True).first()

        obj = getattr(obj, attr, None)
        if obj is None:
            break
    return obj


def horilla_users_with_perms(permissions):
    """
    Filters users who have any of the specified permissions or are superusers.

    :param permissions: A list of permission strings in the format 'app_label.codename'
                        or a single permission string.
    :return: A queryset of users who have any of the specified permissions or are superusers.
    """
    # Ensure permissions is a list even if a single permission string is provided
    if isinstance(permissions, str):
        permissions = [permissions]

    # Start with a queryset that includes all superusers
    users_with_permissions = HorillaUser.objects.filter(is_superuser=True)

    # Filter users based on the permissions list
    for perm in permissions:
        app_label, codename = perm.split(".")
        users_with_permissions |= HorillaUser.objects.filter(
            user_permissions__codename=codename,
            user_permissions__content_type__app_label=app_label,
        )

    return users_with_permissions.distinct()


def handle_no_permission(request, message=_("You don't have permission.")):
    messages.info(request, message)
    # Sec-Fetch-Mode is set by the browser itself for a genuine top-level
    # navigation and can't be spoofed by an htmx fetch() call, unlike the
    # HX-Request header alone -- some browser setups send HX-Request even on
    # a real address-bar visit, which would otherwise render the raw
    # fragment instead of redirecting (e.g. to the login page).
    is_real_navigation = request.headers.get("Sec-Fetch-Mode") == "navigate"
    if request.headers.get("HX-Request") and not is_real_navigation:
        return render(request, "decorator_404.html")

    previous_url = request.META.get("HTTP_REFERER", "/")

    # Prevent open redirect + XSS
    if not url_has_allowed_host_and_scheme(
        previous_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        previous_url = "/"

    return redirect(previous_url)


def get_urlencode(request):
    get_data = request.GET.copy()
    get_data.pop("instances_ids", None)
    previous_data = get_data.urlencode()
    return previous_data


def remove_dynamic_url(path_info):
    """Function to remove a dynamically added URL from any app's urlpatterns."""

    # Iterate over all app URL patterns
    for app_urls in settings.APP_URLS:
        try:
            # Dynamically import the app's urls.py module
            urls_module = importlib.import_module(app_urls)
            # Access the urlpatterns in the module
            urlpatterns = getattr(urls_module, "urlpatterns", None)

            if urlpatterns:
                # Check if the pattern exists in this app's urlpatterns
                for path in urlpatterns:
                    if path.name == path_info:
                        urlpatterns.remove(path)
                        break

        except ModuleNotFoundError:
            print(f"Module {app_urls} not found. Skipping...")

    # Also remove it from the tracked dynamic paths
    if path_info in settings.DYNAMIC_URL_PATTERNS:
        settings.DYNAMIC_URL_PATTERNS.remove(path_info)
