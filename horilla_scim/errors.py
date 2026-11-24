from .schemas import ERROR


class ScimError(Exception):
    """An error reported to the IdP in the SCIM error format (RFC 7644 §3.12)."""

    def __init__(self, status, scim_type=None, detail=""):
        super().__init__(detail)
        self.status = status
        self.scim_type = scim_type
        self.detail = detail

    def as_dict(self):
        body = {"schemas": [ERROR], "status": str(self.status), "detail": self.detail}
        if self.scim_type:
            body["scimType"] = self.scim_type
        return body
