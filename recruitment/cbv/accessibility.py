"""
Accessibility
"""

from django.contrib.auth.context_processors import PermWrapper

from base.methods import check_manager
from employee.models import Employee
from horilla_auth.models import HorillaUser
from recruitment.methods import (
    in_all_managers,
    is_recruitmentmanager,
    is_stagemanager,
    stage_manages,
)
from recruitment.models import Candidate, RecruitmentGeneralSetting, RejectedCandidate


def convert_emp(request, instance, user_perm):
    """
    Covert employee accessibility
    """
    mails = list(Candidate.objects.values_list("email", flat=True))
    existing_emails = list(
        HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    )
    if not instance.email in existing_emails and not instance.start_onboard:
        return True


def add_skill_zone(request, instance, user_perm):
    """
    Add talent pool  accessibility
    """

    mails = list(Candidate.objects.values_list("email", flat=True))
    existing_emails = list(
        HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    )
    if not instance.email in existing_emails and request.user.has_perm(
        "recruitment.add_skillzonecandidate"
    ):
        return True


def add_reject(request, instance, user_perm):
    """
    add reject accessibility
    """
    first = RejectedCandidate.objects.filter(candidate_id=instance).first()
    mails = list(Candidate.objects.values_list("email", flat=True))
    existing_emails = list(
        HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    )
    if not instance.email in existing_emails:
        if request.user.has_perm(
            "recruitment.add_rejectedcandidate"
        ) or is_stagemanager(request):
            if not first:
                return True


def edit_reject(request, instance, user_perm):
    """
    Edit reject accessibility
    """
    first = RejectedCandidate.objects.filter(candidate_id=instance).first()
    mails = list(Candidate.objects.values_list("email", flat=True))
    existing_emails = list(
        HorillaUser.objects.filter(username__in=mails).values_list("email", flat=True)
    )
    if not instance.email in existing_emails:
        if request.user.has_perm(
            "recruitment.add_rejectedcandidate"
        ) or is_stagemanager(request):
            if first:
                return True


def archive_status(request, instance, user_perm):
    """
    To acces archive in list candidates
    """
    if instance.is_active:
        return True


def unarchive_status(request, instance, user_perm):
    """
    To acces un-archive in list candidates
    """
    if not instance.is_active:
        return True


def onboarding_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    accessibility for onboarding tab in candidate individual view
    """
    candidate = Candidate.objects.get(pk=instance.pk)
    if (
        candidate.cand_onboarding_task.exists()
        and in_all_managers(request)
        or request.user.has_perm("onboarding.view_onboardingtask")
    ):
        return True
    return False


def rating_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    accessebility for rating tab in candidate individual view
    """
    candidate = Candidate.objects.get(pk=instance.pk)
    stage_manage = stage_manages(request.user.employee_get, candidate.recruitment_id)
    if (
        stage_manage
        or request.user.has_perm("recruitment.view_candidate")
        or request.user.has_perm("recruitment.view_candidate")
    ):
        return True
    return False


def if_manager_accessibility(request, instance, *args, **kwargs):
    """
    If manager accessibility
    """
    return (
        is_recruitmentmanager(request)
        or is_stagemanager(request)
        or request.user.has_perm("recruitment.view_candidate")
    )


def empl_scheduled_interview_accessibility(
    request, instance: object = None, user_perms: PermWrapper = [], *args, **kwargs
) -> bool:
    """
    sheduled interview tab accessibility for candidate individual view, employee individual view and employee profile
    """
    if request.user.has_perm(
        "recruitment.view_interviewschedule"
    ) or is_recruitmentmanager(request):
        return True
    # This is also the Scheduled Interviews tab of the *candidate* profile.
    # A candidate's pk is not an employee id, so looking an Employee up by it
    # either raised (tab missing) or matched an unrelated employee -- which is
    # why only the first few candidates showed the tab. Only the employee
    # checks below need an Employee.
    if not isinstance(instance, Employee):
        return is_stagemanager(request)
    return bool(
        check_manager(request.user.employee_get, instance)
        or request.user == instance.employee_user_id
    )


def view_candidate_self_tracking(request, instance, *args, **kwargs):
    if (
        request.user.has_perm("recruitment.view_candidate")
        or is_stagemanager(request)
        or is_recruitmentmanager(request)
    ):
        if check_candidate_self_tracking(request, instance, user_perm=None):
            return True
    return False


def request_document(request, instance, *args, **kwargs):
    if (
        request.user.has_perm("recruitment.change_candidate")
        or request.user.has_perm("recruitment.add_candidatedocumentrequest")
        or is_stagemanager(request)
        or is_recruitmentmanager(request)
    ):
        return True


def check_candidate_self_tracking(request, instance, user_perm):
    """
    This method is used to get the candidate self tracking is enabled or not
    """
    selected_company = request.session.get("selected_company")
    if selected_company and selected_company != "all":
        setting = RecruitmentGeneralSetting.objects.filter(
            company_id_id=selected_company
        ).first()
    else:
        setting = RecruitmentGeneralSetting.objects.filter(
            company_id__isnull=True
        ).first()
    return setting.candidate_self_tracking if setting else False
