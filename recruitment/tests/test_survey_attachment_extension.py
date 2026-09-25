"""
Half of GHSA-x567-v324-7mr2 (pre-auth RCE): candidate_survey() (the public,
unauthenticated career-page survey) wrote every uploaded file straight under
MEDIA_ROOT/recruitment_attachment/ with whatever name and extension the
uploader chose. MEDIA_ROOT sits under the app's own working directory
(a namespace package, no __init__.py), so a saved ``pwn.py`` was importable
by anything that later did a dotted-path import against it -- which
get_to_field()'s ``model`` query param did, until that sink was fixed
separately (horilla_automations/methods/methods.py).

This is defense in depth for the same chain: reject server-executable
extensions outright at the upload itself, regardless of what any other
endpoint later does with the file.
"""

from django.core import serializers
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from base.models import Company, Department
from recruitment.models import Candidate, JobPosition, Recruitment, Stage


class SurveyAttachmentExtensionTests(TestCase):
    def setUp(self):
        company = Company.objects.create(
            company="Survey Co",
            hq=True,
            address="1 Test St",
            country="US",
            state="CA",
            city="LA",
            zip="90001",
        )
        department = Department.objects.create(department="Eng")
        job_position = JobPosition.objects.create(
            job_position="Engineer", department_id=department
        )
        self.recruitment = Recruitment.objects.create(
            title="Survey Recruitment", job_position_id=job_position, is_published=True
        )
        self.stage = Stage.objects.create(
            recruitment_id=self.recruitment,
            stage=f"Applied-{self.recruitment.pk}",
            stage_type="applied",
        )
        self.candidate = Candidate.objects.create(
            name="Uploader",
            email="uploader@example.test",
            recruitment_id=self.recruitment,
            job_position_id=job_position,
            stage_id=self.stage,
        )

    def _client_with_candidate_in_session(self):
        client = Client()
        session = client.session
        session["candidate"] = serializers.serialize("json", [self.candidate])
        session.save()
        return client

    def _submit(self, filename, content=b"payload"):
        client = self._client_with_candidate_in_session()
        upload = SimpleUploadedFile(filename, content)
        return client.post(
            reverse("candidate-survey"), {"resume_upload": upload}, format="multipart"
        )

    def test_an_uploaded_python_file_is_rejected(self):
        response = self._submit("pwn.py")
        self.assertContains(response, "That file type isn", status_code=200)
        self.assertFalse(
            self.candidate.recruitmentsurveyanswer_set.filter(
                answer_json__icontains="pwn.py"
            ).exists()
        )

    def test_an_ordinary_document_is_still_accepted(self):
        response = self._submit("resume.pdf")
        self.assertNotContains(response, "That file type isn")
        self.assertTrue(
            self.candidate.recruitmentsurveyanswer_set.filter(
                answer_json__icontains="resume.pdf"
            ).exists()
        )
