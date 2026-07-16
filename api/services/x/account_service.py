"""OAuth 2.0 PKCE and token encryption helpers for X accounts."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from config import x_config


AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"


@dataclass
class PendingOAuth:
    owner_user_id: str
    code_verifier: str
    redirect_uri: str
    created_at: int


class OAuthStateStore:
    """Short-lived single-process PKCE state store for the first release."""

    def __init__(self, ttl_seconds: Optional[int] = None) -> None:
        self.ttl_seconds = int(ttl_seconds or x_config.X_OAUTH_STATE_TTL_SECONDS)
        self._items: Dict[str, PendingOAuth] = {}

    def issue(self, *, owner_user_id: str, redirect_uri: str) -> tuple[str, str]:
        self.purge_expired()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        self._items[state] = PendingOAuth(
            owner_user_id=owner_user_id,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            created_at=int(time.time()),
        )
        return state, verifier

    def consume(self, state: str) -> PendingOAuth:
        self.purge_expired()
        pending = self._items.pop(state, None)
        if pending is None:
            raise ValueError("OAuth state is invalid or expired")
        return pending

    def purge_expired(self) -> None:
        cutoff = int(time.time()) - self.ttl_seconds
        expired = [key for key, item in self._items.items() if item.created_at < cutoff]
        for key in expired:
            self._items.pop(key, None)


oauth_state_store = OAuthStateStore()


def build_oauth_authorization_url(
    *,
    owner_user_id: str,
    redirect_uri: Optional[str] = None,
    scopes: str = "tweet.read users.read tweet.write offline.access",
) -> Dict[str, str]:
    client_id = x_config.X_CLIENT_ID.strip()
    redirect_uri = (redirect_uri or x_config.X_REDIRECT_URI).strip()
    if not client_id or not redirect_uri:
        raise ValueError("X_CLIENT_ID and X_REDIRECT_URI must be configured")
    state, verifier = oauth_state_store.issue(
        owner_user_id=owner_user_id,
        redirect_uri=redirect_uri,
    )
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return {"authorization_url": f"{AUTHORIZE_URL}?{query}", "state": state}


async def exchange_oauth_code(
    *,
    code: str,
    state: str,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    pending = oauth_state_store.consume(state)
    client_id = x_config.X_CLIENT_ID.strip()
    if not client_id:
        raise ValueError("X_CLIENT_ID is not configured")
    endpoint = _oauth_token_endpoint()
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": pending.redirect_uri,
        "code_verifier": pending.code_verifier,
    }
    auth = None
    if x_config.X_CLIENT_SECRET:
        auth = httpx.BasicAuth(client_id, x_config.X_CLIENT_SECRET)
    client = http_client or httpx.AsyncClient(timeout=30)
    owns_client = http_client is None
    try:
        response = await client.post(
            endpoint,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error_description") or response.json().get("error")
            except ValueError:
                detail = "X OAuth token exchange failed"
            raise RuntimeError(str(detail or "X OAuth token exchange failed"))
        payload = response.json()
        payload["owner_user_id"] = pending.owner_user_id
        return payload
    finally:
        if owns_client:
            await client.aclose()


async def refresh_oauth_token(
    refresh_token: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    client_id = x_config.X_CLIENT_ID.strip()
    if not client_id:
        raise ValueError("X_CLIENT_ID is not configured")
    if not refresh_token:
        raise ValueError("refresh token is required")
    endpoint = _oauth_token_endpoint()
    auth = httpx.BasicAuth(client_id, x_config.X_CLIENT_SECRET) if x_config.X_CLIENT_SECRET else None
    client = http_client or httpx.AsyncClient(timeout=30)
    owns_client = http_client is None
    try:
        response = await client.post(
            endpoint,
            data={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "client_id": client_id,
            },
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("error_description") or body.get("error")
            except ValueError:
                detail = "X OAuth token refresh failed"
            raise RuntimeError(str(detail or "X OAuth token refresh failed"))
        return response.json()
    finally:
        if owns_client:
            await client.aclose()


def encrypt_token(token: str, key: Optional[str] = None) -> str:
    if not token:
        return ""
    return _fernet(key).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str, key: Optional[str] = None) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("encrypted X token could not be decrypted") from exc


def _fernet(key: Optional[str] = None) -> Fernet:
    raw_key = (key or x_config.TOKEN_ENCRYPTION_KEY or os.getenv("TOKEN_ENCRYPTION_KEY", "")).strip()
    if not raw_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(raw_key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc


def _oauth_token_endpoint() -> str:
    base_url = x_config.X_API_BASE_URL.rstrip("/")
    return (
        f"{base_url}/oauth2/token"
        if base_url.endswith("/2")
        else f"{base_url}/2/oauth2/token"
    )
