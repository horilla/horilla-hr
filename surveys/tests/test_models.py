"""The survey models: audience, invitations, anonymity and state."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from base.models import Department
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee
from surveys.models import Survey, SurveyInvitation, SurveyQuestion


class SurveyAudienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_selected_company(None)
        cls.company = make_company("Survey Co")
        cls.it = Department.objects.create(department="IT")
        cls.hr = Department.objects.create(department="HR")
        cls.alice = make_employee(
            company=cls.company, email="alice@test.horilla", department=cls.it
        )
        cls.bob = make_employee(
            company=cls.company, email="bob@test.horilla", department=cls.it
        )
        cls.carol = make_employee(
            company=cls.company, email="carol@test.horilla", department=cls.hr
        )
        cls.gone = make_employee(
            company=cls.company, email="gone@test.horilla", department=cls.hr
        )
        type(cls.gone).objects.filter(pk=cls.gone.pk).update(is_active=False)

    def survey(self, **kwargs):
        return Survey.objects.create(title="Pulse", company_id=self.company, **kwargs)

    def test_everyone_active_by_default(self):
        self.assertEqual(
            set(self.survey().audience_employees().values_list("email", flat=True)),
            {"alice@test.horilla", "bob@test.horilla", "carol@test.horilla"},
        )

    def test_by_department(self):
        survey = self.survey(audience=Survey.AUDIENCE_DEPARTMENTS)
        survey.departments.add(self.it)
        self.assertEqual(set(survey.audience_employees()), {self.alice, self.bob})

    def test_by_selected_employees(self):
        survey = self.survey(audience=Survey.AUDIENCE_EMPLOYEES)
        survey.employees.add(self.carol)
        self.assertEqual(list(survey.audience_employees()), [self.carol])

    def test_invite_creates_tokens_once(self):
        survey = self.survey()
        first = survey.invite()
        self.assertEqual(len(first), 3)
        self.assertEqual(len({i.token for i in first}), 3)
        self.assertTrue(all(len(i.token) >= 43 for i in first))
        self.assertEqual(survey.invite(), [])  # idempotent

    def test_invite_picks_up_newcomers(self):
        survey = self.survey()
        survey.invite()
        make_employee(
            company=self.company, email="dan@test.horilla", department=self.it
        )
        self.assertEqual(
            [i.employee.email for i in survey.invite()], ["dan@test.horilla"]
        )

    def test_response_rate(self):
        survey = self.survey()
        a, b, c = survey.invite()
        SurveyInvitation.objects.filter(pk=a.pk).update(
            status=SurveyInvitation.STATUS_SUBMITTED
        )
        self.assertEqual(survey.response_rate(), 33)


class SurveyStateTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.survey = Survey(title="Pulse", status=Survey.STATUS_OPEN)

    def test_draft_and_closed_do_not_accept(self):
        self.survey.status = Survey.STATUS_DRAFT
        self.assertFalse(self.survey.is_accepting())
        self.survey.status = Survey.STATUS_CLOSED
        self.assertFalse(self.survey.is_accepting())

    def test_window(self):
        now = timezone.now()
        self.survey.opens_at = now + timedelta(hours=1)
        self.assertFalse(self.survey.is_accepting(now))
        self.survey.opens_at = now - timedelta(hours=1)
        self.survey.closes_at = now - timedelta(minutes=1)
        self.assertFalse(self.survey.is_accepting(now))
        self.survey.closes_at = now + timedelta(days=1)
        self.assertTrue(self.survey.is_accepting(now))

    def test_closes_after_opens(self):
        now = timezone.now()
        self.survey.opens_at, self.survey.closes_at = now, now
        with self.assertRaises(ValidationError):
            self.survey.clean()


class SurveyQuestionTests(TestCase):
    def test_choice_needs_two_distinct_options(self):
        q = SurveyQuestion(type=SurveyQuestion.TYPE_CHOICE, question="?", options=["a"])
        with self.assertRaises(ValidationError):
            q.clean()
        q.options = ["a", " a "]
        with self.assertRaises(ValidationError):
            q.clean()
        q.options = [" a ", "b", ""]
        q.clean()
        self.assertEqual(q.options, ["a", "b"])

    def test_other_types_drop_options(self):
        q = SurveyQuestion(
            type=SurveyQuestion.TYPE_RATING, question="?", options=["x", "y"]
        )
        q.clean()
        self.assertEqual(q.options, [])
        self.assertEqual([v for v, _ in q.choices()], ["1", "2", "3", "4", "5"])
        self.assertTrue(q.charted())
        self.assertFalse(SurveyQuestion(type=SurveyQuestion.TYPE_TEXT).charted())
