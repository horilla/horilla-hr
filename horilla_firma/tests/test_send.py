"""Sending an offer letter: request shapes, refusals, send safety (rules 1-5, 11)."""

import base64
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from base.models import HorillaMailTemplate
from horilla_firma import firma_api, services
from horilla_firma.models import (
    STATUS_FAILED,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_UNCERTAIN,
    FirmaSignatureRequest,
)
from horilla_firma.tests.common import FirmaTestCase, sent_response, template_response
from horilla_firma.tests.fakes import FakeResponse

PDF = b"%PDF-1.4\n" + b"0" * 64


class SendTemplateTests(FirmaTestCase):
    def values(self, **extra):
        values = {
            "mode": "template",
            "template_id": "tpl-1",
            "title": "Offer letter for Ada",
            "send_token": "tok-%s" % len(FirmaSignatureRequest.all_objects.all()),
        }
        values.update(extra)
        return values

    def request(self, user=None):
        request = RequestFactory().post("/")
        request.user = user or self.sender
        return request

    def test_sends_to_the_single_template_user(self):
        self.session.queue(template_response(), sent_response("sr-1"))
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "success")
        posts = self.calls("POST", "/signing-requests/create-and-send")
        self.assertEqual(len(posts), 1)
        body = self.session.json_body(self.session.calls.index(posts[0]))
        self.assertEqual(
            body,
            {
                "name": "Offer letter for Ada",
                "template_id": "tpl-1",
                "recipients": [
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "email": "ada@example.org",
                        "template_user_id": "tu-1",
                        "designation": "Signer",
                        "order": 1,
                    }
                ],
            },
        )
        record = FirmaSignatureRequest.all_objects.get()
        self.assertEqual(record.status, STATUS_SENT)
        self.assertEqual(record.firma_id, "sr-1")
        self.assertEqual(record.candidate_id, self.candidate)
        self.assertIsNotNone(record.sent_at)
        self.assertEqual(record.firma_template_name, "Offer Letter")

    def test_default_expiration_from_settings(self):
        self.config.default_expiration_hours = 72
        self.config.save()
        self.session.queue(template_response(), sent_response())
        services.send(self.request(), self.candidate, self.values())
        self.assertEqual(self.session.json_body(1)["expiration_hours"], 72)

    def test_no_invitation_email_is_reported(self):
        self.session.queue(template_response(), sent_response(send_email=False))
        result = services.send(self.request(), self.candidate, self.values())
        self.assertIn("did not email", result.message)
        self.assertTrue(FirmaSignatureRequest.all_objects.get().no_invitation_email)

    def test_multi_role_template_is_refused_before_the_post(self):
        self.session.queue(
            template_response(users=(("a", "Signer", 1), ("b", "Approver", 2)))
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertIn("Nothing was sent", result.message)
        self.assertEqual(self.calls("POST"), [])
        self.assertEqual(FirmaSignatureRequest.all_objects.get().status, STATUS_FAILED)

    def test_cc_rows_do_not_count_as_roles(self):
        self.session.queue(template_response(cc=("cc-1",)), sent_response())
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "success")

    def test_missing_template_is_refused(self):
        self.session.queue(FakeResponse(404, {"error": "no", "code": "NOT_FOUND"}))
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertEqual(self.calls("POST"), [])

    def test_disabled_integration_sends_nothing(self):
        self.config.is_enabled = False
        self.config.save()
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertEqual(self.session.calls, [])
        self.assertFalse(FirmaSignatureRequest.all_objects.exists())

    def test_candidate_without_email_is_refused(self):
        self.candidate.email = ""
        self.candidate.save()
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertEqual(self.session.calls, [])

    def test_replayed_form_does_not_send_again(self):
        self.session.queue(template_response(), sent_response())
        values = self.values(send_token="same")
        services.send(self.request(), self.candidate, values)
        again = services.send(self.request(), self.candidate, values)
        self.assertEqual(again.level, "warning")
        self.assertEqual(len(self.calls("POST")), 1)
        self.assertEqual(FirmaSignatureRequest.all_objects.count(), 1)

    def test_send_in_flight_blocks_a_second_send(self):
        FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="x",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_SENDING,
            send_token="running",
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertIn("already being sent", result.message)
        self.assertEqual(self.session.calls, [])

    def test_interrupted_send_becomes_uncertain_and_needs_confirmation(self):
        stale = FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="x",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_SENDING,
            send_token="old",
        )
        FirmaSignatureRequest.all_objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )
        result = services.send(self.request(), self.candidate, self.values())
        stale.refresh_from_db()
        self.assertEqual(stale.status, STATUS_UNCERTAIN)
        self.assertEqual(result.level, "error")
        self.assertIn("may have been sent", result.message)
        self.assertEqual(self.session.calls, [])

        self.session.queue(template_response(), sent_response("sr-2"))
        result = services.send(
            self.request(), self.candidate, self.values(confirm_uncertain=True)
        )
        self.assertEqual(result.level, "success")

    def test_definite_refusal_is_failed_and_says_nothing_was_sent(self):
        self.session.queue(
            template_response(),
            FakeResponse(400, {"error": "bad email", "code": "VALIDATION_ERROR"}),
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertIn("Nothing was sent", result.message)
        self.assertEqual(FirmaSignatureRequest.all_objects.get().status, STATUS_FAILED)

    def test_gateway_error_is_uncertain_and_never_retried(self):
        for response in [
            FakeResponse(502, {"error": "proxy", "code": "PROXY_ERROR"}),
            FakeResponse(500, {"error": "boom", "code": "INTERNAL"}),
            FakeResponse(504, "timeout"),
            FakeResponse(201, "not json"),
        ]:
            with self.subTest(status=response.status_code):
                FirmaSignatureRequest.all_objects.all().delete()
                self.session.calls.clear()
                self.session.queue(template_response(), response)
                result = services.send(
                    self.request(), self.candidate, self.values(confirm_uncertain=True)
                )
                self.assertEqual(result.level, "warning")
                self.assertIn("may have been sent", result.message)
                self.assertEqual(len(self.calls("POST")), 1)
                self.assertEqual(
                    FirmaSignatureRequest.all_objects.get().status, STATUS_UNCERTAIN
                )

    def test_network_error_is_uncertain(self):
        import requests

        self.session.queue(template_response(), requests.exceptions.ReadTimeout("slow"))
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "warning")
        self.assertEqual(
            FirmaSignatureRequest.all_objects.get().status, STATUS_UNCERTAIN
        )

    def test_already_sent_conflict_records_the_existing_request(self):
        self.session.queue(
            template_response(),
            FakeResponse(
                409,
                {
                    "error": "sent",
                    "code": "ALREADY_SENT",
                    "signing_request_id": "sr-existing",
                },
            ),
            FakeResponse(200, {"id": "sr-existing", "status": {"sent": True}}),
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "warning")
        self.assertIn("not sent again", result.message)
        record = FirmaSignatureRequest.all_objects.get()
        self.assertEqual(record.firma_id, "sr-existing")
        self.assertEqual(record.status, STATUS_SENT)
        self.assertEqual(len(self.calls("POST")), 1)

    def test_send_effects_exist_keeps_the_request(self):
        self.session.queue(
            template_response(),
            FakeResponse(
                409,
                {
                    "error": "kept",
                    "code": "SEND_EFFECTS_EXIST",
                    "signing_request_id": "sr-kept",
                },
            ),
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "warning")
        record = FirmaSignatureRequest.all_objects.get()
        self.assertEqual(record.firma_id, "sr-kept")
        self.assertEqual(record.status, STATUS_SENT)

    def test_send_in_progress_without_id_is_uncertain(self):
        self.session.queue(
            template_response(),
            FakeResponse(409, {"error": "busy", "code": "SEND_IN_PROGRESS"}),
        )
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "warning")
        self.assertEqual(
            FirmaSignatureRequest.all_objects.get().status, STATUS_UNCERTAIN
        )

    def test_requests_are_autocommitted(self):
        """Rule 11: the marker row commits before the POST (no request transaction)."""
        for alias, database in settings.DATABASES.items():
            self.assertFalse(database.get("ATOMIC_REQUESTS", False), alias)


