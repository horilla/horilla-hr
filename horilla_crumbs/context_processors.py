import logging
import re
import uuid
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, path, resolve, reverse
from django.utils.translation import gettext as _trans
from django.utils.translation import gettext_lazy as _

from base.context_processors import white_labelling_company
from employee.models import Employee
from horilla.urls import urlpatterns

logger = logging.getLogger(__name__)

# Final path segment that looks like a file, e.g. "logo.png", "app.min.js.map".
_FILE_SEGMENT = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def is_asset_request(request):
    """
    True for static/media or file URLs — these are not navigable pages.

    A missing asset 404s, and the 404 page still renders this processor, which
    would otherwise push path segments like "static / images / ui / xx.png"
    (or sourcemap probes such as "app.min.js.map") into the breadcrumb trail.
    """
    path_info = request.path
    for prefix in (settings.STATIC_URL, settings.MEDIA_URL):
        if prefix and path_info.startswith(prefix):
            return True
    last_segment = path_info.rstrip("/").rsplit("/", 1)[-1]
    return bool(_FILE_SEGMENT.search(last_segment))


def is_valid_uuid(uuid_string):
    try:
        uuid.UUID(uuid_string, version=4)
        return True
    except ValueError:
        return False


def _split_path(self, path=None):

    path = path or self.path
    path = path.strip("/")
    parts = path.split("/") if path else []

    if parts and parts[0] in ("static", "media"):
        return []

    return parts


def _resolve_menu_section(path, menus):
    """
    Find the top-level sidebar section (a MENU entry from some app's
    sidebar.py) that owns a submenu whose redirect matches the given path,
    either exactly or as a parent path (e.g. an employee detail page under
    the Employees list submenu). Returns (section_label, submenu_redirect)
    for the longest/most specific matching submenu, or None if nothing
    matches (e.g. settings pages, which aren't part of the main sidebar).
    """
    best = None
    for menu in menus or []:
        for submenu in menu.get("submenu", []):
            redirect = submenu.get("redirect") or ""
            if not redirect:
                continue
            if path == redirect or path.startswith(redirect):
                if best is None or len(redirect) > len(best[1]):
                    best = (str(menu.get("menu", "")), redirect)
    if best is not None:
        return best

    # No submenu redirect is a prefix of this path - typical for a detail
    # page reached from a list view rather than the list view's own URL
    # (e.g. project's "task-view/<id>" vs. its list page "project-view").
    # Fall back to matching on the shared leading URL segment so the page
    # still resolves to its app's own top-level menu label instead of
    # falling through to the raw path segment, which produces a second,
    # differently-cased duplicate of the same section in the breadcrumb.
    path_root = path.strip("/").split("/")[0] if path.strip("/") else ""
    if not path_root:
        return None
    for menu in menus or []:
        for submenu in menu.get("submenu", []):
            redirect = submenu.get("redirect") or ""
            redirect_root = redirect.strip("/").split("/")[0] if redirect else ""
            if redirect_root and redirect_root == path_root:
                return (str(menu.get("menu", "")), redirect)
    return None


def sync_session_ids(request, key, queryset):
    ids = list(queryset.values_list("id", flat=True))
    if request.session.get(key) != ids:
        request.session[key] = ids


BREADCRUMB_URL_NAMES = {
    "monthly-summary": _("Monthly Summary"),
    "ess": "Employee",
    "offboarding": "Offboarding",
    "helpdesk": "Helpdesk",
    "policies-discipline": "Policies & Discipline",
    "work-schedules": "Work Schedules",
    "requests": "Requests",
    "employee-settings-view": "Configuration",
    "recruitment-settings-view": "Configuration",
    "helpdesk-settings-view": "Configuration",
    "leave-settings-view": "Configuration",
    "payroll-settings-view": "Configuration",
    "performance-settings-view": "Configuration",
    "user-group-view": "Roles and Permissions",
    "employee-permission-assign": "Roles and Permissions",
}

