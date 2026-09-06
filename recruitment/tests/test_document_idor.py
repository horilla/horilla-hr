"""Documents must be scoped to their owner, not resolved by id alone.

GHSA-p745-9729-g8jw: `candidate_login_required` only asserts that *some*
candidate is logged in -- it checks `"candidate_id" in request.session` and
nothing more. Views that then did `CandidateDocument.objects.filter(id=id)`
served any candidate's file to any other, and the ids are sequential, so one
self-registered account could harvest every applicant's resume and identity
documents.

The employee side had the same shape under plain `@login_required`, and the
candidate `file_upload` view was worse than the reported read: it bound a
`CandidateDocumentUpdateForm` to whatever id was supplied, so a candidate
could write into someone else's document record.

Recruiters and HR keep access through the model permission; these tests pin
both halves, because a fix that only denies is as broken as one that only
allows.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase

from base.models import Company, Department, JobPosition
from employee.models import Employee
from horilla_auth.models import HorillaUser
from recruitment.models import Candidate, CandidateDocument, Recruitment
from recruitment.views.views import candidate_documents_visible_to


class _Request:
    """Minimal stand-in: the helper reads only .user and .session."""

    def __init__(self, user, session=None):
        self.user = user
        self.session = session or {}


class CandidateDocumentScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(company="Acme", hq=True)
        department = Department.objects.create(department="Engineering")
        job_position = JobPosition.objects.create(
            job_position="Engineer", department_id=department
        )
        recruitment = Recruitment.objects.create(
            title="Engineer", closed=False, is_active=True
        )
        recruitment.open_positions.add(job_position)

        # Candidate.clean() rejects a job_position_id that is not among the
        # recruitment's open positions, so both must be wired up.
        cls.victim = cls._candidate(
            "Victim", "victim@example.com", "1000000000", recruitment, job_position
        )
        cls.attacker = cls._candidate(
            "Attacker",
            "attacker@example.com",
            "2000000000",
            recruitment,
            job_position,
        )
        cls.victim_doc = CandidateDocument.objects.create(
            title="Passport", candidate_id=cls.victim
        )
        cls.attacker_doc = CandidateDocument.objects.create(
            title="Resume", candidate_id=cls.attacker
        )

    @staticmethod
    def _candidate(name, email, mobile, recruitment, job_position):
        """resume is a required FileField, so it needs a real (tiny) upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        return Candidate.objects.create(
            name=name,
            email=email,
            mobile=mobile,
            recruitment_id=recruitment,
            job_position_id=job_position,
            resume=SimpleUploadedFile(f"{name}.pdf", b"%PDF-1.4 test"),
        )

    def _anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        return AnonymousUser()

    def test_candidate_cannot_reach_another_candidates_document(self):
        """The reported attack: session belongs to attacker, id to victim."""
        request = _Request(self._anonymous(), {"candidate_id": self.attacker.id})
        visible = candidate_documents_visible_to(request)
        self.assertNotIn(self.victim_doc, visible)
        self.assertIsNone(visible.filter(id=self.victim_doc.id).first())

    def test_candidate_can_still_reach_their_own_document(self):
        """A fix that denies everything would also pass the test above."""
        request = _Request(self._anonymous(), {"candidate_id": self.attacker.id})
        self.assertEqual(
            candidate_documents_visible_to(request)
            .filter(id=self.attacker_doc.id)
            .first(),
            self.attacker_doc,
        )

    def test_enumeration_yields_only_own_documents(self):
        """Sequential id scanning is the reported harvesting method."""
        request = _Request(self._anonymous(), {"candidate_id": self.attacker.id})
        visible = candidate_documents_visible_to(request)
        self.assertEqual(list(visible), [self.attacker_doc])

    def test_no_candidate_session_sees_nothing(self):
        """Fails closed rather than falling back to the full queryset."""
        request = _Request(self._anonymous(), {})
        self.assertEqual(list(candidate_documents_visible_to(request)), [])

    def test_recruiter_permission_still_sees_every_document(self):
        """HR must keep working -- this is the half a naive fix breaks."""
        user = HorillaUser.objects.create_user(
            username="recruiter", password="Test-Passw0rd!"
        )
        user.user_permissions.add(
            Permission.objects.get(codename="view_candidatedocument")
        )
        user = HorillaUser.objects.get(pk=user.pk)  # refresh the perm cache

        visible = candidate_documents_visible_to(_Request(user, {}))
        self.assertIn(self.victim_doc, visible)
        self.assertIn(self.attacker_doc, visible)
