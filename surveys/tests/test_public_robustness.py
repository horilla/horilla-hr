"""The no-login page and the HR endpoints behind it must not fall over.

Each of these was a server error or a wrong result on the first version: a
number that PostgreSQL cannot store, odd tokens, two requests at once, a survey
that closes while someone answers, a throttle that trusted a spoofable header.
"""

import threading

from django.core.cache import cache
from django.db import connections
from django.test import (
    Client,
    TestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from django.urls import reverse

from surveys.models import (
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)
from surveys.public import TOKEN_PROBE_LIMIT
from surveys.tests.support import answer_url, build_survey, hr_client, submit

CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=CACHE)
class AnswerValueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="val", people=2)
        cls.number = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=3,
            type=SurveyQuestion.TYPE_NUMBER,
            question="How many?",
        )
        cls.tools = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=4,
            type=SurveyQuestion.TYPE_MULTIPLE,
            question="Tools?",
            options=["Chat", "Mail"],
        )
        cls.invitation = cls.built.invitations[0]

    def setUp(self):
        cache.clear()

    def post(self, data, autosave=False):
        url = answer_url(self.invitation) + ("?autosave=1" if autosave else "")
        return Client().post(url, data)

    def test_numbers_postgres_cannot_store_are_refused_not_a_server_error(self):
        field = f"q{self.number.pk}"
        for bad in (
            "nan",
            "NaN",
            "inf",
            "-inf",
            "Infinity",
            "1e999",
            "9" * 400,
            "1e16",
        ):
            for autosave in (False, True):
                with self.subTest(value=bad, autosave=autosave):
                    response = self.post(
                        {self.built.mood_name(): "3", field: bad}, autosave=autosave
                    )
                    self.assertEqual(response.status_code, 200)
                    if not autosave:
                        self.assertContains(response, "Enter a number")
                    self.assertFalse(
                        SurveyAnswer.objects.filter(question=self.number).exists()
                    )

    def test_ordinary_numbers_are_kept(self):
        field = f"q{self.number.pk}"
        for value, stored in (("12", 12), ("3,5", 3.5), ("-4", -4), ("0", 0)):
            with self.subTest(value=value):
                self.post({self.built.mood_name(): "3", field: value}, autosave=True)
                self.assertEqual(
                    SurveyAnswer.objects.get(question=self.number).value, stored
                )

    def test_text_that_the_database_cannot_store_is_refused(self):
        response = self.post(
            {self.built.mood_name(): "3", self.built.note_name(): "a\x00b"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SurveyAnswer.objects.filter(question=self.built.note).exists())

    def test_a_repeated_option_is_stored_once(self):
        self.post(
            {f"q{self.tools.pk}": ["Chat", "Chat", "Chat", "Mail"]}, autosave=True
        )
        self.assertEqual(
            SurveyAnswer.objects.get(question=self.tools).value, ["Chat", "Mail"]
        )


@override_settings(CACHES=CACHE)
class TokenAndThrottleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="tok", people=2)
        cls.invitation = cls.built.invitations[0]

    def setUp(self):
        cache.clear()

    def test_odd_tokens_are_a_plain_404(self):
        for path in (
            "/surveys/s/abc%00def/",
            "/surveys/s/" + "a" * 200 + "/",
            "/surveys/s/short/",
            "/surveys/s/" + "!" * 43 + "/",
        ):
            with self.subTest(path=path[:40]):
                self.assertEqual(Client().get(path).status_code, 404)

    def test_misses_are_throttled_but_a_valid_link_still_works(self):
        client = Client()
        for _ in range(TOKEN_PROBE_LIMIT):
            self.assertEqual(client.get(answer_url("x" * 43)).status_code, 404)
        self.assertEqual(client.get(answer_url("y" * 43)).status_code, 429)
        # an employee behind the same address is not locked out of their own link
        self.assertEqual(client.get(answer_url(self.invitation)).status_code, 200)

    def test_a_spoofed_forwarded_header_does_not_buy_more_guesses(self):
        client = Client()
        for number in range(TOKEN_PROBE_LIMIT):
            response = client.get(
                answer_url("x" * 43), HTTP_X_FORWARDED_FOR=f"203.0.113.{number}"
            )
            self.assertEqual(response.status_code, 404)
        response = client.get(
            answer_url("z" * 43), HTTP_X_FORWARDED_FOR="203.0.113.250"
        )
        self.assertEqual(response.status_code, 429)

    def test_a_victims_address_in_the_header_does_not_lock_them_out(self):
        attacker = Client()
        for _ in range(TOKEN_PROBE_LIMIT + 5):
            attacker.get(answer_url("x" * 43), HTTP_X_FORWARDED_FOR="198.51.100.7")
        victim = Client(REMOTE_ADDR="198.51.100.7")
        self.assertEqual(victim.get(answer_url(self.invitation)).status_code, 200)


