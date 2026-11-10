"""Upwork OAuth 2.1 flow against a mock authorization server: RFC 9728 / 8414 discovery, dynamic client registration,
PKCE S256 authorize URL, code exchange, and the token stored encrypted per user (never in plain text)."""
import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import httpx

from apps.api.auth import token_store
from common.db import MarketplaceAccount, User, init_db, session

init_db()
SEEN = {}


def handler(req: httpx.Request) -> httpx.Response:
    u = str(req.url)
    if u.endswith("/.well-known/oauth-protected-resource"):
        return httpx.Response(200, json={"authorization_servers": ["https://auth.example"]})
    if u.endswith("/.well-known/oauth-authorization-server"):
        return httpx.Response(200, json={"authorization_endpoint": "https://auth.example/authorize", "token_endpoint": "https://auth.example/token",
                                         "registration_endpoint": "https://auth.example/register"})
    if u.endswith("/register"):
        return httpx.Response(201, json={"client_id": "dyn-client"})
    if u.endswith("/token"):
        form = parse_qs(req.content.decode())
        SEEN["verifier"] = form["code_verifier"][0]
        return httpx.Response(200, json={"access_token": "at-secret", "refresh_token": "rt-secret", "expires_in": 3600})
    return httpx.Response(404)


async def test_oauth_flow_stores_encrypted_token(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(token_store.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with session() as s:
        u = User(email="oauth@test.io", password_hash="x")
        s.add(u)
        s.flush()
        uid = u.id
    url = await token_store.upwork_authorize_url(uid, "https://app/cb")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://auth.example/authorize") and q["client_id"] == ["dyn-client"] and q["code_challenge_method"] == ["S256"]
    assert await token_store.upwork_callback("code-1", q["state"][0]) == uid
    challenge = base64.urlsafe_b64encode(hashlib.sha256(SEEN["verifier"].encode()).digest()).decode().rstrip("=")
    assert challenge == q["code_challenge"][0], "PKCE verifier matches the challenge"
    with session() as s:
        acct = s.query(MarketplaceAccount).filter_by(user_id=uid, provider="upwork").one()
        assert "at-secret" not in acct.encrypted_token
    assert token_store.get_credentials(uid)["access_token"] == "at-secret"
    assert json.dumps(token_store.connected_accounts(uid)).find("at-secret") == -1
