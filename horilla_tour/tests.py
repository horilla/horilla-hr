"""
Tests for the horilla_tour engine.

Covers the things that matter for a multi-tenant SaaS: company isolation,
audience + page targeting, auto-start suppression after completion, and
permission gating of the admin CRUD. The seed migration ships two global
tours (getting-started, dashboard-overview) which the API tests rely on.
"""

import io
import json
import re

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from base.models import Company
from employee.models import Employee
from horilla.horilla_middlewares import set_selected_company
from horilla_auth.models import HorillaUser
from horilla_tour.models import (
    Tour,
    TourProgress,
    TourStep,
    TourStepTranslation,
    TourTranslation,
)


def make_company(name, address):
    return Company.objects.create(
        company=name,
        address=address,
        country="US",
        state="ST",
        city="City",
        zip="00000",
    )


def attach_employee(user, first="Test", last="User"):
    """CompanyMiddleware requires every logged-in user to have an employee."""
    return Employee.objects.create(
        employee_user_id=user,
        employee_first_name=first,
        employee_last_name=last,
        email=user.email or f"{user.username}@t.com",
        phone="1234567890",
        badge_id=f"B{user.id}",
    )


def make_tour(slug, **kwargs):
    defaults = dict(
        title=slug.replace("-", " ").title(),
        page_match="dashboard",
        match_type="url_name",
        audience="all",
        trigger="auto_once",
        is_published=True,
    )
    defaults.update(kwargs)
    tour = Tour.objects.create(slug=slug, **defaults)
    TourStep.objects.create(
        tour=tour, sequence=1, title="Step 1", description="Hello", side="over"
    )
    return tour


class TourApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = HorillaUser.objects.create_superuser(
            username="tour_admin", email="admin@t.com", password="pass12345"
        )
        attach_employee(self.admin, "Admin", "User")
        self.employee = HorillaUser.objects.create_user(
            username="tour_emp", email="emp@t.com", password="pass12345"
        )
        attach_employee(self.employee, "Emp", "User")
        self.active_url = reverse("tour-active")
        self.progress_url = reverse("tour-progress")

    def _active(self, page="dashboard"):
        resp = self.client.get(self.active_url, {"page": page})
        self.assertEqual(resp.status_code, 200)
        return {t["slug"]: t for t in json.loads(resp.content)["tours"]}

    def test_api_requires_login(self):
        resp = self.client.get(self.active_url, {"page": "dashboard"})
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_seeded_getting_started_autostarts_for_admin(self):
        self.client.force_login(self.admin)
        tours = self._active("dashboard")
        self.assertIn("getting-started", tours)
        self.assertTrue(tours["getting-started"]["auto_start"])
        self.assertGreater(len(tours["getting-started"]["steps"]), 0)

    def test_page_matching_excludes_other_pages(self):
        self.client.force_login(self.admin)
        tours = self._active(page="employee-view")
        self.assertNotIn("getting-started", tours)  # only matches 'dashboard'

    def test_audience_filtering(self):
        # admins-only tour must not reach a non-admin user; an 'all' tour must.
        make_tour("admins-only", audience="admins")
        self.client.force_login(self.employee)
        tours = self._active("dashboard")
        self.assertNotIn("admins-only", tours)
        self.assertNotIn("getting-started", tours)  # seeded tour is admins-only
        self.assertIn("dashboard-highlights", tours)  # seeded 'all' tour

    def test_unpublished_tour_hidden(self):
        make_tour("draft-tour", is_published=False)
        self.client.force_login(self.admin)
        self.assertNotIn("draft-tour", self._active("dashboard"))

    def test_progress_completion_suppresses_autostart(self):
        self.client.force_login(self.admin)
        gs = Tour.objects.get(slug="getting-started")
        # Initially auto-starts
        self.assertTrue(self._active("dashboard")["getting-started"]["auto_start"])
        # Record completion
        resp = self.client.post(
            self.progress_url,
            {"tour_id": gs.id, "status": "completed", "last_step": 5},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["ok"])
        self.assertTrue(
            TourProgress.objects.filter(
                tour=gs, user=self.admin, status="completed"
            ).exists()
        )
        # No longer auto-starts, but still listed for replay
        again = self._active("dashboard")["getting-started"]
        self.assertFalse(again["auto_start"])
        self.assertEqual(again["status"], "completed")


class TourPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.regular = HorillaUser.objects.create_user(
            username="plain_user", email="p@t.com", password="pass12345"
        )
        attach_employee(self.regular, "Plain", "User")

    def test_settings_page_denied_for_non_privileged_user(self):
        self.client.force_login(self.regular)
        resp = self.client.get(reverse("tour-section"))
        # permission_required denies (redirect or 403) — never a 200 settings page
        self.assertNotEqual(resp.status_code, 200)


MODULE_TOUR_SLUGS = [
    "employee-directory",
    "ess-dashboard-tour",
    "recruitment-pipeline",
    "leave-management",
    "attendance-tracking",
    "payroll-overview",
    "asset-management",
    "performance-management",
    "onboarding-pipeline",
    "offboarding-process",
    "project-management",
    "helpdesk-overview",
]

MODULE_PAGE_MATCHES = {
    "employee-directory": "employee-view",
    "ess-dashboard-tour": "ess-dashboard",
    "recruitment-pipeline": "cbv-pipeline",
    "leave-management": "leave-dashboard",
    "attendance-tracking": "attendance-dashboard",
    "payroll-overview": "view-payroll-dashboard",
    "asset-management": "asset-dashboard",
    "performance-management": "dashboard-view",
    "onboarding-pipeline": "onboarding-dashboard",
    "offboarding-process": "offboarding-dashboard",
    "project-management": "project-dashboard-view",
    "helpdesk-overview": "helpdesk-dashboard",
}

VALID_AUDIENCES = {"all", "admins", "managers", "employees"}


class TourModuleSeedTests(TestCase):
    """Verify migration 0004 seeded all 12 module tours correctly."""

    def test_all_slugs_present_and_published(self):
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                self.assertIsNotNone(tour, f"Tour '{slug}' not found in DB")
                self.assertTrue(tour.is_published, f"Tour '{slug}' is not published")

    def test_each_tour_has_minimum_steps(self):
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                if tour is None:
                    continue
                step_count = TourStep.objects.filter(tour=tour).count()
                self.assertGreaterEqual(
                    step_count,
                    4,
                    f"Tour '{slug}' has only {step_count} steps (need ≥ 4)",
                )

    def test_page_match_values_are_correct(self):
        for slug, expected_page in MODULE_PAGE_MATCHES.items():
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                if tour is None:
                    continue
                self.assertEqual(
                    tour.page_match,
                    expected_page,
                    f"Tour '{slug}': expected page_match '{expected_page}', got '{tour.page_match}'",
                )

    def test_audience_values_are_valid(self):
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                if tour is None:
                    continue
                self.assertIn(
                    tour.audience,
                    VALID_AUDIENCES,
                    f"Tour '{slug}' has invalid audience '{tour.audience}'",
                )

    def test_trigger_is_auto_once_for_all_module_tours(self):
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                if tour is None:
                    continue
                self.assertEqual(
                    tour.trigger,
                    "auto_once",
                    f"Tour '{slug}' should be auto_once but is '{tour.trigger}'",
                )

    def test_no_duplicate_slugs(self):
        from django.db.models import Count

        duplicates = (
            Tour.objects.values("slug").annotate(cnt=Count("id")).filter(cnt__gt=1)
        )
        dup_slugs = [d["slug"] for d in duplicates]
        self.assertEqual(dup_slugs, [], f"Duplicate tour slugs found: {dup_slugs}")

    def test_global_tours_have_no_company(self):
        """Module tours are seeded globally (company_id=None) so every tenant sees them."""
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                if tour is None:
                    continue
                self.assertIsNone(
                    tour.company_id_id,
                    f"Tour '{slug}' should be global (company_id=None) but has company_id={tour.company_id_id}",
                )