sidebar_urls = [
    "dashboard",
    "ess",
    "pipeline",
    "recruitment-survey-question-template-view",
    "candidate-view",
    "recruitment-view",
    "stage-view",
    "view-onboarding-dashboard",
    "onboarding-view",
    "candidates-view",
    "employee-profile",
    "employee-view",
    "shift-request-view",
    "work-type-request-view",
    "rotating-shift-assign",
    "rotating-work-type-assign",
    "view-payroll-dashboard",
    "view-contract",
    "view-allowance",
    "view-deduction",
    "view-payslip",
    "filing-status-view",
    "attendance-view",
    "work-records",
    "request-attendance-view",
    "attendance-overtime-view",
    "monthly-summary",
    "attendance-activity-view",
    "late-come-early-out-view",
    "view-my-attendance",
    "leave-dashboard",
    "leave-employee-dashboard",
    "user-leave",
    "user-request-view",
    "leave-allocation-request-view",
    "type-view",
    "assign-view",
    "request-view",
    "holiday-view",
    "company-leave-view",
    "dashboard-view",
    "objective-list-view",
    "feedback-view",
    "asset-category-view",
    "asset-request-allocation-view",
    "settings",
    "attendance-settings",
    "geo-face-config",
    "employee-permission-assign",
    "user-group-assign",
    "currency",
    "department-view",
    "job-position-view",
    "job-role-view",
    "work-type-view",
    "rotating-work-type-view",
    "employee-type-view",
    "employee-shift-view",
    "employee-shift-schedule-view",
    "rotating-shift-view",
    "attendance-settings-view",
    "user-group-view",
    "company-view",
    "document-request-view",
    "faq-category-view",
    "ticket-view",
    "tag-view",
    "audit-history-view",
    "ticket-type-view",
    "mail-server-conf",
    "mail-templates-view",
    "multiple-approval-condition",
    "skill-zone-view",
    "view-mail-templates",
    "view-loan",
    "view-reimbursement",
    "department-manager-view",
    "date-settings",
    "offboarding-pipeline",
    "pagination-settings-view",
    "organisation-chart",
    "disciplinary-actions",
    "roster",
    "view-policies",
    "resignation-requests-view",
    "action-type",
    "general-settings",
    "view-biometric-devices",
    "employee-tag-view",
    "grace-settings-view",
    "helpdesk-tag-view",
    "restrict-view",
    "asset-history",
    "view-key-result",
    "view-meetings",
    "interview-view",
    "view-compensatory-leave",
    "compensatory-leave-settings-view",
    "project-dashboard-view",
    "project-view",
    "view-time-sheet",
    "templates",
    "sidebar.html",
    "objective-detailed-view",
    "mail-automations",
    "mail-automations-view",
    "faq-view",
    "auto-payslip-settings-view",
    "bonus-point-setting",
    "employee-past-leave-restriction",
    "track-late-come-early-out",
    "enable-biometric-attendance",
    "allowed-ips",
    "self-tracking-feature",
    "candidate-reject-reasons",
    "skills-view",
    "employee-bonus-point",
    "mail-automations",
    "task-all",
    "check-in-check-out-setting",
    "user-accessibility",
    "asset-batch-view",
    "task-all",
    "gdrive",
    "color-settings",
    "employee-report",
    "employee-pivot",
    "recruitment-report",
    "recruitment-pivot",
    "attendance-report",
    "attendance-pivot",
    "leave-report",
    "leave-pivot",
    "payroll-report",
    "payroll-pivot",
    "asset-report",
    "asset-pivot",
    "pms-report",
    "pms-pivot",
    "linkedin-integration-setting",
    "ldap-settings",
    "gmeet-setting",
    "whatsapp-credential-view",
    "cbv-pipeline",
    "gmeet-view",
    "color-theme-view",
    "survey-template-preview",
    "system-preferences-view",
    "default-export-access",
    "encashment-settings-view",
    "attendance-rule-view",
    "leave-rules-view",
    "restrict-leaves-view",
    "holidays-view",
    "company-leaves-view",
    "offboarding-rules-view",
    "grace-time-view",
    "audit-history",
    "policies-discipline",
    "work-schedules",
    "requests",
    "employee-settings-view",
    "recruitment-settings-view",
    "helpdesk-settings-view",
    "leave-settings-view",
    "payroll-settings-view",
    "performance-settings-view",
    "tours",
    "templates-periods",
]
remove_urls = [
    "feedback-detailed-view",
    "question-template-detailed-view",
    "employee-view-new",
    "objective-detailed-view",
    "ticket-detail",
    "faq-view",
    "get-job-positions",
    "task-view",
    "dashboard",
]

