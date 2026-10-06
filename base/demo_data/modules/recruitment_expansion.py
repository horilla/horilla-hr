"""Give every demo company its own Recruitment pipeline, not just the largest.

recruitment_data.json's 3 Recruitments, all their Candidates, and all their
Stages are 100% scoped to the largest demo company -- switching company
context anywhere in the Recruitment or Onboarding modules shows a
completely empty pipeline for the other two. This creates one open
Recruitment per additional company, with its own Stage set and a small
Candidate pool spread across a realistic status mix, reusing the existing
JobPosition catalog rather than inventing new lookup data. Each new
recruitment also gets its own minimal OnboardingStage pair and a completed
CandidateStage for its one hired candidate, since OnboardingStage is itself
per-recruitment (onboarding_trend.py only ever populated recruitment #1's).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

# (company_id, recruitment title, job_position_id, candidate names, genders)
# Job positions are shared across companies already (see org.py), so these
# just reuse existing catalog entries rather than inventing new ones.
NEW_COMPANY_RECRUITMENTS = [
    (
        2,
        "Software Engineer - India",
        1,  # Software Engineer
        [
            ("Priya Sharma", "female"),
            ("Arjun Mehta", "male"),
            ("Ananya Rao", "female"),
            ("Vikram Singh", "male"),
            ("Kavya Nair", "female"),
            ("Rohan Gupta", "male"),
            ("Ishaan Kapoor", "male"),
            ("Diya Patel", "female"),
            ("Aditya Verma", "male"),
            ("Meera Iyer", "female"),
        ],
    ),
    (
        3,
        "Support Specialist - UK",
        3,  # Sales Associate reused as a generic front-line role
        [
            ("Oliver Bennett", "male"),
            ("Charlotte Hughes", "female"),
            ("Harry Wilson", "male"),
            ("Amelia Clarke", "female"),
            ("George Foster", "male"),
            ("Isla Robertson", "female"),
            ("Jack Sullivan", "male"),
            ("Freya Mitchell", "female"),
            ("Thomas Baker", "male"),
            ("Poppy Edwards", "female"),
        ],
    ),
]

# Index into each recruitment's candidate list -> which stage they land in,
# mirroring the realistic mix the existing Company-1 recruitments already
# show (a healthy chunk hired, one cancelled, the rest still moving through).
STAGE_PLAN = (
    "applied",
    "initial",
    "interview",
    "interview",
    "hired",
    "cancelled",
    "hired",
    "hired",
    "interview",
    "hired",
)

EXTRA_STAGES = (
    # (stage title, stage_type, sequence) -- "Applied"/"Initial" already
    # exist from create_initial_stage()'s own post_save signal.
    ("Interview", "interview", 2),
    ("Hired", "hired", 3),
    ("Cancelled", "cancelled", 4),
)


@transaction.atomic
def backfill_company_recruitment_pipelines(today: date | None = None) -> int:
    """Ensure NEW_COMPANY_RECRUITMENTS exist, each with a full stage set and
    a small, status-diverse candidate pool. Returns candidates created."""
    if not apps.is_installed("recruitment"):
        return 0

    today = today or date.today()

    from recruitment.models import Candidate, Recruitment, Stage

    onboarding_installed = apps.is_installed("onboarding")
    if onboarding_installed:
        from onboarding.models import CandidateStage, OnboardingStage

    created = 0
    for company_id, title, job_position_id, candidates in NEW_COMPANY_RECRUITMENTS:
        recruitment, _ = Recruitment._base_manager.get_or_create(
            title=title,
            defaults={
                "description": "Open hiring pipeline.",
                "job_position_id_id": job_position_id,
                "company_id_id": company_id,
                "vacancy": 2,
                "closed": False,
                "is_published": True,
                "start_date": today - timedelta(days=30),
            },
        )
        # create_initial_stage() (recruitment/signals.py) already made
        # "Applied" (sequence 0) and "Initial" (sequence 1) on first save.
        stage_by_type = {
            s.stage_type: s
            for s in Stage._base_manager.filter(recruitment_id=recruitment)
        }
        for stage_title, stage_type, sequence in EXTRA_STAGES:
            stage, _ = Stage._base_manager.get_or_create(
                recruitment_id=recruitment,
                stage_type=stage_type,
                defaults={"stage": stage_title, "sequence": sequence},
            )
            stage_by_type[stage_type] = stage

        onboarding_final_stage = None
        if onboarding_installed:
            OnboardingStage._base_manager.get_or_create(
                recruitment_id=recruitment,
                is_final_stage=False,
                defaults={"stage_title": "Documentation", "sequence": 0},
            )
            onboarding_final_stage, _ = OnboardingStage._base_manager.get_or_create(
                recruitment_id=recruitment,
                is_final_stage=True,
                defaults={"stage_title": "Completed", "sequence": 1},
            )

        for i, (name, gender) in enumerate(candidates):
            stage_type = STAGE_PLAN[i % len(STAGE_PLAN)]
            stage = stage_by_type.get(stage_type) or stage_by_type["applied"]
            hired = stage_type == "hired"
            email_name = name.lower().replace(" ", ".")
            profile = (
                "recruitment/profile/profile-pic-girl.jpg"
                if gender == "female"
                else "recruitment/profile/profile-pic-boy.jpg"
            )

            candidate, was_created = Candidate._base_manager.get_or_create(
                email=f"{email_name}@horilla-demo.com",
                defaults={
                    "name": name,
                    "gender": gender,
                    "recruitment_id": recruitment,
                    "job_position_id_id": job_position_id,
                    "stage_id": stage,
                    "profile": profile,
                    "resume": "recruitment/resume/resume.pdf",
                    "mobile": f"9000{company_id}{i:04d}",
                    "hired": hired,
                    "canceled": stage_type == "cancelled",
                    "joining_date": today if hired else None,
                },
            )
            if was_created:
                created += 1
            if hired and onboarding_final_stage is not None:
                CandidateStage._base_manager.get_or_create(
                    candidate_id=candidate,
                    defaults={
                        "onboarding_stage_id": onboarding_final_stage,
                        "onboarding_end_date": today - timedelta(days=15),
                    },
                )

    logger.info(
        "Recruitment backfill: created %s candidate(s) across %s new company pipeline(s)",
        created,
        len(NEW_COMPANY_RECRUITMENTS),
    )
    return created
