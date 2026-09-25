from django.urls import path

from project import dashboard as proj_dashboard
from project.cbv import dashboard, project_stage, projects, tasks, timesheet
from project.models import Project

from . import views

urlpatterns = [
    # Dashboard (modern)
    path(
        "dashboard/",
        proj_dashboard.project_dashboard_view,
        name="project-dashboard-view",
    ),
    path(
        "dashboard/api/kpi/",
        proj_dashboard.project_kpi_data,
        name="project-dashboard-kpi",
    ),
    path(
        "dashboard/api/pipeline/",
        proj_dashboard.project_status_pipeline,
        name="project-dashboard-pipeline",
    ),
    path(
        "dashboard/api/tasks/",
        proj_dashboard.project_task_status,
        name="project-dashboard-tasks",
    ),
    path(
        "dashboard/api/trend/",
        proj_dashboard.project_monthly_trend,
        name="project-dashboard-trend",
    ),
    path(
        "dashboard/api/top/",
        proj_dashboard.project_top_active,
        name="project-dashboard-top",
    ),
    path(
        "dashboard/api/contributors/",
        proj_dashboard.project_top_contributors,
        name="project-dashboard-contributors",
    ),
    path(
        "dashboard/api/task-deadlines/",
        proj_dashboard.project_task_deadlines,
        name="project-dashboard-task-deadlines",
    ),
    path(
        "projects-due-in-this-month/",
        dashboard.ProjectsDueInMonth.as_view(),
        name="projects-due-in-this-month",
    ),
    path(
        "project-status-chart/", views.project_status_chart, name="project-status-chart"
    ),
    path("task-status-chart/", views.task_status_chart, name="task-status-chart"),
    # path(
    #     "project-detailed-view/<int:project_id>/",
    #     views.project_detailed_view,
    #     name="project-detailed-view",
    # ),
    path(
        "project-detailed-view/<int:pk>/",
        dashboard.ProjectDetailView.as_view(),
        name="project-detailed-view",
    ),
    # Project
    # path("project-view/", views.project_view, name="project-view"),
    path(
        "project-nav-view/", projects.ProjectsNavView.as_view(), name="project-nav-view"
    ),
    path(
        "project-list-view/", projects.ProjectsList.as_view(), name="project-list-view"
    ),
    path(
        "project-card-view/",
        projects.ProjectCardView.as_view(),
        name="project-card-view",
    ),
    path("project-view/", projects.ProjectsView.as_view(), name="project-view"),
    # path("create-project", views.create_project, name="create-project"),
    path("create-project/", projects.ProjectFormView.as_view(), name="create-project"),
    # path(
    #     "update-project/<int:project_id>/",
    #      views.project_update,
    #      name="update-project"
    # ),
    path(
        "update-project/<int:pk>/",
        projects.ProjectFormView.as_view(),
        name="update-project",
    ),
    path(
        "change-project-status/<int:project_id>/",
        views.change_project_status,
        name="change-project-status",
    ),
    path(
        "delete-project/<int:project_id>/", views.project_delete, name="delete-project"
    ),
    path("project-filter/", views.project_filter, name="project-filter"),
    path("project-import/", views.project_import, name="project-import"),
    path("project-bulk-export/", views.project_bulk_export, name="project-bulk-export"),
    path(
        "project-bulk-archive/", views.project_bulk_archive, name="project-bulk-archive"
    ),
    path("project-bulk-delete/", views.project_bulk_delete, name="project-bulk-delete"),
    path(
        "project-archive/<int:project_id>/",
        views.project_archive,
        name="project-archive",
    ),
    # Task
    path(
        "task-view/<int:project_id>/",
        views.task_view,
        name="task-view",
        kwargs={"model": Project},
    ),
    path(
        "create-task/<int:project_id>/",
        tasks.TaskCreateForm.as_view(),
        name="create-task",
    ),
    path(
        "quick-create-task/<int:stage_id>/",
        views.quick_create_task,
        name="quick-create-task",
    ),
    # path("create-task/<int:stage_id>/", views.create_task, name="create-task"),
    path(
        "create-task-in-project/<int:project_id>/",
        views.create_task_in_project,
        name="create-task-in-project",
    ),
    path(
        "create-stage-task/<int:stage_id>/",
        tasks.TaskCreateForm.as_view(),
        name="create-stage-task",
    ),
    path("update-task/<int:pk>/", tasks.TaskCreateForm.as_view(), name="update-task"),
    # path("update-task/<int:task_id>/", views.update_task, name="update-task"),
    path("delete-task/<int:task_id>/", views.delete_task, name="delete-task"),
    path("task-details/<int:task_id>/", views.task_details, name="task-details"),
    path("task-filter/<int:project_id>/", views.task_filter, name="task-filter"),
    path(
        "task-stage-change/<int:task_id>/",
        views.task_stage_change,
        name="task-stage-change",
    ),
    # path("task-timesheet/<int:task_id>/", views.task_timesheet, name="task-timesheet"),
    path(
        "task-timesheet/<int:task_id>/",
        timesheet.TaskTimeSheet.as_view(),
        name="task-timesheet",
    ),
    # path(
    #     "create-timesheet-task/<int:task_id>/",
    #     views.create_timesheet_task,
    #     name="create-timesheet-task",
    # ),
    path(
        "update-timesheet-task/<int:timesheet_id>/",
        views.update_timesheet_task,
        name="update-timesheet-task",
    ),
    path("drag-and-drop-task/", views.drag_and_drop_task, name="drag-and-drop-task"),
    # Task-all
    path("task-all/", tasks.TasksTemplateView.as_view(), name="task-all"),
    path("tasks-list-view/", tasks.TaskListView.as_view(), name="tasks-list-view"),
    path(
        "tasks-list-individual-view/",
        tasks.TasksInIndividualView.as_view(),
        name="tasks-list-individual-view",
    ),
    path("tasks-card-view/", tasks.TaskCardView.as_view(), name="tasks-card-view"),
    path("tasks-navbar/", tasks.TasksNavBar.as_view(), name="tasks-navbar"),
    path("create-task-all/", tasks.TaskCreateForm.as_view(), name="create-task-all"),
    path(
        "update-task-all/<int:pk>/",
        tasks.TaskCreateForm.as_view(),
        name="update-task-all",
    ),
    path(
        "task-detail-view/<int:pk>/",
        tasks.TaskDetailView.as_view(),
        name="task-detail-view",
    ),
    path(
        "update-project-task-status/<int:task_id>/",
        views.update_project_task_status,
        name="update-project-task-status",
    ),
    # path("task-all", views.task_all, name="task-all"),
    # path("create-task-all", views.task_all_create, name="create-task-all"),
    # path(
    #     "update-task-all/<int:task_id>/", views.update_task_all, name="update-task-all"
    # ),
    path("task-all-filter/", views.task_all_filter, name="task-all-filter"),
    path(
        "task-all-bulk-archive/",
        views.task_all_bulk_archive,
        name="task-all-bulk-archive",
    ),
    path(
        "task-all-bulk-delete/", views.task_all_bulk_delete, name="task-all-bulk-delete"
    ),
    path(
        "task-all-archive/<int:task_id>/",
        views.task_all_archive,
        name="task-all-archive",
    ),
    # Project stage
    path(
        "create-project-stage/<int:project_id>/",
        project_stage.ProjectStageCreateForm.as_view(),
        name="create-project-stage",
    ),
    # path(
    #     "create-project-stage/<int:project_id>/",
    #     views.create_project_stage,
    #     name="create-project-stage",
    # ),
    path(
        "update-project-stage/<int:pk>/",
        project_stage.ProjectStageCreateForm.as_view(),
        name="update-project-stage",
    ),
    # path(
    #     "update-project-stage/<int:stage_id>/",
    #     views.update_project_stage,
    #     name="update-project-stage",
    # ),
    path(
        "delete-project-stage/<int:stage_id>/",
        views.delete_project_stage,
        name="delete-project-stage",
    ),
    path("get-stages/", views.get_stages, name="get-stages"),
    path(
        "create-stage-taskall/", views.create_stage_taskall, name="create-stage-taskall"
    ),
    path("drag-and-drop-stage/", views.drag_and_drop_stage, name="drag-and-drop-stage"),
    # Timesheet
    # path("view-time-sheet", views.time_sheet_view, name="view-time-sheet"),
    path("view-time-sheet/", timesheet.TimeSheetView.as_view(), name="view-time-sheet"),
    path("get-members-of-project/", views.get_members, name="get-members-of-project"),
    path(
        "get-tasks-of-project/",
        views.get_tasks_in_timesheet,
        name="get-tasks-of-project",
    ),
    path(
        "time-sheet-tab-shell/",
        timesheet.TimeSheetTabShell.as_view(),
        name="time-sheet-tab-shell",
    ),
    path(
        "my-time-sheet-tab-shell/",
        timesheet.MyTimeSheetTabShell.as_view(),
        name="my-time-sheet-tab-shell",
    ),
    path(
        "time-sheet-nav/", timesheet.TimeSheetNavView.as_view(), name="time-sheet-nav"
    ),
    path(
        "my-time-sheet-nav/",
        timesheet.MyTimeSheetNavView.as_view(),
        name="my-time-sheet-nav",
    ),
    path("time-sheet-list/", timesheet.TimeSheetList.as_view(), name="time-sheet-list"),
    path(
        "my-time-sheet-list/",
        timesheet.MyTimeSheetList.as_view(),
        name="my-time-sheet-list",
    ),
    path(
        "time-sheet-card/",
        timesheet.TimeSheetCardView.as_view(),
        name="time-sheet-card",
    ),
    path(
        "time-sheet-detail-view/<int:pk>/",
        timesheet.TimeSheetDetailView.as_view(),
        name="time-sheet-detail-view",
    ),
    # path("create-time-sheet", views.time_sheet_creation, name="create-time-sheet"),
    path(
        "create-time-sheet/",
        timesheet.TimeSheetFormView.as_view(),
        name="create-time-sheet",
    ),
    path(
        "create-timesheet-task/<int:task_id>/",
        timesheet.TimeSheetFormView.as_view(),
        name="create-timesheet-task",
    ),
    path(
        "update-time-sheet/<int:pk>/",
        timesheet.TimeSheetFormView.as_view(),
        name="update-time-sheet",
    ),
    # path(
    #     "update-time-sheet/<int:time_sheet_id>/",
    #     views.time_sheet_update,
    #     name="update-time-sheet",
    # ),
    # path("get-project", views.get_project, name="get-project"),
    path(
        "create-project-time-sheet/",
        views.time_sheet_project_creation,
        name="create-project-time-sheet",
    ),
    path(
        "create-task-time-sheet/",
        views.time_sheet_task_creation,
        name="create-task-time-sheet",
    ),
    path(
        "delete-time-sheet/<int:time_sheet_id>/",
        views.time_sheet_delete,
        name="delete-time-sheet",
    ),
    path("filter-time-sheet/", views.time_sheet_filter, name="filter-time-sheet"),
    path("time-sheet-initial/", views.time_sheet_initial, name="time-sheet-initial"),
    path(
        "personal-time-sheet-view/<int:emp_id>/",
        views.personal_time_sheet_view,
        name="personal-time-sheet-view",
    ),
    path("personal-time-sheet/", views.personal_time_sheet, name="personal-time-sheet"),
    path(
        "view-single-time-sheet/<int:time_sheet_id>/",
        views.time_sheet_single_view,
        name="view-single-time-sheet",
    ),
    path(
        "time-sheet-bulk-delete/",
        views.time_sheet_bulk_delete,
        name="time-sheet-bulk-delete",
    ),
]