class TourCompanyIsolationTests(TestCase):
    def setUp(self):
        # Clear any thread-local request left over from prior tests so
        # HorillaModel.save() doesn't stamp modified_by with a stale user id.
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def tearDown(self):
        set_selected_company(None)

    def test_manager_scopes_to_selected_company_plus_global(self):
        company_a = make_company("Alpha", "addr-a")
        company_b = make_company("Beta", "addr-b")
        make_tour("alpha-tour", company_id=company_a)
        make_tour("beta-tour", company_id=company_b)

        set_selected_company(company_a.id)
        slugs_a = set(Tour.objects.values_list("slug", flat=True))
        self.assertIn("alpha-tour", slugs_a)
        self.assertNotIn("beta-tour", slugs_a)
        self.assertIn("getting-started", slugs_a)  # global tour visible everywhere

        set_selected_company(company_b.id)
        slugs_b = set(Tour.objects.values_list("slug", flat=True))
        self.assertIn("beta-tour", slugs_b)
        self.assertNotIn("alpha-tour", slugs_b)
        self.assertIn("getting-started", slugs_b)


def _strip_translations(tour):
    """Simulate a pre-feature tour/step: no TourTranslation/TourStepTranslation rows."""
    TourTranslation.objects.filter(tour=tour).delete()
    TourStepTranslation.objects.filter(tour_step__tour=tour).delete()


class AuditTourTranslationsCommandTests(TestCase):
    """US1 — the audit command classifies every Tour/TourStep as ready/not ready."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def _run(self, *args):
        out = io.StringIO()
        call_command("audit_tour_translations", *args, stdout=out)
        return out.getvalue()

    def test_classifies_tours_without_translation_as_not_ready(self):
        tour = make_tour("no-translation-tour")
        _strip_translations(tour)

        out = self._run()

        self.assertIn("[NAO PRONTO]", out)
        self.assertIn("no-translation-tour", out)

    def test_summary_counts_match_totals(self):
        tour = make_tour("counted-tour")
        _strip_translations(tour)

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as tmp:
            path = tmp.name
        try:
            call_command("audit_tour_translations", "--output", path)
            with open(path, encoding="utf-8") as fh:
                result = json.load(fh)
        finally:
            os.remove(path)

        self.assertEqual(
            result["tours"]["ready"] + result["tours"]["not_ready"],
            result["tours"]["total"],
        )
        self.assertEqual(result["tours"]["total"], Tour.objects.count())
        self.assertEqual(
            result["tour_steps"]["ready"] + result["tour_steps"]["not_ready"],
            result["tour_steps"]["total"],
        )
        self.assertEqual(result["tour_steps"]["total"], TourStep.objects.count())

    def test_command_is_read_only_and_idempotent(self):
        tour = make_tour("readonly-check-tour")
        _strip_translations(tour)

        before = {
            "tours": Tour.objects.count(),
            "steps": TourStep.objects.count(),
            "tour_translations": TourTranslation.objects.count(),
            "step_translations": TourStepTranslation.objects.count(),
            "progress": TourProgress.objects.count(),
        }

        first_run = self._run()
        second_run = self._run()

        after = {
            "tours": Tour.objects.count(),
            "steps": TourStep.objects.count(),
            "tour_translations": TourTranslation.objects.count(),
            "step_translations": TourStepTranslation.objects.count(),
            "progress": TourProgress.objects.count(),
        }

        self.assertEqual(before, after)
        self.assertEqual(first_run, second_run)


class BackfillTourTranslationMigrationTests(TestCase):
    """US2 — the data migration mirrors existing Tour/TourStep text into English translations."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def _run_backfill(self):
        import importlib

        return importlib.import_module(
            "horilla_tour.migrations.0089_backfill_english_tour_translations"
        )

    def test_backfill_mirrors_existing_text_including_blank_description(self):
        tour = make_tour("legacy-tour", description="")
        step = tour.steps.first()
        step.description = ""
        step.save()
        _strip_translations(tour)

        self.assertFalse(TourTranslation.objects.filter(tour=tour).exists())

        from django.apps import apps as django_apps

        backfill = self._run_backfill()
        backfill.backfill(django_apps, None)

        translation = TourTranslation.objects.get(tour=tour, language="en")
        self.assertEqual(translation.title, tour.title)
        self.assertEqual(translation.description, "")

        step_translation = TourStepTranslation.objects.get(
            tour_step=step, language="en"
        )
        self.assertEqual(step_translation.title, step.title)
        self.assertEqual(step_translation.description, "")

    def test_backfill_does_not_touch_tour_progress(self):
        tour = make_tour("progress-safe-tour")
        _strip_translations(tour)
        admin = HorillaUser.objects.create_superuser(
            username="progress_admin", email="pa@t.com", password="pass12345"
        )
        attach_employee(admin, "Progress", "Admin")
        progress = TourProgress.objects.create(
            tour=tour, user=admin, status="in_progress", last_step=1
        )

        before = list(
            TourProgress.objects.values("id", "status", "last_step", "completed_at")
        )

        from django.apps import apps as django_apps

        backfill = self._run_backfill()
        backfill.backfill(django_apps, None)

        after = list(
            TourProgress.objects.values("id", "status", "last_step", "completed_at")
        )
        self.assertEqual(before, after)
        self.assertEqual(TourProgress.objects.count(), 1)
        self.assertEqual(TourProgress.objects.get(pk=progress.pk).status, "in_progress")


