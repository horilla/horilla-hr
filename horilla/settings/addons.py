"""
Optional integrations (e.g. AWS S3, Cashfree Payouts) layered on top of
base settings.

Imported from horilla.settings.__init__ after base.py. Client overrides belong
in local_settings.py (imported after this module) — do not import them here.
"""

import os

from .base import BASE_DIR, INSTALLED_APPS, MEDIA_ROOT, MEDIA_URL, STORAGES, env

if env("AWS_ACCESS_KEY_ID", default=None):
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="virtual")
    # horilla.horilla_backends.PrivateMediaStorage wraps S3Boto3Storage with
    # default_acl="private" and file_overwrite=False -- the right default
    # for company/employee documents, not raw public S3 defaults. Override
    # via DEFAULT_FILE_STORAGE in .env if a deployment needs something else.
    #
    # Mutated in-place on the STORAGES dict from base.py (Django 5.x's
    # actual mechanism) rather than the legacy DEFAULT_FILE_STORAGE
    # setting, which Django no longer reads at all. DEFAULT_FILE_STORAGE
    # is still set below too, in case any third-party code reads it
    # directly, but it has no effect on Django's own storage resolution.
    STORAGES["default"]["BACKEND"] = env(
        "DEFAULT_FILE_STORAGE", default="horilla.horilla_backends.PrivateMediaStorage"
    )
    DEFAULT_FILE_STORAGE = STORAGES["default"]["BACKEND"]

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" not in INSTALLED_APPS:
    INSTALLED_APPS.append("storages")

if env("AWS_ACCESS_KEY_ID", default=None) and "storages" in INSTALLED_APPS:
    # Defaulted (not required) so enabling S3 doesn't hard-crash at
    # startup on a missing env var -- MEDIA_URL/MEDIA_ROOT are mostly
    # vestigial once S3Boto3Storage is generating URLs itself, NAMESPACE
    # just needs to match the app's existing convention
    # (horilla/horilla_backends.py's own default).
    namespace = env("NAMESPACE", default="private")
    MEDIA_URL = f"{env('MEDIA_URL', default=MEDIA_URL)}/{namespace}/"
    MEDIA_ROOT = f"{env('MEDIA_ROOT', default=MEDIA_ROOT)}/{namespace}/"

# Cashfree Payouts V2 + Bank Account Verification
# (company_onboarding's bank verification / penny drop -- see
# company_onboarding/services/cashfree_client.py). CASHFREE_ENV picks the
# base URL: "sandbox" (default, test-mode, no real money moves) or
# "production" (real transfers).
if env("CASHFREE_CLIENT_ID", default=None):
    CASHFREE_CLIENT_ID = env("CASHFREE_CLIENT_ID")
    CASHFREE_CLIENT_SECRET = env("CASHFREE_CLIENT_SECRET")
    CASHFREE_ENV = env("CASHFREE_ENV", default="sandbox")
    # Cashfree issues separate credentials per product -- only set these
    # if Verification Suite has its own distinct client id/secret from
    # Payouts; otherwise cashfree_client.py falls back to the Payouts ones.
    if env("CASHFREE_VERIFICATION_CLIENT_ID", default=None):
        CASHFREE_VERIFICATION_CLIENT_ID = env("CASHFREE_VERIFICATION_CLIENT_ID")
        CASHFREE_VERIFICATION_CLIENT_SECRET = env("CASHFREE_VERIFICATION_CLIENT_SECRET")
    # Only needed for accounts with signature-based request security
    # enabled (Cashfree returns "x-cf-signature missing" if yours needs
    # this and it isn't set) -- path to the RSA public key .pem file
    # Cashfree issues for this. See cashfree_client._generate_signature().
    #
    # Project-relative, not tied to any one machine's absolute filesystem
    # path: a bare relative value (the default, and the recommended way
    # to set this in .env) is resolved against BASE_DIR, so it works the
    # same for every clone of this repo. An absolute path still works too
    # if a deployment genuinely needs the key stored somewhere else.
    _cashfree_key_path = env(
        "CASHFREE_SIGNATURE_PUBLIC_KEY_PATH",
        default="company_onboarding/keys/cashfree_signature_public_key.pem",
    )
    if _cashfree_key_path:
        CASHFREE_SIGNATURE_PUBLIC_KEY_PATH = (
            _cashfree_key_path
            if os.path.isabs(_cashfree_key_path)
            else str(BASE_DIR / _cashfree_key_path)
        )
