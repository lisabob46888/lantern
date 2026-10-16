"""User lists: ix (indices), co (companies), ind (industries). Stored in SQLite."""
from __future__ import annotations

from app.services import securities as S
from app.store import db

LISTS = ("ix", "co", "ind")
# The index list starts with the registry's indices; company and industry lists start empty.
DEFAULTS = {"ix": list(S.INDEX_BY_ID.keys()), "co": [], "ind": []}


def get(name: str) -> list[str]:
    row = db.one("SELECT items FROM watchlists WHERE name=?", (name,))
    return db.loads(row["items"], []) if row else list(DEFAULTS.get(name, []))


def put(name: str, items: list[str]) -> list[str]:
    if name not in LISTS:
        raise ValueError(f"unknown list {name}")
    clean = list(dict.fromkeys(i for i in items if isinstance(i, str) and i))
    db.execute("INSERT INTO watchlists(name, items) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET items=excluded.items",
               (name, db.dumps(clean)))
    return clean


def all_lists() -> dict[str, list[str]]:
    return {n: get(n) for n in LISTS}


def watched_securities() -> list[str]:
    return list(dict.fromkeys(get("ix") + get("co")))