class NewTourTranslationSignalTests(TestCase):
    """US3 — newly created Tour/TourStep rows already have an English translation."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def test_new_tour_and_step_get_english_translation_automatically(self):
        tour = Tour.objects.create(
            slug="fresh-tour",
            title="Fresh Tour",
            description="Brand new",
            page_match="dashboard",
            match_type="url_name",
            audience="all",
            trigger="auto_once",
        )
        step = TourStep.objects.create(
            tour=tour, sequence=1, title="Fresh Step", description="Fresh step body"
        )

        self.assertTrue(tour.translations.filter(language="en").exists())
        translation = tour.translations.get(language="en")
        self.assertEqual(translation.title, tour.title)
        self.assertEqual(translation.description, tour.description)

        self.assertTrue(step.translations.filter(language="en").exists())
        step_translation = step.translations.get(language="en")
        self.assertEqual(step_translation.title, step.title)
        self.assertEqual(step_translation.description, step.description)

    def test_new_tour_is_classified_ready_without_backfill(self):
        Tour.objects.create(
            slug="fresh-audit-tour",
            title="Fresh Audit Tour",
            description="",
            page_match="dashboard",
            match_type="url_name",
            audience="all",
            trigger="auto_once",
        )

        out = io.StringIO()
        call_command("audit_tour_translations", stdout=out)
        output = out.getvalue()

        self.assertIn("[PRONTO]", output)
        self.assertIn("fresh-audit-tour", output)


def _run_english_backfill():
    import importlib

    return importlib.import_module(
        "horilla_tour.migrations.0089_backfill_english_tour_translations"
    )


def _run_ptbr_backfill():
    import importlib

    return importlib.import_module(
        "horilla_tour.migrations.0090_backfill_ptbr_tour_translations"
    )


class PtBrBackfillEnglishRegressionTests(TestCase):
    """US1 — running the pt-br backfill must not alter existing English translations."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def test_english_translation_untouched_after_ptbr_backfill(self):
        tour = make_tour("english-regression-tour")
        step = tour.steps.first()

        from django.apps import apps as django_apps

        english = _run_english_backfill()
        english.backfill(django_apps, None)

        before_tour = TourTranslation.objects.get(tour=tour, language="en")
        before_title, before_description = before_tour.title, before_tour.description
        before_step = TourStepTranslation.objects.get(tour_step=step, language="en")
        before_step_title = before_step.title
        before_step_description = before_step.description

        ptbr = _run_ptbr_backfill()
        ptbr.backfill(django_apps, None)

        after_tour = TourTranslation.objects.get(tour=tour, language="en")
        after_step = TourStepTranslation.objects.get(tour_step=step, language="en")

        self.assertEqual(after_tour.title, before_title)
        self.assertEqual(after_tour.description, before_description)
        self.assertEqual(after_step.title, before_step_title)
        self.assertEqual(after_step.description, before_step_description)


