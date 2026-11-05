"""
Resume has no company_id of its own, so the recruitment is what scopes it.

The resume shortlisting form reads a resume by id from the query string and
attaches that file to the submitted application. Unscoped, that let anyone walk
sequential ids and harvest every CV in the database, across companies. The
public application form must never look at a resume at all.
"""

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from base.models import Department, JobPosition
from horilla.testkit import make_company, make_employee, make_user
from recruitment.models import Candidate, Recruitment, Resume

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
    return rec, jp, company


class ResumeApplicationFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rec_a, cls.jp_a, company_a = _recruitment(
            "Alpha Corp", "Alpha Hire", "Alpha Dev"
        )
        cls.rec_b, _, _ = _recruitment("Beta Corp", "Beta Hire", "Beta Dev")
        cls.resume_b = Resume.objects.create(
            file=SimpleUploadedFile("victim.pdf", PDF, content_type="application/pdf"),
            recruitment_id=cls.rec_b,
        )
        cls.own = Resume.objects.create(
            file=SimpleUploadedFile("mine.pdf", PDF, content_type="application/pdf"),
            recruitment_id=cls.rec_a,
        )
        cls.plain_user = make_user("rs_plain", password="secret123")
        make_employee(
            company=company_a, email="rs_plain@test.horilla", user=cls.plain_user
        )
        cls.hr_user = make_user("rs_hr", password="secret123")
        make_employee(company=company_a, email="rs_hr@test.horilla", user=cls.hr_user)
        cls.hr_user.user_permissions.add(
            Permission.objects.get(codename="add_candidate")
        )

    def _hr_client(self):
        client = Client()
        client.force_login(type(self.hr_user).objects.get(pk=self.hr_user.pk))
        return client

    def _payload(self):
        return {
            "name": "Shortlisted Person",
            "email": "shortlisted@example.com",
            "mobile": "9745281083",
            "recruitment_id": self.rec_a.id,
            "job_position_id": self.jp_a.id,
        }

    def test_public_form_ignores_a_resume_id(self):
        response = Client().get(
            reverse("application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.own.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context.get("resume"))
        self.assertNotIn(self.own.file.name.encode(), response.content)

    def test_resume_form_requires_login(self):
        response = Client().get(
            reverse("resume-application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.own.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_resume_form_requires_the_permission(self):
        client = Client()
        client.force_login(type(self.plain_user).objects.get(pk=self.plain_user.pk))
        response = client.get(
            reverse("resume-application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.own.id},
        )
        self.assertNotEqual(response.status_code, 200)

    def test_resume_from_another_recruitment_is_refused(self):
        response = self._hr_client().get(
            reverse("resume-application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.resume_b.id},
        )
        self.assertRedirects(
            response, reverse("cbv-pipeline"), fetch_redirect_response=False
        )

    def test_resume_from_the_same_recruitment_resolves(self):
        response = self._hr_client().get(
            reverse("resume-application-form"),
            {"recruitmentId": self.rec_a.id, "resumeId": self.own.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["resume"], self.own)

    def test_garbage_ids_are_harmless(self):
        response = self._hr_client().get(
            reverse("resume-application-form"),
            {"recruitmentId": "abc", "resumeId": "xyz"},
        )
        self.assertRedirects(
            response, reverse("cbv-pipeline"), fetch_redirect_response=False
        )

    def test_shortlisted_post_needs_only_the_core_fields(self):
        url = (
            f"{reverse('resume-application-form')}"
            f"?recruitmentId={self.rec_a.id}&resumeId={self.own.id}"
        )
        client = self._hr_client()
        response = client.post(url, self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "candidate/success.html")
        self.assertTrue(response.context["shortlisted"])
        self.assertIn(b"resume-candidate-created", response.content)
        self.assertNotIn(b"oh-alert-container", response.content)
        reloaded = client.get(reverse("reload-messages"), HTTP_HX_REQUEST="true")
        self.assertIn(b"Candidate created from resume.", reloaded.content)
        candidate = Candidate.objects.get(email="shortlisted@example.com")
        self.assertTrue(candidate.resume)
        self.assertEqual(candidate.referral_source, "resume_shortlisting")
        self.own.refresh_from_db()
        self.assertTrue(self.own.is_candidate)

    def test_shortlisted_post_keeps_a_source_the_recruiter_picked(self):
        url = (
            f"{reverse('resume-application-form')}"
            f"?recruitmentId={self.rec_a.id}&resumeId={self.own.id}"
        )
        self._hr_client().post(url, {**self._payload(), "referral_source": "job_board"})
        candidate = Candidate.objects.get(email="shortlisted@example.com")
        self.assertEqual(candidate.referral_source, "job_board")

    def test_shortlisted_post_requires_a_phone_number(self):
        url = (
            f"{reverse('resume-application-form')}"
            f"?recruitmentId={self.rec_a.id}&resumeId={self.own.id}"
        )
        response = self._hr_client().post(url, {**self._payload(), "mobile": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Candidate.objects.filter(email="shortlisted@example.com").exists()
        )

    def test_public_form_does_not_offer_the_shortlisting_source(self):
        response = Client().get(
            reverse("application-form"), {"recruitmentId": self.rec_a.id}
        )
        self.assertNotIn(b"resume_shortlisting", response.content)

    def test_public_post_still_requires_the_referral_source(self):
        response = Client().post(
            f"{reverse('application-form')}?recruitmentId={self.rec_a.id}",
            self._payload(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Candidate.objects.filter(email="shortlisted@example.com").exists()
        )
