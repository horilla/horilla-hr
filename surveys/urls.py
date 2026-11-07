"""URLs of the surveys app."""

from django.urls import path

from surveys import public, views
from surveys.cbv import surveys as cbv

urlpatterns = [
    # the employee's personal link, no login
    path("s/<str:token>/", public.answer, name="survey-answer"),
    # HR
    path("dashboard/", views.dashboard, name="surveys-dashboard"),
    path("dashboard/data/", views.dashboard_data, name="surveys-dashboard-data"),
    path("", cbv.SurveysView.as_view(), name="surveys-view"),
    path("nav/", cbv.SurveysNav.as_view(), name="surveys-nav"),
    path("list/", cbv.SurveysList.as_view(), name="surveys-list"),
    path("create/", cbv.SurveyFormView.as_view(), name="survey-create"),
    path("<int:pk>/edit/", cbv.SurveyFormView.as_view(), name="survey-edit"),
    path("<int:pk>/", views.survey_detail, name="survey-detail"),
    path("<int:pk>/tab/questions/", views.questions_tab, name="survey-questions-tab"),
    path("<int:pk>/tab/audience/", views.audience_tab, name="survey-audience-tab"),
    path("<int:pk>/tab/results/", views.results_tab, name="survey-results-tab"),
    path("<int:pk>/reorder/", views.reorder_questions, name="survey-reorder"),
    path("<int:pk>/open/", views.open_survey, name="survey-open"),
    path("<int:pk>/close/", views.close_survey, name="survey-close"),
    path("<int:pk>/remind/", views.remind, name="survey-remind"),
    path("<int:pk>/export/", views.export_results, name="survey-export"),
    path(
        "question/add/",
        cbv.SurveyQuestionFormView.as_view(),
        name="survey-question-add",
    ),
    path(
        "question/<int:pk>/edit/",
        cbv.SurveyQuestionFormView.as_view(),
        name="survey-question-edit",
    ),
    path(
        "question/<int:pk>/delete/",
        views.delete_question,
        name="survey-question-delete",
    ),
]
