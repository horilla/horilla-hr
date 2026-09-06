import json
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer
from django import template
from django.core.paginator import Page, Paginator
from django.utils.safestring import mark_safe

from base.methods import get_pagination
from base.models import MultipleApprovalManagers
from employee.models import Employee, EmployeeWorkInformation
from horilla.menu.settings_menu import get_settings_menu

register = template.Library()

# Tags and attributes the rich-text editors in this app legitimately produce.
# Deliberately excludes script/style/iframe/object/embed and every event
# handler, so stored markup cannot execute.
_ALLOWED_HTML_TAGS = {
    # "img" is here because these fields are written in a rich-text editor and
    # people paste screenshots into them -- a helpdesk ticket whose screenshot
    # silently vanished on upgrade is a support problem, not a security win.
    # The src protocol allow-list below is what keeps it safe.
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
_ALLOWED_HTML_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    # "style" so that colour and emphasis applied in the editor survive.
    "*": ["class", "style"],
}

# Only properties a rich-text editor actually emits, and only ones whose values
# are plain keywords or literals. Nothing here needs a CSS function, which is
# what _StrictCSSSanitizer relies on.
_ALLOWED_CSS_PROPERTIES = [
    "color",
    "background-color",
    "font-size",
    "font-weight",
    "font-style",
    "text-align",
    "text-decoration",
]


class _StrictCSSSanitizer(CSSSanitizer):
    """Reject declarations whose value contains a CSS function call.

    bleach validates the property NAME against the allow-list but does not
    look at the VALUE, so `color: expression(alert(1))` passes its filter
    untouched -- verified against bleach 6.4.0. That is a legacy IE vector
    rather than a live one in current browsers, but a sanitiser that emits it
    is not doing its job, and restricting the property list does not help
    because the payload rides on whichever property is allowed.

    None of _ALLOWED_CSS_PROPERTIES needs a function value, so dropping any
    declaration containing one costs nothing and closes the whole class --
    expression(), url(), image-set() and anything added later.
    """

    _FUNCTION_CALL = re.compile(r"[a-z-]+\s*\(", re.IGNORECASE)

    def sanitize_css(self, style):
        declarations = []
        for declaration in super().sanitize_css(style).split(";"):
            if not declaration.strip():
                continue
            _, _, value = declaration.partition(":")
            if self._FUNCTION_CALL.search(value):
                continue
            declarations.append(declaration.strip())
        return "; ".join(declarations) + (";" if declarations else "")


_CSS_SANITIZER = _StrictCSSSanitizer(allowed_css_properties=_ALLOWED_CSS_PROPERTIES)


@register.filter(name="sanitize_html")
def sanitize_html(value):
    """
    Render user-authored rich text without trusting it.

    These fields (ticket descriptions and comments, recruitment
    descriptions, policy bodies, OKR comments) were previously rendered
    with ``|safe``. The only thing standing between a user and stored XSS
    was the ``has_xss`` regex applied at write time, which is a blocklist
    and not a parser -- anything it fails to match became executable HTML
    in every viewer's session. This strips to an allow-list instead, so a
    gap in that regex is no longer exploitable.
    """
    if not value:
        return ""
    return mark_safe(
        bleach.clean(
            str(value),
            tags=_ALLOWED_HTML_TAGS,
            attributes=_ALLOWED_HTML_ATTRS,
            # No "data": a data: URI on an <img> can carry text/html, which is
            # a script delivery vector. Pasted screenshots that were inlined as
            # base64 are dropped; hosted ones survive.
            protocols=["http", "https", "mailto"],
            css_sanitizer=_CSS_SANITIZER,
            strip=True,
        )
    )


@register.filter
def equals(value, arg):
    """Check if value equals arg"""
    return value == arg


def _get_employee_of_user(user):
    """
    Resolve the Employee for a user once per request and cache it on the
    user object - this tag/filter is called once per row in list views, and
    without this cache each call re-issues the same lookup query.
    """
    if not hasattr(user, "_horilla_employee_cache"):
        user._horilla_employee_cache = Employee.objects.filter(
            employee_user_id=user
        ).first()
    return user._horilla_employee_cache


