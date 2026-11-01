"""
Tests for the horilla_tour engine.

Covers the things that matter for a multi-tenant SaaS: company isolation,
audience + page targeting, auto-start suppression after completion, and
permission gating of the admin CRUD. The seed migration ships two global
tours (getting-started, dashboard-overview) which the API tests rely on.
"""

import json

from django.test import Client, TestCase
from django.urls import reverse

from base.models import Company
from employee.models import Employee
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_employee
from horilla.testkit import make_employee
from horilla_auth.models import HorillaUser
from horilla_tour.models import Tour, TourProgress, TourStep


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
        # A real employee belongs to a company. Without work-info, the
        # request is scoped to "all my companies" with no companies, and the
        # company manager then hides every tour, global ones included.
        make_employee(
            company=make_company("Tour Co", "addr"),
            email="emp@t.com",
            first_name="Emp",
            last_name="User",
            user=self.employee,
        )
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
        # handle_no_permission() sends a plain navigation back to the referer
        # (here "/"). Asserting the exact redirect, not just "not 200", so a
        # 404 or 500 from a broken view no longer counts as a denial.
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/")


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


class TourModuleSeedTests(TestCase):
    """Verify migration 0004 seeded all 12 module tours correctly."""

    def test_all_slugs_present_and_published(self):
        for slug in MODULE_TOUR_SLUGS:
            with self.subTest(slug=slug):
                tour = Tour.objects.filter(slug=slug).first()
                self.assertIsNotNone(tour, f"Tour '{slug}' not found in DB")
                self.assertTrue(tour.is_published, f"Tour '{slug}' is not published")

    def test_page_match_values_are_correct(self):
        for slug, expected_page in MODULE_PAGE_MATCHES.items():
            with self.subTest(slug=slug):
                tour = Tour.objects.get(slug=slug)
                self.assertEqual(
                    tour.page_match,
                    expected_page,
                    f"Tour '{slug}': expected page_match '{expected_page}', got '{tour.page_match}'",
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
                tour = Tour.objects.get(slug=slug)
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
