"""Connect the Rejected Candidates feature to real demo data.

Two candidates already sit in a cancelled-type stage, and two RejectReason
rows already exist, but no RejectedCandidate row ever links them -- the
Rejected Candidates report has nothing to show despite the underlying data
already telling that story everywhere else.
"""

from __future__ import annotations

import logging
from datetime import date

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def backfill_rejected_candidates(today: date | None = None) -> int:
    """Ensure every candidate in a cancelled-type stage has a matching
    RejectedCandidate row, cycling through the existing RejectReason catalog."""
    if not apps.is_installed("recruitment"):
        return 0

    from recruitment.models import Candidate, RejectedCandidate, RejectReason

    reject_reason_ids = list(
        RejectReason._base_manager.order_by("id").values_list("id", flat=True)
    )
    if not reject_reason_ids:
        return 0

    cancelled_ids = list(
        Candidate._base_manager.filter(stage_id__stage_type="cancelled")
        .exclude(
            pk__in=RejectedCandidate._base_manager.values_list(
                "candidate_id", flat=True
            )
        )
        .order_by("id")
        .values_list("id", flat=True)
    )

    created = 0
    for i, candidate_id in enumerate(cancelled_ids):
        rejected, was_created = RejectedCandidate._base_manager.get_or_create(
            candidate_id_id=candidate_id,
            defaults={"description": "Not selected to move forward at this time."},
        )
        if was_created:
            rejected.reject_reason_id.add(reject_reason_ids[i % len(reject_reason_ids)])
            created += 1

    logger.info(
        "Recruitment feature backfill: %s rejected candidate(s) linked", created
    )
    return created


@transaction.atomic
def backfill_candidate_source(today: date | None = None) -> int:
    """Give every demo Candidate a source (and a handful a referral).

    Candidate.source is never set anywhere the fixtures/backfills create
    candidates -- the only place in the whole app that ever writes it is
    the internal "add candidate" form (recruitment/views/views.py, always
    hardcoded to "software"); the public career-page application form
    never sets it at all. That leaves every demo candidate's source NULL,
    so the recruitment dashboard's "Source of Hire" / "Hire Rate by
    Source" widgets have nothing to bucket candidates into except "Not
    Specified" -- a data-completeness gap, not a query bug (the queries
    already handle every real source value + referral + null correctly).
    """
    if not apps.is_installed("recruitment"):
        return 0

    from recruitment.models import Candidate

    candidate_ids = list(
        Candidate._base_manager.filter(source__isnull=True)
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not candidate_ids:
        return 0

    # Candidate.source only has these three real choices (see
    # recruitment/models.py's source_choices) -- Referral is tracked
    # separately via the `referral` FK, which the dashboard queries already
    # check first, so it isn't part of this rotation.
    sources = ["application", "software", "other"]

    referrer_id = (
        Candidate._base_manager.exclude(pk__in=candidate_ids)
        .filter(converted_employee_id__isnull=False)
        .values_list("converted_employee_id", flat=True)
        .first()
    )
    if referrer_id is None:
        from employee.models import Employee

        referrer_id = (
            Employee._base_manager.order_by("id").values_list("id", flat=True).first()
        )

    updated = 0
    for i, candidate_id in enumerate(candidate_ids):
        fields = {"source": sources[i % len(sources)]}
        # Every 4th candidate becomes a referral instead, so the Referral
        # bucket isn't permanently empty either.
        if referrer_id is not None and i % 4 == 3:
            fields["referral_id"] = referrer_id
        Candidate._base_manager.filter(pk=candidate_id).update(**fields)
        updated += 1

    logger.info("Recruitment feature backfill: %s candidate source(s) set", updated)
    return updated


@transaction.atomic
def backfill_candidate_offer_status(today: date | None = None) -> int:
    """Give demo candidates a realistic offer_letter_status spread.

    Same gap as backfill_candidate_source: offer_letter_status is a real,
    actively-used field (onboarding/views.py writes it when HR marks a
    letter sent/accepted/rejected/joined) but nothing in the fixtures or
    other backfills ever sets it, so every demo candidate sits at the
    model's default "not_sent" -- the recruitment dashboard's "Offer
    Letter Status" widget has 29/29 in one bucket and nothing in the
    other four. Hired candidates skew toward accepted/joined; everyone
    else cycles through the pre-offer states, which is what the field
    actually represents.
    """
    if not apps.is_installed("recruitment"):
        return 0

    from recruitment.models import Candidate

    candidates = list(
        Candidate._base_manager.filter(offer_letter_status="not_sent")
        .select_related("stage_id")
        .order_by("id")
    )
    if not candidates:
        return 0

    hired_statuses = ["accepted", "joined"]
    other_statuses = ["not_sent", "sent", "rejected"]

    updated = 0
    hired_i = 0
    other_i = 0
    for candidate in candidates:
        is_hired = candidate.hired or (
            candidate.stage_id and candidate.stage_id.stage_type == "shortlisted"
        )
        if is_hired:
            status = hired_statuses[hired_i % len(hired_statuses)]
            hired_i += 1
        else:
            status = other_statuses[other_i % len(other_statuses)]
            other_i += 1
        if status == "not_sent":
            continue
        Candidate._base_manager.filter(pk=candidate.pk).update(
            offer_letter_status=status
        )
        updated += 1

    logger.info(
        "Recruitment feature backfill: %s candidate offer letter status(es) set",
        updated,
    )
    return updated


@transaction.atomic
def backfill_recruitment_job_position(today: date | None = None) -> int:
    """Set Recruitment.job_position_id from its own candidates when unset.

    The "Open Positions by Department" dashboard widget buckets every
    recruitment without a job_position_id into a single "Unassigned"
    catch-all, hiding the department breakdown entirely even when the
    underlying candidates all clearly belong to one job position (every
    candidate on a given recruitment is already consistently assigned the
    same job_position_id by the application's own candidate-creation flow
    -- this just carries that same value up onto the recruitment).
    """
    if not apps.is_installed("recruitment"):
        return 0

    from recruitment.models import Candidate, Recruitment

    updated = 0
    for recruitment in Recruitment._base_manager.filter(job_position_id__isnull=True):
        job_position_id = (
            Candidate._base_manager.filter(
                recruitment_id=recruitment, job_position_id__isnull=False
            )
            .values_list("job_position_id", flat=True)
            .first()
        )
        if job_position_id is None:
            continue
        # Recruitment has a unique_together on (job_position_id, start_date)
        # -- two still-unassigned recruitments can share both a candidate's
        # job position and a start_date, so blindly setting this can collide
        # with another row that already occupies that pair. Skip rather than
        # crash; that recruitment just keeps showing under "Unassigned".
        collides = (
            Recruitment._base_manager.exclude(pk=recruitment.pk)
            .filter(
                job_position_id_id=job_position_id,
                start_date=recruitment.start_date,
            )
            .exists()
        )
        if collides:
            continue
        Recruitment._base_manager.filter(pk=recruitment.pk).update(
            job_position_id_id=job_position_id
        )
        recruitment.open_positions.add(job_position_id)
        updated += 1

    logger.info(
        "Recruitment feature backfill: %s recruitment job position(s) set", updated
    )
    return updated
