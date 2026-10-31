"""
schemas.py

SCIM URNs and the static discovery documents (RFC 7643 §5-7).
"""

CORE_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
ENTERPRISE_USER = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
LIST_RESPONSE = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_OP = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
SERVICE_PROVIDER_CONFIG = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
RESOURCE_TYPE = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"

MAX_RESULTS = 200


def service_provider_config(base_url):
    return {
        "schemas": [SERVICE_PROVIDER_CONFIG],
        "documentationUri": "https://datatracker.ietf.org/doc/html/rfc7644",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": MAX_RESULTS},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "Bearer token",
                "description": "Token generated in Horilla SCIM settings.",
                "primary": True,
            }
        ],
        "meta": {
            "resourceType": "ServiceProviderConfig",
            "location": f"{base_url}/ServiceProviderConfig",
        },
    }


def user_resource_type(base_url):
    return {
        "schemas": [RESOURCE_TYPE],
        "id": "User",
        "name": "User",
        "endpoint": "/Users",
        "description": "Horilla employee",
        "schema": CORE_USER,
        "schemaExtensions": [{"schema": ENTERPRISE_USER, "required": False}],
        "meta": {
            "resourceType": "ResourceType",
            "location": f"{base_url}/ResourceTypes/User",
        },
    }


def _attr(
    name,
    type_="string",
    required=False,
    multi=False,
    uniqueness="none",
    sub_attributes=None,
    mutability="readWrite",
    case_exact=False,
):
    attr = {
        "name": name,
        "type": type_,
        "multiValued": multi,
        "required": required,
        "caseExact": case_exact,
        "mutability": mutability,
        "returned": "default",
        "uniqueness": uniqueness,
    }
    if sub_attributes:
        attr["subAttributes"] = sub_attributes
    return attr


def _multi_value_subs():
    return [
        _attr("value"),
        _attr("type"),
        _attr("primary", "boolean"),
    ]


def schemas(base_url):
    user = {
        "schemas": [SCHEMA],
        "id": CORE_USER,
        "name": "User",
        "description": "User account",
        "attributes": [
            _attr("userName", required=True, uniqueness="server"),
            _attr(
                "name",
                "complex",
                sub_attributes=[
                    _attr("formatted", mutability="readOnly"),
                    _attr("givenName", required=True),
                    _attr("familyName"),
                ],
            ),
            _attr("displayName"),
            _attr("title"),
            _attr("active", "boolean"),
            _attr(
                "emails",
                "complex",
                required=True,
                multi=True,
                sub_attributes=_multi_value_subs(),
            ),
            _attr(
                "phoneNumbers",
                "complex",
                multi=True,
                sub_attributes=_multi_value_subs(),
            ),
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base_url}/Schemas/{CORE_USER}",
        },
    }
    enterprise = {
        "schemas": [SCHEMA],
        "id": ENTERPRISE_USER,
        "name": "EnterpriseUser",
        "description": "Enterprise user",
        "attributes": [
            _attr("employeeNumber", uniqueness="server"),
            _attr("department"),
            _attr("manager", "complex", sub_attributes=[_attr("value")]),
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base_url}/Schemas/{ENTERPRISE_USER}",
        },
    }
    return [user, enterprise]


def list_response(resources, total, start_index):
    return {
        "schemas": [LIST_RESPONSE],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }
