"""Model-level field validators must run (HorillaModel/Employee.clean_fields call super)."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from recruitment.models import Candidate

ONLY_RESUME = [f.name for f in Candidate._meta.fields if f.name != "resume"]


def _candidate(filename):
    c = Candidate(name="Test", email="t@example.com", mobile="1234567890")
    c.resume = SimpleUploadedFile(filename, b"x")
    return c


class ResumeFileTypeTests(SimpleTestCase):
    def test_non_pdf_resume_is_rejected(self):
        for name in ("cv.html", "cv.exe", "cv.docm"):
            with self.assertRaises(ValidationError) as ctx:
                _candidate(name).clean_fields(exclude=ONLY_RESUME)
            self.assertIn("resume", ctx.exception.message_dict, name)

    def test_pdf_resume_is_accepted(self):
        _candidate("cv.pdf").clean_fields(exclude=ONLY_RESUME)

    def test_xss_check_still_runs_alongside_validators(self):
        c = _candidate("cv.html")
        c.name = "<script>alert(1)</script>"
        with self.assertRaises(ValidationError) as ctx:
            c.clean_fields(exclude=[f for f in ONLY_RESUME if f != "name"])
        self.assertEqual({"name", "resume"}, set(ctx.exception.message_dict))