user_breadcrumbs = {}


def breadcrumbs_legacy(request):
    """
    Legacy session-accumulated breadcrumb trail.

    Superseded by build_breadcrumbs()/breadcrumbs() below, which recompute
    the trail statelessly from the current request's path on every call
    instead of accumulating it in the session across requests. Kept here
    unused, for reference and as an easy rollback if the stateless version
    needs to be reverted.
    """
    base_url = request.build_absolute_uri("/")
    company = white_labelling_company(request)["white_label_company_name"]

    # Initialize breadcrumbs in the session if not already present
    if "breadcrumbs" not in request.session:
        request.session["breadcrumbs"] = [
            {
                "url": base_url,
                "name": company,
                "found": True,
                "clickable": True,
            }
        ]

    # Drop asset entries an earlier release may have stored in the session.
    cleaned = [
        crumb
        for crumb in request.session["breadcrumbs"]
        if not _FILE_SEGMENT.search(crumb.get("name", ""))
    ]
    if len(cleaned) != len(request.session["breadcrumbs"]):
        request.session["breadcrumbs"] = cleaned

    # An asset request must never extend the trail (see is_asset_request).
    if is_asset_request(request):
        return {"breadcrumbs": request.session["breadcrumbs"]}

    try:
        breadcrumbs = request.session["breadcrumbs"]

        qs = request.META.get("QUERY_STRING", "")
        pairs = qs.split("&")
        filtered_pairs = [pair for pair in pairs if "=" in pair and pair.split("=")[1]]
        filtered_query_string = "&".join(filtered_pairs)
        emp_query_string = None

        for item in breadcrumbs:
            if item["name"] in ["employee-view", "candidate-view"]:
                items = item["url"].split("?", 1)
                if len(items) > 1:
                    emp_query_string = items[1]
                    break

        parts = _split_path(request)
        path = base_url

        # Section-aware breadcrumb: instead of guessing the top-level label from
        # the raw first URL segment, look it up in the same sidebar MENU/SUBMENUS
        # registry that drives the actual left nav (see any app's sidebar.py).
        # The one exception is the main Dashboard: it isn't a "section" of its
        # own, so when the user actually came from there (via HTTP_REFERER,
        # rather than a one-off query marker) we show "Dashboard" instead of
        # whatever section the destination page belongs to.
        menus = getattr(request, "MENUS", None)
        if menus is None:
            try:
                from horilla.config import sidebar as _build_sidebar_menus

                _build_sidebar_menus(request)
                menus = getattr(request, "MENUS", [])
            except Exception:
                menus = []

        current_section = _resolve_menu_section(request.path, menus)

        section_override = None
        try:
            dashboard_path = reverse("dashboard")
        except Exception:
            dashboard_path = None

        referer = request.META.get("HTTP_REFERER")
        if referer and dashboard_path:
            referer_path = urlparse(referer).path
            if referer_path.rstrip("/") == dashboard_path.rstrip("/"):
                section_override = {"name": _trans("Dashboard"), "url": dashboard_path}

        if len(parts) > 1:

            if "recruitment" in parts and apps.is_installed("recruitment"):
                if "search-candidate" in parts:
                    pass
                elif "candidate-view" in parts:
                    pass
                elif "get-mail-log-rec" in parts:
                    pass
                else:
                    from recruitment.models import Candidate

                    sync_session_ids(
                        request,
                        "filtered_candidates",
                        Candidate.objects.filter(is_active=True),
                    )

            if "employee-filter-view" in parts:
                pass
            elif "employee-view" in parts:
                pass
            elif "view-penalties" in parts:
                pass
            elif parts[0] == "employee" and parts[-1].isdigit():
                pass
            else:
                sync_session_ids(request, "filtered_employees", Employee.objects.all())

        if len(parts) == 0:
            request.session["breadcrumbs"].clear()
            breadcrumbs.append({"url": base_url, "name": company, "found": True})

        if len(parts) == 1 and parts[0] in sidebar_urls:
            first_path = breadcrumbs[0]
            request.session["breadcrumbs"].clear()
            request.session["breadcrumbs"].append(first_path)

        if len(parts) > 1:
            last_path = parts[-1]
            if (
                last_path in sidebar_urls
                or parts[-2] == "employee-view"
                or parts[-2] == "candidate-view"
                or parts[-2] == "view-payslip"
            ):
                first_path = breadcrumbs[0]
                request.session["breadcrumbs"].clear()
                request.session["breadcrumbs"].append(first_path)

        for i, item in enumerate(parts):
            path = path + item + "/"
            parsed_url = urlparse(path)
            check_path = parsed_url.path
            try:
                resolver_match = resolve(check_path)
                found = True
            except Resolver404:
                found = False

            clickable = True
            if found and not request.user.is_superuser:
                view_func = resolver_match.func
                required_perms = getattr(view_func, "_required_perms", [])
                if not required_perms:
                    redirect_to = getattr(view_func, "_redirect_to", None)
                    if redirect_to:
                        try:
                            dest_path = reverse(redirect_to)
                            dest_match = resolve(dest_path)
                            required_perms = getattr(
                                dest_match.func, "_required_perms", []
                            )
                        except Exception:
                            pass
                if required_perms:
                    clickable = all(request.user.has_perm(p) for p in required_perms)

            new_dict = {
                "url": path,
                # str() resolves any gettext_lazy() entries to a plain string
                # now, in the request's own active locale, since breadcrumbs
                # get JSON-serialized into the session (a lazy translation
                # proxy isn't JSON-serializable and would 500 the request).
                "name": str(BREADCRUMB_URL_NAMES.get(item, item)),
                "found": found,
                "clickable": clickable,
            }

            if i == 0:
                if section_override:
                    new_dict["name"] = section_override["name"]
                    new_dict["url"] = base_url.rstrip("/") + section_override["url"]
                    new_dict["found"] = True
                elif current_section:
                    new_dict["name"] = current_section[0]

            if item == "attendance":
                from base.templatetags.basefilters import is_reportingmanager

                new_dict["clickable"] = (
                    request.user.is_superuser
                    or request.user.has_perm("attendance.view_attendance")
                    or is_reportingmanager(request.user)
                )

            if item.isdigit() or is_valid_uuid(item):
                # Handle the case when item is a digit (e.g., an ID)
                current_url = resolve(request.path_info)
                url_kwargs = current_url.kwargs
                model_value = url_kwargs.get("model")

                if model_value:
                    try:
                        obj = model_value.objects.get(id=item)  # completed
                        new_dict["name"] = str(obj)
                    except:
                        pass

            key = "HTTP_HX_REQUEST"
            sidebar_nav_key = "HTTP_HX_SIDEBAR_NAV"
            names = [d["name"] for d in breadcrumbs]
            if (
                new_dict not in breadcrumbs
                and new_dict["name"] not in remove_urls + names
                and (
                    key not in request.META.keys()
                    or request.META.get(sidebar_nav_key) == "true"
                )
                and not new_dict["name"].isdigit()
            ):
                if new_dict["name"] in ["employee-view", "candidate-view"]:
                    new_dict["url"] = f'{new_dict["url"]}?{emp_query_string}'

                breadcrumbs.append(new_dict)

        try:
            prev_url = breadcrumbs[-1]
            prev_url["url"] = prev_url["url"].split("?")[0]
            if filtered_query_string:
                prev_url["url"] = f'{prev_url["url"]}?{filtered_query_string}'
            else:
                prev_url["url"] = f'{prev_url["url"]}'
        except:
            pass

        request.session["breadcrumbs"] = breadcrumbs

    except Exception as e:
        request.session["breadcrumbs"] = [
            {"url": base_url, "name": company, "found": True}
        ]
    return {"breadcrumbs": request.session["breadcrumbs"]}


