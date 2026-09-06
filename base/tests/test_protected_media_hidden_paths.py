"""
protected_media serves any file under MEDIA_ROOT to any authenticated user.
The Docker entrypoint persists the generated SECRET_KEY at
media/.generated_secret_key, so hidden paths must 404 even when logged in.
"""

import os
import tempfile

from django.test import TestCase, override_settings

from base.models import Company
from horilla.testkit import make_employee, make_user


class HiddenMediaPathsTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        with open(os.path.join(self.media_root, ".generated_secret_key"), "w") as fh:
            fh.write("super-secret")
        os.makedirs(os.path.join(self.media_root, ".hidden"))
        with open(os.path.join(self.media_root, ".hidden", "x.txt"), "w") as fh:
            fh.write("hidden")
        with open(os.path.join(self.media_root, "visible.txt"), "w") as fh:
            fh.write("visible")
        company = Company.objects.create(company="Acme", hq=True)
        user = make_user("emp", password="pw-not-real")
        make_employee(company=company, email="emp@test.horilla", user=user)
        self.client.force_login(user)

    def test_dot_paths_are_not_served_even_when_authenticated(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            for path in ("/media/.generated_secret_key", "/media/.hidden/x.txt"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(b"super-secret", response.content)

    def test_regular_upload_still_served(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.get("/media/visible.txt")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"visible")
