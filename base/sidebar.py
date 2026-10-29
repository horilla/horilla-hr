"""
base/sidebar.py

Settings menu registrations for the base app.

Sections registered:
  - General       : general settings, permissions, tags, mail
  - Base          : department, job position, job role, company
  - Appearance : color theme (only when horilla_theme is installed)
  - Integrations  : gdrive, linkedin, ldap, google meet, whatsapp
"""

from django.apps import apps
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from horilla.menu import settings_menu

# ---------------------------------------------------------------------------
# Accessibility functions
# ---------------------------------------------------------------------------


def system_preferences_accessibility(request, submenu, user_perms, *args, **kwargs):
    return any(
        request.user.has_perm(p)
        for p in [
            "base.change_announcementexpire",
            "base.view_dynamicpagination",
            "horilla_audit.view_accountblockunblock",
            "employee.change_employeegeneralsetting",
            "horilla_audit.view_historytrackingfields",
            "payroll.view_payrollsettings",
            "base.view_company",
            "base.view_companylanguagesetting",
        ]
    )


def general_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return system_preferences_accessibility(
        request, submenu, user_perms, *args, **kwargs
    )


def employee_permission_accessibility(request, submenu, user_perms, *args, **kwargs):
    # Direct permission assign: superadmin only
    return request.user.is_superuser


def accessibility_restriction_accessibility(
    request, submenu, user_perms, *args, **kwargs
):
    return request.user.has_perm("auth.view_permission")


def user_group_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.is_superuser


def date_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_company")


def history_tags_accessibility(request, submenu, user_perms, *args, **kwargs):
    return any(
        request.user.has_perm(p)
        for p in [
            "base.view_tags",
            "employee.view_employeetag",
            "horilla_audit.view_audittag",
        ]
    )


def audit_tracking_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("horilla_audit.view_auditmodelconfig")


def audit_history_accessibility(request, submenu, user_perms, *args, **kwargs):
    return any(
        request.user.has_perm(p)
        for p in [
            "horilla_audit.view_audittag",
            "horilla_audit.view_auditmodelconfig",
        ]
    )


def mail_server_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm(
        "base.view_dynamicemailconfiguration"
    ) and not apps.is_installed("outlook_auth")


def mail_template_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_horillamailtemplate")


def mail_automation_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("horilla_automations") and request.user.has_perm(
        "horilla_automations.view_mailautomation"
    )


def outlook_mail_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm(
        "base.view_dynamicemailconfiguration"
    ) and apps.is_installed("outlook_auth")


def department_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_department")


def job_position_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_jobposition")


def job_role_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_jobrole")


def company_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_company")


def holidays_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_holidays")


def company_leaves_settings_accessibility(
    request, submenu, user_perms, *args, **kwargs
):
    return request.user.has_perm("base.view_companyleaves")


def color_theme_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("horilla_theme.view_horillacolortheme")


def gdrive_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("horilla_backup.view_googledrivebackup")


def linkedin_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("recruitment.view_linkedinaccount")


def ldap_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("horilla_ldap") and any(
        request.user.has_perm(p)
        for p in ["horilla_ldap.add_ldapsettings", "horilla_ldap.update_ldapsettings"]
    )


def google_meet_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("horilla_meet") and request.user.has_perm(
        "horilla_meet.view_googlecloudcredential"
    )


def whatsapp_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("whatsapp") and request.user.has_perm(
        "whatsapp.add_whatsappcredientials"
    )


def default_export_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_defaultexportpermission")


# ---------------------------------------------------------------------------
# 1. General settings section
# ---------------------------------------------------------------------------


