"""SQLite store (WAL). One connection shared behind a lock — enough for a single-user app."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Iterable

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    story_id TEXT,
    kind TEXT NOT NULL,              -- news | filing | announcement | macro | rss
    source TEXT NOT NULL,            -- provider id, e.g. cls, em_global, finnhub_news, cninfo
    source_url TEXT,
    published_at INTEGER NOT NULL,   -- epoch ms, UTC
    received_at INTEGER NOT NULL,
    markets TEXT NOT NULL DEFAULT '[]',
    title TEXT NOT NULL,
    body TEXT,
    lang TEXT,
    symbols TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT UNIQUE,
    impact INTEGER,
    ai_comment TEXT,                 -- JSON {"en": ..., "zh": ...}
    enrich_state TEXT NOT NULL DEFAULT 'pending',  -- pending | done | skipped | failed
    industries TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_events_pub ON events(published_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_story ON events(story_id);
CREATE INDEX IF NOT EXISTS ix_events_enrich ON events(enrich_state);

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    headline TEXT NOT NULL,
    markets TEXT NOT NULL DEFAULT '[]',
    symbols TEXT NOT NULL DEFAULT '[]',
    impact INTEGER,
    sentiment TEXT,
    event_count INTEGER NOT NULL DEFAULT 1,
    shingles TEXT                     -- JSON list of hashed shingles for clustering
);
CREATE INDEX IF NOT EXISTS ix_stories_last ON stories(last_seen DESC);

CREATE TABLE IF NOT EXISTS ai_reads (
    story_id TEXT NOT NULL,
    tier TEXT NOT NULL,               -- fast | deep
    payload TEXT NOT NULL,            -- JSON, both languages inside
    model TEXT,
    prompt_version TEXT,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (story_id, tier)
);

CREATE TABLE IF NOT EXISTS reports (
    kind TEXT NOT NULL,               -- postmarket | ntk | industry | company_read | index_desc ...
    key TEXT NOT NULL,                -- e.g. "CN:2026-10-15"
    status TEXT NOT NULL,             -- pending | published | failed
    payload TEXT,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (kind, key)
);

CREATE TABLE IF NOT EXISTS calendar (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,               -- earnings | macro | policy
    market TEXT NOT NULL,
    title TEXT NOT NULL,
    scheduled_at INTEGER NOT NULL,    -- epoch ms UTC
    source TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS ix_calendar_at ON calendar(scheduled_at);

CREATE TABLE IF NOT EXISTS watchlists (
    name TEXT PRIMARY KEY,            -- ix | co | ind
    items TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    source TEXT,
    fetched_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    ok_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    last_ok INTEGER,
    last_error TEXT,
    last_error_at INTEGER
);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now_ms() -> int:
    return int(time.time() * 1000)


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            settings.db_path.parent.mkdir(parents=True, exist_ok=True)
            c = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.executescript(SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
            if "industries" not in cols:   # migration for databases created before industry tagging
                c.execute("ALTER TABLE events ADD COLUMN industries TEXT NOT NULL DEFAULT '[]'")
            _conn = c
        return _conn


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    with _lock:
        return conn().execute(sql, tuple(params))


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)


def loads(v: str | None, default: Any = None) -> Any:
    if v is None:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


# --- key/value cache with expiry (persisted, survives restarts) ---

def kv_get(key: str, allow_stale: bool = False) -> tuple[Any, str | None, int] | None:
    row = one("SELECT value, source, fetched_at, expires_at FROM kv WHERE key=?", (key,))
    if not row:
        return None
    if not allow_stale and row["expires_at"] < now_ms():
        return None
    return loads(row["value"]), row["source"], row["fetched_at"]


def kv_set(key: str, value: Any, source: str | None, ttl_s: float) -> None:
    t = now_ms()
    execute(
        "INSERT INTO kv(key,value,source,fetched_at,expires_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, source=excluded.source, "
        "fetched_at=excluded.fetched_at, expires_at=excluded.expires_at",
        (key, dumps(value), source, t, t + int(ttl_s * 1000)),
    )


def health(source: str, ok: bool, error: str | None = None) -> None:
    t = now_ms()
    if ok:
        execute(
            "INSERT INTO source_health(source, ok_count, last_ok) VALUES(?,1,?) "
            "ON CONFLICT(source) DO UPDATE SET ok_count=ok_count+1, last_ok=excluded.last_ok",
            (source, t),
        )
    else:
        execute(
            "INSERT INTO source_health(source, fail_count, last_error, last_error_at) VALUES(?,1,?,?) "
            "ON CONFLICT(source) DO UPDATE SET fail_count=fail_count+1, "
            "last_error=excluded.last_error, last_error_at=excluded.last_error_at",
            (source, (error or "")[:500], t),
        )
