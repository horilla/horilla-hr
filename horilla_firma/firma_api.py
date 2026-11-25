"""
Minimal client for the Firma e-signature REST API (contract 01.45.00).

Authentication is the raw API key in the ``Authorization`` header (no "Bearer"
prefix). This module has no Django imports so it can be tested on its own.
"""

import base64
import hashlib
import hmac
import json
import re
import time

import requests

FIRMA_BASE_URL = "https://api.firma.dev/functions/v1/signing-request-api"
SIGNING_PAGE_BASE = "https://app.firma.dev/signing/"
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
MAX_MESSAGE_LENGTH = 400
MAX_NAME_LENGTH = 255
# An inline base64 document shares Firma's 6,291,456 byte request cap with the
# rest of the body, so only files up to 4 MiB go inline. Larger files use the
# presigned upload (POST /documents, then PUT to upload_url).
INLINE_DOCUMENT_LIMIT = 4 * 1024 * 1024
MAX_UPLOAD_SIZE = 52428800
WEBHOOK_TOLERANCE_SECONDS = 300
# Firma list endpoints serve at most 200 rows per page.
PAGE_SIZE = 200
MAX_PAGES = 100
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Default signature box for document sends, in percent of the page.
DEFAULT_SIGNATURE_BOX = {"x": 58.0, "y": 84.0, "width": 32.0, "height": 7.0}

WEBHOOK_EVENTS = [
    "signing_request.completed",
    "signing_request.recipient.signed",
    "signing_request.recipient.declined",
    "signing_request.cancelled",
    "signing_request.expired",
]

INVALID_RESPONSE_MESSAGE = (
    "The Firma API returned a response this integration does not understand."
)


class FirmaApiError(Exception):
    """An error answer from the Firma API, or a failure to get one."""

    def __init__(
        self, status, code, message, has_firma_body=False, signing_request_id=None
    ):
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[: MAX_MESSAGE_LENGTH - 3] + "..."
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.has_firma_body = has_firma_body
        self.signing_request_id = signing_request_id


def invalid_input(message):
    """A refusal raised before anything was sent to Firma."""
    return FirmaApiError(0, "INVALID_INPUT", message)


def _invalid_response():
    return FirmaApiError(200, "INVALID_RESPONSE", INVALID_RESPONSE_MESSAGE)


