"""
recruitmentfilters.py

This module is used to write custom template filters.

"""

import datetime
import json
import re
import uuid

from django import template
from django.apps import apps

from horilla_auth.models import HorillaUser
from recruitment.models import CandidateRating

# from django.forms.boundfield

register = template.Library()


@register.filter(name="is_stagemanager")
def is_stagemanager(user):
    """
    This method is used to check the employee is stage or recruitment manager
    """
    try:
        cached = getattr(user, "_horilla_is_stagemanager", None)
        if cached is not None:
            return cached
        employee_obj = user.employee_get
        result = (
            employee_obj.stage_set.filter(is_active=True).exists()
            or employee_obj.recruitment_set.exists()
        )
        setattr(user, "_horilla_is_stagemanager", result)
        return result
    except Exception:
        return False


@register.filter(name="is_any_manager")
def is_any_manager(request):
    """
    This method is used to check the employee is stage or recruitment manager
    """
    user = request.user
    cached = getattr(user, "_horilla_is_any_manager", None)
    if cached is not None:
        return cached
    employee = user.employee_get
    result = (
        employee.stage_set.filter(is_active=True).exists()
        or employee.recruitment_set.exists()
        or employee.onboardingstage_set.exists()
        or employee.onboarding_task.exists()
    )
    setattr(user, "_horilla_is_any_manager", result)
    return result


@register.filter(name="is_recruitmentmanager")
def is_recruitmentmangers(user):
    """
    This method is used to check the employee is recruitment manager
    """
    try:
        cached = getattr(user, "_horilla_is_recruitmentmanager", None)
        if cached is not None:
            return cached
        employee_obj = user.employee_get
        result = employee_obj.recruitment_set.exists()
        setattr(user, "_horilla_is_recruitmentmanager", result)
        return result
    except Exception:
        return False


@register.filter(name="stage_manages")
def stage_manages(user, recruitment):
    """
    This method is used to check the employee is manager in any stage in a recruitment
    """
    try:
        return (
            recruitment.stage_set.filter(stage_managers=user.employee_get).exists()
            or recruitment.recruitment_managers.filter(id=user.employee_get.id).exists()
        )
    except Exception as _:
        return False


@register.filter(name="recruitment_manages")
def recruitment_manages(user, recruitment):
    """
    This method is used to check the employee in recruitment managers
    """
    try:
        employee_obj = user.employee_get
        return recruitment.recruitment_managers.filter(id=employee_obj.id).exists()
    except Exception:
        return False


@register.filter(name="employee")
def employee(uid):
    """
    This method is used to return user object with the arg id.

    Args:
        uid (int): user object id

    Returns:
        user object
    """
    return HorillaUser.objects.get(id=uid).employee_get if uid is not None else None


@register.filter(name="media_path")
def media_path(form_tag):
    """
    This method will returns the path of media
    """
    return form_tag.subwidgets[0].__dict__["data"]["value"]


@register.filter(name="generate_id")
def generate_id(element, label=""):
    """
    This method is used to generate element id attr
    """
    element.field.widget.attrs.update({"id": label + str(uuid.uuid1())})
    return element


@register.filter(name="has_candidate_rating")
def has_candidate_rating(candidate_ratings, cand):
    candidate_rating = candidate_ratings.filter(candidate_id=cand.id).first()
    return candidate_rating


@register.filter(name="rating")
def rating(candidate_ratings, cand):
    rating = candidate_ratings.filter(candidate_id=cand.id).first().rating
    return str(rating)


@register.filter(name="avg_rating")
def avg_rating(candidate_ratings, cand):
    ratings = CandidateRating.objects.filter(candidate_id=cand.id)
    rating_list = []
    avg_rate = 0
    for rating in ratings:
        rating_list.append(rating.rating)
    if len(rating_list) != 0:
        avg_rate = round(sum(rating_list) / len(rating_list))

    return str(avg_rate)


@register.filter(name="percentage")
def percentage(value, total):
    if total == 0 or not total:
        return 0
    return min(round((value / total) * 100, 2), 100)


@register.filter(name="is_in_task_managers")
def is_in_task_managers(user):
    """
    This method is used to check the user in the task manager or not
    """
    if apps.is_installed("onboarding"):
        from onboarding.models import OnboardingTask

        return OnboardingTask.objects.filter(
            employee_id__employee_user_id=user
        ).exists()
    return False


@register.filter(name="pipeline_grouper")
def pipeline_grouper(grouper: dict = {}):
    """
    This method is used itemize the dictionary
    """
    return grouper["title"], grouper["stages"]


@register.filter(name="to_json")
def to_json(value):
    ordered_list = [
        {"id": val.id, "stage": val.stage, "type": val.stage_type} for val in value
    ]
    return json.dumps(ordered_list)


@register.filter(name="title_initials")
def title_initials(value):
    """
    Returns the initials (first letter of the first two words) of a title,
    used for the open-recruitment card avatar. Leading bracketed tags
    (e.g. "[Demo] DevOps Engineer Round") are ignored.
    """
    if not value:
        return ""
    text = re.sub(r"^\[.*?\]\s*", "", str(value))
    words = text.split() or str(value).split()
    return "".join(word[0].upper() for word in words[:2] if word[0].isalnum())


@register.filter(name="is_closing_soon")
def is_closing_soon(recruitment):
    """
    A recruitment is "closing soon" if it has an end date within the next
    14 days (and hasn't already passed).
    """
    if not recruitment.end_date:
        return False
    days_left = (recruitment.end_date - datetime.date.today()).days
    return 0 <= days_left <= 14
