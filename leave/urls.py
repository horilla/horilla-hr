from django.apps import apps
from django.urls import path
from django.views.generic import RedirectView

from base.cbv import company_leaves, holidays
from employee.models import Employee
from leave import dashboard as leave_dashboard

if apps.is_installed("attendance"):
    from leave.cbv import compensatory_leave_request

from base.views import object_duplicate
from leave.cbv import (
    assigned_leave,
    dashboard,
    leave_allocation_request,
    leave_requests,
    leave_tab,
    leave_types,
    my_leave_request,
    restricted_days,
    settings_tabs,
)
from leave.forms import RestrictLeaveForm

from . import models, views

urlpatterns = [
    path(
        "individual-leave-tab-list/<int:pk>/",
        leave_tab.IndividualLeaveTab.as_view(),
        name="individual-leave-tab-list",
    ),
    path(
        "user-request-view/",
        my_leave_request.MyLeaveRequestView.as_view(),
        name="user-request-view",
    ),
    path(
        "user-request-filter/",
        my_leave_request.MyLeaveRequestListView.as_view(),
        name="user-request-filter",
    ),
    path(
        "my-leave-request-nav/",
        my_leave_request.MyLeaveRequestNavView.as_view(),
        name="my-leave-request-nav",
    ),
    path(
        "my-leave-request-detail-view/<int:pk>/",
        my_leave_request.MyLeaveRequestDetailView.as_view(),
        name="my-leave-request-detail-view",
    ),
    path(
        "request-view/",
        leave_requests.LeaveRequestsView.as_view(),
        name="request-view",
    ),
    # user-leave-filter
    path(
        "request-filter/",
        leave_requests.LeaveRequestsListView.as_view(),
        name="request-filter",
    ),
    path(
        "leave-requests-nav/",
        leave_requests.LeaveRequestsNavView.as_view(),
        name="leave-requests-nav",
    ),
    path(
        "leave-requests-nav-export/",
        leave_requests.LeaveRequestsExportNav.as_view(),
        name="leave-requests-nav-export",
    ),
    path(
        "leave-requests-detail-view/<int:pk>/",
        leave_requests.LeaveRequestsDetailView.as_view(),
        name="leave-requests-detail-view",
    ),
    path(
        "employee-leave/",
        leave_requests.DashboardOnLeaveTable.as_view(),
        name="employee-leave",
    ),
    path(
        "assign-view/",
        assigned_leave.AssignedLeaveViewPage.as_view(),
        name="assign-view",
    ),
    path(
        "assign-filter/",
        assigned_leave.AssignedleaveList.as_view(),
        name="assign-filter",
    ),
    path(
        "assigned-leave-nav/",
        assigned_leave.AssignedLeaveNavView.as_view(),
        name="assigned-leave-nav",
    ),
    path(
        "assigned-leave-nav-export/",
        assigned_leave.AssignedLeaveExport.as_view(),
        name="assigned-leave-nav-export",
    ),
    path(
        "available-leave-single-view/<int:pk>/",
        assigned_leave.AssignedLeaveDetailView.as_view(),
        name="available-leave-single-view",
    ),
    path("type-view/", leave_types.LeaveTypeView.as_view(), name="type-view"),
    path(
        "leave-type-list/",
        leave_types.LeaveTypeListView.as_view(),
        name="leave-type-list",
    ),
    path(
        "leave-type-navbar/",
        leave_types.LeaveTypeNavView.as_view(),
        name="leave-type-navbar",
    ),
    path(
        "leave-type-detail-view/<int:pk>/",
        leave_types.LeaveTypeDetailView.as_view(),
        name="leave-type-detail-view",
    ),
    path(
        "leave-type-card-view/",
        leave_types.LeaveTypeCardView.as_view(),
        name="leave-type-card-view",
    ),
    path("type-creation/", views.leave_type_creation, name="type-creation"),
    path(
        "leave-type/<int:leave_type_id>/condition/create/",
        views.leave_type_condition_create,
        name="leave-type-condition-create",
    ),
    path(
        "leave-type/<int:leave_type_id>/condition/<int:condition_id>/delete/",
        views.leave_type_condition_delete,
        name="leave-type-condition-delete",
    ),
    # path("type-view/", views.leave_type_view, name="type-view"),
    path(
        "leave-type-individual-view/<int:id>/",
        views.leave_type_individual_view,
        name="leave-type-individual-view",
    ),
    path(
        "type-update/<int:id>/",
        views.leave_type_update,
        name="type-update",
        kwargs={"model": models.LeaveType},
    ),
    path("type-delete/<int:obj_id>/", views.leave_type_delete, name="type-delete"),
    path("type-filter/", views.leave_type_filter, name="type-filter"),
    # path("request-creation", views.leave_request_creation, name="request-creation"),
    path(
        "request-creation/",
        leave_requests.LeaveRequestFormView.as_view(),
        name="request-creation",
    ),
    path(
        "get-employee-leave-types/",
        views.get_employee_leave_types,
        name="get-employee-leave-types",
    ),
    # path(
    #     "leave-request-creation/<int:type_id>/<int:emp_id>",
    #     views.leave_request_creation,
    #     name="leave-request-creation",
    # ),
    path(
        "leave-request-creation/<int:type_id>/<int:emp_id>/",
        leave_requests.LeaveRequestFormView.as_view(),
        name="leave-request-creation",
    ),
    path(
        "leave-requests-info-export/",
        views.leave_requests_export,
        name="leave-requests-info-export",
    ),
    path(
        "create-leave-report/",
        views.create_leave_report,
        name="create-leave-report",
    ),
    path(
        "request-approve/<int:id>/", views.leave_request_approve, name="request-approve"
    ),
    path(
        "request-approve/<int:id>/<int:emp_id>/",
        views.leave_request_approve,
        name="request-approve",
    ),
    path(
        "leave-requests-bulk-approve/",
        views.leave_request_bulk_approve,
        name="leave-requests-bulk-approve",
    ),
    path(
        "leave-requests-bulk-reject/",
        views.leave_bulk_reject,
        name="leave-requests-bulk-reject",
    ),
    path("request-cancel/<int:id>/", views.leave_request_cancel, name="request-cancel"),
    path(
        "request-cancel/<int:id>/<int:emp_id>/",
        views.leave_request_cancel,
        name="request-cancel",
    ),
    # path("request-update/<int:id>", views.leave_request_update, name="request-update"),
    path(
        "request-update/<int:pk>/",
        leave_requests.LeaveRequestFormView.as_view(),
        name="request-update",
    ),
    path("request-delete/<int:id>/", views.leave_request_delete, name="request-delete"),
    # path("user-request/<int:id>", views.user_leave_request, name="user-request"),
    path(
        "user-request/<int:leave>/",
        my_leave_request.MyLeaveRequestSingleForm.as_view(),
        name="user-request",
    ),
    # path("request-filter", views.leave_request_filter, name="request-filter"),
    path("assign/", views.leave_assign, name="assign"),
    # path("assign",assigned_leave.AssignedLeaveFormView.as_view(),name="assign"),
    # path("assign-one/<int:id>", views.leave_assign_one, name="assign-one"),
    path(
        "assign-one/<int:pk>/",
        leave_types.LeaveTypeAssignForm.as_view(),
        name="assign-one",
    ),
    # path("assign-view/", views.leave_assign_view, name="assign-view"),
    # path(
    #     "available-leave-single-view/<int:obj_id>/",
    #     views.available_leave_single_view,
    #     name="available-leave-single-view",
    # ),
    path(
        "available-leave-update/<int:id>/",
        views.available_leave_update,
        name="available-leave-update",
    ),
    # path("available-leave-update/<int:pk>",assigned_leave.AssignedLeaveFormView.as_view(),name="available-leave-update"),
    path(
        "assign-delete/<int:obj_id>/", views.leave_assign_delete, name="assign-delete"
    ),
    path(
        "assigned-leave-bulk-delete/",
        views.leave_assign_bulk_delete,
        name="assigned-leave-bulk-delete",
    ),
    path(
        "assign-leave-type-excel/",
        views.assign_leave_type_excel,
        name="assign-leave-type-excel",
    ),
    path(
        "assign-leave-type-info-import/",
        views.assign_leave_type_import,
        name="assign-leave-type-info-import",
    ),
    path(
        "assigned-leaves-info-export/",
        views.assigned_leaves_export,
        name="assigned-leaves-info-export",
    ),
    # path("assign-filter", views.leave_assign_filter, name="assign-filter"),
    path("get_job_positions/", views.get_job_positions, name="get_job_positions"),
    # path("restrict-view", views.restrict_view, name="restrict-view"),
    # path("restrict-filter", views.restrict_filter, name="restrict-filter"),
    # path("restrict-creation", views.restrict_creation, name="restrict-creation"),
    path(
        "restrict-creation/",
        restricted_days.RestrictedDaysFormView.as_view(),
        name="restrict-creation",
    ),
    # path("restrict-update/<int:id>", views.restrict_update, name="restrict-update"),
    path(
        "restrict-update/<int:pk>/",
        restricted_days.RestrictedDaysFormView.as_view(),
        name="restrict-update",
    ),
    path(
        "get-restrict-job-positions/",
        views.get_job_positions,
        name="get-restrict-job-positions",
    ),
    path("restrict-delete/<int:id>/", views.restrict_delete, name="restrict-delete"),
    path(
        "restrict-days-bulk-delete/",
        views.restrict_days_bulk_delete,
        name="restrict-days-bulk-delete",
    ),
    path(
        "restrict-day-select-filter/",
        views.restrict_day_select_filter,
        name="restrict-day-select-filter",
    ),
    path("restrict-day-select/", views.restrict_day_select, name="restrict-day-select"),
    path("user-leave-filter/", views.user_leave_filter, name="user-leave-filter"),
    # path("user-request-view/", views.user_request_view, name="user-request-view"),
    # path(
    #     "user-request-update/<int:id>",
    #     views.user_request_update,
    #     name="user-request-update",
    # ),
    path(
        "user-request-update/<int:pk>/",
        my_leave_request.MyLeaveRequestForm.as_view(),
        name="user-request-update",
    ),
    path(
        "user-request-delete/<int:id>/",
        views.user_request_delete,
        name="user-request-delete",
    ),
    path(
        "user-request-cancel/<int:id>/",
        views.user_leave_cancel,
        name="user-request-cancel",
    ),
    path("one-request-view/<int:id>/", views.one_request_view, name="one-request-view"),
    # path("user-request-filter", views.user_request_filter, name="user-request-filter"),
    path("user-request-one/<int:id>/", views.user_request_one, name="user-request-one"),
    # path("employee-leave/", views.employee_leave, name="employee-leave"),
    path("overall-leave/", views.overall_leave, name="overall-leave"),
    path(
        "leave-dashboard/",
        RedirectView.as_view(pattern_name="leave-dashboard"),
        name="leave-dashboard-legacy",
    ),
    path(
        "leave-employee-dashboard/",
        views.employee_dashboard,
        name="leave-employee-dashboard",
    ),
    path("available-leaves/", views.available_leave_chart, name="available-leaves"),
    path(
        "dashboard-leave-requests/",
        views.dashboard_leave_request,
        name="dashboard-leave-requests",
    ),
    path(
        "employee-leave-chart/", views.employee_leave_chart, name="employee-leave-chart"
    ),
    path(
        "department-leave-chart/",
        views.department_leave_chart,
        name="department-leave-chart",
    ),
    path("leave-type-chart/", views.leave_type_chart, name="leave-type-chart"),
    path("leave-over-period/", views.leave_over_period, name="leave-over-period"),
    # path(
    #     "leave-request-create", views.leave_request_create, name="leave-request-create"
    # ),
    path(
        "leave-request-create/",
        my_leave_request.MyLeaveRequestForm.as_view(),
        name="leave-request-create",
    ),
    path(
        "employee-leave-details/",
        views.employee_leave_details,
        name="employee-leave-details",
    ),
    # path(
    #     "leave-allocation-request-view/",
    #     views.leave_allocation_request_view,
    #     name="leave-allocation-request-view",
    # ),
    # path(
    #     "leave-allocation-request-create",
    #     views.leave_allocation_request_create,
    #     name="leave-allocation-request-create",
    # ),
    path(
        "leave-allocation-request-create/",
        leave_allocation_request.LeaveAllocationRequestFormView.as_view(),
        name="leave-allocation-request-create",
    ),
    path(
        "leave-allocation-request-bulk-create/",
        leave_allocation_request.LeaveAllocationBulkFormView.as_view(),
        name="leave-allocation-request-bulk-create",
    ),
    # path(
    #     "leave-allocation-request-filter",
    #     views.leave_allocation_request_filter,
    #     name="leave-allocation-request-filter",
    # ),
    path(
        "leave-allocation-request-single-view/<int:req_id>/",
        views.leave_allocation_request_single_view,
        name="leave-allocation-request-single-view",
    ),
    # path(
    #     "leave-allocation-request-update/<int:req_id>",
    #     views.leave_allocation_request_update,
    #     name="leave-allocation-request-update",
    # ),
    path(
        "leave-allocation-request-approve/<int:req_id>/",
        views.leave_allocation_request_approve,
        name="leave-allocation-request-approve",
    ),
    path(
        "leave-allocation-request-reject/<int:req_id>/",
        views.leave_allocation_request_reject,
        name="leave-allocation-request-reject",
    ),
    path(
        "leave-allocation-request-delete/<int:req_id>/",
        views.leave_allocation_request_delete,
        name="leave-allocation-request-delete",
    ),
    # path(
    #     "leave-allocation-request-view/",
    #     views.leave_allocation_request_view,
    #     name="leave-allocation-request-view",
    # ),
    # path(
    #     "leave-allocation-request-filter",
    #     views.leave_allocation_request_filter,
    #     name="leave-allocation-request-filter",
    # ),
    # path(
    #     "leave-allocation-request-update/<int:req_id>",
    #     views.leave_allocation_request_update,
    #     name="leave-allocation-request-update",
    # ),
    path(
        "leave-allocation-request-update/<int:pk>/",
        leave_allocation_request.LeaveAllocationRequestFormView.as_view(),
        name="leave-allocation-request-update",
    ),
    path(
        "leave-allocation-request-approve/<int:req_id>/",
        views.leave_allocation_request_approve,
        name="leave-allocation-request-approve",
    ),
    path(
        "assigned-leave-select/",
        views.assigned_leave_select,
        name="assigned-leave-select",
    ),
    path(
        "assigned-leave-select-filter/",
        views.assigned_leave_select_filter,
        name="assigned-leave-select-filter",
    ),
    path(
        "leave-request-bulk-delete/",
        views.leave_request_bulk_delete,
        name="leave-request-bulk-delete",
    ),
    path(
        "leave-request-select/",
        views.leave_request_select,
        name="leave-request-select",
    ),
    path(
        "leave-request-select-filter/",
        views.leave_request_select_filter,
        name="leave-request-select-filter",
    ),
    path(
        "user-request-bulk-delete/",
        views.user_request_bulk_delete,
        name="user-request-bulk-delete",
    ),
    path(
        "user-request-select/",
        views.user_request_select,
        name="user-request-select",
    ),
    path(
        "user-request-select-filter/",
        views.user_request_select_filter,
        name="user-request-select-filter",
    ),
    path(
        "employee-available-leave-count/",
        views.employee_available_leave_count,
        name="employee-available-leave-count",
    ),
    path(
        "leave-request-add-comment/<int:leave_id>/",
        views.create_leaverequest_comment,
        name="leave-request-add-comment",
    ),
    path(
        "leave-request-view-comment/<int:leave_id>/",
        views.view_leaverequest_comment,
        name="leave-request-view-comment",
    ),
    path(
        "leave-request-delete-comment/<int:comment_id>/",
        views.delete_leaverequest_comment,
        name="leave-request-delete-comment",
    ),
    path(
        "delete-leave-comment-file/",
        views.delete_leave_comment_file,
        name="delete-leave-comment-file",
    ),
    path(
        "allocation-request-add-comment/<int:leave_id>/",
        views.create_allocationrequest_comment,
        name="allocation-request-add-comment",
    ),
    path(
        "allocation-request-view-comment/<int:leave_id>/",
        views.view_allocationrequest_comment,
        name="allocation-request-view-comment",
    ),
    path(
        "allocation-request-delete-comment/<int:comment_id>/",
        views.delete_allocationrequest_comment,
        name="allocation-request-delete-comment",
    ),
    path(
        "delete-allocation-comment-file/",
        views.delete_allocation_comment_file,
        name="delete-allocation-comment-file",
    ),
    path(
        "view-clashes/<int:pk>/",
        leave_requests.LeaveClashListView.as_view(),
        name="view-clashes",
    ),
    # path(
    #     "view-clashes/<int:leave_request_id>/", views.view_clashes, name="view-clashes"
    # ),
    path(
        "leave-rules-view/",
        views.leave_rules_settings_view,
        name="leave-rules-view",
    ),
    path(
        "restrict-leaves-view/",
        views.restrict_leaves_settings_view,
        name="restrict-leaves-view",
    ),
    path(
        "leave-settings-view/",
        settings_tabs.LeaveSettingsView.as_view(),
        name="leave-settings-view",
    ),
    path(
        "leave-settings-tab-view/",
        settings_tabs.LeaveSettingsTabView.as_view(),
        name="leave-settings-tab-view",
    ),
    path(
        "leave-settings-leave-types-tab/",
        settings_tabs.LeaveSettingsLeaveTypesTab.as_view(),
        name="leave-settings-leave-types-tab",
    ),
    path(
        "leave-settings-approvals-tab/",
        settings_tabs.LeaveSettingsApprovalsTab.as_view(),
        name="leave-settings-approvals-tab",
    ),
    path(
        "compensatory-leave-settings-view/",
        views.compensatory_leave_settings_view,
        name="compensatory-leave-settings-view",
    ),
    path(
        "enable-compensatory-leave/",
        views.enable_compensatory_leave,
        name="enable-compensatory-leave",
    ),
    path(
        "employee-past-leave-restriction/",
        views.employee_past_leave_restriction,
        name="employee-past-leave-restriction",
    ),
    # path(
    #     "leave-tab/<int:obj_id>/",
    #     views.employee_view_individual_leave_tab,
    #     name="leave-tab",
    #     kwargs={"model": Employee},
    # ),
    path(
        "leave-tab/<int:pk>/",
        views.employee_view_individual_leave_tab,
        name="leave-tab",
        kwargs={"model": Employee},
    ),
    # path(
    #     "leave-request-and-approve",
    #     views.leave_request_and_approve,
    #     name="leave-request-and-approve",
    # ),
    path(
        "dashboard-on-leave/",
        dashboard.DashboardOnLeave.as_view(),
        name="dashboard-on-leave",
    ),
    path(
        "dashboard-total-leave-request/",
        dashboard.DashboardTotalLeaveRequest.as_view(),
        name="dashboard-total-leave-request",
    ),
    path(
        "leave-request-and-approve/",
        dashboard.LeaveRequestsToApprove.as_view(),
        name="leave-request-and-approve",
    ),
    # path(
    #     "leave-allocation-approve",
    #     views.leave_allocation_approve,
    #     name="leave-allocation-approve",
    # ),
    path(
        "leave-allocation-approve/",
        dashboard.LeaveAllocationRequestToApprove.as_view(),
        name="leave-allocation-approve",
    ),
    path(
        "leave-allocation-request-view/",
        leave_allocation_request.LeaveAllocationRequestView.as_view(),
        name="leave-allocation-request-view",
    ),
    path(
        "list-leave-allocation-request/",
        leave_allocation_request.LeaveAllocationRequestList.as_view(),
        name="list-leave-allocation-request",
    ),
    path(
        "leave-allocation-request-filter/",
        leave_allocation_request.LeaveAllocationRequestTab.as_view(),
        name="leave-allocation-request-filter",
    ),
    path(
        "my-leave-allocation-request-tab/",
        leave_allocation_request.MyLeaveAllocationRequest.as_view(),
        name="my-leave-allocation-request-tab",
    ),
    path(
        "leave-allocation-requests-tab-view/",
        leave_allocation_request.LeaveAllocationRequests.as_view(),
        name="leave-allocation-requests-tab-view",
    ),
    path(
        "my-leave-allocation-nav/",
        leave_allocation_request.MyLeaveAllocationNav.as_view(),
        name="my-leave-allocation-nav",
    ),
    path(
        "leave-allocation-requests-nav/",
        leave_allocation_request.LeaveAllocationRequestsNav.as_view(),
        name="leave-allocation-requests-nav",
    ),
    path(
        "my-leave-allocation-tab-shell/",
        leave_allocation_request.MyLeaveAllocationTabShell.as_view(),
        name="my-leave-allocation-tab-shell",
    ),
    path(
        "leave-allocation-requests-tab-shell/",
        leave_allocation_request.LeaveAllocationRequestsTabShell.as_view(),
        name="leave-allocation-requests-tab-shell",
    ),
    path(
        "detail-leave-allocation-request/<int:pk>/",
        leave_allocation_request.LeaveAllocationRequestDetailView.as_view(),
        name="detail-leave-allocation-request",
    ),
    path(
        "leave-allocation-request-detail-view/<int:pk>/",
        leave_allocation_request.LeaveAllocationsRequestsTabDetailView.as_view(),
        name="leave-allocation-request-detail-view",
    ),
    path(
        "restrict-view/",
        restricted_days.RestrictedDaysView.as_view(),
        name="restrict-view",
    ),
    path(
        "restrict-filter/",
        restricted_days.RestrictedDaysList.as_view(),
        name="restrict-filter",
    ),
    path(
        "nav-restricted-days/",
        restricted_days.RestrictedDaysNav.as_view(),
        name="nav-restricted-days",
    ),
    path(
        "restricted-days-detail-view/<int:pk>/",
        restricted_days.RestrictedDaysDetailView.as_view(),
        name="restricted-days-detail-view",
    ),
    path(
        "cut-penalty/<int:instance_id>/",
        views.cut_available_leave,
        name="leave-cut-penalty",
    ),
    path(
        "duplicate-restrict-leave/<int:obj_id>/",
        object_duplicate,
        name="duplicate-restrict-leave",
        kwargs={
            "model": models.RestrictLeave,
            "form": RestrictLeaveForm,
            "template": "leave/restrict/restrict_form.html",
        },
    ),
    # ── Leave Modern Dashboard ───────────────────────────────────────────────
    path(
        "dashboard/",
        leave_dashboard.leave_dashboard_view,
        name="leave-dashboard",
    ),
    path(
        "dashboard/api/kpi/",
        leave_dashboard.leave_kpi_data,
        name="leave-dashboard-kpi",
    ),
    path(
        "dashboard/api/monthly-trend/",
        leave_dashboard.leave_monthly_trend,
        name="leave-dashboard-monthly-trend",
    ),
    path(
        "dashboard/api/type-distribution/",
        leave_dashboard.leave_type_distribution,
        name="leave-dashboard-type-dist",
    ),
    path(
        "dashboard/api/department/",
        leave_dashboard.leave_department_breakdown,
        name="leave-dashboard-dept",
    ),
    path(
        "dashboard/api/utilization/",
        leave_dashboard.leave_utilization_rate,
        name="leave-dashboard-utilization",
    ),
    path(
        "dashboard/api/paid-unpaid/",
        leave_dashboard.leave_paid_unpaid_split,
        name="leave-dashboard-paid-unpaid",
    ),
    path(
        "dashboard/api/top-takers/",
        leave_dashboard.leave_top_takers,
        name="leave-dashboard-top-takers",
    ),
    path(
        "dashboard/api/on-leave/",
        leave_dashboard.leave_on_leave_today,
        name="leave-dashboard-on-leave",
    ),
    path(
        "dashboard/api/holidays/",
        leave_dashboard.leave_upcoming_holidays,
        name="leave-dashboard-holidays",
    ),
    path(
        "dashboard/api/weekly-pattern/",
        leave_dashboard.leave_weekly_pattern,
        name="leave-dashboard-weekly-pattern",
    ),
    path(
        "dashboard/api/upcoming/",
        leave_dashboard.leave_upcoming,
        name="leave-dashboard-upcoming",
    ),
    path(
        "employee-dashboard/api/kpi/",
        leave_dashboard.employee_kpi_data,
        name="leave-employee-dashboard-kpi",
    ),
    path(
        "employee-dashboard/api/balance/",
        leave_dashboard.employee_leave_balance,
        name="employee-dashboard-balance",
    ),
    path(
        "employee-dashboard/api/trend/",
        leave_dashboard.employee_monthly_trend,
        name="employee-dashboard-trend",
    ),
    path(
        "employee-dashboard/api/upcoming/",
        leave_dashboard.employee_upcoming_leaves,
        name="employee-dashboard-upcoming",
    ),
    path(
        "employee-dashboard/api/history/",
        leave_dashboard.employee_leave_history,
        name="employee-dashboard-history",
    ),
]

