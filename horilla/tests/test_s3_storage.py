"""The S3 backend needs boto3, which django-storages installs via its S3 extra."""

from django.test import SimpleTestCase


class S3StorageTests(SimpleTestCase):
    def test_backend_uses_configured_bucket(self):
        from storages.backends.s3boto3 import S3Boto3Storage

        storage = S3Boto3Storage(bucket_name="horilla-test")

        self.assertEqual(storage.bucket_name, "horilla-test")
