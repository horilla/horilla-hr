"""The Firma API client: request shapes, error handling and send safety."""

import hashlib
import hmac
import time

import requests
from django.test import SimpleTestCase

from horilla_firma import firma_api
from horilla_firma.firma_api import (
    ALREADY_SENT,
    KEPT,
    NOT_CREATED,
    UNKNOWN,
    FirmaApiError,
    FirmaClient,
)
from horilla_firma.tests.fakes import FakeResponse, FakeSession

BASE = firma_api.FIRMA_BASE_URL


def client(*responses):
    session = FakeSession(*responses)
    return FirmaClient("key-123", session=session), session


def template_row(template_id="t1", users=(("u1", "Signer", 1),), cc=()):
    recipients = [
        {"id": uid, "designation": designation, "order": order}
        for uid, designation, order in users
    ]
    recipients += [{"id": cid, "designation": "CC", "order": 0} for cid in cc]
    return {
        "id": template_id,
        "name": "Offer %s" % template_id,
        "recipients": recipients,
    }


class TransportTests(SimpleTestCase):
    def test_raw_key_in_authorization_header_without_bearer(self):
        api, session = client(FakeResponse(200, {"results": [], "pagination": {}}))
        api.test_connection()
        call = session.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], BASE + "/templates")
        self.assertEqual(call["params"], {"page_size": 1})
        self.assertEqual(call["headers"]["Authorization"], "key-123")
        self.assertNotIn("Bearer", call["headers"]["Authorization"])
        self.assertEqual(call["timeout"], firma_api.TIMEOUT)

    def test_missing_key_is_refused_before_any_call(self):
        with self.assertRaises(FirmaApiError) as caught:
            FirmaClient("  ")
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_error_body_is_parsed(self):
        api, _ = client(
            FakeResponse(
                409,
                {"error": "sent", "code": "ALREADY_SENT", "signing_request_id": "sr-1"},
            )
        )
        with self.assertRaises(FirmaApiError) as caught:
            api.create_and_send({"name": "x"})
        error = caught.exception
        self.assertEqual(error.status, 409)
        self.assertEqual(error.code, "ALREADY_SENT")
        self.assertTrue(error.has_firma_body)
        self.assertEqual(error.signing_request_id, "sr-1")

    def test_error_without_firma_body(self):
        api, _ = client(FakeResponse(502, "Bad gateway", reason="Bad Gateway"))
        with self.assertRaises(FirmaApiError) as caught:
            api.test_connection()
        self.assertEqual(caught.exception.code, "HTTP_502")
        self.assertFalse(caught.exception.has_firma_body)

    def test_network_error(self):
        api, _ = client(requests.exceptions.ConnectionError("down"))
        with self.assertRaises(FirmaApiError) as caught:
            api.test_connection()
        self.assertEqual(caught.exception.status, 0)
        self.assertEqual(caught.exception.code, "NETWORK_ERROR")

    def test_long_messages_are_cut(self):
        api, _ = client(FakeResponse(400, {"error": "x" * 2000, "code": "BAD"}))
        with self.assertRaises(FirmaApiError) as caught:
            api.test_connection()
        self.assertLessEqual(
            len(caught.exception.message), firma_api.MAX_MESSAGE_LENGTH
        )

    def test_path_ids_are_quoted(self):
        api, session = client(FakeResponse(200, {"id": "a/b"}))
        api.get_signing_request("a/b?x")
        self.assertEqual(session.calls[0]["url"], BASE + "/signing-requests/a%2Fb%3Fx")

    def test_create_and_send_without_id_is_invalid_response(self):
        api, _ = client(FakeResponse(201, {"name": "no id"}))
        with self.assertRaises(FirmaApiError) as caught:
            api.create_and_send({"name": "x"})
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")

    def test_create_and_send_posts_json_body(self):
        api, session = client(FakeResponse(201, {"id": "sr-9"}))
        api.create_and_send({"name": "Offer"})
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], BASE + "/signing-requests/create-and-send")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(session.json_body(0), {"name": "Offer"})


