"""The demo seed gives the Surveys screens something to show, and stays private."""

from datetime import date

from django.test import TestCase

from base.demo_data.modules.surveys_demo import ANSWERERS, TITLE, seed_demo_survey
from horilla.testkit import make_company, make_employee
from surveys.models import Survey, SurveyResponse


class DemoSurveySeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Demo Seed Co")
        for number in range(ANSWERERS + 3):
            make_employee(company=cls.company, email=f"seed{number}@test.horilla")

    def test_creates_one_closed_anonymous_survey_with_releasable_results(self):
        result = seed_demo_survey(date.today())
        self.assertEqual(result["created"], 1)
        survey = Survey._base_manager.get(title=TITLE)
        self.assertEqual(survey.status, Survey.STATUS_CLOSED)
        self.assertTrue(survey.is_anonymous)
        self.assertEqual(survey.submitted_count(), ANSWERERS)
        self.assertEqual(survey.results_hold(), "")

    def test_the_seeded_answers_carry_no_identity(self):
        seed_demo_survey(date.today())
        responses = SurveyResponse._base_manager.filter(is_draft=False)
        self.assertEqual(responses.count(), ANSWERERS)
        for response in responses:
            self.assertIsNone(response.invitation_id)
            self.assertIsNone(response.created_by_id)

    def test_running_twice_does_not_duplicate(self):
        seed_demo_survey(date.today())
        again = seed_demo_survey(date.today())
        self.assertEqual(again, {"created": 0})
        self.assertEqual(Survey._base_manager.filter(title=TITLE).count(), 1)
