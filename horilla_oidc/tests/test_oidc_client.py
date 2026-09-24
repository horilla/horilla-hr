"""
The security-critical piece of horilla_oidc, proven before any Django view
exists: verify_id_token must accept a genuinely valid token and reject
every way a forged or stale one could otherwise pass. No network access --
a locally generated RSA keypair stands in for the IdP's signing key, and
PyJWKClient's fetch is patched to serve it instead of an HTTP request.
"""

import json
import time
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase

from horilla_oidc.oidc_client import OidcClientError, verify_id_token

ISSUER = "https://idp.test"
CLIENT_ID = "test-client"
KID = "test-key-1"


class VerifyIdTokenTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        alg = jwt.algorithms.RSAAlgorithm(jwt.algorithms.RSAAlgorithm.SHA256)
        jwk = json.loads(alg.to_jwk(cls.private_key.public_key()))
        jwk.update(kid=KID, use="sig", alg="RS256")
        cls.jwks = {"keys": [jwk]}

        # Same keypair, different RSA instance -- stands in for "an attacker's
        # own key," used by the tampered-signature test.
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        # PyJWKClient fetches its JWKS via urllib internally; patching the
        # one method that does that HTTP call is the clean seam -- no need
        # to mock urllib itself.
        patcher = mock.patch(
            "jwt.jwks_client.PyJWKClient.fetch_data", return_value=self.jwks
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.provider = SimpleNamespace(client_id=CLIENT_ID, issuer=ISSUER)
        self.discovery = {"jwks_uri": "https://idp.test/jwks"}
        self.nonce = "expected-nonce-value"

    def _claims(self, **overrides):
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "user-1",
            "email": "person@example.com",
            "nonce": self.nonce,
            "iat": now,
            "exp": now + 300,
        }
        claims.update(overrides)
        return claims

    def _token(self, claims, key=None, **encode_kwargs):
        return jwt.encode(claims, key or self.private_key, algorithm="RS256", headers={"kid": KID}, **encode_kwargs)

    def test_valid_token_is_accepted(self):
        token = self._token(self._claims())
        claims = verify_id_token(self.provider, self.discovery, token, self.nonce)
        self.assertEqual(claims["email"], "person@example.com")

    def test_tampered_signature_is_rejected(self):
        # Signed with a different key than the one in the JWKS -- exactly
        # what an attacker holds if they don't control the real IdP.
        token = self._token(self._claims(), key=self.other_key)
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_wrong_audience_is_rejected(self):
        token = self._token(self._claims(aud="someone-elses-client-id"))
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_wrong_issuer_is_rejected(self):
        token = self._token(self._claims(iss="https://not-the-real-idp.test"))
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_expired_token_is_rejected(self):
        now = int(time.time())
        token = self._token(self._claims(iat=now - 3600, exp=now - 1800))
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_wrong_nonce_is_rejected(self):
        token = self._token(self._claims(nonce="a-different-nonce"))
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_explicit_email_not_verified_is_rejected(self):
        token = self._token(self._claims(email_verified=False))
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, token, self.nonce)

    def test_missing_email_verified_claim_is_accepted(self):
        # Okta/Entra often omit this claim entirely. Absent is trusted
        # (the email came from the IdP's own signed token); only an
        # explicit `false` is a refusal.
        token = self._token(self._claims())
        claims = verify_id_token(self.provider, self.discovery, token, self.nonce)
        self.assertNotIn("email_verified", claims)

    def test_alg_none_is_rejected(self):
        """
        The classic algorithm-confusion attack: a token whose header claims
        no signature is required at all. verify_id_token pins
        algorithms=["RS256"] explicitly rather than trusting the token's own
        header, so PyJWT refuses this before any key lookup happens.
        """
        unsigned = jwt.encode(self._claims(), key="", algorithm="none")
        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, unsigned, self.nonce)

    def test_hmac_signed_with_public_key_is_rejected(self):
        """
        The other half of algorithm confusion: an attacker who knows the
        IdP's public RSA key re-signs the token as HS256, using that public
        key (which is not secret) as the HMAC secret. Pinning
        algorithms=["RS256"] refuses this outright -- HS256 is never in the
        allowed list, regardless of what the token's header claims.

        Built by hand with raw hmac/base64, not jwt.encode(): PyJWT's own
        encode() already refuses to use an asymmetric key as an HMAC secret
        (a second, independent guard on the encoding side), which would
        block this test from ever constructing the attack payload at all.
        The point here is that verify_id_token's *decode* side rejects this
        independently of whether the forging tool has that same guard --
        not every JWT library does, which is exactly what past real-world
        algorithm-confusion CVEs exploited.
        """
        import base64
        import hmac
        import json as json_module

        public_pem = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

        header = b64url(json_module.dumps({"alg": "HS256", "kid": KID}).encode())
        payload = b64url(json_module.dumps(self._claims()).encode())
        signing_input = f"{header}.{payload}".encode()
        signature = hmac.new(public_pem, signing_input, "sha256").digest()
        forged = f"{header}.{payload}.{b64url(signature)}"

        with self.assertRaises(OidcClientError):
            verify_id_token(self.provider, self.discovery, forged, self.nonce)
