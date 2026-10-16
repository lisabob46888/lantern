"""Enrichment: fast triage of pending events in batches, deep AI reads per story."""
from __future__ import annotations

import json
import logging
import re
import threading

from app.config import settings
from app.enrich import llm
from app.enrich.prompts import DEEP_SYSTEM, FAST_SYSTEM, PROMPT_VERSION
from app.hub import hub
from app.pipeline.ingest import event_to_api
from app.services import securities as S
from app.store import db

log = logging.getLogger("lantern.enrich")
MKTS = {"US", "CN", "HK"}
INDUSTRY_KEYS = {"ai", "semi", "robot", "auto", "energy", "bio", "space", "security", "tech", "consumer"}
_deep_inflight: set[str] = set()
_deep_lock = threading.Lock()
DEEP_AUTO_IMPACT = 7
_attempts: dict[str, int] = {}


def _sec_id(t: dict) -> str | None:
    """Model-named ticker -> canonical id. Tolerates 688256.SH, SH688256, HK.0981, 0981.HK, NVDA.US.
    Names the model gives are not stored: display names come from market-data sources only."""
    mkt = str(t.get("market", "")).upper()
    raw = str(t.get("symbol") or t.get("ticker") or t.get("code") or "").strip().upper()
    if mkt not in MKTS or not raw:
        return None
    if mkt == "CN":
        m = re.search(r"(\d{6})", raw)
        return f"CN:{m.group(1)}" if m else None
    if mkt == "HK":
        m = re.search(r"(\d{1,5})", raw)
        return f"HK:{m.group(1).zfill(5)}" if m else None
    sym = re.sub(r"^(US[.:])|([.:]US)$|\.(O|N|OQ|AM)$", "", raw)
    return f"US:{sym}" if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", sym) else None


def _norm_name(s: str) -> str:
    s = re.sub(r"(股份有限公司|有限公司|集团|控股|股份|-[A-Z]|\(.*?\)|（.*?）)", "", s or "")
    s = re.sub(r"\b(inc|corp|corporation|co|ltd|limited|holdings?|group|plc|company|the|class [a-z])\b\.?", "", s.lower())
    return re.sub(r"[\s\W_]+", "", s)


def name_matches(model_name: str, quote: dict) -> bool:
    """Does the model's company name agree with the market-data name for that ticker?
    Guards against real-but-wrong tickers (e.g. an oil company listed as a chipmaker)."""
    parts = [model_name or ""] + re.findall(r"[（(](.*?)[)）]", model_name or "")
    if not any(_norm_name(p) for p in parts):
        return True   # nothing to compare against
    return any(_one_name_matches(_norm_name(p), quote) for p in parts if _norm_name(p))


def _one_name_matches(m: str, quote: dict) -> bool:
    for real in (quote.get("name") or "", quote.get("nameZh") or ""):
        r = _norm_name(real)
        if not r:
            continue
        if r in m or m in r:
            return True
        cjk_m, cjk_r = set(re.findall(r"[\u4e00-\u9fff]", m)), set(re.findall(r"[\u4e00-\u9fff]", r))
        if cjk_r and len(cjk_m & cjk_r) >= min(2, len(cjk_r)):
            return True
        if r[:4] and r[:4] in m:
            return True
    return False


def _clamp_int(v, lo: int, hi: int) -> int | None:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _blocked(e: Exception) -> bool:
    """Zhipu content-moderation refusal (error 1301): the input itself is rejected, retrying will not help."""
    return "1301" in str(e) or "contentFilter" in str(e)


def run_fast_batch(limit: int = 20) -> int:
    """Triage up to `limit` pending events (newest first). Returns how many were processed."""
    if not settings.llm_enabled:
        return 0
    rows = db.query("SELECT * FROM events WHERE enrich_state='pending' ORDER BY published_at DESC LIMIT ?", (limit,))
    return _triage(rows) if rows else 0


