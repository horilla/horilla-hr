"""Shared fixtures: a company, a recruitment, a candidate, users and a fake Firma."""

import hashlib
import hmac
import json
import time
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import Client, TestCase

from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_candidate, make_recruitment
from horilla_firma.firma_api import FirmaClient
from horilla_firma.models import FirmaSettings
from horilla_firma.tests.fakes import FakeResponse, FakeSession

API_KEY = "test-api-key"
WEBHOOK_SECRET = "whsec_test_secret"


def template_response(template_id="tpl-1", users=(("tu-1", "Signer", 1),), cc=()):
    recipients = [
        {"id": uid, "designation": designation, "order": order}
        for uid, designation, order in users
    ]
    recipients += [{"id": cid, "designation": "CC", "order": 0} for cid in cc]
    return FakeResponse(
        200, {"id": template_id, "name": "Offer Letter", "recipients": recipients}
    )


def sent_response(firma_id="sr-1", send_email=True):
    return FakeResponse(
        201,
        {
            "id": firma_id,
            "name": "Offer letter",
            "settings": {"send_signing_email": send_email},
            "first_signer": {"id": "su-1"},
        },
    )


def sign(body, secret=WEBHOOK_SECRET, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(), ("%s." % timestamp).encode() + body, hashlib.sha256
    ).hexdigest()
    return "t=%s,v1=%s" % (timestamp, digest)


def event_body(event_id, event_type, firma_id, **data):
    payload = {
        "id": event_id,
        "type": event_type,
        "data": {"signing_request": {"id": firma_id, **data}},
    }
    return json.dumps(payload).encode()


class FirmaTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Firma Test Co")
        cls.recruitment = make_recruitment(company=cls.company, title="Engineer")
        cls.candidate = make_candidate(
            recruitment=cls.recruitment,
            email="ada@example.org",
            name="Ada Lovelace",
        )
        cls.admin = make_user("firma_admin", is_superuser=True)
        make_employee(
            company=cls.company, email="firma_admin@test.horilla", user=cls.admin
        )
        cls.sender = make_user("firma_sender")
        make_employee(
            company=cls.company, email="firma_sender@test.horilla", user=cls.sender
        )
        cls.sender.user_permissions.add(
            Permission.objects.get(codename="view_candidate"),
            Permission.objects.get(codename="change_candidate"),
        )
        cls.viewer = make_user("firma_viewer")
        make_employee(
            company=cls.company, email="firma_viewer@test.horilla", user=cls.viewer
        )
        cls.viewer.user_permissions.add(
            Permission.objects.get(codename="view_candidate")
        )

    def setUp(self):
        self.config = FirmaSettings(is_enabled=True)
        self.config.api_key = API_KEY
        self.config.webhook_secret = WEBHOOK_SECRET
        self.config.save()
        self.session = FakeSession()
        patcher = mock.patch(
            "horilla_firma.services.FirmaClient",
            side_effect=lambda key: FirmaClient(key, session=self.session),
        )
        self.client_factory = patcher.start()
        self.addCleanup(patcher.stop)
        # TestCase runs each test inside a transaction, which send() refuses.
        # The refusal itself is tested with real transactions in
        # test_transaction.py.
        outer = mock.patch(
            "horilla_firma.services._inside_transaction", return_value=False
        )
        outer.start()
        self.addCleanup(outer.stop)

    def login(self, user):
        client = Client()
        client.force_login(type(user).objects.get(pk=user.pk))
        return client

    def calls(self, method=None, suffix=None):
        return [
            call
            for call in self.session.calls
            if (method is None or call["method"] == method)
            and (suffix is None or call["url"].endswith(suffix))
        ]
