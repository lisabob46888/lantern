"""Scheduled events: earnings dates and macro releases, for the countdown and catalysts."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import app.vendor  # noqa: F401
import gskill

from app.config import settings
from app.sources import finnhub_src
from app.store import db

log = logging.getLogger("lantern.calendar")
ET = ZoneInfo("America/New_York")
BIG_CAP_USD = 50e9


def _words(t: str) -> set[str]:
    t = re.sub(r"\(.*?\)|（.*?）", "", t.lower())
    return set(re.findall(r"[a-z]{3,}|[\u4e00-\u9fff]{2}", t))


def _put(kind: str, mkt: str, title: str, at: datetime, source: str, payload: dict | None = None) -> None:
    ms = int(at.timestamp() * 1000)
    if kind == "macro":  # the model words the same release differently between runs: merge near-duplicates
        w = _words(title)
        for r in db.query("SELECT id, title FROM calendar WHERE kind='macro' AND market=? AND abs(scheduled_at-?) <= 3600000",
                          (mkt, ms)):
            o = _words(r["title"])
            if w and o and len(w & o) / len(w | o) >= 0.5:
                return
    cid = hashlib.sha1(f"{kind}:{mkt}:{title}:{at.date()}".encode()).hexdigest()[:16]
    db.execute("INSERT OR REPLACE INTO calendar(id, kind, market, title, scheduled_at, source, payload) VALUES(?,?,?,?,?,?,?)",
               (cid, kind, mkt, title, ms, source, db.dumps(payload or {})))


def _cap(v) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", str(v)) or 0)
    except ValueError:
        return 0.0


def refresh_us_earnings(watch: set[str], days: int = 21) -> int:
    n = 0
    start = datetime.now(ET).date()
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            rows = gskill.earnings_calendar(d.isoformat()).get("rows") or []
        except Exception as e:
            log.info("nasdaq earnings %s: %s", d, e)
            continue
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            if not sym or (_cap(r.get("market_cap")) < BIG_CAP_USD and f"US:{sym}" not in watch):
                continue
            hour = {"time-pre-market": 8, "time-after-hours": 16}.get(r.get("time") or "", 12)
            at = datetime(d.year, d.month, d.day, hour, 0, tzinfo=ET)
            _put("earnings", "US", f"{r.get('name') or sym} results", at, "nasdaq.earnings",
                 {"symbol": f"US:{sym}", "epsForecast": r.get("eps_forecast"), "timing": r.get("time")})
            n += 1
    if n == 0 and settings.finnhub_key:  # Nasdaq unreachable: Finnhub fallback
        for r in finnhub_src.earnings_calendar(days):
            sym = (r.get("symbol") or "").upper()
            if f"US:{sym}" not in watch:
                continue
            d = datetime.strptime(r["date"], "%Y-%m-%d")
            hour = {"bmo": 8, "amc": 16}.get(r.get("hour") or "", 12)
            _put("earnings", "US", f"{sym} results", d.replace(hour=hour, tzinfo=ET), "finnhub.earnings",
                 {"symbol": f"US:{sym}", "epsForecast": r.get("epsEstimate")})
            n += 1
    return n


MACRO_PROMPT = """Today is {today}. From the search results, list scheduled macroeconomic data releases,
central-bank decisions and major policy meetings for {market_name} in the next 14 days. Only include items
whose date appears in the search results. Times: give the market's LOCAL time in "datetime" and its IANA zone
in "tz"; if a source states another zone (for example Beijing time for a US release), convert it.
Return {{"items": [{{"title_en": "...", "title_zh": "...", "datetime": "YYYY-MM-DDTHH:MM",
"tz": "{tz}", "source_url": "..."}}]}}"""

MACRO_MARKETS = {"US": ("the United States", "America/New_York"), "CN": ("mainland China", "Asia/Shanghai"),
                 "HK": ("Hong Kong", "Asia/Hong_Kong")}


def _macro_query(mkt: str, now: datetime) -> str:
    """Search engines need concrete months ("October November 2026"), not "next two weeks"."""
    later = now + timedelta(days=14)
    en = now.strftime("%B") + ("" if later.month == now.month else " " + later.strftime("%B")) + f" {later.year}"
    zh = f"{now.year}年{now.month}月" + ("" if later.month == now.month else f"{later.month}月")
    return {"US": f"US economic calendar {en} CPI retail sales FOMC",
            "CN": f"中国 {zh} 宏观经济数据 发布时间 统计局 央行",
            "HK": f"香港 {zh} 经济数据 公布日期 统计处 金管局"}[mkt]


def refresh_macro() -> int:
    """Macro dates via GLM web search, one search per market; every item must carry a resolvable source URL."""
    if not settings.llm_enabled:
        return 0
    from app.enrich import llm
    from app.enrich.prompts import FRAME
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)
    n = 0
    for mkt, (name, tz_default) in MACRO_MARKETS.items():
        query = _macro_query(mkt, now)
        try:
            out, sources, _ = llm.chat_json(FRAME, MACRO_PROMPT.format(today=today, market_name=name, tz=tz_default),
                                            web_search=True, search_query=query, fast=True, max_tokens=4000)
        except Exception as e:
            log.info("macro %s: %s", mkt, e)
            continue
        for it in out.get("items") or []:
            try:
                at = datetime.fromisoformat(it["datetime"]).replace(tzinfo=ZoneInfo(it.get("tz") or tz_default))
            except (KeyError, ValueError):
                continue
            url = it.get("source_url") or ""
            if not llm.cited(url, sources) or not (now - timedelta(days=1) <= at <= now + timedelta(days=15)):
                continue  # uncited or out-of-window items are dropped
            _put("macro", mkt, it.get("title_en") or it.get("title_zh") or "", at, "glm.websearch",
                 {"titleZh": it.get("title_zh"), "url": url})
            n += 1
    return n


def upcoming(limit: int = 12, market: str | None = None) -> list[dict]:
    now = db.now_ms()
    sql, args = "SELECT * FROM calendar WHERE scheduled_at >= ?", [now - 3600_000]
    if market and market != "ALL":
        sql += " AND market=?"
        args.append(market)
    sql += " ORDER BY scheduled_at ASC LIMIT ?"
    args.append(limit)
    out = []
    for r in db.query(sql, args):
        p = db.loads(r["payload"], {})
        out.append({"id": r["id"], "kind": r["kind"], "mkt": r["market"], "title": r["title"],
                    "titleZh": p.get("titleZh"), "at": r["scheduled_at"], "source": r["source"],
                    "url": p.get("url"), "symbol": p.get("symbol")})
    return out


def for_symbol(sec_id: str, limit: int = 6) -> list[dict]:
    rows = db.query("SELECT * FROM calendar WHERE scheduled_at >= ? AND payload LIKE ? ORDER BY scheduled_at LIMIT ?",
                    (db.now_ms() - 3600_000, f'%"{sec_id}"%', limit))
    return [{"id": r["id"], "kind": r["kind"], "title": r["title"], "at": r["scheduled_at"], "source": r["source"]}
            for r in rows]


