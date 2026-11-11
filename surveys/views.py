"""The survey page (constructor, audience, results), its actions, the library, the dashboard."""

import csv
import json
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
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop
from django.views.decorators.http import require_POST

from base.backends import ConfiguredEmailBackend
from horilla.decorators import login_required, permission_required
from horilla.http.response import HorillaRedirect
from notifications.signals import notify
from surveys import answers as answer_rules
from surveys.access import can_manage, can_view_results
from surveys.library import load_standard
from surveys.models import (
    Questionnaire,
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)


def _survey_for(request, pk, check):
    survey = get_object_or_404(Survey, pk=pk)
    if not check(request.user, survey):
        messages.error(request, _("You do not have permission for this."))
        return survey, HorillaRedirect(request)
    return survey, None


# --- the survey page -------------------------------------------------------


@login_required
def survey_detail(request, pk):
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
            "can_results": can_view_results(request.user, survey),
            "can_save_to_library": request.user.has_perm("surveys.add_questionnaire"),
            "tab": request.GET.get("tab", "questions"),
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
        {"survey": survey, "can_manage": can_manage(request.user, survey)},
    )


@login_required
@require_POST
def reorder_questions(request, pk):
    survey, denied = _survey_for(request, pk, can_manage)
    if denied:
        return JsonResponse({"status": "forbidden"}, status=403)
    try:
        order = [int(x) for x in json.loads(request.POST.get("order", "[]"))]
    except (ValueError, TypeError):
        return JsonResponse({"status": "error"}, status=400)
    with transaction.atomic():
        for index, question_pk in enumerate(order, start=1):
            survey.questions.filter(pk=question_pk).update(sequence=index)
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def delete_question(request, pk):
    question = get_object_or_404(SurveyQuestion, pk=pk)
    if not can_manage(request.user, question.survey):
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
    invitations = survey.invitations.select_related("employee").order_by(
        "employee__employee_first_name"
    )
    return render(
        request,
        "surveys/tabs/audience.html",
        {
            "survey": survey,
            "can_manage": can_manage(request.user, survey),
            "audience_count": survey.audience_employees().count(),
            "invitations": invitations,
            "pending": invitations.exclude(
                status=SurveyInvitation.STATUS_SUBMITTED
            ).count(),
        },
    )


# --- actions ---------------------------------------------------------------


def _answer_url(request, invitation):
    return request.build_absolute_uri(reverse("survey-answer", args=[invitation.token]))


def _send_invitations(request, survey, invitations, *, reminder=False):
    """A Horilla notification and an e-mail with the personal link, per invitation."""
    sender = request.user.employee_get
    backend = ConfiguredEmailBackend()
    mail_ok = bool(backend.configuration)
    sent = 0
    now = timezone.now()
    for invitation in invitations:
        url = _answer_url(request, invitation)
        user = invitation.employee.employee_user_id
        if user:
            notify.send(
                sender,
                recipient=user,
                verb=(
                    gettext_noop(
                        "Reminder: survey '%(title)s' is waiting for your answers"
                    )
                    if reminder
                    else gettext_noop("You are invited to the survey '%(title)s'")
                ),
                verb_params={"title": survey.title},
                icon="clipboard",
                redirect=url,
            )
        if mail_ok and invitation.employee.get_mail():
            context = {
                "survey": survey,
                "employee": invitation.employee,
                "url": url,
                "reminder": reminder,
            }
            message = EmailMultiAlternatives(
                subject=render_to_string(
                    "surveys/mail/invitation_subject.txt", context
                ).strip(),
                body=render_to_string("surveys/mail/invitation.txt", context),
                from_email=backend.dynamic_from_email_with_display_name,
                to=[invitation.employee.get_mail()],
                connection=backend,
            )
            message.attach_alternative(
                render_to_string("surveys/mail/invitation.html", context), "text/html"
            )
            try:
                message.send()
            except Exception:  # the notification is still delivered
                pass
        field = "reminded_at" if reminder else "sent_at"
        SurveyInvitation._base_manager.filter(pk=invitation.pk).update(**{field: now})
        sent += 1
    return sent, mail_ok


@login_required
@require_POST
def open_survey(request, pk):
    survey, denied = _survey_for(request, pk, can_manage)
    if denied:
        return denied
    if not survey.questions.exists():
        messages.error(
            request, _("Add at least one question before opening the survey.")
        )
        return HorillaRedirect(request)
    with transaction.atomic():
        if survey.status != Survey.STATUS_OPEN:
            survey.status = Survey.STATUS_OPEN
            survey.save()
        new = survey.invite()
    sent, mail_ok = _send_invitations(request, survey, new)
    messages.success(
        request, _("Survey opened: %(n)s invitation(s) sent.") % {"n": sent}
    )
    if sent and not mail_ok:
        messages.warning(
            request,
            _("No mail server is set up - employees were notified in Horilla only."),
        )
    return HorillaRedirect(request)


