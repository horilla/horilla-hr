"""The survey page (constructor, audience, results), its actions, loading the
standard questionnaires, the dashboard."""

import csv
import json
import logging
import math
import random
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop, ngettext
from django.views.decorators.http import require_POST

from base.backends import ConfiguredEmailBackend
from horilla.decorators import login_required, permission_required
from horilla.export_safety import safe_cell
from horilla.http.response import HorillaRedirect
from horilla_views.generic.cbv.views import HorillaFormView
from notifications.signals import notify
from surveys import answers as answer_rules
from surveys.access import can_manage, can_run, can_view_results
from surveys.library import load_standard
from surveys.models import (
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
    local_midnight_of,
    with_counts,
)


log = logging.getLogger("surveys")


def _survey_for(request, pk, check):
    survey = get_object_or_404(Survey, pk=pk)
    if not check(request.user, survey):
        messages.error(request, _("You do not have permission for this."))
        return survey, HorillaRedirect(request)
    return survey, None


# --- the survey page -------------------------------------------------------


@login_required
def survey_detail(request, pk):
    Survey.close_ended()
    survey, denied = _survey_for(
        request, pk, lambda u, s: u.has_perm("surveys.view_survey") or can_manage(u, s)
    )
    if denied:
        return denied
    return render(
        request,
        "surveys/detail.html",
        {
            "survey": survey,
            "can_manage": can_manage(request.user, survey),
            "can_run": can_run(request.user, survey),
            "can_results": can_view_results(request.user, survey),
            "can_save_to_library": request.user.has_perm("surveys.add_questionnaire"),
        },
    )


@login_required
def questions_tab(request, pk):
    survey, denied = _survey_for(
        request, pk, lambda u, s: u.has_perm("surveys.view_survey") or can_manage(u, s)
    )
    if denied:
        return denied
    return render(
        request,
        "surveys/tabs/questions.html",
        {"survey": survey, "can_run": can_run(request.user, survey)},
    )


MAX_ORDER_CHARS = 20_000
MAX_ORDER_ITEMS = 1_000


def _read_order(raw):
    """The question ids of a reorder request, or None when it is not a plain list."""
    if len(raw) > MAX_ORDER_CHARS:
        return None
    try:
        order = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(order, list) or len(order) > MAX_ORDER_ITEMS:
        return None
    # type(...) is int: True and 1.5 are not ids, and 1e999 never gets as far as int()
    if any(type(x) is not int or not 0 < x < 2**31 for x in order):
        return None
    return order


@login_required
@require_POST
def reorder_questions(request, pk):
    survey, denied = _survey_for(request, pk, can_run)
    if denied:
        return JsonResponse({"status": "forbidden"}, status=403)
    order = _read_order(request.POST.get("order", "[]"))
    if order is None:
        return JsonResponse({"status": "error"}, status=400)
    with transaction.atomic():
        for index, question_pk in enumerate(order, start=1):
            survey.questions.filter(pk=question_pk).update(sequence=index)
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def delete_question(request, pk):
    question = get_object_or_404(SurveyQuestion, pk=pk)
    if not can_run(request.user, question.survey):
        messages.error(request, _("You do not have permission for this."))
    elif question.survey.status != Survey.STATUS_DRAFT and question.answers.exists():
        messages.error(
            request, _("This question already has answers; close the survey instead.")
        )
    else:
        question.delete()
        messages.success(request, _("Question deleted."))
    return HorillaRedirect(request)


@login_required
def audience_tab(request, pk):
    survey, denied = _survey_for(
        request, pk, lambda u, s: u.has_perm("surveys.view_survey") or can_manage(u, s)
    )
    if denied:
        return denied
    invited = survey.invitations.count()
    return render(
        request,
        "surveys/tabs/audience.html",
        {
            "survey": survey,
            "can_manage": can_manage(request.user, survey),
            "audience_count": survey.audience_employees().count(),
            "invited": invited,
            "pending": survey.invitations.exclude(
                status=SurveyInvitation.STATUS_SUBMITTED
            ).count(),
        },
    )


