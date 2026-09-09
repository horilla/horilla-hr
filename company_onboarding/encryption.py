"""
company_onboarding/encryption.py

Symmetric field-level encryption for sensitive data at rest (bank account
numbers). The key is derived deterministically from SECRET_KEY via SHA-256
rather than requiring a separate managed secret -- anyone who can read
settings already has DB access implications in this project's threat
model, so this adds no new key-management burden while still meaning a
raw DB dump/leak doesn't hand over plaintext account numbers.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """Encrypts a plaintext string. Falsy values pass through unchanged."""
    if not value:
        return value
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    """
    Decrypts a ciphertext string. Falsy values pass through unchanged. A
    value that isn't valid Fernet ciphertext (e.g. a pre-encryption
    plaintext row that hasn't been re-saved yet) is returned as-is rather
    than raising, so old rows still render instead of crashing the page.
    """
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        return value


def mask_value(value: str, visible: int = 4) -> str:
    """Masks all but the last `visible` characters with 'X'."""
    if not value:
        return ""
    if len(value) <= visible:
        return value
    return ("X" * (len(value) - visible)) + value[-visible:]
