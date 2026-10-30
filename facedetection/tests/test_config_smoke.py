"""Face detection config smoke tests."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from facedetection.models import FaceDetection
from horilla.testkit import make_company


class FaceDetectionConfigTests(TestCase):
    def test_company_unique(self):
        company = make_company("Face Unique")
        FaceDetection.objects.create(company_id=company, start=False)
        with self.assertRaises(ValidationError):
            FaceDetection.objects.create(company_id=company, start=True)
