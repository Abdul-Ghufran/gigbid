"""Users and sessions: bcrypt password hashes, short-lived JWT bearer sessions, tenant = user id."""
from __future__ import annotations

import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.db import User, session
from common.settings import get_settings
from common.tracing import user_id_var

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def issue_token(user_id: str, hours: int = 72) -> str:
    now = dt.datetime.now(dt.UTC)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + dt.timedelta(hours=hours)}, get_settings().app_secret_key, "HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if not creds:
        raise HTTPException(401, "not signed in")
    try:
        sub = jwt.decode(creds.credentials, get_settings().app_secret_key, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired session") from None
    with session() as s:
        u = s.get(User, sub)
        if not u:
            raise HTTPException(401, "unknown user")
        s.expunge(u)
    user_id_var.set(u.id)
    return u


def create_user(email: str, password: str, display_name: str = "", persona_key: str | None = None) -> User:
    with session() as s:
        if s.query(User).filter_by(email=email.lower()).first():
            raise HTTPException(409, "email already registered")
        u = User(email=email.lower(), password_hash=hash_password(password), display_name=display_name or email.split("@")[0],
                 persona_key=persona_key)
        s.add(u)
        s.flush()
        s.expunge(u)
        return u
