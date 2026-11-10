"""Encryption at rest, signed service tokens and PII masking."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

from cryptography.fernet import Fernet

from common.settings import get_settings


# ------------------------------------------------------------------ encryption (OAuth tokens etc.)
def _fernet() -> Fernet:
    key = hashlib.sha256(("fernet:" + get_settings().app_secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ------------------------------------------------------- signed per-user tokens for MCP HTTP auth
def sign_user_token(user_id: str, scopes: list[str], ttl_s: int = 3600) -> str:
    payload = {"sub": user_id, "scopes": scopes, "exp": int(time.time()) + ttl_s}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(get_settings().mcp_shared_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"gbt.{body}.{sig}"


def verify_user_token(token: str) -> dict | None:
    try:
        prefix, body, sig = token.split(".")
        if prefix != "gbt":
            return None
        good = hmac.new(get_settings().mcp_shared_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


# --------------------------------------------------------------------------------- PII masking
_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "[IBAN]"),
    (re.compile(r"\b(?:0x[a-fA-F0-9]{40}|T[1-9A-HJ-NP-Za-km-z]{33}|bc1[a-z0-9]{25,39})\b"), "[WALLET]"),
    (re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d\b"), "[PHONE]"),
    (re.compile(r"@[A-Za-z0-9_]{4,}"), "[HANDLE]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]+"), r"\1[TOKEN]"),
    (re.compile(r"\b(gsk|sk|ghp|gho|pk-lf|sk-lf)[-_][A-Za-z0-9_\-]{10,}\b"), "[SECRET]"),
]


def mask_pii(text: str) -> str:
    if not isinstance(text, str):
        return text
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    return text


def mask_obj(obj):
    """Recursively mask strings inside dicts / lists (used before anything is logged or traced)."""
    if isinstance(obj, str):
        return mask_pii(obj)
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in {"token", "access_token", "refresh_token", "password", "authorization", "api_key"} else mask_obj(v))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(x) for x in obj]
    return obj
