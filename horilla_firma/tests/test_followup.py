"""After the send: signed PDF download with back-off, Refresh and Link."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from horilla.scheduling import get_registered_jobs
from horilla.testkit.factories import make_candidate
from horilla_firma import services
from horilla_firma.models import (
    STATUS_COMPLETED,
    STATUS_DECLINED,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_UNCERTAIN,
    FirmaSignatureRequest,
)
from horilla_firma.tests.common import FirmaTestCase
from horilla_firma.tests.fakes import FakeResponse

READY = {
    "status": "finished",
    "is_partial": False,
    "download_url": "https://files.test/signed.pdf",
}


class FetchTests(FirmaTestCase):
    def setUp(self):
        super().setUp()
        self.record = FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="Offer",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_COMPLETED,
            firma_id="sr-1",
            send_token="t1",
        )

    def test_scheduled_job_is_registered(self):
        import horilla_firma.scheduler  # noqa: F401

        ids = [job.job_id for job in get_registered_jobs()]
        self.assertIn("horilla_firma.scheduler.fetch_pending_signed_documents", ids)

    def test_pending_document_is_downloaded_and_stored(self):
        self.session.queue(
            FakeResponse(200, READY), FakeResponse(200, content=b"%PDF-signed")
        )
        services.fetch_pending_signed_documents()
        self.record.refresh_from_db()
        self.assertTrue(self.record.signed_document)
        self.assertTrue(self.record.signed_document.name.startswith("horilla_firma/"))
        with self.record.signed_document.open("rb") as handle:
            self.assertEqual(handle.read(), b"%PDF-signed")
        self.assertEqual(self.record.fetch_attempts, 0)

    def test_failure_backs_off_and_stops(self):
        for attempt in range(1, services.FETCH_MAX_ATTEMPTS + 1):
            FirmaSignatureRequest.all_objects.filter(pk=self.record.pk).update(
                next_fetch_at=None if attempt == 1 else timezone.now()
            )
            self.session.queue(
                FakeResponse(409, {"error": "not ready", "code": "NOT_READY"})
            )
            services.fetch_pending_signed_documents()
            self.record.refresh_from_db()
            self.assertEqual(self.record.fetch_attempts, attempt)
        self.assertTrue(self.record.fetch_stopped)
        calls = len(self.session.calls)
        services.fetch_pending_signed_documents()
        self.assertEqual(len(self.session.calls), calls)

    def test_retry_waits_until_due(self):
        FirmaSignatureRequest.all_objects.filter(pk=self.record.pk).update(
            fetch_attempts=1, next_fetch_at=timezone.now() + timedelta(minutes=10)
        )
        services.fetch_pending_signed_documents()
        self.assertEqual(self.session.calls, [])

    def test_disabled_integration_does_not_fetch(self):
        self.config.is_enabled = False
        self.config.save()
        services.fetch_pending_signed_documents()
        self.assertEqual(self.session.calls, [])


class RefreshAndLinkTests(FirmaTestCase):
    def make(self, **values):
        defaults = {
            "candidate_id": self.candidate,
            "title": "Offer",
            "source": "template",
            "recipient_name": "Ada",
            "recipient_email": "ada@example.org",
            "status": STATUS_SENT,
            "send_token": "tok-%s" % FirmaSignatureRequest.all_objects.count(),
        }
        defaults.update(values)
        return FirmaSignatureRequest.all_objects.create(**defaults)

    def test_refresh_applies_status_and_fetches_the_pdf(self):
        record = self.make(firma_id="sr-r")
        self.session.queue(
            FakeResponse(
                200,
                {
                    "id": "sr-r",
                    "status": {"sent": True, "finished": True},
                    "timestamps": {"finished_on": "2026-11-20T08:00:00Z"},
                },
            ),
            FakeResponse(200, READY),
            FakeResponse(200, content=b"%PDF-signed"),
        )
        response = self.login(self.sender).post(
            reverse("firma-refresh", kwargs={"pk": record.pk}), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, STATUS_COMPLETED)
        self.assertTrue(record.signed_document)

    def test_refresh_never_moves_back(self):
        record = self.make(firma_id="sr-d", status=STATUS_DECLINED)
        self.session.queue(FakeResponse(200, {"status": {"sent": True}}))
        services.refresh(record)
        record.refresh_from_db()
        self.assertEqual(record.status, STATUS_DECLINED)

    def test_viewer_cannot_refresh(self):
        record = self.make(firma_id="sr-v")
        response = self.login(self.viewer).post(
            reverse("firma-refresh", kwargs={"pk": record.pk}), HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(response, "decorator_404.html")
        self.assertEqual(self.session.calls, [])

    def test_admin_links_an_uncertain_send(self):
        record = self.make(status=STATUS_UNCERTAIN)
        self.session.queue(
            FakeResponse(
                200,
                {
                    "id": "sr-found",
                    "status": {"sent": True},
                    "timestamps": {"sent_on": "2026-11-20T08:00:00Z"},
                },
            ),
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "su-1",
                            "first_name": "Ada",
                            "email": "ada@example.org",
                            "designation": "Signer",
                            "order": 1,
                        }
                    ]
                },
            ),
        )
        response = self.login(self.admin).post(
            reverse("firma-link", kwargs={"pk": record.pk}),
            {"firma_id": "sr-found"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.firma_id, "sr-found")
        self.assertEqual(record.status, STATUS_SENT)

    def test_link_refuses_an_id_already_recorded(self):
        self.make(firma_id="sr-taken")
        record = self.make(status=STATUS_UNCERTAIN)
        result = services.link(record, "sr-taken")
        self.assertEqual(result.level, "error")
        self.assertEqual(self.session.calls, [])

    def test_link_refuses_a_request_firma_does_not_know(self):
        record = self.make(status=STATUS_UNCERTAIN)
        self.session.queue(FakeResponse(404, {"error": "no", "code": "NOT_FOUND"}))
        result = services.link(record, "sr-missing")
        self.assertEqual(result.level, "error")
        record.refresh_from_db()
        self.assertIsNone(record.firma_id)

    def test_sender_without_settings_permission_cannot_link(self):
        record = self.make(status=STATUS_UNCERTAIN)
        response = self.login(self.sender).post(
            reverse("firma-link", kwargs={"pk": record.pk}),
            {"firma_id": "sr-x"},
            HTTP_HX_REQUEST="true",
        )
        self.assertTemplateUsed(response, "decorator_404.html")
        self.assertEqual(self.session.calls, [])


def users_response(*users):
    """GET /signing-requests/{id}/users with (email, designation) pairs."""
    return FakeResponse(
        200,
        {
            "results": [
                {
                    "id": "su-%s" % index,
                    "first_name": "R",
                    "email": email,
                    "designation": designation,
                    "order": index + 1,
                }
                for index, (email, designation) in enumerate(users)
            ]
        },
    )


SENT_DETAIL = {
    "id": "sr-other",
    "status": {"sent": True},
    "timestamps": {"sent_on": "2026-11-20T08:00:00Z"},
}


class LinkRecipientTests(FirmaTestCase):
    """Link only accepts a Firma request sent to this row's recipient."""

    def setUp(self):
        super().setUp()
        self.record = FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="Offer",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_UNCERTAIN,
            send_token="link-tok",
        )

    def test_request_for_another_recipient_is_refused(self):
        self.session.queue(
            FakeResponse(200, SENT_DETAIL),
            users_response(("grace@example.org", "Signer")),
        )
        result = services.link(self.record, "sr-other")
        self.assertEqual(result.level, "error")
        self.assertIn("ada@example.org", result.message)
        self.assertIn("grace@example.org", result.message)
        self.assertEqual(len(self.calls("GET", "/signing-requests/sr-other/users")), 1)
        self.record.refresh_from_db()
        self.assertIsNone(self.record.firma_id)
        self.assertEqual(self.record.status, STATUS_UNCERTAIN)

    def test_recipient_only_in_copy_is_refused(self):
        self.session.queue(
            FakeResponse(200, SENT_DETAIL),
            users_response(("grace@example.org", "Signer"), ("ada@example.org", "CC")),
        )
        result = services.link(self.record, "sr-other")
        self.assertEqual(result.level, "error")
        self.record.refresh_from_db()
        self.assertIsNone(self.record.firma_id)

    def test_request_without_recipients_is_refused(self):
        self.session.queue(FakeResponse(200, SENT_DETAIL), users_response())
        result = services.link(self.record, "sr-other")
        self.assertEqual(result.level, "error")
        self.record.refresh_from_db()
        self.assertIsNone(self.record.firma_id)

    def test_recipient_email_matches_regardless_of_case(self):
        self.session.queue(
            FakeResponse(200, SENT_DETAIL),
            users_response((" Ada@Example.ORG ", "Approver")),
        )
        result = services.link(self.record, "sr-other")
        self.assertEqual(result.level, "success")
        self.record.refresh_from_db()
        self.assertEqual(self.record.firma_id, "sr-other")
        self.assertEqual(self.record.status, STATUS_SENT)

    def test_recipients_unreadable_is_refused(self):
        self.session.queue(
            FakeResponse(200, SENT_DETAIL),
            FakeResponse(500, {"error": "boom", "code": "INTERNAL"}),
        )
        result = services.link(self.record, "sr-other")
        self.assertEqual(result.level, "error")
        self.record.refresh_from_db()
        self.assertIsNone(self.record.firma_id)


