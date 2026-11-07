"""
Resignation letter cancellation transitions.

Every transition re-reads the letter under a row lock and validates the current
status, so two concurrent clicks (or a double submit) apply only once.
Each function returns (letter, error_message); error_message is None on success.
"""

from django.db import transaction
from django.utils.translation import gettext as _

from offboarding.models import OffboardingEmployee, ResignationLetter


def _locked_letter(letter_id):
    return (
        ResignationLetter._base_manager.select_for_update()
        .filter(id=letter_id)
        .first()
    )


def cancel_resignation(letter_id, reason):
    """
    Employee cancels a "requested" resignation: no manager approval needed.
    """
    with transaction.atomic():
        letter = _locked_letter(letter_id)
        if letter is None:
            return None, _("Resignation request not found.")
        if letter.status != "requested":
            return letter, _("Only a request in 'Requested' status can be cancelled.")
        letter.status = "cancelled"
        letter.cancel_reason = reason
        letter.save()
    return letter, None


def request_resignation_cancellation(letter_id, reason):
    """
    Employee asks to cancel an "approved" resignation. The resignation stays
    in force until a manager decides.
    """
    with transaction.atomic():
        letter = _locked_letter(letter_id)
        if letter is None:
            return None, _("Resignation request not found.")
        if letter.status == "cancellation_requested":
            return letter, _(
                "A cancellation request is already pending for this resignation."
            )
        if letter.status != "approved":
            return letter, _(
                "A cancellation can only be requested for an approved resignation."
            )
        letter.status = "cancellation_requested"
        letter.cancel_reason = reason
        letter.save()
    return letter, None


def decide_resignation_cancellation(letter_id, approve):
    """
    Manager approves ("cancelled") or rejects (back to "approved") a pending
    cancellation request.

    The offboarding pipeline record created when the resignation was approved
    is left untouched: it carries stages, tasks and exit reasons, and removing
    it would lose data. Callers can check ``has_offboarding_record`` to warn
    the manager.
    """
    with transaction.atomic():
        letter = _locked_letter(letter_id)
        if letter is None:
            return None, _("Resignation request not found.")
        if letter.status != "cancellation_requested":
            return letter, _(
                "This resignation request has no pending cancellation request."
            )
        letter.status = "cancelled" if approve else "approved"
        if not approve:
            letter.cancel_reason = None
        letter.save()
    return letter, None


def has_offboarding_record(letter):
    """True when the employee is already in the offboarding pipeline."""
    return OffboardingEmployee.objects.filter(employee_id=letter.employee_id).exists()
