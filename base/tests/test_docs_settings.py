"""The documentation environment is the normal one minus the unreleased modules."""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CODE = (
    "import django, json; django.setup(); from django.apps import apps; "
    "from django.conf import settings as s; "
    "print('RESULT' + json.dumps({'apps': [a.label for a in apps.get_app_configs()], "
    "'sidebars': list(s.SIDEBARS)}))"
)


def installed(settings_module):
    env = dict(os.environ, DJANGO_SETTINGS_MODULE=settings_module)
    out = subprocess.run(
        [sys.executable, "-c", CODE],
        cwd=Path(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    line = next(l for l in out.stdout.splitlines() if l.startswith("RESULT"))
    return json.loads(line[len("RESULT") :])


class DocsSettingsTests(SimpleTestCase):
    def test_docs_environment_is_the_normal_one_minus_the_unreleased_modules(self):
        normal = installed("horilla.settings")
        docs = installed("horilla.docs_settings")
        self.assertIn("surveys", normal["apps"])
        self.assertEqual([a for a in normal["apps"] if a != "surveys"], docs["apps"])
        self.assertEqual(
            [a for a in normal["sidebars"] if a != "surveys"], docs["sidebars"]
        )

    def test_modules_added_at_load_time_are_still_installed(self):
        docs = installed("horilla.docs_settings")
        # horilla_api adds these two to the settings list while it loads
        for label in ("geofencing", "facedetection"):
            self.assertIn(label, docs["apps"])