# --- actions ---------------------------------------------------------------


def _answer_url(request, invitation):
    return request.build_absolute_uri(reverse("survey-answer", args=[invitation.token]))


class SendResult:
    """What happened to a batch of invitations, per person."""

    def __init__(self):
        self.emailed = 0
        self.notified_only = 0
        self.unreachable = []  # no e-mail address and no login to notify
        self.failed = []  # an e-mail was tried and did not go
        self.skipped = []  # no longer active: not written to
        self.mail_ok = False
        self.mail_down = False

    @property
    def reached(self):
        return self.emailed + self.notified_only


def _sender(request):
    """The person the notification comes from; an admin without an Employee record
    sends it as themselves."""
    try:
        return request.user.employee_get
    except Exception:
        return request.user


def _send_invitations(request, survey, invitations, *, reminder=False):
    """A Horilla notification and an e-mail with the personal link, per invitation.

    Returns a SendResult. An invitation counts as sent (sent_at / reminded_at)
    only when one channel took it: a person nobody could reach is not recorded as
    invited, so the audience list does not claim it.
    """
    result = SendResult()
    sender = _sender(request)
    backend = ConfiguredEmailBackend()
    result.mail_ok = bool(backend.configuration)
    if result.mail_ok:
        # one connection for the batch, not one per person
        try:
            backend.open()
        except Exception:
            log.exception("survey %s: the mail server could not be reached", survey.pk)
            result.mail_ok, result.mail_down = False, True
    now = timezone.now()
    field = "reminded_at" if reminder else "sent_at"
    try:
        for invitation in invitations:
            employee = invitation.employee
            name = employee.get_full_name()
            if not invitation.person_is_active():
                result.skipped.append(name)
                continue
            url = _answer_url(request, invitation)
            notified = emailed = False
            user = employee.employee_user_id
            if user:
                try:
                    notify.send(
                        sender,
                        recipient=user,
                        verb=(
                            gettext_noop(
                                "Reminder: survey '%(title)s' is waiting for your answers"
                            )
                            if reminder
                            else gettext_noop(
                                "You are invited to the survey '%(title)s'"
                            )
                        ),
                        verb_params={"title": survey.title},
                        icon="clipboard",
                        redirect=url,
                    )
                    notified = True
                except Exception:
                    log.exception(
                        "survey %s: notification for %s failed", survey.pk, name
                    )
            address = employee.get_mail()
            if result.mail_ok and address:
                context = {
                    "survey": survey,
                    "employee": employee,
                    "url": url,
                    "reminder": reminder,
                    "scheduled": survey.availability() == Survey.SCHEDULED,
                }
                try:
                    message = EmailMultiAlternatives(
                        subject=render_to_string(
                            "surveys/mail/invitation_subject.txt", context
                        ).strip(),
                        body=render_to_string("surveys/mail/invitation.txt", context),
                        from_email=backend.dynamic_from_email_with_display_name,
                        to=[address],
                        connection=backend,
                    )
                    message.attach_alternative(
                        render_to_string("surveys/mail/invitation.html", context),
                        "text/html",
                    )
                    emailed = bool(message.send())
                except Exception:
                    log.exception("survey %s: e-mail to %s failed", survey.pk, name)
                if not emailed:
                    result.failed.append(name)
            if emailed:
                result.emailed += 1
            elif notified:
                result.notified_only += 1
            elif not (result.mail_ok and address) and name not in result.failed:
                result.unreachable.append(name)
            if emailed or notified:
                SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                    **{field: now}
                )
    finally:
        if result.mail_ok:
            try:
                backend.close()
            except Exception:
                log.exception(
                    "survey %s: closing the mail connection failed", survey.pk
                )
    return result


def _names(names, limit=5):
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += " " + _("and %(n)s more") % {"n": len(names) - limit}
    return shown


