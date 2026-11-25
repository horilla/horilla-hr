from django.urls import path

from horilla_firma import views

urlpatterns = [
    path("settings/", views.settings_view, name="firma-settings"),
    path("webhook/", views.webhook, name="firma-webhook"),
    path(
        "candidate/<int:pk>/signatures/",
        views.candidate_tab,
        name="firma-candidate-tab",
    ),
    path("candidate/<int:pk>/send-form/", views.send_form, name="firma-send-form"),
    path("candidate/<int:pk>/send/", views.send_for_signature, name="firma-send"),
    path("request/<int:pk>/refresh/", views.refresh_request, name="firma-refresh"),
    path("request/<int:pk>/link/", views.link_request, name="firma-link"),
]
