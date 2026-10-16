"""Normalize -> dedupe -> cluster into stories -> store -> publish."""
from __future__ import annotations

import hashlib
import re

from app.hub import hub
from app.store import db

STORY_WINDOW_MS = 6 * 3600 * 1000
STORY_JACCARD = 0.45
MAX_AGE_MS = 3 * 86400 * 1000   # ignore items older than 3 days on ingest


def _norm_title(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t.lower())


def _shingles(text: str) -> set[int]:
    t = _norm_title(text)
    if re.search(r"[一-鿿]", t):
        grams = {t[i:i + 2] for i in range(len(t) - 1)}          # CJK: character bigrams
    else:
        words = re.findall(r"[a-z0-9]+", text.lower())
        grams = {" ".join(words[i:i + 2]) for i in range(len(words) - 1)} or set(words)
    return {int(hashlib.md5(g.encode()).hexdigest()[:8], 16) for g in grams}


def _jaccard(a: set[int], b: set[int]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def event_to_api(row: dict) -> dict:
    ai = db.loads(row.get("ai_comment"), None)
    return {
        "id": row["id"], "storyId": row.get("story_id"), "kind": row["kind"], "source": row["source"],
        "url": row.get("source_url"), "ts": row["published_at"], "receivedAt": row["received_at"],
        "mkts": db.loads(row.get("markets"), []), "symbols": db.loads(row.get("symbols"), []),
        "title": row["title"], "body": row.get("body") or "", "lang": row.get("lang"),
        "impact": row.get("impact"), "ai": ai, "state": row.get("enrich_state"),
        "industries": db.loads(row.get("industries"), []),
    }


def _assign_story(ev: dict, sh: set[int]) -> str:
    since = ev["published_at"] - STORY_WINDOW_MS
    best, best_s = None, 0.0
    for st in db.query("SELECT id, shingles FROM stories WHERE last_seen >= ? ORDER BY last_seen DESC LIMIT 400",
                       (since,)):
        s = _jaccard(sh, set(db.loads(st["shingles"], [])))
        if s > best_s:
            best, best_s = st["id"], s
    if best and best_s >= STORY_JACCARD:
        db.execute("UPDATE stories SET last_seen=max(last_seen, ?), event_count=event_count+1 WHERE id=?",
                   (ev["published_at"], best))
        return best
    sid = "s" + hashlib.sha1(f"{ev['source']}:{ev['source_id']}".encode()).hexdigest()[:15]
    db.execute("INSERT OR IGNORE INTO stories(id, first_seen, last_seen, headline, markets, symbols, shingles) "
               "VALUES(?,?,?,?,?,?,?)",
               (sid, ev["published_at"], ev["published_at"], ev["title"], db.dumps(ev.get("markets") or []),
                db.dumps(ev.get("symbols") or []), db.dumps(sorted(sh)[:300])))
    return sid


def ingest(raw_events: list[dict], publish: bool = True, max_age_ms: int = MAX_AGE_MS) -> int:
    """Store new events; returns how many were new. Safe to call repeatedly with overlapping batches."""
    now = db.now_ms()
    new = 0
    for ev in sorted(raw_events, key=lambda e: e.get("published_at") or 0):
        title = (ev.get("title") or "").strip()
        if not title or not ev.get("published_at"):
            continue
        if now - ev["published_at"] > max_age_ms or ev["published_at"] - now > 3600_000:
            continue
        eid = "e" + hashlib.sha1(f"{ev['source']}:{ev['source_id']}".encode()).hexdigest()[:15]
        if db.one("SELECT 1 FROM events WHERE id=?", (eid,)):
            continue
        chash = hashlib.sha1(_norm_title(title).encode()).hexdigest()
        if db.one("SELECT 1 FROM events WHERE content_hash=?", (chash,)):
            continue   # same headline already seen from another source
        story = _assign_story(ev, _shingles(title + " " + (ev.get("body") or "")[:200]))
        db.execute(
            "INSERT OR IGNORE INTO events(id, story_id, kind, source, source_url, published_at, received_at, "
            "markets, title, body, lang, symbols, content_hash, enrich_state, industries) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, story, ev["kind"], ev["source"], ev.get("url"), ev["published_at"], now,
             db.dumps(ev.get("markets") or []), title, (ev.get("body") or "")[:4000], ev.get("lang"),
             db.dumps(ev.get("symbols") or []), chash, "pending", db.dumps([ev["industry"]] if ev.get("industry") else [])))
        new += 1
        if publish:
            row = db.one("SELECT * FROM events WHERE id=?", (eid,))
            if row:
                hub.publish("wire", "event", event_to_api(row))
    return new


def recent_events(market: str | None = None, date_cst: str | None = None, limit: int = 200,
                  min_impact: int | None = None) -> list[dict]:
    """Wire query. `date_cst` (YYYY-MM-DD, Beijing/HK day) selects an archived day."""
    sql, args = "SELECT * FROM events WHERE enrich_state != 'skipped'", []
    if date_cst:
        start = _day_start_ms(date_cst)
        sql += " AND published_at >= ? AND published_at < ?"
        args += [start, start + 86400_000]
    if min_impact is not None:
        sql += " AND (impact IS NULL OR impact >= ?)"
        args.append(min_impact)
    sql += " ORDER BY published_at DESC LIMIT ?"
    args.append(limit * 3 if market else limit)
    rows = [event_to_api(r) for r in db.query(sql, args)]
    if market and market != "ALL":
        rows = [r for r in rows if market in r["mkts"]]
    return rows[:limit]


def _day_start_ms(d: str) -> int:
    from datetime import datetime, timedelta, timezone
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
