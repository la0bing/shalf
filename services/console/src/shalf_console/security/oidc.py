"""OpenID Connect authorization-code flow with PKCE.

Works with any standards-compliant provider: Okta, Microsoft Entra ID,
Google, Keycloak, Auth0, Dex (which also bridges SAML and LDAP)...
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from shalf.core import ShalfError
from shalf_console.settings import OIDCProvider

# Asymmetric algorithms only: HS* would let anyone holding the client secret mint tokens.
_ALLOWED_ALGS = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"}


class OIDCError(ShalfError):
    pass


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


class OIDCClient:
    def __init__(self, provider: OIDCProvider, http: httpx.Client, cache_seconds: int = 3600):
        self.provider = provider
        self.http = http
        self.cache_seconds = cache_seconds
        self._metadata: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None

    # -- discovery ---------------------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        if self._metadata and time.monotonic() - self._metadata[0] < self.cache_seconds:
            return self._metadata[1]
        url = self.provider.issuer.rstrip("/") + "/.well-known/openid-configuration"
        response = self.http.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("issuer", "").rstrip("/") != self.provider.issuer.rstrip("/"):
            raise OIDCError(f"Issuer mismatch in discovery document of {self.provider.id}")
        self._metadata = (time.monotonic(), data)
        return data

    def _jwk_set(self, refresh: bool = False) -> dict[str, Any]:
        if not refresh and self._jwks and time.monotonic() - self._jwks[0] < self.cache_seconds:
            return self._jwks[1]
        response = self.http.get(self.metadata()["jwks_uri"], timeout=10)
        response.raise_for_status()
        self._jwks = (time.monotonic(), response.json())
        return self._jwks[1]

    # -- flow --------------------------------------------------------------------
    def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, challenge: str
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.provider.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.provider.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.metadata()['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.provider.client_id,
            "code_verifier": verifier,
        }
        if self.provider.client_secret:
            data["client_secret"] = self.provider.client_secret
        response = self.http.post(self.metadata()["token_endpoint"], data=data, timeout=10)
        if response.status_code != 200:
            raise OIDCError(f"Token exchange failed ({response.status_code})")
        tokens = response.json()
        if "id_token" not in tokens:
            raise OIDCError("Provider returned no id_token")
        return tokens

    def verify_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise OIDCError(f"Malformed id_token: {exc}") from exc
        alg = header.get("alg")
        if alg not in _ALLOWED_ALGS:
            raise OIDCError(f"id_token algorithm {alg!r} not allowed")

        key = self._find_key(header.get("kid")) or self._find_key(header.get("kid"), refresh=True)
        if key is None:
            raise OIDCError("id_token signed with an unknown key")
        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=[alg],
                audience=self.provider.client_id,
                issuer=self.metadata()["issuer"],
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
                leeway=60,
            )
        except jwt.PyJWTError as exc:
            raise OIDCError(f"Invalid id_token: {exc}") from exc
        if claims.get("nonce") != nonce:
            raise OIDCError("id_token nonce mismatch")
        return claims

    def userinfo(self, access_token: str) -> dict[str, Any]:
        endpoint = self.metadata().get("userinfo_endpoint")
        if not endpoint:
            return {}
        response = self.http.get(
            endpoint, headers={"Authorization": f"Bearer {access_token}"}, timeout=10
        )
        return response.json() if response.status_code == 200 else {}

    def _find_key(self, kid: str | None, refresh: bool = False) -> Any:
        for jwk in self._jwk_set(refresh).get("keys", []):
            if kid is None or jwk.get("kid") == kid:
                try:
                    return jwt.PyJWK(jwk).key
                except jwt.PyJWTError:
                    continue
        return None

    # -- identity ----------------------------------------------------------------
    def identity(self, claims: dict[str, Any], extra: dict[str, Any]) -> tuple[str, str, list[str]]:
        """``(email, name, groups)`` from id_token claims (+ userinfo)."""
        merged = {**extra, **claims}
        email = str(merged.get(self.provider.email_claim) or "").lower()
        if not email:
            raise OIDCError(f"No {self.provider.email_claim!r} claim; add the `email` scope")
        if merged.get("email_verified") is False:
            raise OIDCError("Email address not verified by the identity provider")
        domains = [d.lower() for d in self.provider.allowed_domains]
        if domains and email.rsplit("@", 1)[-1] not in domains:
            raise OIDCError("Email domain not allowed")
        groups = merged.get(self.provider.groups_claim) or []
        if isinstance(groups, str):
            groups = [groups]
        name = str(merged.get(self.provider.name_claim) or email)
        return email, name, [str(g) for g in groups]