def _triage(rows: list[dict]) -> int:
    payload = [{"i": i, "source": r["source"], "title": r["title"], "body": (r["body"] or "")[:500]}
               for i, r in enumerate(rows)]
    try:
        out, _, model = llm.chat_json(FAST_SYSTEM, json.dumps({"items": payload}, ensure_ascii=False),
                                      fast=True, max_tokens=8000)
    except Exception as e:
        if _blocked(e):
            if len(rows) == 1:   # isolate the item the moderator rejects; keep it on the wire without AI
                db.execute("UPDATE events SET enrich_state='blocked' WHERE id=?", (rows[0]["id"],))
                return 1
            mid = len(rows) // 2  # split the batch so one sensitive item does not block the rest
            return _triage(rows[:mid]) + _triage(rows[mid:])
        log.warning("fast pass failed: %s", e)
        for r in rows:  # retry on the next tick; give up after 3 attempts
            _attempts[r["id"]] = _attempts.get(r["id"], 0) + 1
            if _attempts[r["id"]] >= 3:
                db.execute("UPDATE events SET enrich_state='failed' WHERE id=?", (r["id"],))
        return 0
    by_i = {it.get("i"): it for it in out.get("items") or [] if isinstance(it, dict)}
    for i, r in enumerate(rows):
        it = by_i.get(i)
        if not it:  # the model skipped this item: retry it once in a later batch
            _attempts[r["id"]] = _attempts.get(r["id"], 0) + 1
            if _attempts[r["id"]] >= 2:
                db.execute("UPDATE events SET enrich_state='failed' WHERE id=?", (r["id"],))
            continue
        impact = _clamp_int(it.get("impact"), 1, 10)
        relevant = bool(it.get("relevant", True)) and (impact or 0) >= 3
        mkts = [m for m in (it.get("markets") or []) if m in MKTS] or db.loads(r["markets"], [])
        syms = list(dict.fromkeys(db.loads(r["symbols"], []) + [s for s in map(_sec_id, it.get("tickers") or []) if s]))
        dirs = {sid: t.get("dir", 0) for t in it.get("tickers") or [] if (sid := _sec_id(t))}
        ai = {"title": {"en": it.get("title_en") or "", "zh": it.get("title_zh") or ""},
              "comment": {"en": it.get("comment_en") or "", "zh": it.get("comment_zh") or ""},
              "sentiment": it.get("sentiment"), "dirs": dirs, "model": model, "v": PROMPT_VERSION}
        inds = list(dict.fromkeys(db.loads(r.get("industries"), []) +
                                  [x for x in (it.get("industries") or []) if x in INDUSTRY_KEYS]))
        db.execute("UPDATE events SET impact=?, markets=?, symbols=?, ai_comment=?, enrich_state=?, industries=? WHERE id=?",
                   (impact, db.dumps(mkts), db.dumps(syms), db.dumps(ai), "done" if relevant else "skipped",
                    db.dumps(inds), r["id"]))
        if r["story_id"]:
            db.execute("UPDATE stories SET impact=max(coalesce(impact,0), ?), sentiment=coalesce(sentiment, ?), "
                       "markets=?, symbols=? WHERE id=?",
                       (impact or 0, it.get("sentiment"), db.dumps(mkts), db.dumps(syms), r["story_id"]))
        row = db.one("SELECT * FROM events WHERE id=?", (r["id"],))
        hub.publish("wire", "event_update" if relevant else "event_hide", event_to_api(row))
        if relevant and impact and impact >= DEEP_AUTO_IMPACT and r["story_id"]:
            request_deep(r["story_id"])
    return len(rows)


def request_deep(story_id: str) -> bool:
    """Start a deep read in the background unless one exists or is running."""
    if not settings.llm_enabled or db.one("SELECT 1 FROM ai_reads WHERE story_id=? AND tier='deep'", (story_id,)):
        return False
    with _deep_lock:
        if story_id in _deep_inflight:
            return False
        _deep_inflight.add(story_id)
    threading.Thread(target=_deep_job, args=(story_id,), daemon=True, name=f"deep-{story_id}").start()
    return True


def _deep_job(story_id: str) -> None:
    try:
        deep_read(story_id)
    except Exception as e:
        log.warning("deep read %s failed: %s", story_id, e)
        hub.publish(f"story:{story_id}", "story_failed", {"id": story_id, "error": str(e)[:200]})
    finally:
        with _deep_lock:
            _deep_inflight.discard(story_id)