class PtBrBackfillEmptyFieldTests(TestCase):
    """US1 — a blank English field must never get invented pt-br content."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def test_blank_description_stays_blank_in_ptbr(self):
        tour = make_tour("ptbr-empty-field-tour", description="")
        step = tour.steps.first()
        step.description = ""
        step.save()

        from django.apps import apps as django_apps

        ptbr = _run_ptbr_backfill()
        original_translations = ptbr.TRANSLATIONS
        ptbr.TRANSLATIONS = {
            tour.slug: {
                "title": "Tour de Teste",
                "description": "",
                "steps": {
                    step.sequence: {"title": "Passo de Teste", "description": ""}
                },
            }
        }
        try:
            ptbr.backfill(django_apps, None)
        finally:
            ptbr.TRANSLATIONS = original_translations

        translation = TourTranslation.objects.get(tour=tour, language="pt-br")
        self.assertEqual(translation.description, "")
        step_translation = TourStepTranslation.objects.get(
            tour_step=step, language="pt-br"
        )
        self.assertEqual(step_translation.description, "")


class PtBrBackfillProgressPreservationTests(TestCase):
    """US1 — the pt-br backfill must never touch existing TourProgress rows."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def test_ptbr_backfill_does_not_touch_tour_progress(self):
        tour = make_tour("ptbr-progress-safe-tour")
        admin = HorillaUser.objects.create_superuser(
            username="ptbr_progress_admin", email="ppa@t.com", password="pass12345"
        )
        attach_employee(admin, "PtbrProgress", "Admin")
        progress = TourProgress.objects.create(
            tour=tour, user=admin, status="in_progress", last_step=1
        )

        before = list(
            TourProgress.objects.values("id", "status", "last_step", "completed_at")
        )

        from django.apps import apps as django_apps

        ptbr = _run_ptbr_backfill()
        ptbr.backfill(django_apps, None)

        after = list(
            TourProgress.objects.values("id", "status", "last_step", "completed_at")
        )
        self.assertEqual(before, after)
        self.assertEqual(TourProgress.objects.count(), 1)
        self.assertEqual(TourProgress.objects.get(pk=progress.pk).status, "in_progress")


class PtBrBackfillCoverageTests(TestCase):
    """US1 — every seeded Tour/TourStep with non-blank English text has a pt-br translation."""

    def test_every_seeded_tour_has_ptbr_translation(self):
        for tour in Tour.objects.all():
            if not tour.title and not tour.description:
                continue
            translation = tour.translations.filter(language="pt-br").first()
            self.assertIsNotNone(
                translation, f"Tour '{tour.slug}' has no pt-br translation"
            )
            if tour.title:
                self.assertTrue(
                    translation.title, f"Tour '{tour.slug}' has a blank pt-br title"
                )
            if tour.description:
                self.assertTrue(
                    translation.description,
                    f"Tour '{tour.slug}' has a blank pt-br description",
                )

    def test_every_seeded_tour_step_has_ptbr_translation(self):
        for step in TourStep.objects.all():
            if not step.title and not step.description:
                continue
            translation = step.translations.filter(language="pt-br").first()
            self.assertIsNotNone(
                translation,
                f"Step {step.sequence} of tour '{step.tour.slug}' has no pt-br translation",
            )
            if step.title:
                self.assertTrue(
                    translation.title,
                    f"Step {step.sequence} of '{step.tour.slug}' has a blank pt-br title",
                )
            if step.description:
                self.assertTrue(
                    translation.description,
                    f"Step {step.sequence} of '{step.tour.slug}' has a blank pt-br description",
                )


