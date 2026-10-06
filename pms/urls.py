from django.urls import path
from django.views.generic import RedirectView

from base.views import object_delete
from horilla_audit.methods import history_tracking
from pms import cbvs
from pms import dashboard as pms_dashboard
from pms.cbv import (
    dashboard,
    employee_objectives,
    feedback,
    key_result,
    meetings,
    objectives,
    period,
    question_template,
    settings_tabs,
)

from . import models, views

urlpatterns = [
    path(
        "individual-performance-tab-list/<int:pk>/",
        feedback.PerformanceTab.as_view(),
        name="individual-performance-tab-list",
    ),
    path("feedback-view/", feedback.FeedbackViewPage.as_view(), name="feedback-view"),
    path(
        "feedback-list-page/",
        feedback.FeedbackListView.as_view(),
        name="feedback-list-page",
    ),
    path(
        "feedback-generic-tab/",
        feedback.FeedbackGenericTabView.as_view(),
        name="feedback-generic-tab",
    ),
    path(
        "self-feedback-tab/",
        feedback.SelfFeedbacktab.as_view(),
        name="self-feedback-tab",
    ),
    path(
        "requested-feedback-tab/",
        feedback.RequestedFeedbackTab.as_view(),
        name="requested-feedback-tab",
    ),
    path(
        "all-feedback-tab/", feedback.AllFeedbackTab.as_view(), name="all-feedback-tab"
    ),
    path(
        "anonymous-feedback-tab/",
        feedback.AnonymousFeedbackTab.as_view(),
        name="anonymous-feedback-tab",
    ),
    path(
        "self-feedback-nav/",
        feedback.SelfFeedbackNav.as_view(),
        name="self-feedback-nav",
    ),
    path(
        "requested-feedback-nav/",
        feedback.RequestedFeedbackNav.as_view(),
        name="requested-feedback-nav",
    ),
    path(
        "all-feedback-nav/",
        feedback.AllFeedbackNav.as_view(),
        name="all-feedback-nav",
    ),
    path(
        "anonymous-feedback-nav/",
        feedback.AnonymousFeedbackNav.as_view(),
        name="anonymous-feedback-nav",
    ),
    path(
        "self-feedback-tab-shell/",
        feedback.SelfFeedbackTabShell.as_view(),
        name="self-feedback-tab-shell",
    ),
    path(
        "requested-feedback-tab-shell/",
        feedback.RequestedFeedbackTabShell.as_view(),
        name="requested-feedback-tab-shell",
    ),
    path(
        "all-feedback-tab-shell/",
        feedback.AllFeedbackTabShell.as_view(),
        name="all-feedback-tab-shell",
    ),
    path(
        "anonymous-feedback-tab-shell/",
        feedback.AnonymousFeedbackTabShell.as_view(),
        name="anonymous-feedback-tab-shell",
    ),
    # objectives
    # path("objective-list-view/", views.objective_list_view, name="objective-list-view"),
    # path("objective-creation/", views.objective_creation, name="objective-creation"),
    path(
        "objective-creation/",
        objectives.CreateObjectiveFormView.as_view(),
        name="objective-creation",
    ),
    path(
        "objective-template-creation/",
        objectives.CreateTemplateObjectiveFormView.as_view(),
        name="objective-template-creation",
    ),
    path(
        "objective-update/<int:pk>/",
        objectives.CreateObjectiveFormView.as_view(),
        name="objective-update",
    ),
    # path(
    #     "objective-update/<int:obj_id>", views.objective_update, name="objective-update"
    # ),
    # path("add-assignees/<int:obj_id>", views.add_assignees, name="add-assignees"),
    path(
        "add-assignees/<int:pk>/",
        objectives.AddAssigneesFormView.as_view(),
        name="add-assignees",
    ),
    # key results
    path(
        "view-key-result/",
        key_result.KeyResultViewPage.as_view(),
        name="view-key-result",
    ),
    path(
        "filter-key-result/",
        key_result.KeyResultsListView.as_view(),
        name="filter-key-result",
    ),
    path(
        "key-result-detail-view/<int:pk>/",
        key_result.KeyResultsDetailedView.as_view(),
        name="key-result-detail-view",
    ),
    path(
        "key-result-navbar/",
        key_result.KeyResultNavView.as_view(),
        name="key-result-navbar",
    ),
    path(
        "key-result-card-view/",
        key_result.KeyResultCardView.as_view(),
        name="key-result-card-view",
    ),
    path(
        "create-key-result/",
        key_result.KeyResultFormView.as_view(),
        name="create-key-result",
    ),
    path(
        "update-key-result/<int:pk>/",
        key_result.KeyResultFormView.as_view(),
        name="update-key-result",
    ),
    path(
        "key-result-delete/<int:key_id>/",
        key_result.DeleteKeyResults.as_view(),
        name="key-result-delete",
    ),
    path(
        "archive-key-result/<int:pk>/",
        views.archive_key_result,
        name="archive-key-result",
    ),
    path(
        "ekr-history/<int:pk>/",
        key_result.EKRHistory.as_view(),
        name="ekr-history",
    ),
    # path("view-key-result/", views.view_key_result, name="view-key-result"),
    # path("filter-key-result/", views.filter_key_result, name="filter-key-result"),
    # path("create-key-result/", views.kr_create_or_update, name="create-key-result"),
    # path(
    #     "update-key-result/<int:kr_id>",
    #     views.kr_create_or_update,
    #     name="update-key-result",
    # ),
    path(
        "delete-key-result/<int:obj_id>/",
        object_delete,
        name="delete-key-result",
        kwargs={"model": models.KeyResult, "redirect_path": "/pms/filter-key-result/"},
    ),
    path("key-result-creation/", views.key_result_create, name="key-result-creation"),
    path(
        "key-reult-remove/<int:obj_id>/<int:kr_id>/",
        views.key_result_remove,
        name="key-result-remove",
    ),
    path(
        "objective-list-search/",
        views.objective_list_search,
        name="objective-list-search",
    ),
    path(
        "objective-dashboard-view/",
        views.objective_dashboard_view,
        name="objective-dashboard-view",
    ),
    path(
        "objective-delete/<int:obj_id>/",
        views.objective_delete,
        name="objective-delete",
    ),
    path(
        "objective-archive/<int:id>/", views.objective_archive, name="objective-archive"
    ),
    path(
        "objective-detailed-view/<int:obj_id>/",
        views.objective_detailed_view,
        name="objective-detailed-view",
        kwargs={"model": models.EmployeeObjective},
    ),
    path(
        "objective-detailed-view-objective-status/<int:id>/",
        views.objective_detailed_view_objective_status,
        name="objective-detailed-view-objective-status",
    ),
    path(
        "objective-detailed-view-key-result-status/<int:obj_id>/<int:kr_id>/",
        views.objective_detailed_view_key_result_status,
        name="objective-detailed-view-key-result-status",
    ),
    path(
        "objective-detailed-view-current-value/<int:kr_id>/",
        views.objective_detailed_view_current_value,
        name="objective-detailed-view-current-value",
    ),
    path(
        "objective-detailed-view-activity/<int:id>/",
        views.objective_detailed_view_activity,
        name="objective-detailed-view-activity",
    ),
    path(
        "emp-objective-search/<int:obj_id>/",
        views.emp_objective_search,
        name="emp-objective-search",
    ),
    path(
        "objective-manager-remove/<int:obj_id>/<int:manager_id>/",
        views.objective_manager_remove,
        name="objective-manager-remove",
    ),
    path(
        "assignees-remove/<int:obj_id>/<int:emp_id>/",
        views.assignees_remove,
        name="assignees-remove",
    ),
    path(
        "objective-detailed-view-comment/<int:id>/",
        views.objective_detailed_view_comment,
        name="objective-detailed-view-comment",
    ),
    path(
        "kr-table-view/<int:emp_objective_id>/",
        objectives.EmployeeObjectiveKeyResultDetailListView.as_view(),
        name="kr-table-view",
    ),
    # path(
    #     "kr-table-view/<int:emp_objective_id>",
    #     views.kr_table_view,
    #     name="kr-table-view",
    # ),
    # path(
    #     "key-result-view",
    #     views.key_result_view,
    #     name="key-result-view",
    # ),
    path(
        "key-result-view/",
        dashboard.KeyResultStatus.as_view(),
        name="key-result-view",
    ),
    path(
        "key-result-creation/<str:obj_id>/<str:obj_type>/",
        views.key_result_creation,
        name="key-result-creation",
    ),
    path(
        "key-result-creation-htmx/<int:id>/",
        views.key_result_creation_htmx,
        name="key-result-creation-htmx",
    ),
    path(
        "key-result-update/<int:id>/", views.key_result_update, name="key-result-update"
    ),
    # path("feedback-view/", views.feedback_list_view, name="feedback-view"),
    path(
        "feedback-list-search/", views.feedback_list_search, name="feedback-list-search"
    ),
    path("feedback-creation/", views.feedback_creation, name="feedback-creation"),
    # path(
    #     "feedback-creation-ajax",
    #     views.feedback_creation_ajax,
    #     name="feedback-creation-ajax",
    # ),
    path(
        "feedback-update/<int:pk>/",
        feedback.FeedbackUpdateFormView.as_view(),
        name="feedback-update",
    ),
    # path("feedback-update/<int:id>", views.feedback_update, name="feedback-update"),
    path(
        "bulk-feedback-create/",
        cbvs.BulkFeedbackFormView.as_view(),
        name="bulk-feedback-create",
    ),
    path("feedback-update/<int:id>/", views.feedback_update, name="feedback-update"),
    path("feedback-delete/<int:id>/", views.feedback_delete, name="feedback-delete"),
    path("feedback-archive/<int:id>/", views.feedback_archive, name="feedback-archive"),
    path("get-collegues/", views.get_collegues, name="get-collegues"),
    path(
        "share-feedback/<int:pk>/",
        cbvs.FeedbackEmployeeFormView.as_view(),
        name="share-feedback",
    ),
    path(
        "feedback-answer-get/<int:id>/",
        views.feedback_answer_get,
        name="feedback-answer-get",
        kwargs={"model": models.Feedback},
    ),
    path(
        "feedback-answer-post/<int:id>/",
        views.feedback_answer_post,
        name="feedback-answer-post",
    ),
    path(
        "feedback-answer-view/<int:id>/",
        views.feedback_answer_view,
        name="feedback-answer-view",
        kwargs={"model": models.Feedback},
    ),
    path(
        "feedback-detailed-view/<int:id>/",
        views.feedback_detailed_view,
        name="feedback-detailed-view",
        kwargs={"model": models.Feedback},
    ),
    path(
        "feedback-detailed-view-answer/<int:id>/<int:emp_id>/",
        views.feedback_detailed_view_answer,
        name="feedback-detailed-view-answer",
    ),
    path(
        "feedback-detailed-view-status/<int:id>/",
        views.feedback_detailed_view_status,
        name="feedback-detailed-view-status",
    ),
    path(
        "get-feedback-overview/<int:obj_id>/",
        views.get_feedback_overview,
        name="get-feedback-overview",
    ),
    path("feedback-status/", views.feedback_status, name="feedback-status"),
    path(
        "question-creation/<int:id>/", views.question_creation, name="question-creation"
    ),
    path("question-view/<int:id>/", views.question_view, name="question-view"),
    path(
        "question-update/<int:temp_id>/<int:q_id>/",
        views.question_update,
        name="question-update",
    ),
    path("question-delete/<int:id>/", views.question_delete, name="question-delete"),
    # path(
    #     "question-template-creation",
    #     views.question_template_creation,
    #     name="question-template-creation",
    # ),
    path(
        "question-template-creation/",
        question_template.QuestionTemplateFormView.as_view(),
        name="question-template-creation",
    ),
    path(
        "question-template-detailed-view/<int:template_id>/",
        views.question_template_detailed_view,
        name="question-template-detailed-view",
        kwargs={"model": models.QuestionTemplate},
    ),
    path(
        "question-template-related-view/<int:template_id>/",
        views.question_template_related_view,
        name="question-template-related-view",
    ),
    # path(
    #     "question-template-update/<int:template_id>/",
    #     views.question_template_update,
    #     name="question-template-update",
    # ),
    path(
        "question-template-update/<int:pk>/",
        question_template.QuestionTemplateFormView.as_view(),
        name="question-template-update",
    ),
    path(
        "question-template-delete/<int:template_id>/",
        views.question_template_delete,
        name="question-template-delete",
    ),
    # path("period-create", views.period_create, name="period-create"),
    path("period-create/", period.PeriodFormView.as_view(), name="period-create"),
    # path("period-hx-view", views.period_hx_view, name="period-hx-view"),
    path("period-delete/<int:period_id>/", views.period_delete, name="period-delete"),
    # path("period-update/<int:period_id>", views.period_update, name="period-update"),
    path(
        "period-update/<int:pk>/", period.PeriodFormView.as_view(), name="period-update"
    ),
    path("period-change/", views.period_change, name="period-change"),
    path(
        "dashboard-view/",
        RedirectView.as_view(pattern_name="dashboard-view"),
        name="dashboard-view-legacy",
    ),
    path(
        "dashboard-risk-objectives/",
        dashboard.DasboardObjectivesRisk.as_view(),
        name="dashboard-risk-objectives",
    ),
    path(
        "dashboard-objective-status/",
        views.dashboard_objective_status,
        name="dashboard-objective-status",
    ),
    path(
        "dashbord-key-result-status/",
        views.dashboard_key_result_status,
        name="dashbord-key-result-status",
    ),
    path(
        "dashboard-feedback-status/",
        views.dashboard_feedback_status,
        name="dashboard-feedback-status",
    ),
    path(
        "create-period/",
        views.create_period,
        name="create-period",
    ),
    path(
        "objective-bulk-archive/",
        views.objective_bulk_archive,
        name="objective-bulk-archive",
    ),
    path(
        "objective-bulk-delete/",
        views.objective_bulk_delete,
        name="objective-bulk-delete",
    ),
    path(
        "feedback-bulk-archive/",
        views.feedback_bulk_archive,
        name="feedback-bulk-archive",
    ),
    path(
        "feedback-bulk-delete/",
        views.feedback_bulk_delete,
        name="feedback-bulk-delete",
    ),
    path(
        "objective-select/",
        views.objective_select,
        name="objective-select",
    ),
    path(
        "objective-select-filter/",
        views.objective_select_filter,
        name="objective-select-filter",
    ),
    # path(
    #     "add-anonymous-feedback",
    #     views.anonymous_feedback_add,
    #     name="add-anonymous-feedback",
    # ),
    path(
        "add-anonymous-feedback/",
        feedback.AddAnonymousFeedbackForm.as_view(),
        name="add-anonymous-feedback",
    ),
    # path(
    #     "edit-anonymous-feedback/<int:obj_id>/",
    #     views.edit_anonymous_feedback,
    #     name="edit-anonymous-feedback",
    # ),
    path(
        "edit-anonymous-feedback/<int:pk>/",
        feedback.AddAnonymousFeedbackForm.as_view(),
        name="edit-anonymous-feedback",
    ),
    path(
        "archive-anonymous-feedback/<int:obj_id>/",
        views.archive_anonymous_feedback,
        name="archive-anonymous-feedback",
    ),
    path(
        "delete-anonymous-feedback/<int:obj_id>/",
        views.delete_anonymous_feedback,
        name="delete-anonymous-feedback",
    ),
    # path(
    #     "single-anonymous-feedback-view/<int:obj_id>/",
    #     views.view_single_anonymous_feedback,
    #     name="single-anonymous-feedback-view",
    # ),
    path(
        "single-anonymous-feedback-view/<int:pk>/",
        feedback.AnounyFeedbackDetailView.as_view(),
        name="single-anonymous-feedback-view",
    ),
    # path(
    #     "view-employee-objective/<int:emp_obj_id>/",
    #     views.view_employee_objective,
    #     name="view-employee-objective",
    # ),
    path(
        "view-employee-objective/<int:pk>/",
        objectives.EmployeeObjectiveDetailView.as_view(),
        name="view-employee-objective",
    ),
    # path(
    #     "create-employee-objective/",
    #     views.create_employee_objective,
    #     name="create-employee-objective",
    # ),
    path(
        "create-employee-objective/",
        objectives.CreateEmployeeObjectiveForm.as_view(),
        name="create-employee-objective",
    ),
    path(
        "update-employee-objective/<int:pk>/",
        objectives.CreateEmployeeObjectiveForm.as_view(),
        name="update-employee-objective",
    ),
    path(
        "get-objective-keyresult/",
        views.get_objective_keyresults,
        name="get-objective-keyresult",
    ),
    # path(
    #     "update-employee-objective/<int:emp_obj_id>/",
    #     views.update_employee_objective,
    #     name="update-employee-objective",
    # ),
    path(
        "archive-employee-objective/<int:emp_obj_id>/",
        views.archive_employee_objective,
        name="archive-employee-objective",
    ),
    path(
        "delete-employee-objective/<int:emp_obj_id>/",
        views.delete_employee_objective,
        name="delete-employee-objective",
    ),
    path(
        "change-employee-objective-status/",
        views.change_employee_objective_status,
        name="change-employee-objective-status",
    ),
    # path(
    #     "employee-key-result-creation/<int:emp_obj_id>",
    #     views.employee_keyresult_creation,
    #     name="employee-key-result-creation",
    # ),
    path(
        "employee-key-result-creation/<int:emp_obj_id>/",
        objectives.CreateEmployeeKeyResultFormView.as_view(),
        name="employee-key-result-creation",
    ),
    # path(
    #     "employee-key-result-update/<int:kr_id>",
    #     views.employee_keyresult_update,
    #     name="employee-key-result-update",
    # ),
    path(
        "employee-key-result-update/<int:pk>/",
        objectives.CreateEmployeeKeyResultFormView.as_view(),
        name="employee-key-result-update",
    ),
    path(
        "delete-employee-keyresult/<int:kr_id>/",
        views.delete_employee_keyresult,
        name="delete-employee-keyresult",
    ),
    path(
        "employee-keyresult-update-status/<int:kr_id>/",
        views.employee_keyresult_update_status,
        name="employee-keyresult-update-status",
    ),
    path(
        "key-result-current-value-update/",
        views.key_result_current_value_update,
        name="key-result-current-value-update",
    ),
    # path(
    #     "view-meetings",
    #     views.view_meetings,
    #     name="view-meetings",
    # ),
    # path(
    #     "create-meeting",
    #     views.create_meetings,
    #     name="create-meeting",
    # ),
    path("get-keyresult-data/", views.get_keyresult_data, name="get-keyresult-data"),
    path(
        "create-meeting/",
        meetings.MeetingsFormView.as_view(),
        name="create-meeting",
    ),
    path(
        "update-meeting/<int:pk>/",
        meetings.MeetingsFormView.as_view(),
        name="update-meeting",
    ),
    path(
        "meetings-delete/<int:obj_id>/",
        object_delete,
        name="meetings-delete",
        kwargs={"model": models.Meetings, "HttpResponse": True},
    ),
    path(
        "archive-meeting/<int:obj_id>/",
        views.archive_meetings,
        name="archive-meeting",
    ),
    path(
        "filter-meeting/",
        views.filter_meetings,
        name="filter-meeting",
    ),
    # path(
    #     "add-response/<int:id>/",
    #     views.add_response,
    #     name="add-response",
    # ),
    path(
        "add-response/<int:id>/",
        meetings.MeetingResponseFormView.as_view(),
        name="add-response",
    ),
    path(
        "meeting-answer-get/<int:id>/",
        views.meeting_answer_get,
        name="meeting-answer-get",
    ),
    path(
        "meeting-answer-post/<int:id>/",
        views.meeting_answer_post,
        name="meeting-answer-post",
    ),
    path(
        "meeting-answer-view/<int:id>/<int:emp_id>/",
        views.meeting_answer_view,
        name="meeting-answer-view",
    ),
    path(
        "meeting-question-template-view/<int:meet_id>/",
        views.meeting_question_template_view,
        name="meeting-question-template-view",
    ),
    path(
        "meeting-single-view/<int:id>/",
        views.meeting_single_view,
        name="meeting-single-view",
    ),
    path(
        "meeting-manager-remove/<int:meet_id>/<int:manager_id>/",
        views.meeting_manager_remove,
        name="meeting-manager-remove",
    ),
    path(
        "meeting-employee-remove/<int:meet_id>/<int:employee_id>/",
        views.meeting_employee_remove,
        name="meeting-employee-remove",
    ),
    path(
        "objective-list-view/",
        objectives.ObjectivesView.as_view(),
        name="objective-list-view",
    ),
    path(
        "objective-template-list-view/",
        objectives.ObjectiveTemplateView.as_view(),
        name="objective-template-list-view",
    ),
    path(
        "list-objectives-view/",
        objectives.ObjectivesList.as_view(),
        name="list-objectives-view",
    ),
    path(
        "tab-objectives-view/",
        objectives.ObjectivesTab.as_view(),
        name="tab-objectives-view",
    ),
    path(
        "nav-objective-templates-view/",
        objectives.ObjectiveTemplateNav.as_view(),
        name="nav-objective-templates-view",
    ),
    path(
        "my-objectives-view-tab/",
        objectives.MyObjectives.as_view(),
        name="my-objectives-view-tab",
    ),
    path(
        "all-objectives-view-tab/",
        objectives.AllObjectives.as_view(),
        name="all-objectives-view-tab",
    ),
    path(
        "my-objectives-nav/",
        objectives.MyObjectivesNav.as_view(),
        name="my-objectives-nav",
    ),
    path(
        "all-objectives-nav/",
        objectives.AllObjectivesNav.as_view(),
        name="all-objectives-nav",
    ),
    path(
        "my-objectives-tab-shell/",
        objectives.MyObjectivesTabShell.as_view(),
        name="my-objectives-tab-shell",
    ),
    path(
        "all-objectives-tab-shell/",
        objectives.AllObjectivesTabShell.as_view(),
        name="all-objectives-tab-shell",
    ),
    path(
        "list-objective-templates-view/",
        objectives.ObjectiveTemplateList.as_view(),
        name="list-objective-templates-view",
    ),
    path(
        "employee-objective-list-view/",
        employee_objectives.EmployeeObjectivesPage.as_view(),
        name="employee-objective-list-view",
    ),
    path(
        "employee-objectives-nav/",
        employee_objectives.EmployeeObjectivesNav.as_view(),
        name="employee-objectives-nav",
    ),
    path(
        "employee-objectives-list/",
        employee_objectives.EmployeeObjectivesList.as_view(),
        name="employee-objectives-list",
    ),
    path(
        "employee-key-result-list-view/",
        employee_objectives.EmployeeKeyResultsPage.as_view(),
        name="employee-key-result-list-view",
    ),
    path(
        "employee-key-results-nav/",
        employee_objectives.EmployeeKeyResultsNav.as_view(),
        name="employee-key-results-nav",
    ),
    path(
        "employee-key-results-list/",
        employee_objectives.EmployeeKeyResultsList.as_view(),
        name="employee-key-results-list",
    ),
    path("view-meetings/", meetings.MeetingsView.as_view(), name="view-meetings"),
    path("meetings-list/", meetings.MeetingsList.as_view(), name="meetings-list"),
    path("meetings-nav/", meetings.MeetingsNav.as_view(), name="meetings-nav"),
    path(
        "meetings-detail-view/<int:pk>/",
        meetings.MeetingsDetailedView.as_view(),
        name="meetings-detail-view",
    ),
    path(
        "question-template-view/",
        question_template.QuestionTemplateView.as_view(),
        name="question-template-view",
    ),
    path(
        "question-template-hx-view/",
        question_template.QuestionTemplateList.as_view(),
        name="question-template-hx-view",
    ),
    path(
        "nav-question-template/",
        question_template.QuestionTemplateNav.as_view(),
        name="nav-question-template",
    ),
    path(
        "period-view/",
        period.PeriodView.as_view(),
        name="period-view",
    ),
    path(
        "period-hx-view/",
        period.PeriodList.as_view(),
        name="period-hx-view",
    ),
    path(
        "nav-period/",
        period.PeriodNav.as_view(),
        name="nav-period",
    ),
    path(
        "period-detail-view/<int:pk>/",
        period.PeriodDetailView.as_view(),
        name="period-detail-view",
    ),
    path("performance-tab/<int:pk>/", views.performance_tab, name="performance-tab"),
    # path(
    #     "dashboard-feedback-answer",
    #     views.dashboard_feedback_answer,
    #     name="dashboard-feedback-answer",
    # ),
    path(
        "dashboard-feedback-answer/",
        dashboard.DashboardFeedbackView.as_view(),
        name="dashboard-feedback-answer",
    ),
    # ===========bonus point setting============
    path(
        "bonus-point-setting/",
        cbvs.BonusPointSettingSectionView.as_view(),
        name="bonus-point-setting",
    ),
    path(
        "performance-settings-view/",
        settings_tabs.PerformanceSettingsView.as_view(),
        name="performance-settings-view",
    ),
    path(
        "performance-settings-tab-view/",
        settings_tabs.PerformanceSettingsTabView.as_view(),
        name="performance-settings-tab-view",
    ),
    path(
        "performance-settings-bonus-point-tab/",
        settings_tabs.PerformanceSettingsBonusPointTab.as_view(),
        name="performance-settings-bonus-point-tab",
    ),
    path(
        "performance-settings-question-template-tab/",
        settings_tabs.PerformanceSettingsQuestionTemplateTab.as_view(),
        name="performance-settings-question-template-tab",
    ),
    path(
        "performance-settings-question-template-nav/",
        settings_tabs.PerformanceSettingsQuestionTemplateNav.as_view(),
        name="performance-settings-question-template-nav",
    ),
    path(
        "performance-settings-question-template-list/",
        settings_tabs.PerformanceSettingsQuestionTemplateList.as_view(),
        name="performance-settings-question-template-list",
    ),
    path(
        "performance-settings-period-tab/",
        settings_tabs.PerformanceSettingsPeriodTab.as_view(),
        name="performance-settings-period-tab",
    ),
    path(
        "performance-settings-period-nav/",
        settings_tabs.PerformanceSettingsPeriodNav.as_view(),
        name="performance-settings-period-nav",
    ),
    path(
        "performance-settings-period-list/",
        settings_tabs.PerformanceSettingsPeriodList.as_view(),
        name="performance-settings-period-list",
    ),
    path(
        "bonus-point-setting-nav/",
        cbvs.BonusPointSettingNavView.as_view(),
        name="bonus-point-setting-nav",
    ),
    path(
        "create-bonus-point-setting/",
        cbvs.BonusPointSettingFormView.as_view(),
        name="create-bonus-point-setting",
    ),
    path(
        "update-bonus-point-setting/<int:pk>/",
        cbvs.BonusPointSettingFormView.as_view(),
        name="update-bonus-point-setting",
    ),
    path(
        "delete-bonus-point-setting/<int:pk>/",
        views.delete_bonus_point_setting,
        name="delete-bonus-point-setting",
    ),
    path(
        "bonus-point-setting-list-view/",
        cbvs.BonusPointSettingListView.as_view(),
        name="bonus-point-setting-list-view",
    ),
    path(
        "bonus-point-setting-detail-view/<int:pk>/",
        cbvs.BonusPointSettingDetailView.as_view(),
        name="bonus-point-setting-detail-view",
    ),
    path(
        "bonus-setting-form-values/",
        views.bonus_setting_form_values,
        name="bonus-setting-form-values",
    ),
    path(
        "update-isactive-bonuspoint-setting/<int:obj_id>/",
        views.update_isactive_bonuspoint_setting,
        name="update-isactive-bonuspoint-setting",
    ),
    # ===========Employee bonus point============
    path(
        "employee-bonus-point/",
        cbvs.EmployeeBonusPointSectionView.as_view(),
        name="employee-bonus-point",
    ),
    path(
        "employee-bonus-point-nav/",
        cbvs.EmployeeBonusPointNavView.as_view(),
        name="employee-bonus-point-nav",
    ),
    path(
        "create-employee-bonus-point/",
        cbvs.EmployeeBonusPointFormView.as_view(),
        name="create-employee-bonus-point",
    ),
    path(
        "employee-bonus-point-list-view/",
        cbvs.EmployeeBonusPointListView.as_view(),
        name="employee-bonus-point-list-view",
    ),
    path(
        "update-employee-bonus-point/<int:pk>/",
        cbvs.EmployeeBonusPointFormView.as_view(),
        name="update-employee-bonus-point",
    ),
    path(
        "delete-employee-bonus-point/<int:pk>/",
        views.delete_employee_bonus_point,
        name="delete-employee-bonus-point",
    ),
    path(
        "history-tracking/<int:obj_id>/",
        history_tracking,
        name="history-tracking",
        kwargs={"model": models.Meetings, "decorators": ["login_required"]},
    ),
    # ── PMS Modern Dashboard ─────────────────────────────────────────────────
    path(
        "dashboard/",
        pms_dashboard.pms_dashboard_view,
        name="dashboard-view",
    ),
    path("dashboard/api/kpi/", pms_dashboard.pms_kpi_data, name="pms-dashboard-kpi"),
    path(
        "dashboard/api/objective-status/",
        pms_dashboard.pms_objective_status,
        name="pms-dashboard-obj-status",
    ),
    path(
        "dashboard/api/kr-status/",
        pms_dashboard.pms_key_result_status,
        name="pms-dashboard-kr-status",
    ),
    path(
        "dashboard/api/feedback-status/",
        pms_dashboard.pms_feedback_status,
        name="pms-dashboard-fb-status",
    ),
    path(
        "dashboard/api/department/",
        pms_dashboard.pms_department_performance,
        name="pms-dashboard-dept",
    ),
    path(
        "dashboard/api/performers/",
        pms_dashboard.pms_top_performers,
        name="pms-dashboard-performers",
    ),
    path(
        "dashboard/api/okr-overview/",
        pms_dashboard.pms_kr_progress_overview,
        name="pms-dashboard-okr-overview",
    ),
    path(
        "dashboard/api/meetings/",
        pms_dashboard.pms_upcoming_meetings,
        name="pms-dashboard-meetings",
    ),
]