@login_required
@require_POST
def close_survey(request, pk):
    survey, denied = _survey_for(request, pk, can_manage)
    if denied:
        return denied
    Survey.objects.filter(pk=pk).update(status=Survey.STATUS_CLOSED)
    messages.success(request, _("Survey closed."))
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
    ).select_related("employee")
    sent, _mail = _send_invitations(request, survey, pending, reminder=True)
    messages.success(request, _("Reminder sent to %(n)s employee(s).") % {"n": sent})
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
            if (
                question.type
                in (question.TYPE_RATING, question.TYPE_LIKERT, question.TYPE_NPS)
                and values
            ):
                item["average"] = round(sum(int(v) for v in values) / len(values), 2)
            if question.type == question.TYPE_NPS and values:
                item["nps"] = _nps(question, [int(v) for v in values])
        elif question.type == question.TYPE_NUMBER:
            numbers = [float(v) for v in values]
            if numbers:
                item.update(
                    average=round(sum(numbers) / len(numbers), 2),
                    minimum=min(numbers),
                    maximum=max(numbers),
                )
            item["texts"] = [str(v) for v in values]
        else:
            item["texts"] = [str(v) for v in values]
        results.append(item)
    return responses.count(), results


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
    survey, denied = _survey_for(request, pk, can_view_results)
    if denied:
        return denied
    department = request.GET.get("department") or None
    total, results = _results(survey, department)
    from base.models import Department

    return render(
        request,
        "surveys/tabs/results.html",
        {
            "survey": survey,
            "total": total,
            "results": results,
            "departments": Department.objects.all() if not survey.is_anonymous else [],
            "department": department,
            "chart_data": json.dumps(
                [
                    {
                        "id": r["question"].pk,
                        "labels": r.get("labels"),
                        "series": r.get("series"),
                        "type": r["question"].type,
                    }
                    for r in results
                    if "series" in r
                ]
            ),
        },
    )


@login_required
def export_results(request, pk):
    survey, denied = _survey_for(request, pk, can_view_results)
    if denied:
        return denied
    questions = list(survey.questions.all())
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="survey-{survey.pk}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    header = ["#", _("Submitted at")]
    if not survey.is_anonymous:
        header += [_("Employee"), _("Department")]
    writer.writerow(header + [q.question for q in questions])
    rows = (
        SurveyResponse.objects.filter(survey=survey, is_draft=False)
        .select_related("invitation__employee__employee_work_info__department_id")
        .order_by("submitted_at")
    )
    for index, row in enumerate(rows, start=1):
        values = row.answers_by_question()
        line = [
            index,
            (
                timezone.localtime(row.submitted_at).strftime("%Y-%m-%d %H:%M")
                if row.submitted_at
                else ""
            ),
        ]
        if not survey.is_anonymous:
            employee = row.invitation.employee if row.invitation else None
            line += [
                employee.get_full_name() if employee else "",
                str(employee.get_department() or "") if employee else "",
            ]
        writer.writerow(
            line + [answer_rules.label(q, values.get(q.pk)) for q in questions]
        )
    return response


# --- library ---------------------------------------------------------------


@login_required
@permission_required("surveys.view_survey")
def library(request):
    return render(
        request,
        "surveys/library.html",
        {"questionnaires": Questionnaire.objects.all()},
    )


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
    return HorillaRedirect(request)


@login_required
@require_POST
@permission_required("surveys.delete_questionnaire")
def delete_questionnaire(request, pk):
    get_object_or_404(Questionnaire, pk=pk).delete()
    messages.success(request, _("Questionnaire deleted."))
    return HorillaRedirect(request)


# --- dashboard -------------------------------------------------------------


@login_required
@permission_required("surveys.view_survey")
def dashboard(request):
    return render(request, "surveys/dashboard.html")


@login_required
@permission_required("surveys.view_survey")
def dashboard_data(request):
    surveys = Survey.objects.all()
    open_surveys = surveys.filter(status=Survey.STATUS_OPEN)
    invitations = SurveyInvitation.objects.filter(survey__in=open_surveys)
    submitted = invitations.filter(status=SurveyInvitation.STATUS_SUBMITTED)
    since = timezone.now() - timezone.timedelta(days=30)
    per_day = (
        SurveyResponse.objects.filter(is_draft=False, submitted_at__gte=since)
        .annotate(day=TruncDate("submitted_at"))
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
            "status": s.get_status_display(),
            "status_code": s.status,
            "answered": s.answered_count(),
            "invited": s.invited_count(),
            "rate": s.response_rate(),
            "url": s.get_detail_url(),
        }
        for s in surveys.order_by("-created_at")[:8]
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
                for day in (since.date() + timedelta(days=i) for i in range(31))
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
