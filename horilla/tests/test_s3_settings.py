"""Guard media storage configuration for AWS and S3-compatible services.

Horilla previously ignored custom S3 endpoints and required AWS region and
media path settings that a minimal MinIO configuration does not need.
"""

import importlib.util
import os
from unittest.mock import patch

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.test import SimpleTestCase, override_settings
from storages.backends.s3 import S3Storage

from horilla.settings import base


class S3SettingsTests(SimpleTestCase):
    minio = {
        "AWS_ACCESS_KEY_ID": "minio-access-key",
        "AWS_SECRET_ACCESS_KEY": "minio-secret-key",
        "AWS_STORAGE_BUCKET_NAME": "horilla-media",
        "AWS_S3_ENDPOINT_URL": "http://minio:9000",
        "DEFAULT_FILE_STORAGE": "storages.backends.s3boto3.S3Boto3Storage",
        "AWS_S3_ADDRESSING_STYLE": "path",
    }

    def load_addons(self, **environment):
        # Execute in a fresh namespace without reloading the live settings.
        spec = importlib.util.find_spec("horilla.settings.addons")
        addons = importlib.util.module_from_spec(spec)
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(base, "INSTALLED_APPS", base.INSTALLED_APPS.copy()),
        ):
            spec.loader.exec_module(addons)
        return addons

    def storage_settings(self, addons):
        # Mask any S3 values already loaded from the developer's environment.
        names = (*self.minio, "AWS_S3_REGION_NAME")
        return override_settings(
            **{name: getattr(addons, name, None) for name in names},
            STORAGES=addons.STORAGES,
            MEDIA_URL=addons.MEDIA_URL,
            MEDIA_ROOT=addons.MEDIA_ROOT,
        )

    def test_aws_settings_are_preserved(self):
        aws = {
            **self.minio,
            "AWS_ACCESS_KEY_ID": "aws-access-key",
            "AWS_SECRET_ACCESS_KEY": "aws-secret-key",
            "AWS_STORAGE_BUCKET_NAME": "aws-media",
            "AWS_S3_REGION_NAME": "us-west-2",
            "AWS_S3_ADDRESSING_STYLE": "virtual",
            "MEDIA_URL": "/uploads",
            "MEDIA_ROOT": "/srv/uploads",
            "NAMESPACE": "private",
        }
        del aws["AWS_S3_ENDPOINT_URL"]
        for endpoint in ({}, {"AWS_S3_ENDPOINT_URL": ""}):
            with self.subTest(endpoint=endpoint):
                addons = self.load_addons(**aws, **endpoint)
                with self.storage_settings(addons):
                    self.assertIsInstance(default_storage, S3Storage)
                    self.assertIsNone(default_storage.endpoint_url)
                    self.assertEqual(default_storage.region_name, "us-west-2")
                    self.assertEqual(default_storage.addressing_style, "virtual")
                    self.assertEqual(default_storage.bucket_name, "aws-media")
                    self.assertEqual(default_storage.access_key, "aws-access-key")
                    self.assertEqual(default_storage.secret_key, "aws-secret-key")
                    self.assertEqual(
                        settings.STORAGES["default"]["BACKEND"],
                        aws["DEFAULT_FILE_STORAGE"],
                    )
                    self.assertEqual(
                        settings.DEFAULT_FILE_STORAGE, aws["DEFAULT_FILE_STORAGE"]
                    )
                    self.assertEqual(
                        settings.STORAGES["staticfiles"], base.STORAGES["staticfiles"]
                    )
                    self.assertEqual(settings.MEDIA_URL, "/uploads/private/")
                    self.assertEqual(settings.MEDIA_ROOT, "/srv/uploads/private/")

    def test_endpoint_preserves_configured_region_and_media_paths(self):
        addons = self.load_addons(
            **self.minio,
            AWS_S3_REGION_NAME="eu-west-1",
            MEDIA_URL="/uploads/",
            MEDIA_ROOT="/srv/uploads",
            NAMESPACE="private",
        )
        with self.storage_settings(addons):
            self.assertIsInstance(default_storage, S3Storage)
            self.assertEqual(
                default_storage.endpoint_url, self.minio["AWS_S3_ENDPOINT_URL"]
            )
            self.assertEqual(default_storage.addressing_style, "path")
            self.assertEqual(default_storage.region_name, "eu-west-1")
            self.assertEqual(settings.MEDIA_URL, "/uploads/private/")
            self.assertEqual(settings.MEDIA_ROOT, "/srv/uploads/private/")

    def test_minio_works_with_only_the_documented_variables(self):
        addons = self.load_addons(**self.minio)
        with self.storage_settings(addons):
            self.assertIsInstance(default_storage, S3Storage)
            self.assertEqual(
                default_storage.endpoint_url, self.minio["AWS_S3_ENDPOINT_URL"]
            )
            self.assertEqual(default_storage.addressing_style, "path")
            self.assertIsNone(default_storage.region_name)
            self.assertEqual(settings.MEDIA_URL, base.MEDIA_URL)
            self.assertEqual(settings.MEDIA_ROOT, base.MEDIA_ROOT)

    def test_endpoint_without_access_key_keeps_local_storage(self):
        addons = self.load_addons(AWS_S3_ENDPOINT_URL=self.minio["AWS_S3_ENDPOINT_URL"])
        with self.storage_settings(addons):
            self.assertIsInstance(default_storage, FileSystemStorage)
            self.assertEqual(settings.MEDIA_URL, base.MEDIA_URL)
