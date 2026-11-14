"""Who may do what with a survey.

Two levels. HR, with the module's permissions, runs surveys: builds them, opens
and closes them. A survey's managers (people HR names on it, who may have no
HR rights) look after one survey: they see it, its audience and its results,
export the results and send reminders - and nothing that changes the survey or
what it asks.
"""


def can_manage(user, survey):
    """See the survey, its audience and results; send reminders."""
    if user.has_perm("surveys.change_survey"):
        return True
    try:
        return survey.managers.filter(pk=user.employee_get.pk).exists()
    except Exception:
        return False


def can_run(user, survey=None):
    """Change the survey: its questions, its settings, opening and closing it."""
    return user.has_perm("surveys.change_survey")


def can_view_results(user, survey):
    if user.has_perm("surveys.view_surveyresponse"):
        return True
    return can_manage(user, survey)
