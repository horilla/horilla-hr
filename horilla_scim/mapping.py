"""
mapping.py

Translation between a SCIM User document and Horilla employee attributes.

SCIM attribute names are case-insensitive (RFC 7643 §2.1) and IdPs differ in
how they send booleans (Entra ID sends "False" as a string in PATCH), so every
read goes through ``get_ci`` / ``to_bool``.
"""

from dataclasses import dataclass, field

from .errors import ScimError
from .schemas import CORE_USER, ENTERPRISE_USER

UNSET = object()


def get_ci(mapping, name, default=None):
    """Case-insensitive dict lookup."""
    if not isinstance(mapping, dict):
        return default
    if name in mapping:
        return mapping[name]
    lowered = name.lower()
    for key, value in mapping.items():
        if isinstance(key, str) and key.lower() == lowered:
            return value
    return default


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ScimError(400, "invalidValue", "'active' must be a boolean.")


def _pick(values, preferred_type=None):
    """The primary entry of a multi-valued attribute, else the preferred type,
    else the first one."""
    if not isinstance(values, list) or not values:
        return None
    entries = [v for v in values if isinstance(v, dict)]
    for entry in entries:
        if get_ci(entry, "primary") in (True, "true", "True"):
            return entry
    if preferred_type:
        for entry in entries:
            if str(get_ci(entry, "type", "")).lower() == preferred_type:
                return entry
    return entries[0] if entries else None


@dataclass
class UserAttributes:
    """Parsed SCIM user. ``UNSET`` means the document did not carry it."""

    user_name: object = UNSET
    external_id: object = UNSET
    given_name: object = UNSET
    family_name: object = UNSET
    display_name: object = UNSET
    email: object = UNSET
    phone: object = UNSET
    active: object = UNSET
    title: object = UNSET
    employee_number: object = UNSET
    department: object = UNSET
    manager_id: object = UNSET
    extra: dict = field(default_factory=dict)

    def first_name(self):
        if self.given_name not in (UNSET, None, ""):
            return self.given_name
        if self.display_name not in (UNSET, None, ""):
            return str(self.display_name).split(" ")[0]
        if self.user_name not in (UNSET, None, ""):
            return str(self.user_name).split("@")[0]
        return None


def parse_user(doc):
    if not isinstance(doc, dict):
        raise ScimError(400, "invalidSyntax", "Request body must be a JSON object.")
    attrs = UserAttributes()

    def _str(key, source=doc):
        value = get_ci(source, key, UNSET)
        if value is UNSET or value is None:
            return value
        if not isinstance(value, (str, int)):
            raise ScimError(400, "invalidValue", f"'{key}' must be a string.")
        return str(value).strip()

    attrs.user_name = _str("userName")
    attrs.external_id = _str("externalId")
    attrs.display_name = _str("displayName")
    attrs.title = _str("title")

    name = get_ci(doc, "name", UNSET)
    if isinstance(name, dict):
        attrs.given_name = _str("givenName", name)
        attrs.family_name = _str("familyName", name)

    emails = get_ci(doc, "emails", UNSET)
    if emails is not UNSET:
        entry = _pick(emails, "work")
        attrs.email = (
            (str(get_ci(entry, "value", "")).strip() or None) if entry else None
        )

    phones = get_ci(doc, "phoneNumbers", UNSET)
    if phones is not UNSET:
        entry = _pick(phones, "work")
        attrs.phone = (str(get_ci(entry, "value", "")).strip() or "") if entry else ""

    active = get_ci(doc, "active", UNSET)
    if active is not UNSET and active is not None:
        attrs.active = to_bool(active)

    enterprise = get_ci(doc, ENTERPRISE_USER, UNSET)
    if isinstance(enterprise, dict):
        attrs.employee_number = _str("employeeNumber", enterprise)
        attrs.department = _str("department", enterprise)
        manager = get_ci(enterprise, "manager", UNSET)
        if isinstance(manager, dict):
            attrs.manager_id = _str("value", manager)
        elif manager is None or isinstance(manager, str):
            # Some IdPs send the manager id directly, or null to clear it.
            attrs.manager_id = manager
    return attrs


def to_scim(identity, employee, location):
    user = employee.employee_user_id
    work_info = getattr(employee, "employee_work_info", None)
    full_name = " ".join(
        part
        for part in [employee.employee_first_name, employee.employee_last_name]
        if part
    )
    doc = {
        "schemas": [CORE_USER, ENTERPRISE_USER],
        "id": identity.subject,
        "userName": user.username,
        "name": {
            "givenName": employee.employee_first_name,
            "familyName": employee.employee_last_name or "",
            "formatted": full_name,
        },
        "displayName": full_name,
        "emails": [{"value": employee.email, "type": "work", "primary": True}],
        "active": bool(user.is_active),
        "meta": {
            "resourceType": "User",
            "created": identity.created_at.isoformat(),
            "lastModified": identity.updated_at.isoformat(),
            "location": location,
        },
    }
    if identity.external_id:
        doc["externalId"] = identity.external_id
    if employee.phone:
        doc["phoneNumbers"] = [
            {"value": employee.phone, "type": "work", "primary": True}
        ]

    enterprise = {}
    if employee.badge_id:
        enterprise["employeeNumber"] = employee.badge_id
    if work_info is not None:
        if work_info.job_position_id_id:
            doc["title"] = work_info.job_position_id.job_position
        if work_info.department_id_id:
            enterprise["department"] = work_info.department_id.department
        manager = work_info.reporting_manager_id
        if manager is not None and manager.employee_user_id_id:
            manager_identity = identity.__class__.objects.filter(
                source=identity.source,
                provider_id=identity.provider_id,
                user_id=manager.employee_user_id_id,
                unlinked_at__isnull=True,
            ).first()
            if manager_identity is not None:
                enterprise["manager"] = {"value": manager_identity.subject}
    doc[ENTERPRISE_USER] = enterprise
    return doc
