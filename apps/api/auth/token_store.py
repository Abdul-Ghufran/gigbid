"""Encrypted per-user marketplace credentials and the Upwork OAuth 2.1 flow.

Tokens are Fernet-encrypted at rest (key derived from APP_SECRET_KEY), never logged (mask_obj redacts token
fields) and always looked up by user id (tenant scoping).  The OAuth flow follows the MCP authorization spec:
protected-resource metadata (RFC 9728) -> authorization-server metadata (RFC 8414) -> dynamic client
registration (RFC 7591) when no client id is configured -> authorization code + PKCE (S256).
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode, urlparse

import httpx

from common.db import MarketplaceAccount, OAuthState, session
from common.security import decrypt, encrypt
from common.settings import get_settings


def save_account(user_id: str, provider: str, creds: dict) -> str:
    with session() as s:
        for old in s.query(MarketplaceAccount).filter_by(user_id=user_id).all():
            old.status = "replaced"
        a = MarketplaceAccount(user_id=user_id, provider=provider, encrypted_token=encrypt(json.dumps(creds)))
        s.add(a)
        s.flush()
        return a.id


def connected_accounts(user_id: str) -> list[dict]:
    with session() as s:
        return [{"id": a.id, "provider": a.provider, "status": a.status, "connected_at": a.created_at.isoformat()}
                for a in s.query(MarketplaceAccount).filter_by(user_id=user_id).all()]


def disconnect(user_id: str, account_id: str):
    with session() as s:
        a = s.get(MarketplaceAccount, account_id)
        if a and a.user_id == user_id:
            a.status = "disconnected"


def get_credentials(user_id: str) -> dict | None:
    with session() as s:
        a = s.query(MarketplaceAccount).filter_by(user_id=user_id, status="connected").first()
        return json.loads(decrypt(a.encrypted_token)) if a else None


async def _discover(mcp_url: str) -> dict:
    u = urlparse(mcp_url)
    base = f"{u.scheme}://{u.netloc}"
    async with httpx.AsyncClient(timeout=15) as h:
        pr = await h.get(f"{base}/.well-known/oauth-protected-resource")
        auth_server = pr.json()["authorization_servers"][0] if pr.status_code == 200 else base
        meta = await h.get(auth_server.rstrip("/") + "/.well-known/oauth-authorization-server")
        meta.raise_for_status()
        return meta.json()


async def upwork_authorize_url(user_id: str, redirect_uri: str) -> str:
    s = get_settings()
    meta = await _discover(s.upwork_mcp_url)
    client_id = s.upwork_client_id
    client_secret = s.upwork_client_secret
    if not client_id and meta.get("registration_endpoint"):
        async with httpx.AsyncClient(timeout=15) as h:
            r = await h.post(meta["registration_endpoint"], json={
                "client_name": "GigBid", "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none"})
            r.raise_for_status()
            client_id, client_secret = r.json()["client_id"], r.json().get("client_secret", "")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(24)
    with session() as db:
        db.add(OAuthState(state=state, user_id=user_id, encrypted_verifier=encrypt(verifier),
                          meta={"token_endpoint": meta["token_endpoint"], "client_id": client_id,
                                "client_secret": encrypt(client_secret) if client_secret else "", "redirect_uri": redirect_uri}))
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256", "resource": s.upwork_mcp_url}
    return meta["authorization_endpoint"] + "?" + urlencode(q)


async def upwork_callback(code: str, state: str) -> str:
    with session() as db:
        st = db.get(OAuthState, state)
        if not st:
            raise ValueError("unknown OAuth state")
        user_id, verifier, meta = st.user_id, decrypt(st.encrypted_verifier), st.meta
        db.delete(st)
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": meta["redirect_uri"], "client_id": meta["client_id"],
            "code_verifier": verifier, "resource": get_settings().upwork_mcp_url}
    if meta.get("client_secret"):
        data["client_secret"] = decrypt(meta["client_secret"])
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.post(meta["token_endpoint"], data=data)
        r.raise_for_status()
        tok = r.json()
    save_account(user_id, "upwork", {k: tok.get(k) for k in ("access_token", "refresh_token", "expires_in", "scope")})
    return user_id
