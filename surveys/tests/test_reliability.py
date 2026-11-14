"""Lifecycle, what a survey does once people have answered, sending, who may do
what, and the company a survey belongs to.

These are the things that went wrong quietly in the first version: an empty
survey opened without a word, an invitation counted as sent that nobody could
read, a manager who could rewrite the questions, a link that kept working after
the person left.
"""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from employee.models import Employee
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from surveys import views
from surveys.forms import SurveyQuestionForm
from surveys.models import (
    Questionnaire,
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)
from surveys.tests.support import answer_url, build_survey, hr_client, submit

CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def mailer(*, fail_for=(), sent=1):
    """Patch the survey mailer: a working backend, recording what is sent.

    `fail_for` are addresses whose message raises; `sent` is what send() returns
    for the others (0 means the server took nothing).
    """
    backend = mock.Mock(
        configuration=True,
        dynamic_from_email_with_display_name="HR <hr@test.horilla>",
    )

    def send(message):
        if message.to[0] in fail_for:
            raise OSError("mailbox unavailable")
        if sent:
            mail.outbox.append(message)
        return sent

    return (
        mock.patch.object(views, "ConfiguredEmailBackend", return_value=backend),
        mock.patch("django.core.mail.EmailMultiAlternatives.send", send),
        backend,
    )


def messages_of(response):
    return [str(m) for m in response.context["messages"]] if response.context else []


@override_settings(CACHES=CACHE)
class OpeningTests(TestCase):
    """The rules of opening a survey."""

    def setUp(self):
        cache.clear()

    def open(self, built):
        return hr_client(built).post(
            reverse("survey-open", args=[built.survey.pk]), follow=True
        )

    def flashes(self, response):
        return " | ".join(str(m) for m in response.context["messages"])

    def test_a_survey_with_nobody_to_send_to_is_not_opened(self):
        built = build_survey(
            tag="emp", people=0, status=Survey.STATUS_DRAFT, anonymous=False
        )
        built.survey.invitations.all().delete()
        # the audience is chosen employees, and none are chosen
        Survey.objects.filter(pk=built.survey.pk).update(
            audience=Survey.AUDIENCE_EMPLOYEES
        )
        response = self.open(built)
        built.survey.refresh_from_db()
        self.assertEqual(built.survey.status, Survey.STATUS_DRAFT)
        self.assertIn("No active employee matches", self.flashes(response))

    def test_a_closing_date_in_the_past_blocks_opening(self):
        built = build_survey(tag="past", status=Survey.STATUS_CLOSED)
        Survey.objects.filter(pk=built.survey.pk).update(
            closes_at=timezone.now() - timedelta(days=1)
        )
        response = self.open(built)
        built.survey.refresh_from_db()
        self.assertEqual(built.survey.status, Survey.STATUS_CLOSED)
        self.assertIn("closing date has passed", self.flashes(response))

    def test_reopening_works_once_the_closing_date_is_moved(self):
        built = build_survey(tag="move", status=Survey.STATUS_CLOSED)
        Survey.objects.filter(pk=built.survey.pk).update(
            closes_at=timezone.now() + timedelta(days=3)
        )
        self.open(built)
        built.survey.refresh_from_db()
        self.assertEqual(built.survey.status, Survey.STATUS_OPEN)

    def test_a_survey_that_is_already_open_invites_only_the_new_people(self):
        built = build_survey(tag="late", people=2)
        before = built.survey.invitations.count()
        make_employee(company=built.company, email="late@late.horilla")
        with mailer()[0], mailer()[1]:
            response = self.open(built)
        self.assertEqual(built.survey.invitations.count(), before + 1)
        self.assertIn("new people", self.flashes(response))

    def test_nobody_new_is_said_plainly(self):
        built = build_survey(tag="none", people=2)
        response = self.open(built)
        self.assertIn("invited already", self.flashes(response))