def _report(request, result, *, lead=None):
    """Tell HR what happened, in numbers and names."""
    parts = []
    if result.emailed:
        parts.append(_("%(n)s emailed") % {"n": result.emailed})
    if result.notified_only:
        parts.append(_("%(n)s notified in Horilla only") % {"n": result.notified_only})
    summary = ", ".join(parts) if parts else _("Nobody was reached")
    messages.success(request, f"{lead} {summary}." if lead else f"{summary}.")
    if result.mail_down:
        messages.warning(
            request,
            _(
                "The mail server could not be reached - people were notified "
                "in Horilla only."
            ),
        )
    elif not result.mail_ok and result.reached:
        messages.warning(
            request,
            _("No mail server is set up - employees were notified in Horilla only."),
        )
    if result.failed:
        messages.error(
            request,
            _("The e-mail did not go to: %(names)s.")
            % {"names": _names(result.failed)},
        )
    if result.unreachable:
        messages.warning(
            request,
            _(
                "No e-mail address and no login to notify, so these people have "
                "no way to get their link: %(names)s. Copy their link from the "
                "Audience tab."
            )
            % {"names": _names(result.unreachable)},
        )
    if result.skipped:
        messages.info(
            request,
            _("Not written to, as they are no longer active: %(names)s.")
            % {"names": _names(result.skipped)},
        )


@login_required
@require_POST
def open_survey(request, pk):
    """Open a draft or closed survey, or - when it is open - invite the people who
    have joined the audience since."""
    survey, denied = _survey_for(request, pk, can_run)
    if denied:
        return denied
    if not survey.questions.exists():
        messages.error(
            request, _("Add at least one question before opening the survey.")
        )
        return HorillaRedirect(request)
    if survey.closes_at and survey.closes_at <= timezone.now():
        messages.error(
            request,
            _("The closing date has passed. Change it before opening the survey."),
        )
        return HorillaRedirect(request)
    already_open = survey.status == Survey.STATUS_OPEN
    if not survey.audience_employees().exists() and not survey.invitations.exists():
        messages.error(
            request,
            _("No active employee matches the audience yet. Check the audience first."),
        )
        return HorillaRedirect(request)
    with transaction.atomic():
        if not already_open:
            survey.status = Survey.STATUS_OPEN
            survey.save()
        new = survey.invite()
    if already_open and not new:
        messages.info(request, _("Everyone in the audience has been invited already."))
        return HorillaRedirect(request)
    result = _send_invitations(request, survey, new)
    _report(
        request,
        result,
        lead=(
            _("Invitations sent to new people:")
            if already_open
            else _("Survey opened:")
        ),
    )
    if survey.availability() == Survey.SCHEDULED:
        messages.info(
            request,
            _("The survey opens on %(date)s; until then the link says so.")
            % {
                "date": formats.date_format(
                    timezone.localtime(survey.opens_at), "d.m.Y H:i"
                )
            },
        )
    return HorillaRedirect(request)


@login_required
@require_POST
def close_survey(request, pk):
    survey, denied = _survey_for(request, pk, can_run)
    if denied:
        return denied
    dropped = survey.drop_anonymous_drafts()
    Survey.objects.filter(pk=pk).update(status=Survey.STATUS_CLOSED)
    messages.success(request, _("Survey closed."))
    if dropped:
        messages.info(
            request,
            ngettext(
                "%(n)s unfinished answer of this anonymous survey was deleted.",
                "%(n)s unfinished answers of this anonymous survey were deleted.",
                dropped,
            )
            % {"n": dropped},
        )
    return HorillaRedirect(request)


@login_required
@require_POST
def remind(request, pk):
    survey, denied = _survey_for(request, pk, can_manage)
    if denied:
        return denied
    if not survey.is_accepting():
        messages.error(request, _("The survey is not open."))
        return HorillaRedirect(request)
    pending = survey.invitations.exclude(
        status=SurveyInvitation.STATUS_SUBMITTED
    ).select_related("employee", "employee__employee_user_id")
    result = _send_invitations(request, survey, pending, reminder=True)
    _report(request, result, lead=_("Reminder sent:"))
    return HorillaRedirect(request)


