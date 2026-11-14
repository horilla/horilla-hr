"""The public page, the mail and the wording: what a person with a keyboard, a screen
reader, another language or a shared computer meets.

Each test pins something the first version got wrong: a page the browser may keep, a
question a screen reader cannot name, a count that said "1 employees", a date that
ignored the language, a sentence that began with "You".
"""

import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import formats, timezone, translation

from surveys.models import Survey, SurveyQuestion
from surveys.tests.support import answer_url, build_survey, hr_client, submit

SURVEYS = Path(__file__).resolve().parent.parent


class PublicPageHeadersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="hdr", people=2)
        cls.invitation = cls.built.invitations[0]

    def assert_private(self, response):
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["X-Robots-Tag"], "noindex")

    def test_the_answer_page_is_not_kept_and_does_not_pass_the_link_on(self):
        self.assert_private(Client().get(answer_url(self.invitation)))

    def test_the_other_answers_of_the_link_are_private_too(self):
        client = Client()
        self.assert_private(client.get(answer_url("x" * 43)))  # 404
        self.assert_private(
            client.post(answer_url(self.invitation) + "?autosave=1", {})
        )  # JSON
        submit(self.built, self.invitation)
        self.assert_private(client.get(answer_url(self.invitation)))  # done page
        Survey.objects.filter(pk=self.built.survey.pk).update(
            status=Survey.STATUS_CLOSED
        )
        other = self.built.invitations[1]
        self.assert_private(client.get(answer_url(other)))  # closed page

    def test_the_page_names_the_company_that_sent_it(self):
        page = Client().get(answer_url(self.invitation))
        self.assertContains(page, '<p class="sv-brand">hdr Co</p>', html=False)
        self.assertContains(page, "<title>Pulse - hdr Co</title>", html=False)


class AnswerPageMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="mrk", people=2)
        cls.built.mood.is_required = True
        cls.built.mood.save()
        cls.nps = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=3,
            type=SurveyQuestion.TYPE_NPS,
            question="Recommend?",
        )
        cls.tools = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=4,
            type=SurveyQuestion.TYPE_MULTIPLE,
            question="Tools?",
            options=["Chat", "Mail"],
        )
        cls.invitation = cls.built.invitations[0]

    def page(self):
        return Client().get(answer_url(self.invitation)).content.decode()

    def test_a_group_of_options_is_a_fieldset_with_a_legend(self):
        html = self.page()
        self.assertIn('<fieldset class="sv-set"', html)
        for question in ("Mood?", "Recommend?", "Tools?"):
            self.assertRegex(
                html, rf"<legend[^>]*>[^<]*<span[^>]*>\d+\.</span>{question}"
            )

    def test_a_single_field_has_a_label_that_points_at_it(self):
        html = self.page()
        pk = self.built.note.pk
        self.assertIn(f'<label for="f-{pk}">', html)
        self.assertIn(f'id="f-{pk}"', html)

    def test_required_questions_are_marked_for_assistive_technology(self):
        html = self.page()
        self.assertIn('role="radiogroup" aria-required="true"', html)
        self.assertEqual(html.count("aria-required"), 1)  # only the required one

    def test_the_save_status_and_progress_are_announced(self):
        html = self.page()
        self.assertIn('id="savedAt" role="status" aria-live="polite"', html)
        self.assertIn("Questions answered:", html)

    def test_scores_say_which_end_is_which(self):
        html = self.page()
        self.assertIn("0 is the lowest", html)
        self.assertIn("10 is the highest", html)

    def test_errors_are_summarised_linked_and_tied_to_their_field(self):
        response = Client().post(
            answer_url(self.invitation), {self.built.note_name(): "x"}
        )
        html = response.content.decode()
        mood = self.built.mood.pk
        self.assertIn('id="errorSummary" role="alert" tabindex="-1"', html)
        self.assertIn(f'href="#q-{mood}"', html)
        self.assertIn(f'id="q-{mood}"', html)
        self.assertIn(f'id="err-{mood}"', html)
        self.assertIn(f'aria-describedby="err-{mood}"', html)
        self.assertIn("Please answer this question.", html)

    def test_the_error_of_a_text_field_is_marked_invalid(self):
        SurveyQuestion.objects.filter(pk=self.built.note.pk).update(is_required=True)
        response = Client().post(
            answer_url(self.invitation), {self.built.mood_name(): "3"}
        )
        pk = self.built.note.pk
        html = response.content.decode()
        self.assertRegex(
            html, rf'id="f-{pk}"[^>]*aria-invalid="true" aria-describedby="err-{pk}"'
        )

    def test_the_brand_colour_is_dark_enough_for_white_text(self):
        css = (SURVEYS / "templates/surveys/public/base.html").read_text()
        # #c8321b with white text is 5.35:1; the old #e54f38 was 3.81:1
        self.assertIn("--sv-primary: #c8321b", css)
        self.assertNotIn("#e54f38", css)
        self.assertIn(":focus-visible", css)


class ChartAlternativesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="cht", anonymous=False, people=3)
        for invitation in cls.built.invitations[:3]:
            submit(cls.built, invitation, mood="4")

    def test_a_chart_has_a_label_and_the_same_numbers_as_a_table(self):
        page = hr_client(self.built).get(
            reverse("survey-results-tab", args=[self.built.survey.pk])
        )
        html = page.content.decode()
        self.assertIn('<canvas id="chart-', html)
        self.assertIn('role="img"', html)
        self.assertIn("Chart of the answers to: Mood?", html)
        self.assertRegex(html, r"<td>4</td><td>3</td>")  # three people chose 4

    def test_the_dashboard_charts_are_labelled_and_have_tables(self):
        html = hr_client(self.built).get(reverse("surveys-dashboard")).content.decode()
        self.assertEqual(len(re.findall(r'<canvas id="chart\w+" role="img"', html)), 2)
        self.assertIn('id="tableDays"', html)
        self.assertIn('id="tableDept"', html)


class ReorderWithoutTheMouseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="mov", people=1)

    def test_questions_can_be_moved_with_buttons(self):
        html = (
            hr_client(self.built)
            .get(reverse("survey-questions-tab", args=[self.built.survey.pk]))
            .content.decode()
        )
        self.assertEqual(html.count('data-direction="-1"'), 2)
        self.assertEqual(html.count('data-direction="1"'), 2)
        self.assertIn('aria-label="Move up"', html)


class CountsAndDatesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = build_survey(tag="cn1", people=0, status=Survey.STATUS_DRAFT)
        cls.many = build_survey(tag="cn2", people=3, status=Survey.STATUS_DRAFT)

    def audience(self, built):
        return (
            hr_client(built)
            .get(reverse("survey-audience-tab", args=[built.survey.pk]))
            .content.decode()
        )

    def test_one_employee_is_not_employees(self):
        self.assertIn("1 active employee matches", self.audience(self.one))
        self.assertIn("4 active employees match", self.audience(self.many))

    def test_one_response_is_not_responses(self):
        built = build_survey(tag="cn3", anonymous=False, people=2)
        submit(built, built.invitations[0])
        page = hr_client(built).get(
            reverse("survey-results-tab", args=[built.survey.pk])
        )
        self.assertRegex(page.content.decode(), r">1</span>\s*response\b")

    def test_one_person_who_has_not_answered(self):
        built = build_survey(tag="cn4", anonymous=False, people=0)
        html = self.audience(built)
        self.assertIn("1 person has not answered yet", html)

    def test_dates_follow_the_language(self):
        built = build_survey(tag="dat", people=1)
        moment = timezone.now() + timezone.timedelta(days=3)
        Survey.objects.filter(pk=built.survey.pk).update(closes_at=moment)
        expected = {}
        for language in ("en", "de"):
            with translation.override(language):
                expected[language] = formats.date_format(
                    timezone.localtime(moment), "DATETIME_FORMAT"
                )
        self.assertNotEqual(expected["en"], expected["de"])
        # the template, rendered the way a request in that language would
        for language, text in expected.items():
            with translation.override(language):
                html = render_to_string(
                    "surveys/public/closed.html",
                    {
                        "survey": Survey.objects.get(pk=built.survey.pk),
                        "reason": "ended",
                    },
                )
                self.assertIn(text, html)
        self.assertNotRegex(html, r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}")


class MailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="mal", people=1)

    def context(self, **extra):
        return {
            "survey": self.built.survey,
            "employee": self.built.invitations[0].employee,
            "url": "https://hr.example.com/surveys/s/TOKEN/",
            **extra,
        }

    def test_the_html_mail_repeats_the_link_as_text(self):
        html = render_to_string("surveys/mail/invitation.html", self.context())
        self.assertIn("If the button does not work, copy this link", html)
        self.assertEqual(html.count("https://hr.example.com/surveys/s/TOKEN/"), 2)

    def test_the_reminder_prefix_is_a_translatable_string(self):
        reminder = render_to_string(
            "surveys/mail/invitation_subject.txt", self.context(reminder=True)
        ).strip()
        first = render_to_string(
            "surveys/mail/invitation_subject.txt", self.context()
        ).strip()
        self.assertEqual(reminder, "Reminder: Pulse")
        self.assertEqual(first, "Pulse")
        source = (SURVEYS / "templates/surveys/mail/invitation_subject.txt").read_text()
        self.assertIn('{% trans "Reminder:" %}', source)


class WordingTests(TestCase):
    """A guard over every text the module can show."""

    TEXT = re.compile(
        r"""(?:\{%\s*trans\s+|\b_\(\s*|gettext(?:_lazy|_noop)?\(\s*|\{%\s*blocktrans[^%]*%\})\s*["']?\s*(You\w*)\b"""
    )

    def sources(self):
        for path in SURVEYS.rglob("*"):
            if path.suffix in {".py", ".html", ".txt"} and "tests" not in path.parts:
                if "migrations" in path.parts:
                    continue
                yield path

    def test_no_text_begins_with_you(self):
        found = []
        for path in self.sources():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if self.TEXT.search(line):
                    found.append(
                        f"{path.relative_to(SURVEYS)}:{number}: {line.strip()}"
                    )
        self.assertEqual(found, [])

    def test_the_old_blunt_wording_is_gone(self):
        text = "".join(path.read_text() for path in self.sources())
        for blunt in ("This question is required", "You do not have permission"):
            self.assertNotIn(blunt, text)