class TemplateListTests(SimpleTestCase):
    def test_reads_every_page(self):
        api, session = client(
            FakeResponse(
                200,
                {"results": [template_row("t1")], "pagination": {"total_pages": 2}},
            ),
            FakeResponse(
                200,
                {"results": [template_row("t2")], "pagination": {"total_pages": 2}},
            ),
        )
        templates, complete = api.list_templates()
        self.assertTrue(complete)
        self.assertEqual([t["id"] for t in templates], ["t1", "t2"])
        self.assertEqual(
            session.calls[0]["params"],
            {"page": 1, "page_size": 200, "sort_by": "name", "sort_order": "asc"},
        )
        self.assertEqual(session.calls[1]["params"]["page"], 2)

    def test_short_page_without_pagination_ends_the_list(self):
        api, session = client(FakeResponse(200, {"results": [template_row("t1")]}))
        templates, complete = api.list_templates()
        self.assertTrue(complete)
        self.assertEqual(len(session.calls), 1)

    def test_empty_page_before_the_promised_end_is_incomplete(self):
        api, _ = client(
            FakeResponse(200, {"results": [], "pagination": {"total_pages": 3}})
        )
        templates, complete = api.list_templates()
        self.assertFalse(complete)

    def test_page_cap_is_incomplete(self):
        api, _ = client(
            FakeResponse(
                200, {"results": [template_row()], "pagination": {"total_pages": 9}}
            ),
            FakeResponse(
                200, {"results": [template_row()], "pagination": {"total_pages": 9}}
            ),
        )
        _, complete = api.list_templates(max_pages=2)
        self.assertFalse(complete)

    def test_unreadable_page_raises(self):
        api, _ = client(FakeResponse(200, {"results": "nope"}))
        with self.assertRaises(FirmaApiError):
            api.list_templates()

    def test_cc_rows_are_dropped_and_users_sorted(self):
        parsed = firma_api.parse_template(
            template_row(users=(("b", "Approver", 2), ("a", "Signer", 1)), cc=("c",))
        )
        self.assertEqual([u["id"] for u in parsed["users"]], ["a", "b"])

    def test_get_template_404_is_none(self):
        api, _ = client(FakeResponse(404, {"error": "no", "code": "NOT_FOUND"}))
        self.assertIsNone(api.get_template("t1"))


class TemplateMatchingTests(SimpleTestCase):
    def test_single_user_template_is_picked(self):
        template = firma_api.parse_template(template_row())
        ok, user = firma_api.pick_template_user(template)
        self.assertTrue(ok)
        self.assertEqual(user["id"], "u1")

    def test_template_without_users_sends_as_signer(self):
        ok, user = firma_api.pick_template_user({"name": "x", "users": []})
        self.assertTrue(ok)
        self.assertIsNone(user)

    def test_multi_user_template_is_refused(self):
        template = firma_api.parse_template(
            template_row(users=(("a", "Signer", 1), ("b", "Approver", 2)))
        )
        ok, message = firma_api.pick_template_user(template)
        self.assertFalse(ok)
        self.assertIn("2 recipients", message)

    def test_unmatched_recipient_is_refused(self):
        users = [{"id": "u1", "designation": "Signer", "order": 1}]
        with self.assertRaises(FirmaApiError) as caught:
            firma_api.check_template_recipients(
                users, [{"first_name": "A", "email": "a@b.co", "order": 5}]
            )
        self.assertIn("matches no role", caught.exception.message)

    def test_unknown_template_user_id_is_refused(self):
        users = [{"id": "u1", "designation": "Signer", "order": 1}]
        with self.assertRaises(FirmaApiError):
            firma_api.check_template_recipients(users, [{"template_user_id": "zz"}])

    def test_doubly_matched_recipient_is_refused(self):
        users = [
            {"id": "u1", "designation": "Signer", "order": 1},
            {"id": "u2", "designation": "Signer", "order": 1},
        ]
        with self.assertRaises(FirmaApiError) as caught:
            firma_api.check_template_recipients(users, [{"order": 1}])
        self.assertIn("more than one role", caught.exception.message)

    def test_two_recipients_on_one_role_are_refused(self):
        users = [{"id": "u1", "designation": "Signer", "order": 1}]
        with self.assertRaises(FirmaApiError):
            firma_api.check_template_recipients(
                users, [{"template_user_id": "u1"}, {"order": 1}]
            )

    def test_uncovered_role_is_refused(self):
        users = [
            {"id": "u1", "designation": "Signer", "order": 1},
            {"id": "u2", "designation": "Approver", "order": 2},
        ]
        with self.assertRaises(FirmaApiError) as caught:
            firma_api.check_template_recipients(users, [{"template_user_id": "u1"}])
        self.assertIn("No recipient fills", caught.exception.message)

    def test_cc_recipients_are_not_matched(self):
        users = [{"id": "u1", "designation": "Signer", "order": 1}]
        firma_api.check_template_recipients(
            users, [{"template_user_id": "u1"}, {"designation": "CC", "order": 9}]
        )


