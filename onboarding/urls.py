"""
urls.py

This module is used to map url path with view methods.
"""

from django.urls import path

from onboarding import dashboard as on_dashboard
from onboarding import views
from onboarding.cbv import dashboard, onboarding_candidates, onboarding_view, pipeline
from recruitment.cbv import candidates
from recruitment.models import Candidate

urlpatterns = [
    path(
        "stage-creation/<int:obj_id>/",
        onboarding_view.StageCreateForm.as_view(),
        name="stage-creation",
    ),
    path(
        "stage-update/<int:pk>/<int:obj_id>/",
        onboarding_view.StageCreateForm.as_view(),
        name="stage-update",
    ),
    path(
        "onboarding-stage-sequence-update/<int:pk>/",
        views.update_stage_order,
        name="onboarding-stage-sequence-update",
    ),
    path(
        "task-creation/<int:obj_id>/",
        onboarding_view.TaskCreateForm.as_view(),
        name="task-creation",
    ),
    path(
        "onboarding-cand-detail-view/<int:pk>/",
        pipeline.CandidateOnboardingDetail.as_view(),
        name="onboarding-cand-detail-view",
    ),
    path(
        "task-update/<int:pk>/",
        onboarding_view.TaskUpdateFormView.as_view(),
        name="task-update",
    ),
    # path("stage-creation/<str:obj_id>", views.stage_creation, name="stage-creation"),
    # path(
    #     "stage-update/<int:stage_id>/<int:recruitment_id>",
    #     views.stage_update,
    #     name="stage-update",
    # ),
    path("stage-delete/<int:stage_id>/", views.stage_delete, name="stage-delete"),
    path("task-creation/", views.task_creation, name="task-creation"),
    path("task-delete/<int:task_id>/", views.task_delete, name="task-delete"),
    # path(
    #     "task-update/<int:task_id>/",
    #     views.task_update,
    #     name="task-update",
    # ),
    path("candidate-creation/", views.candidate_creation, name="candidate-creation"),
    path(
        "candidate-update/<int:obj_id>/",
        views.candidate_update,
        name="candidate-update",
    ),
    path(
        "candidate-delete/<int:obj_id>/",
        views.candidate_delete,
        name="candidate-delete",
    ),
    # path(
    #     "candidate-single-view/<int:id>",
    #     views.candidates_single_view,
    #     name="candidate-single-view",
    #     kwargs={"model": Candidate},
    # ),
    path(
        "candidate-single-view/<int:pk>/",
        onboarding_view.OnboardingCandidateDetailView.as_view(),
        name="candidate-single-view",
    ),
    # path("candidates-view/", views.candidates_view, name="candidates-view"),
    path(
        "hired-candidates-view/",
        views.hired_candidate_view,
        name="hired-candidates-view",
    ),
    path("candidate-filter/", views.candidate_filter, name="candidate-filter"),
    path("email-send/", views.email_send, name="email-send"),
    path("view-onboarding/", views.onboarding_view, name="onboarding-view"),
    path("kanban-view/", views.kanban_view, name="kanban-view"),
    path(
        "candidate-task-update/<int:taskId>/",
        views.candidate_task_update,
        name="candidate-task-update",
    ),
    path(
        "get-status/<int:task_id>/",
        views.get_status,
        name="get-status",
    ),
    path(
        "assign-task/<int:task_id>/",
        views.assign_task,
        name="assign-task",
    ),
    path(
        "candidate-stage-update/<int:candidate_id>/<int:recruitment_id>/",
        views.candidate_stage_update,
        name="candidate-stage-update",
    ),
    path(
        "candidate-stage-bulk-update/",
        views.candidate_stage_bulk_update,
        name="candidate-stage-bulk-update",
    ),
    path(
        "candidate-task-bulk-update/",
        views.candidate_task_bulk_update,
        name="candidate-task-bulk-update",
    ),
    path(
        "stage-name-update/<int:stage_id>/",
        views.stage_name_update,
        name="stage-name-update",
    ),
    path("user-creation/<str:token>/", views.user_creation, name="user-creation"),
    path("profile-view/<str:token>/", views.profile_view, name="profile-view"),
    path(
        "employee-creation/<str:token>/",
        views.employee_creation,
        name="employee-creation",
    ),
    path(
        "employee-bank-details/<str:token>/",
        views.employee_bank_details,
        name="employee-bank-details",
    ),
    path("welcome-aboard/", views.welcome_aboard, name="welcome-aboard"),
    path(
        "onboard-candidate-chart/",
        views.onboard_candidate_chart,
        name="onboard-candidate-chart",
    ),
    path("update-joining/", views.update_joining, name="update-joining"),
    path(
        "view-onboarding-dashboard/",
        views.view_dashboard,
        name="view-onboarding-dashboard",
    ),
    path("stage-chart/", views.dashboard_stage_chart, name="stage-chart"),
    path(
        "candidate-sequence-update/",
        views.candidate_sequence_update,
        name="onboarding-candidate-sequence-update",
    ),
    path(
        "stage-sequence-update/",
        views.stage_sequence_update,
        name="onboarding-stage-sequence-update",
    ),
    path(
        "send-mail/<int:candidate_id>/",
        views.onboarding_send_mail,
        name="onboarding-send-mail",
    ),
    path(
        "update-probation-end/", views.update_probation_end, name="update-probation-end"
    ),
    # path("task-report-onboarding", views.task_report, name="task-report-onboarding"),
    path(
        "task-report-onboarding/",
        dashboard.MyOnboardingTaskList.as_view(),
        name="task-report-onboarding",
    ),
    # path(
    #     "candidate-tasks-status",
    #     views.candidate_tasks_status,
    #     name="candidate-tasks-status",
    # ),
    path(
        "candidate-tasks-status/",
        dashboard.MyOnboardingCandidatesSingleView.as_view(),
        name="candidate-tasks-status",
    ),
    path("change-task-status/", views.change_task_status, name="change-task-status"),
    path(
        "update-offer-letter-status/",
        views.update_offer_letter_status,
        name="update-offer-letter-status",
    ),
    # path(
    #     "add-to-rejected-candidates",
    #     views.add_to_rejected_candidates,
    #     name="add-to-rejected-candidates",
    # ),
    path(
        "undo-rejected-candidate/<int:candidate_id>/",
        views.undo_rejected_candidate,
        name="undo-rejected-candidate",
    ),
    path(
        "candidate-select-filter-onboarding/",
        views.candidate_select_filter,
        name="candidate-select-filter-onboarding",
    ),
    path(
        "candidate-select/", views.candidate_select, name="candidate-select-onboarding"
    ),
    path(
        "candidates-view/",
        onboarding_candidates.OnboardingCandidatesView.as_view(),
        name="candidates-view",
    ),
    path(
        "onboarding-candidates-list/",
        onboarding_candidates.OnboardingCandidatesList.as_view(),
        name="onboarding-candidates-list",
    ),
    path(
        "onboarding-candidates-nav/",
        onboarding_candidates.OnboardingCandidatesNav.as_view(),
        name="onboarding-candidates-nav",
    ),
    path(
        "get-cand-tasks/<int:pk>/",
        onboarding_candidates.CandidateProfileTasks.as_view(),
        name="get-cand-task",
    ),
    path(
        "offer-letter-bulk-status-update/",
        views.offer_letter_bulk_status_update,
        name="offer-letter-bulk-status-update",
    ),
    path(
        "onboarding-candidate-bulk-delete/",
        views.onboarding_candidate_bulk_delete,
        name="onboarding-candidate-bulk-delete",
    ),
    path(
        "cbv-change-stage/<int:pk>/",
        pipeline.ChangeStage.as_view(),
        name="onboarding-cbv-change-stage",
    ),
    path(
        "kanban-required-task-check/",
        pipeline.KanbanRequiredTaskCheck.as_view(),
        name="onboarding-kanban-required-task-check",
    ),
    path(
        "onboarding-view/",
        pipeline.PipelineView.as_view(),
        name="cbv-pipeline-onboarding",
    ),
    path(
        "cbv-pipeline-nav/",
        pipeline.PipelineNav.as_view(),
        name="cbv-pipeline-nav-onboarding",
    ),
    path(
        "cbv-pipeline-tab/",
        pipeline.RecruitmentTabView.as_view(),
        name="cbv-pipeline-tab-onboarding",
    ),
    path(
        "get-stages/<int:recruitment_id>/",
        pipeline.CandidatePipeline.as_view(),
        name="get-stages-onboarding",
    ),
    path(
        "assign-task-pipeline/<int:task_id>/<int:cand_id>/",
        pipeline.AssignTask.as_view(),
        name="assign-task-pipeline",
    ),
    path(
        "assign-task-pipeline/<int:task_id>/<int:cand_id>/<int:cand_task_id>/",
        pipeline.AssignTask.as_view(),
        name="assign-task-pipeline",
    ),
    # path("candidate-lists-cbv/<int:stage_id>/",pipeline.CandidateList.as_view(),name='candidate-lists-cbv'),
    # path("candidate-lists-cbv/<int:stage_id>/<int:rec_id>/",pipeline.CandidateList.as_view(),name='candidate-lists-cbv'),
    path(
        "candidate-lists-cbv/",
        pipeline.CandidateList.as_view(),
        name="candidate-lists-cbv-onboarding",
    ),
    path(
        "candidate-card-cbv/<int:pk>/",
        pipeline.CandidateKanbanView.as_view(),
        name="candidate-card-cbv-onboarding",
    ),
    path(
        "onboarding-pipeline-shell/<int:rec_id>/",
        pipeline.RecruitmentPipelineContentShell.as_view(),
        name="onboarding-pipeline-shell",
    ),
    path(
        "onboarding-pipeline-tab-nav/<int:rec_id>/",
        pipeline.RecruitmentCandidateNav.as_view(),
        name="onboarding-pipeline-tab-nav",
    ),
    # path("cbv-change-stage/<int:pk>/",pipeline.ChangeStage.as_view(),name="cbv-change-stage")
    # ── Onboarding Modern Dashboard ──────────────────────────────────────────
    path(
        "dashboard/",
        on_dashboard.onboarding_dashboard_view,
        name="onboarding-dashboard",
    ),
    path(
        "dashboard/api/kpi/",
        on_dashboard.onboarding_kpi_data,
        name="onboarding-dashboard-kpi",
    ),
    path(
        "dashboard/api/position/",
        on_dashboard.onboarding_by_job_position,
        name="onboarding-dashboard-position",
    ),
    path(
        "dashboard/api/my-tasks/",
        on_dashboard.onboarding_task_managers,
        name="onboarding-dashboard-my-tasks",
    ),
    path(
        "dashboard/api/completion-trend/",
        on_dashboard.onboarding_completion_trend,
        name="onboarding-dashboard-completion-trend",
    ),
]