@register.simple_tag
def is_manager_of(user, instance, field_name="employee_id"):
    employee = _get_employee_of_user(user)

    target_employee = getattr(instance, field_name, None)

    if not hasattr(user, "_horilla_is_manager_of_cache"):
        user._horilla_is_manager_of_cache = {}
    cache = user._horilla_is_manager_of_cache
    key = (getattr(employee, "id", None), getattr(target_employee, "id", None))
    if key not in cache:
        cache[key] = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=employee, employee_id=target_employee
        ).exists()
    return cache[key]


@register.filter(name="is_reportingmanager")
def is_reportingmanager(user):
    """

    This method will return true if the user employee profile is reporting manager to any employee
    """
    employee = _get_employee_of_user(user)
    return EmployeeWorkInformation.objects.filter(
        reporting_manager_id=employee
    ).exists()


@register.filter(name="is_leave_approval_manager")
def is_leave_approval_manager(user):
    """
    This method will return true if the user is comes in MultipleApprovalCondition model as approving manager
    """
    if hasattr(user, "_horilla_is_leave_approval_manager_cache"):
        return user._horilla_is_leave_approval_manager_cache
    employee = _get_employee_of_user(user)
    manager = (
        MultipleApprovalManagers.objects.entire()
        .filter(employee_id=employee.id)
        .exists()
        if employee
        else False
    )
    user._horilla_is_leave_approval_manager_cache = manager
    return manager


@register.filter(name="check_manager")
def check_manager(user, instance):
    try:
        if isinstance(instance, Employee):
            return instance.employee_work_info.reporting_manager_id == user.employee_get
        return (
            user.employee_get
            == instance.employee_id.employee_work_info.reporting_manager_id
        )
    except:
        return False


@register.filter(name="filtersubordinates")
def filtersubordinates(user):
    """
    This method returns true if the user employee has corresponding related reporting manager object in EmployeeWorkInformation model
    args:
        user    : request.user
    """

    employee = user.employee_get
    employee_manages = employee.reporting_manager.all()
    return employee_manages.exists()


@register.filter(name="filter_field")
def filter_field(value):
    if value.endswith("_id"):
        value = value[:-3]
    if value.endswith("_ids"):
        value = value[:-4]
    splitted = value.split("__")

    return splitted[-1].replace("_", " ").capitalize()


@register.filter(name="user_perms")
def user_perms(perms):
    """
    permission names return method
    """
    return json.dumps(list(perms.values_list("codename", flat="True")))


@register.filter(name="all_user_perms")
def all_user_perms(user):
    """
    Return JSON list of effective permission codenames for a user for the
    currently selected company (group assignments + direct user permissions).
    """
    if not user:
        return json.dumps([])
    from base.auth_backends import get_effective_permission_codenames

    return json.dumps(get_effective_permission_codenames(user))


@register.filter(name="company_user_groups")
def company_user_groups(user):
    """
    Groups assigned to the user in the currently selected company.
    """
    from base.auth_backends import get_user_groups_for_company

    if not user:
        return []
    return list(get_user_groups_for_company(user))


@register.filter(name="abs_value")
def abs_value(value):
    """
    permission names return method
    """
    return abs(value)


@register.filter(name="startswith")
def startswith(value, arg):
    """Checks if the value starts with the provided argument."""
    return value.startswith(arg)


@register.filter(name="has_content")
def has_content(value):
    """Returns True if the input string has non-whitespace content."""
    if isinstance(value, str):
        return bool(value.strip())
    return True


@register.filter(name="readable")
def readable(value):
    try:
        value = value.replace("_", " ").replace("id", "").title()
    except:
        value = value
    return value