@override_settings(CACHES=CACHE)
class ClosedAndSubmittedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="clo", people=2)
        cls.invitation = cls.built.invitations[0]

    def test_autosave_on_a_closed_survey_says_so_instead_of_saved(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            status=Survey.STATUS_CLOSED
        )
        response = Client().post(
            answer_url(self.invitation) + "?autosave=1",
            {self.built.note_name(): "late"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"saved": False, "reason": "closed"})
        self.assertFalse(SurveyAnswer.objects.exists())

    def test_autosave_after_submitting_says_so(self):
        submit(self.built, self.invitation)
        response = Client().post(
            answer_url(self.invitation) + "?autosave=1",
            {self.built.note_name(): "again"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"saved": False, "reason": "submitted"})

    def test_a_second_submit_is_a_polite_no_op(self):
        first = submit(self.built, self.invitation, note="first")
        second = submit(self.built, self.invitation, note="second")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "already been answered")
        self.assertEqual(SurveyResponse.objects.filter(is_draft=False).count(), 1)
        self.assertEqual(
            SurveyAnswer.objects.get(question=self.built.note).value, "first"
        )

    def test_the_form_cancels_an_older_autosave_when_a_newer_one_starts(self):
        page = Client().get(answer_url(self.invitation))
        self.assertContains(page, 'hx-sync="this:replace"')


@skipUnlessDBFeature("has_select_for_update")
class ParallelRequestTests(TransactionTestCase):
    """Two tabs, a double click, a flaky connection that repeats a request."""

    def setUp(self):
        cache.clear()
        self.built = build_survey(tag="par", people=3)
        self.invitation = self.built.invitations[0]

    def run_together(self, work, count=6):
        outcomes, barrier = [], threading.Barrier(count)

        def worker():
            try:
                barrier.wait(timeout=20)
                outcomes.append(work(Client()))
            except Exception as error:  # a 500 raises in the test client
                outcomes.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        return outcomes

    def test_parallel_first_autosaves_make_one_draft_and_no_errors(self):
        url = answer_url(self.invitation) + "?autosave=1"
        outcomes = self.run_together(
            lambda client: client.post(url, {self.built.note_name(): "hello"})
        )
        errors = [o for o in outcomes if isinstance(o, Exception)]
        self.assertEqual(errors, [])
        self.assertEqual({o.status_code for o in outcomes}, {200})
        self.assertEqual(
            SurveyResponse.objects.filter(survey=self.built.survey).count(), 1
        )

    def test_parallel_submits_count_once_on_an_anonymous_survey(self):
        url = answer_url(self.invitation)
        data = {self.built.mood_name(): "5", self.built.note_name(): "same"}
        outcomes = self.run_together(lambda client: client.post(url, data))
        errors = [o for o in outcomes if isinstance(o, Exception)]
        self.assertEqual(errors, [])
        self.assertEqual({o.status_code for o in outcomes}, {200})
        self.assertEqual(
            SurveyResponse.objects.filter(
                survey=self.built.survey, is_draft=False
            ).count(),
            1,
        )
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, SurveyInvitation.STATUS_SUBMITTED)

    def test_parallel_submits_on_a_named_survey_make_one_response(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(is_anonymous=False)
        url = answer_url(self.invitation)
        data = {self.built.mood_name(): "5", self.built.note_name(): "same"}
        outcomes = self.run_together(lambda client: client.post(url, data))
        self.assertEqual([o for o in outcomes if isinstance(o, Exception)], [])
        self.assertEqual(
            SurveyResponse.objects.filter(survey=self.built.survey).count(), 1
        )


class ReorderAndFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="reo", people=1)

    def reorder(self, payload):
        return hr_client(self.built).post(
            reverse("survey-reorder", args=[self.built.survey.pk]), {"order": payload}
        )

    def sequence(self):
        return list(
            self.built.survey.questions.order_by("sequence", "id").values_list(
                "pk", flat=True
            )
        )

    def test_hostile_order_payloads_are_a_400_and_change_nothing(self):
        before = self.sequence()
        payloads = {
            "deeply nested": "[" * 30000 + "]" * 30000,
            "infinity": "[Infinity]",
            "huge exponent": "[1e999]",
            "booleans": "[true, false]",
            "not a list": '{"a": 1}',
            "too many": str(list(range(5000))),
            "too long": "[" + "1," * 20000 + "1]",
            "negative": "[-1, -2]",
            "not json": "banana",
        }
        for label, payload in payloads.items():
            with self.subTest(label):
                self.assertEqual(self.reorder(payload).status_code, 400)
        self.assertEqual(self.sequence(), before)

    def test_a_valid_order_is_applied(self):
        first, second = self.sequence()
        response = self.reorder(f"[{second}, {first}]")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sequence(), [second, first])

    def test_a_non_numeric_department_filter_is_ignored(self):
        named = build_survey(tag="reo_n", anonymous=False, people=1)
        for value in ("abc", "1;drop", "9" * 40, "-1", ""):
            with self.subTest(value=value):
                page = hr_client(named).get(
                    reverse("survey-results-tab", args=[named.survey.pk]),
                    {"department": value},
                )
                self.assertEqual(page.status_code, 200)
