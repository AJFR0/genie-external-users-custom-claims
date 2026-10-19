"""Mint, cache and inspect service-principal OAuth tokens that carry a custom identity claim."""
from __future__ import annotations

import base64
import json
import threading
import time
from dataclasses import dataclass
from typing import Callable

import requests

from .claims import validate_claim


class TokenError(RuntimeError):
    """The token endpoint refused the request."""

    def __init__(self, status: int, body: str):
        super().__init__(f"token endpoint returned HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body

    @property
    def custom_claim_not_enabled(self) -> bool:
        return self.status == 403 and "custom_claim" in self.body.lower()


@dataclass(frozen=True)
class MintedToken:
    access_token: str
    expires_at: float
    claim: str | None


def mint_claim_token(host, client_id, client_secret, claim, *, scope="all-apis", http=None, now=time.time) -> MintedToken:
    """Request a client_credentials token for a service principal; send claim as custom_claim.

    Does NOT validate the claim: the isolation tests use it to send malformed values on purpose.
    Application code should go through ClaimTokenProvider.
    """
    data = {"grant_type": "client_credentials", "scope": scope}
    if claim is not None:
        data["custom_claim"] = claim
    poster = http or requests
    resp = poster.post(f"{host.rstrip('/')}/oidc/v1/token", data=data, auth=(client_id, client_secret), timeout=30)
    if resp.status_code != 200:
        raise TokenError(resp.status_code, resp.text)
    body = resp.json()
    return MintedToken(body["access_token"], now() + int(body.get("expires_in", 3600)), claim)


def decode_jwt_unverified(token: str) -> dict:
    """Decode a JWT header and payload for display. Never use the result to authorize anything."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT")

    def part(segment: str) -> dict:
        return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))

    return {"header": part(parts[0]), "payload": part(parts[1])}


class ClaimTokenProvider:
    """One cached token per claim, for one service principal. Tokens never leave the server."""

    def __init__(self, host, client_id, client_secret, *, refresh_margin_s: int = 300, minter=mint_claim_token, now=time.time):
        self._host = host
        self._client_id = client_id
        self._client_secret = client_secret
        self._margin = refresh_margin_s
        self._minter = minter
        self._now = now
        self._cache: dict[str, MintedToken] = {}
        self._lock = threading.Lock()

    @property
    def client_id(self) -> str:
        return self._client_id

    def token_for(self, claim: str) -> tuple[MintedToken, bool]:
        """Return (token, cache_hit). Validates the claim before any network call."""
        validate_claim(claim)
        with self._lock:
            cached = self._cache.get(claim)
            if cached is not None and cached.expires_at - self._now() > self._margin:
                return cached, True
        fresh = self._minter(self._host, self._client_id, self._client_secret, claim)
        with self._lock:
            self._cache[claim] = fresh
        return fresh, False

    def auth_for(self, claim: str) -> Callable[[], dict[str, str]]:
        """Return a headers factory bound to one claim, for StatementRunner and GenieClient."""
        def headers() -> dict[str, str]:
            token, _ = self.token_for(claim)
            return {"Authorization": f"Bearer {token.access_token}"}
        return headers

    def forget(self, claim: str) -> None:
        with self._lock:
            self._cache.pop(claim, None)

    def mint_raw(self, claim: str | None) -> MintedToken:
        """Mint without validation or caching. For the isolation tests only."""
        return self._minter(self._host, self._client_id, self._client_secret, claim)
