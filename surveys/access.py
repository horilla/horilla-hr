"""Who may do what with a survey.

The module permissions cover HR; a survey's managers may see its results and
send reminders without them, like offboarding managers.
"""


def can_manage(user, survey):
    if user.has_perm("surveys.change_survey"):
        return True
    try:
        return survey.managers.filter(pk=user.employee_get.pk).exists()
    except Exception:
        return False


def can_view_results(user, survey):
    if user.has_perm("surveys.view_surveyresponse"):
        return True
    return can_manage(user, survey)