@register.simple_tag(takes_context=True)
def general_section_main(context):
    user = context["request"].user

    if not user.is_authenticated:
        return False

    return any(
        [
            user.has_perm("base.change_announcementexpire"),
            user.has_perm("base.view_dynamicpagination"),
            user.has_perm("horilla_audit.view_accountblockunblock"),
            user.has_perm("offboarding.change_offboardinggeneralsetting"),
            user.has_perm("attendance.change_attendancegeneralsetting"),
            user.has_perm("payroll.change_payrollgeneralsetting"),
            user.has_perm("employee.change_employeegeneralsetting"),
            user.has_perm("payroll.change_encashmentgeneralsettings"),
            user.has_perm("horilla_audit.view_historytrackingfields"),
            user.has_perm("payroll.view_payrollsettings"),
            user.has_perm("auth.view_permission"),
            user.has_perm("auth.view_group"),
            user.has_perm("base.view_company"),
            user.has_perm("base.view_tags"),
            user.has_perm("employee.view_employeetag"),
            user.has_perm("horilla_audit.view_audittag"),
            user.has_perm("base.view_dynamicemailconfiguration"),
            user.has_perm("horilla_backup.view_googledrivebackup"),
        ]
    )


@register.simple_tag(takes_context=True)
def general_section(context):
    user = context["request"].user

    if not user.is_authenticated:
        return False

    return any(
        [
            user.has_perm("base.change_announcementexpire"),
            user.has_perm("base.view_dynamicpagination"),
            user.has_perm("horilla_audit.view_accountblockunblock"),
            user.has_perm("offboarding.change_offboardinggeneralsetting"),
            user.has_perm("attendance.change_attendancegeneralsetting"),
            user.has_perm("payroll.change_payrollgeneralsetting"),
            user.has_perm("employee.change_employeegeneralsetting"),
            user.has_perm("payroll.change_encashmentgeneralsettings"),
            user.has_perm("horilla_audit.view_historytrackingfields"),
            user.has_perm("payroll.view_payrollsettings"),
        ]
    )


@register.simple_tag(takes_context=True)
def employee_section(context):
    user = context["request"].user

    if not user.is_authenticated:
        return False

    return any(
        [
            user.has_perm("base.view_worktype"),
            user.has_perm("base.view_rotatingworktype"),
            user.has_perm("base.view_employeeshift"),
            user.has_perm("base.view_rotatingshift"),
            user.has_perm("base.view_employeeshiftschedule"),
            user.has_perm("base.view_employeetype"),
            user.has_perm("employee.view_actiontype"),
            user.has_perm("employee.view_employeetag"),
        ]
    )


@register.simple_tag(takes_context=True)
def attendance_section(context):
    user = context["request"].user

    if not user.is_authenticated:
        return False

    return any(
        [
            user.has_perm("attendance.view_attendancevalidationcondition"),
            user.has_perm("base.view_biometricattendance"),
            user.has_perm("attendance.add_attendance"),
            user.has_perm("geofencing.add_geofencing"),
            user.has_perm("facedetection.add_facedetection"),
        ]
    )