if apps.is_installed("recruitment"):
    urlpatterns.extend(
        [
            path(
                "check-interview-conflicts/",
                views.check_interview_conflicts,
                name="check-interview-conflicts",
            ),
        ]
    )

if apps.is_installed("attendance"):

    urlpatterns.extend(
        [
            path(
                "view-compensatory-leave/",
                compensatory_leave_request.CompensatoryLeaveView.as_view(),
                name="view-compensatory-leave",
            ),
            path(
                "compensatory-list/",
                compensatory_leave_request.CompensatoryListView.as_view(),
                name="compensatory-list",
            ),
            path(
                "compensatory-nav/",
                compensatory_leave_request.CompensatoryLeaveNav.as_view(),
                name="compensatory-nav",
            ),
            path(
                "my-compensatory-nav/",
                compensatory_leave_request.MyCompensatoryLeaveNav.as_view(),
                name="my-compensatory-nav",
            ),
            path(
                "compensatory-tab-view/",
                compensatory_leave_request.CompensatoryLeaveTabView.as_view(),
                name="compensatory-tab-view",
            ),
            path(
                "my-compensatory-tab/",
                compensatory_leave_request.MyCompensatoryLeaveTab.as_view(),
                name="my-compensatory-tab",
            ),
            path(
                "my-compensatory-tab-shell/",
                compensatory_leave_request.MyCompensatoryTabShell.as_view(),
                name="my-compensatory-tab-shell",
            ),
            path(
                "compensatory-tab/",
                compensatory_leave_request.CompensatoryLeaveTab.as_view(),
                name="compensatory-tab",
            ),
            path(
                "compensatory-tab-shell/",
                compensatory_leave_request.CompensatoryTabShell.as_view(),
                name="compensatory-tab-shell",
            ),
            path(
                "my-compensatory-detail-view/<int:pk>/",
                compensatory_leave_request.MyCompensatoryDetailView.as_view(),
                name="my-compensatory-detail-view",
            ),
            path(
                "compensatory-detail-view/<int:pk>/",
                compensatory_leave_request.CompensatoryTabDetailView.as_view(),
                name="compensatory-detail-view",
            ),
            path(
                "get-leave-attendance-dates/",
                views.get_leave_attendance_dates,
                name="get-leave-attendance-dates",
            ),
            # path(
            #     "view-compensatory-leave",
            #     views.view_compensatory_leave,
            #     name="view-compensatory-leave",
            # ),
            path(
                "filter-compensatory-leave/",
                views.filter_compensatory_leave,
                name="filter-compensatory-leave",
            ),
            path(
                "create-compensatory-leave/",
                compensatory_leave_request.CompensatoryForm.as_view(),
                name="create-compensatory-leave",
            ),
            # path(
            #     "create-compensatory-leave",
            #     views.create_compensatory_leave,
            #     name="create-compensatory-leave",
            # ),
            path(
                "update-compensatory-leave/<int:pk>/",
                compensatory_leave_request.CompensatoryForm.as_view(),
                name="update-compensatory-leave",
            ),
            # path(
            #     "update-compensatory-leave/<int:comp_id>",
            #     views.create_compensatory_leave,
            #     name="update-compensatory-leave",
            # ),
            path(
                "delete-compensatory-leave/<int:comp_id>/",
                views.delete_compensatory_leave,
                name="delete-compensatory-leave",
            ),
            path(
                "approve-compensatory-leave/<int:comp_id>/",
                views.approve_compensatory_leave,
                name="approve-compensatory-leave",
            ),
            path(
                "reject-compensatory-leave/<int:comp_id>/",
                views.reject_compensatory_leave,
                name="reject-compensatory-leave",
            ),
            path(
                "compensatory-leave-individual-view/<int:comp_leave_id>/",
                views.compensatory_leave_individual_view,
                name="compensatory-leave-individual-view",
            ),
            path(
                "view-compensatory-leave-comment/<int:comp_leave_id>/",
                views.view_compensatory_leave_comment,
                name="view-compensatory-leave-comment",
            ),
            path(
                "create-compensatory-leave-comment/<int:comp_leave_id>/",
                views.create_compensatory_leave_comment,
                name="create-compensatory-leave-comment",
            ),
            path(
                "compensatory-request-delete-comment/<int:comment_id>/",
                views.delete_leaverequest_compensatory_comment,
                name="compensatory-request-delete-comment",
            ),
            path(
                "delete-compensatory-comment-file/",
                views.delete_comment_compensatory_file,
                name="delete-compensatory-comment-file",
            ),
        ]
    )
