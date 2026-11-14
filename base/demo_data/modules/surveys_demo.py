"""One closed anonymous pulse survey, so the Surveys screens open with data."""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from django.apps import apps
from django.db import transaction
from django.db.models import Count

logger = logging.getLogger(__name__)

TITLE = "Quarterly pulse"
ANSWERERS = 12  # comfortably above SURVEYS_MIN_RESPONSES, so results show


def seed_demo_survey(today: date) -> dict:
    """Create the demo survey in the largest company; safe to call repeatedly."""
    if not apps.is_installed("surveys"):
        return {"skipped": "surveys not installed"}

    from base.models import Company
    from employee.models import EmployeeWorkInformation
    from surveys.models import (
        Survey,
        SurveyAnswer,
        SurveyInvitation,
        SurveyQuestion,
        SurveyResponse,
        local_midnight_of,
    )

    if Survey._base_manager.filter(title=TITLE).exists():
        return {"created": 0}

    biggest = (
        EmployeeWorkInformation._base_manager.filter(company_id__isnull=False)
        .values("company_id")
        .annotate(people=Count("pk"))
        .order_by("-people", "company_id")
        .first()
    )
    if biggest is None:
        return {"skipped": "no company"}
    company = Company._base_manager.get(pk=biggest["company_id"])

    closed_on = local_midnight_of(today - timedelta(days=3))
    rng = random.Random(f"surveys-demo-{company.pk}")

    with transaction.atomic():
        survey = Survey(
            title=TITLE,
            description="A short check-in on how the quarter felt.",
            is_anonymous=True,
            status=Survey.STATUS_CLOSED,
            opens_at=closed_on - timedelta(days=11),
            closes_at=closed_on,
            company_id=company,
        )
        survey.save()
        mood = SurveyQuestion.objects.create(
            survey=survey,
            sequence=1,
            type=SurveyQuestion.TYPE_RATING,
            question="How was the quarter for you?",
            is_required=True,
        )
        workload = SurveyQuestion.objects.create(
            survey=survey,
            sequence=2,
            type=SurveyQuestion.TYPE_CHOICE,
            question="How did your workload feel?",
            options=["Too light", "About right", "Too heavy"],
        )
        note = SurveyQuestion.objects.create(
            survey=survey,
            sequence=3,
            type=SurveyQuestion.TYPE_TEXT,
            question="Anything we should change?",
        )
        survey.invite()

        invitations = list(
            SurveyInvitation._base_manager.filter(survey=survey).order_by("pk")
        )
        notes = [
            "More focus time, fewer meetings.",
            "Clearer priorities at the start of the month.",
            "The new onboarding checklist helped a lot.",
            "",
            "Keep the Friday demos.",
        ]
        for invitation in invitations[:ANSWERERS]:
            response = SurveyResponse.start(survey, invitation)
            SurveyAnswer.objects.bulk_create(
                [
                    SurveyAnswer(
                        response=response, question=mood, value=rng.randint(3, 5)
                    ),
                    SurveyAnswer(
                        response=response,
                        question=workload,
                        value=rng.choice(workload.options),
                    ),
                    SurveyAnswer(
                        response=response, question=note, value=rng.choice(notes)
                    ),
                ]
            )
            SurveyResponse.finish(response, invitation, anonymous=True, now=closed_on)
            SurveyInvitation._base_manager.filter(pk=invitation.pk).update(
                status=SurveyInvitation.STATUS_SUBMITTED,
                sent_at=closed_on - timedelta(days=10),
                submitted_at=closed_on,
            )

    answered = SurveyResponse._base_manager.filter(
        survey=survey, is_draft=False
    ).count()
    logger.info("Demo survey seeded: %s answers in %s", answered, company)
    return {"created": 1, "answered": answered}
