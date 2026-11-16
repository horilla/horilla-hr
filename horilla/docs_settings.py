"""Settings of the documentation environment (the sample company of the user guide).

Use with the sample company only:

    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py migrate
    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py seed_docs_sample --flush --noinput
    DJANGO_SETTINGS_MODULE=horilla.docs_settings python manage.py runserver

It is the normal settings with the modules that are not released yet left out, so
that no screenshot or page of the guide shows them. Remove a name from
UNRELEASED_APPS when the module is released and its chapter is written.
"""

from horilla.settings import *  # noqa: F401,F403
from horilla.settings import INSTALLED_APPS as _INSTALLED_APPS
from horilla.settings import SIDEBARS as _SIDEBARS

UNRELEASED_APPS = ["surveys"]

INSTALLED_APPS = [app for app in _INSTALLED_APPS if app not in UNRELEASED_APPS]
SIDEBARS = [app for app in _SIDEBARS if app not in UNRELEASED_APPS]
