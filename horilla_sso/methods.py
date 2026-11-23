"""Single sign-on (OpenID Connect authorization-code flow) shared by every provider, with no HTTP views."""

import secrets

import jwt
import requests
from jwt import PyJWKClient

from employee.models import Employee
from horilla_sso import providers
from horilla_sso.providers import AUTHORITY, GUID, SSOError  # noqa: F401  (re-exported)


def same(a, b):
    """Constant-time equality of two strings, whatever characters they hold."""
    return secrets.compare_digest(str(a).encode(), str(b).encode())


def pinned(config):
    """True when a Microsoft app accepts one specific directory, which is what makes its ``email`` claim trustworthy."""
    return providers.PROVIDERS["microsoft"].pinned(config)


def build_authorization_url(config, redirect_uri):
    """Returns ``(url, state, nonce)``; the state and nonce are kept in the session to check the reply."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    return (
        providers.for_config(config).authorization_url(
            config, redirect_uri, state, nonce
        ),
        state,
        nonce,
    )


def exchange_code(config, code, redirect_uri):
    """Trades the code for the ID token."""
    provider = providers.for_config(config)
    try:
        response = requests.post(
            provider.token_url(config),
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                **provider.token_data(config),
            },
            timeout=15,
        )
    except requests.RequestException as error:
        raise SSOError(
            f"{provider.label} Could Not Be Reached. Please Try Again."
        ) from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if (
        response.status_code != 200
        or not isinstance(body.get("id_token"), str)
        or not body["id_token"]
    ):
        raise SSOError(f"{provider.label} Did Not Accept The Sign-In.")
    return body["id_token"]


def _signing_key(id_token, jwks_url):
    """The public key of the provider that signed this token."""
    return PyJWKClient(jwks_url, timeout=15).get_signing_key_from_jwt(id_token).key


def validate_id_token(config, id_token, nonce):
    """The claims of an ID token signed by the provider for this app and sign-in; else ``SSOError``."""
    provider = providers.for_config(config)
    unverified = f"The {provider.label} Sign-In Could Not Be Verified."
    try:
        key = _signing_key(id_token, provider.jwks_url(config))
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=config.client_id,
            leeway=60,
            options={"verify_iss": False, "require": ["exp", "aud", "iss"]},
        )
    except Exception as error:
        raise SSOError(unverified) from error
    provider.check_claims(config, claims)
    if not nonce or not same(claims.get("nonce", ""), nonce):
        raise SSOError(unverified)
    return claims


def emails_in(claims, trust_email=True, provider="microsoft"):
    """The distinct, lower-cased email-like claims of an account, as that provider trusts them."""
    return providers.PROVIDERS[provider].emails_in(claims, trust_email)


def find_employee(claims, trust_email=True, provider="microsoft"):
    """
    The one employee this account belongs to, by email then work email, or ``None``.

    More than one employee for the same email counts as no match rather than a guess.
    """
    for email in emails_in(claims, trust_email, provider):
        matches = list(Employee.objects.entire().filter(email__iexact=email)[:2])
        if not matches:
            matches = list(
                Employee.objects.entire().filter(
                    employee_work_info__email__iexact=email
                )[:2]
            )
        if len(matches) == 1:
            return matches[0]
    return None


def domain_allowed(config, claims):
    """True when the account may sign in under this config's domain rules."""
    return providers.for_config(config).domain_allowed(config, claims)
