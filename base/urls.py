from django.contrib.auth.models import Group
from django.urls import path, re_path
from django.utils.translation import gettext_lazy as _

from base import announcement
from base import dashboard as dashboard_module
from base import ess_dashboard, request_and_approve, views
from base.cbv import (
    announcement_cbv,
    company,
    company_leaves,
    department,
    employee_shift,
    employee_shift_shedule,
    employee_type,
    holidays,
    job_position,
    job_role,
    mail_log_tab,
    mail_server,
    mail_template,
    multiple_approval_condition,
    penalty,
    roster,
    rotating_shift,
    rotating_shift_assign,
    rotating_work_type,
    settings_rotatingwork,
    settings_work_type,
    shift_request,
    work_shift_tab,
    work_type_request,
)
from base.cbv.dashboard import dashboard
from base.forms import (
    HolidayForm,
    MailTemplateForm,
    RotatingShiftAssignForm,
    RotatingShiftForm,
    RotatingWorkTypeAssignForm,
    RotatingWorkTypeForm,
    ShiftRequestForm,
    WorkTypeRequestForm,
)
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeShiftSchedule,
    EmployeeType,
    Holidays,
    HorillaMailTemplate,
    JobPosition,
    JobRole,
    RotatingShift,
    RotatingShiftAssign,
    RotatingWorkType,
    RotatingWorkTypeAssign,
    ShiftRequest,
    Tags,
    WorkType,
    WorkTypeRequest,
)
from horilla_audit.cbv import audit
from horilla_audit.models import AuditTag