def deep_read(story_id: str) -> dict:
    from app.services import marketdata
    events = db.query("SELECT * FROM events WHERE story_id=? ORDER BY published_at ASC LIMIT 8", (story_id,))
    if not events:
        raise ValueError("story has no events")
    syms = list(dict.fromkeys(s for e in events for s in db.loads(e["symbols"], [])))[:8]
    quotes = marketdata.quotes(syms) if syms else {}
    material = {
        "story": [{"time_utc_ms": e["published_at"], "source": e["source"], "title": e["title"],
                   "body": (e["body"] or "")[:1500]} for e in events],
        "live_quotes": {k: {"name": v.get("name") or v.get("nameZh"), "price": v.get("price"), "pct_today": v.get("pct")}
                        for k, v in quotes.items()},
    }
    out, _, model = llm.chat_json(DEEP_SYSTEM, json.dumps(material, ensure_ascii=False), max_tokens=5000)
    affected = []
    for a in out.get("affected") or []:
        sid = _sec_id(a)
        if sid:
            affected.append({"id": sid, "dir": _clamp_int(a.get("dir"), -1, 1) or 0,
                             "note": {"en": a.get("note_en", ""), "zh": a.get("note_zh", "")}})
    bi = lambda k: {"en": out.get(f"{k}_en") or "", "zh": out.get(f"{k}_zh") or ""}  # noqa: E731
    analog = out.get("analog") if isinstance(out.get("analog"), dict) else None
    read = {
        "simple": bi("simple"), "detail": bi("detail"), "horizon": bi("horizon"),
        "bull": bi("bull"), "bear": bi("bear"), "affected": affected,
        "ripple": [{"where": {"en": r.get("where_en", ""), "zh": r.get("where_zh", "")},
                    "text": {"en": r.get("text_en", ""), "zh": r.get("text_zh", "")}}
                   for r in out.get("ripple") or [] if isinstance(r, dict)][:3],
        "analog": {"title": {"en": analog.get("title_en", ""), "zh": analog.get("title_zh", "")},
                   "text": {"en": analog.get("text_en", ""), "zh": analog.get("text_zh", "")}} if analog else None,
        "confidence": _clamp_int(out.get("confidence"), 0, 100),
        "sources": [{"title": e["title"], "url": e["source_url"], "source": e["source"]} for e in events],
    }
    db.execute("INSERT OR REPLACE INTO ai_reads(story_id, tier, payload, model, prompt_version, created_at) "
               "VALUES(?,?,?,?,?,?)", (story_id, "deep", db.dumps(read), model, PROMPT_VERSION, db.now_ms()))
    hub.publish(f"story:{story_id}", "story_read", {"id": story_id, "read": read})
    hub.publish("wire", "story_read", {"id": story_id})
    return read


def story_api(story_id: str, lang: str = "en") -> dict | None:
    st = db.one("SELECT * FROM stories WHERE id=?", (story_id,))
    if not st:
        return None
    events = [event_to_api(e) for e in db.query("SELECT * FROM events WHERE story_id=? ORDER BY published_at DESC",
                                                (story_id,))]
    deep = db.one("SELECT payload, model, prompt_version, created_at FROM ai_reads WHERE story_id=? AND tier='deep'",
                  (story_id,))
    state = "ready" if deep else ("disabled" if not settings.llm_enabled else "pending")
    if not deep and settings.llm_enabled:
        request_deep(story_id)
    return {"id": story_id, "headline": st["headline"], "firstSeen": st["first_seen"], "lastSeen": st["last_seen"],
            "impact": st["impact"], "sentiment": st["sentiment"], "mkts": db.loads(st["markets"], []),
            "symbols": db.loads(st["symbols"], []), "events": events, "readState": state,
            "read": db.loads(deep["payload"]) if deep else None,
            "readMeta": {"model": deep["model"], "promptVersion": deep["prompt_version"], "at": deep["created_at"]} if deep else None}