def _invitation_for_hr(request, pk, invitation_pk):
    """An invitation of survey `pk`, for the people who run surveys only: its link
    is the answer, so it is not handed to a survey's manager."""
    survey, denied = _survey_for(request, pk, can_run)
    if denied:
        return None, None, denied
    invitation = get_object_or_404(
        SurveyInvitation.objects.select_related("employee"),
        pk=invitation_pk,
        survey=survey,
    )
    return survey, invitation, None


@login_required
@require_POST
def invitation_link(request, pk, invitation_pk):
    """The personal link of one person, to copy and send by hand."""
    survey, invitation, denied = _invitation_for_hr(request, pk, invitation_pk)
    if denied:
        return JsonResponse({"status": "forbidden"}, status=403)
    if invitation.submitted():
        return JsonResponse({"status": "submitted"}, status=409)
    response = JsonResponse({"status": "ok", "url": _answer_url(request, invitation)})
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def invitation_resend(request, pk, invitation_pk):
    """Send one person their link again."""
    survey, invitation, denied = _invitation_for_hr(request, pk, invitation_pk)
    if denied:
        return denied
    if not survey.is_accepting():
        messages.error(request, _("The survey is not open."))
    elif invitation.submitted():
        messages.info(request, _("They have answered already."))
    else:
        result = _send_invitations(request, survey, [invitation], reminder=True)
        _report(request, result, lead=_("Link sent again:"))
    return HorillaRedirect(request)


# --- results ---------------------------------------------------------------


def _results(survey, department=None):
    """Per question: counts for charted types, averages for scales, texts otherwise."""
    responses = SurveyResponse.objects.filter(survey=survey, is_draft=False)
    if department:
        responses = responses.filter(
            invitation__employee__employee_work_info__department_id=department
        )
    answers = SurveyAnswer.objects.filter(response__in=responses).select_related(
        "question"
    )
    by_question = defaultdict(list)
    for answer in answers:
        if answer.value not in (None, "", []):
            by_question[answer.question_id].append(answer.value)

    results = []
    for question in survey.questions.all():
        values = by_question.get(question.pk, [])
        item = {"question": question, "answered": len(values)}
        if question.type in question.CHOICE_TYPES or question.type in (
            question.TYPE_LIKERT,
            question.TYPE_YES_NO,
            question.TYPE_RATING,
            question.TYPE_NPS,
        ):
            counts = Counter()
            for value in values:
                for v in value if isinstance(value, list) else [value]:
                    counts[str(v)] += 1
            labels = [(v, str(label)) for v, label in question.choices()]
            item["labels"] = [label for _v, label in labels]
            item["series"] = [counts.get(v, 0) for v, _label in labels]
            # Answers to options that were taken out (or renamed) after people had
            # answered still count: they are shown together, not dropped
            known = {v for v, _label in labels}
            removed = sum(n for v, n in counts.items() if v not in known)
            if removed:
                item["labels"].append(_("Other (removed options)"))
                item["series"].append(removed)
            if question.type in (
                question.TYPE_RATING,
                question.TYPE_LIKERT,
                question.TYPE_NPS,
            ):
                scores = [n for n in map(_whole, values) if n is not None]
                if scores:
                    item["average"] = round(sum(scores) / len(scores), 2)
                if question.type == question.TYPE_NPS and scores:
                    item["nps"] = _nps(question, scores)
        elif question.type == question.TYPE_NUMBER:
            numbers = [n for n in map(_number, values) if n is not None]
            if numbers:
                item.update(
                    average=round(sum(numbers) / len(numbers), 2),
                    minimum=min(numbers),
                    maximum=max(numbers),
                )
            item["texts"] = [str(v) for v in values]
        else:
            item["texts"] = [str(v) for v in values]
        if survey.is_anonymous and "texts" in item:
            # not in the order they came in, which is the order of the audience list
            item["texts"].sort(key=str.casefold)
        results.append(item)
    return responses.count(), results


