"""An anonymous survey must not give its answers away.

Covers the identity stamp that Horilla puts on every record, the times that could
be matched against the audience list, the minimum number of answers before
results show, and what happens to unfinished drafts.
"""

import csv
import io
import re
from datetime import datetime, time
from importlib import import_module
from unittest import mock

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import formats, timezone

from surveys.forms import SurveyForm
from surveys.models import Survey, SurveyInvitation, SurveyResponse
from surveys.tests.support import (
    answer_url,
    build_survey,
    close,
    hr_client,
    submit,
)

CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def is_local_midnight(value):
    local = timezone.localtime(value)
    return local.time() == time(0, 0)


@override_settings(CACHES=CACHE)
class IdentityStampTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anon = build_survey(tag="stamp_a", anonymous=True)
        cls.named = build_survey(tag="stamp_n", anonymous=False)

    def logged_in_as(self, invitation):
        user = invitation.employee.employee_user_id
        self.assertIsNotNone(user, "the test needs an employee with a user")
        client = Client()
        client.force_login(user)
        return client, user

    def test_an_anonymous_response_carries_no_user_even_when_the_respondent_is_logged_in(
        self,
    ):
        invitation = self.anon.invitations[0]
        client, _user = self.logged_in_as(invitation)

        client.post(
            answer_url(invitation) + "?autosave=1", {self.anon.note_name(): "wip"}
        )
        draft = SurveyResponse.objects.get(survey=self.anon.survey)
        self.assertIsNone(draft.created_by_id, "stamped while a draft")
        self.assertIsNone(draft.modified_by_id)

        submit(self.anon, invitation, client=client)
        response = SurveyResponse.objects.get(survey=self.anon.survey)
        self.assertFalse(response.is_draft)
        self.assertIsNone(response.created_by_id, "stamped after submit")
        self.assertIsNone(response.modified_by_id)
        self.assertIsNone(response.invitation_id)

    def test_a_named_survey_keeps_its_invitation_and_exact_time(self):
        """The control: a named response is tied to its person by the invitation.

        It carries no browser-session stamp either: whoever happens to be logged
        in (an HR admin opening an employee's link to see it) is not its author.
        """
        invitation = self.named.invitations[0]
        client, _user = self.logged_in_as(invitation)
        submit(self.named, invitation, client=client)
        response = SurveyResponse.objects.get(survey=self.named.survey)
        self.assertEqual(response.invitation_id, invitation.pk)
        self.assertFalse(is_local_midnight(response.submitted_at))
        self.assertIsNone(response.created_by_id)

    def test_an_anonymous_response_keeps_only_the_date(self):
        invitation = self.anon.invitations[1]
        submit(self.anon, invitation)
        response = SurveyResponse.objects.get(
            survey=self.anon.survey, is_draft=False, invitation=None
        )
        for field in ("created_at", "started_at", "submitted_at"):
            value = getattr(response, field)
            self.assertTrue(is_local_midnight(value), f"{field} is {value}")
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, SurveyInvitation.STATUS_SUBMITTED)
        self.assertTrue(is_local_midnight(invitation.submitted_at))
        # Nothing left that is exactly equal on both sides to the microsecond
        self.assertEqual(
            timezone.localtime(response.submitted_at).date(),
            timezone.localtime(invitation.submitted_at).date(),
        )