class FirmaClient:
    """Calls the Firma API with one API key."""

    def __init__(self, api_key, base_url=FIRMA_BASE_URL, session=None):
        api_key = (api_key or "").strip()
        if not api_key:
            raise invalid_input("The Firma API key is not set.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = session or requests

    # Transport

    def request(self, method, path, params=None, body=None):
        url = "%s%s" % (self.base_url, path)
        headers = {"Authorization": self.api_key, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body)
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        try:
            response = self.session.request(
                method,
                url,
                params=params or None,
                data=data,
                headers=headers,
                timeout=TIMEOUT,
            )
        except requests.exceptions.RequestException:
            raise FirmaApiError(
                0, "NETWORK_ERROR", "Could not reach the Firma API. Please try again."
            ) from None

        parsed = None
        text = response.text or ""
        if text:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None

        if not 200 <= response.status_code < 300:
            body_dict = parsed if isinstance(parsed, dict) else {}
            code = body_dict.get("code")
            code = code if isinstance(code, str) else None
            error = body_dict.get("error")
            error = error if isinstance(error, str) else None
            sr_id = body_dict.get("signing_request_id")
            fallback = "HTTP_%s" % response.status_code
            raise FirmaApiError(
                response.status_code,
                code or fallback,
                "Firma API error %s (%s): %s"
                % (
                    response.status_code,
                    code or fallback,
                    error or response.reason or "Request failed",
                ),
                has_firma_body=bool(code and error),
                signing_request_id=sr_id if isinstance(sr_id, str) and sr_id else None,
            )
        return parsed

    @staticmethod
    def _expect_dict(value):
        if not isinstance(value, dict):
            raise _invalid_response()
        return value

    def _list_all(self, path, params, max_pages=MAX_PAGES, page_size=PAGE_SIZE):
        """Every row of a paginated list. Returns (rows, complete).

        ``complete`` is True only when the listing reached its end: the page
        ``pagination.total_pages`` names, or (without pagination data) a page
        shorter than ``page_size``. Any error raises, so a caller never takes a
        partial list for a complete one.
        """
        rows = []
        page = 1
        while page <= max_pages:
            body = self._expect_dict(
                self.request(
                    "GET", path, params={**params, "page": page, "page_size": page_size}
                )
            )
            results = body.get("results")
            if not isinstance(results, list):
                raise _invalid_response()
            rows.extend(row for row in results if isinstance(row, dict))
            pagination = body.get("pagination")
            pagination = pagination if isinstance(pagination, dict) else {}
            total_pages = pagination.get("total_pages")
            if isinstance(total_pages, int) and not isinstance(total_pages, bool):
                if page >= total_pages:
                    return rows, True
            elif len(results) < page_size:
                return rows, True
            if not results:
                # Firma promised more pages but returned none.
                return rows, False
            page += 1
        return rows, False

    # Read paths

    def test_connection(self):
        """GET /templates?page_size=1. Raises FirmaApiError for a bad key."""
        return self._expect_dict(
            self.request("GET", "/templates", params={"page_size": 1})
        )

    def list_templates(self, max_pages=MAX_PAGES):
        """Every template, page by page. Returns (templates, complete)."""
        rows, complete = self._list_all(
            "/templates",
            {"sort_by": "name", "sort_order": "asc"},
            max_pages=max_pages,
        )
        return [parse_template(row) for row in rows if row.get("id")], complete

    def get_template(self, template_id):
        """GET /templates/{id}, or None when it does not exist."""
        try:
            body = self.request("GET", "/templates/%s" % _quote(template_id))
        except FirmaApiError as error:
            if error.status == 404:
                return None
            raise
        return parse_template(self._expect_dict(body))

    def get_signing_request(self, signing_request_id):
        return self._expect_dict(
            self.request("GET", "/signing-requests/%s" % _quote(signing_request_id))
        )

    def get_signing_request_users(self, signing_request_id):
        body = self._expect_dict(
            self.request(
                "GET", "/signing-requests/%s/users" % _quote(signing_request_id)
            )
        )
        results = body.get("results")
        return results if isinstance(results, list) else []

    def fetch_signed_pdf(self, signing_request_id):
        """The final signed PDF bytes, or FirmaApiError.

        GET /signing-requests/{id}/download answers JSON with a presigned
        ``download_url``. A 409 right after completion, or a partial document,
        means the final document is not ready yet; the caller tries later.
        """
        info = self._expect_dict(
            self.request(
                "GET", "/signing-requests/%s/download" % _quote(signing_request_id)
            )
        )
        if info.get("is_partial") or info.get("status") != "finished":
            raise FirmaApiError(
                409, "NOT_READY", "The signed document is not ready yet."
            )
        url = info.get("download_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise FirmaApiError(
                200, "INVALID_RESPONSE", "The Firma API returned no download URL."
            )
        try:
            # Presigned URL: no API key on this call.
            response = self.session.request("GET", url, timeout=TIMEOUT)
        except requests.exceptions.RequestException:
            raise FirmaApiError(
                0, "NETWORK_ERROR", "Could not download the signed document."
            ) from None
        if response.status_code != 200 or not response.content:
            raise FirmaApiError(
                response.status_code,
                "DOWNLOAD_FAILED",
                "Could not download the signed document.",
            )
        return response.content

    # Documents

    def upload_document(self, file_name, content):
        """POST /documents, then PUT the bytes to ``upload_url``.

        Returns ``document_id``.
        """
        size = len(content)
        if size > MAX_UPLOAD_SIZE:
            raise invalid_input("The document is larger than Firma's 50 MB limit.")
        body = self._expect_dict(
            self.request(
                "POST",
                "/documents",
                body={
                    "file_name": file_name[:255],
                    "file_size": size,
                    "content_type": "application/pdf",
                },
            )
        )
        document_id = body.get("document_id")
        upload_url = body.get("upload_url")
        if not document_id or not isinstance(upload_url, str):
            raise FirmaApiError(
                200, "INVALID_RESPONSE", "The Firma API returned no upload URL."
            )
        try:
            # Presigned URL: no API key on this call.
            response = self.session.request(
                "PUT",
                upload_url,
                data=content,
                headers={"Content-Type": "application/pdf"},
                timeout=UPLOAD_TIMEOUT,
            )
        except requests.exceptions.RequestException:
            raise FirmaApiError(
                0, "UPLOAD_FAILED", "Could not upload the document to Firma."
            ) from None
        if not 200 <= response.status_code < 300:
            # Nothing has been sent yet, so this is a plain failure.
            raise FirmaApiError(
                400,
                "UPLOAD_FAILED",
                "Could not upload the document to Firma (%s)." % response.status_code,
            )
        return document_id

    # Create and send

    def create_and_send(self, body):
        parsed = self._expect_dict(
            self.request("POST", "/signing-requests/create-and-send", body=body)
        )
        if not parsed.get("id"):
            raise _invalid_response()
        return parsed

    # Webhooks

    def list_webhooks(self, url):
        """Every company webhook registered for ``url`` (all pages)."""
        rows, _complete = self._list_all("/webhooks", {"url": url})
        return rows

    def create_webhook(self, url, events=None):
        body = self._expect_dict(
            self.request(
                "POST",
                "/webhooks",
                body={"url": url, "events": events or WEBHOOK_EVENTS},
            )
        )
        return body.get("id")

    def update_webhook(self, webhook_id, values):
        """PUT /webhooks/{id}. ``enabled: true`` also clears Firma's auto-disable."""
        return self._expect_dict(
            self.request("PUT", "/webhooks/%s" % _quote(webhook_id), body=values)
        )


def _quote(value):
    return requests.utils.quote(str(value), safe="")


def parse_template(row):
    """A template with its Signer and Approver users (CC rows dropped), by order."""
    users = []
    for recipient in row.get("recipients") or []:
        if not isinstance(recipient, dict) or not recipient.get("id"):
            continue
        designation = recipient.get("designation") or "Signer"
        if str(designation).upper() == "CC":
            continue
        users.append(
            {
                "id": recipient["id"],
                "designation": designation,
                "order": recipient.get("order") or 1,
            }
        )
    users.sort(key=lambda user: user["order"])
    return {"id": row["id"], "name": row.get("name") or row["id"], "users": users}


def pick_template_user(template):
    """The single template user a one-recipient send fills.

    Returns (ok, user_or_message). Create-and-send needs a recipient for every
    template user, and this integration sends to one recipient (the
    candidate), so templates with more than one Signer or Approver are refused.
    """
    users = template["users"]
    if len(users) <= 1:
        return True, (users[0] if users else None)
    return False, (
        'The Firma template "%s" has %s recipients who sign or approve. This '
        "integration sends to one recipient, so choose a template with a single "
        "signer." % (template["name"], len(users))
    )


def _is_cc(recipient):
    return str(recipient.get("designation") or "").upper() == "CC"


def _matches(recipient, user, user_ids):
    """Firma's create-and-send match rule: template_user_id, then a template
    user id in ``id``, then ``order`` when neither names a template user."""
    if recipient.get("template_user_id"):
        return recipient["template_user_id"] == user["id"]
    recipient_id = recipient.get("id")
    if recipient_id and recipient_id in user_ids:
        return recipient_id == user["id"]
    order = recipient.get("order")
    try:
        return order is not None and int(order) == int(user["order"])
    except (TypeError, ValueError):
        return False


def check_template_recipients(template_users, recipients):
    """Refuses a recipient list Firma would partly ignore.

    Firma's create-and-send gives each template user the first matching
    recipient and silently drops non-CC recipients that match no template
    user. This check runs before the POST and raises INVALID_INPUT when a
    recipient names an unknown template user, matches no template user or more
    than one, or shares a template user with another recipient, and when a
    template user has no recipient.
    """
    if not template_users:
        return
    user_ids = {user["id"] for user in template_users}
    claimed = {}
    for index, recipient in enumerate(recipients, start=1):
        if _is_cc(recipient):
            continue
        template_user_id = recipient.get("template_user_id")
        if template_user_id and template_user_id not in user_ids:
            raise invalid_input(
                "Recipient %s names a template role that is not in the Firma "
                "template." % index
            )
        matched = [u for u in template_users if _matches(recipient, u, user_ids)]
        if not matched:
            raise invalid_input(
                "Recipient %s matches no role in the Firma template, and Firma "
                "would leave it out." % index
            )
        if len(matched) > 1:
            raise invalid_input(
                "Recipient %s matches more than one role in the Firma template." % index
            )
        user_id = matched[0]["id"]
        if user_id in claimed:
            raise invalid_input(
                "Recipients %s and %s fill the same role in the Firma template."
                % (claimed[user_id], index)
            )
        claimed[user_id] = index
    for user in template_users:
        if user["id"] not in claimed:
            raise invalid_input(
                "No recipient fills the %s role at order %s in the Firma template."
                % (user["designation"], user["order"])
            )


def split_name(full_name):
    parts = (full_name or "").strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first[:100], last[:100]


def _recipient(first_name, last_name, email):
    first_name = (first_name or "").strip()
    email = (email or "").strip()
    if not first_name:
        raise invalid_input("The recipient's name is required.")
    if not EMAIL_PATTERN.match(email):
        raise invalid_input("The recipient's email address is not valid.")
    recipient = {"first_name": first_name[:100], "email": email}
    if last_name and last_name.strip():
        recipient["last_name"] = last_name.strip()[:100]
    return recipient


def _base_body(name, expiration_hours):
    name = (name or "").strip()[:MAX_NAME_LENGTH]
    if not name:
        raise invalid_input("The signing request needs a name.")
    body = {"name": name}
    if expiration_hours:
        if not isinstance(expiration_hours, int) or expiration_hours < 1:
            raise invalid_input(
                "Expiration must be a whole number of hours, 1 or more."
            )
        body["expiration_hours"] = expiration_hours
    return body


def build_template_body(
    template_id,
    template_user,
    name,
    first_name,
    last_name,
    email,
    expiration_hours=None,
):
    """Create-and-send body for a template with at most one user.

    The recipient fills the template's single user, matched by
    ``template_user_id`` and keeping that user's designation and order. With no
    template user it is added as the Signer at order 1.
    """
    if not (template_id or "").strip():
        raise invalid_input("Choose a Firma template.")
    body = _base_body(name, expiration_hours)
    recipient = _recipient(first_name, last_name, email)
    if template_user:
        recipient["template_user_id"] = template_user["id"]
        recipient["designation"] = template_user["designation"]
        recipient["order"] = template_user["order"]
    else:
        recipient["designation"] = "Signer"
        recipient["order"] = 1
    check_template_recipients([template_user] if template_user else [], [recipient])
    body["template_id"] = template_id.strip()
    body["recipients"] = [recipient]
    return body


def build_document_body(
    name,
    first_name,
    last_name,
    email,
    page_count,
    document_b64=None,
    document_id=None,
    expiration_hours=None,
):
    """Create-and-send body for a PDF with one Signer and one signature box.

    The box goes on the last page when the page count is known, else on page 1.
    """
    if bool(document_b64) == bool(document_id):
        raise invalid_input(
            "Provide the document either inline or as an uploaded document id."
        )
    if isinstance(page_count, int) and not isinstance(page_count, bool):
        page_number = page_count if page_count >= 1 else 1
    else:
        page_number = 1
    body = _base_body(name, expiration_hours)
    recipient = _recipient(first_name, last_name, email)
    recipient.update({"id": "temp_1", "designation": "Signer", "order": 1})
    if document_b64:
        body["document"] = document_b64
    else:
        body["document_id"] = document_id
    body["recipients"] = [recipient]
    body["fields"] = [
        {
            "type": "signature",
            "recipient_id": "temp_1",
            "page_number": page_number,
            "position": dict(DEFAULT_SIGNATURE_BOX),
            "required": True,
        }
    ]
    return body


def encode_inline(content):
    return base64.b64encode(content).decode("ascii")


# Send safety

NOT_CREATED = "not_created"
ALREADY_SENT = "already_sent"
KEPT = "kept"
UNKNOWN = "unknown"
_DEFINITE_503_CODES = {"ANCHOR_DISABLED_EDGE", "SEALS_DISABLED"}


def classify_create_and_send_failure(error):
    """What a failed create-and-send left behind.

    Returns (kind, signing_request_id):

    * ``not_created``: Firma answered and created nothing (4xx except the 409s
      below, 429, 503 ANCHOR_DISABLED_EDGE or SEALS_DISABLED with Firma's
      body), or the input was refused before any call.
    * ``already_sent``: 409 ALREADY_SENT with ``signing_request_id``.
    * ``kept``: 409 SEND_EFFECTS_EXIST with ``signing_request_id``, or
      SEND_IN_PROGRESS. The request exists and may be out.
    * ``unknown``: no usable answer (network error, unreadable 2xx) or any
      other 5xx, Firma's own 500 included (its rollback can fail). The request
      may have been sent, so it must never be sent again automatically.
    """
    if not isinstance(error, FirmaApiError):
        return UNKNOWN, None
    if error.code in ("INVALID_INPUT", "UPLOAD_FAILED"):
        return NOT_CREATED, None
    if error.status == 0 or error.code == "INVALID_RESPONSE":
        return UNKNOWN, None
    if error.status == 409:
        if error.code == "ALREADY_SENT" and error.signing_request_id:
            return ALREADY_SENT, error.signing_request_id
        if error.code == "SEND_EFFECTS_EXIST" and error.signing_request_id:
            return KEPT, error.signing_request_id
        if error.code == "SEND_IN_PROGRESS":
            return KEPT, error.signing_request_id
        return NOT_CREATED, None
    if error.status < 500:
        return NOT_CREATED, None
    if (
        error.status == 503
        and error.has_firma_body
        and error.code in _DEFINITE_503_CODES
    ):
        return NOT_CREATED, None
    return UNKNOWN, None


def status_from_flags(flags):
    """Maps the ``status`` flags of GET /signing-requests/{id} to a status word."""
    if not isinstance(flags, dict):
        return None
    if flags.get("finished"):
        return "completed"
    if flags.get("declined"):
        return "declined"
    if flags.get("cancelled"):
        return "cancelled"
    if flags.get("expired"):
        return "expired"
    if flags.get("sent"):
        return "sent"
    return None


# Webhook signatures


def _parse_signature_header(header):
    timestamp = None
    signatures = []
    for part in (header or "").split(","):
        key, _sep, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def verify_signature_header(header, raw_body, secret, now=None):
    """Checks one ``t=<unix s>,v1=<hex>`` header: HMAC-SHA256 over ``t.raw_body``.

    Returns "ok", "invalid" or "stale". Fails closed when there is no secret.
    """
    if not secret or not header:
        return "invalid"
    timestamp, signatures = _parse_signature_header(header)
    if not timestamp or not timestamp.isdigit() or not signatures:
        return "invalid"
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    signed = timestamp.encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not any(
        hmac.compare_digest(expected, candidate.strip().lower())
        for candidate in signatures
    ):
        return "invalid"
    now = time.time() if now is None else now
    if abs(now - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
        return "stale"
    return "ok"


def verify_webhook(headers_get, raw_body, secret, now=None):
    """Verifies ``X-Firma-Signature``, and ``X-Firma-Signature-Old`` in rotation."""
    results = [
        verify_signature_header(headers_get("X-Firma-Signature"), raw_body, secret, now)
    ]
    old = headers_get("X-Firma-Signature-Old")
    if old:
        results.append(verify_signature_header(old, raw_body, secret, now))
    if "ok" in results:
        return "ok"
    if "stale" in results:
        return "stale"
    return "invalid"