@register.simple_tag(takes_context=True)
def show_section(context):
    user = context["request"].user

    if not user.is_authenticated:
        return False

    return any(
        [
            user.has_perm("attendance.view_attendancevalidationcondition"),
            user.has_perm("helpdesk.view_departmentmanager"),
            user.has_perm("helpdesk.view_tickettype"),
            user.has_perm("employee.view_employeetag"),
            user.has_perm("pms.add_bonuspointsetting"),
            user.has_perm("payroll.view_payslipautogenerate"),
            user.has_perm("leave.add_restrictleave"),
            user.has_perm("base.view_biometricattendance"),
            user.has_perm("attendance.add_attendance"),
            user.has_perm("geofencing.add_geofencing"),
            user.has_perm("facedetection.add_facedetection"),
            user.has_perm("recruitment.view_recruitment"),
            user.has_perm("recruitment.view_rejectreason"),
            user.has_perm("recruitment.add_recruitment"),
            user.has_perm("recruitment.add_linkedinaccount"),
            user.has_perm("horilla_audit.view_accountblockunblock"),
            user.has_perm("offboarding.change_offboardinggeneralsetting"),
            user.has_perm("attendance.change_attendancegeneralsetting"),
            user.has_perm("payroll.change_payrollgeneralsetting"),
            user.has_perm("employee.change_employeegeneralsetting"),
            user.has_perm("payroll.change_encashmentgeneralsettings"),
            user.has_perm("payroll.view_payrollsettings"),
            user.has_perm("auth.view_permission"),
            user.has_perm("auth.view_group"),
            user.has_perm("horilla_audit.view_audittag"),
            user.has_perm("horilla_backup.view_googledrivebackup"),
            user.has_perm("horilla_ldap.add_ldapsettings"),
            user.has_perm("horilla_ldap.update_ldapsettings"),
            user.has_perm("employee.view_actiontype"),
            user.has_perm("base.view_tags"),
            user.has_perm("whatsapp.view_whatsappcredientials"),
            user.has_perm("base.view_company"),
            user.has_perm("base.view_tags"),
            user.has_perm("base.view_dynamicemailconfiguration"),
            user.has_perm("base.view_department"),
            user.has_perm("base.view_jobposition"),
            user.has_perm("base.view_jobrole"),
            user.has_perm("base.view_worktype"),
            user.has_perm("base.view_rotatingworktype"),
            user.has_perm("base.view_employeeshift"),
            user.has_perm("base.view_rotatingshift"),
            user.has_perm("base.view_employeeshiftschedule"),
            user.has_perm("base.view_employeetype"),
            user.has_perm("base.change_announcementexpire"),
            user.has_perm("base.view_dynamicpagination"),
            user.has_perm("horilla_backup.view_googledrivebackup"),
            user.has_perm("recruitment.view_linkedinaccount"),
            user.has_perm("horilla_ldap.add_ldapsettings"),
            user.has_perm("horilla_ldap.update_ldapsettings"),
            user.has_perm("horilla_meet.view_googlecloudcredential"),
            user.has_perm("whatsapp.add_whatsappcredientials"),
            user.has_perm("horilla_theme.view_horillacolortheme"),
        ]
    )


@register.simple_tag(takes_context=True)
def settings_menu(context):

    request = context.get("request")
    if request is None:
        return []
    return get_settings_menu(request)


@register.simple_tag
def settings_search_index():
    """
    Build the settings search index dynamically from the settings_registry.

    Each item in a sidebar class can declare a ``search_entries`` list of
    ``{"text": ..., "description": ...}`` dicts for field-level search
    granularity.  Items without ``search_entries`` fall back to a single
    page-level entry using the item label.

    To add new searchable fields for a settings page, open the relevant
    ``<app>/sidebar.py``, find the item dict, and add/extend its
    ``search_entries`` list — no changes needed anywhere else.
    """
    import json

    from horilla.menu.settings_menu import settings_registry

    entries = []
    seen = set()  # (text_lower, url) pairs — prevents exact duplicates

    for cls in settings_registry._entries:
        obj = cls()
        section = str(getattr(obj, "title", ""))
        for item in getattr(obj, "items", []):
            page = str(item.get("label", ""))
            try:
                url = str(item.get("url", ""))
            except Exception:
                continue
            if not page or not url:
                continue

            search_entries = item.get("search_entries", [])
            if search_entries:
                for entry in search_entries:
                    text = str(entry.get("text", ""))
                    description = str(entry.get("description", ""))
                    key = (text.lower(), url)
                    if not text or key in seen:
                        continue
                    seen.add(key)
                    anchor = str(entry.get("anchor", ""))
                    entries.append(
                        {
                            "text": text,
                            "description": description,
                            "section": section,
                            "page": page,
                            "url": f"{url}#{anchor}" if anchor else url,
                        }
                    )
            else:
                # Fallback: page label only (no field-level granularity yet)
                key = (page.lower(), url)
                if key not in seen:
                    seen.add(key)
                    entries.append(
                        {
                            "text": page,
                            "description": "",
                            "section": section,
                            "page": page,
                            "url": url,
                        }
                    )

    return json.dumps(entries, ensure_ascii=False)


@register.filter(name="config_perms")
def config_perms(user):
    from django.apps import apps

    app_permissions = {
        "leave": ["leave.view_restrictleave"],
        "base": [
            "base.add_holidays",
            "base.change_holidays",
            "base.add_companyleaves",
            "base.change_companyleaves",
            "base.add_horillamailtemplates",
            "base.view_horillamailtemplates",
        ],
    }
    for app, perms in app_permissions.items():
        if apps.is_installed(app):
            for perm in perms:
                if user.has_perm(perm):
                    return True
    return False
