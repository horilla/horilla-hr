"""
company_onboarding/services/cashfree_client.py

Wraps two separate Cashfree products:

  1. Verification Suite's Bank Account Verification (Sync) -- an instant,
     read-only check of whether an account_number/ifsc is real and whose
     name it's registered under. No money moves for this call.
       https://www.cashfree.com/docs/secure-id/kyc-stack/verify-bank-account

  2. Payouts V2 (beneficiary -> transfer) -- actually moves money. Real
     money moves on every call to initiate_bank_transfer().
       https://www.cashfree.com/docs/api-reference/payouts/v2/beneficiary-v2/create-beneficiary-v2
       https://www.cashfree.com/docs/api-reference/payouts/v2/transfers-v2/standard-transfer-v2
       https://www.cashfree.com/docs/api-reference/payouts/v2/transfers-v2/get-transfer-status-v2

V2 auth is a flat x-client-id/x-client-secret/x-api-version header set on
every request -- no separate bearer-token step like V1 had. Transfers V2
is async by default: the POST only acknowledges receipt (status
RECEIVED/PENDING); the real outcome has to be fetched afterward via
get_transfer_status(), which is why CompanyBankVerification.DropStatus
has a PENDING state alongside SUCCESS/FAILED.

CASHFREE_CLIENT_ID / CASHFREE_CLIENT_SECRET / CASHFREE_ENV (and the
verification-specific overrides) come from settings (see
horilla/settings/addons.py, .env.dist) -- never hardcoded.

Some Cashfree accounts (this project's included) have signature-based
request security enabled, in which case every call also needs an
x-cf-signature header: RSA-OAEP(SHA-1) encrypt "{client_id}.{unix_ts}"
with a public key Cashfree issues per account, base64-encode the
ciphertext. See _generate_signature() -- CASHFREE_SIGNATURE_PUBLIC_KEY_PATH
points at that key's .pem file; calls are made without the header (as
before) if it isn't set, which only works for accounts that don't require it.
"""

import base64
import hashlib
import time
import uuid
from decimal import Decimal

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings

_PAYOUT_BASE_URLS = {
    "production": "https://api.cashfree.com/payout",
    "sandbox": "https://sandbox.cashfree.com/payout",
}
_VERIFICATION_BASE_URLS = {
    "production": "https://api.cashfree.com/verification",
    "sandbox": "https://sandbox.cashfree.com/verification",
}
_API_VERSION = "2024-01-01"
_TIMEOUT = 20

# Terminal states for Transfers V2 -- anything else (RECEIVED, PENDING,
# APPROVAL_PENDING, QUEUED, VALIDATION_PENDING, ...) means still in
# flight, not done yet.
_TRANSFER_SUCCESS_STATUSES = {"SUCCESS"}
_TRANSFER_FAILED_STATUSES = {"FAILED", "REJECTED", "REVERSED"}


class CashfreePayoutError(Exception):
    """
    Raised for anything that stops a transfer from being *attempted*
    (bad credentials, invalid beneficiary details, network/timeout
    failures). A transfer Cashfree itself declines (e.g. bank offline) is
    NOT an error -- it comes back as a normal FAILED/PENDING result, an
    expected outcome of this flow, not a bug.
    """


def _env() -> str:
    return getattr(settings, "CASHFREE_ENV", "sandbox")


def _payout_credentials() -> tuple[str, str]:
    client_id = getattr(settings, "CASHFREE_CLIENT_ID", None)
    client_secret = getattr(settings, "CASHFREE_CLIENT_SECRET", None)
    if not client_id or not client_secret:
        raise CashfreePayoutError(
            "Cashfree isn't configured -- set CASHFREE_CLIENT_ID and "
            "CASHFREE_CLIENT_SECRET in .env."
        )
    return client_id, client_secret


def _verification_credentials() -> tuple[str, str]:
    # Cashfree issues separate credentials per product -- these default to
    # the Payouts ones since some accounts share one key pair across
    # products, but can be overridden independently in .env if Cashfree
    # issued distinct Verification Suite credentials.
    client_id = getattr(settings, "CASHFREE_VERIFICATION_CLIENT_ID", None)
    client_secret = getattr(settings, "CASHFREE_VERIFICATION_CLIENT_SECRET", None)
    if client_id and client_secret:
        return client_id, client_secret
    return _payout_credentials()


_signature_public_key = None
_signature_public_key_loaded_from = None


