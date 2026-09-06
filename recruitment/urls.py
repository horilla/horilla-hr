"""
urls.py

This module is used to map url path with view methods.
"""

from django.urls import path

from base.views import add_remove_dynamic_fields, object_duplicate
from recruitment import cbvs
from recruitment import dashboard as rec_dashboard
from recruitment.cbv import (
    candidate_mail_log,
    candidate_profile,
    candidate_reject_reason,
    candidates,
    dashboard,
    interview,
    pipeline,
    recruitment_survey,
    recruitment_view,
    settings_tabs,
    skill_zone,
    skills,
    stage_view,
)
from recruitment.forms import QuestionForm, RecruitmentCreationForm, StageCreationForm
from recruitment.models import Candidate, Recruitment, RecruitmentSurvey, Stage
from recruitment.views import actions
from recruitment.views import dashboard as views_dashboard
from recruitment.views import linkedin, search, surveys, views

urlpatterns = [
    path(
        "interview-view/", interview.InterviewViewPage.as_view(), name="interview-view"
    ),
    path(
        "get-cand-tasks/<int:pk>/",
        candidate_profile.CandidateProfileTasks.as_view(),
        name="get-cand-task",
    ),
    path(
        "interview-nav-view/",
        interview.InterviewNavView.as_view(),
        name="interview-nav-view",
    ),
    path(
        "interview-list-view/",
        interview.InterviewLIstView.as_view(),
        name="interview-list-view",
    ),
    path(
        "interview-detail-view/<int:pk>/",
        interview.InterviewDetailView.as_view(),
        name="interview-detail-view",
    ),
    # path("recruitment-create/", views.recruitment, name="recruitment-create"),
    path(
        "recruitment-create/",
        recruitment_view.RecruitmentForm.as_view(),
        name="recruitment-create",
    ),
    # path("recruitment-view/", views.recruitment_view, name="recruitment-view"),
    path(
        "recruitment-search/",
        search.recruitment_search,
        name="recruitment-search",
    ),
    # path(
    #     "recruitment-update/<int:rec_id>/",
    #     views.recruitment_update,
    #     name="recruitment-update",
    # ),
    path(
        "recruitment-update/<int:pk>/",
        recruitment_view.RecruitmentForm.as_view(),
        name="recruitment-update",
    ),
    # path(
    #     "recruitment-duplicate/<int:obj_id>/",
    #     object_duplicate,
    #     name="recruitment-duplicate",
    #     kwargs={
    #         "model": Recruitment,
    #         "form": RecruitmentCreationForm,
    #         "template": "recruitment/recruitment_form.html",
    #     },
    # ),
    path(
        "recruitment-duplicate/<int:pk>/",
        recruitment_view.RecruitmentFormDuplicate.as_view(),
        name="recruitment-duplicate",
    ),
    # path(
    #     "recruitment-update-pipeline/<int:rec_id>/",
    #     views.recruitment_update_pipeline,
    #     name="recruitment-update-pipeline",
    # ),
    path(
        "recruitment-update-pipeline/<int:pk>/",
        recruitment_view.RecruitmentForm.as_view(),
        name="recruitment-update-pipeline",
    ),
    # path(
    #     "recruitment-update-delete/<int:rec_id>/",
    #     actions.recruitment_delete_pipeline,
    #     name="recruitment-delete-pipeline",
    # ),
    path(
        "recruitment-delete/<int:rec_id>/",
        actions.recruitment_delete,
        name="recruitment-delete",
    ),
    path(
        "recruitment-close-pipeline/<int:rec_id>/",
        views.recruitment_close_pipeline,
        name="recruitment-close-pipeline",
    ),
    path(
        "recruitment-reopen-pipeline/<int:rec_id>/",
        views.recruitment_reopen_pipeline,
        name="recruitment-reopen-pipeline",
    ),
    path("pipeline/", views.recruitment_pipeline, name="pipeline"),
    path("pipeline-search/", views.filter_pipeline, name="pipeline-search"),
    path(
        "pipeline-stages-component/<str:view>/",
        views.stage_component,
        name="pipeline-stages-component",
    ),
    path("get-stage-count/", views.get_stage_badge_count, name="get-stage-count"),
    path(
        "update-candidate-stage-and-sequence/",
        views.update_candidate_stage_and_sequence,
        name="update-candidate-stage-and-sequence",
    ),
    path(
        "update-candidate-sequence/",
        views.update_candidate_sequence,
        name="update-candidate-sequence",
    ),
    # path(
    #     "update-candidate-stage",
    #     views.update_candidate_stage,
    #     name="update-candidate-stage",
    # ),
    path(
        "candidate-stage-component/",
        views.candidate_component,
        name="candidate-stage-component",
    ),
    path(
        "candidate-stage-change/",
        views.change_candidate_stage,
        name="candidate-stage-change",
    ),
    # path("pipeline-card/", views.recruitment_pipeline_card, name="pipeline-card"),
    path(
        "recruitment-archive/<int:rec_id>/",
        views.recruitment_archive,
        name="recruitment-archive",
    ),
    path(
        "candidate-schedule-date-update/",
        views.candidate_schedule_date_update,
        name="candidate-schedule-date-update",
    ),
    # path("stage-create/", views.stage, name="rec-stage-create"),
    path("stage-create/", stage_view.StageFormView.as_view(), name="rec-stage-create"),
    path(
        "update-stage-seq/<int:pk>/",
        views.update_stage_order,
        name="rec-update-stage-seq",
    ),
    # path("stage-view/", views.stage_view, name="rec-stage-view"),
    path("stage-data/<int:rec_id>/", views.stage_data, name="stage-data"),
    path("stage-search/", search.stage_search, name="stage-search"),
    # path("stage-update/<int:stage_id>/", views.stage_update, name="rec-stage-update"),
    path(
        "stage-update/<int:pk>/",
        stage_view.StageFormView.as_view(),
        name="rec-stage-update",
    ),
    # path(
    #     "rec-stage-duplicate/<int:obj_id>/",
    #     object_duplicate,
    #     name="rec-stage-duplicate",
    #     kwargs={
    #         "model": Stage,
    #         "form": StageCreationForm,
    #         "template": "stage/stage_form.html",
    #     },
    # ),
    path(
        "rec-stage-duplicate/<int:pk>/",
        stage_view.StageDuplicateForm.as_view(),
        name="rec-stage-duplicate",
    ),
    # path("add-candidate-to-stage/", views.add_candidate, name="add-candidate-to-stage"),
    path(
        "add-candidate-to-stage/",
        recruitment_view.AddCandidateFormView.as_view(),
        name="add-candidate-to-stage",
    ),
    path(
        "stage-update-pipeline/<int:pk>/",
        stage_view.StageFormView.as_view(),
        name="stage-update-pipeline",
    ),
    # path(
    #     "stage-update-pipeline/<int:stage_id>/",
    #     views.stage_update_pipeline,
    #     name="stage-update-pipeline",
    # ),
    path(
        "stage-title-update/<int:stage_id>/",
        views.stage_title_update,
        name="stage-title-update",
    ),
    path(
        "stage-delete/<int:stage_id>/",
        actions.stage_delete,
        name="rec-stage-delete",
    ),
    path(
        "remove-stage-manager/<int:mid>/<int:sid>/",
        actions.remove_stage_manager,
        name="rec-remove-stage-manager",
    ),
    path(
        "remove-recruitment-manager/<int:mid>/<int:rid>/",
        actions.remove_recruitment_manager,
        name="remove-recruitment-manager",
    ),
    path("candidate-create/", views.candidate, name="candidate-create"),
    path(
        "recruitment-stage-get/<int:rec_id>/",
        views.recruitment_stage_get,
        name="recruitment-stage-get",
    ),
    path(
        "candidate-stage-update/<int:cand_id>/",
        views.candidate_stage_update,
        name="candidate-stage-update",
    ),
    path("view-note/<int:cand_id>/", views.view_note, name="view-note"),
    path("add-note/<int:pk>/", views.add_note, name="add-note"),
    path("add-note/", views.add_note, name="add-note-post"),
    path("create-note/<int:cand_id>/", views.create_note, name="create-note"),
    path("create-note/", views.create_note, name="create-note-post"),
    path("note-update/<int:note_id>/", views.note_update, name="note-update"),
    path(
        "note-update-individual/<int:note_id>/",
        views.note_update_individual,
        name="note-update-individual",
    ),
    path(
        "note-delete/<int:note_id>/",
        actions.note_delete,
        name="note-delete",
    ),
    path(
        "note-delete-individual/<int:note_id>/",
        actions.note_delete_individual,
        name="note-delete-individual",
    ),
    path(
        "candidate-can-view-note/<int:id>/",
        views.candidate_can_view_note,
        name="candidate-can-view-note",
    ),
    path("send-mail/<int:cand_id>/", views.form_send_mail, name="send-mail"),
    path("send-mail/", views.form_send_mail, name="send-mail"),
    # path(
    #     "interview-schedule/<int:cand_id>/",
    #     views.interview_schedule,
    #     name="interview-schedule",
    # ),
    path(
        "interview-schedule/<int:cand_id>/",
        interview.InterviewForm.as_view(),
        name="interview-schedule",
    ),
    path(
        "create-interview-schedule/",
        interview.InterviewForm.as_view(),
        name="create-interview-schedule",
    ),
    # path(
    #     "create-interview-schedule",
    #     views.create_interview_schedule,
    #     name="create-interview-schedule",
    # ),
    path(
        "edit-interview/<int:pk>/",
        interview.InterviewForm.as_view(),
        name="edit-interview",
    ),
    # path(
    #     "edit-interview/<int:interview_id>/",
    #     views.interview_edit,
    #     name="edit-interview",
    # ),
    path(
        "delete-interview/<int:interview_id>/",
        views.interview_delete,
        name="delete-interview",
    ),
    path("get_managers/", views.get_managers, name="get_managers"),
    path(
        "get-interview-managers/",
        views.get_interview_managers,
        name="get-interview-managers",
    ),
    # path("candidate-view/", views.candidate_view, name="candidate-view"),
    # path("interview-view/", views.interview_view, name="interview-view"),
    path(
        "interview-filter-view/",
        views.interview_filter_view,
        name="interview-filter-view",
    ),
    path(
        "interview-employee-remove/<int:interview_id>/<int:employee_id>/",
        views.interview_employee_remove,
        name="interview-employee-remove",
    ),
    path(
        "candidate-filter-view/",
        search.candidate_filter_view,
        name="candidate-filter-view",
    ),
    path(
        "search-candidate/",
        search.candidate_search,
        name="search-candidate",
    ),
    # path("candidate-view-list/", views.candidate_view_list, name="candidate-view-list"),
    path("candidate-view-card/", views.candidate_view_card, name="candidate-view-card"),
    path(
        "candidate-info-export/", views.candidate_export, name="candidate-info-export"
    ),
    path(
        "candidate-view/<int:cand_id>/",
        views.candidate_view_individual,
        name="candidate-view-individual",
        kwargs={"model": Candidate},
    ),
    path(
        "profile/recruitment/candidate-view/<int:pk>/",
        candidate_profile.CandidateProfileView.as_view(),
        name="candidate-view",
    ),
    path(
        "candidate-mail-log-list/<int:pk>/",
        candidate_mail_log.CandidateMailLogTabList.as_view(),
        name="candidate-mail-log-list",
    ),
    # path("candidate-mail-log-detail/<int:pk>/", candidate_mail_log.CandidateMailLogDetailView.as_view(), name="candidate-mail-log-deail"),
    path(
        "candidate-update/<int:cand_id>/",
        views.candidate_update,
        name="rec-candidate-update",
        kwargs={"model": Candidate},
    ),
    path(
        "candidate-conversion/<int:cand_id>/",
        views.candidate_conversion,
        name="candidate-conversion",
        kwargs={"model": Candidate},
    ),
    path(
        "delete-profile-image/<int:obj_id>/",
        views.delete_profile_image,
        name="delete-profile-image",
    ),
    path(
        "candidate-delete/<int:cand_id>/",
        actions.candidate_delete,
        name="rec-candidate-delete",
    ),
    path(
        "candidate-archive/<int:cand_id>/",
        actions.candidate_archive,
        name="rec-candidate-archive",
    ),
    path(
        "candidate-bulk-delete/",
        actions.candidate_bulk_delete,
        name="candidate-bulk-delete",
    ),
    path(
        "candidate-bulk-archive/",
        actions.candidate_bulk_archive,
        name="candidate-bulk-archive",
    ),
    path(
        "candidate-history/<int:cand_id>/",
        views.candidate_history,
        name="candidate-history",
    ),
    path(
        "application-form/",
        surveys.application_form,
        name="application-form",
    ),
    path(
        "send-acknowledgement/", views.send_acknowledgement, name="send-acknowledgement"
    ),
    path(
        "skill-zone-status-dashboard/",
        dashboard.SkillZoneStatusList.as_view(),
        name="skill-zone-status-dashboard",
    ),
    path(
        "candidate-on-onboard-dashboard/",
        dashboard.CandidateOnOnboardList.as_view(),
        name="candidate-on-onboard-dashboard",
    ),
    path(
        "current-hiring-pipeline-dashboard/",
        dashboard.CurrentHiringList.as_view(),
        name="current-hiring-pipeline-dashboard",
    ),
    path(
        "ongoing-recruitment-dashboard/",
        dashboard.OnGoingRecruitmentList.as_view(),
        name="ongoing-recruitment-dashboard",
    ),
    path(
        "dashboard-pipeline/",
        views_dashboard.dashboard_pipeline,
        name="recruitment-pipeline",
    ),
    path(
        "get-open-positions/",
        views_dashboard.get_open_position,
        name="get-open-position",
    ),
    path(
        "dashboard-hiring/",
        views_dashboard.dashboard_hiring,
        name="dashboard-hiring",
    ),
    path(
        "dashboard-vacancy/",
        views_dashboard.dashboard_vacancy,
        name="dashboard-vacancy",
    ),
    path(
        "candidate-status/",
        views_dashboard.candidate_status,
        name="candidate-status",
    ),
    path(
        "candidate-sequence-update/",
        views.candidate_sequence_update,
        name="candidate-sequence-update",
    ),
    path(
        "stage-sequence-update/",
        views.stage_sequence_update,
        name="stage-sequence-update",
    ),
    path(
        "survey-template-preview/",
        surveys.survey_preview,
        name="survey-template-preview",
    ),
    path(
        "survey-template-preview/<int:pk>/",
        surveys.survey_preview,
        name="survey-template-preview",
    ),
    path(
        "update-question-order/",
        surveys.question_order_update,
        name="update-question-order",
    ),
    path(
        "recruitment-application-survey/",
        surveys.survey_form,
        name="recruitment-application-survey",
    ),
    path(
        "recruitment-survey-question-template-view/",
        recruitment_survey.SurveyTemplateSettingsView.as_view(),
        name="recruitment-survey-question-template-view",
    ),
    path(
        "survey-template-filter/",
        recruitment_survey.SurveyTemplateQuestionsTab.as_view(),
        name="survey-template-filter",
    ),
    path(
        "list-survey-templates/",
        recruitment_survey.SurveyTemplateList.as_view(),
        name="list-survey-templates",
    ),
    path(
        "list-survey-questions/",
        recruitment_survey.SurveyQuestionList.as_view(),
        name="list-survey-questions",
    ),
    path(
        "survey-template-nav/",
        recruitment_survey.SurveyTemplateNavView.as_view(),
        name="survey-template-nav",
    ),
    path(
        "survey-question-nav/",
        recruitment_survey.SurveyQuestionNavView.as_view(),
        name="survey-question-nav",
    ),
    path(
        "survey-template-tab-shell/",
        recruitment_survey.SurveyTemplateTabShell.as_view(),
        name="survey-template-tab-shell",
    ),
    path(
        "survey-question-tab-shell/",
        recruitment_survey.SurveyQuestionTabShell.as_view(),
        name="survey-question-tab-shell",
    ),
    path(
        "survey-template-settings-tab-view/",
        recruitment_survey.SurveyTemplateTabView.as_view(),
        name="survey-template-settings-tab-view",
    ),
    path(
        "survey-template-tab/",
        surveys.survey_template_tab,
        name="survey-template-tab",
    ),
    path(
        "survey-template-tab-list/",
        surveys.survey_template_tab_list,
        name="survey-template-tab-list",
    ),
    path(
        "survey-question-tab/",
        surveys.survey_question_tab,
        name="survey-question-tab",
    ),
    path(
        "survey-question-tab-list/",
        surveys.survey_question_tab_list,
        name="survey-question-tab-list",
    ),
    # path(
    #     "recruitment-survey-question-template-create",
    #     surveys.create_question_template,
    #     name="recruitment-survey-question-template-create",
    # ),
    path(
        "recruitment-survey-question-template-create/",
        recruitment_survey.QuestionFormView.as_view(),
        name="recruitment-survey-question-template-create",
    ),
    path(
        "add-remove-options-field/",
        add_remove_dynamic_fields,
        name="add-remove-options-field",
        kwargs={
            "model": RecruitmentSurvey,
            "form_class": QuestionForm,
            "template": "survey/add_more_options.html",
            "field_type": "character",
            "field_name_pre": "options",
        },
    ),
    # path(
    #     "recruitment-survey-question-template-edit/<int:survey_id>/",
    #     surveys.update_question_template,
    #     name="recruitment-survey-question-template-edit",
    # ),
    path(
        "recruitment-survey-question-template-edit/<int:pk>/",
        recruitment_survey.QuestionFormView.as_view(),
        name="recruitment-survey-question-template-edit",
    ),
    # path(
    #     "recruitment-survey-question-template-duplicate/<int:obj_id>/",
    #     object_duplicate,
    #     name="recruitment-survey-question-template-duplicate",
    #     kwargs={
    #         "model": RecruitmentSurvey,
    #         "form": QuestionForm,
    #         "template": "survey/template_form.html",
    #     },
    # ),
    path(
        "recruitment-survey-question-template-duplicate/<int:obj_id>/",
        recruitment_survey.QuestionDuplicateFormView.as_view(),
        name="recruitment-survey-question-template-duplicate",
    ),
    path(
        "recruitment-survey-question-template-delete/<int:survey_id>/",
        surveys.delete_survey_question,
        name="recruitment-survey-question-template-delete",
    ),
    path(
        "candidate-survey/",
        surveys.candidate_survey,
        name="candidate-survey",
    ),
    # path(
    #     "filter-survey/",
    #     search.filter_survey,
    #     name="rec-filter-survey",
    # ),
    # path(
    #     "single-survey-view/<int:survey_id>/",
    #     surveys.single_survey,
    #     name="single-survey-view",
    # ),
    path(
        "single-survey-view/<int:pk>/",
        recruitment_survey.RecruitmentSurveyDetailView.as_view(),
        name="single-survey-view",
    ),
    path(
        "survey-template-create/",
        recruitment_survey.SurveyTemplateFormView.as_view(),
        name="survey-template-create",
    ),
    # path(
    #     "survey-template-create",
    #     surveys.create_template,
    #     name="survey-template-create",
    # ),
    # path(
    #     "survey-template-delete/<int:pk>/",
    #     surveys.delete_survey_template,
    #     name="survey-template-delete",
    # ),
    path(
        "survey-template-delete/<int:pk>/",
        surveys.delete_survey_template,
        name="survey-template-delete",
    ),
    path(
        "survey-template-delete/",
        surveys.delete_template,
        name="survey-template-delete",
    ),
    path(
        "survey-template-question-add/",
        surveys.question_add,
        name="survey-template-question-add",
    ),
    path("candidate-select/", views.candidate_select, name="candidate-select"),
    path(
        "candidate-select-filter/",
        views.candidate_select_filter,
        name="candidate-select-filter",
    ),
    path("skill-zone-view/", views.skill_zone_view, name="skill-zone-view"),
    # path("skill-zone-create/", views.skill_zone_create, name="skill-zone-create"),
    path(
        "skill-zone-create/",
        skill_zone.SkillZoneFormView.as_view(),
        name="skill-zone-create",
    ),
    # path(
    #     "skill-zone-update/<int:sz_id>",
    #     views.skill_zone_update,
    #     name="skill-zone-update",
    # ),
    path(
        "skill-zone-update/<int:pk>/",
        skill_zone.SkillZoneFormView.as_view(),
        name="skill-zone-update",
    ),
    path(
        "skill-zone-delete/<int:sz_id>/",
        views.skill_zone_delete,
        name="skill-zone-delete",
    ),
    path(
        "skill-zone-archive/<int:sz_id>/",
        views.skill_zone_archive,
        name="skill-zone-archive",
    ),
    path("skill-zone-filter/", views.skill_zone_filter, name="skill-zone-filter"),
    # path(
    #     "skill-zone-cand-create/<int:sz_id>",
    #     views.skill_zone_candidate_create,
    #     name="skill-zone-cand-create",
    # ),
    path(
        "skill-zone-cand-create/<int:sz_id>/",
        skill_zone.SkillZoneCandidateFormView.as_view(),
        name="skill-zone-cand-create",
    ),
    # path(
    #     "skill-zone-cand-card-view/<int:sz_id>/",
    #     views.skill_zone_cand_card_view,
    #     name="skill-zone-cand-card-view",
    # ),
    # path(
    #     "skill-zone-cand-edit/<int:sz_cand_id>/",
    #     views.skill_zone_cand_edit,
    #     name="skill-zone-cand-edit",
    # ),
    path(
        "skill-zone-cand-edit/<int:pk>/",
        skill_zone.SkillZoneCandidateFormView.as_view(),
        name="skill-zone-cand-edit",
    ),
    path(
        "skill-zone-cand-filter/",
        views.skill_zone_cand_filter,
        name="skill-zone-cand-filter",
    ),
    path(
        "skill-zone-cand-archive/<int:sz_cand_id>/",
        views.skill_zone_cand_archive,
        name="skill-zone-cand-archive",
    ),
    # path("to-skill-zone/<int:cand_id>", views.to_skill_zone, name="to-skill-zone"),
    path(
        "to-skill-zone/<int:cand_id>/",
        candidates.ToSkillZoneFormView.as_view(),
        name="to-skill-zone",
    ),
    path(
        "add-to-rejected-candidates/",
        candidates.RejectReasonFormView.as_view(),
        name="add-to-rejected-candidates",
    ),
    path(
        "delete-candidate-rejection/<int:rej_id>/",
        views.delete_candidate_rejection,
        name="delete-candidate-rejection",
    ),
    path(
        "skill-zone-cand-delete/<int:sz_cand_id>/",
        views.skill_zone_cand_delete,
        name="skill-zone-cand-delete",
    ),
    path("get-template/<int:obj_id>/", actions.get_template, name="get-template"),
    path("get-mail-preview/", actions.get_mail_preview, name="get-mail-preview"),
    path("get-template-hint/", actions.get_template_hint, name="get-template-hint"),
    path(
        "create-candidate-rating/<int:cand_id>/",
        views.create_candidate_rating,
        name="create-candidate-rating",
    ),
    path(
        "update-candidate-rating/<int:cand_id>/",
        views.update_candidate_rating,
        name="update-candidate-rating",
    ),
    path(
        "open-recruitments/",
        views.open_recruitments,
        name="open-recruitments",
    ),
    path(
        "recruitment-details/<int:id>/",
        views.recruitment_details,
        name="recruitment-details",
    ),
    path(
        "add-more-files/<int:id>/",
        views.add_more_files,
        name="add-more-files",
    ),
    path(
        "add-more-files-individual/<int:id>/",
        views.add_more_individual_files,
        name="add-more-files-individual",
    ),
    path(
        "delete-stage-note-file/<int:id>/",
        views.delete_stage_note_file,
        name="delete-stage-note-file",
    ),
    path(
        "delete-individual-note-file/<int:id>/",
        views.delete_individual_note_file,
        name="delete-individual-note-file",
    ),
    # path("get-mail-log-rec/", views.get_mail_log, name="get-mail-log-rec"),
    path(
        "candidate-self-tracking/",
        views.candidate_self_tracking,
        name="candidate-self-tracking",
    ),
    path(
        "candidate-self-tracking-rating-option/",
        views.candidate_self_tracking_rating_option,
        name="candidate-self-tracking-rating-option",
    ),
    path(
        "candidate-self-status-tracking/",
        views.candidate_self_status_tracking,
        name="candidate-self-status-tracking",
    ),
    path(
        "candidate-self-status-tracking/<int:cand_id>/",
        views.candidate_self_status_tracking_managers_view,
        name="candidate-self-status-tracking",
    ),
    path(
        "candidate-login/",
        views.candidate_login,
        name="candidate-login",
    ),
    path(
        "create-reject-reason/", views.create_reject_reason, name="create-reject-reason"
    ),
    path(
        "candidate-reject-reasons-list/",
        candidate_reject_reason.RejectReasonListView.as_view(),
        name="candidate-reject-reasons-list",
    ),
    path(
        "candidate-reject-reasons-nav/",
        candidate_reject_reason.RejectReasonNav.as_view(),
        name="candidate-reject-reasons-nav",
    ),
    path(
        "create-reject-reason-view/",
        candidate_reject_reason.RejectReasonFormView.as_view(),
        name="create-reject-reason-view",
    ),
    path(
        "update-reject-reason-view/<int:pk>/",
        candidate_reject_reason.RejectReasonFormView.as_view(),
        name="update-reject-reason-view",
    ),
    path(
        "delete-reject-reasons/",
        views.delete_reject_reason,
        name="delete-reject-reasons",
    ),
    path(
        "recruitment-settings-view/",
        settings_tabs.RecruitmentSettingsView.as_view(),
        name="recruitment-settings-view",
    ),
    path(
        "recruitment-settings-tab-view/",
        settings_tabs.RecruitmentSettingsTabView.as_view(),
        name="recruitment-settings-tab-view",
    ),
    path(
        "recruitment-settings-reject-reason-tab/",
        settings_tabs.RecruitmentSettingsRejectReasonTab.as_view(),
        name="recruitment-settings-reject-reason-tab",
    ),
    path(
        "recruitment-settings-skill-tab/",
        settings_tabs.RecruitmentSettingsSkillTab.as_view(),
        name="recruitment-settings-skill-tab",
    ),
    path(
        "recruitment-settings-stage-tab/",
        settings_tabs.RecruitmentSettingsStageTab.as_view(),
        name="recruitment-settings-stage-tab",
    ),
    path(
        "resume-completion/",
        views.resume_completion,
        name="resume-completion",
    ),
    path("candidate-view/", candidates.CandidatesView.as_view(), name="candidate-view"),
    path("list-candidate/", candidates.ListCandidates.as_view(), name="list-candidate"),
    path("card-candidate/", candidates.CardCandidates.as_view(), name="card-candidate"),
    path("nav-candidate/", candidates.CandidateNav.as_view(), name="nav-candidate"),
    path("export/", candidates.ExportView.as_view(), name="export"),
    path(
        "candidate-detail/<int:pk>/",
        candidates.CandidateDetail.as_view(),
        name="candidate-detail",
    ),
    # path(
    #     "check-vaccancy/",
    #     views.check_vaccancy,
    #     name="check-vaccancy",
    # ),
    # path(
    #     "add-candidate-reject/",
    #     candidates.AddToRejectedCandidatesView.as_view(),
    #     name="add-candidate-reject",
    # ),
    path(
        "recruitment-view/",
        recruitment_view.RecruitmentView.as_view(),
        name="recruitment-view",
    ),
    path(
        "list-recruitment/",
        recruitment_view.RecruitmentList.as_view(),
        name="list-recruitment",
    ),
    path(
        "nav-recruitment/",
        recruitment_view.RecruitmentNav.as_view(),
        name="nav-recruitment",
    ),
    path(
        "recruitment-detail-view/<int:pk>/",
        recruitment_view.RecruitmentDetailView.as_view(),
        name="recruitment-detail-view",
    ),
    path("stage-view/", stage_view.StageView.as_view(), name="rec-stage-view"),
    path("list-stage/", stage_view.StageList.as_view(), name="list-stage"),
    path("nav-stage/", stage_view.StageNav.as_view(), name="nav-stage"),
    path(
        "stage-detail-view/<int:pk>/",
        stage_view.StageDetailView.as_view(),
        name="stage-detail-view",
    ),
    # path(
    #     "add-skill-form/",
    #     recruitment_view.RecruitmentNewSkillForm.as_view(),
    #     name="add-skill-form",
    # ),
    path("skills-list-view/", skills.SkillsListView.as_view(), name="skills-list-view"),
    path("skills-nav-view/", skills.SkillsNavView.as_view(), name="skills-nav-view"),
    path(
        "settings/skills-view/",
        views.skills_view,
        name="skills-view",
    ),
    path(
        "create-skills/",
        views.create_skills,
        name="create-skills",
    ),
    path(
        "settings-create-skills/",
        skills.SkillsCreateForm.as_view(),
        name="settings-create-skills",
    ),
    path(
        "settings-update-skills/<int:pk>/",
        skills.SkillsCreateForm.as_view(),
        name="settings-update-skills",
    ),
    path(
        "delete-skills/",
        views.delete_skills,
        name="delete-skills",
    ),
    path(
        "add-bulk-resume/",
        views.add_bulk_resumes,
        name="add-bulk-resume",
    ),
    path(
        "view-bulk-resume/",
        views.view_bulk_resumes,
        name="view-bulk-resume",
    ),
    path(
        "delete-resume-file/",
        views.delete_resume_file,
        name="delete-resume-file",
    ),
    path(
        "matching-resumes/<int:rec_id>/",
        views.matching_resumes,
        name="matching-resumes",
    ),
    path(
        "matching-resume-completion/",
        views.matching_resume_completion,
        name="matching-resume-completion",
    ),
    path(
        "candidate-reject-reasons/",
        views.candidate_reject_reasons,
        name="candidate-reject-reasons",
    ),
    path(
        "hired-candidate-chart/",
        views.hired_candidate_chart,
        name="hired-candidate-chart",
    ),
    path(
        "self-tracking-feature/",
        views.self_tracking_feature,
        name="self-tracking-feature",
    ),
    path(
        "candidate-document-request/",
        views.candidate_document_request,
        name="candidate-document-request",
    ),
    path(
        "candidate-file-upload/<int:id>/",
        views.file_upload,
        name="candidate-file-upload",
    ),
    path("candidate-view-file/<int:id>/", views.view_file, name="candidate-view-file"),
    path(
        "candidate-document-create/<int:id>/",
        views.document_create,
        name="candidate-document-create",
    ),
    path(
        "candidate-update-document-title/<int:id>/",
        views.update_document_title,
        name="candidate-update-document-title",
    ),
    path(
        "candidate-document-approve/<int:id>/",
        views.document_approve,
        name="candidate-document-approve",
    ),
    path(
        "candidate-document-reject/<int:id>/",
        views.document_reject,
        name="candidate-document-reject",
    ),
    path(
        "candidate-document-delete/<int:id>/",
        views.document_delete,
        name="candidate-document-delete",
    ),
    path(
        "candidate-add-notes/<int:cand_id>/",
        views.candidate_add_notes,
        name="candidate-add-notes",
    ),
    path(
        "employee-interview-tab/",
        views.employee_profile_interview_tab,
        name="employee-interview-tab",
    ),
    path("cbv-pipeline/", pipeline.PipelineView.as_view(), name="cbv-pipeline"),
    path(
        "cbv-pipeline-tab/",
        pipeline.RecruitmentTabView.as_view(),
        name="cbv-pipeline-tab",
    ),
    # path(
    #     "cbv-pipeline-tab-list/",
    #     pipeline.RecruitmentTabView.as_view(),
    #     name="cbv-pipeline-tab-list",
    # ),
    path("cbv-pipeline-nav/", pipeline.PipelineNav.as_view(), name="cbv-pipeline-nav"),
    path(
        "get-stages/<int:rec_id>/",
        pipeline.GetStages.as_view(),
        name="get-stages-recruitment",
    ),
    path(
        "candidate-lists-cbv/<int:stage_id>/",
        pipeline.CandidateList.as_view(),
        name="candidate-lists-cbv",
    ),
    path(
        "candidate-lists-cbv/<int:stage_id>/<int:rec_id>/",
        pipeline.CandidateList.as_view(),
        name="candidate-lists-cbv",
    ),
    path(
        "candidate-card-cbv/<int:pk>/",
        pipeline.CandidateCard.as_view(),
        name="candidate-card-cbv",
    ),
    path(
        "recruitment-pipeline-shell/<int:rec_id>/",
        pipeline.RecruitmentPipelineContentShell.as_view(),
        name="recruitment-pipeline-shell",
    ),
    path(
        "cbv-change-stage/<int:pk>/",
        pipeline.ChangeStage.as_view(),
        name="cbv-change-stage",
    ),
    # Linkedin Integration urls
    path(
        "linkedin-integration-setting/",
        cbvs.LinkedinSettingSectionView.as_view(),
        name="linkedin-integration-setting",
    ),
    path(
        "linkedin-setting-nav/",
        cbvs.LinkedInSettingNavView.as_view(),
        name="linkedin-setting-nav",
    ),
    path(
        "linkedin-setting-list/",
        cbvs.LinkedInSettingListView.as_view(),
        name="linkedin-setting-list",
    ),
    path(
        "create-linkedin-account/",
        cbvs.LinkedInAccountFormView.as_view(),
        name="create-linkedin-account",
    ),
    path(
        "update-linkedin-account/<int:pk>/",
        cbvs.LinkedInAccountFormView.as_view(),
        name="update-linkedin-account",
    ),
    path(
        "delete-linkedin-account/<int:pk>/",
        linkedin.delete_linkedin_account,
        name="delete-linkedin-account",
    ),
    path(
        "update-isactive-linkedin-account/<int:obj_id>/",
        linkedin.update_isactive_linkedin,
        name="update-isactive-linkedin-account",
    ),
    path(
        "val-linkedin/<int:pk>/", linkedin.validate_linkedin_token, name="val-linkedin"
    ),
    # ── Recruitment Modern Dashboard ─────────────────────────────────────────
    path(
        "dashboard/",
        rec_dashboard.recruitment_dashboard_view,
        name="recruitment-dashboard",
    ),
    path(
        "dashboard/api/kpi/",
        rec_dashboard.recruitment_kpi_data,
        name="recruitment-dashboard-kpi",
    ),
    path(
        "dashboard/api/offer-status/",
        rec_dashboard.recruitment_offer_status,
        name="recruitment-dashboard-offer-status",
    ),
    path(
        "dashboard/api/stage-summary/",
        rec_dashboard.recruitment_stage_summary,
        name="recruitment-dashboard-stage-summary",
    ),
    path(
        "dashboard/api/pipeline/",
        rec_dashboard.recruitment_pipeline_data,
        name="recruitment-dashboard-pipeline",
    ),
    path(
        "dashboard/api/source-quality/",
        rec_dashboard.recruitment_source_quality,
        name="recruitment-dashboard-source-quality",
    ),
    path(
        "dashboard/api/time-to-hire/",
        rec_dashboard.recruitment_time_to_hire,
        name="recruitment-dashboard-time-to-hire",
    ),
    path(
        "dashboard/api/managers/",
        rec_dashboard.recruitment_managers_data,
        name="recruitment-dashboard-managers",
    ),
    path(
        "dashboard/api/source-of-hire/",
        rec_dashboard.recruitment_source_of_hire,
        name="recruitment-dashboard-source",
    ),
    path(
        "dashboard/api/upcoming-interviews/",
        rec_dashboard.recruitment_upcoming_interviews,
        name="recruitment-dashboard-interviews",
    ),
    path(
        "dashboard/api/open-by-dept/",
        rec_dashboard.recruitment_open_by_department,
        name="recruitment-dashboard-open-dept",
    ),
    path(
        "dashboard/api/stage-conversion/",
        rec_dashboard.recruitment_stage_conversion,
        name="recruitment-dashboard-conversion",
    ),
    path(
        "dashboard/api/source-conversion/",
        rec_dashboard.recruitment_source_conversion,
        name="recruitment-dashboard-source-conv",
    ),
    path(
        "dashboard/api/joinings/",
        rec_dashboard.recruitment_joinings_monthly,
        name="recruitment-dashboard-joinings",
    ),
]
