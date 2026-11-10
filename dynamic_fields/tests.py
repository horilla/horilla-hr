import importlib

from django.test import SimpleTestCase


class TestDiscoveryTests(SimpleTestCase):
    """dynamic_fields is optional, so `manage.py test` finds it when it isn't installed."""

    def test_the_migrations_package_imports_without_the_app_installed(self):
        importlib.import_module("dynamic_fields.migrations")
