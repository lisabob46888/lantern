"""Core REST endpoints: status, sessions, quotes, bars, search, wire, stories, calendar, reports, lists."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, HTTPException, Query

from app.config import settings
from app.enrich import worker
from app.pipeline.ingest import event_to_api, recent_events
from app.services import calendar, marketdata, postmarket, sessions, watchlists
from app.services import securities as S
from app.sources.router import breaker
from app.store import db

router = APIRouter(prefix="/api/v1")
CST = timezone(timedelta(hours=8))


def _sec(sec_id: str) -> str:
    sid = S.normalize(sec_id)
    if not sid:
        raise HTTPException(400, f"unrecognised security id: {sec_id}")
    return sid


@router.get("/status")
def status() -> dict:
    from app import scheduler
    return {
        "llm": {"enabled": settings.llm_enabled, "model": settings.glm_model},
        "keys": {"glm": bool(settings.glm_api_key), "finnhub": bool(settings.finnhub_key),
                 "tushare": bool(settings.tushare_token), "secContact": bool(settings.sec_contact)},
        "pollers": scheduler.status,
        "breakers": breaker.snapshot(),
        "sources": db.query("SELECT * FROM source_health ORDER BY source"),
        "personalUseOnly": True,
    }


@router.get("/sessions")
def get_sessions() -> list[dict]:
    return sessions.all_status()


@router.get("/quotes")
def get_quotes(ids: str = Query(..., description="comma-separated security ids")) -> dict:
    return marketdata.quotes([_sec(i) for i in ids.split(",") if i.strip()])


@router.get("/indices")
def get_indices(market: str = "ALL") -> list[dict]:
    ids = [i for i, d in S.INDEX_BY_ID.items() if market in ("ALL", d.mkt)]
    qs = marketdata.quotes(ids)
    return [qs.get(i) or {**S.get(i).to_api(), "price": None} for i in ids]


@router.get("/securities/search")
def search(q: str) -> list[dict]:
    return S.search(q)[:20]


@router.get("/securities/{sec_id}/quote")
def sec_quote(sec_id: str) -> dict:
    q = marketdata.detail_quote(_sec(sec_id))
    if not q:
        raise HTTPException(404, "no quote from any source")
    return q


@router.get("/indices/{sec_id}/profile")
def index_profile(sec_id: str) -> dict:
    """Header data for the index page: 52-week range from weekly bars + what the index tracks."""
    from app.services import reads
    sid = _sec(sec_id)
    if sid not in S.INDEX_BY_ID:
        raise HTTPException(400, "not an index")
    d = S.INDEX_BY_ID[sid]
    yb = marketdata.bars(sid, "1Y")["bars"]
    return {"id": sid, "exchange": d.exchange, "lo52": min((b["l"] for b in yb), default=None),
            "hi52": max((b["h"] for b in yb), default=None),
            "about": reads.index_profile(sid, d.name, d.exchange)}


@router.get("/securities/{sec_id}/bars")
def sec_bars(sec_id: str, range: str = "6M") -> dict:  # noqa: A002 - query name used by the client
    return marketdata.bars(_sec(sec_id), range)


@router.get("/securities/{sec_id}/events")
def sec_events(sec_id: str, days: int = 400, min_impact: int = 5) -> list[dict]:
    """Events to label on the chart: news tagged to the symbol; for an index, high-impact news in its market."""
    sid = _sec(sec_id)
    since = db.now_ms() - days * 86400_000
    if sid.startswith("IX:"):
        mkt = sid.split(":")[1]
        rows = db.query("SELECT * FROM events WHERE published_at>=? AND enrich_state='done' AND impact>=? AND markets LIKE ? "
                        "ORDER BY impact DESC, published_at DESC LIMIT 40", (since, max(min_impact, 7), f'%"{mkt}"%'))
    else:
        rows = db.query("SELECT * FROM events WHERE published_at>=? AND symbols LIKE ? AND enrich_state!='skipped' "
                        "ORDER BY published_at DESC LIMIT 60", (since, f'%"{sid}"%'))
    seen, out = set(), []
    for r in rows:  # one label per story
        if r["story_id"] in seen:
            continue
        seen.add(r["story_id"])
        out.append(event_to_api(r))
    return out


@router.get("/wire")
def wire(market: str = "ALL", date: str | None = None, limit: int = 150) -> dict:
    return {"items": recent_events(market, date, limit), "aiEnabled": settings.llm_enabled}


@router.get("/archive/days")
def archive_days(limit: int = 14) -> list[dict]:
    since = db.now_ms() - 30 * 86400_000   # the wire archive; older company filings live on company pages
    rows = db.query("SELECT published_at FROM events WHERE enrich_state!='skipped' AND published_at>=? "
                    "ORDER BY published_at DESC LIMIT 20000", (since,))
    counts: dict[str, int] = {}
    for r in rows:
        d = datetime.fromtimestamp(r["published_at"] / 1000, CST).date().isoformat()
        counts[d] = counts.get(d, 0) + 1
    return [{"date": d, "events": n} for d, n in sorted(counts.items(), reverse=True)[:limit]]


@router.get("/stories/{story_id}")
def story(story_id: str) -> dict:
    s = worker.story_api(story_id)
    if not s:
        raise HTTPException(404, "story not found")
    syms = list(dict.fromkeys(s["symbols"] + [a["id"] for a in (s["read"] or {}).get("affected", [])]))
    s["quotes"] = marketdata.quotes(syms) if syms else {}
    return s


@router.get("/need-to-know")
def need_to_know(date: str | None = None, market: str = "ALL", limit: int = 6) -> dict:
    """Ranked stories of the day: impact first, then breadth across markets, then recency."""
    day = date or datetime.now(CST).date().isoformat()
    start = int(datetime.fromisoformat(day).replace(tzinfo=CST).timestamp() * 1000)
    rows = db.query("SELECT * FROM stories WHERE last_seen>=? AND last_seen<? AND impact>=6", (start, start + 86400_000))
    if market != "ALL":
        rows = [r for r in rows if market in db.loads(r["markets"], [])]
    rows.sort(key=lambda r: (r["impact"] or 0, len(db.loads(r["markets"], [])), r["last_seen"]), reverse=True)
    items = []
    for r in rows[:limit]:
        ev = db.one("SELECT * FROM events WHERE story_id=? AND enrich_state='done' ORDER BY impact DESC, published_at ASC LIMIT 1",
                    (r["id"],))
        if not ev:
            continue
        e = event_to_api(ev)
        items.append({"storyId": r["id"], "impact": r["impact"], "mkts": db.loads(r["markets"], []),
                      "title": (e["ai"] or {}).get("title") or {"en": e["title"], "zh": e["title"]},
                      "why": (e["ai"] or {}).get("comment") or {"en": "", "zh": ""}, "ts": r["last_seen"]})
    return {"date": day, "items": items, "aiEnabled": settings.llm_enabled}


@router.get("/calendar")
def get_calendar(market: str = "ALL", limit: int = 12) -> list[dict]:
    return calendar.upcoming(limit, market)


@router.get("/reports/post-market")
def get_postmarket(market: str, date: str | None = None) -> dict:
    mkt = market.upper()
    if mkt not in ("US", "CN", "HK"):
        raise HTTPException(400, "market must be US, CN or HK")
    d = date or sessions.status(mkt)["lastCompleted"]
    if not d:
        raise HTTPException(404, "no completed session")
    return postmarket.get(mkt, d)


@router.post("/reports/post-market/regenerate")
def regen_postmarket(market: str, date: str) -> dict:
    return postmarket.generate(market.upper(), date)


@router.get("/watchlists")
def get_lists() -> dict:
    return watchlists.all_lists()


@router.put("/watchlists/{name}")
def put_list(name: str, items: list[str] = Body(...)) -> list[str]:
    try:
        return watchlists.put(name, [_sec(i) if name != "ind" else i for i in items])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
