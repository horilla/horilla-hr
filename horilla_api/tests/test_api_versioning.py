"""
The API must be reachable under an explicit version, and the old path must keep
working.

There was no versioning at all -- every endpoint lived at /api/<app>/ -- so any
breaking change silently broke integrators with no way to pin. /api/v1/ is now
the path to build against; /api/ stays as a deprecated alias because removing it
would be exactly the breaking change this is meant to prevent.
"""

from django.test import TestCase


class ApiVersioningTests(TestCase):
    def test_versioned_path_is_served(self):
        response = self.client.post("/api/v1/auth/login/", {})

        # 400 (bad credentials payload) proves the route resolved; a 404 would
        # mean the prefix is not mounted.
        self.assertNotEqual(response.status_code, 404)

    def test_unversioned_path_still_works(self):
        response = self.client.post("/api/auth/login/", {})

        self.assertNotEqual(response.status_code, 404)

    def test_both_paths_reach_the_same_endpoint(self):
        versioned = self.client.post("/api/v1/auth/login/", {})
        legacy = self.client.post("/api/auth/login/", {})

        self.assertEqual(versioned.status_code, legacy.status_code)


class ApiSchemaTests(TestCase):
    """
    drf-yasg is wired up but nothing ever asserted on the schema, so a breaking
    API change was undetectable in CI.
    """

    def test_schema_is_generated_and_declares_v1(self):
        # The drf-yasg route is `swagger<format>/`, so the trailing slash matters;
        # without it Django redirects (301) rather than serving.
        response = self.client.get("/api/v1/swagger.json/")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["info"]["version"], "v1")

    def test_schema_lists_paths(self):
        schema = self.client.get("/api/v1/swagger.json/").json()

        # A schema that generates but describes nothing is worse than none: it
        # looks like coverage.
        self.assertTrue(schema.get("paths"), "schema declares no paths")

    def test_auth_login_is_described(self):
        schema = self.client.get("/api/v1/swagger.json/").json()

        matches = [p for p in schema["paths"] if p.rstrip("/").endswith("auth/login")]
        self.assertTrue(matches, "auth/login missing from the published schema")