@override_settings(CACHES=CACHE)
class AvailabilityTests(TestCase):
    """What the person behind the link is told."""

    def setUp(self):
        cache.clear()
        self.built = build_survey(tag="av", people=2)
        self.invitation = self.built.invitations[0]

    def page(self):
        return Client().get(answer_url(self.invitation))

    def test_not_open_yet_says_when_it_opens(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            opens_at=timezone.now() + timedelta(days=2)
        )
        response = self.page()
        self.assertContains(response, "This survey opens on")
        self.assertNotContains(response, 'name="q')

    def test_past_its_end_says_it_closed_on_a_date(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            closes_at=timezone.now() - timedelta(hours=1)
        )
        self.assertContains(self.page(), "This survey closed on")

    def test_closed_by_hand_says_closed(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            status=Survey.STATUS_CLOSED
        )
        self.assertContains(self.page(), "This survey has closed.")

    def test_autosave_past_the_end_is_refused(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            closes_at=timezone.now() - timedelta(hours=1)
        )
        response = Client().post(
            answer_url(self.invitation) + "?autosave=1", {self.built.note_name(): "x"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(SurveyAnswer.objects.exists())

    def test_the_sweep_closes_a_survey_past_its_end_and_drops_its_drafts(self):
        Client().post(
            answer_url(self.invitation) + "?autosave=1", {self.built.note_name(): "x"}
        )
        self.assertTrue(SurveyResponse.objects.filter(is_draft=True).exists())
        Survey.objects.filter(pk=self.built.survey.pk).update(
            closes_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(Survey.close_ended(), 1)
        self.built.survey.refresh_from_db()
        self.assertEqual(self.built.survey.status, Survey.STATUS_CLOSED)
        self.assertFalse(SurveyResponse.objects.filter(is_draft=True).exists())

    def test_the_lists_show_a_survey_past_its_end_as_closed(self):
        Survey.objects.filter(pk=self.built.survey.pk).update(
            closes_at=timezone.now() - timedelta(hours=1)
        )
        survey = Survey.objects.get(pk=self.built.survey.pk)
        self.assertIn("Closed", survey.status_badge())  # before any sweep ran
        page = hr_client(self.built).get(
            reverse("surveys-list"), HTTP_HX_REQUEST="true"
        )
        self.assertContains(page, "Closed")
        survey.refresh_from_db()
        self.assertEqual(survey.status, Survey.STATUS_CLOSED)  # and now in the database

    def test_a_scheduled_survey_says_so_in_the_mail(self):
        built = build_survey(tag="sch", people=1, status=Survey.STATUS_DRAFT)
        built.survey.invitations.all().delete()
        Survey.objects.filter(pk=built.survey.pk).update(
            opens_at=timezone.now() + timedelta(days=2)
        )
        patches = mailer()
        with patches[0], patches[1]:
            hr_client(built).post(reverse("survey-open", args=[built.survey.pk]))
        self.assertTrue(mail.outbox)
        self.assertIn("The survey opens on", mail.outbox[0].body)


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class QuestionsWithAnswersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="qa", anonymous=False, people=3)
        cls.tool = SurveyQuestion.objects.create(
            survey=cls.built.survey,
            sequence=3,
            type=SurveyQuestion.TYPE_CHOICE,
            question="Tool?",
            options=["Chat", "Mail", "Phone"],
        )
        cls.client_ = Client()
        cls.first = cls.built.invitations[0]
        Client().post(
            answer_url(cls.first),
            {
                cls.built.mood_name(): "4",
                f"q{cls.tool.pk}": "Mail",
            },
        )

    def form(self, question, **data):
        question = SurveyQuestion.objects.get(pk=question.pk)  # as a request loads it
        base = {
            "question": question.question,
            "type": question.type,
            "options_text": "\n".join(question.options),
        }
        base.update(data)
        return SurveyQuestionForm(data=base, instance=question)

    def test_the_type_cannot_change_once_there_are_answers(self):
        form = self.form(self.tool, type=SurveyQuestion.TYPE_NUMBER)
        self.assertTrue(form.fields["type"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["type"], SurveyQuestion.TYPE_CHOICE)

    def test_an_answered_option_cannot_be_renamed_or_removed(self):
        for options in ("Chat\nPhone", "Chat\nEmail\nPhone"):
            with self.subTest(options=options):
                form = self.form(self.tool, options_text=options)
                self.assertFalse(form.is_valid())
                self.assertIn("options_text", form.errors)
                self.assertIn("Mail", " ".join(form.errors["options_text"]))

    def test_an_option_without_answers_can_still_go_and_a_new_one_can_come(self):
        form = self.form(self.tool, options_text="Mail\nPhone\nVideo")
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_question_without_answers_is_free(self):
        fresh = SurveyQuestion.objects.create(
            survey=self.built.survey,
            sequence=9,
            type=SurveyQuestion.TYPE_CHOICE,
            question="Free?",
            options=["a", "b"],
        )
        form = self.form(fresh, type=SurveyQuestion.TYPE_TEXT, options_text="")
        self.assertFalse(form.fields["type"].disabled)
        self.assertTrue(form.is_valid(), form.errors)

    def test_results_keep_answers_to_options_that_were_taken_out(self):
        SurveyQuestion.objects.filter(pk=self.tool.pk).update(options=["Chat", "Phone"])
        page = hr_client(self.built).get(
            reverse("survey-results-tab", args=[self.built.survey.pk])
        )
        self.assertEqual(page.status_code, 200)
        entry = [c for c in page.context["chart_data"] if c["id"] == self.tool.pk][0]
        self.assertIn("Other (removed options)", entry["labels"])
        self.assertEqual(
            entry["series"][entry["labels"].index("Other (removed options)")], 1
        )

    def test_results_survive_a_value_that_no_longer_reads_as_a_number(self):
        SurveyAnswer.objects.filter(question=self.built.mood).update(value="banana")
        page = hr_client(self.built).get(
            reverse("survey-results-tab", args=[self.built.survey.pk])
        )
        self.assertEqual(page.status_code, 200)

    def test_a_zero_average_is_shown(self):
        number = SurveyQuestion.objects.create(
            survey=self.built.survey,
            sequence=8,
            type=SurveyQuestion.TYPE_NUMBER,
            question="How many?",
        )
        response = SurveyResponse.objects.get(survey=self.built.survey)
        SurveyAnswer.objects.create(response=response, question=number, value=0)
        page = hr_client(self.built).get(
            reverse("survey-results-tab", args=[self.built.survey.pk])
        )
        self.assertContains(page, "Average")

    def test_deleting_a_survey_shows_what_goes_with_it(self):
        page = hr_client(self.built).get(
            reverse("generic-delete"),
            {"model": "surveys.Survey", "pk": self.built.survey.pk},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(
            page.context["related_objects_count"].get("Survey responses"), 1
        )


@override_settings(CACHES=CACHE)
class AutosaveFollowsTheFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.built = build_survey(tag="auto", people=2)
        self.invitation = self.built.invitations[0]
        self.url = answer_url(self.invitation) + "?autosave=1"

    def test_emptying_a_field_clears_the_saved_answer(self):
        Client().post(self.url, {self.built.note_name(): "hello"})
        self.assertEqual(
            SurveyAnswer.objects.get(question=self.built.note).value, "hello"
        )
        Client().post(self.url, {self.built.note_name(): ""})
        self.assertFalse(SurveyAnswer.objects.filter(question=self.built.note).exists())

    def test_unticking_the_last_choice_clears_it(self):
        tools = SurveyQuestion.objects.create(
            survey=self.built.survey,
            sequence=5,
            type=SurveyQuestion.TYPE_MULTIPLE,
            question="Tools?",
            options=["a", "b"],
        )
        Client().post(self.url, {f"q{tools.pk}": ["a"]})
        self.assertTrue(SurveyAnswer.objects.filter(question=tools).exists())
        Client().post(self.url, {self.built.note_name(): "x"})  # nothing ticked now
        self.assertFalse(SurveyAnswer.objects.filter(question=tools).exists())

    def test_a_required_question_may_be_emptied_in_a_draft(self):
        SurveyQuestion.objects.filter(pk=self.built.mood.pk).update(is_required=True)
        Client().post(self.url, {self.built.mood_name(): "3"})
        Client().post(self.url, {self.built.mood_name(): ""})
        self.assertFalse(SurveyAnswer.objects.filter(question=self.built.mood).exists())
        # and submitting still insists
        response = Client().post(answer_url(self.invitation), {})
        self.assertContains(response, "required")
        self.assertFalse(SurveyResponse.objects.filter(is_draft=False).exists())

    def test_the_page_saves_while_typing_and_ignores_enter(self):
        page = Client().get(answer_url(self.invitation))
        self.assertContains(page, "input delay:800ms")
        self.assertContains(page, 'e.key === "Enter"')


@override_settings(CACHES=CACHE)
class SendingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.built = build_survey(
            tag="snd", people=3, status=Survey.STATUS_DRAFT, anonymous=False
        )
        self.built.survey.invitations.all().delete()
        names = {
            e.employee_first_name: e
            for e in Employee.objects.filter(email__startswith="snd.")
        }
        self.people = [names[f"Person{i}"] for i in range(3)]

    def open(self, **mail_kwargs):
        mail.outbox.clear()
        first, second, backend = mailer(**mail_kwargs)
        with first, second:
            response = hr_client(self.built).post(
                reverse("survey-open", args=[self.built.survey.pk]), follow=True
            )
        return response, " | ".join(str(m) for m in response.context["messages"])

    def test_everyone_reached_is_counted_and_stamped(self):
        _response, text = self.open()
        self.assertIn("emailed", text)
        stamped = SurveyInvitation.objects.exclude(sent_at=None).count()
        self.assertEqual(stamped, SurveyInvitation.objects.count())
        self.assertEqual(len(mail.outbox), SurveyInvitation.objects.count())

    def test_a_failed_mail_is_named_and_not_called_sent(self):
        address = self.people[0].email
        # the notification still goes to someone with a login: only the mail failed
        _response, text = self.open(fail_for=(address,))
        self.assertIn("The e-mail did not go to", text)
        self.assertIn("Person0", text)
        self.assertIn("notified in Horilla only", text)

    def test_a_server_that_takes_nothing_is_a_failure_too(self):
        _response, text = self.open(sent=0)
        self.assertIn("The e-mail did not go to", text)

    def test_someone_nobody_can_reach_gets_no_stamp_and_is_named(self):
        ghost = self.people[1]
        Employee.objects.filter(pk=ghost.pk).update(email="", employee_user_id=None)
        _response, text = self.open()
        self.assertIn("no way to get their link", text)
        self.assertIn("Person1", text)
        invitation = SurveyInvitation.objects.get(employee=ghost)
        self.assertIsNone(invitation.sent_at)

    def test_the_sender_falls_back_to_the_user_when_there_is_no_employee_record(self):
        # Horilla's middleware turns such a user away before any view runs, so this
        # is only the guard that keeps a send from raising halfway
        class NoEmployee:
            @property
            def employee_get(self):
                raise Employee.DoesNotExist

        user = NoEmployee()
        self.assertIs(views._sender(mock.Mock(user=user)), user)

    def test_one_connection_is_used_for_the_whole_batch(self):
        first, second, backend = mailer()
        with first, second:
            hr_client(self.built).post(
                reverse("survey-open", args=[self.built.survey.pk])
            )
        backend.open.assert_called_once()
        backend.close.assert_called_once()

    def test_a_mail_server_that_cannot_be_reached_is_said_not_swallowed(self):
        first, second, backend = mailer()
        backend.open.side_effect = OSError("connection refused")
        with first, second:
            response = hr_client(self.built).post(
                reverse("survey-open", args=[self.built.survey.pk]), follow=True
            )
        text = " | ".join(str(m) for m in response.context["messages"])
        self.assertIn("could not be reached", text)
        self.assertEqual(mail.outbox, [])

    def test_a_reminder_skips_people_who_are_no_longer_active(self):
        self.open()
        gone = SurveyInvitation.objects.get(employee=self.people[2])
        Employee.objects.filter(pk=self.people[2].pk).update(is_active=False)
        first, second, _backend = mailer()
        mail.outbox.clear()
        with first, second:
            hr_client(self.built).post(
                reverse("survey-remind", args=[self.built.survey.pk])
            )
        recipients = {m.to[0] for m in mail.outbox}
        self.assertNotIn(self.people[2].email, recipients)
        gone.refresh_from_db()
        self.assertIsNone(gone.reminded_at)


@override_settings(CACHES=CACHE)
class PeopleWhoLeftTests(TestCase):
    def setUp(self):
        cache.clear()
        self.built = build_survey(tag="gone", people=2)
        self.invitation = self.built.invitations[0]

    def test_an_inactive_employee_cannot_open_the_link(self):
        Employee.objects.filter(pk=self.invitation.employee_id).update(is_active=False)
        self.assertEqual(Client().get(answer_url(self.invitation)).status_code, 404)

    def test_a_switched_off_login_cannot_open_the_link(self):
        user = self.invitation.employee.employee_user_id
        user.is_active = False
        user.save()
        self.assertEqual(Client().get(answer_url(self.invitation)).status_code, 404)

    def test_they_cannot_submit_or_autosave_either(self):
        Employee.objects.filter(pk=self.invitation.employee_id).update(is_active=False)
        post = Client().post(answer_url(self.invitation), {self.built.note_name(): "x"})
        self.assertEqual(post.status_code, 404)
        auto = Client().post(
            answer_url(self.invitation) + "?autosave=1", {self.built.note_name(): "x"}
        )
        self.assertEqual(auto.status_code, 409)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_a_working_link_is_not_affected(self):
        self.assertEqual(Client().get(answer_url(self.invitation)).status_code, 200)


@override_settings(CACHES=CACHE)
class CompanyTests(TestCase):
    def setUp(self):
        cache.clear()
        set_selected_company(None)

    def test_the_audience_is_the_surveys_company_whatever_company_is_selected(self):
        mine = build_survey(tag="co_a", people=2, status=Survey.STATUS_DRAFT)
        other = make_company("Other Co")
        stranger = make_employee(company=other, email="stranger@other.horilla")
        everyone = set(mine.survey.audience_employees().values_list("pk", flat=True))
        self.assertNotIn(stranger.pk, everyone)
        set_selected_company(str(other.pk))
        try:
            again = set(mine.survey.audience_employees().values_list("pk", flat=True))
        finally:
            set_selected_company(None)
        self.assertEqual(again, everyone)
        self.assertTrue(everyone)

    def test_a_logged_in_respondent_of_another_company_sees_the_questions(self):
        built = build_survey(tag="co_b", people=2)
        other = make_company("Respondent Co")
        user = make_user("co_b_visitor")
        make_employee(company=other, email="visitor@other.horilla", user=user)
        client = Client()
        client.force_login(user)
        session = client.session
        session["selected_company"] = str(other.pk)
        session.save()
        page = client.get(answer_url(built.invitations[0]))
        self.assertContains(page, built.mood_name())
        done = client.post(answer_url(built.invitations[0]), {built.mood_name(): "5"})
        self.assertContains(done, "answers are in")
        self.assertEqual(SurveyResponse.objects.filter(is_draft=False).count(), 1)


@override_settings(CACHES=CACHE, SURVEYS_MIN_RESPONSES=1)
class WhoMayDoWhatTests(TestCase):
    """Every URL of the module against HR, a survey's manager, a plain employee and
    somebody not logged in."""

    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="perm", anonymous=False, people=3)
        cls.survey = cls.built.survey
        cls.manager_user = make_user("perm_manager")
        cls.manager = make_employee(
            company=cls.built.company,
            email="manager@perm.horilla",
            user=cls.manager_user,
        )
        cls.plain_user = make_user("perm_plain")
        make_employee(
            company=cls.built.company, email="plain@perm.horilla", user=cls.plain_user
        )
        cls.survey.managers.add(cls.manager)
        submit(cls.built, cls.built.invitations[0])
        cls.invitation = cls.built.invitations[1]
        cls.question = cls.built.note

    def client_for(self, role):
        client = Client()
        if role == "hr":
            client.force_login(self.built.hr_user)
        elif role == "manager":
            client.force_login(self.manager_user)
        elif role == "plain":
            client.force_login(self.plain_user)
        return client

    def urls(self):
        pk = self.survey.pk
        ipk = self.invitation.pk
        # name, args, method, who may
        return [
            ("survey-detail", [pk], "get", {"hr", "manager"}),
            ("survey-questions-tab", [pk], "get", {"hr", "manager"}),
            ("survey-audience-tab", [pk], "get", {"hr", "manager"}),
            ("survey-results-tab", [pk], "get", {"hr", "manager"}),
            ("survey-export", [pk], "get", {"hr", "manager"}),
            ("survey-remind", [pk], "post", {"hr", "manager"}),
            ("survey-reorder", [pk], "post", {"hr"}),
            ("survey-open", [pk], "post", {"hr"}),
            ("survey-close", [pk], "post", {"hr"}),
            ("survey-question-delete", [self.question.pk], "post", {"hr"}),
            ("survey-invitation-link", [pk, ipk], "post", {"hr"}),
            ("survey-invitation-resend", [pk, ipk], "post", {"hr"}),
        ]

    def attempt(self, role, name, args, method):
        client = self.client_for(role)
        url = reverse(name, args=args)
        kwargs = {"HTTP_HX_REQUEST": "true"} if method == "get" else {}
        first, second, _backend = mailer()
        with first, second:
            return getattr(client, method)(url, **kwargs)

    def allowed(self, response):
        """A 200 (or a redirect that carries the action back to the page) is let in;
        the refusals are a 403 or a redirect with the permission message."""
        return response.status_code == 200 or (
            response.status_code in (302, 303) and "login" not in response.url
        )

    def test_the_matrix(self):
        for name, args, method, who in self.urls():
            for role in ("hr", "manager", "plain", "anonymous"):
                with self.subTest(url=name, role=role):
                    # a survey that is closed, to see whether "open" is let through
                    Survey.objects.filter(pk=self.survey.pk).update(
                        status=(
                            Survey.STATUS_CLOSED
                            if name == "survey-open"
                            else Survey.STATUS_OPEN
                        )
                    )
                    SurveyQuestion.objects.get_or_create(
                        pk=self.question.pk,
                        defaults=dict(
                            survey=self.survey,
                            type="text",
                            question="Note?",
                            sequence=2,
                        ),
                    )
                    before = (
                        Survey.objects.get(pk=self.survey.pk).status,
                        SurveyQuestion.objects.filter(survey=self.survey).count(),
                    )
                    response = self.attempt(role, name, args, method)
                    after = (
                        Survey.objects.get(pk=self.survey.pk).status,
                        SurveyQuestion.objects.filter(survey=self.survey).count(),
                    )
                    if role in who:
                        self.assertNotEqual(
                            response.status_code, 403, f"{role} was refused {name}"
                        )
                    else:
                        # whatever else happens, nothing was changed
                        self.assertEqual(before, after, f"{role} changed {name}")
                        if name == "survey-invitation-link":
                            self.assertIn(response.status_code, (302, 403))
                            self.assertNotIn(b"/surveys/s/", response.content)

    def test_a_manager_cannot_change_the_survey(self):
        client = self.client_for("manager")
        self.assertEqual(
            client.post(reverse("survey-close", args=[self.survey.pk])).status_code, 302
        )
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.status, Survey.STATUS_OPEN)
        response = client.post(
            reverse("survey-reorder", args=[self.survey.pk]), {"order": "[]"}
        )
        self.assertEqual(response.status_code, 403)
        edit = client.get(
            reverse("survey-question-add") + f"?survey={self.survey.pk}",
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(edit, 'name="question"')

    def test_a_manager_sees_remind_but_not_edit_close_or_the_links(self):
        page = self.client_for("manager").get(
            reverse("survey-detail", args=[self.survey.pk])
        )
        self.assertContains(page, reverse("survey-remind", args=[self.survey.pk]))
        self.assertNotContains(page, reverse("survey-close", args=[self.survey.pk]))
        self.assertNotContains(page, reverse("survey-open", args=[self.survey.pk]))
        self.assertNotContains(page, reverse("survey-edit", args=[self.survey.pk]))
        tab = self.client_for("manager").get(
            reverse("survey-questions-tab", args=[self.survey.pk])
        )
        self.assertNotContains(tab, "js-handle")
        self.assertNotContains(tab, reverse("survey-question-add"))
        audience = self.client_for("manager").get(
            reverse("survey-invitations", args=[self.survey.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertNotContains(audience, "survey-invitation-link")
        self.assertNotContains(audience, "/surveys/s/")

    def test_hr_sees_the_link_buttons_but_never_the_token_in_the_page(self):
        audience = self.client_for("hr").get(
            reverse("survey-invitations", args=[self.survey.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertContains(audience, "surveyCopyLink")
        self.assertNotContains(audience, self.invitation.token)

    def test_the_link_endpoint_gives_hr_the_link_and_refuses_the_answered(self):
        client = self.client_for("hr")
        response = client.post(
            reverse("survey-invitation-link", args=[self.survey.pk, self.invitation.pk])
        )
        self.assertEqual(
            response.json()["url"].endswith(f"/s/{self.invitation.token}/"), True
        )
        self.assertIn("no-store", response["Cache-Control"])
        answered = self.built.invitations[0]
        refused = client.post(
            reverse("survey-invitation-link", args=[self.survey.pk, answered.pk])
        )
        self.assertEqual(refused.status_code, 409)

    def test_an_anonymous_survey_gives_nobody_a_link_to_a_draft(self):
        anon = build_survey(tag="perm_a", anonymous=True, people=2)
        invitation = anon.invitations[0]
        # a person who started and has not submitted: a draft tied to the invitation
        Client().post(
            answer_url(invitation) + "?autosave=1", {anon.note_name(): "private draft"}
        )
        client = hr_client(anon)
        response = client.post(
            reverse("survey-invitation-link", args=[anon.survey.pk, invitation.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"status": "anonymous"})
        self.assertNotIn(invitation.token.encode(), response.content)
        audience = client.get(
            reverse("survey-invitations", args=[anon.survey.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertNotContains(audience, "surveyCopyLink")
        self.assertNotContains(audience, "survey-invitation-link")
        # mailing the link to the person is still there
        self.assertContains(
            audience,
            reverse("survey-invitation-resend", args=[anon.survey.pk, invitation.pk]),
        )

    def test_an_invitation_of_another_survey_is_a_404(self):
        other = build_survey(tag="perm2", people=1)
        client = hr_client(self.built)
        response = client.post(
            reverse(
                "survey-invitation-link",
                args=[self.survey.pk, other.invitations[0].pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_the_menu_is_for_hr_only(self):
        from surveys.sidebar import surveys_accessibility

        def request_for(user):
            return mock.Mock(user=user)

        self.assertTrue(
            surveys_accessibility(request_for(self.built.hr_user), None, None)
        )
        self.assertFalse(
            surveys_accessibility(request_for(self.manager_user), None, None)
        )
        self.assertFalse(
            surveys_accessibility(request_for(self.plain_user), None, None)
        )

    def test_naming_a_manager_tells_them_where_the_survey_is(self):
        from notifications.models import Notification

        newcomer_user = make_user("perm_new")
        newcomer = make_employee(
            company=self.built.company, email="new@perm.horilla", user=newcomer_user
        )
        form = {
            "title": self.survey.title,
            "audience": Survey.AUDIENCE_ALL,
            "managers": [str(self.manager.pk), str(newcomer.pk)],
        }
        self.client_for("hr").post(
            reverse("survey-edit", args=[self.survey.pk]), form, HTTP_HX_REQUEST="true"
        )
        got = Notification.objects.filter(recipient=newcomer_user)
        self.assertEqual(got.count(), 1)
        self.assertEqual(got[0].data["redirect"], self.survey.get_detail_url())
        # the one who was a manager already is not told again
        self.assertFalse(
            Notification.objects.filter(recipient=self.manager_user).exists()
        )


@override_settings(CACHES=CACHE)
class LibraryRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.built = build_survey(tag="lib", people=1, status=Survey.STATUS_DRAFT)
        cls.writer = make_user("lib_writer")
        make_employee(company=cls.built.company, email="w@lib.horilla", user=cls.writer)
        from django.contrib.auth.models import Permission

        cls.writer.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="surveys",
                codename__in=["add_questionnaire", "view_survey", "view_questionnaire"],
            )
        )
        cls.target = Questionnaire.objects.create(title="Old", questions=[])

    def post_save(self, user, replace):
        client = Client()
        client.force_login(user)
        return client.post(
            reverse("survey-save-to-library", args=[self.built.survey.pk]),
            {
                "title": "New title",
                "description": "",
                "is_anonymous": "on",
                "replace": replace,
            },
            HTTP_HX_REQUEST="true",
        )

    def test_replace_needs_the_change_permission(self):
        self.post_save(self.writer, str(self.target.pk))
        self.target.refresh_from_db()
        self.assertEqual(self.target.title, "Old")
        self.assertEqual(self.target.questions, [])

    def test_hr_with_every_permission_can_replace(self):
        self.post_save(self.built.hr_user, str(self.target.pk))
        self.target.refresh_from_db()
        self.assertEqual(self.target.title, "New title")
        self.assertTrue(self.target.questions)

    def test_saving_as_new_still_needs_only_the_add_permission(self):
        self.post_save(self.writer, "new")
        self.assertTrue(Questionnaire.objects.filter(title="New title").exists())

    def test_a_standard_code_exists_once(self):
        Questionnaire.objects.create(title="A", code="enps")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Questionnaire.objects.create(title="B", code="enps")
        # questionnaires HR made have no code and may repeat
        Questionnaire.objects.create(title="C")
        Questionnaire.objects.create(title="C")

    def test_loading_the_standard_ones_twice_adds_no_copies(self):
        from surveys.library import load_standard

        first = load_standard()
        second = load_standard()
        self.assertTrue(first)
        self.assertEqual(second, [])


@override_settings(CACHES=CACHE)
class NumbersAndDatesTests(TestCase):
    def test_the_lists_do_not_ask_the_database_more_for_more_surveys(self):
        built = build_survey(tag="n1", people=2)
        client = hr_client(built)

        def queries():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as ctx:
                for name in ("surveys-list", "surveys-card"):
                    client.get(reverse(name), HTTP_HX_REQUEST="true")
                client.get(reverse("surveys-dashboard-data"))
            return len(ctx)

        baseline = queries()
        for index in range(6):
            extra = Survey.objects.create(
                title=f"More {index}",
                status=Survey.STATUS_OPEN,
                company_id=built.company,
            )
            SurveyQuestion.objects.create(
                survey=extra, sequence=1, type="text", question="Q?"
            )
            extra.invite()
        self.assertLessEqual(queries(), baseline + 4)

    def test_the_dashboard_counts_a_late_evening_answer_on_its_local_day(self):
        built = build_survey(tag="n2", anonymous=False, people=1)
        zone = timezone.get_current_timezone()
        today = timezone.localdate()
        late = timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time()), zone
        ) + timedelta(hours=23, minutes=30)
        SurveyResponse._base_manager.create(
            survey=built.survey, is_draft=False, submitted_at=late
        )
        data = hr_client(built).get(reverse("surveys-dashboard-data")).json()
        by_day = {row["day"]: row["n"] for row in data["per_day"]}
        self.assertEqual(by_day[today.isoformat()], 1)
        self.assertEqual(len(data["per_day"]), 31)