def build_breadcrumbs(request):
    """
    Compute the breadcrumb trail for the current request's path alone,
    independent of session state.
    """
    base_url = request.build_absolute_uri("/")
    company = white_labelling_company(request)["white_label_company_name"]
    root = {
        "url": f"{base_url}?breadcrumb_nav=true",
        "name": company,
        "found": True,
        "clickable": True,
    }

    if is_asset_request(request):
        return [root]

    parts = _split_path(request)
    if not parts:
        return [root]

    menus = getattr(request, "MENUS", None)
    if menus is None:
        try:
            from horilla.config import sidebar as _build_sidebar_menus

            _build_sidebar_menus(request)
            menus = getattr(request, "MENUS", [])
        except Exception:
            logger.exception("Failed building sidebar menus for breadcrumbs")
            menus = []

    current_section = _resolve_menu_section(request.path, menus)

    section_override = None
    referer = request.META.get("HTTP_REFERER")
    if referer and parts[0] != "settings":
        referer_path = urlparse(referer).path
        try:
            referer_url_name = resolve(referer_path).url_name or ""
        except Resolver404:
            referer_url_name = ""
        if "dashboard" in referer_url_name:
            referer_section = _resolve_menu_section(referer_path, menus)
            if referer_section and referer_section != current_section:
                section_override = {
                    "name": referer_section[0],
                    "url": referer_section[1],
                }
            elif referer_url_name == "dashboard" and current_section:
                section_override = {"name": _trans("Dashboard"), "url": referer_path}

    trail = [root]
    path = base_url
    for i, item in enumerate(parts):
        path = path + item + "/"
        check_path = urlparse(path).path
        try:
            resolver_match = resolve(check_path)
            found = True
        except Resolver404:
            resolver_match = None
            found = False

        clickable = True
        if found and not request.user.is_superuser:
            view_func = resolver_match.func
            required_perms = getattr(view_func, "_required_perms", [])
            if not required_perms:
                redirect_to = getattr(view_func, "_redirect_to", None)
                if redirect_to:
                    try:
                        dest_match = resolve(reverse(redirect_to))
                        required_perms = getattr(dest_match.func, "_required_perms", [])
                    except Exception:
                        pass
            if required_perms:
                clickable = all(request.user.has_perm(p) for p in required_perms)

        crumb = {
            "url": path,
            "name": str(BREADCRUMB_URL_NAMES.get(item, item)),
            "found": found,
            "clickable": clickable,
        }

        if i == 0:
            if section_override:
                crumb["name"] = section_override["name"]
                crumb["url"] = base_url.rstrip("/") + section_override["url"]
                crumb["found"] = True
            elif current_section:
                crumb["name"] = current_section[0]

            if found:
                redirect_to = getattr(resolver_match.func, "_redirect_to", None)
                if redirect_to:
                    try:
                        crumb["url"] = base_url.rstrip("/") + reverse(redirect_to)
                    except Exception:
                        pass

        if item == "attendance":
            from base.templatetags.basefilters import is_reportingmanager

            crumb["clickable"] = (
                request.user.is_superuser
                or request.user.has_perm("attendance.view_attendance")
                or is_reportingmanager(request.user)
            )

        if item.isdigit() or is_valid_uuid(item):
            url_kwargs = resolve(request.path_info).kwargs
            model_value = url_kwargs.get("model")
            if model_value:
                try:
                    crumb["name"] = str(model_value.objects.get(id=item))
                except Exception:
                    pass

        existing_names = [t["name"] for t in trail]
        if (
            crumb["name"] not in remove_urls + existing_names
            and not crumb["name"].isdigit()
        ):
            trail.append(crumb)

    # Preserve the current request's own (non-empty-valued) query string on
    # its own trail entry, so reloading/clicking it keeps the same filters.
    query_string = "breadcrumb_nav=true"
    extra_query_string = "&".join(
        pair
        for pair in request.META.get("QUERY_STRING", "").split("&")
        if "=" in pair and pair.split("=")[1] and pair.split("=")[0] != "breadcrumb_nav"
    )
    if extra_query_string:
        query_string = f"{query_string}&{extra_query_string}"
    if len(trail) > 1:
        trail[-1]["url"] = f'{trail[-1]["url"].split("?")[0]}?{query_string}'

    return trail


