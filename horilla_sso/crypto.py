"""Encryption of the Microsoft client secret at rest."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    )
    return Fernet(key)


def encrypt(value):
    """Encrypt a secret for storage; an empty value stays empty."""
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token):
    """The secret behind a stored token, or an empty string if it cannot be read."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