def _load_signature_public_key():
    global _signature_public_key, _signature_public_key_loaded_from
    key_path = getattr(settings, "CASHFREE_SIGNATURE_PUBLIC_KEY_PATH", None)
    if not key_path:
        return None
    if _signature_public_key is not None and _signature_public_key_loaded_from == key_path:
        return _signature_public_key
    try:
        with open(key_path, "rb") as f:
            _signature_public_key = serialization.load_pem_public_key(f.read())
    except (OSError, ValueError) as exc:
        raise CashfreePayoutError(
            f"Could not load CASHFREE_SIGNATURE_PUBLIC_KEY_PATH ({key_path}): {exc}"
        ) from exc
    _signature_public_key_loaded_from = key_path
    return _signature_public_key


def _generate_signature(client_id: str) -> str | None:
    """
    Returns the x-cf-signature header value, or None if
    CASHFREE_SIGNATURE_PUBLIC_KEY_PATH isn't configured (some accounts
    don't need this at all).
    """
    public_key = _load_signature_public_key()
    if public_key is None:
        return None
    payload = f"{client_id}.{int(time.time())}".encode()
    ciphertext = public_key.encrypt(
        payload,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode()


def _request(method: str, base: str, path: str, **kwargs) -> tuple[int, dict]:
    try:
        response = requests.request(method, f"{base}{path}", timeout=_TIMEOUT, **kwargs)
    except requests.exceptions.RequestException as exc:
        raise CashfreePayoutError(f"Could not reach Cashfree ({path}): {exc}") from exc
    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise CashfreePayoutError(
            f"Cashfree returned a non-JSON response ({path}): {response.status_code}"
        ) from exc


def _payout_request(method: str, path: str, **kwargs) -> tuple[int, dict]:
    client_id, client_secret = _payout_credentials()
    headers = {
        "x-api-version": _API_VERSION,
        "x-client-id": client_id,
        "x-client-secret": client_secret,
        "Content-Type": "application/json",
    }
    signature = _generate_signature(client_id)
    if signature:
        headers["x-cf-signature"] = signature
    headers.update(kwargs.pop("headers", {}) or {})
    base = _PAYOUT_BASE_URLS.get(_env(), _PAYOUT_BASE_URLS["sandbox"])
    return _request(method, base, path, headers=headers, **kwargs)


def verify_bank_account(*, account_number: str, ifsc: str, name: str = "", phone: str = "") -> dict:
    """
    Instant, read-only check -- no money moves. Returns
    {"valid": bool, "account_status": str, "name_at_bank": str,
    "name_match_result": str, "message": str, "http_status": int,
    "request_payload": dict, "response_payload": dict} -- the last three
    are for CashfreeApiLog, not meant to drive any decision logic.
    """
    client_id, client_secret = _verification_credentials()
    base = _VERIFICATION_BASE_URLS.get(_env(), _VERIFICATION_BASE_URLS["sandbox"])
    request_payload = {
        "bank_account": account_number,
        "ifsc": ifsc,
        "name": name or None,
        "phone": phone or None,
    }
    headers = {
        "x-client-id": client_id,
        "x-client-secret": client_secret,
        "Content-Type": "application/json",
    }
    signature = _generate_signature(client_id)
    if signature:
        headers["x-cf-signature"] = signature
    status_code, data = _request("POST", base, "/bank-account/sync", headers=headers, json=request_payload)
    account_status = (data.get("account_status") or "").upper()
    return {
        "valid": account_status == "VALID",
        "account_status": account_status or "UNKNOWN",
        "name_at_bank": data.get("name_at_bank", ""),
        "name_match_result": data.get("name_match_result", ""),
        "message": data.get("message") or data.get("account_status_code") or "",
        "http_status": status_code,
        "request_payload": request_payload,
        "response_payload": data,
    }


def _beneficiary_id(account_number: str, ifsc: str, company_id: int) -> str:
    """
    Deterministic from (company_id, account_number, ifsc) -- if the
    account details on file ever change, this naturally becomes a
    *different* beneficiary id rather than silently reusing stale bank
    details registered under an old one.
    """
    digest = hashlib.sha256(f"{account_number}:{ifsc}".encode()).hexdigest()[:16]
    return f"co{company_id}{digest}"


def _get_beneficiary(bene_id: str, log_sink: list | None = None) -> dict | None:
    # beneficiary_id is a QUERY param on this endpoint, not a path segment
    # -- GET /beneficiary/{id} looks RESTful but isn't what Cashfree's API
    # actually accepts (confirmed against their own OpenAPI spec).
    request_payload = {"beneficiary_id": bene_id}
    status_code, data = _payout_request("GET", "/beneficiary", params=request_payload)
    if log_sink is not None:
        log_sink.append(
            {
                "call_type": "GET_BENEFICIARY",
                "http_status": status_code,
                "request_payload": request_payload,
                "response_payload": data,
            }
        )
    if status_code == 404:
        return None
    if status_code >= 400:
        # Cashfree documents 404 for "not found" but in practice returns
        # 400 with a validation-style error body for it too (confirmed:
        # the same account also gets 400s for things like an invalid
        # IFSC) -- so "not found" has to be detected from the error code/
        # message, not just the HTTP status.
        code = (data.get("code") or "").lower()
        message = data.get("message") or ""
        if "not_found" in code or "does not exist" in message.lower() or "not exist" in message.lower():
            return None
        raise CashfreePayoutError(f"Cashfree getBeneficiary failed: {message}")
    return data


def _create_beneficiary(
    *,
    bene_id: str,
    name: str,
    email: str,
    phone: str,
    address: str,
    bank_account: str,
    ifsc: str,
    log_sink: list | None = None,
) -> bool:
    """
    Returns True if `bene_id` is now registered with Cashfree. Returns
    False (not raises) on a conflict -- Cashfree dedupes beneficiaries by
    (bank_account_number, bank_ifsc), not by the beneficiary_id we chose,
    so "already exists" here means this exact account is already
    registered under a DIFFERENT beneficiary_id (e.g. from another
    integration). The caller has to look that id up separately.
    """
    request_payload = {
        "beneficiary_id": bene_id,
        "beneficiary_name": name,
        "beneficiary_instrument_details": {
            "bank_account_number": bank_account,
            "bank_ifsc": ifsc,
        },
        "beneficiary_contact_details": {
            "beneficiary_email": email,
            "beneficiary_phone": phone,
            "beneficiary_country_code": "+91",
            "beneficiary_address": (address or "")[:150] or "NA",
        },
    }
    status_code, data = _payout_request("POST", "/beneficiary", json=request_payload)
    if log_sink is not None:
        log_sink.append(
            {
                "call_type": "CREATE_BENEFICIARY",
                "http_status": status_code,
                "request_payload": request_payload,
                "response_payload": data,
            }
        )
    if status_code >= 400:
        code = (data.get("code") or "").lower()
        message = data.get("message") or ""
        if status_code == 409 or "conflict" in code or "already" in message.lower():
            return False
        raise CashfreePayoutError(f"Cashfree createBeneficiary failed: {message}")
    return True


def _get_beneficiary_by_account(
    bank_account: str, ifsc: str, log_sink: list | None = None
) -> dict | None:
    """Same lookup, keyed by the account itself instead of a beneficiary_id."""
    request_payload = {"bank_account_number": bank_account, "bank_ifsc": ifsc}
    status_code, data = _payout_request("GET", "/beneficiary", params=request_payload)
    if log_sink is not None:
        log_sink.append(
            {
                "call_type": "GET_BENEFICIARY",
                "http_status": status_code,
                "request_payload": request_payload,
                "response_payload": data,
            }
        )
    if status_code == 404:
        return None
    if status_code >= 400:
        code = (data.get("code") or "").lower()
        message = data.get("message") or ""
        if "not_found" in code or "does not exist" in message.lower() or "not exist" in message.lower():
            return None
        raise CashfreePayoutError(f"Cashfree getBeneficiary (by account) failed: {message}")
    return data


def _ensure_beneficiary(
    *,
    bene_id: str,
    name: str,
    email: str,
    phone: str,
    address: str,
    bank_account: str,
    ifsc: str,
    log_sink: list | None = None,
) -> str:
    """
    Get-or-create -- returns the beneficiary_id to actually use for the
    transfer. Usually that's `bene_id` (our own deterministic id), but if
    Cashfree already has this exact bank_account_number+ifsc registered
    under a DIFFERENT beneficiary_id (e.g. from another integration using
    this same Cashfree account), returns that existing id instead.
    """
    if _get_beneficiary(bene_id, log_sink=log_sink) is not None:
        return bene_id
    if _create_beneficiary(
        bene_id=bene_id,
        name=name,
        email=email,
        phone=phone,
        address=address,
        bank_account=bank_account,
        ifsc=ifsc,
        log_sink=log_sink,
    ):
        return bene_id
    existing = _get_beneficiary_by_account(bank_account, ifsc, log_sink=log_sink)
    if existing and existing.get("beneficiary_id"):
        return existing["beneficiary_id"]
    raise CashfreePayoutError(
        "Cashfree reports this bank account is already registered as a "
        "beneficiary, but its beneficiary_id could not be looked up."
    )


def _request_transfer(*, bene_id: str, amount: Decimal, transfer_id: str) -> tuple[int, dict, dict]:
    """POST /transfers -- async by default, only acknowledges receipt."""
    request_payload = {
        "transfer_id": transfer_id,
        "transfer_amount": float(amount),
        "beneficiary_details": {"beneficiary_id": bene_id},
        "transfer_mode": "banktransfer",
        "remarks": "Krew HRMS bank verification",
    }
    status_code, data = _payout_request("POST", "/transfers", json=request_payload)
    if status_code >= 400:
        raise CashfreePayoutError(f"Cashfree requestTransfer failed: {data.get('message')}")
    return status_code, request_payload, data


def get_transfer_status(transfer_id: str) -> dict:
    """
    GET /transfers?transfer_id=... -- transfer_id is a QUERY param, not a
    path segment (confirmed against Cashfree's own OpenAPI spec). Returns
    {"resolved": bool, "success": bool | None, "reference_id": str,
    "message": str, "http_status": int, "response_payload": dict}.
    resolved=False means still in flight (RECEIVED/PENDING/...); check
    back later. success is only meaningful when resolved=True.
    """
    status_code, data = _payout_request(
        "GET", "/transfers", params={"transfer_id": transfer_id}
    )
    status = (data.get("status") or "").upper()
    reference_id = str(data.get("cf_transfer_id") or data.get("utr") or transfer_id)
    message = data.get("status_description") or data.get("status_code") or ""
    if status in _TRANSFER_SUCCESS_STATUSES:
        resolved, success = True, True
    elif status in _TRANSFER_FAILED_STATUSES:
        resolved, success = True, False
    else:
        resolved, success = False, None
    return {
        "resolved": resolved,
        "success": success,
        "reference_id": reference_id,
        "message": message,
        "http_status": status_code,
        "response_payload": data,
    }


def initiate_bank_transfer(
    *,
    account_number: str,
    ifsc: str,
    amount: Decimal,
    company_id: int,
    beneficiary_name: str,
    beneficiary_email: str,
    beneficiary_phone: str,
    beneficiary_address: str,
    log_sink: list | None = None,
) -> dict:
    """
    Ensures the beneficiary is registered, then requests a transfer of
    `amount` (Decimal, rupees, Cashfree requires >= 1.00) to the given
    bank account. Since Transfers V2 is async, this only tells you the
    transfer was *accepted*, not that it succeeded -- returns
    {"transfer_id": str, "resolved": bool, "success": bool | None,
    "message": str, "http_status": int, "request_payload": dict,
    "response_payload": dict}. Call get_transfer_status(transfer_id)
    later to find out what actually happened if resolved is False here.

    If `log_sink` (a list) is passed, every beneficiary GET/CREATE call
    made along the way appends a {"call_type", "http_status",
    "request_payload", "response_payload"} entry to it -- including when
    this raises, since the caller's list is mutated in place regardless
    of whether _ensure_beneficiary completes or errors out partway.
    """
    bene_id = _ensure_beneficiary(
        bene_id=_beneficiary_id(account_number, ifsc, company_id),
        name=beneficiary_name,
        email=beneficiary_email,
        phone=beneficiary_phone,
        address=beneficiary_address,
        bank_account=account_number,
        ifsc=ifsc,
        log_sink=log_sink,
    )
    transfer_id = f"pd{uuid.uuid4().hex[:20]}"
    status_code, request_payload, data = _request_transfer(
        bene_id=bene_id, amount=amount, transfer_id=transfer_id
    )
    status = (data.get("status") or "").upper()
    result = {
        "transfer_id": transfer_id,
        "http_status": status_code,
        "request_payload": request_payload,
        "response_payload": data,
    }

    if status in _TRANSFER_SUCCESS_STATUSES:
        return {**result, "resolved": True, "success": True, "message": ""}
    if status in _TRANSFER_FAILED_STATUSES:
        return {
            **result,
            "resolved": True,
            "success": False,
            "message": data.get("status_description", "Transfer failed"),
        }
    return {**result, "resolved": False, "success": None, "message": ""}