def breadcrumbs(request):
    """
    Active breadcrumbs context processor.
    """
    try:
        if is_asset_request(request):
            return {"breadcrumbs": request.session.get("breadcrumbs", [])}

        existing = request.session.get("breadcrumbs")
        has_existing = isinstance(existing, list) and existing

        if request.GET.get("breadcrumb_nav") == "true":
            return {
                "breadcrumbs": existing if has_existing else build_breadcrumbs(request)
            }

        local_trail = build_breadcrumbs(request)
        is_htmx = "HTTP_HX_REQUEST" in request.META
        is_sidebar_nav = request.META.get("HTTP_HX_SIDEBAR_NAV") == "true"
        is_push_nav = request.META.get("HTTP_HX_PUSH_NAV") == "true"

        if is_htmx and not is_sidebar_nav and not is_push_nav:
            trail = existing if has_existing else local_trail
            return {"breadcrumbs": trail}

        referer_path = urlparse(request.META.get("HTTP_REFERER") or "").path

        reset = (
            (is_htmx and is_sidebar_nav)
            or (not is_htmx and not referer_path)
            or len(local_trail) <= 1
        )

        if reset:
            trail = local_trail
        else:
            trail = existing if has_existing else local_trail
            leaf = local_trail[-1]
            if not trail or trail[-1].get("name") != leaf["name"]:
                trail = trail + [leaf]

        request.session["breadcrumbs"] = trail
        return {"breadcrumbs": trail}
    except Exception:
        logger.exception("Failed building breadcrumbs for %s", request.path)
        base_url = request.build_absolute_uri("/")
        company = white_labelling_company(request)["white_label_company_name"]
        fallback = [
            {"url": base_url, "name": company, "found": True, "clickable": True}
        ]
        request.session["breadcrumbs"] = fallback
        return {"breadcrumbs": fallback}


