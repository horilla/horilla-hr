"""The page an employee answers on - reached by the personal link, no login.

/surveys/s/<token>/ shows the questionnaire with whatever was saved before;
every change is autosaved (POST ?autosave=1 from htmx), "Submit" validates
everything and closes the response. An anonymous survey forgets which
invitation the response came from at that moment, in the same transaction.

Unknown tokens are rate-limited per client address so the token space cannot
be probed: after TOKEN_PROBE_LIMIT misses within TOKEN_PROBE_WINDOW seconds a
further miss answers 429 for the rest of the window. A valid link is never
throttled: the count is of misses, and an address that others share (an office
behind one router) must not lock people out of their own link.

Everything that changes a response runs under a row lock on the invitation, so
two requests for the same link (a double click, two tabs) are served one after
the other instead of racing to create the same response.
"""

import hmac
import re
from functools import wraps

from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import formats, timezone
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from horilla.client_ip import client_ip
from surveys import answers as answer_rules
from surveys.models import (
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)

TOKEN_PROBE_LIMIT = 30
TOKEN_PROBE_WINDOW = 600

# What secrets.token_urlsafe produces; anything else cannot be a link of ours, so
# it is turned away before the database sees it (a NUL byte, a 10 kB path)
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{20,64}")


def private_page(view):
    """Every answer of the public page is for one person only.

    The link is the secret, so nothing may keep a copy of the page (a shared
    computer's cache, a proxy) and nothing may pass the link on in a Referer
    header when the page links elsewhere.
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        add_never_cache_headers(response)
        response["Referrer-Policy"] = "no-referrer"
        response["X-Robots-Tag"] = "noindex"
        return response

    return wrapped


def _show(request, template, survey, context=None, status=None):
    """Render a public page with the name of the company that sent the survey.

    The name tells the person the page is the one their own company asked them to
    open, not a look-alike.
    """
    context = {
        "survey": survey,
        "company_name": survey.company_label(),
        **(context or {}),
    }
    return render(request, template, context, status=status)


def find_invitation(request, token):
    """The invitation for `token`, or None after counting a miss against the client.

    Returns (invitation, throttled).
    """
    if TOKEN_SHAPE.fullmatch(token):
        # Constant-time compare on the candidate row, so a near-miss costs the same
        candidate = (
            SurveyInvitation._base_manager.filter(token=token)
            .select_related("survey", "employee", "employee__employee_user_id")
            .first()
        )
        if candidate is not None and hmac.compare_digest(candidate.token, token):
            return candidate, False
    key = f"surveys:probe:{client_ip(request)}"
    if cache.get(key, 0) >= TOKEN_PROBE_LIMIT:
        return None, True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, TOKEN_PROBE_WINDOW)
    return None, False


def _questions(survey):
    # Not survey.questions.all(): that manager filters by the company the visitor
    # happens to have selected in Horilla, which for a logged-in employee of
    # another company would give an empty form
    return list(SurveyQuestion._base_manager.filter(survey=survey))


def _not_saved(reason):
    """Autosave refused: the page must say so instead of showing "Saved"."""
    return JsonResponse({"saved": False, "reason": reason}, status=409)


def _not_open(request, survey):
    """Why the link cannot be answered right now: not yet, closed, or past its end."""
    return _show(
        request,
        "surveys/public/closed.html",
        survey,
        {"reason": survey.availability()},
    )


def _gone(request, autosave):
    """The person behind the link is no longer active: it works for nobody."""
    if autosave:
        return _not_saved("closed")
    return render(request, "surveys/public/not_found.html", status=404)


def _page(request, survey, invitation, questions, saved, errors):
    return _show(
        request,
        "surveys/public/answer.html",
        survey,
        {
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


@private_page
@require_http_methods(["GET", "POST"])
def answer(request, token):
    invitation, throttled = find_invitation(request, token)
    if throttled:
        return HttpResponse(_("Too many attempts. Try again later."), status=429)
    if invitation is None:
        return render(request, "surveys/public/not_found.html", status=404)

    autosave = request.GET.get("autosave") == "1"
    if request.method == "POST":
        return _save(request, invitation, autosave)

    survey = invitation.survey
    if not invitation.person_is_active():
        return _gone(request, False)
    if invitation.submitted():
        return _show(request, "surveys/public/done.html", survey, {"already": True})
    if not survey.is_accepting():
        return _not_open(request, survey)
    response = SurveyResponse._base_manager.filter(invitation=invitation).first()
    saved = response.answers_by_question() if response else {}
    return _page(request, survey, invitation, _questions(survey), saved, {})


def _save(request, invitation, autosave):
    """An autosave or the submit, under a lock on the invitation."""
    with transaction.atomic():
        # Lock the row and read it again: a request that waited here sees what
        # the one before it did (a submitted invitation, a response that exists)
        invitation = (
            SurveyInvitation._base_manager.select_for_update(of=("self",))
            .select_related("survey", "employee", "employee__employee_user_id")
            .get(pk=invitation.pk)
        )
        survey = invitation.survey
        if not invitation.person_is_active():
            return _gone(request, autosave)
        if invitation.submitted():
            if autosave:
                return _not_saved("submitted")
            return _show(request, "surveys/public/done.html", survey, {"already": True})
        if not survey.is_accepting():
            if autosave:
                return _not_saved("closed")
            return _not_open(request, survey)

        questions = _questions(survey)
        values, errors = answer_rules.collect(
            questions, request.POST, strict=not autosave
        )
        response = SurveyResponse._base_manager.filter(invitation=invitation).first()
        if response is None:
            response = SurveyResponse.start(survey, invitation)
            SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                status=SurveyInvitation.STATUS_STARTED
            )
        for question, value in values.items():
            if value is None:  # left empty: nothing is kept for it
                SurveyAnswer.objects.filter(
                    response=response, question=question
                ).delete()
            else:
                SurveyAnswer.objects.update_or_create(
                    response=response, question=question, defaults={"value": value}
                )
        if autosave:
            return JsonResponse(
                {
                    "saved": True,
                    "at": formats.time_format(timezone.localtime(), "TIME_FORMAT"),
                }
            )
        if not errors:
            moment = SurveyResponse.finish(
                response,
                invitation,
                anonymous=survey.is_anonymous,
                now=timezone.now(),
            )
            SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                status=SurveyInvitation.STATUS_SUBMITTED, submitted_at=moment
            )
            return _show(request, "surveys/public/done.html", survey)

    saved = {q.pk: v for q, v in values.items()}
    return _page(request, survey, invitation, questions, saved, errors)
