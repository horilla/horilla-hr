"""dynamic_fields is optional, so this runs without the app installed."""

from django.test import SimpleTestCase

from dynamic_fields.methods import is_management_command


class TestIsManagementCommand(SimpleTestCase):
    def test_manage_py_and_django_admin_are(self):
        for program in (
            "manage.py",
            "/app/manage.py",
            "/opt/venv/bin/django-admin",
            "/opt/venv/lib/python3.12/site-packages/django/__main__.py",
        ):
            with self.subTest(program=program):
                self.assertTrue(is_management_command([program, "makemigrations"]))

    def test_web_servers_are_not(self):
        for program in (
            "/opt/venv/bin/gunicorn",
            "/opt/venv/lib/python3.12/site-packages/gunicorn/__main__.py",
            "/opt/venv/bin/uvicorn",
        ):
            with self.subTest(program=program):
                self.assertFalse(is_management_command([program]))

    def test_no_program_name_is_not(self):
        self.assertFalse(is_management_command([]))
