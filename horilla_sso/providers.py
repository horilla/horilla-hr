"""The sign-in services (Microsoft, Google): what differs between them, so the flow itself can be shared."""

import re
from urllib.parse import urlencode

from horilla_sso.models import GoogleSSOSettings, MicrosoftSSOSettings

AUTHORITY = "https://login.microsoftonline.com"
GUID = re.compile(r"^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I)
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class SSOError(Exception):
    """A sign-in that cannot go ahead; the message is safe to show."""


def _emails(claims, names):
    found = []
    for name in names:
        value = str(claims.get(name) or "").strip().lower()
        if "@" in value and value not in found:
            found.append(value)
    return found


class Provider:
    """One sign-in service; subclasses say where to go and which claims to trust."""

    key = ""
    label = ""
    model = None
    scope = "openid profile email"
    login_url = callback_url = settings_url = ""

    def config(self):
        return self.model.current()

    def authorize_url(self, config):
        raise NotImplementedError

    def token_url(self, config):
        raise NotImplementedError

    def jwks_url(self, config):
        raise NotImplementedError

    def authorize_params(self, config):
        return {}

    def token_data(self, config):
        return {}

    def check_claims(self, config, claims):
        """Provider rules on the claims of a token that is already signed and current; else ``SSOError``."""

    def trust_email(self, config):
        return True

    def emails_in(self, claims, trust_email=True):
        return _emails(claims, ("email",))

    def domain_allowed(self, config, claims):
        allowed = config.domains()
        if not allowed:
            return True
        return any(
            email.rsplit("@", 1)[1] in allowed
            for email in self.emails_in(claims, self.trust_email(config))
        )

    def authorization_url(self, config, redirect_uri, state, nonce):
        query = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": self.scope,
            "state": state,
            "nonce": nonce,
            **self.authorize_params(config),
        }
        return f"{self.authorize_url(config)}?{urlencode(query)}"


class Microsoft(Provider):
    key = "microsoft"
    label = "Microsoft"
    model = MicrosoftSSOSettings
    login_url = "microsoft-sso-login"
    callback_url = "microsoft-sso-callback"
    settings_url = "microsoft-sso-settings"

    def authorize_url(self, config):
        return f"{AUTHORITY}/{config.tenant_id}/oauth2/v2.0/authorize"

    def token_url(self, config):
        return f"{AUTHORITY}/{config.tenant_id}/oauth2/v2.0/token"

    def jwks_url(self, config):
        return f"{AUTHORITY}/{config.tenant_id}/discovery/v2.0/keys"

    def authorize_params(self, config):
        return {"response_mode": "query", "prompt": "select_account"}

    def token_data(self, config):
        return {"scope": self.scope}

    def pinned(self, config):
        """True when the app accepts one specific directory, which is what makes the ``email`` claim trustworthy."""
        return bool(GUID.match(config.tenant_id or ""))

    def trust_email(self, config):
        return self.pinned(config)

    def check_claims(self, config, claims):
        tenant = claims.get("tid", "")
        if not tenant or claims.get("iss") != f"{AUTHORITY}/{tenant}/v2.0":
            raise SSOError("The Microsoft Sign-In Could Not Be Verified.")
        if GUID.match(config.tenant_id) and tenant.lower() != config.tenant_id.lower():
            raise SSOError("This Microsoft Account Is Not From The Allowed Directory.")

    def emails_in(self, claims, trust_email=True):
        """
        The distinct, lower-cased email-like claims of a Microsoft account.

        The ``email`` claim is whatever the account's own directory says, so it is only read when ``trust_email``
        is true (the app is pinned to one directory). The sign-in name (``preferred_username``, ``upn``) must
        belong to a domain its directory has verified, so it is always read.
        """
        names = (
            ("email", "preferred_username", "upn")
            if trust_email
            else ("preferred_username", "upn")
        )
        return _emails(claims, names)


class Google(Provider):
    key = "google"
    label = "Google"
    model = GoogleSSOSettings
    login_url = "google-sso-login"
    callback_url = "google-sso-callback"
    settings_url = "google-sso-settings"

    def authorize_url(self, config):
        return "https://accounts.google.com/o/oauth2/v2/auth"

    def token_url(self, config):
        return "https://oauth2.googleapis.com/token"

    def jwks_url(self, config):
        return "https://www.googleapis.com/oauth2/v3/certs"

    def authorize_params(self, config):
        params = {"prompt": "select_account"}
        domains = config.domains()
        if len(domains) == 1:
            params["hd"] = domains[
                0
            ]  # only a hint for Google's chooser; the token is what is checked
        return params

    @staticmethod
    def _verified(claims):
        verified = claims.get("email_verified")
        return verified is True or verified == "true"

    def check_claims(self, config, claims):
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise SSOError("The Google Sign-In Could Not Be Verified.")
        if not self._verified(claims):
            raise SSOError("This Google Account's Email Is Not Verified.")

    def emails_in(self, claims, trust_email=True):
        return _emails(claims, ("email",)) if self._verified(claims) else []

    def domain_allowed(self, config, claims):
        """Only a Workspace account of an allowed domain: its ``hd`` claim and its email domain must both match."""
        allowed = config.domains()
        hosted = str(claims.get("hd") or "").strip().lower()
        if not allowed or hosted not in allowed:
            return False
        return any(
            email.rsplit("@", 1)[1] == hosted for email in self.emails_in(claims)
        )


PROVIDERS = {provider.key: provider for provider in (Microsoft(), Google())}


def for_config(config):
    return PROVIDERS[config.provider_key]


def ready_providers():
    """``(provider, config)`` for each service that is switched on and fully set up."""
    ready = []
    for provider in PROVIDERS.values():
        config = provider.config()
        if config and config.is_ready():
            ready.append((provider, config))
    return ready