def _number(value):
    """A stored answer as a finite number, or None: a value that no longer reads as
    one (the question's type was changed) must not take the results page down."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _whole(value):
    number = _number(value)
    return None if number is None else int(number)


def _nps(question, scores):
    """Net Promoter Score of the answers: % of promoters minus % of detractors."""
    promoters = sum(score >= question.NPS_PROMOTER_FROM for score in scores)
    detractors = sum(score <= question.NPS_DETRACTOR_TILL for score in scores)
    return {
        "score": round(100 * (promoters - detractors) / len(scores)),
        "promoters": promoters,
        "passives": len(scores) - promoters - detractors,
        "detractors": detractors,
    }


@login_required
def results_tab(request, pk):
    Survey.close_ended()  # a survey past its closing time counts as closed here
    survey, denied = _survey_for(request, pk, can_view_results)
    if denied:
        return denied
    department = request.GET.get("department", "")
    # a department is a number; an anonymous survey is never cut by department
    department = (
        department
        if department.isdigit() and len(department) < 10 and not survey.is_anonymous
        else None
    )
    from base.models import Department

    context = {
        "survey": survey,
        "departments": Department.objects.all() if not survey.is_anonymous else [],
        "department": department,
        "hold": survey.results_hold(),
        "withheld": survey.results_withheld(),
        "needed": survey.min_responses(),
    }
    if context["withheld"]:
        # too few answers to show without pointing at the people who gave them
        context.update(total=survey.submitted_count(), results=[], chart_data=[])
        return render(request, "surveys/tabs/results.html", context)

    total, results = _results(survey, department)
    context.update(
        total=total,
        results=results,
        # handed to the template as data (json_script), never written into the script
        chart_data=[
            {
                "id": r["question"].pk,
                "labels": r.get("labels"),
                "series": r.get("series"),
                "type": r["question"].type,
            }
            for r in results
            if "series" in r
        ],
    )
    return render(request, "surveys/tabs/results.html", context)


@login_required
def export_results(request, pk):
    Survey.close_ended()  # a survey past its closing time counts as closed here
    survey, denied = _survey_for(request, pk, can_view_results)
    if denied:
        return denied
    hold = survey.results_hold()
    if hold:
        if hold == Survey.HOLD_UNTIL_CLOSED:
            text = _(
                "The export of an anonymous survey is available once the survey is closed."
            )
        else:
            text = ngettext(
                "The export is available once %(n)s person has answered.",
                "The export is available once %(n)s people have answered.",
                survey.min_responses(),
            ) % {"n": survey.min_responses()}
        messages.info(request, text)
        return HorillaRedirect(request)
    questions = list(survey.questions.all())
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="survey-{survey.pk}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    # Every cell goes through safe_cell: what people typed must not run as a formula
    # when HR opens the file in a spreadsheet
    if survey.is_anonymous:
        header = ["#"]
    else:
        header = ["#", _("Submitted at"), _("Employee"), _("Department")]
    writer.writerow([safe_cell(c) for c in header + [q.question for q in questions]])
    rows = list(
        SurveyResponse.objects.filter(survey=survey, is_draft=False)
        .select_related("invitation__employee__employee_work_info__department_id")
        .prefetch_related("answers")
        .order_by("pk" if survey.is_anonymous else "submitted_at")
    )
    if survey.is_anonymous:
        # no time, and not in the order of submission either: the audience list
        # shows who answered when, and the same order would line the two up
        random.shuffle(rows)
    for index, row in enumerate(rows, start=1):
        values = row.answers_by_question()
        line = [index]
        if not survey.is_anonymous:
            employee = row.invitation.employee if row.invitation else None
            line += [
                (
                    timezone.localtime(row.submitted_at).strftime("%Y-%m-%d %H:%M")
                    if row.submitted_at
                    else ""
                ),
                employee.get_full_name() if employee else "",
                str(employee.get_department() or "") if employee else "",
            ]
        line += [answer_rules.label(q, values.get(q.pk)) for q in questions]
        writer.writerow([safe_cell(c) for c in line])
    return response


# --- library ---------------------------------------------------------------


@login_required
@require_POST
@permission_required("surveys.add_questionnaire")
def load_standard_questionnaires(request):
    added = load_standard()
    if added:
        messages.success(
            request, _("%(n)s standard questionnaire(s) added.") % {"n": len(added)}
        )
    else:
        messages.info(request, _("The standard questionnaires are already there."))
    if request.headers.get("HX-Request"):
        # the Actions menu of the library: show the messages; the cards and the
        # list reload themselves (their .reload-record button)
        return HorillaFormView.HttpResponse()
    return HorillaRedirect(request)


# --- dashboard -------------------------------------------------------------


@login_required
@permission_required("surveys.view_survey")
def dashboard(request):
    tiles = [
        ("kOpen", _("Open surveys"), "clipboard-outline", "#3b82f61f"),
        ("kInvited", _("Invited (open surveys)"), "people-outline", "#b71db01f"),
        ("kAnswered", _("Answered"), "checkmark-done-outline", "#1cba5121"),
        ("kRate", _("Response rate"), "trending-up-outline", "#ea7f2f2e"),
    ]
    return render(request, "surveys/dashboard.html", {"tiles": tiles})


@login_required
@permission_required("surveys.view_survey")
def dashboard_data(request):
    Survey.close_ended()
    surveys = Survey.objects.all()
    open_surveys = surveys.filter(status=Survey.STATUS_OPEN)
    invitations = SurveyInvitation.objects.filter(survey__in=open_surveys)
    submitted = invitations.filter(status=SurveyInvitation.STATUS_SUBMITTED)
    # days are the local ones: a response sent late in the evening belongs to that
    # day for the people who read the chart, not to the next day in UTC
    zone = timezone.get_current_timezone()
    first_day = timezone.localdate() - timedelta(days=30)
    since = local_midnight_of(first_day)
    per_day = (
        SurveyResponse.objects.filter(is_draft=False, submitted_at__gte=since)
        .annotate(day=TruncDate("submitted_at", tzinfo=zone))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )
    per_department = (
        SurveyInvitation.objects.filter(survey__in=open_surveys)
        .values("employee__employee_work_info__department_id__department")
        .annotate(
            total=Count("id"),
            done=Count("id", filter=Q(status=SurveyInvitation.STATUS_SUBMITTED)),
        )
        .order_by("-total")
    )
    counts = {r["day"]: r["n"] for r in per_day}
    recent = [
        {
            "id": s.pk,
            "title": s.title,
            "status": dict(Survey.STATUSES)[s.shown_status()],
            "status_code": s.shown_status(),
            "answered": s.answered_count(),
            "invited": s.invited_count(),
            "rate": s.response_rate(),
            "url": s.get_detail_url(),
        }
        for s in with_counts(surveys).order_by("-created_at")[:8]
    ]
    total_inv = invitations.count()
    return JsonResponse(
        {
            "kpi": {
                "open": open_surveys.count(),
                "invited": total_inv,
                "answered": submitted.count(),
                "rate": round(100 * submitted.count() / total_inv) if total_inv else 0,
                "total": surveys.count(),
            },
            "per_day": [
                {"day": day.isoformat(), "n": counts.get(day, 0)}
                for day in (first_day + timedelta(days=i) for i in range(31))
            ],
            "per_department": [
                {
                    "department": r[
                        "employee__employee_work_info__department_id__department"
                    ]
                    or _("No department"),
                    "total": r["total"],
                    "done": r["done"],
                }
                for r in per_department
            ],
            "recent": recent,
        }
    )
