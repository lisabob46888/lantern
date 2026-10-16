"""Pollers. Each runs in its own asyncio loop; blocking source calls go to threads.

Intervals follow the design doc: quotes every 3 s while a market is active (60 s otherwise),
wires 10-30 s, filings 60 s, RSS 10 min, calendars daily.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from app.config import settings
from app.enrich import worker
from app.hub import hub
from app.pipeline import connectors as C
from app.pipeline.ingest import ingest
from app.services import calendar, marketdata, sessions, watchlists
from app.store import db

log = logging.getLogger("lantern.scheduler")
_tasks: list[asyncio.Task] = []
_last_quotes: dict[str, float] = {}
status: dict[str, dict] = {}   # poller name -> {lastRun, lastOk, lastError, lastErrorAt, items}


def _record(name: str, ok: bool, items: int = 0, err: str | None = None) -> None:
    s = status.setdefault(name, {})
    s["lastRun"] = db.now_ms()
    if ok:
        s["lastOk"], s["items"] = s["lastRun"], items
    else:
        s["lastError"], s["lastErrorAt"] = (err or "")[:300], s["lastRun"]


async def _loop(name: str, interval: Callable[[], float], job: Callable[[], int], initial_delay: float = 0) -> None:
    await asyncio.sleep(initial_delay)
    while True:
        t = time.time()
        try:
            n = await asyncio.to_thread(job)
            _record(name, True, n or 0)
        except Exception as e:
            log.warning("poller %s failed: %s", name, e)
            _record(name, False, err=f"{type(e).__name__}: {e}")
        await asyncio.sleep(max(1.0, interval() - (time.time() - t)))


def _any_active() -> bool:
    try:
        return any(sessions.is_active(m) for m in ("US", "CN", "HK"))
    except Exception:
        return True


def job_quotes() -> int:
    ids = watchlists.watched_securities()
    if not ids:
        return 0
    qs = marketdata.quotes(ids)
    changed = {k: v for k, v in qs.items() if _last_quotes.get(k) != v.get("price")}
    for k, v in changed.items():
        _last_quotes[k] = v.get("price")
    if changed:
        hub.publish("quotes", "quotes", changed)
    return len(changed)


def job_wire(fetch: Callable[[], list[dict]]) -> Callable[[], int]:
    return lambda: ingest(fetch())


def job_cninfo() -> int:
    return ingest(C.cninfo([i for i in watchlists.get("co") if i.startswith("CN:")]))


def job_company_news() -> int:
    return ingest(C.company_news([i for i in watchlists.get("co") if not i.startswith("CN:")]))


def job_enrich() -> int:
    return worker.run_fast_batch(20)


def job_calendar() -> int:
    n = calendar.refresh_us_earnings(set(watchlists.get("co")))
    try:
        n += calendar.refresh_macro()
    except Exception as e:
        log.info("macro calendar: %s", e)
    return n


def job_postmarket() -> int:
    from app.services import postmarket
    return postmarket.check_and_generate()


def start() -> None:
    loop = asyncio.get_running_loop()
    hub.bind(loop)
    specs: list[tuple[str, Callable[[], float], Callable[[], int], float]] = [
        ("quotes", lambda: 3 if _any_active() else 60, job_quotes, 0),
        ("cls", lambda: 10, job_wire(C.cls), 1),
        ("em_global", lambda: 15, job_wire(C.em_global), 2),
        ("finnhub_news", lambda: 30, job_wire(C.finnhub_news), 3),
        ("cninfo", lambda: 60 if sessions.is_active("CN") else 600, job_cninfo, 5),
        ("company_news", lambda: 300, job_company_news, 8),
        ("edgar", lambda: 60 if settings.sec_contact else 3600, job_wire(C.edgar), 10),
        ("rss", lambda: 600, job_wire(C.rss), 15),
        ("enrich", lambda: 3, job_enrich, 4),
        ("calendar", lambda: 24 * 3600, job_calendar, 20),
        ("postmarket", lambda: 60, job_postmarket, 30),
    ]
    for name, interval, job, delay in specs:
        _tasks.append(loop.create_task(_loop(name, interval, job, delay), name=f"poll-{name}"))
    log.info("scheduler started %d pollers", len(_tasks))


async def stop() -> None:
    for t in _tasks:
        t.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