class BodyTests(SimpleTestCase):
    def test_template_body_targets_the_template_user(self):
        body = firma_api.build_template_body(
            "t1",
            {"id": "u1", "designation": "Signer", "order": 1},
            "Offer letter",
            "Ada",
            "Lovelace",
            "ada@example.org",
            48,
        )
        self.assertEqual(
            body,
            {
                "name": "Offer letter",
                "expiration_hours": 48,
                "template_id": "t1",
                "recipients": [
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "email": "ada@example.org",
                        "template_user_id": "u1",
                        "designation": "Signer",
                        "order": 1,
                    }
                ],
            },
        )

    def test_template_body_refuses_bad_email(self):
        with self.assertRaises(FirmaApiError):
            firma_api.build_template_body("t1", None, "x", "Ada", "", "not-an-email")

    def test_template_body_refuses_missing_template(self):
        with self.assertRaises(FirmaApiError):
            firma_api.build_template_body(" ", None, "x", "Ada", "", "a@b.co")

    def test_expiration_must_be_positive(self):
        with self.assertRaises(FirmaApiError):
            firma_api.build_template_body("t1", None, "x", "Ada", "", "a@b.co", 0.5)

    def test_document_body_inline_with_known_page_count(self):
        body = firma_api.build_document_body(
            "Offer", "Ada", "", "a@b.co", 3, document_b64="QUJD"
        )
        self.assertEqual(body["document"], "QUJD")
        self.assertNotIn("document_id", body)
        self.assertEqual(
            body["recipients"],
            [
                {
                    "first_name": "Ada",
                    "email": "a@b.co",
                    "id": "temp_1",
                    "designation": "Signer",
                    "order": 1,
                }
            ],
        )
        field = body["fields"][0]
        self.assertEqual(field["type"], "signature")
        self.assertEqual(field["recipient_id"], "temp_1")
        self.assertEqual(field["page_number"], 3)
        self.assertEqual(field["position"], firma_api.DEFAULT_SIGNATURE_BOX)

    def test_document_body_unknown_page_count_uses_page_one(self):
        body = firma_api.build_document_body(
            "Offer", "Ada", "", "a@b.co", None, document_id="doc-1"
        )
        self.assertEqual(body["document_id"], "doc-1")
        self.assertEqual(body["fields"][0]["page_number"], 1)

    def test_document_body_needs_exactly_one_source(self):
        with self.assertRaises(FirmaApiError):
            firma_api.build_document_body("Offer", "Ada", "", "a@b.co", 1)
        with self.assertRaises(FirmaApiError):
            firma_api.build_document_body(
                "Offer", "Ada", "", "a@b.co", 1, document_b64="QQ", document_id="d"
            )

    def test_split_name(self):
        self.assertEqual(
            firma_api.split_name("Ada King Lovelace"), ("Ada", "King Lovelace")
        )
        self.assertEqual(firma_api.split_name("Ada"), ("Ada", ""))
        self.assertEqual(firma_api.split_name(""), ("", ""))


class DocumentUploadTests(SimpleTestCase):
    def test_upload_posts_metadata_then_puts_bytes_without_key(self):
        api, session = client(
            FakeResponse(
                201, {"document_id": "doc-1", "upload_url": "https://s3.test/u"}
            ),
            FakeResponse(200, ""),
        )
        content = b"%PDF-1.4" + b"0" * 10
        self.assertEqual(api.upload_document("offer.pdf", content), "doc-1")
        self.assertEqual(session.calls[0]["url"], BASE + "/documents")
        self.assertEqual(
            session.json_body(0),
            {
                "file_name": "offer.pdf",
                "file_size": len(content),
                "content_type": "application/pdf",
            },
        )
        put = session.calls[1]
        self.assertEqual(put["method"], "PUT")
        self.assertEqual(put["url"], "https://s3.test/u")
        self.assertEqual(put["data"], content)
        self.assertNotIn("Authorization", put["headers"])

    def test_failed_put_is_upload_failed(self):
        api, _ = client(
            FakeResponse(
                201, {"document_id": "doc-1", "upload_url": "https://s3.test/u"}
            ),
            FakeResponse(403, ""),
        )
        with self.assertRaises(FirmaApiError) as caught:
            api.upload_document("offer.pdf", b"%PDF")
        self.assertEqual(caught.exception.code, "UPLOAD_FAILED")

    def test_oversized_file_is_refused_before_any_call(self):
        api, session = client()
        with self.assertRaises(FirmaApiError):
            api.upload_document("big.pdf", b"0" * (firma_api.MAX_UPLOAD_SIZE + 1))
        self.assertEqual(session.calls, [])


