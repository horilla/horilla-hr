"""The page an employee answers on - reached by the personal link, no login.

/surveys/s/<token>/ shows the questionnaire with whatever was saved before;
every change is autosaved (POST ?autosave=1 from htmx), "Submit" validates
everything and closes the response. An anonymous survey forgets which
invitation the response came from at that moment, in the same transaction.

Unknown tokens are rate-limited per client address so the token space cannot
be probed: TOKEN_PROBE_LIMIT misses within TOKEN_PROBE_WINDOW seconds answer
429 for the rest of the window.
"""

import hmac

from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from surveys import answers as answer_rules
from surveys.models import SurveyAnswer, SurveyInvitation, SurveyResponse

TOKEN_PROBE_LIMIT = 30
TOKEN_PROBE_WINDOW = 600


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (
        forwarded.split(",")[0].strip()
        if forwarded
        else request.META.get("REMOTE_ADDR", "")
    )


def find_invitation(request, token):
    """The invitation for `token`, or None after counting a miss against the client."""
    key = f"surveys:probe:{client_ip(request)}"
    if cache.get(key, 0) >= TOKEN_PROBE_LIMIT:
        return None, True
    # Constant-time compare on the candidate row, so a near-miss costs the same
    candidate = (
        SurveyInvitation._base_manager.filter(token=token)
        .select_related("survey", "employee")
        .first()
    )
    if candidate is not None and hmac.compare_digest(candidate.token, token):
        return candidate, False
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, TOKEN_PROBE_WINDOW)
    return None, False


@require_http_methods(["GET", "POST"])
def answer(request, token):
    invitation, throttled = find_invitation(request, token)
    if throttled:
        return HttpResponse(_("Too many attempts. Try again later."), status=429)
    if invitation is None:
        return render(request, "surveys/public/not_found.html", status=404)

    survey = invitation.survey
    questions = list(survey.questions.all())
    autosave = request.GET.get("autosave") == "1"

    if invitation.submitted():
        return render(
            request, "surveys/public/done.html", {"survey": survey, "already": True}
        )
    if not survey.is_accepting():
        return render(request, "surveys/public/closed.html", {"survey": survey})

    response = getattr(invitation, "response", None)

    if request.method == "POST":
        values, errors = answer_rules.collect(
            questions, request.POST, strict=not autosave
        )
        with transaction.atomic():
            if response is None:
                response = SurveyResponse.objects.create(
                    survey=survey, invitation=invitation
                )
                SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                    status=SurveyInvitation.STATUS_STARTED
                )
            for question, value in values.items():
                SurveyAnswer.objects.update_or_create(
                    response=response, question=question, defaults={"value": value}
                )
            if autosave:
                return JsonResponse(
                    {"saved": True, "at": timezone.localtime().strftime("%H:%M")}
                )
            if not errors:
                now = timezone.now()
                SurveyResponse.objects.filter(pk=response.pk).update(
                    is_draft=False,
                    submitted_at=now,
                    invitation=None if survey.is_anonymous else invitation,
                )
                SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                    status=SurveyInvitation.STATUS_SUBMITTED, submitted_at=now
                )
                return render(request, "surveys/public/done.html", {"survey": survey})
        saved = {q.pk: v for q, v in values.items()}
    else:
        errors = {}
        saved = response.answers_by_question() if response else {}

    return render(
        request,
        "surveys/public/answer.html",
        {
            "survey": survey,
            "invitation": invitation,
            "questions": [
                {
                    "q": question,
                    "name": answer_rules.field_name(question),
                    "value": saved.get(question.pk),
                    "error": errors.get(question),
                    "choices": question.choices(),
                }
                for question in questions
            ],
            "answered": sum(
                1 for q in questions if saved.get(q.pk) not in (None, "", [])
            ),
            "errors": errors,
        },
    )
