"""
The webhook acts on the employee named by the payload's phone number: it
creates leave/attendance/shift/asset requests and can mail that employee's
files to the sender. So a POST is only honoured when Meta's
X-Hub-Signature-256 matches an HMAC of the raw body.
"""

import hashlib
import hmac
import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from base.models import IntegrationApps
from whatsapp.models import WhatsappCredientials

SECRET = "meta-app-secret-not-real"
PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "metadata": {},
                        "contacts": [{"profile": {"name": "Mallory"}}],
                        "messages": [
                            {
                                "id": "wamid.1",
                                "from": "919999999999",
                                "type": "text",
                                "text": {"body": "leave"},
                            },
                        ],
                    }
                }
            ]
        }
    ],
}


class WebhookSignatureTests(TestCase):
    def setUp(self):
        IntegrationApps.objects.update_or_create(
            app_label="whatsapp", defaults={"is_enabled": True}
        )
        self.creds = WhatsappCredientials.objects.create(
            meta_token="t",
            meta_business_id="b",
            meta_phone_number_id="p",
            meta_phone_number="919000000000",
            meta_webhook_token="verify-token",
            meta_app_secret=SECRET,
        )
        self.url = reverse("whatsapp")
        self.body = json.dumps(PAYLOAD)

    def _post(self, signature=None, body=None):
        body = self.body if body is None else body
        headers = {}
        if signature is not None:
            headers["HTTP_X_HUB_SIGNATURE_256"] = signature
        return self.client.post(
            self.url, data=body, content_type="application/json", **headers
        )

    def _sign(self, body, secret=SECRET):
        return (
            "sha256="
            + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        )

    def test_unsigned_payload_rejected(self):
        self.assertEqual(self._post().status_code, 403)

    def test_wrong_signature_rejected(self):
        self.assertEqual(
            self._post(self._sign(self.body, "wrong-secret")).status_code, 403
        )

    def test_tampered_body_rejected(self):
        """Signature valid for the original body must not validate a changed one."""
        sig = self._sign(self.body)
        tampered = self.body.replace("919999999999", "918888888888")
        self.assertEqual(self._post(sig, body=tampered).status_code, 403)

    def test_valid_signature_reaches_message_handling(self):
        """
        A correctly signed payload must get past the gate. Asserted by
        patching the handler the view calls for an unknown sender, so this
        fails if the signature check starts rejecting genuine deliveries --
        a "not 403" assertion would still pass if the gate broke open.
        """
        with mock.patch("whatsapp.views.send_flow_message") as send:
            self.client.post(
                self.url,
                data=self.body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=self._sign(self.body),
            )
        self.assertTrue(send.called, "signed payload never reached message handling")

    def test_rejected_payload_never_reaches_message_handling(self):
        with mock.patch("whatsapp.views.send_flow_message") as send:
            self._post(self._sign(self.body, "wrong-secret"))
        self.assertFalse(send.called, "forged payload was acted on")

    def test_no_app_secret_configured_fails_closed(self):
        self.creds.meta_app_secret = ""
        self.creds.save()
        self.assertEqual(self._post(self._sign(self.body)).status_code, 403)

    def test_get_verification_still_works(self):
        response = self.client.get(
            self.url,
            {"hub.verify_token": "verify-token", "hub.challenge": "12345"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"12345")
