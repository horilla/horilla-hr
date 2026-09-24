"""
context_processors.py

Injects the list of SSO-enabled companies into every template's context,
so login.html can offer a company picker without base.views.login_user
needing to know anything about OIDC. login_user stays exactly as it is --
this is the seam the codebase already uses for template-wide context
(horilla.config.get_MENUS, horilla_crumbs.context_processors.breadcrumbs)
rather than threading a new argument through every view that might render
a page with a login link.
"""

from base.models import Company


def sso_companies(request):
    if request.user.is_authenticated:
        # Only relevant on the pre-login page; skip the query otherwise.
        return {}
    companies = Company.objects.filter(
        oidc_provider__is_enabled=True
    ).select_related("oidc_provider")
    return {"sso_companies": companies}
