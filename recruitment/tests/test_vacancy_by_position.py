"""A recruitment's vacancy follows its job position's headcount."""

from datetime import date

from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from base.models import Department, JobPosition
from employee.models import EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_job_position, make_recruitment
from recruitment.forms import RecruitmentCreationForm


class Fixture(TestCase):
    def setUp(self):
        self.company = make_company("Vacancy Co")
        self.position = make_job_position(
            title="Clerk", department=Department.objects.create(department="Ops")
        )

    def recruit(self, day=1, **kwargs):
        """A recruitment on the position; (position, start date) is unique, so each gets its own day."""
        recruitment = make_recruitment(job_position=self.position, **kwargs)
        type(recruitment).objects.entire().filter(pk=recruitment.pk).update(
            start_date=date(2026, 11, day)
        )
        return type(recruitment).objects.entire().get(pk=recruitment.pk)

    def employ(self, number, active=True):
        employee = make_employee(
            company=self.company,
            email=f"v{number}@vac.horilla",
            first_name=f"V{number}",
        )
        EmployeeWorkInformation.objects.filter(employee_id=employee).update(
            job_position_id=self.position
        )
        if not active:
            employee.is_active = False
            employee.save()
        return employee


class AvailableVacancyTests(Fixture):
    def test_no_headcount_means_no_limit(self):
        self.assertIsNone(self.position.available_vacancies())

    def test_the_headcount_less_the_people_in_the_position(self):
        self.position.headcount = 5
        self.position.save()
        self.employ(1)
        self.employ(2)
        self.employ(3, active=False)  # left the company: their place is free
        self.assertEqual(self.position.filled_count(), 2)
        self.assertEqual(self.position.available_vacancies(), 3)

    def test_open_recruitments_use_up_places_and_a_closed_one_does_not(self):
        self.position.headcount = 5
        self.position.save()
        self.recruit(vacancy=2, title="Open", day=1)
        self.recruit(vacancy=4, closed=True, title="Closed", day=2)
        self.assertEqual(self.position.open_vacancy_count(), 2)
        self.assertEqual(self.position.available_vacancies(), 3)

    def test_editing_a_recruitment_does_not_count_its_own_vacancy_against_itself(self):
        self.position.headcount = 5
        self.position.save()
        mine = self.recruit(vacancy=4)
        self.assertEqual(self.position.available_vacancies(), 1)
        self.assertEqual(self.position.available_vacancies(exclude_recruitment=mine), 5)

    def test_it_never_goes_below_zero(self):
        self.position.headcount = 1
        self.position.save()
        self.employ(1)
        self.employ(2)
        self.assertEqual(self.position.available_vacancies(), 0)


class FormCheckTests(Fixture):
    def form(self, vacancy, positions=None, instance=None):
        data = QueryDict(mutable=True)
        data.update(
            {
                "title": "Opening",
                "description": "x",
                "vacancy": vacancy,
                "start_date": "2026-11-09",
            }
        )
        data.setlist(
            "open_positions", [str(p.pk) for p in (positions or [self.position])]
        )
        form = RecruitmentCreationForm(data=data, instance=instance)
        form.is_valid()
        return form

    def test_a_vacancy_above_what_is_free_is_refused_with_the_figures(self):
        self.position.headcount = 3
        self.position.save()
        self.employ(1)
        form = self.form(vacancy=3)  # only 2 free
        message = " ".join(form.errors.get("vacancy", []))
        self.assertIn("Vacancy (3) Is More Than The 2 Still Free For Clerk", message)

    def test_a_vacancy_within_what_is_free_passes_the_check(self):
        self.position.headcount = 3
        self.position.save()
        self.employ(1)
        self.assertNotIn("vacancy", self.form(vacancy=2).errors)

    def test_a_position_without_a_headcount_is_not_capped(self):
        self.assertNotIn("vacancy", self.form(vacancy=500).errors)

    def test_an_existing_recruitment_that_no_longer_fits_can_still_be_saved_unchanged(
        self,
    ):
        self.position.headcount = 3
        self.position.save()
        existing = self.recruit(vacancy=3)
        self.employ(1)
        self.employ(2)
        self.employ(3)  # the position is now over its headcount
        form = self.form(vacancy=3, instance=existing)
        self.assertNotIn("vacancy", form.errors)


