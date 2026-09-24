"""
crypto.py

Symmetric encryption for OidcProvider.client_secret.

horilla_ldap.LDAPSettings.bind_password ships as a plain CharField in this
codebase today -- cleartext in the database. client_secret is a materially
worse thing to leave that way: it is the credential that lets someone
impersonate the login of any employee an IdP vouches for, not a single
service-account bind password. cryptography is already a direct dependency
(requirements.txt), so this costs nothing new to add.

ponytail: the Fernet key is derived from SECRET_KEY rather than a dedicated,
independently-rotatable key. That means rotating SECRET_KEY would silently
break decryption of every stored client_secret. Upgrade to a separate
OIDC_ENCRYPTION_KEY env var if key rotation without invalidating existing
OIDC configs becomes a real requirement.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Raises cryptography.fernet.InvalidToken if the value is not one we encrypted
    (e.g. SECRET_KEY changed, or the DB column somehow holds plaintext)."""
    return _fernet().decrypt(token.encode()).decode()


__all__ = ["encrypt", "decrypt", "InvalidToken"]