class PtBrTerminologyConsistencyTests(TestCase):
    """US2 — pt-br tour text must reuse the established HR glossary consistently."""

    # (English term, pt-br stem). The stem (not the full glossary word) is
    # checked against the translated text, since a natural pt-br translation
    # may conjugate the term into a verb ("integrar"/"integrando" rather than
    # the noun "Integração") depending on how the English sentence uses it.
    GLOSSARY = [
        ("Employee", "Funcionário", "funcionári"),
        ("Manager", "Administrador", "administrador"),
        ("Payslip", "Holerite", "holerite"),
        ("Recruitment", "Recrutamento", "recrut"),
        ("Onboarding", "Integração", "integr"),
        ("Attendance", "Presença", "presen"),
        ("Objective", "Objetivo", "objetiv"),
        ("Ticket", "Chamado", "chamad"),
    ]
    # Note: "Leave" is deliberately excluded — it also occurs as the verb
    # "leave it blank" (unrelated to the HR leave-request concept), which
    # would make this whole-word match report false positives.

    def _assert_term_translated(self, ptbr_text, ptbr_stem, ptbr_term, context):
        self.assertIn(
            ptbr_stem.lower(),
            ptbr_text.lower(),
            f"{context}: expected pt-br term '{ptbr_term}' in translated text: {ptbr_text!r}",
        )

    def test_hr_terms_are_translated_consistently_across_tours(self):
        for term, ptbr_term, ptbr_stem in self.GLOSSARY:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for tour in Tour.objects.all():
                translation = tour.translations.filter(language="pt-br").first()
                if not translation:
                    continue
                combined_en = f"{tour.title} {tour.description}"
                if pattern.search(combined_en):
                    combined_ptbr = f"{translation.title} {translation.description}"
                    self._assert_term_translated(
                        combined_ptbr, ptbr_stem, ptbr_term, f"tour '{tour.slug}'"
                    )
            for step in TourStep.objects.all():
                translation = step.translations.filter(language="pt-br").first()
                if not translation:
                    continue
                combined_en = f"{step.title} {step.description}"
                if pattern.search(combined_en):
                    combined_ptbr = f"{translation.title} {translation.description}"
                    self._assert_term_translated(
                        combined_ptbr,
                        ptbr_stem,
                        ptbr_term,
                        f"step {step.sequence} of tour '{step.tour.slug}'",
                    )


class AuditTourTranslationsLanguageTests(TestCase):
    """US3 — the audit command generalizes to any language via --language."""

    def setUp(self):
        from horilla.horilla_middlewares import _thread_locals

        _thread_locals.request = None

    def _run(self, *args):
        out = io.StringIO()
        call_command("audit_tour_translations", *args, stdout=out)
        return out.getvalue()

    def test_default_language_is_still_english(self):
        tour = make_tour("default-lang-tour")
        _strip_translations(tour)

        out = self._run()

        self.assertIn("[NAO PRONTO]", out)
        self.assertIn("default-lang-tour", out)
        self.assertIn("idioma: en", out)

    def test_pt_br_language_reports_coverage(self):
        tour = make_tour("ptbr-lang-tour")
        _strip_translations(tour)

        out = self._run("--language", "pt-br")

        self.assertIn("[NAO PRONTO]", out)
        self.assertIn("ptbr-lang-tour", out)
        self.assertIn("idioma: pt-br", out)

    def test_pt_br_language_includes_draft_and_company_specific_tours(self):
        company = make_company("Audit Co", "123 Street")
        draft_tour = Tour.objects.create(
            slug="draft-company-tour",
            title="Draft Company Tour",
            description="Draft",
            page_match="dashboard",
            match_type="url_name",
            audience="all",
            trigger="auto_once",
            is_published=False,
            company_id=company,
        )
        TourStep.objects.create(
            tour=draft_tour, sequence=1, title="Step", description="Body"
        )
        _strip_translations(draft_tour)

        out = self._run("--language", "pt-br")

        self.assertIn("draft-company-tour", out)

    def test_output_json_includes_language_key(self):
        tour = make_tour("json-lang-tour")
        _strip_translations(tour)

        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="r", suffix=".json", delete=False) as tmp:
            path = tmp.name
        try:
            call_command(
                "audit_tour_translations", "--language", "pt-br", "--output", path
            )
            with open(path, encoding="utf-8") as fh:
                result = json.load(fh)
        finally:
            os.remove(path)

        self.assertEqual(result["language"], "pt-br")
        self.assertIn("tours", result)
        self.assertIn("tour_steps", result)

    def test_blank_translation_field_is_reported_as_not_ready(self):
        """A translation row that exists but has a blank title/description
        (distinct from no row at all) must not be reported as ready, unless
        the original English text is itself blank (FR-009)."""
        tour = make_tour("blank-field-tour")
        TourTranslation.objects.create(
            tour=tour, language="pt-br", title="", description="Descrição"
        )

        out = self._run("--language", "pt-br")

        self.assertIn("[NAO PRONTO]", out)
        self.assertIn("blank-field-tour", out)
