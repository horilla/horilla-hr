"""Who may read a signed offer letter through Horilla's per-file media rule.

base/media_access.py follows every foreign key of the record holding the file
(and, from the holder only, every record pointing at it) and grants access on
the view permission or the authorship of any of them. A signed offer letter
must therefore hang only from the candidate.
"""

from unittest import mock

from django.contrib.auth.models import Permission
from django.test import RequestFactory

from base.media_access import user_can_access_media
from base.models import HorillaMailTemplate
from horilla.testkit import make_employee, make_user
from horilla_firma import services
from horilla_firma.models import STATUS_COMPLETED, FirmaSignatureRequest
from horilla_firma.tests.common import FirmaTestCase, sent_response
from recruitment.models import Candidate

PDF = b"%PDF-1.4\n" + b"0" * 64
SIGNED_PATH = "horilla_firma/firmasignaturerequest/signed_document/offer-signed.pdf"
RESUME_PATH = "recruitment/candidate/resume/ada-resume.pdf"


class SignedDocumentAccessTests(FirmaTestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("tpl_author")
        make_employee(company=self.company, email="tpla@test.horilla", user=self.author)
        self.mail_template = HorillaMailTemplate.objects.create(
            title="Offer Letter Body", body="<p>Dear {{ instance.name }}</p>"
        )
        HorillaMailTemplate.objects.filter(pk=self.mail_template.pk).update(
            created_by=self.author
        )
        self.record = self._signed_offer_letter()

    def _signed_offer_letter(self):
        """A document send made through the real send path, then signed."""
        self.session.queue(sent_response("sr-signed"))
        request = RequestFactory().post("/")
        request.user = self.sender
        with mock.patch.object(
            services, "render_offer_letter_pdf", return_value=PDF
        ), mock.patch.object(services, "count_pdf_pages", return_value=1):
            result = services.send(
                request,
                self.candidate,
                {
                    "mode": "document",
                    "mail_template": self.mail_template,
                    "title": "Offer letter",
                    "send_token": "media-token",
                },
            )
        self.assertEqual(result.level, "success")
        FirmaSignatureRequest.all_objects.filter(pk=result.record.pk).update(
            status=STATUS_COMPLETED, signed_document=SIGNED_PATH
        )
        return FirmaSignatureRequest.all_objects.get(pk=result.record.pk)

    def _user(self, username, *codenames):
        user = make_user(username)
        make_employee(
            company=self.company, email="%s@test.horilla" % username, user=user
        )
        for codename in codenames:
            user.user_permissions.add(Permission.objects.get(codename=codename))
        # A fresh instance: Django caches permissions on the user object.
        return type(user).objects.get(pk=user.pk)

    def test_the_offer_letter_template_name_is_kept_without_a_link(self):
        self.assertEqual(self.record.mail_template_title, "Offer Letter Body")
        self.assertEqual(self.record.mail_template_pk, self.mail_template.pk)
        related = {
            field.related_model._meta.label
            for field in FirmaSignatureRequest._meta.get_fields()
            if field.concrete and field.related_model is not None
        }
        self.assertNotIn("base.HorillaMailTemplate", related)

    def test_mail_template_viewer_cannot_read_the_signed_offer(self):
        user = self._user("tpl_viewer", "view_horillamailtemplate")
        self.assertFalse(user.has_perm("recruitment.view_candidate"))
        self.assertFalse(user_can_access_media(user, SIGNED_PATH))

    def test_mail_template_author_cannot_read_the_signed_offer(self):
        author = type(self.author).objects.get(pk=self.author.pk)
        self.assertFalse(user_can_access_media(author, SIGNED_PATH))

    def test_user_without_permissions_cannot_read_the_signed_offer(self):
        self.assertFalse(user_can_access_media(self._user("nobody"), SIGNED_PATH))

    def test_candidate_viewer_can_read_the_signed_offer(self):
        viewer = type(self.viewer).objects.get(pk=self.viewer.pk)
        self.assertTrue(user_can_access_media(viewer, SIGNED_PATH))

    def test_signature_request_permission_does_not_open_candidate_files(self):
        """The reverse link from the candidate must not widen the candidate's files."""
        Candidate.objects.filter(pk=self.candidate.pk).update(resume=RESUME_PATH)
        user = self._user("sr_viewer", "view_firmasignaturerequest")
        self.assertFalse(user_can_access_media(user, RESUME_PATH))

    def test_signature_request_author_does_not_open_candidate_files(self):
        Candidate.objects.filter(pk=self.candidate.pk).update(resume=RESUME_PATH)
        author = self._user("sr_author")
        FirmaSignatureRequest.all_objects.filter(pk=self.record.pk).update(
            created_by=author
        )
        self.assertFalse(user_can_access_media(author, RESUME_PATH))