class DownloadTests(SimpleTestCase):
    def test_finished_document_is_downloaded_without_key(self):
        api, session = client(
            FakeResponse(
                200,
                {
                    "status": "finished",
                    "is_partial": False,
                    "download_url": "https://files.test/x.pdf",
                },
            ),
            FakeResponse(200, content=b"%PDF-signed"),
        )
        self.assertEqual(api.fetch_signed_pdf("sr-1"), b"%PDF-signed")
        self.assertEqual(
            session.calls[0]["url"], BASE + "/signing-requests/sr-1/download"
        )
        self.assertNotIn("headers", session.calls[1])

    def test_partial_document_is_not_ready(self):
        api, _ = client(
            FakeResponse(
                200,
                {
                    "status": "finished",
                    "is_partial": True,
                    "download_url": "https://files.test/x.pdf",
                },
            )
        )
        with self.assertRaises(FirmaApiError) as caught:
            api.fetch_signed_pdf("sr-1")
        self.assertEqual(caught.exception.code, "NOT_READY")

    def test_non_https_download_url_is_refused(self):
        api, _ = client(
            FakeResponse(
                200, {"status": "finished", "download_url": "http://files.test/x"}
            )
        )
        with self.assertRaises(FirmaApiError) as caught:
            api.fetch_signed_pdf("sr-1")
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")


class WebhookListTests(SimpleTestCase):
    def test_lists_every_page_for_the_url(self):
        api, session = client(
            FakeResponse(
                200,
                {
                    "results": [{"id": "w1", "url": "https://h/x"}],
                    "pagination": {"total_pages": 2},
                },
            ),
            FakeResponse(
                200,
                {
                    "results": [{"id": "w2", "url": "https://h/x"}],
                    "pagination": {"total_pages": 2},
                },
            ),
        )
        hooks = api.list_webhooks("https://h/x")
        self.assertEqual([h["id"] for h in hooks], ["w1", "w2"])
        self.assertEqual(
            session.calls[0]["params"],
            {"url": "https://h/x", "page": 1, "page_size": 200},
        )

    def test_create_webhook_body(self):
        api, session = client(FakeResponse(201, {"id": "w1"}))
        self.assertEqual(api.create_webhook("https://h/x"), "w1")
        self.assertEqual(
            session.json_body(0),
            {"url": "https://h/x", "events": firma_api.WEBHOOK_EVENTS},
        )


