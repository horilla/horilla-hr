"""Candidate stage progression deepen tests."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from base.models import Department, JobPosition
from horilla.testkit import make_company
from recruitment.models import Candidate, Recruitment, RejectedCandidate, Stage


class CandidateStageProgressionTests(TestCase):
    def setUp(self):
        company = make_company("Rec Pipeline Co")
        dept = Department.objects.create(department="Engineering Unit")
        dept.company_id.add(company)
        self.jp = JobPosition.objects.create(
            job_position="Backend Dev", department_id=dept
        )
        self.rec = Recruitment.objects.create(
            title="Backend Hire Unit",
            description="Smoke pipeline",
            company_id=company,
            job_position_id=self.jp,
            vacancy=2,
            is_published=True,
            optional_resume=True,
            optional_profile_image=True,
        )
        self.rec.open_positions.add(self.jp)
        # Recruitment post_save seeds Applied + Initial stages.
        self.applied = Stage.objects.get(recruitment_id=self.rec, stage_type="applied")
        self.hired, _ = Stage.objects.get_or_create(
            recruitment_id=self.rec,
            stage="Hired",
            defaults={"stage_type": "hired", "sequence": 10},
        )

    def _pdf(self, name="resume.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4\n%", content_type="application/pdf")

    def _make_candidate(self, stage):
        return Candidate.objects.create(
            name="Pat Candidate",
            email="pat.candidate@test.horilla",
            mobile="9998887777",
            recruitment_id=self.rec,
            job_position_id=self.jp,
            stage_id=stage,
            resume=self._pdf(),
        )

    def test_candidate_save_sets_hired_flag(self):
        cand = self._make_candidate(self.applied)
        self.assertFalse(cand.hired)
        cand.stage_id = self.hired
        cand.resume = self._pdf("resume2.pdf")
        cand.save()
        cand.refresh_from_db()
        self.assertTrue(cand.hired)

    def test_candidate_in_the_cancelled_stage_is_flagged_canceled(self):
        cancelled = Stage.objects.create(
            recruitment_id=self.rec,
            stage="Rejected Candidates",
            stage_type="cancelled",
            sequence=50,
        )
        cand = self._make_candidate(self.applied)
        self.assertFalse(cand.canceled)
        cand.stage_id = cancelled
        cand.resume = self._pdf("resume3.pdf")
        cand.save()
        cand.refresh_from_db()
        self.assertTrue(cand.canceled)

    def test_rejecting_a_candidate_moves_them_to_the_rejected_stage(self):
        cand = self._make_candidate(self.applied)
        RejectedCandidate.objects.create(candidate_id=cand, description="Not a fit")
        cand.refresh_from_db()
        self.assertEqual(cand.stage_id.stage_type, "cancelled")
        self.assertTrue(cand.canceled)
