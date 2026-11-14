"""HR's side: creating, building, opening, reminding, results and export."""

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from surveys.models import (
    Survey,
    SurveyAnswer,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class HrSurveyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_selected_company(None)
        cls.company = make_company("HR Co")
        cls.hr_user = make_user("survey_hr", is_superuser=True)
        cls.hr = make_employee(
            company=cls.company, email="hr@hr.horilla", user=cls.hr_user
        )
        cls.alice = make_employee(
            company=cls.company, email="alice@hr.horilla", first_name="Alice"
        )
        cls.bob = make_employee(
            company=cls.company, email="bob@hr.horilla", first_name="Bob"
        )
        cls.plain_user = make_user("survey_plain")
        cls.plain = make_employee(
            company=cls.company, email="plain@hr.horilla", user=cls.plain_user
        )

    def setUp(self):
        self.client.force_login(self.hr_user)

    def make_survey(self, **kwargs):
        survey = Survey.objects.create(title="Pulse", company_id=self.company, **kwargs)
        SurveyQuestion.objects.create(
            survey=survey, sequence=1, type=SurveyQuestion.TYPE_RATING, question="Mood?"
        )
        SurveyQuestion.objects.create(
            survey=survey,
            sequence=2,
            type=SurveyQuestion.TYPE_CHOICE,
            question="Office?",
            options=["Yes", "No"],
        )
        return survey

    def test_the_pages_open_for_hr_and_not_for_others(self):
        survey = self.make_survey()
        for name, args in (
            ("surveys-dashboard", []),
            ("surveys-view", []),
            ("survey-detail", [survey.pk]),
        ):
            self.assertEqual(
                self.client.get(reverse(name, args=args)).status_code, 200, name
            )
        self.client.force_login(self.plain_user)
        page = self.client.get(reverse("survey-detail", args=[survey.pk]))
        # sent back to the home page with the "no permission" message, nothing shown
        self.assertRedirects(page, "/", fetch_redirect_response=False)
        self.assertNotContains(page, "Pulse", status_code=302)

    def test_each_page_lights_up_only_its_own_submenu(self):
        """The sidebar marks every submenu whose link the path starts with."""
        from surveys.sidebar import SUBMENUS

        survey = self.make_survey()
        dashboard, surveys, library = (s["redirect"] for s in SUBMENUS)
        pages = {
            reverse("surveys-dashboard"): dashboard,
            reverse("surveys-view"): surveys,
            survey.get_detail_url(): surveys,
            reverse("surveys-library"): library,
        }
        for path, submenu in pages.items():
            lit = [
                s["redirect"]
                for s in SUBMENUS
                if path.startswith(s["redirect"])
                or any(path.startswith(p) for p in s.get("match_prefixes", []))
            ]
            self.assertEqual(lit, [submenu], path)
        self.assertRedirects(
            self.client.get("/surveys/"), reverse("surveys-view"), status_code=302
        )

    def test_the_list_and_the_cards_with_their_actions(self):
        survey = self.make_survey()
        nav = self.client.get(reverse("surveys-nav"), HTTP_HX_REQUEST="true")
        self.assertContains(nav, reverse("surveys-list"))
        self.assertContains(nav, reverse("surveys-card"))
        for name in ("surveys-list", "surveys-card"):
            view = self.client.get(reverse(name), HTTP_HX_REQUEST="true")
            self.assertContains(view, "Pulse", msg_prefix=name)
            self.assertContains(view, survey.get_detail_url(), msg_prefix=name)
            # Edit and Delete need perms, so the actions are rendered with them
            self.assertContains(view, survey.get_update_url(), msg_prefix=name)
            self.assertContains(
                view, f"model=surveys.Survey&pk={survey.pk}", msg_prefix=name
            )

    def test_the_tabs_of_a_survey(self):
        survey = self.make_survey(status=Survey.STATUS_OPEN)
        survey.invite()
        page = self.client.get(survey.get_detail_url())
        self.assertContains(page, reverse("survey-tabs", args=[survey.pk]))
        tabs = self.client.get(
            reverse("survey-tabs", args=[survey.pk]), HTTP_HX_REQUEST="true"
        )
        for name in (
            "survey-questions-tab",
            "survey-audience-tab",
            "survey-results-tab",
        ):
            self.assertContains(tabs, reverse(name, args=[survey.pk]), msg_prefix=name)

        audience = self.client.get(reverse("survey-audience-tab", args=[survey.pk]))
        invitations_url = reverse("survey-invitations", args=[survey.pk])
        self.assertContains(audience, invitations_url)
        invitations = self.client.get(invitations_url, HTTP_HX_REQUEST="true")
        self.assertContains(invitations, "Alice")
        self.assertContains(invitations, "Invited")

        self.client.force_login(self.plain_user)
        for url in (reverse("survey-tabs", args=[survey.pk]), invitations_url):
            self.assertEqual(
                self.client.get(url, HTTP_HX_REQUEST="true").status_code, 403, url
            )

    def test_creating_a_survey_goes_to_its_page(self):
        response = self.client.post(
            reverse("survey-create"),
            {
                "title": "Onboarding feedback",
                "description": "",
                "is_anonymous": "on",
                "audience": "all",
            },
            HTTP_HX_REQUEST="true",
        )
        survey = Survey.objects.get(title="Onboarding feedback")
        self.assertContains(response, survey.get_detail_url())
        self.assertEqual(survey.company_id, self.company)
        self.assertEqual(survey.status, Survey.STATUS_DRAFT)

    def test_an_audience_rule_needs_its_choice(self):
        response = self.client.post(
            reverse("survey-create"),
            {"title": "x", "audience": "departments"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Choose at least one")
        self.assertFalse(Survey.objects.filter(title="x").exists())

    def test_the_form_shows_only_the_field_of_the_chosen_audience(self):
        form = self.client.get(reverse("survey-create"), HTTP_HX_REQUEST="true")
        self.assertContains(form, "showAudienceField")
        for field in ("departments", "job_positions", "employees"):
            self.assertContains(form, f'id="id_{field}_parent_div"')

    def test_a_hidden_audience_field_keeps_nothing(self):
        from base.models import Department

        department = Department.objects.create(department="Crewing")
        self.client.post(
            reverse("survey-create"),
            {
                "title": "Everyone",
                "audience": "all",
                "departments": [department.pk],
                "employees": [self.alice.pk],
            },
            HTTP_HX_REQUEST="true",
        )
        survey = Survey.objects.get(title="Everyone")
        self.assertFalse(survey.departments.exists())
        self.assertFalse(survey.employees.exists())

        self.client.post(
            reverse("survey-create"),
            {
                "title": "Crewing only",
                "audience": "departments",
                "departments": [department.pk],
                "employees": [self.alice.pk],
            },
            HTTP_HX_REQUEST="true",
        )
        survey = Survey.objects.get(title="Crewing only")
        self.assertEqual(list(survey.departments.all()), [department])
        self.assertFalse(survey.employees.exists())

    def test_adding_and_ordering_questions(self):
        survey = Survey.objects.create(title="Pulse", company_id=self.company)
        self.client.post(
            reverse("survey-question-add") + f"?survey={survey.pk}",
            {
                "question": "Colour?",
                "type": "choice",
                "options_text": "Red\nBlue\n\n",
                "is_required": "on",
            },
            HTTP_HX_REQUEST="true",
        )
        self.client.post(
            reverse("survey-question-add") + f"?survey={survey.pk}",
            {"question": "Why?", "type": "textarea"},
            HTTP_HX_REQUEST="true",
        )
        colour, why = survey.questions.order_by("sequence")
        self.assertEqual(
            (colour.options, colour.is_required, why.sequence),
            (["Red", "Blue"], True, 2),
        )

        bad = self.client.post(
            reverse("survey-question-add") + f"?survey={survey.pk}",
            {"question": "One?", "type": "choice", "options_text": "Only"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(bad, "needs at least two options")

        self.client.post(
            reverse("survey-reorder", args=[survey.pk]),
            {"order": f"[{why.pk}, {colour.pk}]"},
        )
        self.assertEqual(
            list(survey.questions.values_list("question", flat=True)),
            ["Why?", "Colour?"],
        )

    def test_the_question_buttons_fill_the_modal_not_replace_it(self):
        """htmx hands hx-swap down to the children: an outerHTML on the tab's
        wrapper made "Add question" replace the modal's body, so the form lost
        its dialog and its errors went nowhere."""
        survey = Survey.objects.create(title="Pulse", company_id=self.company)
        SurveyQuestion.objects.create(survey=survey, type="text", question="Why?")
        html = self.client.get(
            reverse("survey-questions-tab", args=[survey.pk])
        ).content.decode()
        self.assertEqual(html.count("hx-swap"), 1)
        # the one swap is on the reload trigger, which has nothing inside
        self.assertRegex(html, r'<span hidden[^>]*hx-swap="outerHTML"></span>')
        self.assertIn('hx-target="#genericModalBody"', html)

    def test_a_choice_question_without_options_says_what_is_missing(self):
        survey = Survey.objects.create(title="Pulse", company_id=self.company)
        for type_ in ("choice", "multiple"):
            response = self.client.post(
                reverse("survey-question-add") + f"?survey={survey.pk}",
                {"question": "New", "type": type_, "options_text": ""},
                HTTP_HX_REQUEST="true",
            )
            # the form comes back with the error under the options
            self.assertContains(response, "needs at least two options")
            self.assertContains(response, 'id="id_options_text_error"')
        self.assertFalse(survey.questions.exists())
        # the other types need no options, and the form hides the field for them
        response = self.client.get(
            reverse("survey-question-add") + f"?survey={survey.pk}",
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "id_options_text_parent_div")
        self.assertContains(response, "One option per line, at least two")

    def test_opening_invites_the_audience_and_mails_the_link(self):
        survey = self.make_survey()
        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            from unittest import mock

            from surveys import views

            backend = mock.Mock(
                configuration=True,
                dynamic_from_email_with_display_name="HR <hr@hr.horilla>",
            )
            with mock.patch.object(
                views, "ConfiguredEmailBackend", return_value=backend
            ), mock.patch(
                "django.core.mail.EmailMultiAlternatives.send",
                lambda m: mail.outbox.append(m) or 1,
            ):
                self.client.post(reverse("survey-open", args=[survey.pk]))
        survey.refresh_from_db()
        self.assertEqual(survey.status, Survey.STATUS_OPEN)
        self.assertEqual(survey.invitations.count(), 4)  # hr, alice, bob, plain
        self.assertEqual(len(mail.outbox), 4)
        token = survey.invitations.get(employee=self.alice).token
        alice_mail = next(m for m in mail.outbox if m.to == ["alice@hr.horilla"])
        self.assertIn(f"/surveys/s/{token}/", alice_mail.body)
        self.assertEqual(survey.invitations.filter(sent_at__isnull=False).count(), 4)

    def test_a_survey_without_questions_does_not_open(self):
        survey = Survey.objects.create(title="Empty", company_id=self.company)
        self.client.post(reverse("survey-open", args=[survey.pk]))
        survey.refresh_from_db()
        self.assertEqual(survey.status, Survey.STATUS_DRAFT)
        self.assertEqual(survey.invitations.count(), 0)

    def test_reminders_go_only_to_the_pending(self):
        survey = self.make_survey(status=Survey.STATUS_OPEN)
        survey.invite()
        done = survey.invitations.get(employee=self.alice)
        SurveyInvitation.objects.filter(pk=done.pk).update(
            status=SurveyInvitation.STATUS_SUBMITTED
        )
        self.client.post(reverse("survey-remind", args=[survey.pk]))
        self.assertEqual(
            survey.invitations.filter(reminded_at__isnull=False).count(), 3
        )
        self.assertIsNone(survey.invitations.get(pk=done.pk).reminded_at)

    def test_results_count_and_export(self):
        survey = self.make_survey(status=Survey.STATUS_OPEN, is_anonymous=False)
        mood, office = survey.questions.order_by("sequence")
        for employee, rating, choice in (
            (self.alice, "4", "Yes"),
            (self.bob, "2", "No"),
            (self.plain, "4", "Yes"),
        ):
            invitation = SurveyInvitation.objects.create(
                survey=survey,
                employee=employee,
                token=SurveyInvitation.new_token(),
                status=SurveyInvitation.STATUS_SUBMITTED,
            )
            response = SurveyResponse.objects.create(
                survey=survey, invitation=invitation, is_draft=False
            )
            SurveyAnswer.objects.create(response=response, question=mood, value=rating)
            SurveyAnswer.objects.create(
                response=response, question=office, value=choice
            )
        SurveyResponse.objects.create(
            survey=survey, is_draft=True
        )  # a draft never counts

        page = self.client.get(reverse("survey-results-tab", args=[survey.pk]))
        self.assertContains(page, "<b>3.33</b>")
        self.assertContains(page, '"series": [2, 1]')

        export = self.client.get(reverse("survey-export", args=[survey.pk]))
        self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")
        lines = export.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn("Alice Employee", lines[1])
        self.assertIn("Yes", lines[1])

    def test_a_manager_sees_results_without_the_permission(self):
        survey = self.make_survey(status=Survey.STATUS_OPEN)
        survey.managers.add(self.plain)
        self.client.force_login(self.plain_user)
        self.assertEqual(
            self.client.get(
                reverse("survey-results-tab", args=[survey.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("survey-detail", args=[survey.pk])).status_code, 200
        )

    def test_dashboard_data(self):
        survey = self.make_survey(status=Survey.STATUS_OPEN)
        survey.invite()
        data = self.client.get(reverse("surveys-dashboard-data")).json()
        self.assertEqual(
            (data["kpi"]["open"], data["kpi"]["invited"], data["kpi"]["answered"]),
            (1, 4, 0),
        )
        self.assertEqual(data["recent"][0]["title"], "Pulse")
