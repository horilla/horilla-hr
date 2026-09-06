"""
Optional integrations (e.g. AWS S3) layered on top of base settings.

Imported from horilla.settings.__init__ after base.py. Client overrides belong
in local_settings.py (imported after this module) — do not import them here.
"""

from .base import INSTALLED_APPS, MEDIA_ROOT, MEDIA_URL, STORAGES, env

if env("AWS_ACCESS_KEY_ID", default=None):
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")
    # DEFAULT_FILE_STORAGE was removed in Django 5.1 and this project pins
    # 5.2, so setting it alone is silently ignored -- uploads kept going to
    # local disk while the bucket stayed empty. STORAGES["default"] is the
    # replacement and is what FileField actually reads.
    _default_storage_backend = env("DEFAULT_FILE_STORAGE")
    DEFAULT_FILE_STORAGE = _default_storage_backend
    STORAGES = {
        **STORAGES,
        "default": {"BACKEND": _default_storage_backend},
    }
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE")

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" not in INSTALLED_APPS:
    INSTALLED_APPS.append("storages")

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" in INSTALLED_APPS:
    MEDIA_URL = f"{env('MEDIA_URL')}/{env('NAMESPACE')}/"
    MEDIA_ROOT = f"{env('MEDIA_ROOT')}/{env('NAMESPACE')}/"
