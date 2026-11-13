"""URLs of the surveys app."""

from django.urls import path
from django.views.generic import RedirectView

from surveys import public, views
from surveys.cbv import surveys as cbv

urlpatterns = [
    # the employee's personal link, no login
    path("s/<str:token>/", public.answer, name="survey-answer"),
    # HR
    path("dashboard/", views.dashboard, name="surveys-dashboard"),
    path("dashboard/data/", views.dashboard_data, name="surveys-dashboard-data"),
    # Each sidebar page has a path of its own: the sidebar highlights every
    # submenu whose link the current path starts with, so a list at
    # /surveys/ would light up beside the Dashboard and the Library.
    path("", RedirectView.as_view(pattern_name="surveys-view")),
    path("surveys-view/", cbv.SurveysView.as_view(), name="surveys-view"),
    path("nav/", cbv.SurveysNav.as_view(), name="surveys-nav"),
    path("list/", cbv.SurveysList.as_view(), name="surveys-list"),
    path("card/", cbv.SurveysCard.as_view(), name="surveys-card"),
    path("create/", cbv.SurveyFormView.as_view(), name="survey-create"),
    path("<int:pk>/edit/", cbv.SurveyFormView.as_view(), name="survey-edit"),
    path("survey-detail/<int:pk>/", views.survey_detail, name="survey-detail"),
    path("<int:pk>/tabs/", cbv.SurveyTabs.as_view(), name="survey-tabs"),
    path(
        "<int:pk>/invitations/",
        cbv.InvitationsList.as_view(),
        name="survey-invitations",
    ),
    path("<int:pk>/tab/questions/", views.questions_tab, name="survey-questions-tab"),
    path("<int:pk>/tab/audience/", views.audience_tab, name="survey-audience-tab"),
    path("<int:pk>/tab/results/", views.results_tab, name="survey-results-tab"),
    path("<int:pk>/reorder/", views.reorder_questions, name="survey-reorder"),
    path("<int:pk>/open/", views.open_survey, name="survey-open"),
    path("<int:pk>/close/", views.close_survey, name="survey-close"),
    path("<int:pk>/remind/", views.remind, name="survey-remind"),
    path("<int:pk>/export/", views.export_results, name="survey-export"),
    path(
        "<int:survey_pk>/save-to-library/",
        cbv.SaveToLibraryView.as_view(),
        name="survey-save-to-library",
    ),
    # the library of questionnaires
    path("library/", cbv.LibraryView.as_view(), name="surveys-library"),
    path("library/nav/", cbv.LibraryNav.as_view(), name="surveys-library-nav"),
    path(
        "library/cards/",
        cbv.QuestionnaireCards.as_view(),
        name="surveys-library-cards",
    ),
    path(
        "library/list/",
        cbv.QuestionnaireList.as_view(),
        name="surveys-library-list",
    ),
    path(
        "library/<int:pk>/",
        cbv.QuestionnaireDetail.as_view(),
        name="questionnaire-detail",
    ),
    path(
        "library/load-standard/",
        views.load_standard_questionnaires,
        name="surveys-library-load-standard",
    ),
    path(
        "library/<int:pk>/edit/",
        cbv.QuestionnaireFormView.as_view(),
        name="questionnaire-edit",
    ),
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
