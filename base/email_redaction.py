"""
Keep credentials out of EmailLog, and stamp each row with its company.

``ConfiguredEmailBackend.send_messages`` logs every outbound mail body to
``EmailLog``. Two problems with that:

* ``send_otp`` puts the literal two-factor code in the body, and the
  password-reset mails carry single-use reset links. Both were being written to
  a database table in cleartext, where anyone who could read the mail log could
  replay them.
* ``EmailLog`` has a ``company_id`` FK but nothing ever populated it, so every
  row was NULL and the readers -- which filter only on recipient address -- would
  happily show one tenant's mail to another.
"""

from __future__ import annotations

import re

REDACTED = "[redacted: credential omitted from mail log]"

# Matched against the subject, case-insensitively. A mail whose subject says it
# carries a credential has its body dropped wholesale rather than pattern-matched
# out: partial redaction of an unknown template is how secrets survive.
_CREDENTIAL_SUBJECTS = (
    "otp",
    "one time password",
    "one-time password",
    "verification code",
    "password reset",
    "reset your password",
    "set your password",
    "temporary password",
)

# Belt and braces for bodies whose subject gave nothing away. Deliberately
# narrow -- these run on every outbound mail.
_INLINE_PATTERNS = (
    # "Your OTP code is 123456", "code: 8891"
    re.compile(r"(code\s*(?:is|:)\s*)([A-Za-z0-9\-]{4,})", re.IGNORECASE),
    # Django's reset links: /reset/<uidb64>/<token>/
    re.compile(r"(/reset/)([^/\s]+/[^/\s]+)", re.IGNORECASE),
    re.compile(r"(token\s*(?:is|=|:)\s*)(\S+)", re.IGNORECASE),
)


def redact_credential_body(subject: str, body: str) -> str:
    """Return a body safe to persist in ``EmailLog``."""
    subject_text = (subject or "").lower()
    if any(marker in subject_text for marker in _CREDENTIAL_SUBJECTS):
        return REDACTED

    result = body or ""
    for pattern in _INLINE_PATTERNS:
        result = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", result)
    return result


def get_current_company():
    """
    The ``Company`` for the request in flight, or None outside one.

    Mail sent from a management command or a scheduled job has no request, and
    NULL is the honest answer there -- better than guessing a tenant.
    """
    from base.models import Company
    from horilla.horilla_middlewares import get_selected_company

    company_id = get_selected_company()
    if not company_id or company_id == "all":
        return None
    return Company.objects.filter(id=company_id).first()