def _section_redirect(url_name):
    """Return a named redirect view that stores its destination for breadcrumb permission checks."""

    def _redirect(request):
        return redirect(url_name)

    _redirect._redirect_to = url_name
    return _redirect


def _leave_redirect(request):
    return redirect(reverse("leave-employee-dashboard") + "?dashboard=true")


def _attendance_redirect(request):
    from base.templatetags.basefilters import is_reportingmanager

    if (
        request.user.is_superuser
        or request.user.has_perm("attendance.view_attendance")
        or is_reportingmanager(request.user)
    ):
        return redirect("attendance-dashboard")
    return redirect("attendance-view")


urlpatterns.append(path("recruitment/", _section_redirect("recruitment-dashboard")))
urlpatterns.append(
    path("onboarding/", _section_redirect("onboarding-modern-dashboard"))
)
urlpatterns.append(path("employee/", _section_redirect("ess-dashboard")))
urlpatterns.append(path("attendance/", _attendance_redirect))
urlpatterns.append(path("leave/", _leave_redirect))
urlpatterns.append(path("payroll/", _section_redirect("view-payroll-dashboard")))
urlpatterns.append(path("pms/", _section_redirect("dashboard-view")))
urlpatterns.append(path("asset/", _section_redirect("asset-dashboard")))
urlpatterns.append(path("project/", _section_redirect("project-dashboard-view")))
urlpatterns.append(path("helpdesk/", _section_redirect("helpdesk-dashboard")))
