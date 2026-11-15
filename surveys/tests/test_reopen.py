"""Reopening a closed anonymous survey must not give an answer away.

HR sees the results at the close. If the survey is reopened, one person answers
and it is closed again, comparing the two results would show that answer. So
what was released stays as it was, and later answers join it only once at
least SURVEYS_MIN_RESPONSES of them have come in: two releases then differ by a
group, never by one person.
"""

import csv
import importlib
import io

from django.apps import apps
from django.test import TestCase, override_settings
from django.urls import reverse

from surveys.models import Survey, SurveyResponse
from surveys.tests.support import build_survey, close, hr_client, submit


def reopen(built):
    Survey.objects.filter(pk=built.survey.pk).update(status=Survey.STATUS_OPEN)
    built.survey.refresh_from_db()


class ReopenKeepsReleasedResultsTests(TestCase):
    def setUp(self):
        self.built = build_survey(tag="reopen", anonymous=True, people=14)
        self.hr = hr_client(self.built)
        self.next = 0

    def answer(self, count, label):
        for _ in range(count):
            submit(
                self.built,
                self.built.invitations[self.next],
                note=f"{label}-{self.next}",
            )
            self.next += 1

    def results(self):
        return self.hr.get(reverse("survey-results-tab", args=[self.built.survey.pk]))

    def exported_rows(self):
        response = self.hr.get(reverse("survey-export", args=[self.built.survey.pk]))
        self.assertIn("text/csv", response["Content-Type"])
        text = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))[1:]

    def first_release(self, count=6):
        self.answer(count, "early")
        close(self.built)
        page = self.results()
        self.assertEqual(page.context["total"], count)
        self.assertEqual(page.context["held"], 0)

    def test_what_was_released_stays_visible_while_the_survey_is_open_again(self):
        self.first_release()
        reopen(self.built)
        page = self.results()
        self.assertEqual(page.context["hold"], "")
        self.assertEqual(page.context["total"], 6)
        self.assertContains(page, "early-0")

    def test_answers_given_after_a_reopen_do_not_change_the_results_before_the_close(
        self,
    ):
        self.first_release()
        reopen(self.built)
        before = self.results().context["total"]
        self.answer(1, "late")
        after = self.results()
        self.assertEqual(after.context["total"], before)
        self.assertNotContains(after, "late-6")

    def test_a_few_late_answers_stay_held_after_the_second_close(self):
        self.first_release()
        reopen(self.built)
        self.answer(2, "late")
        close(self.built)
        page = self.results()
        self.assertEqual(page.context["total"], 6)
        self.assertEqual(page.context["held"], 2)
        self.assertNotContains(page, "late-6")
        self.assertContains(page, "2 newer answers are not shown yet")
        rows = self.exported_rows()
        self.assertEqual(len(rows), 6)
        self.assertNotIn("late-6", " ".join(" ".join(row) for row in rows))

    def test_late_answers_are_released_once_enough_have_come_in(self):
        self.first_release()
        reopen(self.built)
        self.answer(2, "late")
        close(self.built)
        self.assertEqual(self.results().context["total"], 6)
        reopen(self.built)
        self.answer(3, "later")
        close(self.built)
        page = self.results()
        self.assertEqual(page.context["total"], 11)
        self.assertEqual(page.context["held"], 0)
        self.assertEqual(len(self.exported_rows()), 11)

    def test_two_releases_never_differ_by_fewer_than_the_minimum(self):
        self.first_release()
        seen = [self.results().context["total"]]
        for _ in range(4):  # one new answer, then close, four times in a row
            reopen(self.built)
            self.answer(1, "drip")
            close(self.built)
            seen.append(self.results().context["total"])
        self.assertEqual(seen, [6, 6, 6, 6, 6])
        reopen(self.built)
        self.answer(1, "drip")
        close(self.built)
        seen.append(self.results().context["total"])
        # the fifth waiting answer releases all five together, never one alone
        self.assertEqual(seen[-1], 11)

    @override_settings(SURVEYS_MIN_RESPONSES=3)
    def test_the_increment_follows_the_setting(self):
        self.first_release(count=4)
        reopen(self.built)
        self.answer(2, "late")
        close(self.built)
        self.assertEqual(self.results().context["total"], 4)
        reopen(self.built)
        self.answer(1, "late")
        close(self.built)
        self.assertEqual(self.results().context["total"], 7)

    def test_a_first_close_with_too_few_answers_releases_nothing(self):
        self.answer(3, "few")
        close(self.built)
        page = self.results()
        self.assertEqual(page.context["hold"], Survey.HOLD_TOO_FEW)
        self.assertEqual(page.context["total"], 3)
        self.assertEqual(page.context["results"], [])
        self.assertEqual(
            SurveyResponse.objects.filter(
                survey=self.built.survey, released=True
            ).count(),
            0,
        )

    def test_the_export_is_cut_at_the_same_line_as_the_results(self):
        self.first_release()
        reopen(self.built)
        self.answer(1, "late")
        close(self.built)
        self.assertEqual(len(self.exported_rows()), 6)

    def test_a_named_survey_is_not_affected(self):
        named = build_survey(tag="reopen_n", anonymous=False, people=3)
        hr = hr_client(named)
        submit(named, named.invitations[0], note="named-1")
        url = reverse("survey-results-tab", args=[named.survey.pk])
        self.assertContains(hr.get(url), "named-1")
        close(named)
        reopen(named)
        submit(named, named.invitations[1], note="named-2")
        self.assertContains(hr.get(url), "named-2")


class ReleasedMigrationTests(TestCase):
    """The migration marks what a closed anonymous survey already showed."""

    def run_migration(self):
        module = importlib.import_module("surveys.migrations.0007_response_released")
        module.release_closed_anonymous(apps, None)

    def test_a_closed_survey_with_enough_answers_counts_as_released(self):
        built = build_survey(tag="mig_a", anonymous=True, people=7)
        for invitation in built.invitations[:6]:
            submit(built, invitation)
        close(built)
        SurveyResponse._base_manager.filter(survey=built.survey).update(released=False)
        self.run_migration()
        self.assertEqual(built.survey.released_count(), 6)

    def test_open_and_too_small_surveys_stay_unreleased(self):
        open_survey = build_survey(tag="mig_o", anonymous=True, people=7)
        for invitation in open_survey.invitations[:6]:
            submit(open_survey, invitation)
        few = build_survey(tag="mig_f", anonymous=True, people=7)
        for invitation in few.invitations[:3]:
            submit(few, invitation)
        close(few)
        self.run_migration()
        self.assertEqual(open_survey.survey.released_count(), 0)
        self.assertEqual(few.survey.released_count(), 0)
