"""The personal link: what it shows, what it saves, and what it refuses."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee
from surveys.models import (
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)
from surveys.public import TOKEN_PROBE_LIMIT


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class PublicAnswerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_selected_company(None)
        cls.company = make_company("Public Co")
        cls.olha = make_employee(
            company=cls.company, email="olha@test.horilla", first_name="Olha"
        )
        cls.survey = Survey.objects.create(
            title="Pulse", status=Survey.STATUS_OPEN, company_id=cls.company
        )
        cls.mood = SurveyQuestion.objects.create(
            survey=cls.survey,
            sequence=1,
            type=SurveyQuestion.TYPE_RATING,
            question="Mood?",
            is_required=True,
        )
        cls.tools = SurveyQuestion.objects.create(
            survey=cls.survey,
            sequence=2,
            type=SurveyQuestion.TYPE_MULTIPLE,
            question="Tools?",
            options=["Chat", "Mail", "Phone"],
        )
        cls.note = SurveyQuestion.objects.create(
            survey=cls.survey,
            sequence=3,
            type=SurveyQuestion.TYPE_TEXT,
            question="Note?",
        )
        (cls.invitation,) = cls.survey.invite()

    def setUp(self):
        cache.clear()

    def url(self, token=None):
        return reverse("survey-answer", args=[token or self.invitation.token])

    def post(self, data, autosave=False):
        return self.client.post(self.url() + ("?autosave=1" if autosave else ""), data)

    def names(self):
        return {
            "mood": f"q{self.mood.pk}",
            "tools": f"q{self.tools.pk}",
            "note": f"q{self.note.pk}",
        }

    def test_the_form_needs_no_login(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mood?")
        self.assertContains(response, "Anonymous")

    def test_a_wrong_token_is_404_and_throttled_after_too_many(self):
        for _ in range(TOKEN_PROBE_LIMIT):
            self.assertEqual(self.client.get(self.url("x" * 43)).status_code, 404)
        self.assertEqual(self.client.get(self.url("y" * 43)).status_code, 429)
        # The real token is throttled too for that client:
        # probing cannot be mixed with use.
        self.assertEqual(self.client.get(self.url()).status_code, 429)

    def test_autosave_keeps_a_draft_and_marks_started(self):
        n = self.names()
        response = self.post(
            {n["tools"]: ["Chat", "Mail"], n["note"]: "later"}, autosave=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        draft = SurveyResponse.objects.get(survey=self.survey)
        self.assertTrue(draft.is_draft)
        self.assertEqual(draft.invitation, self.invitation)
        self.assertEqual(
            draft.answers_by_question(),
            {self.tools.pk: ["Chat", "Mail"], self.note.pk: "later"},
        )
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, SurveyInvitation.STATUS_STARTED)

        # Coming back shows the draft
        page = self.client.get(self.url())
        self.assertContains(page, 'value="later"')

    def test_autosave_ignores_a_bad_value_without_failing(self):
        n = self.names()
        self.post({n["mood"]: "9", n["note"]: "ok"}, autosave=True)
        self.assertEqual(
            SurveyResponse.objects.get().answers_by_question(), {self.note.pk: "ok"}
        )

    def test_submit_validates_required_and_options(self):
        n = self.names()
        response = self.post({n["tools"]: ["Fax"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This question is required.")
        self.assertContains(response, "Choose from the given options.")
        self.assertTrue(SurveyResponse.objects.get().is_draft)

    def test_submitting_an_anonymous_survey_forgets_who(self):
        n = self.names()
        response = self.post({n["mood"]: "4", n["tools"]: ["Chat"], n["note"]: "fine"})
        self.assertContains(response, "your answers are in")
        answer = SurveyResponse.objects.get()
        self.assertFalse(answer.is_draft)
        self.assertIsNone(answer.invitation)
        self.assertEqual(answer.answers_by_question()[self.mood.pk], "4")
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, SurveyInvitation.STATUS_SUBMITTED)
        self.assertIsNotNone(self.invitation.submitted_at)
        # The same link now only says thank you, and takes nothing more
        self.assertContains(self.client.get(self.url()), "already answered")
        self.post({n["note"]: "again"})
        self.assertEqual(SurveyAnswer.objects.get(question=self.note).value, "fine")

    def test_a_named_survey_keeps_the_link(self):
        Survey.objects.filter(pk=self.survey.pk).update(is_anonymous=False)
        self.post({self.names()["mood"]: "5"})
        self.assertEqual(SurveyResponse.objects.get().invitation, self.invitation)

    def test_a_closed_survey_takes_nothing(self):
        Survey.objects.filter(pk=self.survey.pk).update(status=Survey.STATUS_CLOSED)
        self.assertContains(self.client.get(self.url()), "not open")
        self.post({self.names()["mood"]: "5"})
        self.assertFalse(SurveyResponse.objects.exists())
