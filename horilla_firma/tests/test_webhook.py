"""The webhook: verification, de-duplication, forward-only status (rules 6, 10)."""

import json
import time

from django.test import Client
from django.urls import reverse

from horilla_firma.models import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_SENT,
    FirmaSignatureRequest,
    FirmaWebhookEvent,
)
from horilla_firma.tests.common import WEBHOOK_SECRET, FirmaTestCase, event_body, sign


class WebhookTests(FirmaTestCase):
    def setUp(self):
        super().setUp()
        self.record = FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="Offer",
            source="template",
            recipient_name="Ada Lovelace",
            recipient_email="ada@example.org",
            status=STATUS_SENT,
            firma_id="sr-1",
            send_token="t1",
        )
        # CSRF is enforced, as in production: the endpoint must be exempt.
        self.web = Client(enforce_csrf_checks=True)
        self.url = reverse("firma-webhook")

    def deliver(self, body, header=None, old_header=None):
        headers = {}
        if header is not False:
            headers["HTTP_X_FIRMA_SIGNATURE"] = header or sign(body)
        if old_header:
            headers["HTTP_X_FIRMA_SIGNATURE_OLD"] = old_header
        return self.web.post(
            self.url, data=body, content_type="application/json", **headers
        )

    def test_completed_event_updates_the_request_without_downloading(self):
        body = event_body(
            "evt-1",
            "signing_request.completed",
            "sr-1",
            completed_at="2026-11-24T10:00:00Z",
        )
        response = self.deliver(body)
        self.assertEqual(response.status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, STATUS_COMPLETED)
        self.assertEqual(
            self.record.completed_at.isoformat(), "2026-11-24T10:00:00+00:00"
        )
        self.assertTrue(FirmaWebhookEvent.objects.filter(event_id="evt-1").exists())
        # The signed PDF is fetched by the scheduler, never inside the delivery.
        self.assertEqual(self.session.calls, [])
        self.assertFalse(self.record.signed_document)

    def test_recipient_signed_moves_to_in_progress(self):
        body = event_body("evt-2", "signing_request.recipient.signed", "sr-1")
        self.assertEqual(self.deliver(body).status_code, 200)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, STATUS_IN_PROGRESS)

    def test_status_never_moves_back(self):
        self.deliver(event_body("evt-3", "signing_request.completed", "sr-1"))
        for index, event in enumerate(
            [
                "signing_request.recipient.declined",
                "signing_request.cancelled",
                "signing_request.expired",
                "signing_request.recipient.signed",
            ]
        ):
            self.deliver(event_body("evt-late-%s" % index, event, "sr-1"))
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, STATUS_COMPLETED)

    def test_duplicate_delivery_is_acknowledged_once(self):
        body = event_body("evt-4", "signing_request.recipient.signed", "sr-1")
        self.assertEqual(self.deliver(body).status_code, 200)
        second = self.deliver(body)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(json.loads(second.content)["status"], "duplicate")
        self.assertEqual(FirmaWebhookEvent.objects.count(), 1)

    def test_unsigned_delivery_is_refused(self):
        body = event_body("evt-5", "signing_request.completed", "sr-1")
        self.assertEqual(self.deliver(body, header=False).status_code, 401)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, STATUS_SENT)
        self.assertFalse(FirmaWebhookEvent.objects.exists())

    def test_wrong_secret_is_refused(self):
        body = event_body("evt-6", "signing_request.completed", "sr-1")
        response = self.deliver(body, header=sign(body, secret="other"))
        self.assertEqual(response.status_code, 401)

    def test_no_secret_configured_fails_closed(self):
        self.config.webhook_secret = ""
        self.config.save()
        body = event_body("evt-7", "signing_request.completed", "sr-1")
        self.assertEqual(self.deliver(body).status_code, 401)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, STATUS_SENT)

    def test_old_timestamp_is_refused(self):
        body = event_body("evt-8", "signing_request.completed", "sr-1")
        header = sign(body, timestamp=int(time.time()) - 301)
        self.assertEqual(self.deliver(body, header=header).status_code, 401)

    def test_rotation_header_is_accepted(self):
        body = event_body("evt-9", "signing_request.completed", "sr-1")
        response = self.deliver(
            body,
            header=sign(body, secret="next-secret"),
            old_header=sign(body, secret=WEBHOOK_SECRET),
        )
        self.assertEqual(response.status_code, 200)

    def test_unknown_request_is_acknowledged_and_not_kept(self):
        body = event_body("evt-10", "signing_request.completed", "sr-elsewhere")
        response = self.deliver(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "unknown_request")
        self.assertFalse(FirmaWebhookEvent.objects.exists())

    def test_invalid_json_and_missing_id(self):
        body = b"not json"
        self.assertEqual(self.deliver(body).status_code, 400)
        body = json.dumps({"type": "signing_request.completed"}).encode()
        self.assertEqual(self.deliver(body).status_code, 400)

    def test_oversized_body_is_refused(self):
        body = b"{" + b" " * (1024 * 1024 + 1) + b"}"
        self.assertEqual(self.deliver(body).status_code, 413)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.web.get(self.url).status_code, 405)
