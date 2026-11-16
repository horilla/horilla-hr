"""Settings of the documentation environment (the sample company of the user guide).

Use with the sample company only:

    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py migrate
    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py seed_docs_sample --flush --noinput
    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py runserver

It is the normal settings with the modules that are not released yet left out, so
that no screenshot or page of the guide shows them. Remove a name from
UNRELEASED_APPS when the module is released and its chapter is written.

The two lists are changed in place, not copied: horilla_api adds geofencing and
facedetection to the very same INSTALLED_APPS list when it loads, and a copy would
never see them.
"""

from horilla.settings import *  # noqa: F401,F403
from horilla.settings import INSTALLED_APPS, SIDEBARS

UNRELEASED_APPS = ["surveys"]

for _app in UNRELEASED_APPS:
    while _app in INSTALLED_APPS:
        INSTALLED_APPS.remove(_app)
    while _app in SIDEBARS:
        SIDEBARS.remove(_app)
