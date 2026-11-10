"""Relational store (Postgres in docker / production, SQLite fallback for tests).

Every user-owned row carries `user_id` (the tenant key) and every query in the API filters on it.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from contextlib import contextmanager

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from common.settings import ROOT, get_settings


def _now():
    return dt.datetime.now(dt.UTC)


def _id():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    persona_key: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ai | web | data | None (own profile)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    hourly_rate: Mapped[float] = mapped_column(Float, default=40)
    min_project: Mapped[float] = mapped_column(Float, default=300)
    weekly_connects_budget: Mapped[int] = mapped_column(Integer, default=60)
    autonomy: Mapped[str] = mapped_column(String(20), default="suggest")  # suggest | auto_skip_low_fit (never auto-send)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    saved_searches: Mapped[list] = mapped_column(JSON, default=list)  # [{id, query, category, interval_minutes}]


class MarketplaceAccount(Base):
    __tablename__ = "marketplace_accounts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # gigsim | upwork
    encrypted_token: Mapped[str] = mapped_column(Text)  # Fernet-encrypted JSON (access/refresh tokens)
    status: Mapped[str] = mapped_column(String(20), default="connected")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32))
    encrypted_verifier: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class JobRecord(Base):
    """One row per (user, marketplace job): the inbox.  Unique key gives idempotent scouting."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # f"{user_id}:{job_id}"
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)  # near-duplicate detection
    duplicate_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="new")
    # new | analysing | skipped | watch | awaiting_approval | approved | submitted | rejected | needs_attention | dead_letter
    thread_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # fit, risk, decision, price for the inbox
    pipeline_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # f"{user_id}:{marketplace thread id}"
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    marketplace_thread_id: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="new")
    last_seen_message: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Run(Base):
    """One graph execution (or resume).  Node events are kept in RunEvent for the run viewer."""
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    graph: Mapped[str] = mapped_column(String(20))  # bid | conversation
    thread_id: Mapped[str] = mapped_column(String(80), index=True)
    trace_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | interrupted | done | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # node_start | node_end | tool_call | llm | interrupt | error
    node: Mapped[str] = mapped_column(String(40), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    """Append-only (no UPDATE/DELETE path exists in code; a DB trigger enforces it on Postgres)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    server: Mapped[str] = mapped_column(String(30))
    tool: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    trace_id: Mapped[str] = mapped_column(String(40), index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)


class PortfolioUpload(Base):
    __tablename__ = "portfolio_uploads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # cv | case_study | repo | review | proposal
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Edit(Base):
    """Raw user edits to drafts (diffs).  NOT memory: promotion rules decide what becomes memory."""
    __tablename__ = "edits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    job_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(20), default="")
    before: Mapped[str] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    diff: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


_engine = None
_Session = None


def engine():
    global _engine, _Session
    if _engine is None:
        url = get_settings().sqlalchemy_url
        kw = {}
        if url.startswith("sqlite"):
            (ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
            kw["connect_args"] = {"check_same_thread": False}
        else:
            kw.update(pool_pre_ping=True, pool_size=5, max_overflow=5)
        _engine = create_engine(url, json_serializer=lambda o: json.dumps(o, default=str), **kw)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _pragma(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def init_db():
    eng = engine()
    Base.metadata.create_all(eng)
    if eng.dialect.name == "postgresql":
        with eng.begin() as c:
            c.exec_driver_sql("""
            CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
            CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
              FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
            """)


@contextmanager
def session():
    engine()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def audit(user_id: str, server: str, tool: str, arguments: dict, result: dict, trace_id: str, ok: bool = True):
    from common.security import mask_obj

    with session() as s:
        s.add(AuditLog(user_id=user_id or "anonymous", server=server, tool=tool, arguments=mask_obj(arguments),
                       result=mask_obj(result), trace_id=trace_id or "", ok=ok))