class EndpointTests(Fixture):
    def setUp(self):
        super().setUp()
        self.user = make_user("vacadmin", is_superuser=True)
        make_employee(
            company=self.company, email="vacadmin@vac.horilla", user=self.user
        )
        self.client.force_login(self.user)
        self.url = reverse("recruitment-position-vacancy")

    def test_it_reports_what_is_free_and_how_it_was_worked_out(self):
        self.position.headcount = 4
        self.position.save()
        self.employ(1)
        self.recruit(vacancy=1)
        data = self.client.get(self.url, {"open_positions": [self.position.pk]}).json()
        self.assertEqual(data["available"], 2)
        self.assertEqual(
            data["positions"][0],
            {
                "id": self.position.pk,
                "name": "Clerk",
                "department": "Ops",
                "applied": 0,
                "selected": 0,
                "headcount": 4,
                "filled": 1,
                "open": 1,
                "available": 2,
            },
        )

    def test_it_counts_who_applied_and_who_was_selected_for_a_recruitment(self):
        from horilla.testkit.factories import make_candidate

        recruitment = self.recruit(vacancy=3)
        make_candidate(recruitment=recruitment, email="a1@vac.horilla", name="A1")
        make_candidate(
            recruitment=recruitment, email="a2@vac.horilla", name="A2", hired=True
        )
        data = self.client.get(
            self.url,
            {"open_positions": [self.position.pk], "recruitment": recruitment.pk},
        ).json()
        row = data["positions"][0]
        self.assertEqual((row["applied"], row["selected"]), (2, 1))
        # a new recruitment has nobody yet
        fresh = self.client.get(
            self.url, {"open_positions": [self.position.pk]}
        ).json()["positions"][0]
        self.assertEqual((fresh["applied"], fresh["selected"]), (0, 0))

    def test_it_says_nothing_is_limited_when_there_is_no_headcount(self):
        data = self.client.get(self.url, {"open_positions": [self.position.pk]}).json()
        self.assertIsNone(data["available"])

    def test_it_is_for_people_who_can_add_or_change_recruitments(self):
        self.client.logout()
        plain = make_user("plainvac")
        make_employee(company=self.company, email="plainvac@vac.horilla", user=plain)
        self.client.force_login(plain)
        self.assertEqual(
            self.client.get(
                self.url, {"open_positions": [self.position.pk]}
            ).status_code,
            403,
        )


class JobPositionFormTests(Fixture):
    def test_the_headcount_is_on_the_job_position_form(self):
        from base.forms import JobPositionForm

        self.assertIn("headcount", JobPositionForm().fields)


class RecruitmentFormPageTests(Fixture):
    def test_the_add_form_carries_the_vacancy_lookup(self):
        user = make_user("vacform", is_superuser=True)
        make_employee(company=self.company, email="vacform@vac.horilla", user=user)
        self.client.force_login(user)
        response = self.client.get(
            reverse("recruitment-create"), HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, reverse("recruitment-position-vacancy"))
        self.assertContains(response, "data-vacancy-text")


