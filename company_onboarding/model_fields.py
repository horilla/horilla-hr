"""
company_onboarding/model_fields.py
"""

from django.db import models

from company_onboarding.encryption import decrypt_value, encrypt_value


class EncryptedCharField(models.CharField):
    """
    Transparently encrypts on write, decrypts on read. Ciphertext is
    significantly longer than the plaintext it holds (Fernet's fixed
    overhead + base64 encoding), so `max_length` here governs DB column
    width, not the real user-facing input limit -- pass `plain_max_length`
    for the limit actually enforced on forms.
    """

    def __init__(self, *args, plain_max_length=100, **kwargs):
        self.plain_max_length = plain_max_length
        kwargs.setdefault("max_length", 500)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["plain_max_length"] = self.plain_max_length
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_value(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt_value(value)

    def formfield(self, **kwargs):
        defaults = {"max_length": self.plain_max_length}
        defaults.update(kwargs)
        return super().formfield(**defaults)
