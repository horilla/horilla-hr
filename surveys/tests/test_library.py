"""The library: standard questionnaires, a survey from one, saving one, the 0-10 scale."""

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase, override_settings
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from surveys import answers
from surveys.library import STANDARD, load_standard
from surveys.models import (
    Questionnaire,
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class LibraryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_selected_company(None)
        # An installation may add questionnaires of its own by migration
        Questionnaire._base_manager.all().delete()
        cls.company = make_company("Library Co")
        cls.hr_user = make_user("library_hr", is_superuser=True)
        cls.hr = make_employee(
            company=cls.company, email="hr@library.horilla", user=cls.hr_user
        )
        cls.plain_user = make_user("library_plain")
        cls.plain = make_employee(
            company=cls.company, email="plain@library.horilla", user=cls.plain_user
        )

    def setUp(self):
        self.client.force_login(self.hr_user)

    def make_questionnaire(self, **kwargs):
        defaults = {
            "title": "Team pulse",
            "description": "Monthly.",
            "is_anonymous": False,
            "questions": [
                {"type": "rating", "question": "Mood?", "is_required": True},
                {"type": "choice", "question": "Office?", "options": ["Yes", "No"]},
                {"type": "textarea", "question": "Anything else?"},
            ],
        }
        defaults.update(kwargs)
        return Questionnaire.objects.create(**defaults)

    def create_survey(self, **data):
        form = {"title": "Pulse", "description": "", "audience": "all"}
        form.update(data)
        return self.client.post(reverse("survey-create"), form, HTTP_HX_REQUEST="true")

    # --- the standard questionnaires --------------------------------------

    def test_the_standard_questionnaires_load_once(self):
        added = load_standard()
        self.assertEqual([q.code for q in added], ["enps", "engagement", "new_hire_30"])
        self.assertEqual(load_standard(), [])
        self.assertEqual(Questionnaire.objects.count(), 3)

    def test_every_standard_questionnaire_builds_valid_questions(self):
        for questionnaire in load_standard():
            questions = questionnaire.build_questions()
            self.assertEqual(
                len(questions), questionnaire.question_count(), questionnaire.code
            )
            self.assertTrue(all(q.question for q in questions), questionnaire.code)
        self.assertEqual(len(STANDARD), 3)
        enps = Questionnaire.objects.get(code="enps")
        self.assertEqual(enps.questions[0]["type"], SurveyQuestion.TYPE_NPS)
        self.assertTrue(enps.is_anonymous)

    def test_loading_again_keeps_changes_and_returns_a_deleted_one(self):
        load_standard()
        Questionnaire.objects.filter(code="enps").update(title="Our eNPS")
        Questionnaire.objects.get(code="engagement").delete()

        added = load_standard()
        self.assertEqual([q.code for q in added], ["engagement"])
        self.assertEqual(Questionnaire.objects.get(code="enps").title, "Our eNPS")

    def test_the_button_and_the_command_load_them(self):
        response = self.client.post(reverse("surveys-library-load-standard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Questionnaire.objects.count(), 3)
        Questionnaire.objects.all().delete()
        call_command("seed_survey_library", verbosity=0)
        self.assertEqual(Questionnaire.objects.count(), 3)

    def test_a_broken_question_is_refused(self):
        questionnaire = Questionnaire(
            title="Broken", questions=[{"type": "choice", "question": "One option?"}]
        )
        with self.assertRaises(ValidationError):
            questionnaire.full_clean()

    # --- the page -----------------------------------------------------------

    def test_the_library_page_shows_the_questionnaires(self):
        self.make_questionnaire()
        page = self.client.get(reverse("surveys-library"))
        self.assertContains(page, "Team pulse")
        self.assertContains(page, "3 questions")
        self.assertContains(page, "Anything else?")
        self.assertContains(page, "Rating 1–5")

        self.client.force_login(self.plain_user)
        self.assertNotEqual(
            self.client.get(reverse("surveys-library")).status_code, 200
        )

    # --- a survey from the library or blank ---------------------------------

    def test_use_fills_the_create_form_from_the_questionnaire(self):
        questionnaire = self.make_questionnaire()
        form = self.client.get(
            reverse("survey-create") + f"?questionnaire={questionnaire.pk}",
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(form, 'value="Team pulse"')
        self.assertContains(form, "Monthly.")
        self.assertRegex(
            form.content.decode(), rf'<option value="{questionnaire.pk}"\s+selected'
        )

    def test_a_survey_from_the_library_gets_a_copy_of_the_questions(self):
        questionnaire = self.make_questionnaire()
        response = self.create_survey(questionnaire=questionnaire.pk)
        survey = Survey.objects.get(title="Pulse")
        self.assertContains(response, survey.get_detail_url())
        self.assertEqual(survey.status, Survey.STATUS_DRAFT)
        self.assertEqual(
            [
                (q.sequence, q.type, q.question, q.options, q.is_required)
                for q in survey.questions.all()
            ],
            [
                (1, "rating", "Mood?", [], True),
                (2, "choice", "Office?", ["Yes", "No"], False),
                (3, "textarea", "Anything else?", [], False),
            ],
        )

        # The copy is the survey's own: changing it leaves the library alone
        first = survey.questions.first()
        self.client.post(
            reverse("survey-question-edit", args=[first.pk]),
            {"question": "How was the week?", "type": "rating"},
            HTTP_HX_REQUEST="true",
        )
        self.client.post(
            reverse("survey-question-delete", args=[survey.questions.last().pk])
        )
        self.assertEqual(
            [q.question for q in survey.questions.all()],
            ["How was the week?", "Office?"],
        )
        questionnaire.refresh_from_db()
        self.assertEqual(questionnaire.questions[0]["question"], "Mood?")
        self.assertEqual(questionnaire.question_count(), 3)

    def test_a_blank_survey_has_no_questions(self):
        self.make_questionnaire()
        self.create_survey(questionnaire="blank")
        self.create_survey(title="No choice sent")
        for title in ("Pulse", "No choice sent"):
            self.assertFalse(Survey.objects.get(title=title).questions.exists(), title)

    def test_the_create_form_offers_the_library_only_when_it_has_something(self):
        form = self.client.get(reverse("survey-create"), HTTP_HX_REQUEST="true")
        self.assertNotContains(form, 'name="questionnaire"')
        self.make_questionnaire()
        form = self.client.get(reverse("survey-create"), HTTP_HX_REQUEST="true")
        self.assertContains(form, 'name="questionnaire"')
        # "Blank survey" is selected, and is a value Horilla's select keeps enabled
        self.assertRegex(form.content.decode(), r'<option value="blank"\s+selected')

        survey = Survey.objects.create(title="Old", company_id=self.company)
        edit = self.client.get(
            reverse("survey-edit", args=[survey.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertNotContains(edit, 'name="questionnaire"')

    # --- saving to the library ----------------------------------------------

    def survey_with_questions(self):
        survey = Survey.objects.create(
            title="Exit talk", description="On leaving.", company_id=self.company
        )
        SurveyQuestion.objects.create(
            survey=survey, sequence=2, type="yes_no", question="Would you return?"
        )
        SurveyQuestion.objects.create(
            survey=survey,
            sequence=1,
            type="multiple",
            question="Why?",
            options=["Pay", "Growth"],
            is_required=True,
        )
        return survey

    def save_to_library(self, survey, **data):
        form = {"title": survey.title, "description": survey.description}
        form.update(data)
        return self.client.post(
            reverse("survey-save-to-library", args=[survey.pk]),
            form,
            HTTP_HX_REQUEST="true",
        )

    def test_a_survey_is_saved_as_a_new_questionnaire(self):
        survey = self.survey_with_questions()
        form = self.client.get(
            reverse("survey-save-to-library", args=[survey.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(form, 'value="Exit talk"')

        self.save_to_library(survey, title="Exit interview", is_anonymous="on")
        questionnaire = Questionnaire.objects.get(title="Exit interview")
        self.assertEqual(
            (questionnaire.company_id, questionnaire.is_anonymous, questionnaire.code),
            (self.company, True, ""),
        )
        self.assertEqual(
            questionnaire.questions,
            [
                {
                    "type": "multiple",
                    "question": "Why?",
                    "options": ["Pay", "Growth"],
                    "is_required": True,
                },
                {
                    "type": "yes_no",
                    "question": "Would you return?",
                    "options": [],
                    "is_required": False,
                },
            ],
        )

    def test_a_survey_replaces_a_questionnaire(self):
        old = self.make_questionnaire()
        survey = self.survey_with_questions()
        self.save_to_library(survey, replace=old.pk, title="Exit interview")
        self.assertEqual(Questionnaire.objects.count(), 1)
        old.refresh_from_db()
        self.assertEqual(
            (old.title, old.question_count(), old.questions[0]["question"]),
            ("Exit interview", 2, "Why?"),
        )

    def test_a_survey_without_questions_is_not_saved(self):
        survey = Survey.objects.create(title="Empty", company_id=self.company)
        self.save_to_library(survey)
        self.assertFalse(Questionnaire.objects.exists())

    def test_the_library_is_changed_only_with_its_permissions(self):
        questionnaire = self.make_questionnaire()
        survey = self.survey_with_questions()
        survey.managers.add(self.plain)  # manages the survey, not the library
        self.client.force_login(self.plain_user)

        self.save_to_library(survey)
        self.client.post(reverse("surveys-library-load-standard"))
        self.client.post(reverse("questionnaire-delete", args=[questionnaire.pk]))
        self.client.post(
            reverse("questionnaire-edit", args=[questionnaire.pk]),
            {"title": "Hacked"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(
            list(Questionnaire.objects.values_list("title", flat=True)),
            ["Team pulse"],
        )

    def test_editing_and_deleting_a_questionnaire(self):
        questionnaire = self.make_questionnaire()
        self.client.post(
            reverse("questionnaire-edit", args=[questionnaire.pk]),
            {"title": "Weekly pulse", "description": "", "is_anonymous": "on"},
            HTTP_HX_REQUEST="true",
        )
        questionnaire.refresh_from_db()
        self.assertEqual(
            (
                questionnaire.title,
                questionnaire.is_anonymous,
                questionnaire.question_count(),
            ),
            ("Weekly pulse", True, 3),
        )
        self.client.post(reverse("questionnaire-delete", args=[questionnaire.pk]))
        self.assertFalse(Questionnaire.objects.exists())


class NpsScaleTests(TestCase):
    """The 0-10 scale: what it accepts and the score in the results."""

    @classmethod
    def setUpTestData(cls):
        set_selected_company(None)
        cls.company = make_company("NPS Co")
        cls.hr_user = make_user("nps_hr", is_superuser=True)
        cls.hr = make_employee(
            company=cls.company, email="hr@nps.horilla", user=cls.hr_user
        )
        cls.survey = Survey.objects.create(
            title="eNPS", status=Survey.STATUS_OPEN, company_id=cls.company
        )
        cls.question = SurveyQuestion.objects.create(
            survey=cls.survey,
            sequence=1,
            type=SurveyQuestion.TYPE_NPS,
            question="Recommend us?",
            is_required=True,
        )

    def test_the_scale_runs_from_0_to_10(self):
        self.assertEqual(
            [value for value, _label in self.question.choices()],
            [str(i) for i in range(11)],
        )
        self.assertEqual(answers.validate(self.question, "0"), "0")
        self.assertEqual(answers.validate(self.question, "10"), "10")
        for wrong in ("11", "-1", "five"):
            with self.assertRaises(answers.AnswerError):
                answers.validate(self.question, wrong)
        with self.assertRaises(answers.AnswerError):
            answers.validate(self.question, None)  # required

    def test_the_form_offers_the_eleven_values(self):
        (invitation,) = self.survey.invite()
        page = self.client.get(reverse("survey-answer", args=[invitation.token]))
        name = answers.field_name(self.question)
        for value in (0, 10):
            self.assertContains(page, f'name="{name}" value="{value}"')

        data = QueryDict(mutable=True)
        data[name] = "0"  # zero is an answer, not an empty field
        values, errors = answers.collect([self.question], data, strict=True)
        self.assertEqual((values, errors), ({self.question: "0"}, {}))

    def test_the_results_give_the_score(self):
        # 10, 9, 9 promote; 8, 7 are passive; 6, 3, 0 detract: (3 - 3) / 8 = 0
        scores = ["10", "9", "9", "8", "7", "6", "3", "0"]
        for index, score in enumerate(scores):
            employee = make_employee(
                company=self.company, email=f"e{index}@nps.horilla"
            )
            invitation = SurveyInvitation.objects.create(
                survey=self.survey,
                employee=employee,
                token=SurveyInvitation.new_token(),
                status=SurveyInvitation.STATUS_SUBMITTED,
            )
            response = SurveyResponse.objects.create(
                survey=self.survey, invitation=invitation, is_draft=False
            )
            SurveyAnswer.objects.create(
                response=response, question=self.question, value=score
            )
        self.client.force_login(self.hr_user)
        url = reverse("survey-results-tab", args=[self.survey.pk])
        page = self.client.get(url)
        self.assertEqual(
            page.context["results"][0]["nps"],
            {"score": 0, "promoters": 3, "passives": 2, "detractors": 3},
        )
        self.assertContains(page, '"series": [1, 0, 0, 1, 0, 0, 1, 1, 1, 2, 1]')
        self.assertContains(page, "<b>6.5</b>")

        SurveyAnswer.objects.filter(value__in=["3", "0"]).delete()
        nps = self.client.get(url).context["results"][0]["nps"]
        # 3 promoters, 1 detractor of 6: +33
        self.assertEqual((nps["score"], nps["detractors"]), (33, 1))
