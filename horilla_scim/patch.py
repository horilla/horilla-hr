"""
patch.py

Applies a SCIM PatchOp (RFC 7644 §3.5.2) to a User document.

The view renders the current user as a SCIM document, applies the operations
here, and parses the result like a PUT body. That keeps the mapping in one
place (mapping.py) and makes PATCH support every attribute PUT does.

Supported paths are the shapes IdPs send:
  active, userName, name.givenName, title, externalId
  emails[type eq "work"].value, phoneNumbers[type eq "mobile"].value
  urn:...:enterprise:2.0:User:department, ...:manager, ...:manager.value
and path-less operations whose value is a partial document (Okta, Entra).
"""

import copy
import re

from .errors import ScimError
from .mapping import get_ci
from .schemas import CORE_USER, ENTERPRISE_USER, PATCH_OP

_SEGMENT = re.compile(
    r"^(?P<attr>[A-Za-z0-9_$-]+)"
    r'(?:\[\s*(?P<f_attr>[A-Za-z0-9_]+)\s+eq\s+"(?P<f_value>[^"]*)"\s*\])?'
    r"(?:\.(?P<sub>[A-Za-z0-9_$-]+))?$",
    re.IGNORECASE,
)


def _real_key(container, name):
    """Existing key in ``container`` matching ``name`` case-insensitively."""
    for key in container:
        if isinstance(key, str) and key.lower() == name.lower():
            return key
    return name


def _split_path(path):
    """Return (container_key or None, segment) for a path."""
    lowered = path.lower()
    if lowered.startswith(ENTERPRISE_USER.lower() + ":"):
        return ENTERPRISE_USER, path[len(ENTERPRISE_USER) + 1 :]
    if lowered.startswith(CORE_USER.lower() + ":"):
        return None, path[len(CORE_USER) + 1 :]
    return None, path


def _apply_path(doc, op, path, value):
    container_key, segment = _split_path(path)
    target = doc
    if container_key is not None:
        key = _real_key(doc, container_key)
        target = doc.setdefault(key, {})
        if not isinstance(target, dict):
            target = doc[key] = {}

    match = _SEGMENT.match(segment)
    if not match:
        raise ScimError(400, "invalidPath", f"Unsupported path '{path}'.")
    attr, sub = match.group("attr"), match.group("sub")
    f_attr, f_value = match.group("f_attr"), match.group("f_value")
    key = _real_key(target, attr)

    if f_attr:
        items = target.get(key)
        if not isinstance(items, list):
            items = target[key] = []
        matches = [
            item
            for item in items
            if isinstance(item, dict)
            and str(get_ci(item, f_attr, "")).lower() == f_value.lower()
        ]
        if op == "remove":
            if sub:
                for item in matches:
                    item.pop(_real_key(item, sub), None)
            else:
                target[key] = [item for item in items if item not in matches]
            return
        if not matches:
            item = {f_attr: f_value}
            # A value added through a filter becomes the primary one, so it
            # is the entry the mapping reads.
            for other in items:
                if isinstance(other, dict):
                    other.pop(_real_key(other, "primary"), None)
            item["primary"] = True
            items.append(item)
            matches = [item]
        for item in matches:
            if sub:
                item[_real_key(item, sub)] = value
            elif isinstance(value, dict):
                item.update(value)
        return

    if sub:
        parent = target.get(key)
        if op == "remove":
            if isinstance(parent, dict):
                parent.pop(_real_key(parent, sub), None)
            return
        if not isinstance(parent, dict):
            parent = target[key] = {}
        parent[_real_key(parent, sub)] = value
        return

    if op == "remove":
        target.pop(key, None)
    elif op == "add" and isinstance(target.get(key), list) and isinstance(value, list):
        # add on a multi-valued attribute appends; new primaries win.
        if any(isinstance(v, dict) and get_ci(v, "primary") for v in value):
            for item in target[key]:
                if isinstance(item, dict):
                    item.pop(_real_key(item, "primary"), None)
        target[key].extend(value)
    elif op == "add" and isinstance(target.get(key), dict) and isinstance(value, dict):
        target[key].update(value)
    else:
        target[key] = value


def apply_patch(document, body):
    if not isinstance(body, dict):
        raise ScimError(400, "invalidSyntax", "Request body must be a JSON object.")
    schemas = get_ci(body, "schemas") or []
    if PATCH_OP not in schemas:
        raise ScimError(400, "invalidSyntax", f"PATCH requires the {PATCH_OP} schema.")
    operations = get_ci(body, "Operations")
    if not isinstance(operations, list) or not operations:
        raise ScimError(400, "invalidSyntax", "'Operations' must be a non-empty list.")

    doc = copy.deepcopy(document)
    for operation in operations:
        if not isinstance(operation, dict):
            raise ScimError(400, "invalidSyntax", "Each operation must be an object.")
        op = str(get_ci(operation, "op", "")).lower()
        if op not in ("add", "replace", "remove"):
            raise ScimError(400, "invalidSyntax", f"Unsupported op '{op}'.")
        path = get_ci(operation, "path")
        value = get_ci(operation, "value")

        if path:
            if op != "remove" and value is None:
                raise ScimError(400, "invalidValue", "Operation has no value.")
            _apply_path(doc, op, str(path).strip(), value)
            continue

        if op == "remove":
            raise ScimError(400, "noTarget", "'remove' requires a path.")
        if not isinstance(value, dict):
            raise ScimError(
                400, "invalidValue", "Operation without a path needs an object value."
            )
        for key, item in value.items():
            if key.lower() == ENTERPRISE_USER.lower() and isinstance(item, dict):
                for sub_key, sub_value in item.items():
                    _apply_path(doc, op, f"{ENTERPRISE_USER}:{sub_key}", sub_value)
            else:
                # Entra sends dotted keys here, e.g. {"name.givenName": "Ann"}.
                _apply_path(doc, op, key, item)
    return doc