class MultiPositionWizardTests(Fixture):
    """The create form takes several job positions, with a vacancy line for each."""

    def setUp(self):
        super().setUp()
        self.second = make_job_position(
            title="Analyst", department=self.position.department_id
        )
        self.user = make_user("vacwiz", is_superuser=True)
        self.boss = make_employee(
            company=self.company, email="vacwiz@vac.horilla", user=self.user
        )
        self.client.force_login(self.user)

    def extended(self, lines, positions=None, validate_step=None, instance=None):
        import json

        from recruitment.cbv.recruitment_view import RecruitmentCreationFormExtended

        data = QueryDict(mutable=True)
        data.update(
            {
                "title": "Opening",
                "description": "x",
                "start_date": "2026-11-09",
                "vacancy": "1",
                "vacancy_lines": json.dumps(lines),
                "is_published": "on",
            }
        )
        data.setlist(
            "open_positions",
            [str(p.pk) for p in (positions or [self.position, self.second])],
        )
        data.setlist("recruitment_managers", [str(self.boss.pk)])
        if validate_step:
            data["validate_step"] = validate_step
        form = RecruitmentCreationFormExtended(data=data, instance=instance)
        form.is_valid()
        return form

    def test_the_lines_become_the_recruitments_vacancy_total(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 3},
            ]
        )
        self.assertNotIn("vacancy_lines", form.errors, form.errors)
        self.assertEqual(form.cleaned_data["vacancy"], 5)
        self.assertEqual(
            {p.job_position: n for p, n in form.vacancy_line_list.items()},
            {"Clerk": 2, "Analyst": 3},
        )

    def test_the_job_positions_are_the_lines_own_not_the_hidden_inputs(self):
        third = make_job_position(title="Other", department=self.position.department_id)
        # nothing was posted for open_positions apart from one the lines do not mention
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 4},
                {"position": third.pk, "vacancy": 9},
            ],
            positions=[self.second],
        )
        self.assertNotIn("vacancy_lines", form.errors, form.errors)
        self.assertEqual(
            {p.job_position: n for p, n in form.vacancy_line_list.items()},
            {"Clerk": 4, "Other": 9},
        )
        self.assertEqual(
            sorted(p.job_position for p in form.cleaned_data["open_positions"]),
            ["Clerk", "Other"],
        )

    def test_a_job_position_cannot_be_on_two_lines(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 1},
                {"position": self.position.pk, "vacancy": 2},
            ]
        )
        self.assertIn("One Line", " ".join(form.errors.get("vacancy_lines", [])))

    def test_a_line_must_name_a_job_position(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 1},
                {"position": "", "vacancy": 2},
            ]
        )
        self.assertIn("Every Line", " ".join(form.errors.get("vacancy_lines", [])))

    def test_no_lines_means_no_job_position(self):
        form = self.extended([])
        self.assertIn(
            "At Least One Job Position", " ".join(form.errors.get("vacancy_lines", []))
        )

    def test_each_line_is_held_to_its_own_positions_free_places(self):
        self.position.headcount = 2
        self.position.save()
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 3},
                {"position": self.second.pk, "vacancy": 50},
            ]
        )
        message = " ".join(form.errors.get("vacancy_lines", []))
        self.assertIn("Vacancy (3) For Clerk Is More Than The 2 Still Free", message)
        self.assertNotIn("Analyst", message)  # no headcount there, so no limit

    def test_a_total_of_zero_is_refused_on_the_vacancy_step(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 0},
                {"position": self.second.pk, "vacancy": 0},
            ]
        )
        self.assertIn("vacancy_lines", form.errors)
        self.assertNotIn(
            "vacancy", form.errors
        )  # the hidden total's error is shown where it can be seen

    def test_the_details_step_alone_does_not_need_the_vacancies(self):
        form = self.extended([], validate_step="1")
        self.assertNotIn("vacancy_lines", form.errors)
        self.assertNotIn("vacancy", form.errors)

    def test_the_vacancy_step_check_does_look_at_the_lines(self):
        self.position.headcount = 1
        self.position.save()
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 1},
            ],
            validate_step="2",
        )
        self.assertIn("vacancy_lines", form.errors)

    def test_saving_keeps_a_line_per_position_and_the_total(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 3},
            ]
        )
        recruitment = form.save()
        recruitment.set_vacancy_lines(form.vacancy_line_list)
        recruitment.refresh_from_db()
        self.assertEqual(recruitment.vacancy, 5)
        self.assertEqual(
            {
                l.job_position_id.job_position: l.vacancy
                for l in recruitment.vacancy_lines.all()
            },
            {"Clerk": 2, "Analyst": 3},
        )
        self.assertEqual(recruitment.open_positions.count(), 2)

    def test_open_vacancies_of_a_position_come_from_its_own_line(self):
        self.position.headcount = 10
        self.position.save()
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 5},
            ]
        )
        recruitment = form.save()
        recruitment.set_vacancy_lines(form.vacancy_line_list)
        self.assertEqual(
            self.position.open_vacancy_count(), 2
        )  # not the recruitment's total of 7
        self.assertEqual(self.position.available_vacancies(), 8)

    def test_an_old_recruitment_without_lines_still_counts_its_vacancy_for_each_position(
        self,
    ):
        self.position.headcount = 10
        self.position.save()
        self.recruit(vacancy=3)
        self.assertEqual(self.position.open_vacancy_count(), 3)

    def test_editing_an_old_recruitment_starts_its_lines_from_its_one_vacancy(self):
        import json

        old = self.recruit(vacancy=4)
        old.open_positions.add(self.second)
        form = self.extended([], instance=old)
        initial = json.loads(form.fields["vacancy_lines"].initial)
        self.assertEqual(
            sorted((row["vacancy"]) for row in initial if row["vacancy"] is not None),
            [4],
        )
        self.assertEqual([row["vacancy"] for row in initial].count(None), 1)

    def test_the_page_has_a_vacancy_step_between_the_other_two_and_no_job_position_on_the_first(
        self,
    ):
        import re

        response = self.client.get(
            reverse("recruitment-create"), HTTP_HX_REQUEST="true"
        )
        html = response.content.decode()
        self.assertIn('data-step-tab="vacancy"', html)
        self.assertIn('data-step-panel="vacancy"', html)
        self.assertLess(
            html.index('data-step-tab="details"'), html.index('data-step-tab="vacancy"')
        )
        self.assertLess(
            html.index('data-step-tab="vacancy"'),
            html.index('data-step-tab="pipeline"'),
        )
        # the job position is chosen on the vacancy step, line by line, so the first step carries no select for it
        self.assertIsNone(re.search(r'<select[^>]*name="open_positions"', html))
        self.assertNotIn('id="id_open_positions_parent_div"', html)
        self.assertIn("data-vac-add", html)
        self.assertIn('class="rec-vac-sn">', html)  # the serial number column
        self.assertIn("data-position-options", html)
        self.assertIn("Clerk", html)  # the positions the lines can pick from

    def test_the_managers_take_the_full_width_of_the_first_step(self):
        html = self.client.get(
            reverse("recruitment-create"), HTTP_HX_REQUEST="true"
        ).content.decode()
        import re

        block = re.search(
            r'<div\s+class="col-12 col-md-(\d+)"\s+id="id_recruitment_managers_parent_div"',
            html,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block.group(1), "12")

    def post(self, lines, **extra):
        import json

        data = {
            "title": "Wizard Opening",
            "description": "x",
            "start_date": "2026-11-09",
            "vacancy": "1",
            "vacancy_lines": json.dumps(lines),
            "open_positions": [self.position.pk, self.second.pk],
            "recruitment_managers": [self.boss.pk],
            "pipeline_mode": "default",
            "pipeline_stages": "",
            "is_published": "on",
        }
        data.update(extra)
        return self.client.post(
            reverse("recruitment-create"), data, HTTP_HX_REQUEST="true"
        )

    def test_next_on_the_vacancy_step_checks_the_lines_without_saving(self):
        self.position.headcount = 1
        self.position.save()
        bad = self.post(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 1},
            ],
            validate_step="2",
        )
        self.assertIn("Still Free", bad.content.decode())
        good = self.post(
            [
                {"position": self.position.pk, "vacancy": 1},
                {"position": self.second.pk, "vacancy": 1},
            ],
            validate_step="2",
        )
        self.assertEqual(good.content.decode().strip(), "<!--pipeline-step-ok-->")
        from recruitment.models import Recruitment

        self.assertFalse(
            Recruitment.objects.entire().filter(title="Wizard Opening").exists()
        )

    def test_saving_through_the_wizard_stores_the_lines(self):
        from recruitment.models import Recruitment

        self.post(
            [
                {"position": self.position.pk, "vacancy": 2},
                {"position": self.second.pk, "vacancy": 3},
            ]
        )
        recruitment = Recruitment.objects.entire().get(title="Wizard Opening")
        self.assertEqual(recruitment.vacancy, 5)
        self.assertEqual(
            {
                l.job_position_id.job_position: l.vacancy
                for l in recruitment.vacancy_lines.all()
            },
            {"Clerk": 2, "Analyst": 3},
        )
        self.assertEqual(recruitment.open_positions.count(), 2)

    def test_a_line_left_empty_stays_not_specified_and_adds_nothing(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": 3},
                {"position": self.second.pk, "vacancy": None},
            ]
        )
        self.assertNotIn("vacancy_lines", form.errors, form.errors)
        self.assertEqual(form.cleaned_data["vacancy"], 3)
        recruitment = form.save()
        recruitment.set_vacancy_lines(form.vacancy_line_list)
        lines = {
            l.job_position_id.job_position: l.vacancy
            for l in recruitment.vacancy_lines.all()
        }
        self.assertEqual(lines, {"Clerk": 3, "Analyst": None})
        self.assertEqual(recruitment.vacancy, 3)
        self.assertEqual(recruitment.unfilled_for(self.second), 0)

    def test_every_line_not_specified_is_a_total_of_zero_and_refused(self):
        form = self.extended(
            [
                {"position": self.position.pk, "vacancy": None},
                {"position": self.second.pk, "vacancy": ""},
            ]
        )
        self.assertIn("vacancy_lines", form.errors)

    def test_the_total_is_shown_above_the_lines(self):
        html = self.client.get(
            reverse("recruitment-create"), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertLess(html.index("data-vac-total"), html.index("data-vac-rows"))

    def test_duplicate_opens_the_same_steps_filled_in_from_the_original(self):
        import json
        import re

        old = self.recruit(vacancy=3, title="Original")
        old.set_vacancy_lines({self.position: 3, self.second: None})
        old.open_positions.set([self.position, self.second])
        response = self.client.get(
            reverse("recruitment-duplicate", kwargs={"pk": old.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-step-tab="vacancy"', html)
        self.assertIn("data-vac-add", html)
        self.assertIn("Original (copy)", html)
        # the vacancy lines of the original, as the vacancy step's starting point
        hidden = re.search(r'<input[^>]*name="vacancy_lines"[^>]*value="([^"]*)"', html)
        rows = json.loads(hidden.group(1).replace("&quot;", '"'))
        self.assertEqual(
            sorted((row["position"], row["vacancy"]) for row in rows),
            sorted([(self.position.pk, 3), (self.second.pk, None)]),
        )
        # no plain, single-step job position select
        self.assertIsNone(re.search(r'<select[^>]*name="open_positions"', html))

    def test_saving_a_duplicate_creates_a_new_recruitment_with_the_lines_and_leaves_the_original(
        self,
    ):
        import json

        from recruitment.models import Recruitment

        old = self.recruit(vacancy=3, title="Original")
        old.set_vacancy_lines({self.position: 3, self.second: 2})
        before = Recruitment.objects.entire().count()
        data = {
            "title": "Original (copy)",
            "description": "x",
            "start_date": "2026-11-09",
            "vacancy": "1",
            "vacancy_lines": json.dumps(
                [
                    {"position": self.position.pk, "vacancy": 3},
                    {"position": self.second.pk, "vacancy": 2},
                ]
            ),
            "open_positions": [self.position.pk, self.second.pk],
            "recruitment_managers": [self.boss.pk],
            "pipeline_mode": "default",
            "pipeline_stages": "",
            "is_published": "on",
        }
        response = self.client.post(
            reverse("recruitment-duplicate", kwargs={"pk": old.pk}),
            data,
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(Recruitment.objects.entire().count(), before + 1)
        copy = Recruitment.objects.entire().get(title="Original (copy)")
        self.assertNotEqual(copy.pk, old.pk)
        self.assertEqual(copy.vacancy, 5)
        self.assertEqual(
            {
                l.job_position_id.job_position: l.vacancy
                for l in copy.vacancy_lines.all()
            },
            {"Clerk": 3, "Analyst": 2},
        )
        old.refresh_from_db()
        self.assertEqual(old.title, "Original")

    def test_every_way_into_the_create_form_shows_all_three_steps(self):
        """The list's Create, the pipeline's Create and the empty-page buttons all open recruitment-create."""
        base = reverse("recruitment-create")
        for url in (base, base + "?pipeline=true"):
            with self.subTest(url=url):
                html = self.client.get(url, HTTP_HX_REQUEST="true").content.decode()
                for step in ("details", "vacancy", "pipeline"):
                    self.assertIn(f'data-step-tab="{step}"', html)

    def test_editing_from_the_list_and_from_the_pipeline_shows_all_three_steps_too(
        self,
    ):
        recruitment = self.recruit(vacancy=2)
        for name in ("recruitment-update", "recruitment-update-pipeline"):
            with self.subTest(view=name):
                html = self.client.get(
                    reverse(name, kwargs={"pk": recruitment.pk}), HTTP_HX_REQUEST="true"
                ).content.decode()
                for step in ("details", "vacancy", "pipeline"):
                    self.assertIn(f'data-step-tab="{step}"', html)

    def _edit_post(self, recruitment, **extra):
        import json

        stages = json.loads(
            self.extended([], instance=recruitment).fields["pipeline_stages"].initial
        )
        data = {
            "title": "Existing",
            "description": "x",
            "start_date": "2026-11-01",
            "vacancy": "3",
            "vacancy_lines": json.dumps([{"position": self.position.pk, "vacancy": 3}]),
            "open_positions": [self.position.pk],
            "recruitment_managers": [self.boss.pk],
            "pipeline_mode": "custom",
            "pipeline_stages": json.dumps(stages),
            "is_published": "on",
        }
        data.update(extra)
        return self.client.post(
            reverse("recruitment-update", kwargs={"pk": recruitment.pk}),
            data,
            HTTP_HX_REQUEST="true",
        )

    def test_going_from_the_vacancy_step_to_the_pipeline_does_not_check_the_pipeline(
        self,
    ):
        """The pipeline is checked when it is saved; checking it on the way in kept people from reaching it."""
        recruitment = self.recruit(vacancy=3, title="Existing")
        recruitment.set_vacancy_lines({self.position: 3})
        # a pipeline that is not valid on its own (no stage is of the required type)
        bad = self._edit_post(
            recruitment,
            validate_step="2",
            pipeline_stages='[{"name": "Only", "type": "interview"}]',
        )
        self.assertEqual(bad.content.decode().strip(), "<!--pipeline-step-ok-->")

    def test_a_stage_saved_with_the_old_hired_type_can_be_edited_and_saved(self):
        from recruitment.models import Stage

        recruitment = self.recruit(vacancy=3, title="Existing")
        recruitment.set_vacancy_lines({self.position: 3})
        # as seeded data has it: the Hired stage carries the type "hired", which the app now calls "shortlisted"
        from horilla.testkit.factories import make_stage

        made = make_stage(
            recruitment=recruitment, stage="Hired Here", stage_type="shortlisted"
        )
        Stage.objects.filter(pk=made.pk).update(stage_type="hired")
        self.assertTrue(
            Stage.objects.filter(
                recruitment_id=recruitment, stage_type="hired"
            ).exists()
        )
        form = self.extended([], instance=recruitment)
        import json

        types = {
            row["type"] for row in json.loads(form.fields["pipeline_stages"].initial)
        }
        self.assertNotIn("hired", types)  # offered as the type the app knows
        response = self._edit_post(recruitment)
        self.assertNotIn("Choose a valid stage type", response.content.decode())
        self.assertFalse(
            Stage.objects.filter(
                recruitment_id=recruitment, stage_type="hired"
            ).exists()
        )
        self.assertTrue(
            Stage.objects.filter(
                recruitment_id=recruitment, stage_type="shortlisted"
            ).exists()
        )


class VacancyProgressTests(Fixture):
    """The pipeline shows how many of a recruitment's places are filled, and the detail per job position."""

    def setUp(self):
        super().setUp()
        self.second = make_job_position(
            title="Analyst", department=self.position.department_id
        )

    def candidate(self, recruitment, number, position=None, hired=False):
        from recruitment.models import Candidate

        return Candidate.objects.create(
            name=f"C{number}",
            email=f"c{number}@prog.horilla",
            recruitment_id=recruitment,
            job_position_id=position or self.position,
            hired=hired,
        )

    def test_one_position_counts_every_candidate_against_it(self):
        recruitment = self.recruit(vacancy=3)
        recruitment.set_vacancy_lines({self.position: 3})
        self.candidate(recruitment, 1)
        self.candidate(recruitment, 2, hired=True)
        progress = recruitment.vacancy_progress()
        row = progress["rows"][0]
        self.assertEqual(
            (
                row["position"],
                row["vacancy"],
                row["applied"],
                row["selected"],
                row["remaining"],
            ),
            ("Clerk", 3, 2, 1, 2),
        )
        self.assertEqual(
            (
                progress["total"],
                progress["selected"],
                progress["remaining"],
                progress["percent"],
            ),
            (3, 1, 2, 33),
        )
        self.assertEqual(
            (progress["positions"], progress["positions_filled"], progress["state"]),
            (1, 0, "partial"),
        )

    def test_each_position_has_its_own_figures_and_can_be_filled(self):
        recruitment = self.recruit(vacancy=2)
        recruitment.open_positions.add(self.second)
        recruitment.set_vacancy_lines({self.position: 2, self.second: None})
        self.candidate(recruitment, 1, hired=True)
        self.candidate(recruitment, 2, hired=True)
        self.candidate(recruitment, 3, position=self.second)
        progress = recruitment.vacancy_progress()
        rows = {row["position"]: row for row in progress["rows"]}
        self.assertTrue(rows["Clerk"]["is_filled"])
        self.assertEqual(
            (
                rows["Analyst"]["vacancy"],
                rows["Analyst"]["applied"],
                rows["Analyst"]["remaining"],
            ),
            (None, 1, None),
        )
        self.assertEqual(
            (progress["positions"], progress["positions_filled"], progress["state"]),
            (2, 1, "full"),
        )

    def test_selecting_more_than_the_places_is_reported_as_over(self):
        """Each position reports how many were selected beyond its places, and the totals add them up."""
        recruitment = self.recruit(vacancy=1)
        recruitment.open_positions.add(self.second)
        recruitment.set_vacancy_lines({self.position: 1, self.second: 2})
        for number in (1, 2, 3):
            self.candidate(recruitment, number, hired=True)
        self.candidate(recruitment, 4, position=self.second, hired=True)
        progress = recruitment.vacancy_progress()
        rows = {row["position"]: row for row in progress["rows"]}
        self.assertEqual((rows["Clerk"]["over"], rows["Clerk"]["remaining"]), (2, 0))
        self.assertEqual(rows["Analyst"]["over"], 0)
        self.assertEqual(
            (progress["over"], progress["positions_over"], progress["state"]),
            (2, 1, "over"),
        )

    def test_the_indicator_can_be_loaded_again_on_its_own_with_current_figures(self):
        """After candidates are selected or moved the bar is fetched again and shows the new count."""
        user = make_user("refreshadmin", is_superuser=True)
        make_employee(
            company=self.company, email="refreshadmin@prog.horilla", user=user
        )
        self.client.force_login(user)
        recruitment = self.recruit(vacancy=2)
        recruitment.set_vacancy_lines({self.position: 2})
        url = reverse("recruitment-pipeline-vacancy", kwargs={"rec_id": recruitment.pk})
        self.assertIn(
            "0 / 2", self.client.get(url, HTTP_HX_REQUEST="true").content.decode()
        )
        self.candidate(recruitment, 1, hired=True)
        html = self.client.get(url, HTTP_HX_REQUEST="true").content.decode()
        self.assertIn("1 / 2", html)
        self.assertIn(f'data-refresh-url="{url}"', html)

    def test_the_indicator_closes_every_element_it_opens(self):
        """An unclosed element would swallow the nav's action buttons into the title."""
        from django.template.loader import render_to_string

        recruitment = self.recruit(vacancy=2)
        recruitment.set_vacancy_lines({self.position: 2})
        html = render_to_string(
            "cbv/pipeline/vacancy_progress.html",
            {"vacancy": recruitment.vacancy_progress()},
        )
        self.assertEqual(html.count("<div"), html.count("</div>"))

    def test_nothing_hired_yet_is_the_empty_state_and_no_vacancy_is_not_specified(self):
        recruitment = self.recruit(vacancy=4)
        recruitment.set_vacancy_lines({self.position: 4})
        self.assertEqual(recruitment.vacancy_progress()["state"], "empty")
        recruitment.set_vacancy_lines({self.position: None})
        self.assertEqual(recruitment.vacancy_progress()["state"], "none")

    def test_the_pipeline_tab_shows_the_indicator_and_the_popover(self):
        user = make_user("progadmin", is_superuser=True)
        make_employee(company=self.company, email="progadmin@prog.horilla", user=user)
        self.client.force_login(user)
        recruitment = self.recruit(vacancy=3)
        recruitment.set_vacancy_lines({self.position: 3})
        self.candidate(recruitment, 1, hired=True)
        response = self.client.get(
            reverse("recruitment-pipeline-tab-nav", kwargs={"rec_id": recruitment.pk}),
            HTTP_HX_REQUEST="true",
        )
        html = response.content.decode()
        self.assertIn('class="vp"', html)
        self.assertIn("1 / 3", html)
        self.assertIn("Vacancy Details", html)
        self.assertIn("Clerk", html)
        self.assertIn("Positions Filled", html)
        self.assertIn("0 / 1", html)
