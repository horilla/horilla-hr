"""
urls.py

This page is used to map request or url path with function

"""

from django.urls import path

from attendance import dashboard as att_dashboard
from attendance.cbv import (
    attendance_activity,
    attendance_request,
    attendance_tab,
    attendances,
    break_point,
    check_in_check_out,
    dashboard,
    dashboard_offline_online,
    grace_time,
    hour_account,
    ip_restriction,
    late_come_and_early_out,
    my_attendances,
)
from attendance.views import clock_in_out
from attendance.views import dashboard as attendance_dashboard
from attendance.views import geofaceconfig, penalty, requests, search
from base.forms import AttendanceAllowedIPForm
from base.models import AttendanceAllowedIP
from base.views import add_remove_dynamic_fields

from .views import regularisation_import, summary, views

urlpatterns = [
    path(
        "individual-panalty-list-view/<int:pk>/",
        attendances.PenaltyAccountListView.as_view(),
        name="individual-panalty-list-view",
    ),
    path(
        "attendance-activity-view/",
        attendance_activity.AttendanceActivityView.as_view(),
        name="attendance-activity-view",
    ),
    path(
        "attendance-activity-search/",
        attendance_activity.AttendanceActivityListView.as_view(),
        name="attendance-activity-search",
    ),
    path(
        "attendance-nav-view/",
        attendance_activity.AttendanceActivityNavView.as_view(),
        name="attendance-nav-view",
    ),
    path(
        "attendance-bulk-export/",
        attendance_activity.AttendanceBulkExport.as_view(),
        name="attendance-bulk-export",
    ),
    path(
        "attendance-activity-single-view/<int:pk>/",
        attendance_activity.AttendanceDetailView.as_view(),
        name="attendance-activity-single-view",
    ),
    # path(
    #     "activity-attendance-delete/<int:obj_id>",
    #     attendance_activity.AttendanceActivityDeleteView.as_view(),
    #     name="activity-attendance-delete",
    # ),
    path(
        "attendance-view/",
        attendances.AttendancesView.as_view(),
        name="attendance-view",
    ),
    path(
        "attendances-list-view/",
        attendances.AttendancesListView.as_view(),
        name="attendances-list-view",
    ),
    path(
        "attendances-tab-view/",
        attendances.AttendancesTabView.as_view(),
        name="attendances-tab-view",
    ),
    path(
        "attendences-navbar-export/",
        attendances.AttendancesExportNav.as_view(),
        name="attendences-navbar-export",
    ),
    path(
        "validate-attendance-tab/",
        attendances.ValidateAttendancesList.as_view(),
        name="validate-attendance-tab",
    ),
    path(
        "validate-attendance-tab-shell/",
        attendances.ValidateAttendanceTabShell.as_view(),
        name="validate-attendance-tab-shell",
    ),
    path(
        "validate-attendance-nav/",
        attendances.ValidateAttendanceNav.as_view(),
        name="validate-attendance-nav",
    ),
    path(
        "validate-attendance-individual-tab/<int:pk>/",
        attendances.ValidateAttendancesIndividualTabView.as_view(),
        name="validate-attendance-individual-tab",
    ),
    path(
        "ot-attendance-tab/",
        attendances.OTAttendancesList.as_view(),
        name="ot-attendance-tab",
    ),
    path(
        "ot-attendance-tab-shell/",
        attendances.OTAttendanceTabShell.as_view(),
        name="ot-attendance-tab-shell",
    ),
    path(
        "ot-attendance-nav/",
        attendances.OTAttendanceNav.as_view(),
        name="ot-attendance-nav",
    ),
    path(
        "validated-attendance-tab/",
        attendances.ValidatedAttendancesList.as_view(),
        name="validated-attendance-tab",
    ),
    path(
        "validated-attendance-tab-shell/",
        attendances.ValidatedAttendanceTabShell.as_view(),
        name="validated-attendance-tab-shell",
    ),
    path(
        "validated-attendance-nav/",
        attendances.ValidatedAttendanceNav.as_view(),
        name="validated-attendance-nav",
    ),
    path(
        "validate-detail-view/<int:pk>/",
        attendances.ValidateDetailView.as_view(),
        name="validate-detail-view",
    ),
    path(
        "individual-validate-detail-view/<int:pk>/",
        attendances.ValidateAttendancesIndividualDetailView.as_view(),
        name="individual-validate-detail-view",
    ),
    path(
        "ot-detail-view/<int:pk>/",
        attendances.OtDetailView.as_view(),
        name="ot-detail-view",
    ),
    path(
        "validated-detail-view/<int:pk>/",
        attendances.ValidatedDetailView.as_view(),
        name="validated-detail-view",
    ),
    path(
        "attendance-create/",
        attendances.AttendancesFormView.as_view(),
        name="attendance-create",
    ),
    path(
        "break-point-list/",
        break_point.BreakPointList.as_view(),
        name="break-point-list",
    ),
    path(
        "break-point-navbar/",
        break_point.BreakPointNavView.as_view(),
        name="break-point-navbar",
    ),
    path(
        "break-point-create-form/",
        break_point.BreakPointCreateForm.as_view(),
        name="break-point-create-form",
    ),
    path(
        "break-point-update-form/<int:pk>/",
        break_point.BreakPointCreateForm.as_view(),
        name="break-point-update-form",
    ),
    # path("attendance-create", views.attendance_create, name="attendance-create"),
    path(
        "update-shift-details/",
        views.form_shift_dynamic_data,
        name="update-shift-details",
    ),
    path(
        "profile-attendance-tab/",
        views.profile_attendance_tab,
        name="profile-attendance-tab",
    ),
    path("attendance-tab/<int:pk>/", views.attendance_tab, name="attendance-tab"),
    path("attendance-create/", views.attendance_create, name="attendance-create"),
    path("attendance-excel/", views.attendance_excel, name="attendance-excel"),
    path(
        "attendance-info-import/",
        views.attendance_import,
        name="attendance-info-import",
    ),
    path(
        "attendance-info-export-form/",
        views.attendance_export,
        name="attendance-info-export-form",
    ),
    path(
        "attendance-info-export/",
        views.attendance_export,
        name="attendance-info-export",
    ),
    # path("attendance-view/", views.attendance_view, name="attendance-view"),
    path(
        "attendance-search/",
        search.attendance_search,
        name="attendance-search",
    ),
    path(
        "attendance-update/<int:pk>/",
        attendances.AttendanceUpdateFormView.as_view(),
        name="attendance-update",
    ),
    # path(
    #     "attendance-update/<int:obj_id>/",
    #     views.attendance_update,
    #     name="attendance-update",
    # ),
    path(
        "attendance-delete/<int:obj_id>/",
        views.attendance_delete,
        name="attendance-delete",
    ),
    path(
        "attendance-bulk-delete/",
        views.attendance_bulk_delete,
        name="attendance-bulk-delete",
    ),
    # path(
    #     "attendance-overtime-create",
    #     views.attendance_overtime_create,
    #     name="attendance-overtime-create",
    # ),
    path(
        "attendance-overtime-create/",
        hour_account.HourAccountFormView.as_view(),
        name="attendance-overtime-create",
    ),
    path(
        "attendance-account-info-export/",
        views.attendance_account_export,
        name="attendance-account-info-export",
    ),
    # path(
    #     "attendance-overtime-view/",
    #     views.attendance_overtime_view,
    #     name="attendance-overtime-view",
    # ),
    # path(
    #     "attendance-overtime-search",
    #     attendance.views.search.attendance_overtime_search,
    #     name="attendance-ot-search",
    # ),
    # path(
    #     "attendance-overtime-update/<int:obj_id>/",
    #     views.attendance_overtime_update,
    #     name="attendance-overtime-update",
    # ),
    path(
        "attendance-overtime-update/<int:pk>/",
        hour_account.HourAccountFormView.as_view(),
        name="attendance-overtime-update",
    ),
    path(
        "attendance-overtime-delete/<int:obj_id>/",
        views.attendance_overtime_delete,
        name="attendance-overtime-delete",
    ),
    # path(
    #     "attendance-activity-view/",
    #     views.attendance_activity_view,
    #     name="attendance-activity-view",
    # ),
    # path(
    #     "attendance-activity-single-view/<int:obj_id>/",
    #     views.activity_single_view,
    #     name="attendance-activity-single-view",
    # ),
    # path(
    #     "attendance-activity-search",
    #     attendance.views.search.attendance_activity_search,
    #     name="attendance-activity-search",
    # ),
    path(
        "attendance-activity-delete/<int:obj_id>/",
        views.attendance_activity_delete,
        name="attendance-activity-delete",
    ),
    path(
        "attendance-activity-bulk-delete/",
        views.attendance_activity_bulk_delete,
        name="attendance-activity-bulk-delete",
    ),
    path(
        "attendance-activity-import/",
        views.attendance_activity_import,
        name="attendance-activity-import",
    ),
    path(
        "attendance-activity-import-excel/",
        views.attendance_activity_import_excel,
        name="attendance-activity-import-excel",
    ),
    path(
        "attendance-activity-info-export/",
        views.attendance_activity_export,
        name="attendance-activity-info-export",
    ),
    # path("view-my-attendance/", views.view_my_attendance, name="view-my-attendance"),
    path(
        "filter-own-attendance/",
        search.filter_own_attendance,
        name="filter-own-attendance",
    ),
    path(
        "own-attendance-filter/",
        search.own_attendance_sort,
        name="own-attendance-filter",
    ),
    path("clock-in/", clock_in_out.clock_in, name="clock-in"),
    path("clock-out/", clock_in_out.clock_out, name="clock-out"),
    path(
        "on-time-view/",
        views.on_time_view,
        name="on-time-view",
    ),
    # path(
    #     "late-come-early-out-view/",
    #     views.late_come_early_out_view,
    #     name="late-come-early-out-view",
    # ),
    # path(
    #     "late-in-early-out-single-view/<int:obj_id>/",
    #     views.late_in_early_out_single_view,
    #     name="late-in-early-out-single-view",
    # ),
    # path(
    #     "late-come-early-out-search",
    #     search.late_come_early_out_search,
    #     name="late-come-early-out-search",
    # ),
    path(
        "late-come-early-out-delete/<int:obj_id>/",
        views.late_come_early_out_delete,
        name="late-come-early-out-delete",
    ),
    path(
        "late-come-early-out-bulk-delete/",
        views.late_come_early_out_bulk_delete,
        name="late-come-early-out-bulk-delete",
    ),
    path(
        "late-come-early-out-info-export/",
        views.late_come_early_out_export,
        name="late-come-early-out-info-export",
    ),
    path(
        "validation-condition-create/",
        views.validation_condition_create,
        name="validation-condition-create",
    ),
    path(
        "validation-condition-update/<int:obj_id>/",
        views.validation_condition_update,
        name="validation-condition-update",
    ),
    path(
        "validation-condition-delete/<int:obj_id>/",
        views.validation_condition_delete,
        name="validation-condition-delete",
    ),
    path(
        "validate-bulk-attendance/",
        views.validate_bulk_attendance,
        name="validate-bulk-attendance",
    ),
    path(
        "validate-this-attendance/<int:obj_id>/",
        views.validate_this_attendance,
        name="validate-this-attendance",
    ),
    path(
        "revalidate-this-attendance/<int:obj_id>/",
        views.revalidate_this_attendance,
        name="revalidate-this-attendance",
    ),
    path(
        "approve-overtime/<int:obj_id>/",
        views.approve_overtime,
        name="approve-overtime",
    ),
    path(
        "approve-bulk-overtime/",
        views.approve_bulk_overtime,
        name="approve-bulk-overtime",
    ),
    path(
        "attendance-add-to-batch/",
        views.attendance_add_to_batch,
        name="attendance-add-to-batch",
    ),
    path(
        "dashboard/",
        att_dashboard.attendance_dashboard_view,
        name="attendance-dashboard",
    ),
    path(
        "on-break-employees/",
        attendance_dashboard.on_break_employees,
        name="on-break-employees",
    ),
    path(
        "dashboard-approve-overtimes/",
        attendance_dashboard.dashboard_approve_overtimes,
        name="dashboard-approve-overtimes",
    ),
    path(
        "dashboard-validate-attendances/",
        attendance_dashboard.dashboard_validate_attendances,
        name="dashboard-validate-attendances",
    ),
    path(
        "department-overtime-chart/",
        attendance_dashboard.department_overtime_chart,
        name="department-overtime-chart",
    ),
    path(
        "dashboard-attendance/",
        attendance_dashboard.dashboard_attendance,
        name="dashboard-attendance",
    ),
    # path(
    #     "request-attendance/",
    #     requests.request_attendance,
    #     name="request-attendance",
    # ),
    # path(
    #     "request-attendance-view/",
    #     requests.request_attendance_view,
    #     name="request-attendance-view",
    # ),
    path(
        "request-attendance/<int:attendance_id>/",
        requests.attendance_request_changes,
        name="attendance-change",
    ),
    path(
        "not-in-yet/",
        dashboard_offline_online.DashboardOfflineEmployees.as_view(),
        name="not-in-yet",
    ),
    path(
        "not-out-yet/",
        dashboard_offline_online.DashboardOnlineEmployees.as_view(),
        name="not-out-yet",
    ),
    path(
        "validate-attendance-request/<int:attendance_id>/",
        requests.validate_attendance_request,
        name="validate-attendance-request",
    ),
    path(
        "approve-validate-attendance-request/<int:attendance_id>/",
        requests.approve_validate_attendance_request,
        name="approve-validate-attendance-request",
    ),
    path(
        "edit-validate-attendance/<int:attendance_id>/",
        requests.edit_validate_attendance,
        name="edit-validate-attendance",
    ),
    path(
        "search-attendance-requests/",
        search.search_attendance_requests,
        name="search-attendance-requests",
    ),
    path(
        "cancel-validate-attendance-request/<int:attendance_id>/",
        requests.cancel_attendance_request,
        name="cancel-validate-attendance-request",
    ),
    path(
        "select-all-filter-attendance-request/",
        requests.select_all_filter_attendance_request,
        name="select-all-filter-attendance-request",
    ),
    path(
        "bulk-reject-attendance-request/",
        requests.bulk_reject_attendance_request,
        name="bulk-reject-attendance-request",
    ),
    path(
        "bulk-approve-attendance-request/",
        requests.bulk_approve_attendance_request,
        name="bulk-approve-attendance-request",
    ),
    # path(
    #     "request-new-attendance",
    #     requests.request_new,
    #     name="request-new-attendance",
    # ),
    path(
        "request-new-attendance/",
        attendance_request.NewAttendanceRequestFormView.as_view(),
        name="request-new-attendance",
    ),
    path(
        "request-bulk-attendance/",
        attendance_request.BulkAttendanceRequestFormView.as_view(),
        name="request-bulk-attendance",
    ),
    path(
        "update-attendance-request/<int:pk>/",
        attendance_request.UpdateAttendanceRequestFormView.as_view(),
        name="update-attendance-request",
    ),
    path(
        "create-batch-attendance/",
        requests.create_batch_attendance,
        name="create-batch-attendance",
    ),
    path("get-batches/", requests.get_batches, name="get-batches"),
    path("update-title/", requests.update_title, name="update-title"),
    path(
        "delete-batch/<int:batch_id>/",
        requests.delete_batch,
        name="delete-batch",
    ),
    path(
        "employee-widget-filter/",
        search.widget_filter,
        name="attendance-widget-filter",
    ),
    path(
        "update-fields-based-shift/",
        views.update_fields_based_shift,
        name="update-fields-based-shift",
    ),
    path(
        "update-worked-hour-field/",
        views.update_worked_hour_field,
        name="update-worked-hour-field",
    ),
    path(
        "update-date-details/",
        views.form_date_checking,
        name="update-date-details",
    ),
    path(
        "user-request-one-view/<int:id>/",
        views.user_request_one_view,
        name="user-request-one-view",
    ),
    #    path(
    #     "get-attendance-activities/<int:obj_id>",
    #     views.get_attendance_activities,
    #     name="get-attendance-activities",
    # ),
    path(
        "get-attendance-activities/<int:pk>/",
        attendances.AttendanceDetailActivityList.as_view(),
        name="get-attendance-activities",
    ),
    path(
        "get-attendance-activities/<int:obj_id>/",
        views.get_attendance_activities,
        name="get-attendance-activities",
    ),
    path(
        "hour-attendance-select/",
        views.hour_attendance_select,
        name="hour-attendance-select",
    ),
    path(
        "hour-attendance-select-filter/",
        views.hour_attendance_select_filter,
        name="hour-attendance-select-filter",
    ),
    path(
        "attendance-account-bulk-delete/",
        views.attendance_account_bulk_delete,
        name="attendance-account-bulk-delete",
    ),
    path(
        "activity-attendance-select/",
        views.activity_attendance_select,
        name="activity-attendance-select",
    ),
    path(
        "activity-attendance-select-filter/",
        views.activity_attendance_select_filter,
        name="activity-attendance-select-filter",
    ),
    path(
        "latecome-attendance-select/",
        views.latecome_attendance_select,
        name="latecome-attendance-select",
    ),
    path(
        "latecome-attendance-select-filter/",
        views.latecome_attendance_select_filter,
        name="latecome-attendance-select-filter",
    ),
    path("pending-hours/", attendance_dashboard.pending_hours, name="pending-hours"),
    path("create-garce-time/", views.create_grace_time, name="create-grace-time"),
    path("assign-shift/<int:grace_id>/", views.assign_shift, name="assign-shift"),
    path(
        "update-garce-time/<int:grace_id>/",
        views.update_grace_time,
        name="update-grace-time",
    ),
    path(
        "delete-garce-time/<int:grace_id>/",
        views.delete_grace_time,
        name="delete-grace-time",
    ),
    path(
        "update-isactive-gracetime/",
        views.update_isactive_gracetime,
        name="update-isactive-gracetime",
    ),
    path(
        "update-gracetime-clock-in-clock-out/",
        views.update_gracetime_clock_in_clock_out,
        name="update-gracetime-clock-in-clock-out",
    ),
    path(
        "attendance-request-add-comment/<int:attendance_id>/",
        views.create_attendancerequest_comment,
        name="attendance-request-add-comment",
    ),
    path(
        "attendance-request-view-comment/<int:attendance_id>/",
        views.view_attendancerequest_comment,
        name="attendance-request-view-comment",
    ),
    path(
        "attendance-request-delete-comment/<int:comment_id>/",
        views.delete_attendancerequest_comment,
        name="attendance-request-delete-comment",
    ),
    path(
        "delete-comment-file/",
        views.delete_comment_file,
        name="delete-comment-file",
    ),
    path("work-records/", views.work_records, name="work-records"),
    path("work-record-export/", views.work_record_export, name="work-record-export"),
    path(
        "work-records-change-month/",
        views.work_records_change_month,
        name="work-records-change-month",
    ),
    path("enable-timerunner/", views.enable_timerunner, name="enable-timerunner"),
    path(
        "get-employee-shift/",
        requests.get_employee_shift,
        name="get-employee-shift",
    ),
    path(
        "view-my-attendance/",
        my_attendances.MyAttendances.as_view(),
        name="view-my-attendance",
    ),
    path(
        "my-attendance-list/",
        my_attendances.MyAttendanceList.as_view(),
        name="my-attendance-list",
    ),
    path(
        "my-attendance-nav/",
        my_attendances.MyAttendancestNav.as_view(),
        name="my-attendance-nav",
    ),
    path(
        "my-attendance-detail/<int:pk>/",
        my_attendances.MyAttendancesDetailView.as_view(),
        name="my-attendance-detail",
    ),
    path(
        "attendance-overtime-view/",
        hour_account.HourAccount.as_view(),
        name="attendance-overtime-view",
    ),
    path(
        "attendance-overtime-search/",
        hour_account.HourAccountList.as_view(),
        name="attendance-ot-search",
    ),
    path(
        "attendance-overtime-individual-tab/<int:pk>/",
        attendance_tab.HourAccountIndividualTabView.as_view(),
        name="attendance-overtime-individual-tab",
    ),
    path(
        "all-attendances-individual-tab/<int:pk>/",
        attendance_tab.AllAttendancesList.as_view(),
        name="all-attendances-individual-tab",
    ),
    path(
        "hour-account-nav/",
        hour_account.HourAccountNav.as_view(),
        name="hour-account-nav",
    ),
    path(
        "hour-account-export/",
        hour_account.HourExportView.as_view(),
        name="hour-account-export",
    ),
    path(
        "hour-account-detail-view/<int:pk>/",
        hour_account.HourAccountDetailView.as_view(),
        name="hour-account-detail-view",
    ),
    path(
        "late-come-early-out-view/",
        late_come_and_early_out.LateComeAndEarlyOut.as_view(),
        name="late-come-early-out-view",
    ),
    path(
        "late-come-early-out-search/",
        late_come_and_early_out.LateComeAndEarlyOutList.as_view(),
        name="late-come-early-out-search",
    ),
    path(
        "late-come-and-early-out-nav/",
        late_come_and_early_out.LateComeAndEarlyOutListNav.as_view(),
        name="late-come-and-early-out-nav",
    ),
    path(
        "late-come-and-early-out-export/",
        late_come_and_early_out.LateEarlyExportView.as_view(),
        name="late-come-and-early-out-export",
    ),
    path(
        "cut-penalty/<int:instance_id>/",
        penalty.cut_available_leave,
        name="cut-penalty",
    ),
    # path(
    #     "dashboard-overtime-approve",
    #     dashboard.dashboard_overtime_approve,
    #     name="dashboard-overtime-approve",
    # ),
    path(
        "dashboard-overtime-approve/",
        dashboard.DashboardaAttendanceOT.as_view(),
        name="dashboard-overtime-approve",
    ),
    # path(
    #     "dashboard-attendance-validate",
    #     dashboard.dashboard_attendance_validate,
    #     name="dashboard-attendance-validate",
    # ),
    path(
        "dashboard-attendance-validate/",
        dashboard.DashboardAttendanceToValidate.as_view(),
        name="dashboard-attendance-validate",
    ),
    path(
        "dashboard-on-break/",
        dashboard.DashboardOnBreak.as_view(),
        name="dashboard-on-break",
    ),
    path(
        "attendance-settings-view/",
        views.validation_condition_view,
        name="attendance-settings-view",
    ),
    path(
        "time-policies-view/",
        views.time_policies_settings_view,
        name="time-policies-view",
    ),
    path(
        "attendance-rule-view/",
        views.attendance_rule_settings_view,
        name="attendance-rule-view",
    ),
    path(
        "track-late-come-early-out/",
        views.track_late_come_early_out,
        name="track-late-come-early-out",
    ),
    path(
        "enable-disable-tracking-late-come-early-out/",
        views.enable_disable_tracking_late_come_early_out,
        name="enable-disable-tracking-late-come-early-out",
    ),
    path(
        "check-in-check-out-setting/",
        views.check_in_check_out_setting,
        name="check-in-check-out-setting",
    ),
    path(
        "enable-disable-check-in/",
        views.enable_disable_check_in,
        name="enable-disable-check-in",
    ),
    path(
        "grace-settings-view/",
        views.grace_time_view,
        name="grace-settings-view",
    ),
    path(
        "grace-time-view/",
        views.grace_time_page_view,
        name="grace-time-view",
    ),
    path(
        "grace-time-list-tab/",
        views.grace_time_list_tab,
        name="grace-time-list-tab",
    ),
    path(
        "grace-time-validation-condition-tab/",
        views.grace_time_validation_condition_tab,
        name="grace-time-validation-condition-tab",
    ),
    path(
        "settings/attendance-settings-create/",
        views.validation_condition_create,
        name="attendance-settings-create",
    ),
    path(
        "settings/attendance-settings-update/<int:obj_id>/",
        views.validation_condition_update,
        name="attendance-settings-update",
    ),
    path(
        "allowed-ips/",
        views.allowed_ips,
        name="allowed-ips",
    ),
    path(
        "allowed-ips-list/",
        ip_restriction.IpRestrictionList.as_view(),
        name="allowed-ips-list",
    ),
    path(
        "allowed-ips-nav/",
        ip_restriction.IpRestrictionnav.as_view(),
        name="allowed-ips-nav",
    ),
    path(
        "settings/enable-ip-restriction/",
        views.enable_ip_restriction,
        name="enable-ip-restriction",
    ),
    path(
        "settings/create-allowed-ip/",
        views.create_allowed_ips,
        name="create-allowed-ip",
    ),
    path(
        "settings/delete-allowed-ip/",
        views.delete_allowed_ips,
        name="delete-allowed-ip",
    ),
    path(
        "settings/edit-allowed-ip/",
        views.edit_allowed_ips,
        name="edit-allowed-ip",
    ),
    path(
        "settings/add-remove-ip-fields/",
        add_remove_dynamic_fields,
        name="add-remove-ip-fields",
        kwargs={
            "model": AttendanceAllowedIP,
            "form_class": AttendanceAllowedIPForm,
            "template": "attendance/ip_restriction/add_more_ip_fields.html",
            "field_type": "character",
            "field_name_pre": "ip_address",
        },
    ),
    path(
        "late-in-early-out-single-view/<int:pk>/",
        late_come_and_early_out.LateComeEarlyOutDetailView.as_view(),
        name="late-in-early-out-single-view",
    ),
    path(
        "request-attendance-view/",
        attendance_request.AttendancesRequestView.as_view(),
        name="request-attendance-view",
    ),
    path(
        "attendance-request-tab/",
        attendance_request.AttendancesRequestTabView.as_view(),
        name="attendance-request-tab",
    ),
    path(
        "attendance-request-list/",
        attendance_request.AttendancesRequestListView.as_view(),
        name="attendance-request-list",
    ),
    path(
        "attendance-request-list-tab/",
        attendance_request.AttendanceRequestListTab.as_view(),
        name="attendance-request-list-tab",
    ),
    path(
        "requested-attendance-tab-shell/",
        attendance_request.RequestedAttendanceTabShell.as_view(),
        name="requested-attendance-tab-shell",
    ),
    path(
        "requested-attendance-nav/",
        attendance_request.RequestedAttendanceNav.as_view(),
        name="requested-attendance-nav",
    ),
    path(
        "attendance-request-individual-tab/<int:pk>/",
        attendance_tab.RequestedAttendanceIndividualView.as_view(),
        name="attendance-request-individual-tab",
    ),
    path(
        "attendance-request-individual-tab-shell/<int:pk>/",
        attendance_tab.RequestedAttendanceIndividualTabShell.as_view(),
        name="attendance-request-individual-tab-shell",
    ),
    path(
        "attendance-request-individual-tab-nav/<int:pk>/",
        attendance_tab.RequestedAttendanceIndividualNav.as_view(),
        name="attendance-request-individual-tab-nav",
    ),
    path(
        "attendance-list-tab/",
        attendance_request.AttendanceListTab.as_view(),
        name="attendance-list-tab",
    ),
    path(
        "all-attendance-tab-shell/",
        attendance_request.AllAttendanceTabShell.as_view(),
        name="all-attendance-tab-shell",
    ),
    path(
        "all-attendance-request-nav/",
        attendance_request.AllAttendanceRequestNav.as_view(),
        name="all-attendance-request-nav",
    ),
    path(
        "attendances-tab-detail-view/<int:pk>/",
        attendance_request.AttendanceListTabDetailView.as_view(),
        name="attendances-tab-detail-view",
    ),
    path(
        "default-grace-time-list/",
        grace_time.DefaultGraceTimeList.as_view(),
        name="default-grace-time-list",
    ),
    path(
        "default-grace-time-nav/",
        grace_time.DefaultGraceTimeNav.as_view(),
        name="default-grace-time-nav",
    ),
    path(
        "grace-time-nav/",
        grace_time.GraceTimeNav.as_view(),
        name="grace-time-nav",
    ),
    path(
        "grace-time-create/",
        grace_time.GraceTimeFormView.as_view(),
        name="grace-time-create",
    ),
    path(
        "grace-time-update/<int:pk>/",
        grace_time.GraceTimeFormView.as_view(),
        name="grace-time-update",
    ),
    path(
        "grace-time-list/",
        grace_time.GraceTimeList.as_view(),
        name="grace-time-list",
    ),
    path(
        "check-in-check-out-list/",
        check_in_check_out.CheckInCheckOutListView.as_view(),
        name="check-in-check-out-list",
    ),
    path(
        "check-in-check-out-nav/",
        check_in_check_out.CheckInCheckOutNavBar.as_view(),
        name="check-in-check-out-nav",
    ),
    path(
        "settings/geo-face-config/", geofaceconfig.geofaceconfig, name="geo-face-config"
    ),
    # ── Attendance Modern Dashboard API ──────────────────────────────────────
    path(
        "dashboard/api/kpi/",
        att_dashboard.attendance_kpi_data,
        name="attendance-dashboard-kpi",
    ),
    path(
        "dashboard/api/weekly/",
        att_dashboard.attendance_weekly_trend,
        name="attendance-dashboard-weekly",
    ),
    path(
        "dashboard/api/departments/",
        att_dashboard.attendance_department_breakdown,
        name="attendance-dashboard-dept",
    ),
    path(
        "dashboard/api/late-early/",
        att_dashboard.attendance_late_early_data,
        name="attendance-dashboard-late-early",
    ),
    path(
        "dashboard/api/overtime/",
        att_dashboard.attendance_overtime_summary,
        name="attendance-dashboard-overtime",
    ),
    path(
        "dashboard/api/hours/",
        att_dashboard.attendance_hours_distribution,
        name="attendance-dashboard-hours",
    ),
    path(
        "dashboard/api/shifts/",
        att_dashboard.attendance_shift_distribution,
        name="attendance-dashboard-shifts",
    ),
    path(
        "dashboard/api/absenteeism/",
        att_dashboard.attendance_absenteeism_trend,
        name="attendance-dashboard-absenteeism",
    ),
    path(
        "dashboard/api/work-types/",
        att_dashboard.attendance_work_type_distribution,
        name="attendance-dashboard-work-types",
    ),
    path(
        "dashboard/api/avg-hours/",
        att_dashboard.attendance_avg_working_hours,
        name="attendance-dashboard-avg-hours",
    ),
    path(
        "dashboard/api/top-absentees/",
        att_dashboard.attendance_top_absentees,
        name="attendance-dashboard-absentees",
    ),
    path(
        "dashboard/api/clockin-dist/",
        att_dashboard.attendance_clockin_distribution,
        name="attendance-dashboard-clockin",
    ),
    path(
        "dashboard/api/calendar/",
        att_dashboard.attendance_calendar_heatmap,
        name="attendance-dashboard-calendar",
    ),
    path(
        "dashboard/api/overview/",
        att_dashboard.attendance_overview,
        name="attendance-dashboard-overview",
    ),
    # Monthly summary (HR-188 / HR-190)
    path(
        "monthly-summary/",
        summary.attendance_monthly_summary,
        name="attendance-monthly-summary",
    ),
    path(
        "monthly-summary/table/",
        summary.attendance_monthly_summary_table,
        name="attendance-monthly-summary-table",
    ),
    path(
        "monthly-summary/export/",
        summary.attendance_monthly_summary_export,
        name="attendance-monthly-summary-export",
    ),
    path(
        "monthly-summary/detail/",
        summary.attendance_monthly_summary_detail,
        name="attendance-monthly-summary-detail",
    ),
    path(
        "monthly-summary/calendar/",
        summary.attendance_monthly_summary_calendar,
        name="attendance-monthly-summary-calendar",
    ),
    path(
        "monthly-summary/conflict-resolve/",
        summary.attendance_monthly_summary_conflict_resolve,
        name="attendance-monthly-summary-conflict-resolve",
    ),
    # Ctrl/Shift-click a range of calendar day cells, then apply one status
    # to all of them at once — the in-context sibling of the spreadsheet-based
    # bulk regularisation above, for when the days are all visible together
    # on one employee's calendar rather than scattered across the summary.
    path(
        "monthly-summary/conflict-bulk-resolve/",
        summary.attendance_monthly_summary_conflict_bulk_resolve,
        name="attendance-monthly-summary-conflict-bulk-resolve",
    ),
    # Bulk regularisation by spreadsheet: download the days awaiting a
    # decision, fill one column, upload. See regularisation_import for why the
    # template is pre-filled rather than empty.
    path(
        "monthly-summary/regularisation-template/",
        regularisation_import.regularisation_template,
        name="attendance-regularisation-template",
    ),
    path(
        "monthly-summary/regularisation-import/",
        regularisation_import.regularisation_import,
        name="attendance-regularisation-import",
    ),
    path(
        "monthly-summary/regularisation-confirm/",
        regularisation_import.regularisation_confirm,
        name="attendance-regularisation-confirm",
    ),
    path(
        "monthly-summary/bulk-override/",
        summary.attendance_monthly_summary_bulk_override,
        name="attendance-monthly-summary-bulk-override",
    ),
    path(
        "monthly-summary/undo-bulk/",
        summary.attendance_monthly_summary_undo_bulk,
        name="attendance-monthly-summary-undo-bulk",
    ),
    path(
        "monthly-summary/daily-hours-edit/",
        summary.attendance_monthly_summary_daily_hours_edit,
        name="attendance-monthly-summary-daily-hours-edit",
    ),
]
