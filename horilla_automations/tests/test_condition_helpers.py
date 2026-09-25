"""Automation condition helper smoke tests."""

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from employee.models import Employee
from horilla.testkit import make_company, make_employee, make_user
from horilla_automations.methods.methods import (
    evaluate_condition,
    generate_choices,
    get_model_class,
    split_query_string,
)


class EvaluateConditionTests(SimpleTestCase):
    def test_equality(self):
        self.assertTrue(evaluate_condition(1, "==", 1))
        self.assertTrue(evaluate_condition(1, "!=", 2))

    def test_invalid_operator(self):
        with self.assertRaises(ValueError):
            evaluate_condition(1, ">>>", 2)


class AutomationHelperTests(SimpleTestCase):
    def test_get_model_class(self):
        self.assertIs(get_model_class("employee.models.Employee"), Employee)

    def test_split_query_string(self):
        parts = split_query_string("a=1&logic=b=2")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].get("a"), "1")


class ModelClassResolutionSecurityTests(SimpleTestCase):
    """
    GHSA-x567-v324-7mr2 (pre-auth RCE): get_model_class()/generate_choices()
    used to do ``__import__(module_name, fromlist=[class_name])`` on a
    string that, for generate_choices(), comes straight from a request's
    ``model`` query param (via get_to_field(), behind only @login_required).
    __import__ executes the target module's top-level code -- chained with
    an unauthenticated upload endpoint that writes files under MEDIA_ROOT
    with whatever extension the uploader chose (fixed separately in
    recruitment/views/surveys.py), this was a full RCE: point ``model`` at
    ``media.recruitment_attachment.<uploaded_file>`` and its code runs.

    Both functions now resolve only through Django's own model registry
    (apps.get_models()), so nothing that isn't a model Django already
    loaded at startup can ever be returned, regardless of what exists on
    disk.
    """

    def test_a_path_outside_the_model_registry_is_rejected(self):
        with self.assertRaises(LookupError):
            get_model_class("media.recruitment_attachment.pwn.Pwn")

    def test_generate_choices_rejects_the_same_way(self):
        with self.assertRaises(LookupError):
            generate_choices("media.recruitment_attachment.pwn.Pwn")

    def test_a_real_but_unrelated_stdlib_or_third_party_module_is_also_rejected(self):
        # Not just "doesn't exist" -- a real, importable module that simply
        # isn't a Django model must be refused too.
        with self.assertRaises(LookupError):
            get_model_class("os.path.Path")

    def test_legitimate_model_paths_still_resolve(self):
        from recruitment.models import Candidate

        self.assertIs(get_model_class("recruitment.models.Candidate"), Candidate)


class GetToFieldViewTests(TestCase):
    """The one place generate_choices() is reachable from a request."""

    def setUp(self):
        company = make_company("Automation Co")
        user = make_user("automation_user", password="secret123")
        make_employee(company=company, email="automation_user@test.horilla", user=user)
        self.client = Client()
        self.client.force_login(user)

    def test_a_non_model_path_is_refused_cleanly_not_a_500(self):
        response = self.client.get(
            reverse("get-to-mail-field"),
            {"model": "media.recruitment_attachment.pwn.Pwn"},
        )
        self.assertIn(response.status_code, (400, 404))

    def test_a_real_model_path_still_works(self):
        response = self.client.get(
            reverse("get-to-mail-field"), {"model": "recruitment.models.Candidate"}
        )
        self.assertEqual(response.status_code, 200)