class SendDocumentTests(FirmaTestCase):
    def setUp(self):
        super().setUp()
        self.mail_template = HorillaMailTemplate.objects.create(
            title="Offer Letter Body", body="<p>Dear {{ instance.name }}</p>"
        )

    def values(self, **extra):
        values = {
            "mode": "document",
            "mail_template": self.mail_template,
            "title": "Offer letter",
            "send_token": "doc-token",
        }
        values.update(extra)
        return values

    def request(self):
        request = RequestFactory().post("/")
        request.user = self.sender
        return request

    def test_small_pdf_is_sent_inline_with_signature_on_the_last_page(self):
        self.session.queue(sent_response("sr-doc"))
        with mock.patch.object(
            services, "render_offer_letter_pdf", return_value=PDF
        ), mock.patch.object(services, "count_pdf_pages", return_value=2):
            result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "success")
        body = self.session.json_body(0)
        self.assertEqual(base64.b64decode(body["document"]), PDF)
        self.assertNotIn("document_id", body)
        self.assertEqual(body["fields"][0]["page_number"], 2)
        self.assertEqual(body["fields"][0]["recipient_id"], "temp_1")
        self.assertEqual(body["recipients"][0]["email"], "ada@example.org")
        record = FirmaSignatureRequest.all_objects.get()
        self.assertEqual(record.mail_template_title, "Offer Letter Body")
        self.assertEqual(record.mail_template_pk, self.mail_template.pk)
        self.assertEqual(record.source, "document")

    def test_unknown_page_count_puts_the_box_on_page_one(self):
        self.session.queue(sent_response())
        with mock.patch.object(
            services, "render_offer_letter_pdf", return_value=PDF
        ), mock.patch.object(services, "count_pdf_pages", return_value=None):
            services.send(self.request(), self.candidate, self.values())
        self.assertEqual(self.session.json_body(0)["fields"][0]["page_number"], 1)

    def test_large_pdf_uses_the_presigned_upload(self):
        big = b"%PDF-1.4" + b"0" * firma_api.INLINE_DOCUMENT_LIMIT
        self.session.queue(
            FakeResponse(
                201, {"document_id": "doc-9", "upload_url": "https://s3.test/put"}
            ),
            FakeResponse(200, ""),
            sent_response(),
        )
        with mock.patch.object(
            services, "render_offer_letter_pdf", return_value=big
        ), mock.patch.object(services, "count_pdf_pages", return_value=1):
            result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "success")
        self.assertEqual(self.session.calls[1]["method"], "PUT")
        self.assertNotIn("Authorization", self.session.calls[1]["headers"])
        body = self.session.json_body(2)
        self.assertEqual(body["document_id"], "doc-9")
        self.assertNotIn("document", body)

    def test_pdf_that_cannot_be_generated_is_refused(self):
        with mock.patch.object(
            services,
            "render_offer_letter_pdf",
            side_effect=services.SendRefused("The offer letter PDF could not be made."),
        ):
            result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertEqual(self.session.calls, [])
        self.assertEqual(FirmaSignatureRequest.all_objects.get().status, STATUS_FAILED)

    def test_broken_mail_template_is_a_definite_non_send(self):
        self.mail_template.body = "<p>{% if %}</p>"
        self.mail_template.save()
        result = services.send(self.request(), self.candidate, self.values())
        self.assertEqual(result.level, "error")
        self.assertIn("Nothing was sent", result.message)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(FirmaSignatureRequest.all_objects.get().status, STATUS_FAILED)

    def test_offer_letter_is_rendered_with_the_candidate(self):
        from django.http import HttpResponse

        with mock.patch.object(
            services,
            "generate_pdf",
            return_value=HttpResponse(PDF, content_type="application/pdf"),
        ) as generate:
            services.render_offer_letter_pdf(
                self.request(), self.mail_template, self.candidate
            )
        self.assertIn("Dear Ada Lovelace", generate.call_args.args[0])

    def test_offer_letter_render_checks_the_pdf_response(self):
        from django.http import HttpResponse

        request = self.request()
        with mock.patch.object(
            services,
            "generate_pdf",
            return_value=HttpResponse("Error generating PDF", status=500),
        ):
            with self.assertRaises(services.SendRefused):
                services.render_offer_letter_pdf(
                    request, self.mail_template, self.candidate
                )
        with mock.patch.object(
            services,
            "generate_pdf",
            return_value=HttpResponse(PDF, content_type="application/pdf"),
        ):
            self.assertEqual(
                services.render_offer_letter_pdf(
                    request, self.mail_template, self.candidate
                ),
                PDF,
            )


