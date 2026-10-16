"""Finnhub provider (your own key). Free tier covers US quotes, news, profiles,
basic financials, recommendations, peers and the earnings calendar; premium
endpoints raise and the router parks them."""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta

import finnhub
import requests

from app.config import settings

_client: finnhub.Client | None = None
_lock = threading.Lock()
_last_call = 0.0


class NotConfigured(RuntimeError):
    pass


def client() -> finnhub.Client:
    global _client
    if not settings.finnhub_key:
        raise NotConfigured("FINNHUB_KEY not set")
    if _client is None:
        _client = finnhub.Client(api_key=settings.finnhub_key)
    return _client


def _throttle() -> None:
    """Free tier allows 60 calls/min; keep at most ~1 call per 1.1 s."""
    global _last_call
    with _lock:
        wait = 1.1 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def _call(fn, *args, **kw):
    """One retry after a timeout or dropped connection: a single stalled request through the
    local proxy should not cost a whole poll cycle. Other errors (premium, quota) raise at once."""
    for attempt in (0, 1):
        _throttle()
        try:
            return fn(*args, **kw)
        except (requests.Timeout, requests.ConnectionError):
            if attempt:
                raise
            time.sleep(1.0)


def quote(symbol: str) -> dict:
    q = _call(client().quote, symbol)
    return q if q and q.get("c") else {}


def general_news(category: str = "general") -> list[dict]:
    return _call(client().general_news, category, min_id=0) or []


def company_news(symbol: str, days: int = 14) -> list[dict]:
    to = date.today()
    return _call(client().company_news, symbol, _from=(to - timedelta(days=days)).isoformat(), to=to.isoformat()) or []


def profile(symbol: str) -> dict:
    return _call(client().company_profile2, symbol=symbol) or {}


def basic_financials(symbol: str) -> dict:
    return _call(client().company_basic_financials, symbol, "all") or {}


def recommendation_trends(symbol: str) -> list[dict]:
    return _call(client().recommendation_trends, symbol) or []


def price_target(symbol: str) -> dict:
    return _call(client().price_target, symbol) or {}


def peers(symbol: str) -> list[str]:
    return _call(client().company_peers, symbol) or []


def earnings_calendar(days: int = 45) -> list[dict]:
    start = date.today()
    r = _call(client().earnings_calendar, _from=start.isoformat(), to=(start + timedelta(days=days)).isoformat(),
                                   symbol="", international=False)
    return (r or {}).get("earningsCalendar") or []


def symbol_lookup(q: str) -> list[dict]:
    return (_call(client().symbol_lookup, q) or {}).get("result") or []


def candles(symbol: str, resolution: str, start: int, end: int) -> list[dict]:
    r = _call(client().stock_candles, symbol, resolution, start, end) or {}
    if r.get("s") != "ok":
        return []
    return [{"t": t * 1000, "o": o, "h": h, "l": lo, "c": c, "v": v}
            for t, o, h, lo, c, v in zip(r["t"], r["o"], r["h"], r["l"], r["c"], r["v"])]
