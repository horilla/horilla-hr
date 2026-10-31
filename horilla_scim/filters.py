"""
filters.py

The subset of the SCIM filter grammar (RFC 7644 §3.4.2.2) that IdPs send
when provisioning: one ``eq`` comparison on a user identifier. Okta, Entra
ID, OneLogin and JumpCloud all look users up this way before creating them.
Anything richer is rejected with ``invalidFilter`` rather than half-parsed.
"""

import re

from .errors import ScimError

# Bounds the work the regular expressions below can do on hostile input.
MAX_FILTER_LENGTH = 512

# Attribute segments contain no whitespace and are joined by a single
# whitespace character, so they can't compete with the separators around
# ``eq`` for the same spaces (which made matching quadratic).
_EQ = re.compile(
    r'^(?P<attr>[A-Za-z0-9_.:\[\]"]+(?:\s[A-Za-z0-9_.:\[\]"]+)*?)'
    r'\s+eq\s+"(?P<value>(?:[^"\\]|\\.)*)"$',
    re.IGNORECASE,
)

# Normalised attribute path -> ExternalIdentity lookup.
_LOOKUPS = {
    "id": "subject",
    "externalid": "external_id",
    "username": "user__username__iexact",
    "emails.value": "user__employee_get__email__iexact",
    'emails[type eq "work"].value': "user__employee_get__email__iexact",
}


def parse_filter(expression):
    """Return a ``{lookup: value}`` dict for ``ExternalIdentity.objects.filter``."""
    expression = expression or ""
    if len(expression) > MAX_FILTER_LENGTH:
        raise ScimError(
            400,
            "invalidFilter",
            f"Filters must be at most {MAX_FILTER_LENGTH} characters.",
        )
    expression = expression.strip()
    if "\x00" in expression:
        # PostgreSQL refuses NUL in a query parameter (ValueError, a 500).
        raise ScimError(
            400, "invalidFilter", "Filters must not contain NUL characters."
        )
    match = _EQ.match(expression)
    if not match:
        raise ScimError(
            400, "invalidFilter", "Only 'attribute eq \"value\"' filters are supported."
        )
    attr = match.group("attr").strip()
    # Accept the attribute qualified with the core schema URN.
    prefix = "urn:ietf:params:scim:schemas:core:2.0:user:"
    if attr.lower().startswith(prefix):
        attr = attr[len(prefix) :]
    lookup = _LOOKUPS.get(re.sub(r"\s+", " ", attr.lower()))
    if lookup is None:
        raise ScimError(
            400, "invalidFilter", f"Filtering on '{attr}' is not supported."
        )
    value = re.sub(r"\\(.)", r"\1", match.group("value"))
    return {lookup: value}
