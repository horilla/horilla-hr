"""Settings: encrypted secrets, Test connection, Register webhook (rules 9, 12, 13)."""

from django.test import override_settings
from django.urls import reverse

from horilla_firma import firma_api
from horilla_firma.models import FirmaSettings
from horilla_firma.tests.common import API_KEY, WEBHOOK_SECRET, FirmaTestCase
from horilla_firma.tests.fakes import FakeResponse

HTTPS_HOST = {"HTTP_HOST": "hr.example.org", "wsgi.url_scheme": "https"}
WEBHOOK_URL = "https://hr.example.org/firma/webhook/"


class SecretStorageTests(FirmaTestCase):
    def test_secrets_are_encrypted_at_rest(self):
        row = FirmaSettings.objects.get()
        self.assertNotIn(API_KEY, row.api_key_encrypted)
        self.assertNotIn(WEBHOOK_SECRET, row.webhook_secret_encrypted)
        self.assertEqual(row.api_key, API_KEY)
        self.assertEqual(row.webhook_secret, WEBHOOK_SECRET)

    def test_unreadable_secret_is_treated_as_missing(self):
        FirmaSettings.objects.update(api_key_encrypted="garbage")
        self.assertIsNone(FirmaSettings.ready())


@override_settings(ALLOWED_HOSTS=["hr.example.org", "testserver", "localhost"])
class SettingsViewTests(FirmaTestCase):
    url = None

    def setUp(self):
        super().setUp()
        self.url = reverse("firma-settings")

    def post(self, data, user=None):
        return self.login(user or self.admin).post(self.url, data, **HTTPS_HOST)

    def test_page_requires_the_settings_permission(self):
        response = self.login(self.sender).get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_page_shows_the_webhook_url_and_the_enable_webhooks_notice(self):
        response = self.login(self.admin).get(self.url, **HTTPS_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, WEBHOOK_URL)
        self.assertContains(response, "Enable Webhooks")
        # Saved secrets are never written back into the page.
        self.assertNotContains(response, API_KEY)
        self.assertNotContains(response, WEBHOOK_SECRET)

    def test_blank_secret_fields_keep_the_saved_values(self):
        response = self.post(
            {
                "action": "save",
                "is_enabled": "on",
                "api_key": "",
                "webhook_secret": "",
                "default_expiration_hours": "48",
            }
        )
        self.assertEqual(response.status_code, 302)
        row = FirmaSettings.objects.get()
        self.assertEqual(row.api_key, API_KEY)
        self.assertEqual(row.webhook_secret, WEBHOOK_SECRET)
        self.assertEqual(row.default_expiration_hours, 48)

    def test_new_key_replaces_the_old_one(self):
        self.post({"action": "save", "is_enabled": "on", "api_key": " new-key "})
        self.assertEqual(FirmaSettings.objects.get().api_key, "new-key")

    def test_enabling_without_a_key_is_refused(self):
        FirmaSettings.objects.all().delete()
        response = self.post({"action": "save", "is_enabled": "on", "api_key": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FirmaSettings.objects.filter(is_enabled=True).exists())

    def test_connection_test(self):
        self.session.queue(FakeResponse(200, {"results": [], "pagination": {}}))
        response = self.post({"action": "test"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.session.calls[0]["url"], firma_api.FIRMA_BASE_URL + "/templates"
        )

    def test_register_refuses_without_a_secret(self):
        self.config.webhook_secret = ""
        self.config.save()
        self.post({"action": "register"})
        self.assertEqual(self.session.calls, [])
        self.assertEqual(FirmaSettings.objects.get().webhook_id, "")

    def test_register_refuses_a_plain_http_address(self):
        self.login(self.admin).post(
            self.url, {"action": "register"}, HTTP_HOST="hr.example.org"
        )
        self.assertEqual(self.session.calls, [])

    def test_register_creates_the_webhook(self):
        self.session.queue(
            FakeResponse(200, {"results": [], "pagination": {"total_pages": 1}}),
            FakeResponse(201, {"id": "wh-1"}),
        )
        response = self.post({"action": "register"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.session.calls[0]["params"]["url"], WEBHOOK_URL)
        self.assertEqual(
            self.session.json_body(1),
            {"url": WEBHOOK_URL, "events": firma_api.WEBHOOK_EVENTS},
        )
        self.assertEqual(FirmaSettings.objects.get().webhook_id, "wh-1")
        follow = self.login(self.admin).get(self.url, **HTTPS_HOST)
        self.assertContains(follow, "Enable Webhooks")

    def test_register_reuses_an_enabled_complete_webhook(self):
        self.session.queue(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "wh-9",
                            "url": WEBHOOK_URL,
                            "enabled": True,
                            "events": firma_api.WEBHOOK_EVENTS,
                            "auto_disabled_at": None,
                        }
                    ],
                    "pagination": {"total_pages": 1},
                },
            )
        )
        self.post({"action": "register"})
        self.assertEqual(len(self.session.calls), 1)
        self.assertEqual(FirmaSettings.objects.get().webhook_id, "wh-9")

    def test_register_re_enables_an_auto_disabled_webhook_and_adds_events(self):
        self.session.queue(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "wh-7",
                            "url": WEBHOOK_URL,
                            "enabled": True,
                            "events": ["signing_request.completed"],
                            "auto_disabled_at": "2026-11-01T00:00:00Z",
                        }
                    ],
                    "pagination": {"total_pages": 1},
                },
            ),
            FakeResponse(200, {"id": "wh-7"}),
        )
        self.post({"action": "register"})
        put = self.session.calls[1]
        self.assertEqual(put["method"], "PUT")
        self.assertTrue(put["url"].endswith("/webhooks/wh-7"))
        body = self.session.json_body(1)
        self.assertTrue(body["enabled"])
        self.assertEqual(sorted(body["events"]), sorted(firma_api.WEBHOOK_EVENTS))

    def test_register_ignores_webhooks_for_other_addresses(self):
        self.session.queue(
            FakeResponse(
                200,
                {
                    "results": [{"id": "wh-x", "url": "https://other.example/hook"}],
                    "pagination": {"total_pages": 1},
                },
            ),
            FakeResponse(201, {"id": "wh-new"}),
        )
        self.post({"action": "register"})
        self.assertEqual(FirmaSettings.objects.get().webhook_id, "wh-new")