class InterruptedSendTests(FirmaTestCase):
    """A "sending" row left by an interrupted send is shown as an unknown outcome."""

    def make_sending(self, minutes_ago, token="stale", candidate=None):
        record = FirmaSignatureRequest.all_objects.create(
            candidate_id=candidate or self.candidate,
            title="Interrupted offer",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_SENDING,
            send_token=token,
        )
        FirmaSignatureRequest.all_objects.filter(pk=record.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
        return record

    def tab(self, user):
        return self.login(user).get(
            reverse("firma-candidate-tab", kwargs={"pk": self.candidate.pk}),
            HTTP_HX_REQUEST="true",
        )

    def test_opening_the_tab_shows_a_stale_send_as_unknown_with_link(self):
        record = self.make_sending(10)
        response = self.tab(self.admin)
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, STATUS_UNCERTAIN)
        self.assertContains(response, "Outcome Unknown")
        self.assertContains(response, "may have been sent")
        self.assertContains(response, reverse("firma-link", kwargs={"pk": record.pk}))
        self.assertEqual(self.session.calls, [])

    def test_a_send_still_running_is_left_alone(self):
        record = self.make_sending(1)
        response = self.tab(self.admin)
        record.refresh_from_db()
        self.assertEqual(record.status, STATUS_SENDING)
        self.assertNotContains(
            response, reverse("firma-link", kwargs={"pk": record.pk})
        )

    def test_send_form_asks_for_confirmation_after_a_stale_send(self):
        record = self.make_sending(10)
        self.session.queue(
            FakeResponse(200, {"results": [], "pagination": {"total_pages": 1}})
        )
        response = self.login(self.sender).get(
            reverse("firma-send-form", kwargs={"pk": self.candidate.pk}),
            HTTP_HX_REQUEST="true",
        )
        record.refresh_from_db()
        self.assertEqual(record.status, STATUS_UNCERTAIN)
        self.assertContains(response, 'name="confirm_uncertain"')

    def test_scheduled_job_expires_stale_sends_of_every_candidate(self):
        import horilla_firma.scheduler as scheduler

        ids = [job.job_id for job in get_registered_jobs()]
        self.assertIn("horilla_firma.scheduler.expire_interrupted_sends", ids)
        other = make_candidate(
            recruitment=self.recruitment, email="grace@example.org", name="Grace"
        )
        stale = self.make_sending(10, token="old")
        fresh = self.make_sending(1, token="new", candidate=other)
        scheduler.expire_interrupted_sends()
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, STATUS_UNCERTAIN)
        self.assertIn("may have been sent", stale.message)
        self.assertEqual(fresh.status, STATUS_SENDING)
        self.assertEqual(self.session.calls, [])
