"""Post-market report per market and trade date: session data + GLM analysis.

Generated once per completed session, after the publish time (US 16:30 ET, CN 15:30 CST,
HK 16:30 HKT). Data blocks a source cannot provide are left out and listed in `missing`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import app.vendor  # noqa: F401
import market as vibe_market

from app.config import settings
from app.hub import hub
from app.services import calendar, marketdata, sessions, watchlists
from app.services import securities as S
from app.store import db

log = logging.getLogger("lantern.postmarket")
PUBLISH_MIN = {"US": 16 * 60 + 30, "CN": 15 * 60 + 30, "HK": 16 * 60 + 30}
PUB_LABEL = {"US": "16:30 ET", "CN": "15:30 CST", "HK": "16:30 HKT"}


def _day_bounds(mkt: str, d: str) -> tuple[int, int]:
    tz = ZoneInfo(sessions.RULES[mkt]["tz"])
    start = datetime.fromisoformat(d).replace(tzinfo=tz)
    return int(start.timestamp() * 1000), int(start.timestamp() * 1000) + 86400_000


def gather(mkt: str, d: str) -> dict:
    data: dict = {"market": mkt, "tradeDate": d, "missing": [], "sources": []}
    idx_ids = [i for i, x in S.INDEX_BY_ID.items() if x.mkt == mkt]
    closes = []
    for iid in idx_ids:
        b = marketdata.bars(iid, "1M")
        rows = [r for r in b["bars"] if r["t"] <= d]
        if len(rows) >= 2 and rows[-1]["t"] == d:
            last, prev = rows[-1], rows[-2]
            closes.append({"id": iid, "name": S.INDEX_BY_ID[iid].name, "nameZh": S.INDEX_BY_ID[iid].name_zh,
                           "close": last["c"], "pct": round((last["c"] / prev["c"] - 1) * 100, 2), "volume": last["v"]})
            data["sources"].append(b["source"])
    data["indices"] = closes
    if not closes:
        data["missing"].append("index closes")
    if mkt == "CN":
        try:
            ov = vibe_market.get_overview()
            sent = ov.get("sentiment") or {}
            data["breadth"] = {"up": sent.get("up"), "down": sent.get("down"), "flat": sent.get("flat"),
                               "limitUp": sent.get("zt"), "limitDown": sent.get("dt")}
            data["sectors"] = [{"name": s["name"], "pct": s.get("pct"), "netFlowYi": s.get("net")}
                               for s in (ov.get("sectors") or [])[:12]]
            data["sources"].append("eastmoney.overview")
        except Exception as e:
            data["missing"].append(f"breadth/sectors ({type(e).__name__})")
        try:
            emo = vibe_market.get_short_term_emotion()
            data["limitUpLadder"] = {"maxBoards": emo.get("max_boards"), "brokenBoards": emo.get("zb_count")}
        except Exception:
            data["missing"].append("limit-up ladder")
    else:
        data["missing"].append("market breadth (no reachable source for this market)")
    watch = [i for i in watchlists.get("co") if i.startswith(mkt + ":")]
    qs = marketdata.quotes(watch) if watch else {}
    data["movers"] = sorted(({"id": k, "ticker": v.get("ticker"), "name": v.get("name") or v.get("nameZh"),
                              "pct": v.get("pct"), "price": v.get("price")} for k, v in qs.items() if v.get("pct") is not None),
                            key=lambda m: -abs(m["pct"]))[:8]
    lo, hi = _day_bounds(mkt, d)
    stories = db.query("SELECT e.title, e.impact, e.ai_comment, e.symbols FROM events e WHERE e.published_at>=? AND "
                       "e.published_at<? AND e.markets LIKE ? AND e.enrich_state='done' ORDER BY e.impact DESC LIMIT 12",
                       (lo - 6 * 3600_000, hi, f'%"{mkt}"%'))
    data["stories"] = [{"title": (db.loads(s["ai_comment"], {}) or {}).get("title", {}).get("en") or s["title"],
                        "impact": s["impact"], "symbols": db.loads(s["symbols"], [])} for s in stories]
    data["next"] = [{"title": c["title"], "at": c["at"]} for c in calendar.upcoming(6, mkt)]
    return data


def generate(mkt: str, d: str) -> dict:
    key = f"{mkt}:{d}"
    data = gather(mkt, d)
    ai, model = None, None
    if settings.llm_enabled and data["indices"]:
        from app.enrich import llm
        from app.enrich.prompts import POSTMARKET_SYSTEM
        try:
            ai, _, model = llm.chat_json(POSTMARKET_SYSTEM, json.dumps(data, ensure_ascii=False), max_tokens=4000)
        except Exception as e:
            log.warning("postmarket AI %s failed: %s", key, e)
    report = {**data, "ai": ai, "model": model, "published": PUB_LABEL[mkt]}
    status = "failed" if not data["indices"] else ("published" if ai else "data_only")
    db.execute("INSERT OR REPLACE INTO reports(kind, key, status, payload, created_at) VALUES(?,?,?,?,?)",
               ("postmarket", key, status, db.dumps(report), db.now_ms()))
    hub.publish(f"report:{mkt}", "postmarket", {"key": key, "status": status})
    return report


def check_and_generate() -> int:
    made = 0
    for mkt in ("US", "CN", "HK"):
        st = sessions.status(mkt)
        d = st["lastCompleted"]
        if not d:
            continue
        local = datetime.now(ZoneInfo(st["tz"]))
        if d == st["localDate"] and local.hour * 60 + local.minute < PUBLISH_MIN[mkt]:
            continue
        done = db.one("SELECT status FROM reports WHERE kind='postmarket' AND key=?", (f"{mkt}:{d}",))
        if done and (done["status"] == "published" or (done["status"] == "data_only" and not settings.llm_enabled)):
            continue
        prior = db.one("SELECT created_at FROM reports WHERE kind='postmarket' AND key=?", (f"{mkt}:{d}",))
        if prior and db.now_ms() - prior["created_at"] < 30 * 60_000:
            continue  # failed recently; retry in 30 minutes
        generate(mkt, d)
        made += 1
    return made


def get(mkt: str, d: str) -> dict:
    row = db.one("SELECT status, payload, created_at FROM reports WHERE kind='postmarket' AND key=?", (f"{mkt}:{d}",))
    if not row:
        return {"market": mkt, "tradeDate": d, "status": "pending", "published": PUB_LABEL[mkt]}
    return {**db.loads(row["payload"], {}), "status": row["status"], "createdAt": row["created_at"]}