@override_settings(CACHES=CACHE)
class MinimumAnswersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anon = build_survey(tag="min_a", anonymous=True)
        cls.named = build_survey(tag="min_n", anonymous=False)

    def answer(self, built, count, prefix="secret"):
        for number, invitation in enumerate(built.invitations[:count]):
            submit(built, invitation, note=f"{prefix}-{number}")

    def test_results_and_export_wait_for_five_answers(self):
        self.answer(self.anon, 4)
        close(self.anon)
        hr = hr_client(self.anon)
        page = hr.get(reverse("survey-results-tab", args=[self.anon.survey.pk]))
        self.assertContains(page, "once 5 people have answered")
        self.assertNotContains(page, "secret-0")
        export = hr.get(reverse("survey-export", args=[self.anon.survey.pk]))
        self.assertEqual(export.status_code, 302)  # back to the survey, with a message
        self.assertNotIn("text/csv", export.get("Content-Type", ""))
        self.assertNotIn(b"secret-0", export.content)

        self.reopen(self.anon)
        self.answer(self.anon, 5)  # the fifth person
        close(self.anon)
        page = hr.get(reverse("survey-results-tab", args=[self.anon.survey.pk]))
        self.assertNotContains(page, "once 5 people have answered")
        self.assertContains(page, "secret-0")
        export = hr.get(reverse("survey-export", args=[self.anon.survey.pk]))
        self.assertIn("text/csv", export["Content-Type"])

    def reopen(self, built):
        Survey.objects.filter(pk=built.survey.pk).update(status=Survey.STATUS_OPEN)
        built.survey.refresh_from_db()

    @override_settings(SURVEYS_MIN_RESPONSES=2)
    def test_the_minimum_is_a_setting(self):
        hr = hr_client(self.anon)
        url = reverse("survey-results-tab", args=[self.anon.survey.pk])
        self.answer(self.anon, 1)
        close(self.anon)
        self.assertContains(hr.get(url), "once 2 people have answered")
        self.reopen(self.anon)
        self.answer(self.anon, 2)
        close(self.anon)
        self.assertNotContains(hr.get(url), "once 2 people have answered")

    def test_a_named_survey_shows_results_for_a_single_answer(self):
        self.answer(self.named, 1)
        page = hr_client(self.named).get(
            reverse("survey-results-tab", args=[self.named.survey.pk])
        )
        self.assertNotContains(page, "people have answered")
        self.assertContains(page, "secret-0")


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class ResultsWaitForCloseTests(TestCase):
    """Two looks at the results, before and after one person answers, would give
    that person's answer away. An anonymous survey shows none until it is closed."""

    @classmethod
    def setUpTestData(cls):
        cls.anon = build_survey(tag="wait_a", anonymous=True, people=3)
        cls.named = build_survey(tag="wait_n", anonymous=False, people=3)

    def results(self, built):
        return hr_client(built).get(
            reverse("survey-results-tab", args=[built.survey.pk])
        )

    def test_an_open_anonymous_survey_shows_no_results_even_with_many_answers(self):
        for number, invitation in enumerate(self.anon.invitations[:3]):
            submit(self.anon, invitation, note=f"hush-{number}")
        page = self.results(self.anon)
        self.assertContains(page, "once the survey is closed")
        self.assertNotContains(page, "hush-0")
        self.assertEqual(page.context["results"], [])
        self.assertEqual(page.context["chart_data"], [])
        # the chart data block is there but empty: nothing for a script to draw
        self.assertContains(
            page, '<script id="survey-chart-data" type="application/json">[]</script>'
        )
        self.assertNotContains(
            page, reverse("survey-export", args=[self.anon.survey.pk])
        )

    def test_the_answers_of_an_open_survey_cannot_be_compared_before_and_after(self):
        hr = hr_client(self.anon)
        url = reverse("survey-results-tab", args=[self.anon.survey.pk])
        submit(self.anon, self.anon.invitations[0], note="first-one")
        before = hr.get(url).content
        submit(self.anon, self.anon.invitations[1], note="second-one")
        after = hr.get(url).content
        for text in (before, after):
            self.assertNotIn(b"first-one", text)
            self.assertNotIn(b"second-one", text)
        # the count of responses is not a secret (the audience list shows who
        # answered), the answers are
        self.assertEqual(hr.get(url).context["results"], [])

    def test_the_export_of_an_open_anonymous_survey_is_refused(self):
        submit(self.anon, self.anon.invitations[0], note="hush-export")
        export = hr_client(self.anon).get(
            reverse("survey-export", args=[self.anon.survey.pk])
        )
        self.assertEqual(export.status_code, 302)
        self.assertNotIn("text/csv", export.get("Content-Type", ""))
        self.assertNotIn(b"hush-export", export.content)

    def test_closing_releases_the_results_and_the_export(self):
        submit(self.anon, self.anon.invitations[0], note="after-close")
        close(self.anon)
        self.assertContains(self.results(self.anon), "after-close")
        export = hr_client(self.anon).get(
            reverse("survey-export", args=[self.anon.survey.pk])
        )
        self.assertIn("text/csv", export["Content-Type"])

    def test_a_survey_past_its_closing_time_releases_its_results(self):
        built = build_survey(tag="wait_e", anonymous=True, people=2)
        submit(built, built.invitations[0], note="ended-answer")
        # a draft that was never sent in is dropped, as on a manual close
        Client().post(
            answer_url(built.invitations[1]) + "?autosave=1",
            {built.note_name(): "unfinished"},
        )
        Survey.objects.filter(pk=built.survey.pk).update(
            closes_at=timezone.now() - timezone.timedelta(hours=1)
        )
        page = self.results(built)
        self.assertContains(page, "ended-answer")
        self.assertNotContains(page, "once the survey is closed")
        self.assertFalse(
            SurveyResponse.objects.filter(survey=built.survey, is_draft=True).exists()
        )

    def test_a_named_survey_shows_results_while_open(self):
        submit(self.named, self.named.invitations[0], note="visible-now")
        self.assertContains(self.results(self.named), "visible-now")

    def test_a_survey_in_draft_says_there_are_no_answers_yet(self):
        draft = build_survey(
            tag="wait_d", anonymous=True, people=1, status=Survey.STATUS_DRAFT
        )
        page = self.results(draft)
        self.assertNotContains(page, "once the survey is closed")


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class ExportAndAudienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anon = build_survey(tag="exp_a", anonymous=True)
        cls.named = build_survey(tag="exp_n", anonymous=False)
        # Submitted in the opposite order to the alphabet, so a list that follows
        # the order of submission cannot pass for a sorted one
        for number, invitation in enumerate(cls.anon.invitations[:4]):
            submit(cls.anon, invitation, note=f"anon-{3 - number}")
        for number, invitation in enumerate(cls.named.invitations[:2]):
            submit(cls.named, invitation, note=f"named-{number}")
        close(cls.anon)

    def rows(self, built):
        export = hr_client(built).get(reverse("survey-export", args=[built.survey.pk]))
        text = export.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))

    def test_an_anonymous_export_has_no_times_and_is_shuffled(self):
        with mock.patch(
            "surveys.views.random.shuffle", side_effect=lambda rows: rows.reverse()
        ) as shuffle:
            rows = self.rows(self.anon)
        shuffle.assert_called_once()
        header, data = rows[0], rows[1:]
        self.assertNotIn("Submitted at", header)
        self.assertNotIn("Employee", header)
        joined = "\n".join(",".join(r) for r in data)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}", joined), joined)
        self.assertEqual(
            {r[-1] for r in data}, {"anon-0", "anon-1", "anon-2", "anon-3"}
        )
        # rows are taken in creation order and then handed to the shuffle: the
        # reversing stand-in puts the last one submitted ("anon-0") first
        self.assertEqual(data[0][-1], "anon-0")

    def test_a_named_export_keeps_who_and_when(self):
        header = self.rows(self.named)[0]
        self.assertIn("Submitted at", header)
        self.assertIn("Employee", header)

    def test_the_audience_list_of_an_anonymous_survey_shows_no_answer_time(self):
        today = formats.date_format(timezone.localdate(), "DATE_FORMAT")
        anon = hr_client(self.anon).get(
            reverse("survey-invitations", args=[self.anon.survey.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(anon, "Submitted")  # who answered is still shown
        self.assertNotContains(anon, today)
        named = hr_client(self.named).get(
            reverse("survey-invitations", args=[self.named.survey.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(named, today)

    def test_free_text_answers_are_not_listed_in_submission_order(self):
        page = hr_client(self.anon).get(
            reverse("survey-results-tab", args=[self.anon.survey.pk])
        )
        html = page.content.decode()
        order = [html.index(f"anon-{n}") for n in range(4)]
        self.assertEqual(order, sorted(order))  # alphabetical: 0, 1, 2, 3
        self.assertTrue(all(order))


@override_settings(CACHES=CACHE)
class AnonymityLockAndDraftTests(TestCase):
    def setUp(self):
        self.anon = build_survey(tag="lock_a", anonymous=True)
        self.named = build_survey(tag="lock_n", anonymous=False)

    def form_data(self, survey, **extra):
        data = {
            "title": survey.title,
            "audience": Survey.AUDIENCE_ALL,
            "is_anonymous": "",
        }
        data.update(extra)
        return data

    def test_is_anonymous_cannot_change_once_the_survey_is_open(self):
        survey = self.anon.survey
        form = SurveyForm(instance=survey, data=self.form_data(survey))
        self.assertTrue(form.fields["is_anonymous"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["is_anonymous"])

        survey.is_anonymous = False
        with self.assertRaises(ValidationError) as caught:
            survey.full_clean()
        self.assertIn("is_anonymous", caught.exception.message_dict)

    def test_is_anonymous_is_free_while_the_survey_is_a_draft(self):
        draft = Survey.objects.create(
            title="Draft", company_id=self.anon.company, is_anonymous=True
        )
        form = SurveyForm(instance=draft, data=self.form_data(draft))
        self.assertFalse(form.fields["is_anonymous"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["is_anonymous"])

    def start_a_draft(self, built, invitation):
        Client().post(
            answer_url(invitation) + "?autosave=1", {built.note_name(): "half"}
        )

    def test_closing_an_anonymous_survey_deletes_unfinished_drafts(self):
        built = self.anon
        done, started = built.invitations[0], built.invitations[1]
        submit(built, done)
        self.start_a_draft(built, started)
        self.assertEqual(SurveyResponse.objects.filter(is_draft=True).count(), 1)

        hr_client(built).post(reverse("survey-close", args=[built.survey.pk]))
        built.survey.refresh_from_db()
        self.assertEqual(built.survey.status, Survey.STATUS_CLOSED)
        self.assertFalse(SurveyResponse.objects.filter(is_draft=True).exists())
        self.assertEqual(
            SurveyResponse.objects.filter(survey=built.survey, is_draft=False).count(),
            1,
        )
        started.refresh_from_db()
        self.assertEqual(started.status, SurveyInvitation.STATUS_INVITED)
        done.refresh_from_db()
        self.assertEqual(done.status, SurveyInvitation.STATUS_SUBMITTED)

    def test_closing_a_named_survey_keeps_drafts(self):
        built = self.named
        self.start_a_draft(built, built.invitations[0])
        hr_client(built).post(reverse("survey-close", args=[built.survey.pk]))
        self.assertTrue(SurveyResponse.objects.filter(is_draft=True).exists())


class ScrubMigrationTests(TestCase):
    """0003 removes identity from anonymous responses stored by the first version."""

    def test_old_anonymous_rows_are_scrubbed_and_named_ones_left_alone(self):
        anon = build_survey(tag="mig_a", anonymous=True)
        named = build_survey(tag="mig_n", anonymous=False)
        exact = timezone.make_aware(datetime(2026, 11, 12, 14, 37, 21, 123456))
        user = anon.hr_user

        def old_style(built, invitation):
            response = SurveyResponse.objects.create(
                survey=built.survey, is_draft=False, submitted_at=exact
            )
            SurveyResponse.objects.filter(pk=response.pk).update(
                created_by=user,
                modified_by=user,
                created_at=exact,
                started_at=exact,
                submitted_at=exact,
            )
            SurveyInvitation.objects.filter(pk=invitation.pk).update(
                status=SurveyInvitation.STATUS_SUBMITTED, submitted_at=exact
            )
            return response

        anonymous_response = old_style(anon, anon.invitations[0])
        named_response = old_style(named, named.invitations[0])

        migration = import_module("surveys.migrations.0003_scrub_anonymous_responses")
        migration.scrub_anonymous_responses(apps, None)

        anonymous_response.refresh_from_db()
        self.assertIsNone(anonymous_response.created_by_id)
        self.assertIsNone(anonymous_response.modified_by_id)
        for field in ("created_at", "started_at", "submitted_at"):
            self.assertTrue(is_local_midnight(getattr(anonymous_response, field)))
        anon.invitations[0].refresh_from_db()
        self.assertTrue(is_local_midnight(anon.invitations[0].submitted_at))

        named_response.refresh_from_db()
        self.assertEqual(named_response.created_by_id, user.pk)
        self.assertEqual(named_response.submitted_at, exact)
        named.invitations[0].refresh_from_db()
        self.assertEqual(named.invitations[0].submitted_at, exact)