class SendViewTests(FirmaTestCase):
    def post(self, user, **data):
        payload = {
            "mode": "template",
            "template_id": "tpl-1",
            "title": "Offer letter",
            "send_token": "view-token",
        }
        payload.update(data)
        return self.login(user).post(
            reverse("firma-send", kwargs={"pk": self.candidate.pk}),
            payload,
            HTTP_HX_REQUEST="true",
        )

    def test_sender_can_send(self):
        self.session.queue(template_response(), sent_response("sr-view"))
        response = self.post(self.sender)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sent for signature")
        self.assertEqual(FirmaSignatureRequest.all_objects.get().firma_id, "sr-view")

    def test_viewer_cannot_send(self):
        response = self.post(self.viewer)
        self.assertTemplateUsed(response, "decorator_404.html")
        self.assertEqual(self.session.calls, [])
        self.assertFalse(FirmaSignatureRequest.all_objects.exists())

    def test_anonymous_cannot_send(self):
        from django.test import Client

        response = Client().post(
            reverse("firma-send", kwargs={"pk": self.candidate.pk}), {}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.session.calls, [])

    def test_get_is_not_allowed(self):
        response = self.login(self.sender).get(
            reverse("firma-send", kwargs={"pk": self.candidate.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_send_form_lists_templates_and_marks_multi_role_ones(self):
        self.session.queue(
            FakeResponse(
                200,
                {
                    "results": [
                        {
                            "id": "tpl-1",
                            "name": "Single",
                            "recipients": [
                                {"id": "u", "designation": "Signer", "order": 1}
                            ],
                        },
                        {
                            "id": "tpl-2",
                            "name": "Double",
                            "recipients": [
                                {"id": "a", "designation": "Signer", "order": 1},
                                {"id": "b", "designation": "Signer", "order": 2},
                            ],
                        },
                    ],
                    "pagination": {"total_pages": 1},
                },
            )
        )
        response = self.login(self.sender).get(
            reverse("firma-send-form", kwargs={"pk": self.candidate.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="tpl-1"')
        self.assertContains(response, "Double")
        self.assertContains(response, 'name="send_token"')
        self.assertNotContains(response, 'value="tpl-2"')

    def test_tab_shows_requests_to_viewers_without_the_send_button(self):
        FirmaSignatureRequest.all_objects.create(
            candidate_id=self.candidate,
            title="Old offer",
            source="template",
            recipient_name="Ada",
            recipient_email="ada@example.org",
            status=STATUS_SENT,
            firma_id="sr-old",
            send_token="t-old",
        )
        response = self.login(self.viewer).get(
            reverse("firma-candidate-tab", kwargs={"pk": self.candidate.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Old offer")
        self.assertNotContains(
            response, reverse("firma-send-form", kwargs={"pk": self.candidate.pk})
        )

    def test_tab_is_registered_on_the_candidate_profile(self):
        from horilla_views.generic.cbv.views import HorillaProfileView

        self.assertIn(
            "candidateprofileview-E-Signatures",
            HorillaProfileView._tab_view_registry,
        )
