"""
filters.py

The subset of the SCIM filter grammar (RFC 7644 §3.4.2.2) that IdPs send
when provisioning: one ``eq`` comparison on a user identifier. Okta, Entra
ID, OneLogin and JumpCloud all look users up this way before creating them.
Anything richer is rejected with ``invalidFilter`` rather than half-parsed.
"""

import re

from .errors import ScimError

_EQ = re.compile(
    r'^\s*(?P<attr>[A-Za-z0-9_.:\[\]" ]+?)\s+eq\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*$',
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
    if "\x00" in (expression or ""):
        # PostgreSQL refuses NUL in a query parameter (ValueError, a 500).
        raise ScimError(
            400, "invalidFilter", "Filters must not contain NUL characters."
        )
    match = _EQ.match(expression or "")
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
