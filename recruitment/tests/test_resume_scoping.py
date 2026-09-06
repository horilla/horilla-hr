"""
Resume has no company_id of its own, so the recruitment is what scopes it.

The public application form reads a resume by id from the query string and
attaches that file to the submitted application. Unscoped, that let anyone
walk sequential ids and harvest every CV in the database, across companies.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from base.models import Department, JobPosition
from horilla.testkit import make_company
from recruitment.models import Recruitment, Resume

PDF = b"%PDF-1.4 fake resume bytes"


def _recruitment(company_name, title, job_title):
    company = make_company(company_name)
    dept = Department.objects.create(department=f"{company_name} Dept")
    dept.company_id.add(company)
    jp = JobPosition.objects.create(job_position=job_title, department_id=dept)
    rec = Recruitment.objects.create(
        title=title,
        description="d",
        company_id=company,
        job_position_id=jp,
        vacancy=1,
        is_published=True,
        optional_resume=True,
        optional_profile_image=True,
    )
    rec.open_positions.add(jp)
    return rec


class ResumeScopingTests(TestCase):
    def setUp(self):
        self.rec_a = _recruitment("Alpha Corp", "Alpha Hire", "Alpha Dev")
        self.rec_b = _recruitment("Beta Corp", "Beta Hire", "Beta Dev")
        self.resume_b = Resume.objects.create(
            file=SimpleUploadedFile("victim.pdf", PDF, content_type="application/pdf"),
            recruitment_id=self.rec_b,
        )

    def test_application_form_ignores_a_resume_from_another_recruitment(self):
        """The cross-tenant read: apply to A, cite B's resume id."""
        response = self.client.get(
            reverse("application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.resume_b.id},
        )
        self.assertEqual(response.status_code, 200)
        # The victim's file must not be handed to the applicant in any form.
        self.assertNotIn(PDF, response.content)
        self.assertNotIn(
            self.resume_b.file.name.encode(),
            response.content,
            "another recruitment's resume leaked into the public form",
        )

    def test_resume_from_the_same_recruitment_still_resolves(self):
        """The guard must not break the legitimate prefill path."""
        own = Resume.objects.create(
            file=SimpleUploadedFile("mine.pdf", PDF, content_type="application/pdf"),
            recruitment_id=self.rec_a,
        )
        response = self.client.get(
            reverse("application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": own.id},
        )
        self.assertEqual(response.status_code, 200)

    def test_missing_resume_id_is_harmless(self):
        response = self.client.get(
            reverse("application-form"), {"recruitmentId": self.rec_a.id}
        )
        self.assertEqual(response.status_code, 200)
