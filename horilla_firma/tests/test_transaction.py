"""Rule 11 with real transactions: the "sending" row is committed before the POST.

FirmaTestCase is a TestCase, which runs every test inside a transaction, so
it cannot see whether the row is committed. These tests use real commits and
read the row from a second database connection at the moment Firma is called.
"""

import threading
from unittest import mock

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection, transaction
from django.test import Client, RequestFactory, TransactionTestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from horilla.testkit.factories import make_candidate, make_recruitment
from horilla_firma import services
from horilla_firma.firma_api import FirmaClient
from horilla_firma.models import (
    STATUS_SENDING,
    STATUS_SENT,
    FirmaSettings,
    FirmaSignatureRequest,
)
from horilla_firma.tests.common import API_KEY, sent_response, template_response
from horilla_firma.tests.fakes import FakeSession


def _seen_from_another_connection(candidate_pk):
    """The statuses another connection sees for the candidate's requests."""
    seen = {}

    def read():
        try:
            seen["statuses"] = list(
                FirmaSignatureRequest.all_objects.filter(
                    candidate_id=candidate_pk
                ).values_list("status", flat=True)
            )
        except Exception as error:  # noqa: BLE001 - reported to the test
            seen["error"] = repr(error)
        finally:
            close_old_connections()
            connection.close()

    thread = threading.Thread(target=read)
    thread.start()
    thread.join(timeout=30)
    return seen


class ObservingSession(FakeSession):
    """Records the transaction state at the moment create-and-send is called."""

    def __init__(self, candidate_pk):
        super().__init__()
        self.candidate_pk = candidate_pk
        self.observed = None

    def request(self, method, url, **kwargs):
        if url.endswith("/signing-requests/create-and-send"):
            self.observed = {
                "in_atomic_block": transaction.get_connection().in_atomic_block,
                "autocommit": transaction.get_autocommit(),
                "other_connection": _seen_from_another_connection(self.candidate_pk),
            }
        return super().request(method, url, **kwargs)


class SendCommitTests(TransactionTestCase):
    def setUp(self):
        company = make_company("Firma Commit Co")
        recruitment = make_recruitment(company=company, title="Engineer")
        self.candidate = make_candidate(
            recruitment=recruitment, email="ada@example.org", name="Ada Lovelace"
        )
        self.sender = make_user("firma_commit_sender")
        make_employee(company=company, email="commit@test.horilla", user=self.sender)
        config = FirmaSettings(is_enabled=True)
        config.api_key = API_KEY
        config.save()
        self.session = ObservingSession(self.candidate.pk)
        patcher = mock.patch(
            "horilla_firma.services.FirmaClient",
            side_effect=lambda key: FirmaClient(key, session=self.session),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, token):
        request = RequestFactory().post("/")
        request.user = self.sender
        return services.send(
            request,
            self.candidate,
            {
                "mode": "template",
                "template_id": "tpl-1",
                "title": "Offer letter",
                "send_token": token,
            },
        )

    def posts(self):
        return [
            call
            for call in self.session.calls
            if call["url"].endswith("/signing-requests/create-and-send")
        ]

    def test_sending_row_is_committed_and_visible_before_the_post(self):
        self.session.queue(template_response(), sent_response("sr-commit"))
        result = self.send("commit-token")
        self.assertEqual(result.level, "success")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(
            self.session.observed,
            {
                "in_atomic_block": False,
                "autocommit": True,
                "other_connection": {"statuses": [STATUS_SENDING]},
            },
        )
        self.assertEqual(FirmaSignatureRequest.all_objects.get().status, STATUS_SENT)

    def test_the_check_detects_an_uncommitted_row(self):
        """Without the refusal, a send inside a transaction POSTs before commit."""
        self.session.queue(template_response(), sent_response("sr-hidden"))
        with mock.patch.object(services, "_inside_transaction", return_value=False):
            with transaction.atomic():
                self.send("hidden-token")
        observed = self.session.observed
        self.assertTrue(observed["in_atomic_block"])
        other = observed["other_connection"]
        if connection.vendor == "sqlite":
            # The shared-cache SQLite test database locks the table while the
            # writer's transaction is open; a plain file database may answer
            # without the uncommitted row instead. Any other error fails.
            if "error" in other:
                self.assertEqual(set(other), {"error"})
                self.assertIn("locked", other["error"])
            else:
                self.assertEqual(set(other), {"statuses"})
                self.assertNotIn(STATUS_SENDING, other["statuses"])
        else:
            # PostgreSQL and MySQL read committed data: no row at all.
            self.assertEqual(other, {"statuses": []})

    def test_send_inside_a_transaction_is_refused_before_anything_is_sent(self):
        self.session.queue(template_response(), sent_response("sr-nested"))
        with transaction.atomic():
            result = self.send("nested-token")
        self.assertEqual(result.level, "error")
        self.assertIn("Nothing was sent", result.message)
        self.assertEqual(self.session.calls, [])
        self.assertIsNone(self.session.observed)
        self.assertFalse(FirmaSignatureRequest.all_objects.exists())


class AtomicRequestsSendViewTests(TransactionTestCase):
    """With ATOMIC_REQUESTS on, the send view still commits the row first."""

    def setUp(self):
        company = make_company("Firma Atomic Co")
        recruitment = make_recruitment(company=company, title="Engineer")
        self.candidate = make_candidate(
            recruitment=recruitment, email="ada@example.org", name="Ada Lovelace"
        )
        self.sender = make_user("firma_atomic_sender")
        make_employee(company=company, email="atomic@test.horilla", user=self.sender)
        self.sender.user_permissions.add(
            Permission.objects.get(codename="view_candidate"),
            Permission.objects.get(codename="change_candidate"),
        )
        config = FirmaSettings(is_enabled=True)
        config.api_key = API_KEY
        config.save()
        self.session = ObservingSession(self.candidate.pk)
        patcher = mock.patch(
            "horilla_firma.services.FirmaClient",
            side_effect=lambda key: FirmaClient(key, session=self.session),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = connection.settings_dict.get("ATOMIC_REQUESTS", False)
        connection.settings_dict["ATOMIC_REQUESTS"] = True
        self.addCleanup(
            connection.settings_dict.__setitem__, "ATOMIC_REQUESTS", previous
        )

    def test_send_view_commits_the_row_before_the_post(self):
        self.session.queue(template_response(), sent_response("sr-atomic"))
        client = Client()
        client.force_login(type(self.sender).objects.get(pk=self.sender.pk))
        response = client.post(
            reverse("firma-send", kwargs={"pk": self.candidate.pk}),
            {
                "mode": "template",
                "template_id": "tpl-1",
                "title": "Offer letter",
                "send_token": "atomic-token",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Nothing was sent")
        posts = [
            call
            for call in self.session.calls
            if call["url"].endswith("/signing-requests/create-and-send")
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(
            self.session.observed,
            {
                "in_atomic_block": False,
                "autocommit": True,
                "other_connection": {"statuses": [STATUS_SENDING]},
            },
        )
        record = FirmaSignatureRequest.all_objects.get()
        self.assertEqual((record.status, record.firma_id), (STATUS_SENT, "sr-atomic"))