class ClassificationTests(SimpleTestCase):
    """Every failure class from the send-safety rules (1 and 2)."""

    def classify(self, status, code=None, has_body=True, sr_id=None):
        error = FirmaApiError(
            status,
            code or "HTTP_%s" % status,
            "m",
            has_firma_body=has_body,
            signing_request_id=sr_id,
        )
        return firma_api.classify_create_and_send_failure(error)

    def test_definite_refusals(self):
        for status, code in [
            (400, "VALIDATION_ERROR"),
            (401, "UNAUTHORIZED"),
            (402, "INSUFFICIENT_CREDITS"),
            (403, "FORBIDDEN"),
            (404, "NOT_FOUND"),
            (409, "OTHER_CONFLICT"),
            (413, "PAYLOAD_TOO_LARGE"),
            (422, "UNPROCESSABLE"),
            (429, "RATE_LIMITED"),
            (503, "ANCHOR_DISABLED_EDGE"),
            (503, "SEALS_DISABLED"),
        ]:
            with self.subTest(status=status, code=code):
                self.assertEqual(self.classify(status, code), (NOT_CREATED, None))

    def test_local_refusals(self):
        self.assertEqual(
            firma_api.classify_create_and_send_failure(firma_api.invalid_input("bad")),
            (NOT_CREATED, None),
        )
        self.assertEqual(self.classify(400, "UPLOAD_FAILED"), (NOT_CREATED, None))

    def test_already_sent_with_id(self):
        self.assertEqual(
            self.classify(409, "ALREADY_SENT", sr_id="sr-1"), (ALREADY_SENT, "sr-1")
        )

    def test_already_sent_without_id_is_a_refusal(self):
        self.assertEqual(self.classify(409, "ALREADY_SENT"), (NOT_CREATED, None))

    def test_send_effects_exist_and_in_progress_are_kept(self):
        self.assertEqual(
            self.classify(409, "SEND_EFFECTS_EXIST", sr_id="sr-2"), (KEPT, "sr-2")
        )
        self.assertEqual(
            self.classify(409, "SEND_IN_PROGRESS", sr_id="sr-3"), (KEPT, "sr-3")
        )
        self.assertEqual(self.classify(409, "SEND_IN_PROGRESS"), (KEPT, None))

    def test_uncertain_outcomes(self):
        for status, code, has_body in [
            (500, "INTERNAL", True),
            (502, "PROXY_ERROR", True),
            (503, "HTTP_503", False),
            (503, "ANCHOR_DISABLED_EDGE", False),
            (504, "HTTP_504", False),
            (546, "HTTP_546", False),
            (0, "NETWORK_ERROR", False),
            (200, "INVALID_RESPONSE", False),
        ]:
            with self.subTest(status=status, code=code):
                self.assertEqual(self.classify(status, code, has_body), (UNKNOWN, None))

    def test_unexpected_exception_is_uncertain(self):
        self.assertEqual(
            firma_api.classify_create_and_send_failure(RuntimeError("x")),
            (UNKNOWN, None),
        )


class StatusFlagTests(SimpleTestCase):
    def test_flags(self):
        self.assertEqual(firma_api.status_from_flags({"finished": True}), "completed")
        self.assertEqual(firma_api.status_from_flags({"declined": True}), "declined")
        self.assertEqual(firma_api.status_from_flags({"cancelled": True}), "cancelled")
        self.assertEqual(firma_api.status_from_flags({"expired": True}), "expired")
        self.assertEqual(firma_api.status_from_flags({"sent": True}), "sent")
        self.assertIsNone(firma_api.status_from_flags({}))
        self.assertIsNone(firma_api.status_from_flags(None))


class SignatureTests(SimpleTestCase):
    secret = "whsec_test"
    body = b'{"id":"evt_1","type":"signing_request.completed"}'

    def header(self, timestamp=None, secret=None, body=None):
        timestamp = int(time.time()) if timestamp is None else timestamp
        signed = ("%s." % timestamp).encode() + (body or self.body)
        digest = hmac.new(
            (secret or self.secret).encode(), signed, hashlib.sha256
        ).hexdigest()
        return "t=%s,v1=%s" % (timestamp, digest)

    def verify(self, headers, secret=None):
        return firma_api.verify_webhook(
            headers.get, self.body, self.secret if secret is None else secret
        )

    def test_valid_signature(self):
        self.assertEqual(self.verify({"X-Firma-Signature": self.header()}), "ok")

    def test_wrong_secret(self):
        headers = {"X-Firma-Signature": self.header(secret="other")}
        self.assertEqual(self.verify(headers), "invalid")

    def test_tampered_body(self):
        headers = {"X-Firma-Signature": self.header(body=b"{}")}
        self.assertEqual(self.verify(headers), "invalid")

    def test_no_secret_fails_closed(self):
        self.assertEqual(
            self.verify({"X-Firma-Signature": self.header()}, secret=""), "invalid"
        )

    def test_missing_header(self):
        self.assertEqual(self.verify({}), "invalid")

    def test_older_than_five_minutes_is_stale(self):
        headers = {"X-Firma-Signature": self.header(int(time.time()) - 301)}
        self.assertEqual(self.verify(headers), "stale")

    def test_old_header_during_rotation(self):
        headers = {
            "X-Firma-Signature": self.header(secret="new-secret"),
            "X-Firma-Signature-Old": self.header(),
        }
        self.assertEqual(self.verify(headers), "ok")

    def test_malformed_timestamp(self):
        headers = {"X-Firma-Signature": "t=abc,v1=00"}
        self.assertEqual(self.verify(headers), "invalid")
