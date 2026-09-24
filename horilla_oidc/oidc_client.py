"""
oidc_client.py

The OIDC protocol mechanics: discovery, authorization-URL construction,
token exchange, and ID token verification. Deliberately free of any Django
request/session coupling, so the security-critical piece --
verify_id_token -- is unit-testable against a locally generated RSA
keypair with no network access and no Django test client.

What is hand-rolled here (discovery fetch, URL building, token exchange) is
plain HTTP plumbing: reading it end to end is enough to trust it.

What is NOT hand-rolled: JWT signature verification against a rotating
JWKS. That goes through PyJWT's PyJWKClient (fetching/caching the JWKS,
matching `kid`, converting a JWK into a usable key object) and jwt.decode
with `algorithms` pinned explicitly rather than trusted from the token's
own header -- the standard defence against algorithm-confusion attacks
(e.g. a forged token claiming `alg: none`, or an RSA-signed scheme
downgraded to HMAC using the public key as the HMAC secret). PyJWT is
already a direct, actively-maintained dependency in this codebase
(requirements.txt pins it specifically to close a CVE on this exact
verification path) -- reimplementing that logic by hand here would be
relocating well-tested library code into new, unreviewed code for no
benefit.
"""

from __future__ import annotations

from urllib.parse import urlencode

import jwt
import requests
from cryptography.fernet import InvalidToken
from django.core.cache import cache

DISCOVERY_CACHE_TTL = 60 * 60 * 24  # 24h. IdP endpoints/keys change rarely.
HTTP_TIMEOUT = 10
CLOCK_SKEW_LEEWAY = 60  # seconds; IdP and server clocks are never exactly in sync.


class OidcClientError(Exception):
    """Anything that should surface as the login page's generic error. The
    message carries the underlying cause, for the server log only."""


def discovery_cache_key(provider) -> str:
    return f"oidc_discovery_{provider.pk}"


def get_discovery(provider) -> dict:
    """
    Fetch (and cache) `{issuer}/.well-known/openid-configuration`.

    Manual per-field overrides on the provider (authorization_endpoint,
    token_endpoint, jwks_uri) win over whatever discovery returns, for IdPs
    whose discovery document is missing, wrong, or unreachable.
    """
    cache_key = discovery_cache_key(provider)
    discovery = cache.get(cache_key)
    if discovery is None:
        issuer = provider.issuer.rstrip("/")
        try:
            response = requests.get(
                f"{issuer}/.well-known/openid-configuration", timeout=HTTP_TIMEOUT
            )
            response.raise_for_status()
            discovery = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise OidcClientError(f"discovery fetch from {issuer} failed: {exc}") from exc
        cache.set(cache_key, discovery, DISCOVERY_CACHE_TTL)

    return {
        "authorization_endpoint": provider.authorization_endpoint
        or discovery.get("authorization_endpoint"),
        "token_endpoint": provider.token_endpoint or discovery.get("token_endpoint"),
        "jwks_uri": provider.jwks_uri or discovery.get("jwks_uri"),
    }


def build_authorization_url(provider, discovery: dict, redirect_uri: str, state: str, nonce: str) -> str:
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


def exchange_code_for_tokens(provider, discovery: dict, code: str, redirect_uri: str) -> dict:
    try:
        client_secret = provider.client_secret
    except InvalidToken as exc:
        raise OidcClientError(
            "stored client secret cannot be decrypted (SECRET_KEY changed?); re-enter it in SSO settings"
        ) from exc
    try:
        response = requests.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": provider.client_id,
                "client_secret": client_secret,
            },
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        body = getattr(getattr(exc, "response", None), "text", "")[:300]
        raise OidcClientError(f"token exchange failed: {exc} {body}") from exc


def verify_id_token(provider, discovery: dict, id_token: str, expected_nonce: str) -> dict:
    """
    Verify signature, issuer, audience, expiry, and nonce. Returns the
    claims dict on success; raises OidcClientError on any failure.

    `algorithms=["RS256"]` is asserted explicitly -- never read from the
    token's own header -- which is what closes the algorithm-confusion
    attack class (a token whose header claims a different/weaker
    algorithm than the one actually used to sign it).
    """
    try:
        jwks_client = jwt.PyJWKClient(discovery["jwks_uri"], timeout=HTTP_TIMEOUT)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=provider.client_id,
            issuer=provider.issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
            leeway=CLOCK_SKEW_LEEWAY,
        )
    except jwt.PyJWTError as exc:
        raise OidcClientError(f"ID token rejected: {exc}") from exc

    if claims.get("nonce") != expected_nonce:
        raise OidcClientError("ID token nonce mismatch")
    # OIDC Core 3.1.3.7: with several audiences, azp must name this client.
    aud = claims.get("aud")
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != provider.client_id:
        raise OidcClientError("ID token has multiple audiences and azp is not this client")

    # Not every IdP sends email_verified (Google always does; Okta/Entra
    # often omit it). Absent is treated as trusted -- the email came from
    # the IdP's own signed ID token, already verified above -- but an
    # explicit `false` is a hard refusal.
    if claims.get("email_verified") is False:
        raise OidcClientError("IdP reports the email as unverified")

    return claims
