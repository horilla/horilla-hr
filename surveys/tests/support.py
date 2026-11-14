"""Fixtures shared by the privacy, robustness and injection tests of the surveys app."""

from django.test import Client
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from surveys.models import Survey, SurveyQuestion


class Built:
    """A survey with two questions, its invitations and the HR user who runs it."""

    def __init__(self, company, hr_user, survey, mood, note, invitations):
        self.company = company
        self.hr_user = hr_user
        self.survey = survey
        self.mood = mood
        self.note = note
        self.invitations = invitations

    def mood_name(self):
        return f"q{self.mood.pk}"

    def note_name(self):
        return f"q{self.note.pk}"


def build_survey(
    *, tag, anonymous=True, people=6, status=Survey.STATUS_OPEN, title="Pulse"
):
    """A survey in its own company, with `people` employees plus an HR user invited."""
    set_selected_company(None)
    company = make_company(f"{tag} Co")
    hr_user = make_user(f"{tag}_hr", password="pw12345", is_superuser=True)
    make_employee(company=company, email=f"{tag}.hr@test.horilla", user=hr_user)
    for number in range(people):
        make_employee(
            company=company,
            email=f"{tag}.p{number}@test.horilla",
            first_name=f"Person{number}",
        )
    survey = Survey.objects.create(
        title=title, status=status, is_anonymous=anonymous, company_id=company
    )
    mood = SurveyQuestion.objects.create(
        survey=survey, sequence=1, type=SurveyQuestion.TYPE_RATING, question="Mood?"
    )
    note = SurveyQuestion.objects.create(
        survey=survey, sequence=2, type=SurveyQuestion.TYPE_TEXT, question="Note?"
    )
    invitations = survey.invite()
    return Built(company, hr_user, survey, mood, note, invitations)


def answer_url(invitation_or_token):
    token = getattr(invitation_or_token, "token", invitation_or_token)
    return reverse("survey-answer", args=[token])


def submit(built, invitation, *, mood="4", note="fine", client=None):
    """Answer and submit through the personal link, as the employee would."""
    client = client or Client()
    return client.post(
        answer_url(invitation),
        {built.mood_name(): mood, built.note_name(): note},
    )


def hr_client(built):
    client = Client()
    client.force_login(built.hr_user)
    return client
