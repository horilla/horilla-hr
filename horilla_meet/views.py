import os
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from base.backends import logger
from horilla.decorators import (
    check_integration_enabled,
    login_required,
    permission_required,
)
from horilla.http.response import HorillaRedirect
from horilla_meet.methods import get_google_credentials
from horilla_meet.models import *


@login_required
def google_authenticate(request):

    cred = GoogleCloudCredential.objects.filter(
        company_id=request.user.employee_get.get_company()
    ).first()
    if not cred:
        messages.error(request, _("Google Cloud Credential not found."))
        return redirect("gmeet-view")

    redirect_uri = request.build_absolute_uri("/meet/auth-callback/")
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cred.client_id,
                "client_secret": cred.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token",
                "redirect_uris": cred.redirect_uri_list,
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/meetings.space.created",
        ],
        redirect_uri=redirect_uri,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = flow.code_verifier
    return redirect(auth_url)


@login_required
def google_auth_callback(request):

    state = request.session.pop("oauth_state", None)
    if not state or state != request.GET.get("state"):
        return HttpResponse("Invalid state", status=400)

    cred = GoogleCloudCredential.objects.filter(
        company_id=request.user.employee_get.get_company()
    ).first()

    redirect_uri = request.build_absolute_uri("/meet/auth-callback/")
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cred.client_id,
                "client_secret": cred.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token",
                "redirect_uris": cred.redirect_uri_list,
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/meetings.space.created",
        ],
        redirect_uri=redirect_uri,
    )

    if settings.DEBUG and not request.is_secure():
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    flow.code_verifier = request.session.pop("oauth_code_verifier", None)

    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    GoogleCredential.from_google_credentials(request.user.employee_get, credentials)
    messages.success(request, _("Successfully authenticated with Google credentials."))

    return redirect("gmeet-view")


@login_required
@permission_required("horilla_meet.delete_googlecloudcredentials")
def delete_google_credentials(request, obj_id):
    try:
        GoogleCloudCredential.objects.get(id=obj_id).delete()
        messages.success(request, _("Google Cloud Credential deleted successfully."))
        return HorillaRedirect(request)
    except GoogleCloudCredential.DoesNotExist:
        messages.error(request, _("Google Cloud Credential not found."))
        return HorillaRedirect(request)
    except Exception as e:
        messages.error(
            request, _("Error deleting Google Cloud Credential: %(e)s") % {"e": e}
        )
        return HorillaRedirect(request)


@login_required
@permission_required("horilla_meet.add_googlemeeting")
@check_integration_enabled(app_name="horilla_meet")
def create_google_meet_link(request):
    google_credetial = GoogleCredential.objects.filter(
        employee_id=request.user.employee_get
    )
    if not google_credetial.exists():
        return redirect("authenticate-gmeet")
    messages.error(
        request, _("Google Credential not found. Please authenticate first.")
    )
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@permission_required("horilla_meet.delete_googlemeeting")
@check_integration_enabled(app_name="horilla_meet")
def delete_google_meet(request, id):
    meeting = get_object_or_404(GoogleMeeting, id=id)
    try:
        event_id = meeting.event_id
        if event_id:
            credentials = get_google_credentials(request)

            service = build("calendar", "v3", credentials=credentials)
            service.events().delete(calendarId="primary", eventId=event_id).execute()

        meeting.delete()
        messages.success(request, _("Google Meet deleted successfully."))
        if request.GET.get("detail_view", False):
            return redirect("gmeet-list-view")
        return HttpResponse("")
    except GoogleMeeting.DoesNotExist:
        messages.error(request, _("Google Meeting not found."))
        return HttpResponse("")
    except Exception as e:
        messages.error(request, _("Error deleting Google Meeting: %(e)s") % {"e": e})
        return HttpResponse("")


if apps.is_installed("recruitment"):
    from recruitment.models import InterviewSchedule

    @login_required
    @permission_required("horilla_meet.add_googlemeeting")
    @check_integration_enabled(app_name="horilla_meet")
    def create_inteview_google_meeting(request):
        id = request.GET.get("id")
        try:
            interview = get_object_or_404(InterviewSchedule, id=id)
        except Exception as e:
            logger.error(f"Error fetching interview: {e}")
            return JsonResponse({"error": str(e)}, status=500)

        title = f"Interview for {interview.candidate_id}"
        description = interview.description or f"Interview for {interview.candidate_id}"
        start_time = datetime.combine(
            interview.interview_date, interview.interview_time
        )
        attendees = [
            employee.get_mail()
            for employee in interview.employee_id.all()
            if employee.get_mail()
        ]
        attendees.append(interview.candidate_id.get_email())

        interview_meeting_link = InterviewMeetingLink.objects.filter(
            interview=interview
        ).first()
        if interview_meeting_link:
            meeting_id = interview_meeting_link.meeting.id
        else:
            meeting_id = None

        try:
            meeting, created = GoogleMeeting.objects.update_or_create(
                id=meeting_id,
                defaults={
                    "title": title,
                    "start_time": start_time,
                    "description": description,
                    "attendees": attendees,
                },
            )

            meeting.refresh_from_db()
            if not interview_meeting_link:
                InterviewMeetingLink.objects.create(
                    interview=interview, meeting=meeting
                )

            if created:
                messages.success(request, _("Meeting created successfully"))
            else:
                messages.success(request, _("Meeting updated successfully"))

            return JsonResponse({"success": "true"})

        except Exception as e:
            logger.error(f"Error creating/updating Google Meeting: {e}")
            messages.error(
                _("Error creating/updating Google Meeting: %(error)s") % {"error": e}
            )
            return JsonResponse({"error": str(e)}, status=500)


if apps.is_installed("pms"):
    from pms.models import Meetings

    @login_required
    @permission_required("horilla_meet.add_googlemeeting")
    @check_integration_enabled(app_name="horilla_meet")
    def create_pms_google_meeting(request):
        id = request.GET.get("id")
        try:
            meeting = get_object_or_404(Meetings, id=id)
        except Exception as e:
            logger.error(f"Error fetching interview: {e}")
            return JsonResponse({"error": str(e)}, status=500)

        title = meeting.title
        start_time = meeting.date
        description = f"Meeting for {meeting.title}"
        employees = meeting.employee_id.all() | meeting.manager.all()
        attendees = [
            employee.get_mail() for employee in employees if employee.get_mail()
        ]

        pms_meeting_link = PmsMeetingLink.objects.filter(meeting=meeting).first()

        if pms_meeting_link:
            meeting_id = pms_meeting_link.google_meeting.id
        else:
            meeting_id = None

        try:
            Gmeeting, created = GoogleMeeting.objects.update_or_create(
                id=meeting_id,
                defaults={
                    "title": title,
                    "start_time": start_time,
                    "description": description,
                    "attendees": attendees,
                },
            )

            Gmeeting.refresh_from_db()
            if not pms_meeting_link:
                PmsMeetingLink.objects.create(meeting=meeting, google_meeting=Gmeeting)

            if created:
                messages.success(request, _("Meeting created successfully"))
            else:
                messages.success(request, _("Meeting updated successfully"))

            return JsonResponse({"success": "true"})

        except Exception as e:
            logger.error(f"Error creating/updating Google Meeting: {e}")
            messages.error(
                _("Error creating/updating Google Meeting: %(error)s") % {"error": e}
            )
            return JsonResponse({"error": str(e)}, status=500)
