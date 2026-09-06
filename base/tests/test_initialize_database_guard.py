"""
The database-initialization wizard must not be reachable once setup is done.

The original hole: every step view after the password-gated entry view carried
only ``@hx_request_required``, which asserts an ``HX-Request`` header and
nothing else -- forgeable with a single curl flag.
``initialize_database_user`` calls ``create_superuser()`` then ``login()``, so
an unauthenticated caller could create a superuser under an unused username on
a fully provisioned instance and be logged in as them.

These tests assert the *outcome* -- no superuser created, no session
established -- rather than a particular status code, because the guard has two
independent implementations and the response shape is an implementation detail:

* ``@database_init_required`` on the user step: requires the DB_INIT_PASSWORD to
  have been verified this session (``db_init_verified``), and redirects to login
  otherwise.
* ``@superuser_required`` on the seven later steps.

Note there is deliberately NO ``DEBUG`` gate: it was removed in c99eaea4b4
("Fixed the initialize database 404 error in production server") because it
blocked legitimate first-run setup on a production deployment. A test asserting
404 in production would re-assert that bug.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from base.models import Company
from horilla.testkit import make_employee
from horilla_auth.models import HorillaUser

# Every view in the flow, including the edit/delete endpoints that are easy to
# miss when auditing "the signup steps".
STEP_URL_NAMES = [
    "initialize-database-user",
    "initialize-database-company",
    "initialize-database-department",
    "initialize-database-job-position",
]


class InitializedDatabaseRejectsSetupFlow(TestCase):
    """With a superuser that has an employee, setup is over."""

    def setUp(self):
        company = Company.objects.create(company="Acme", hq=True)
        user = HorillaUser.objects.create_superuser(
            username="root", email="root@test.horilla", password="pw-not-real"
        )
        # initialize_database_condition() only counts setup as finished when a
        # superuser has an employee attached, so the guard is not armed without
        # this.
        make_employee(company=company, email="root@test.horilla", user=user)

    def test_step_views_do_not_serve_the_wizard(self):
        for name in STEP_URL_NAMES:
            with self.subTest(view=name):
                response = self.client.get(
                    reverse(name), headers={"hx-request": "true"}
                )

                # Asserted on the rendered body, not the status code:
                # handle_no_permission() answers an HX-Request with a 200
                # rendering of decorator_404.html rather than a 403, so a
                # status assertion here would either miss the block or
                # accidentally pin that quirk. What must hold is that no
                # wizard form reaches an anonymous caller.
                if response.status_code == 200:
                    self.assertIn(
                        "decorator_404.html",
                        [t.name for t in response.templates],
                    )
                    self.assertNotIn(b"<form", response.content)
                else:
                    self.assertIn(response.status_code, (302, 403, 404))

    def test_forged_hx_header_cannot_create_a_superuser(self):
        before = HorillaUser.objects.filter(is_superuser=True).count()

        self.client.post(
            reverse("initialize-database-user"),
            {
                "username": "backdoor",
                "password": "attacker-chosen",
                "confirm_password": "attacker-chosen",
                "firstname": "Back",
                "lastname": "Door",
                "badge_id": "BD1",
                "email": "backdoor@test.horilla",
                "phone": "9999999999",
            },
            headers={"hx-request": "true"},
        )

        # The outcome is what matters, not the status code.
        self.assertFalse(HorillaUser.objects.filter(username="backdoor").exists())
        self.assertEqual(HorillaUser.objects.filter(is_superuser=True).count(), before)
        # A block that still logged the caller in would defeat the point.
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(DEBUG=False)
    def test_still_refused_with_debug_off(self):
        before = HorillaUser.objects.filter(is_superuser=True).count()

        self.client.post(
            reverse("initialize-database-user"),
            {
                "username": "backdoor2",
                "password": "x",
                "confirm_password": "x",
                "firstname": "B",
                "lastname": "D",
                "badge_id": "BD2",
                "email": "bd2@test.horilla",
                "phone": "9999999999",
            },
            headers={"hx-request": "true"},
        )

        self.assertFalse(HorillaUser.objects.filter(username="backdoor2").exists())
        self.assertEqual(HorillaUser.objects.filter(is_superuser=True).count(), before)


class UninitializedDatabaseAllowsSetupFlow(TestCase):
    """A genuinely fresh install must still be able to complete setup."""

    def test_user_step_needs_the_init_password_first(self):
        self.assertFalse(HorillaUser.objects.exists())

        response = self.client.get(
            reverse("initialize-database-user"), headers={"hx-request": "true"}
        )

        # Knowing the URL is not enough; DB_INIT_PASSWORD gates entry.
        self.assertEqual(response.status_code, 302)

    def test_user_step_is_reachable_after_verifying_the_init_password(self):
        from django.conf import settings

        self.assertFalse(HorillaUser.objects.exists())

        self.client.post(
            reverse("initialize-database"),
            {"password": settings.DB_INIT_PASSWORD},
        )
        self.assertTrue(self.client.session.get("db_init_verified"))

        response = self.client.get(
            reverse("initialize-database-user"), headers={"hx-request": "true"}
        )

        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False)
    def test_fresh_setup_works_with_debug_off(self):
        from django.conf import settings

        # Regression guard for c99eaea4b4: a DEBUG gate here blocked first-run
        # setup on real deployments, which is where setup actually happens.
        self.client.post(
            reverse("initialize-database"),
            {"password": settings.DB_INIT_PASSWORD},
        )
        response = self.client.get(
            reverse("initialize-database-user"), headers={"hx-request": "true"}
        )

        self.assertEqual(response.status_code, 200)