urlpatterns = [
    path("", views.home, name="home-page"),
    path("dashboard/", dashboard_module.main_dashboard_view, name="dashboard"),
    path(
        "dashboard/api/kpi/",
        dashboard_module.dashboard_kpi_data,
        name="dashboard-kpi-data",
    ),
    path(
        "dashboard/api/attendance-trend/",
        dashboard_module.dashboard_attendance_trend,
        name="dashboard-attendance-trend",
    ),
    path(
        "dashboard/api/leave-breakdown/",
        dashboard_module.dashboard_leave_breakdown,
        name="dashboard-leave-breakdown",
    ),
    path(
        "dashboard/api/departments/",
        dashboard_module.dashboard_department_headcount,
        name="dashboard-department-headcount",
    ),
    path(
        "dashboard/api/gender/",
        dashboard_module.dashboard_gender_split,
        name="dashboard-gender-split",
    ),
    path(
        "dashboard/api/announcements/",
        dashboard_module.dashboard_announcements,
        name="dashboard-announcements",
    ),
    path(
        "dashboard/api/announcements/<int:pk>/",
        dashboard_module.dashboard_announcement_detail,
        name="dashboard-announcement-detail",
    ),
    path(
        "dashboard/api/todays-leave/",
        dashboard_module.dashboard_todays_leave,
        name="dashboard-todays-leave",
    ),
    path(
        "dashboard/api/leave-coverage/",
        dashboard_module.dashboard_leave_coverage,
        name="dashboard-leave-coverage",
    ),
    path(
        "dashboard/api/upcoming-holidays/",
        dashboard_module.dashboard_upcoming_holidays,
        name="dashboard-upcoming-holidays",
    ),
    path(
        "dashboard/api/birthdays-anniversaries/",
        dashboard_module.dashboard_birthdays_anniversaries,
        name="dashboard-birthdays-anniversaries",
    ),
    path(
        "dashboard/api/recruitment-pipeline/",
        dashboard_module.dashboard_recruitment_pipeline,
        name="dashboard-recruitment-pipeline",
    ),
    path(
        "dashboard/api/payroll-summary/",
        dashboard_module.dashboard_payroll_summary,
        name="dashboard-payroll-summary",
    ),
    path(
        "dashboard/api/pending-approvals/",
        dashboard_module.dashboard_pending_approvals,
        name="dashboard-pending-approvals",
    ),
    path(
        "dashboard/api/turnover/",
        dashboard_module.dashboard_turnover,
        name="dashboard-turnover",
    ),
    path(
        "dashboard/api/employee-status/",
        dashboard_module.dashboard_employee_status,
        name="dashboard-employee-status",
    ),
    path(
        "dashboard/api/attendance-overview/",
        dashboard_module.dashboard_attendance_overview,
        name="dashboard-attendance-overview",
    ),
    path(
        "dashboard/api/department-overtime/",
        dashboard_module.dashboard_department_overtime,
        name="dashboard-department-overtime",
    ),
    path(
        "dashboard/api/leave-trends/",
        dashboard_module.dashboard_leave_trends,
        name="dashboard-leave-trends",
    ),
    path(
        "dashboard/api/leave-by-department/",
        dashboard_module.dashboard_leave_by_department,
        name="dashboard-leave-by-department",
    ),
    path(
        "dashboard/api/department-leave-days/",
        dashboard_module.dashboard_department_leave_days,
        name="dashboard-department-leave-days",
    ),
    path(
        "dashboard/api/hiring-timeline/",
        dashboard_module.dashboard_hiring_timeline,
        name="dashboard-hiring-timeline",
    ),
    path(
        "dashboard/api/recruitment-by-stage/",
        dashboard_module.dashboard_recruitment_by_stage,
        name="dashboard-recruitment-by-stage",
    ),
    path(
        "dashboard/save-prefs/",
        dashboard_module.save_dashboard_prefs,
        name="dashboard-save-prefs",
    ),
    path(
        "dashboard/load-prefs/",
        dashboard_module.load_dashboard_prefs,
        name="dashboard-load-prefs",
    ),
    path(
        "dashboard/dismiss-setup-checklist/",
        dashboard_module.dismiss_setup_checklist,
        name="dashboard-dismiss-setup-checklist",
    ),
    # ── ESS Dashboard ──────────────────────────────────────────────────────────
    path("ess/", ess_dashboard.ess_dashboard, name="ess-dashboard"),
    path("ess/api/kpi/", ess_dashboard.ess_kpi_data, name="ess-kpi-data"),
    path(
        "ess/api/leave-balance/",
        ess_dashboard.ess_leave_balance,
        name="ess-leave-balance",
    ),
    path(
        "ess/api/leave-requests/",
        ess_dashboard.ess_leave_requests,
        name="ess-leave-requests",
    ),
    path(
        "ess/api/attendance-calendar/",
        ess_dashboard.ess_attendance_calendar,
        name="ess-attendance-calendar",
    ),
    path(
        "ess/api/work-hours-month/",
        ess_dashboard.ess_work_hours_month,
        name="ess-work-hours-month",
    ),
    path("ess/api/payslips/", ess_dashboard.ess_payslips, name="ess-payslips"),
    path("ess/api/objectives/", ess_dashboard.ess_objectives, name="ess-objectives"),
    path(
        "ess/api/announcements/",
        ess_dashboard.ess_announcements,
        name="ess-announcements",
    ),
    path("ess/api/upcoming/", ess_dashboard.ess_upcoming, name="ess-upcoming"),
    path(
        "employee/work-type-request-view/",
        work_type_request.WorkRequestView.as_view(),
        name="work-type-request-view",
    ),
    path(
        "work-list-view/",
        work_type_request.WorkRequestListView.as_view(),
        name="work-list-view",
    ),
    path(
        "work-nav-view/",
        work_type_request.WorkRequestNavView.as_view(),
        name="work-nav-view",
    ),
    path(
        "work-export-candidate/",
        work_type_request.WorkExportCandidate.as_view(),
        name="work-export-candidate",
    ),
    path(
        "work-detail-view/<int:pk>/",
        work_type_request.WorkTypeDetailView.as_view(),
        name="work-detail-view",
    ),
    path(
        "employee/rotating-work-type-assign/",
        rotating_work_type.RotatingWorkRequestView.as_view(),
        name="rotating-work-type-assign",
    ),
    path(
        "rotating-list-view/",
        rotating_work_type.RotatingWorkListView.as_view(),
        name="rotating-list-view",
    ),
    path(
        "rotating-navbar-view/",
        rotating_work_type.RotatingWorkNavView.as_view(),
        name="rotating-navbar-view",
    ),
    path(
        "work-rotating-detail-view/<int:pk>/",
        rotating_work_type.RotatingWorkDetailView.as_view(),
        name="work-rotating-detail-view",
    ),
    path(
        "rotating-action-export/",
        rotating_work_type.RotatingWorkExport.as_view(),
        name="rotating-action-export",
    ),
    path(
        "employee-worktype-tab-list/<int:pk>/",
        work_shift_tab.WorkTypeIndividualTabList.as_view(),
        name="employee-worktype-tab-list",
    ),
    path(
        "employee-worktype-tab-shell/<int:pk>/",
        work_shift_tab.WorkTypeIndividualTabShell.as_view(),
        name="employee-worktype-tab-shell",
    ),
    path(
        "employee-worktype-tab-nav/<int:pk>/",
        work_shift_tab.WorkTypeIndividualNav.as_view(),
        name="employee-worktype-tab-nav",
    ),
    path(
        "employee-rotating-work-tab-list/<int:pk>/",
        work_shift_tab.RotatingWorkIndividualTab.as_view(),
        name="employee-rotating-work-tab-list",
    ),
    path(
        "employee-rotating-work-tab-shell/<int:pk>/",
        work_shift_tab.RotatingWorkIndividualTabShell.as_view(),
        name="employee-rotating-work-tab-shell",
    ),
    path(
        "employee-rotating-work-tab-nav/<int:pk>/",
        work_shift_tab.RotatingWorkIndividualNav.as_view(),
        name="employee-rotating-work-tab-nav",
    ),
    path(
        "individual-work-rotating-detail-view/<int:pk>/",
        work_shift_tab.DetailViewChild.as_view(),
        name="individual-work-rotating-detail-view",
    ),
    path(
        "individual-email-log-list/<int:pk>/",
        mail_log_tab.MailLogTabList.as_view(),
        name="individual-email-log-list",
    ),
    path(
        "individual-mail-log-detail/<int:pk>/",
        mail_log_tab.MailLogDetailView.as_view(),
        name="individual-mail-log-detail",
    ),
    path(
        "mail-template-create-form/",
        mail_template.MailTemplateFormView.as_view(),
        name="mail-template-create-form",
    ),
    path(
        "mail-template-edit-form/<int:pk>/",
        mail_template.MailTemplateFormView.as_view(),
        name="mail-template-edit-form",
    ),
    path(
        "mail-template-duplicate-form/<int:pk>/",
        mail_template.MailTemplateDuplicateForm.as_view(),
        name="mail-template-duplicate-form",
    ),
    path("initialize-database/", views.initialize_database, name="initialize-database"),
    path("load-demo-database/", views.load_demo_database, name="load-demo-database"),
    path(
        "initialize-database-user/",
        views.initialize_database_user,
        name="initialize-database-user",
    ),
    path(
        "initialize-database-company/",
        views.initialize_database_company,
        name="initialize-database-company",
    ),
    path(
        "initialize-database-department/",
        views.initialize_database_department,
        name="initialize-database-department",
    ),
    path(
        "initialize-department-edit/<int:obj_id>/",
        views.initialize_department_edit,
        name="initialize-department-edit",
    ),
    path(
        "initialize-department-delete/<int:obj_id>/",
        views.initialize_department_delete,
        name="initialize-department-delete",
    ),
    path(
        "initialize-database-job-position/",
        views.initialize_database_job_position,
        name="initialize-database-job-position",
    ),
    path(
        "initialize-job-position-edit/<int:obj_id>/",
        views.initialize_job_position_edit,
        name="initialize-job-position-edit",
    ),
    path(
        "initialize-job-position-delete/<int:obj_id>/",
        views.initialize_job_position_delete,
        name="initialize-job-position-delete",
    ),
    path("404/", views.custom404, name="404"),
    path("login/", views.login_user, name="login"),
    path(
        "forgot-password/",
        views.HorillaPasswordResetView.as_view(),
        name="forgot-password",
    ),
    path(
        "employee-reset-password/",
        views.EmployeePasswordResetView.as_view(),
        name="employee-reset-password",
    ),
    path("reset-send-success/", views.reset_send_success, name="reset-send-success"),
    path("change-password/", views.change_password, name="change-password"),
    path("change-username/", views.change_username, name="change-username"),
    path("two-factor/", views.two_factor_auth, name="two-factor"),
    path("send-otp/", views.send_otp, name="send-otp"),
    path("logout/", views.logout_user, name="logout"),
    path("toggle-theme/", views.toggle_theme, name="toggle_theme"),
    # path("settings/", views.common_settings, name="settings"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path(
        "settings/user-group-create/", views.user_group_table, name="user-group-create"
    ),
    path("settings/user-group-view/", views.user_group, name="user-group-view"),
    path(
        "settings/user-group-search/", views.user_group_search, name="user-group-search"
    ),
    path(
        "settings/user-group-detail/<int:obj_id>/",
        views.user_group_detail,
        name="user-group-detail",
    ),
    path(
        "user-group-delete/<int:obj_id>/",
        views.object_delete,
        name="user-group-delete",
        kwargs={"model": Group, "redirect": "user-group-view", "superuser_only": True},
    ),
    path(
        "group-permission-remove/<int:pid>/<int:gid>/",
        views.user_group_permission_remove,
        name="group-permission-remove",
    ),
    path(
        "user-group-assign-view/",
        views.group_assign_view,
        name="user-group-assign-view",
    ),
    path("settings/user-group-assign/", views.group_assign, name="user-group-assign"),
    path(
        "group-remove-user/<int:uid>/<int:gid>/",
        views.group_remove_user,
        name="group-remove-user",
    ),
    path(
        "settings/employee-permission-assign/",
        views.employee_permission_assign,
        name="employee-permission-assign",
    ),
    path(
        "employee-permission-search/",
        views.employee_permission_search,
        name="permission-search",
    ),
    path(
        "update-user-permission/",
        views.update_permission,
        name="update-user-permission",
    ),
    path(
        "update-group-permission/",
        views.update_group_permission,
        name="update-group-permission",
    ),
    path(
        "permission-table/",
        views.permission_table,
        name="permission-table",
    ),
    path(
        "employee-permission-codenames/<int:emp_id>/",
        views.employee_permission_codenames,
        name="employee-permission-codenames",
    ),
    path("settings/mail-server-conf/", views.mail_server_conf, name="mail-server-conf"),
    path(
        "mail-server-list/",
        mail_server.MailServerListView.as_view(),
        name="mail-server-list",
    ),
    path(
        "mail-server-nav/",
        mail_server.MailServerNav.as_view(),
        name="mail-server-nav",
    ),
    path(
        "create-mail-server/",
        mail_server.MailServerFormView.as_view(),
        name="create-mail-server",
    ),
    path(
        "update-mail-server/<int:pk>/",
        mail_server.MailServerFormView.as_view(),
        name="update-mail-server",
    ),
    path(
        "settings/mail-server-create-update/",
        views.mail_server_create_or_update,
        name="mail-server-create-update",
    ),
    path(
        "settings/mail-server-test-email/",
        views.mail_server_test_email,
        name="mail-server-test-email",
    ),
    path("mail-server-delete/", views.mail_server_delete, name="mail-server-delete"),
    path(
        "replace-primary-mail/", views.replace_primary_mail, name="replace-primary-mail"
    ),
    path(
        "settings/mail-templates-view/",
        views.mail_templates_settings_view,
        name="mail-templates-view",
    ),
    path(
        "configuration/view-mail-templates/",
        views.view_mail_templates,
        name="view-mail-templates",
    ),
    path(
        "view-mail-template/<int:obj_id>/",
        views.view_mail_template,
        name="view-mail-template",
    ),
    path(
        "view-mail-templates-nav/",
        mail_template.MailTemplateNavView.as_view(),
        name="view-mail-templates-nav",
    ),
    path(
        "create-mail-template/",
        views.create_mail_templates,
        name="create-mail-template",
    ),
    path(
        "duplicate-mail-template/<int:obj_id>/",
        views.object_duplicate,
        name="duplicate-mail-template",
        kwargs={
            "model": HorillaMailTemplate,
            "form": MailTemplateForm,
            "template": "mail/htmx/form.html",
        },
    ),
    path(
        "delete-mail-template/",
        views.delete_mail_templates,
        name="delete-mail-template",
    ),
    path("settings/company-create/", views.company_create, name="company-create"),
    path("settings/company-view/", views.company_view, name="company-view"),
    path("company-list/", company.CompanyListView.as_view(), name="company-list"),
    path("company-navbar/", company.CompanyNavView.as_view(), name="company-navbar"),
    path(
        "company-create-form/",
        company.CompanyCreateForm.as_view(),
        name="company-create-form",
    ),
    path(
        "company-update-form/<int:pk>/",
        company.CompanyCreateForm.as_view(),
        name="company-update-form",
    ),
    path(
        "settings/company-update/<int:id>/",
        views.company_update,
        name="company-update",
        kwargs={"model": Company},
    ),
    path(
        "settings/company-delete/<int:obj_id>/",
        views.object_delete,
        name="company-delete",
        kwargs={
            "model": Company,
            "HttpResponse": "<script>$('#reloadMessagesButton').click()</script>",
        },
        # kwargs={"model": Company, "redirect": "/settings/company-view"},
    ),
    path("settings/department-view/", views.department_view, name="department-view"),
    path(
        "department-list/",
        department.DepartmentListView.as_view(),
        name="department-list",
    ),
    path(
        "department-nav/", department.DepartmentNavView.as_view(), name="department-nav"
    ),
    path(
        "department-detail-view/<int:pk>/",
        department.DepartmentDetailView.as_view(),
        name="department-detail-view",
    ),
    path(
        "settings/department-creation/",
        views.department_create,
        name="department-creation",
    ),
    path(
        "settings-department-creation/",
        department.DepartmentCreateForm.as_view(),
        name="settings-department-creation",
    ),
    path(
        "settings/department-update/<int:id>/",
        views.department_update,
        name="department-update",
        kwargs={"model": Department},
    ),
    path(
        "settings-department-update/<int:pk>/",
        department.DepartmentCreateForm.as_view(),
        name="settings-department-update",
    ),
    path(
        "department-delete/<int:obj_id>/",
        views.object_delete,
        name="department-delete",
        kwargs={
            "model": Department,
            "HttpResponse": True,
        },
    ),
    path(
        "job-position-create-form/",
        job_position.JobPositionCreateForm.as_view(),
        name="job-position-create-form",
    ),
    path(
        "job-position-update-form/<int:pk>/",
        job_position.JobPositionCreateForm.as_view(),
        name="job-position-update-form",
    ),
    path(
        "job-position-list/",
        job_position.JobPositionListView.as_view(),
        name="job-position-list",
    ),
    path(
        "job-position-navbar/",
        job_position.JobPositionNavView.as_view(),
        name="job-position-navbar",
    ),
    path(
        "job-position-detail-view/<int:pk>/",
        job_position.JobPositionDetailView.as_view(),
        name="job-position-detail-view",
    ),
    path(
        "settings/job-position-creation/",
        views.job_position_creation,
        name="job-position-creation",
    ),
    path(
        "settings/job-position-view/",
        views.job_position,
        name="job-position-view",
    ),
    path(
        "settings/job-position-update/<int:id>/",
        views.job_position_update,
        name="job-position-update",
        kwargs={"model": JobPosition},
    ),
    path(
        "job-position-delete/<int:obj_id>/",
        views.object_delete,
        name="job-position-delete",
        kwargs={
            "model": JobPosition,
            "HttpResponse": True,
        },
    ),
    path("settings/job-role-create/", views.job_role_create, name="job-role-create"),
    path("job-role-list/", job_role.JobRoleListView.as_view(), name="job-role-list"),
    path("job-role-nav/", job_role.JobRoleNav.as_view(), name="job-role-nav"),
    path(
        "job-role-detail-view/<int:pk>/",
        job_role.JobRoleDetailView.as_view(),
        name="job-role-detail-view",
    ),
    path(
        "create-job-role/", job_role.JobRoleFormView.as_view(), name="create-job-role"
    ),
    path(
        "update-job-role/<int:pk>/",
        job_role.JobRoleFormView.as_view(),
        name="update-job-role",
    ),
    path("settings/job-role-view/", views.job_role_view, name="job-role-view"),
    path(
        "settings/job-role-update/<int:id>/",
        views.job_role_update,
        name="job-role-update",
        kwargs={"model": JobRole},
    ),
    path(
        "job-role-delete/<int:obj_id>/",
        views.object_delete,
        name="job-role-delete",
        kwargs={
            "model": JobRole,
            "HttpResponse": True,
        },
    ),
    path("settings/work-type-view/", views.work_type_view, name="work-type-view"),
    path(
        "worktype-list/",
        settings_work_type.WorkTypeList.as_view(),
        name="worktype-list",
    ),
    path(
        "worktype-nav/", settings_work_type.WorkTypeNav.as_view(), name="worktype-nav"
    ),
    path(
        "worktype-detail-view/<int:pk>/",
        settings_work_type.WorkTypeDetailView.as_view(),
        name="worktype-detail-view",
    ),
    path(
        "work-type-create-form/",
        work_type_request.WorkTypesCreateForm.as_view(),
        name="work-type-create-form",
    ),
    path(
        "work-type-update-form/<int:pk>/",
        work_type_request.WorkTypesCreateForm.as_view(),
        name="work-type-update-form",
    ),
    # path("candidate-work-type-create-form/",work_type_request.DynamicWorkTypeCreateForm.as_view(),name="candidate-work-type-create-form"),
    path("settings/work-type-create/", views.work_type_create, name="work-type-create"),
    path(
        "settings/work-type-update/<int:id>/",
        views.work_type_update,
        name="work-type-update",
        kwargs={"model": WorkType},
    ),
    path(
        "work-type-delete/<int:obj_id>/",
        views.object_delete,
        name="work-type-delete",
        kwargs={
            "model": WorkType,
            "HttpResponse": True,
        },
    ),
    path(
        "add-remove-work-type-fields/",
        views.add_remove_dynamic_fields,
        name="add-remove-work-type-fields",
        kwargs={
            "model": WorkType,
            "form_class": RotatingWorkTypeForm,
            "template": "base/rotating_work_type/htmx/add_more_work_type_fields.html",
            "empty_label": _("---Choose Work Type---"),
            "field_name_pre": "work_type",
        },
    ),
    path(
        "rotating-work-type-create-form/",
        settings_rotatingwork.RotatingWorkTypesCreateForm.as_view(),
        name="rotating-work-type-create-form",
    ),
    path(
        "rotating-work-type-update-form/<int:pk>/",
        settings_rotatingwork.RotatingWorkTypesCreateForm.as_view(),
        name="rotating-work-type-update-form",
    ),
    path(
        "settings/rotating-work-type-create/",
        views.rotating_work_type_create,
        name="rotating-work-type-create",
    ),
    path(
        "settings/rotating-work-type-view/",
        views.rotating_work_type_view,
        name="rotating-work-type-view",
    ),
    path(
        "rotating-list/",
        settings_rotatingwork.RotatingWorkTypeList.as_view(),
        name="rotating-list",
    ),
    path(
        "rotating-nav/",
        settings_rotatingwork.RotatingWorkTypeNav.as_view(),
        name="rotating-nav",
    ),
    path(
        "settings/rotating-work-type-update/<int:id>/",
        views.rotating_work_type_update,
        name="rotating-work-type-update",
        kwargs={"model": RotatingWorkType},
    ),
    path(
        "rotating-work-type-delete/<int:obj_id>/",
        views.object_delete,
        name="rotating-work-type-delete",
        kwargs={
            "model": RotatingWorkType,
            "HttpResponse": True,
        },
    ),
    # path(
    #     "employee/rotating-work-type-assign/",
    #     views.rotating_work_type_assign,
    #     name="rotating-work-type-assign",
    # ),
    # path(
    #     "rotating-work-type-assign-add",
    #     views.rotating_work_type_assign_add,
    #     name="rotating-work-type-assign-add",
    # ),
    path(
        "rotating-work-type-assign-add/",
        rotating_work_type.RotatingWorkTypeFormView.as_view(),
        name="rotating-work-type-assign-add",
    ),
    path(
        "rotating-work-type-assign-view/",
        views.rotating_work_type_assign_view,
        name="rotating-work-type-assign-view",
    ),
    path(
        "rotating-work-type-assign-export/",
        views.rotating_work_type_assign_export,
        name="rotating-work-type-assign-export",
    ),
    path(
        "settings/rotating-work-type-assign-update/<int:pk>/",
        rotating_work_type.RotatingWorkTypeFormView.as_view(),
        name="rotating-work-type-assign-update",
    ),
    # path(
    #     "settings/rotating-work-type-assign-update/<int:id>/",
    #     views.rotating_work_type_assign_update,
    #     name="rotating-work-type-assign-update",
    # ),
    # path(
    #     "rotating-work-type-assign-duplicate/<int:obj_id>/",
    #     views.object_duplicate,
    #     name="rotating-work-type-assign-duplicate",
    #     kwargs={
    #         "model": RotatingWorkTypeAssign,
    #         "form": RotatingWorkTypeAssignForm,
    #         "template": "base/rotating_work_type/htmx/rotating_work_type_assign_form.html",
    #     },
    # ),
    path(
        "rotating-work-type-assign-duplicate/<int:pk>/",
        rotating_work_type.RotatingWorkTypeDuplicateForm.as_view(),
        name="rotating-work-type-assign-duplicate",
    ),
    path(
        "rotating-work-type-assign-archive/<int:obj_id>/",
        views.rotating_work_type_assign_archive,
        name="rotating-work-type-assign-archive",
    ),
    path(
        "rotating-work-type-assign-bulk-archive/",
        views.rotating_work_type_assign_bulk_archive,
        name="rotating-shift-work-type-bulk-archive",
    ),
    path(
        "rotating-work-type-assign-bulk-delete/",
        views.rotating_work_type_assign_bulk_delete,
        name="rotating-shift-work-type-bulk-delete",
    ),
    path(
        "rotating-work-type-assign-delete/<int:obj_id>/",
        views.rotating_work_type_assign_delete,
        name="rotating-work-type-assign-delete",
    ),
    path(
        "settings/employee-type-view/",
        views.employee_type_view,
        name="employee-type-view",
    ),
    path(
        "settings/employee-type-list/",
        employee_type.EmployeeTypeListView.as_view(),
        name="employee-type-list",
    ),
    path(
        "settings/employee-type-nav/",
        employee_type.EmployeeTypeNav.as_view(),
        name="employee-type-nav",
    ),
    path(
        "settings/employee-type-create/",
        views.employee_type_create,
        name="employee-type-create",
    ),
    path(
        "settings/employee-type-create-view/",
        employee_type.EmployeeTypeFormView.as_view(),
        name="employee-type-create-view",
    ),
    path(
        "settings/employee-type-update-view/<int:pk>/",
        employee_type.EmployeeTypeFormView.as_view(),
        name="employee-type-update-view",
    ),
    path(
        "settings/employee-type-update/<int:id>/",
        views.employee_type_update,
        name="employee-type-update",
        kwargs={"model": EmployeeType},
    ),
    path(
        "employee-type-delete/<int:obj_id>/",
        views.object_delete,
        name="employee-type-delete",
        kwargs={
            "model": EmployeeType,
            "HttpResponse": True,
        },
    ),
    path(
        "settings/employee-shift-view/",
        views.employee_shift_view,
        name="employee-shift-view",
    ),
    path(
        "settings/employee-shift-list/",
        employee_shift.EmployeeShiftListView.as_view(),
        name="employee-shift-list",
    ),
    path(
        "settings/employee-shift-nav/",
        employee_shift.EmployeeShiftNav.as_view(),
        name="employee-shift-nav",
    ),
    path(
        "employee-shift-detail-view/<int:pk>/",
        employee_shift.EmployeeShiftDetailView.as_view(),
        name="employee-shift-detail-view",
    ),
    path(
        "settings/employee-shift-create/",
        views.employee_shift_create,
        name="employee-shift-create",
    ),
    path(
        "settings/employee-shift-create-view/",
        shift_request.ShiftTypeCreateFormView.as_view(),
        name="employee-shift-create-view",
    ),
    path(
        "settings/employee-shift-update/<int:id>/",
        views.employee_shift_update,
        name="employee-shift-update",
        kwargs={"model": EmployeeShift},
    ),
    path(
        "employee-shift-update-view/<int:pk>/",
        shift_request.ShiftTypeCreateFormView.as_view(),
        name="employee-shift-update-view",
    ),
    path(
        "employee-shift-delete/<int:obj_id>/",
        views.object_delete,
        name="employee-shift-delete",
        kwargs={
            "model": EmployeeShift,
            "HttpResponse": True,
        },
    ),
    path(
        "employee-shift-shedule-list/",
        employee_shift_shedule.EmployeeShiftSheduleList.as_view(),
        name="employee-shift-shedule-list",
    ),
    path(
        "employee-shift-shedule-detail-view/<int:pk>/",
        employee_shift_shedule.EmployeeShiftSheduleDetailView.as_view(),
        name="employee-shift-shedule-detail-view",
    ),
    path(
        "employee-shift-shedule-navbar/",
        employee_shift_shedule.EmployeeShiftSheduleNav.as_view(),
        name="employee-shift-shedule-navbar",
    ),
    path(
        "settings-employee-shift-shedule-create/",
        employee_shift_shedule.EmployeeShiftSheduleCreateForm.as_view(),
        name="settings-employee-shift-shedule-create",
    ),
    path(
        "settings-employee-shift-shedule-update/<int:pk>/",
        employee_shift_shedule.EmployeeShiftSheduleCreateForm.as_view(),
        name="settings-employee-shift-shedule-update",
    ),
    path(
        "settings/employee-shift-schedule-view/",
        views.employee_shift_schedule_view,
        name="employee-shift-schedule-view",
    ),
    path(
        "settings/employee-shift-schedule-create/",
        views.employee_shift_schedule_create,
        name="employee-shift-schedule-create",
    ),
    path(
        "settings/employee-shift-schedule-update/<int:id>/",
        views.employee_shift_schedule_update,
        name="employee-shift-schedule-update",
        kwargs={"model": EmployeeShiftSchedule},
    ),
    path(
        "employee-shift-schedule-delete/<int:obj_id>/",
        views.object_delete,
        name="employee-shift-schedule-delete",
        kwargs={
            "model": EmployeeShiftSchedule,
            "HttpResponse": "<script>$('#reloadMessagesButton').click();$('.oh-modal__close--custom').click();</script>",
        },
    ),
    # path(
    #     "settings/rotating-shift-create/",
    #     views.rotating_shift_create,
    #     name="rotating-shift-create",
    # ),
    path(
        "rotating-shift-create/",
        rotating_shift.RotatingShiftTypeCreateFormView.as_view(),
        name="rotating-shift-create",
    ),
    path(
        "add-remove-shift-fields/",
        views.add_remove_dynamic_fields,
        name="add-remove-shift-fields",
        kwargs={
            "model": EmployeeShift,
            "form_class": RotatingShiftForm,
            "template": "base/rotating_shift/htmx/add_more_shift_fields.html",
            "empty_label": _("---Choose Shift---"),
            "field_name_pre": "shift",
        },
    ),
    path(
        "settings/rotating-shift-view/",
        views.rotating_shift_view,
        name="rotating-shift-view",
    ),
    path(
        "settings/rotating-shift-list/",
        rotating_shift.RotatingShiftTypeListView.as_view(),
        name="rotating-shift-list",
    ),
    path(
        "settings/rotating-shift-nav/",
        rotating_shift.RotatingShiftTypeNav.as_view(),
        name="rotating-shift-nav",
    ),
    # path(
    #     "settings/rotating-shift-update/<int:id>/",
    #     views.rotating_shift_update,
    #     name="rotating-shift-update",
    #     kwargs={"model": RotatingShift},
    # ),
    path(
        "settings/rotating-shift-update/<int:pk>/",
        rotating_shift.RotatingShiftTypeCreateFormView.as_view(),
        name="rotating-shift-update",
    ),
    path(
        "rotating-shift-delete/<int:obj_id>/",
        views.object_delete,
        name="rotating-shift-delete",
        kwargs={
            "model": RotatingShift,
            "HttpResponse": "<script>$('#reloadMessagesButton').click()</script>",
        },
    ),
    # path(
    #     "employee/rotating-shift-assign/",
    #     views.rotating_shift_assign,
    #     name="rotating-shift-assign",
    # ),
    path(
        "rotating-shift-assign-add/",
        rotating_shift_assign.RotatingShiftFormView.as_view(),
        name="rotating-shift-assign-add",
    ),
    path(
        "rotating-shift-assign-view/",
        views.rotating_shift_assign_view,
        name="rotating-shift-assign-view",
    ),
    path(
        "rotating-shift-assign-info-export/",
        views.rotating_shift_assign_export,
        name="rotating-shift-assign-info-export",
    ),
    # path(
    #     "settings/rotating-shift-assign-update/<int:id>/",
    #     views.rotating_shift_assign_update,
    #     name="rotating-shift-assign-update",
    # ),
    path(
        "rotating-shift-assign-info-import/",
        views.rotating_shift_assign_import,
        name="rotating-shift-assign-info-import",
    ),
    path(
        "settings/rotating-shift-assign-update/<int:pk>/",
        rotating_shift_assign.RotatingShiftFormView.as_view(),
        name="rotating-shift-assign-update",
    ),
    # path(
    #     "rotating-shift-assign-duplicate/<int:obj_id>/",
    #     views.object_duplicate,
    #     name="rotating-shift-assign-duplicate",
    #     kwargs={
    #         "model": RotatingShiftAssign,
    #         "form": RotatingShiftAssignForm,
    #         "template": "base/rotating_shift/htmx/rotating_shift_assign_form.html",
    #     },
    # ),
    path(
        "rotating-shift-assign-duplicate/<int:pk>/",
        rotating_shift_assign.RotatingShiftAssignDuplicate.as_view(),
        name="rotating-shift-assign-duplicate",
    ),
    path(
        "rotating-shift-assign-archive/<int:obj_id>/",
        views.rotating_shift_assign_archive,
        name="rotating-shift-assign-archive",
    ),
    path(
        "rotating-shift-assign-bulk-archive/",
        views.rotating_shift_assign_bulk_archive,
        name="rotating-shift-assign-bulk-archive",
    ),
    path(
        "rotating-shift-assign-bulk-delete/",
        views.rotating_shift_assign_bulk_delete,
        name="rotating-shift-assign-bulk-delete",
    ),
    path(
        "rotating-shift-assign-delete/<int:obj_id>/",
        views.rotating_shift_assign_delete,
        name="rotating-shift-assign-delete",
    ),
    # path("work-type-request", views.work_type_request, name="work-type-request"),
    path(
        "work-type-request/",
        work_type_request.WorkTypeFormView.as_view(),
        name="work-type-request",
    ),
    # path(
    #     "work-type-request-duplicate/<int:obj_id>/",
    #     views.object_duplicate,
    #     name="work-type-request-duplicate",
    #     kwargs={
    #         "model": WorkTypeRequest,
    #         "form": WorkTypeRequestForm,
    #         "template": "work_type_request/request_form.html",
    #     },
    # ),
    path(
        "work-type-request-duplicate/<int:pk>/",
        work_type_request.WorkTypeDuplicateForm.as_view(),
        name="work-type-request-duplicate",
    ),
    # path(
    #     "employee/",
    #     views.work_type_request_view,
    #     name="work-type-request-view",
    # ),
    path(
        "work-type-request-info-export/",
        views.work_type_request_export,
        name="work-type-request-info-export",
    ),
    path(
        "work-type-request-search/",
        views.work_type_request_search,
        name="work-type-request-search",
    ),
    path(
        "work-type-request-cancel/<int:id>/",
        views.work_type_request_cancel,
        name="work-type-request-cancel",
    ),
    path(
        "work-type-request-bulk-cancel/",
        views.work_type_request_bulk_cancel,
        name="work-type-request-bulk-cancel",
    ),
    path(
        "work-type-request-approve/<int:id>/",
        views.work_type_request_approve,
        name="work-type-request-approve",
    ),
    path(
        "work-type-request-bulk-approve/",
        views.work_type_request_bulk_approve,
        name="work-type-request-bulk-approve",
    ),
    # path(
    #     "work-type-request-update/<int:work_type_request_id>/",
    #     views.work_type_request_update,
    #     name="work-type-request-update",
    # ),
    path(
        "work-type-request-update/<int:pk>/",
        work_type_request.WorkTypeFormView.as_view(),
        name="work-type-request-update",
    ),
    path(
        "work-type-request-delete/<int:obj_id>/",
        views.work_type_request_delete,
        name="work-type-request-delete",
    ),
    path(
        "work-type-request-single-view/<int:obj_id>/",
        views.work_type_request_single_view,
        name="work-type-request-single-view",
    ),
    path(
        "work-type-request-bulk-delete/",
        views.work_type_request_bulk_delete,
        name="work-type-request-bulk-delete",
    ),
    # path("shift-request", views.shift_request, name="shift-request"),
    path(
        "shift-request/",
        shift_request.ShiftRequestFormView.as_view(),
        name="shift-request",
    ),
    # path(
    #     "shift-request-duplicate/<int:obj_id>/",
    #     views.object_duplicate,
    #     name="shift-request-duplicate",
    #     kwargs={
    #         "model": ShiftRequest,
    #         "form": ShiftRequestForm,
    #         "template": "shift_request/htmx/shift_request_create_form.html",
    #     },
    # ),
    path(
        "shift-request-duplicate/<int:pk>/",
        shift_request.ShiftRequestFormDuplicate.as_view(),
        name="shift-request-duplicate",
    ),
    # path(
    #     "shift-request-reallocate",
    #     views.shift_request_allocation,
    #     name="shift-request-reallocate",
    # ),
    path(
        "shift-request-reallocate/",
        shift_request.ShiftAllocationFormView.as_view(),
        name="shift-request-reallocate",
    ),
    path(
        "update-employee-allocation/",
        views.update_employee_allocation,
        name="update-employee-allocation",
    ),
    # path(
    #     "employee/shift-request-view/",
    #     views.shift_request_view,
    #     name="shift-request-view",
    # ),
    path(
        "shift-request-info-export/",
        views.shift_request_export,
        name="shift-request-info-export",
    ),
    path(
        "shift-request-search/", views.shift_request_search, name="shift-request-search"
    ),
    path(
        "shift-request-details/<int:id>/",
        views.shift_request_details,
        name="shift-request-details",
    ),
    path(
        "shift-allocation-request-details/<int:id>/",
        views.shift_allocation_request_details,
        name="shift-allocation-request-details",
    ),
    # path(
    #     "shift-request-update/<int:shift_request_id>/",
    #     views.shift_request_update,
    #     name="shift-request-update",
    # ),
    path(
        "shift-request-update/<int:pk>/",
        shift_request.ShiftRequestFormView.as_view(),
        name="shift-request-update",
    ),
    # path(
    #     "shift-allocation-request-update/<int:shift_request_id>/",
    #     views.shift_allocation_request_update,
    #     name="shift-allocation-request-update",
    # ),
    path(
        "shift-allocation-request-update/<int:pk>/",
        shift_request.ShiftAllocationFormView.as_view(),
        name="shift-allocation-request-update",
    ),
    path(
        "shift-request-cancel/<int:id>/",
        views.shift_request_cancel,
        name="shift-request-cancel",
    ),
    path(
        "shift-allocation-request-cancel/<int:id>/",
        views.shift_allocation_request_cancel,
        name="shift-allocation-request-cancel",
    ),
    path(
        "shift-request-bulk-cancel/",
        views.shift_request_bulk_cancel,
        name="shift-request-bulk-cancel",
    ),
    path(
        "shift-request-approve/<int:id>/",
        views.shift_request_approve,
        name="shift-request-approve",
    ),
    path(
        "shift-allocation-request-approve/<int:id>/",
        views.shift_allocation_request_approve,
        name="shift-allocation-request-approve",
    ),
    path(
        "shift-request-bulk-approve/",
        views.shift_request_bulk_approve,
        name="shift-request-bulk-approve",
    ),
    path(
        "shift-request-delete/<int:id>/",
        views.shift_request_delete,
        name="shift-request-delete",
    ),
    path(
        "shift-request-bulk-delete/",
        views.shift_request_bulk_delete,
        name="shift-request-bulk-delete",
    ),
    path("notifications/", views.notifications, name="notifications"),
    path("clear-notifications/", views.clear_notification, name="clear-notifications"),
    path(
        "delete-all-notifications/",
        views.delete_all_notifications,
        name="delete-all-notifications",
    ),
    path("read-notifications/", views.read_notifications, name="read-notifications"),
    path(
        "mark-as-read-notification/<int:notification_id>/",
        views.mark_as_read_notification,
        name="mark-as-read-notification",
    ),
    path(
        "mark-as-read-notification-json/",
        views.mark_as_read_notification_json,
        name="mark-as-read-notification-json",
    ),
    path("all-notifications/", views.all_notifications, name="all-notifications"),
    path(
        "delete-notifications/<id>/",
        views.delete_notification,
        name="delete-notifications",
    ),
    path(
        "notification-sound",
        views.notification_sound,
        name="notification-sound",
    ),
    path("settings/general-settings/", views.general_settings, name="general-settings"),
    path(
        "settings/system-preferences-view/",
        views.system_preferences_settings_view,
        name="system-preferences-view",
    ),
    path(
        "settings/update-announcement-expire-days/",
        views.update_announcement_expire_days,
        name="update-announcement-expire-days",
    ),
    path(
        "settings/encashment-settings-view/",
        views.encashment_general_settings_view,
        name="encashment-settings-view",
    ),
    path("settings/date-settings/", views.date_settings, name="date-settings"),
    path("settings/save-date/", views.save_date_format, name="save_date_format"),
    path("settings/get-date-format/", views.get_date_format, name="get-date-format"),
    path("settings/save-time/", views.save_time_format, name="save_time_format"),
    path("settings/get-time-format/", views.get_time_format, name="get-time-format"),
    path(
        "history-field-settings/",
        views.history_field_settings,
        name="history-field-settings",
    ),
    path(
        "enable-account-block-unblock/",
        views.enable_account_block_unblock,
        name="enable-account-block-unblock",
    ),
    path(
        "enable-profile-edit-feature/",
        views.enable_profile_edit_feature,
        name="enable-profile-edit-feature",
    ),
    path(
        "settings/default-export-access/",
        views.default_export_access_settings_view,
        name="default-export-access-settings",
    ),
    path(
        "enable-default-export-access/",
        views.enable_default_export_access,
        name="enable-default-export-access",
    ),
    path(
        "settings/update-language-settings/",
        views.update_language_settings,
        name="update-language-settings",
    ),
    path(
        "rwork-individual-view/<int:instance_id>/",
        views.rotating_work_individual_view,
        name="rwork-individual-view",
    ),
    path(
        "rshit-individual-view/<int:instance_id>/",
        views.rotating_shift_individual_view,
        name="rshift-individual-view",
    ),
    path("shift-select/", views.shift_select, name="shift-select"),
    path(
        "shift-select-filter/",
        views.shift_select_filter,
        name="shift-select-filter",
    ),
    path("work-type-select/", views.work_type_select, name="work-type-select"),
    path(
        "work-type-filter/",
        views.work_type_select_filter,
        name="work-type-select-filter",
    ),
    path("r-shift-select/", views.rotating_shift_select, name="r-shift-select"),
    path(
        "r-shift-select-filter/",
        views.rotating_shift_select_filter,
        name="r-shift-select-filter",
    ),
    path(
        "r-work-type-select/",
        views.rotating_work_type_select,
        name="r-work-type-select",
    ),
    path(
        "r-work-type-filter/",
        views.rotating_work_type_select_filter,
        name="r-work-type-select-filter",
    ),
    path("settings/tag-view/", views.tag_view, name="tag-view"),
    path(
        "settings/helpdesk-tag-view/", views.helpdesk_tag_view, name="helpdesk-tag-view"
    ),
    path("tag-create/", views.tag_create, name="tag-create"),
    path("tag-update/<int:tag_id>/", views.tag_update, name="tag-update"),
    path(
        "tag-delete/<int:obj_id>/",
        views.object_delete,
        name="tag-delete",
        kwargs={
            "model": Tags,
            "HttpResponse": True,
        },
    ),
    path("audit-tag-list/", audit.AudiTagsList.as_view(), name="audit-tag-list"),
    path(
        "audit-tag-navbar/", audit.AuditTagsNavView.as_view(), name="audit-tag-navbar"
    ),
    path(
        "settings-audit-tag-create/",
        audit.AuditTagCreateForm.as_view(),
        name="settings-audit-tag-create",
    ),
    path(
        "settings-audit-tag-update/<int:pk>/",
        audit.AuditTagCreateForm.as_view(),
        name="settings-audit-tag-update",
    ),
    path("audit-tag-create/", views.audit_tag_create, name="audit-tag-create"),
    path(
        "audit-tag-update/<int:tag_id>/",
        views.audit_tag_update,
        name="audit-tag-update",
    ),
    path(
        "audit-tag-delete/<int:obj_id>/",
        views.object_delete,
        name="audit-tag-delete",
        kwargs={
            "model": AuditTag,
            "HttpResponse": "<script>$('#reloadMessagesButton').click()</script>",
        },
    ),
    # path(
    #     "configuration/multiple-approval-condition",
    #     views.multiple_approval_condition,
    #     name="multiple-approval-condition",
    # ),
    path(
        "configuration/condition-value-fields/",
        views.get_condition_value_fields,
        name="condition-value-fields",
    ),
    path(
        "configuration/add-more-approval-managers/",
        views.add_more_approval_managers,
        name="add-more-approval-managers",
    ),
    path(
        "configuration/remove-approval-manager/",
        views.remove_approval_manager,
        name="remove-approval-manager",
    ),
    # path(
    #     "configuration/hx-multiple-approval-condition",
    #     views.hx_multiple_approval_condition,
    #     name="hx-multiple-approval-condition",
    # ),
    # path(
    #     "multiple-level-approval-create",
    #     views.multiple_level_approval_create,
    #     name="multiple-level-approval-create",
    # ),
    path(
        "multiple-level-approval-create/",
        multiple_approval_condition.MultipleApprovalConditionFormView.as_view(),
        name="multiple-level-approval-create",
    ),
    # path(
    #     "multiple-level-approval-edit/<int:condition_id>",
    #     views.multiple_level_approval_edit,
    #     name="multiple-level-approval-edit",
    # ),
    path(
        "multiple-level-approval-edit/<int:pk>/",
        multiple_approval_condition.EditApprovalConditionFormView.as_view(),
        name="multiple-level-approval-edit",
    ),
    path(
        "multiple-level-approval-delete/<int:condition_id>/",
        views.multiple_level_approval_delete,
        name="multiple-level-approval-delete",
    ),
    path(
        "shift-request-add-comment/<int:shift_id>/",
        views.create_shiftrequest_comment,
        name="shift-request-add-comment",
    ),
    path(
        "view-shift-comment/<int:shift_id>/",
        views.view_shift_comment,
        name="view-shift-comment",
    ),
    path(
        "delete-shift-comment-file/",
        views.delete_shift_comment_file,
        name="delete-shift-comment-file",
    ),
    path(
        "view-work-type-comment/<int:work_type_id>/",
        views.view_work_type_comment,
        name="view-work-type-comment",
    ),
    path(
        "delete-work-type-comment-file/",
        views.delete_work_type_comment_file,
        name="delete-work-type-comment-file",
    ),
    path(
        "shift-request-delete-comment/<int:comment_id>/",
        views.delete_shiftrequest_comment,
        name="shift-request-delete-comment",
    ),
    path(
        "worktype-request-add-comment/<int:worktype_id>/",
        views.create_worktyperequest_comment,
        name="worktype-request-add-comment",
    ),
    path(
        "worktype-request-delete-comment/<int:comment_id>/",
        views.delete_worktyperequest_comment,
        name="worktype-request-delete-comment",
    ),
    # path(
    #     "dashboard-shift-request",
    #     request_and_approve.dashboard_shift_request,
    #     name="dashboard-shift-request",
    # ),
    path(
        "dashboard-shift-request/",
        dashboard.ShiftRequestToApprove.as_view(),
        name="dashboard-shift-request",
    ),
    # path(
    #     "dashboard-work-type-request",
    #     request_and_approve.dashboard_work_type_request,
    #     name="dashboard-work-type-request",
    # ),
    path(
        "dashboard-work-type-request/",
        dashboard.DashboardWorkTypeRequest.as_view(),
        name="dashboard-work-type-request",
    ),
    path(
        "settings/pagination-settings-view/",
        views.pagination_settings_view,
        name="pagination-settings-view",
    ),
    path("settings/action-type/", views.action_type_view, name="action-type"),
    path("action-type-create/", views.action_type_create, name="action-type-create"),
    path(
        "action-type-update/<int:act_id>/",
        views.action_type_update,
        name="action-type-update",
    ),
    path(
        "action-type-delete/<int:act_id>/",
        views.action_type_delete,
        name="action-type-delete",
    ),
    # path(
    #     "pagination-settings-view",
    #     views.pagination_settings_view,
    #     name="pagination-settings-view",
    # ),
    # path("announcement/", announcement.announcement_view, name="announcement"),
    # path(
    #     "create-announcement",
    #     announcement.create_announcement,
    #     name="create-announcement",
    # ),
    path(
        "announcement-list/", announcement.announcement_list, name="announcement-list"
    ),
    path(
        "create-announcement/",
        announcement_cbv.AnnouncementFormView.as_view(),
        name="create-announcement",
    ),
    path(
        "delete-announcement/<int:anoun_id>/",
        announcement.delete_announcement,
        name="delete-announcement",
    ),
    # path(
    #     "update-announcement/<int:anoun_id>",
    #     announcement.update_announcement,
    #     name="update-announcement",
    # ),
    path(
        "dashboard-announcement-list/",
        dashboard.DashboardAnnouncementView.as_view(),
        name="dashboard-announcement-list",
    ),
    path(
        "dashboard-announcement-viewed-by-list/<int:announcement_id>/",
        dashboard.AnnouncementViewedByList.as_view(),
        name="dashboard-announcement-viewed-by-list",
    ),
    path(
        "update-announcement/<int:pk>/",
        announcement_cbv.AnnouncementFormView.as_view(),
        name="update-announcement",
    ),
    path(
        "remove-announcement-file/<int:obj_id>/<int:attachment_id>/",
        announcement.remove_announcement_file,
        name="remove-announcement-file",
    ),
    path(
        "announcement-add-comment/<int:anoun_id>/",
        announcement.create_announcement_comment,
        name="announcement-add-comment",
    ),
    path(
        "announcement-view-comment/<int:anoun_id>/",
        announcement.comment_view,
        name="announcement-view-comment",
    ),
    # path(
    #     "announcement-single-view/<int:anoun_id>",
    #     announcement.announcement_single_view,
    #     name="announcement-single-view",
    # ),
    path(
        "announcement-single-view/<int:pk>/",
        announcement_cbv.AnnouncementDetailView.as_view(),
        name="announcement-single-view",
    ),
    path(
        "announcement-single-view/",
        announcement.announcement_single_view,
        name="announcement-single-view",
    ),
    path(
        "announcement-delete-comment/<int:comment_id>/",
        announcement.delete_announcement_comment,
        name="announcement-delete-comment",
    ),
    path(
        "announcement-viewed-by/", announcement.viewed_by, name="announcement-viewed-by"
    ),
    path("driver-viewed/", views.driver_viewed_status, name="driver-viewed"),
    path(
        "dashboard-components-toggle/",
        views.dashboard_components_toggle,
        name="dashboard-components-toggle",
    ),
    path(
        "reorder-dashboard-charts/",
        views.reorder_dashboard_charts,
        name="reorder-dashboard-charts",
    ),
    path("employee-chart-show/", views.employee_chart_show, name="employee-chart-show"),
    path(
        "settings/activate-biometric-attendance/",
        views.activate_biometric_attendance,
        name="activate-biometric-attendance",
    ),
    path(
        "employee/shift-request-view/",
        shift_request.ShiftRequestView.as_view(),
        name="shift-request-view",
    ),
    path(
        "list-shift-request/",
        shift_request.ShiftRequestList.as_view(),
        name="list-shift-request",
    ),
    path(
        "shift-request-nav/",
        shift_request.ShitRequestNav.as_view(),
        name="shift-request-nav",
    ),
    path("shift-export/", shift_request.ExportView.as_view(), name="shift-export"),
    path(
        "shift-request-tab/",
        shift_request.ShiftRequestTab.as_view(),
        name="shift-request-tab",
    ),
    path(
        "shift-request-individual-tab-view/<int:pk>/",
        work_shift_tab.ShiftRequestIndividualTabView.as_view(),
        name="shift-request-individual-tab-view",
    ),
    path(
        "shift-request-individual-tab-shell/<int:pk>/",
        work_shift_tab.ShiftRequestIndividualTabShell.as_view(),
        name="shift-request-individual-tab-shell",
    ),
    path(
        "shift-request-individual-tab-nav/<int:pk>/",
        work_shift_tab.ShiftRequestIndividualNav.as_view(),
        name="shift-request-individual-tab-nav",
    ),
    path(
        "shift-allocation-individual-tab-view/<int:pk>/",
        work_shift_tab.ShiftAllocationIndividualTabView.as_view(),
        name="shift-allocation-individual-tab-view",
    ),
    path(
        "shift-allocation-individual-tab-shell/<int:pk>/",
        work_shift_tab.ShiftAllocationIndividualTabShell.as_view(),
        name="shift-allocation-individual-tab-shell",
    ),
    path(
        "shift-allocation-individual-tab-nav/<int:pk>/",
        work_shift_tab.ShiftAllocationIndividualNav.as_view(),
        name="shift-allocation-individual-tab-nav",
    ),
    path(
        "rotating-shift-individual-tab-view/<int:pk>/",
        work_shift_tab.RotatingShiftAssignIndividualView.as_view(),
        name="rotating-shift-individual-tab-view",
    ),
    path(
        "rotating-shift-individual-tab-shell/<int:pk>/",
        work_shift_tab.RotatingShiftIndividualTabShell.as_view(),
        name="rotating-shift-individual-tab-shell",
    ),
    path(
        "rotating-shift-individual-tab-nav/<int:pk>/",
        work_shift_tab.RotatingShiftIndividualNav.as_view(),
        name="rotating-shift-individual-tab-nav",
    ),
    path(
        "rotating-shift-individual-detail-view/<int:pk>/",
        work_shift_tab.RotatingShiftAssignIndividualDetailView.as_view(),
        name="rotating-shift-individual-detail-view",
    ),
    path(
        "allocated-shift-view/",
        shift_request.AllocatedShift.as_view(),
        name="allocated-shift-view",
    ),
    path(
        "shift-detail-view/<int:pk>/",
        shift_request.ShiftRequestDetailview.as_view(),
        name="shift-detail-view",
    ),
    path(
        "allocate-detail-view/<int:pk>/",
        shift_request.AllocatedShiftDetailView.as_view(),
        name="allocate-detail-view",
    ),
    path(
        "employee/rotating-shift-assign/",
        rotating_shift_assign.RotatingShiftAssignView.as_view(),
        name="rotating-shift-assign",
    ),
    path(
        "rotating-shift-request-list/",
        rotating_shift_assign.RotatingShiftList.as_view(),
        name="rotating-shift-request-list",
    ),
    path(
        "rotating-shift-request-nav/",
        rotating_shift_assign.RotatingShiftAssignNav.as_view(),
        name="rotating-shift-request-nav",
    ),
    path(
        "rotating-shift-detail-view/<int:pk>/",
        rotating_shift_assign.RotatingShiftDetailview.as_view(),
        name="rotating-shift-detail-view",
    ),
    path(
        "export-rshift/",
        rotating_shift_assign.RotatingExportView.as_view(),
        name="export-rshift",
    ),
    # path(
    #     "emp-workinfo-complete",
    #     views.employee_workinfo_complete,
    #     name="emp-workinfo-complete",
    # ),
    path(
        "emp-workinfo-complete/",
        dashboard.EmployeeWorkInformationList.as_view(),
        name="emp-workinfo-complete",
    ),
    path(
        "update-emp-workinfo/<int:pk>/",
        dashboard.EmployeeWorkInformationFormView.as_view(),
        name="update-emp-workinfo",
    ),
    path(
        "configuration/multiple-approval-condition/",
        multiple_approval_condition.MultipleApprovalConditionView.as_view(),
        name="multiple-approval-condition",
    ),
    path(
        "configuration/hx-multiple-approval-condition/",
        multiple_approval_condition.MultipleApprovalConditionList.as_view(),
        name="hx-multiple-approval-condition",
    ),
    path(
        "nav-multiple-approval-condition/",
        multiple_approval_condition.MultipleApprovalConditionNav.as_view(),
        name="nav-multiple-approval-condition",
    ),
    path(
        "detail-view-multiple-approval-condition/<int:pk>/",
        multiple_approval_condition.MultipleApprovalConditionDetailView.as_view(),
        name="detail-view-multiple-approval-condition",
    ),
    path(
        "get-horilla-installed-apps/",
        views.get_horilla_installed_apps,
        name="get-horilla-installed-apps",
    ),
    # path("configuration/holiday-view", views.holiday_view, name="holiday-view"),
    path(
        "configuration/holidays-excel-template/",
        views.holidays_excel_template,
        name="holidays-excel-template",
    ),
    path(
        "settings/holidays-view/",
        views.holidays_settings_view,
        name="holidays-view",
    ),
    path(
        "configuration/holiday-view/",
        holidays.HolidaysView.as_view(),
        name="holiday-view",
    ),
    path("holiday-filter/", holidays.HolidayListView.as_view(), name="holiday-filter"),
    path("holiday-navbar/", holidays.HolidayNavView.as_view(), name="holiday-navbar"),
    path(
        "holiday-nav-export/",
        holidays.HolidayExport.as_view(),
        name="holiday-nav-export",
    ),
    path(
        "holiday-detail-view/<int:pk>/",
        holidays.HolidayDetailView.as_view(),
        name="holiday-detail-view",
    ),
    path(
        "holiday-creation/", holidays.HolidayFormView.as_view(), name="holiday-creation"
    ),
    path(
        "holiday-update/<int:pk>/",
        holidays.HolidayFormView.as_view(),
        name="holiday-update",
    ),
    path(
        "holidays-info-import/", views.holidays_info_import, name="holidays-info-import"
    ),
    path("holiday-info-export/", views.holiday_info_export, name="holiday-info-export"),
    path(
        "get-upcoming-holidays/",
        views.get_upcoming_holidays,
        name="get-upcoming-holidays",
    ),
    path(
        "duplicate-holiday/<int:obj_id>/",
        views.object_duplicate,
        name="duplicate-holiday",
        kwargs={
            "model": Holidays,
            "form": HolidayForm,
            "template": "holiday/holiday_form.html",
        },
    ),
    path("holiday-delete/<int:obj_id>/", views.holiday_delete, name="holiday-delete"),
    path(
        "holidays-bulk-delete/", views.bulk_holiday_delete, name="holidays-bulk-delete"
    ),
    # path("holiday-filter", views.holiday_filter, name="holiday-filter"),
    path("holiday-select/", views.holiday_select, name="holiday-select"),
    path(
        "holiday-select-filter/",
        views.holiday_select_filter,
        name="holiday-select-filter",
    ),
    # path(
    #     "company-leave-creation",
    #     views.company_leave_creation,
    #     name="company-leave-creation",
    # ),
    # path(
    #     "configuration/company-leave-view",
    #     views.company_leave_view,
    #     name="company-leave-view",
    # ),
    path(
        "settings/company-leaves-view/",
        views.company_leaves_settings_view,
        name="company-leaves-view",
    ),
    path(
        "configuration/company-leave-view/",
        company_leaves.CompanyLeavesView.as_view(),
        name="company-leave-view",
    ),
    path(
        "company-leave-filter/",
        company_leaves.CompanyleaveListView.as_view(),
        name="company-leave-filter",
    ),
    path(
        "company-leave-navbar/",
        company_leaves.CompanyLeaveNavView.as_view(),
        name="company-leave-navbar",
    ),
    path(
        "company-leave-detail-view/<int:pk>/",
        company_leaves.CompanyLeaveDetailView.as_view(),
        name="company-leave-detail-view",
    ),
    path(
        "company-leave-creation/",
        company_leaves.CompanyleaveFormView.as_view(),
        name="company-leave-creation",
    ),
    path(
        "company-leave-update/<int:pk>/",
        company_leaves.CompanyleaveFormView.as_view(),
        name="company-leave-update",
    ),
    # path(
    #     "company-leave-update/<int:id>",
    #     views.company_leave_update,
    #     name="company-leave-update",
    # ),
    path(
        "company-leave-delete/<int:id>/",
        views.company_leave_delete,
        name="company-leave-delete",
    ),
    # path(
    #     "company-leave-filter", views.company_leave_filter, name="company-leave-filter"
    # ),
    # path("view-penalties", views.view_penalties, name="view-penalties"),
    path("view-penalties/", penalty.ViewPenaltyList.as_view(), name="view-penalties"),
    path(
        "delete-penalties/<int:penalty_id>/",
        views.delete_penalities,
        name="delete-penalties",
    ),
    path(
        "enable-integration/",
        views.EnableIntegrationsView.as_view(),
        name="enable-integration",
    ),
    # ── Shift Roster ──────────────────────────────────────────────────────
    path(
        "employee/roster/",
        roster.RosterHomeView.as_view(),
        name="roster-home",
    ),
    path(
        "roster/nav/",
        roster.RosterNavView.as_view(),
        name="roster-nav",
    ),
    path(
        "roster/grid/",
        roster.RosterGridView.as_view(),
        name="roster-grid",
    ),
    path(
        "roster/cell/",
        roster.RosterCellUpdateView.as_view(),
        name="roster-cell-form",
    ),
    path(
        "roster/cell/update/",
        roster.RosterCellUpdateView.as_view(),
        name="roster-cell-update",
    ),
    path(
        "roster/publish/form/",
        roster.RosterPublishFormView.as_view(),
        name="roster-publish-form",
    ),
    path(
        "roster/publish/",
        roster.RosterPublishView.as_view(),
        name="roster-publish",
    ),
    path(
        "roster/employees/publish/",
        roster.RosterEmployeeBulkPublishView.as_view(),
        name="roster-employees-publish",
    ),
    path(
        "roster/my/",
        roster.MyRosterView.as_view(),
        name="my-roster",
    ),
    path(
        "roster/import/form/",
        roster.RosterImportFormView.as_view(),
        name="roster-import-form",
    ),
    path(
        "roster/import/",
        roster.RosterImportView.as_view(),
        name="roster-import",
    ),
    path(
        "roster/import/template/",
        roster.RosterTemplateDownloadView.as_view(),
        name="roster-template-download",
    ),
    # ── End Shift Roster ──────────────────────────────────────────────────
]

urlpatterns.append(
    re_path(r"^media/(?P<path>.*)$", views.protected_media, name="protected_media"),
)