@settings_menu.register
class GeneralSettings:
    title = _("General")
    order = 1
    items = [
        {
            "label": _("System Preferences"),
            "url": reverse_lazy("system-preferences-view"),
            "accessibility": system_preferences_accessibility,
            "search_entries": [
                {
                    "text": _("Default Expire Days"),
                    "description": _(
                        "Auto-expiry days for announcements, configurable per company"
                    ),
                    "anchor": "setting-default-expire-days",
                },
                {
                    "text": _("Default Records Per Page"),
                    "description": _(
                        "Your personal rows-per-page preference for the selected company"
                    ),
                    "anchor": "setting-default-records-per-page",
                },
                {
                    "text": _("Badge ID Prefix"),
                    "description": _("Prefix added to employee badge IDs e.g. EMP0001"),
                    "anchor": "setting-badge-id-prefix",
                },
                {
                    "text": _("Currency Symbol"),
                    "description": _("Symbol shown for monetary values e.g. $ €"),
                    "anchor": "setting-currency-symbol",
                },
                {
                    "text": _("Currency Position"),
                    "description": _(
                        "Whether symbol appears before or after the amount"
                    ),
                    "anchor": "setting-currency-position",
                },
                {
                    "text": _("Date Format"),
                    "description": _("How dates are displayed across the system"),
                    "anchor": "setting-date-format",
                },
                {
                    "text": _("Time Format"),
                    "description": _("12-hour or 24-hour display format"),
                    "anchor": "setting-time-format",
                },
                {
                    "text": _("Restrict Login Account"),
                    "description": _("Allow admins to block or unblock employee login"),
                    "anchor": "setting-restrict-login-account",
                },
                {
                    "text": _("Restrict Profile Edit"),
                    "description": _(
                        "Prevent employees from editing their own profile"
                    ),
                    "anchor": "setting-restrict-profile-edit",
                },
                {
                    "text": _("Work Information Tracking"),
                    "description": _(
                        "Enable tracking of changes to employee work information fields for the selected company"
                    ),
                    "anchor": "setting-work-info-tracking",
                },
                {
                    "text": _("Tracking Fields"),
                    "description": _(
                        "Select which work information fields are recorded in change history"
                    ),
                    "anchor": "setting-tracking-fields",
                },
                {
                    "text": _("Enable Languages"),
                    "description": _(
                        "Restrict which languages appear in the navbar language switcher for this company"
                    ),
                    "anchor": "companyLanguageSettings",
                },
            ],
        },
        {
            "label": _("Menu Access Restrictions"),
            "url": reverse_lazy("user-accessibility"),
            "accessibility": accessibility_restriction_accessibility,
            "search_entries": [
                {
                    "text": _("Menu Access Restrictions"),
                    "description": _(
                        "Control which user roles can see which menu items"
                    ),
                },
            ],
        },
        {
            "label": _("Roles and Permissions"),
            "url": reverse_lazy("user-group-view"),
            "accessibility": user_group_accessibility,
            "search_entries": [
                {
                    "text": _("Roles and Permissions"),
                    "description": _(
                        "Create reusable roles and assign direct employee permissions"
                    ),
                },
                {
                    "text": _("Roles"),
                    "description": _("Create and manage reusable permission roles"),
                },
                {
                    "text": _("Employee Permissions"),
                    "description": _(
                        "Grant or revoke specific access rights per employee"
                    ),
                },
            ],
        },
        {
            "label": _("Audit & History"),
            "url": reverse_lazy("audit-history-view"),
            "accessibility": audit_history_accessibility,
            "search_entries": [
                {
                    "text": _("Audit & History"),
                    "description": _(
                        "View and configure audit logs and change history"
                    ),
                },
                {
                    "text": _("Audit Tags"),
                    "description": _("Create tags to categorise audit log records"),
                },
                {
                    "text": _("Audit Tracking"),
                    "description": _(
                        "Choose which models are recorded in the audit log"
                    ),
                },
                {
                    "text": _("Tracked Models"),
                    "description": _(
                        "Model paths whose changes are tracked in audit history"
                    ),
                },
            ],
        },
        {
            "label": _("Outlook Mail"),
            "url": reverse_lazy("outlook_view_records"),
            "accessibility": outlook_mail_accessibility,
            "search_entries": [
                {
                    "text": _("Outlook Mail"),
                    "description": _("Configure Microsoft 365 or Outlook email server"),
                },
                {
                    "text": _("Outlook Mail Server"),
                    "description": _("Microsoft Exchange or Outlook SMTP integration"),
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 2. Organization section
# ---------------------------------------------------------------------------


@settings_menu.register
class BaseSettings:
    title = _("Organization")
    order = 2
    items = [
        {
            "label": _("Companies"),
            "url": reverse_lazy("company-view"),
            "accessibility": company_accessibility,
            "search_entries": [
                {
                    "text": _("Company Name"),
                    "description": _("Legal name of the company"),
                },
                {"text": _("Company Address"), "description": _("Street address")},
                {
                    "text": _("Company Country"),
                    "description": _("Country where the company is registered"),
                },
                {"text": _("Company State"), "description": _("State or province")},
                {"text": _("Company City"), "description": _("City")},
                {"text": _("Company Zip"), "description": _("Postal or ZIP code")},
                {
                    "text": _("Company Logo"),
                    "description": _("Logo or icon for the company"),
                },
            ],
        },
        {
            "label": _("Departments"),
            "url": reverse_lazy("department-view"),
            "accessibility": department_accessibility,
            "search_entries": [
                {"text": _("Departments"), "description": _("Name of the department")},
                {
                    "text": _("Department Manager"),
                    "description": _("Manager assigned to the department"),
                },
            ],
        },
        {
            "label": _("Job Positions"),
            "url": reverse_lazy("job-position-view"),
            "accessibility": job_position_accessibility,
            "search_entries": [
                {
                    "text": _("Job Position"),
                    "description": _("Name of the job position"),
                },
            ],
        },
        {
            "label": _("Job Roles"),
            "url": reverse_lazy("job-role-view"),
            "accessibility": job_role_accessibility,
            "search_entries": [
                {"text": _("Job Roles"), "description": _("Name of the job role")},
            ],
        },
        {
            "label": _("Weekly Off Days"),
            "url": reverse_lazy("company-leaves-view"),
            "accessibility": company_leaves_settings_accessibility,
            "search_entries": [
                {
                    "text": _("Weekly Off Days"),
                    "description": _("Configure recurring weekly off days"),
                },
                {
                    "text": _("Based On Week"),
                    "description": _("Which week of the month the off day applies"),
                },
                {
                    "text": _("Based On Week Day"),
                    "description": _("Which day of the week is the off day"),
                },
            ],
        },
        # {
        #     "label": _("Public Holidays"),
        #     "url": reverse_lazy("holidays-view"),
        #     "accessibility": holidays_settings_accessibility,
        #     "search_entries": [
        #         {"text": _("Public Holiday"), "description": _("Name of the public holiday")},
        #         {"text": _("Holiday Start Date"), "description": _("Start date")},
        #         {"text": _("Holiday End Date"), "description": _("End date")},
        #         {"text": _("Recurring Holiday"), "description": _("Whether this holiday repeats every year")},
        #     ],
        # },
    ]


# ---------------------------------------------------------------------------
# 3. Mail section
# ---------------------------------------------------------------------------


@settings_menu.register
class MailSettings:
    title = _("Email")
    order = 3
    items = [
        {
            "label": _("Email Servers"),
            "url": reverse_lazy("mail-server-conf"),
            "accessibility": mail_server_accessibility,
            "search_entries": [
                {"text": _("Email Host"), "description": _("SMTP server hostname")},
                {"text": _("Email Port"), "description": _("SMTP server port number")},
                {
                    "text": _("Default From Email"),
                    "description": _("Sender email address for outgoing mail"),
                },
                {
                    "text": _("Email Host Username"),
                    "description": _("Username for SMTP authentication"),
                },
                {
                    "text": _("Display Name"),
                    "description": _("Name shown in From field of outgoing emails"),
                },
                {
                    "text": _("Email Authentication Password"),
                    "description": _("Password for SMTP authentication"),
                },
                {
                    "text": _("Use TLS"),
                    "description": _("Enable TLS encryption for SMTP"),
                },
                {
                    "text": _("Use SSL"),
                    "description": _("Enable SSL encryption for SMTP"),
                },
                {
                    "text": _("Fail Silently"),
                    "description": _("Suppress errors when email sending fails"),
                },
                {
                    "text": _("Primary Mail Server"),
                    "description": _("Mark as the primary outgoing mail server"),
                },
                {
                    "text": _("Email Send Timeout"),
                    "description": _("Timeout in seconds for SMTP connections"),
                },
                {
                    "text": _("Use Dynamic Display Name"),
                    "description": _(
                        "Use the triggering user's name as the sender display name"
                    ),
                },
            ],
        },
        {
            "label": _("Email Templates"),
            "url": reverse_lazy("mail-templates-view"),
            "accessibility": mail_template_accessibility,
            "search_entries": [
                {
                    "text": _("Email Templates"),
                    "description": _("Create reusable email body templates"),
                },
                {"text": _("Template Title"), "description": _("Name of the template")},
                {
                    "text": _("Template Body"),
                    "description": _("Rich-text body content of the template"),
                },
            ],
        },
        {
            "label": _("Email Automations"),
            "url": reverse_lazy("mail-automations-view"),
            "accessibility": mail_automation_accessibility,
            "search_entries": [
                {
                    "text": _("Email Automations"),
                    "description": _("Trigger automated emails on model events"),
                },
                {
                    "text": _("Automation Title"),
                    "description": _("Name of the automation rule"),
                },
                {
                    "text": _("Trigger Condition"),
                    "description": _(
                        "When the automation fires: On Create Update or Delete"
                    ),
                },
                {
                    "text": _("Delivery Channel"),
                    "description": _("Send via Email Notification or Both"),
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 5. Appearance section (only when horilla_theme is installed)
# ---------------------------------------------------------------------------


@settings_menu.register
class ThemeManagerSettings:
    title = _("Appearance")
    order = 10
    condition = lambda self, request: apps.is_installed("horilla_theme")
    items = [
        {
            "label": _("Color Theme"),
            "url": reverse_lazy("horilla_theme:color_theme_view"),
            "accessibility": color_theme_accessibility,
            "search_entries": [
                {
                    "text": _("Color Theme"),
                    "description": _(
                        "Select and apply a visual color theme for the application"
                    ),
                },
                {
                    "text": _("Theme Management"),
                    "description": _(
                        "Customise the UI appearance with preset color palettes"
                    ),
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 6. Integrations section
# ---------------------------------------------------------------------------


@settings_menu.register
class IntegrationsSettings:
    title = _("Integrations")
    order = 11
    items = [
        {
            "label": _("Google Drive Backup"),
            "url": reverse_lazy("gdrive"),
            "accessibility": gdrive_accessibility,
            "search_entries": [
                {
                    "text": _("Google Drive Backup"),
                    "description": _("Back up the database and media to Google Drive"),
                },
                {
                    "text": _("OAuth Credentials File"),
                    "description": _("Google OAuth 2.0 credentials JSON"),
                },
                {
                    "text": _("Google Drive Folder ID"),
                    "description": _("Google Drive folder where backups are stored"),
                },
                {
                    "text": _("Backup DB"),
                    "description": _("Include the database in the backup"),
                },
                {
                    "text": _("Backup Media"),
                    "description": _("Include media files in the backup"),
                },
                {
                    "text": _("Interval Backup"),
                    "description": _(
                        "Enable automatic backup at regular time intervals"
                    ),
                },
                {
                    "text": _("Fixed Time Backup"),
                    "description": _(
                        "Schedule an automatic backup at a fixed time each day"
                    ),
                },
            ],
        },
        {
            "label": _("LinkedIn"),
            "url": reverse_lazy("linkedin-integration-setting"),
            "accessibility": linkedin_accessibility,
            "search_entries": [
                {
                    "text": _("LinkedIn Integration"),
                    "description": _("Connect LinkedIn for job posting"),
                },
                {
                    "text": _("LinkedIn API Token"),
                    "description": _("API token for LinkedIn integration"),
                },
                {
                    "text": _("Enable LinkedIn"),
                    "description": _("Activate LinkedIn integration for job posting"),
                },
                {
                    "text": _("Post on LinkedIn"),
                    "description": _("Automatically post job openings to LinkedIn"),
                },
            ],
        },
        {
            "label": _("LDAP"),
            "url": reverse_lazy("ldap-settings"),
            "accessibility": ldap_accessibility,
            "search_entries": [
                {
                    "text": _("LDAP"),
                    "description": _("Connect to LDAP for employee authentication"),
                },
                {
                    "text": _("LDAP Server"),
                    "description": _("LDAP server address e.g. ldap://127.0.0.1:389"),
                },
                {
                    "text": _("Bind DN"),
                    "description": _("LDAP bind distinguished name"),
                },
                {
                    "text": _("Base DN"),
                    "description": _("LDAP base distinguished name for user search"),
                },
            ],
        },
        {
            "label": _("Google Meet"),
            "url": reverse_lazy("gmeet-setting"),
            "accessibility": google_meet_accessibility,
            "search_entries": [
                {
                    "text": _("Google Meet"),
                    "description": _("Configure Google Meet for interviews"),
                },
                {
                    "text": _("Google Cloud Project ID"),
                    "description": _("Google Cloud project ID"),
                },
                {
                    "text": _("Google Client ID"),
                    "description": _("OAuth client ID for Google Meet"),
                },
                {
                    "text": _("Google Client Secret"),
                    "description": _("OAuth client secret for Google Meet"),
                },
                {
                    "text": _("Enable Google Meet"),
                    "description": _(
                        "Activate Google Meet integration for video interviews"
                    ),
                },
                {
                    "text": _("Redirect URIs"),
                    "description": _("Authorised OAuth redirect URIs for Google Meet"),
                },
            ],
        },
        {
            "label": _("WhatsApp"),
            "url": reverse_lazy("whatsapp-credential-view"),
            "accessibility": whatsapp_accessibility,
            "search_entries": [
                {
                    "text": _("WhatsApp"),
                    "description": _(
                        "Configure WhatsApp Business API for notifications"
                    ),
                },
                {
                    "text": _("Meta Token"),
                    "description": _("WhatsApp Business API access token"),
                },
                {
                    "text": _("Meta Business ID"),
                    "description": _("WhatsApp Meta business account ID"),
                },
                {
                    "text": _("Meta Phone Number"),
                    "description": _("WhatsApp business phone number"),
                },
                {
                    "text": _("Webhook Token"),
                    "description": _("Token for verifying WhatsApp webhook callbacks"),
                },
                {
                    "text": _("Enable WhatsApp"),
                    "description": _("Activate WhatsApp Business API integration"),
                },
                {
                    "text": _("Meta Phone Number ID"),
                    "description": _("WhatsApp Meta phone number identifier"),
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 7. Master Data section
# ---------------------------------------------------------------------------


def master_import_accessibility(request, submenu, user_perms, *args, **kwargs):
    user = request.user
    return (
        user.is_superuser
        or user.has_perm("employee.add_employee")
        or user.has_perm("leave.add_availableleave")
        or user.has_perm("asset.add_assetassignment")
        or user.has_perm("asset.add_asset")
    )


@settings_menu.register
class MasterDataSettings:
    title = _("Master Data")
    order = 12
    condition = lambda self, request: apps.is_installed("master_import")
    items = [
        {
            "label": _("Import Data"),
            "url": reverse_lazy("master-import"),
            "accessibility": master_import_accessibility,
            "search_entries": [
                {
                    "text": _("Import Data"),
                    "description": _(
                        "Bring employees into Horilla from a CSV or Excel file"
                    ),
                },
                {
                    "text": _("Update Existing Employees"),
                    "description": _("Change many employees at once from a sheet"),
                },
            ],
        },
        {
            "label": _("Import History"),
            "url": reverse_lazy("master-import-history"),
            "accessibility": master_import_accessibility,
            "search_entries": [
                {
                    "text": _("Import History"),
                    "description": _(
                        "Every file brought in through Master Data Import"
                    ),
                },
            ],
        },
    ]
