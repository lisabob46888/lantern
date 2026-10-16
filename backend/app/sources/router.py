"""Source router: try providers in order, first non-empty answer wins.

Every answer is wrapped in `Sourced` so the API can show where each value came
from. Failing providers trip a per-provider circuit breaker; "no permission"
style errors (Finnhub premium, Tushare points) park the provider for hours.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from app.store import db

log = logging.getLogger("lantern.sources")
_pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="src")

# Compliance tiers, as labelled by Vibe-Research / provider terms.
TIER_PERSONAL = "personal"   # site front-end APIs: Eastmoney, Sina, Tencent, Yahoo, THS, CLS
TIER_PUBLIC = "public"       # government / regulator data: SEC EDGAR, Treasury, cninfo
TIER_KEYED = "keyed"         # your own API key: Finnhub, Tushare
TIER_AI = "ai"               # GLM web search, always with cited URLs

_NO_PERMISSION = ("not set", "notconfigured", "permission", "premium", "权限", "积分", "access denied", "403", "401",
                  "don't have access", "not allowed", "subscription")


@dataclass
class Provider:
    name: str
    fn: Callable[..., Any]
    tier: str = TIER_PERSONAL
    timeout: float = 12.0


@dataclass
class Sourced:
    data: Any
    source: str | None
    tier: str | None
    fetched_at: int
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.source is not None

    def meta(self) -> dict:
        return {"source": self.source, "tier": self.tier, "fetchedAt": self.fetched_at}


class _Breaker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float]] = {}  # name -> (consecutive fails, open_until)

    def is_open(self, name: str) -> bool:
        with self._lock:
            _, until = self._state.get(name, (0, 0.0))
            return until > time.time()

    def ok(self, name: str) -> None:
        with self._lock:
            self._state.pop(name, None)

    def fail(self, name: str, err: str) -> None:
        with self._lock:
            n, _ = self._state.get(name, (0, 0.0))
            n += 1
            low = err.lower()
            if any(k in low for k in _NO_PERMISSION):
                cool = 6 * 3600.0
            else:
                cool = min(600.0, 15.0 * (2 ** (n - 1))) if n >= 2 else 0.0
            self._state[name] = (n, time.time() + cool)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            now = time.time()
            return {k: {"fails": n, "openFor": max(0, int(u - now))} for k, (n, u) in self._state.items()}


breaker = _Breaker()
_mem: dict[str, tuple[float, Sourced]] = {}
_mem_lock = threading.Lock()


def is_empty(v: Any) -> bool:
    if v is None:
        return True
    if hasattr(v, "empty") and isinstance(getattr(v, "empty"), bool):  # pandas
        return v.empty
    if isinstance(v, (list, tuple, dict, str)):
        return len(v) == 0
    return False


def route(providers: list[Provider], *args: Any, cache_key: str | None = None,
          ttl: float = 0, persist: bool = False, validate: Callable[[Any], bool] | None = None,
          **kwargs: Any) -> Sourced:
    """Run providers in order. `ttl` caches the winning answer in memory (and in
    SQLite when `persist`), so pollers and page loads share one upstream call."""
    if cache_key and ttl > 0:
        with _mem_lock:
            hit = _mem.get(cache_key)
        if hit and hit[0] > time.time():
            return hit[1]
        if persist:
            row = db.kv_get(cache_key)
            if row:
                val, src, at = row
                res = Sourced(val, src, None, at)
                with _mem_lock:
                    _mem[cache_key] = (time.time() + ttl, res)
                return res

    errors: list[str] = []
    for p in providers:
        if breaker.is_open(p.name):
            errors.append(f"{p.name}: circuit open")
            continue
        fut = _pool.submit(p.fn, *args, **kwargs)
        try:
            val = fut.result(timeout=p.timeout)
        except FutTimeout:
            msg = f"timeout after {p.timeout:.0f}s"
            breaker.fail(p.name, msg)
            db.health(p.name, False, msg)
            errors.append(f"{p.name}: {msg}")
            continue
        except Exception as e:  # provider bugs and upstream errors alike
            msg = f"{type(e).__name__}: {e}"[:300]
            breaker.fail(p.name, msg)
            db.health(p.name, False, msg)
            errors.append(f"{p.name}: {msg}")
            log.debug("provider %s failed: %s", p.name, msg)
            continue
        if is_empty(val):
            errors.append(f"{p.name}: empty")
            continue
        if validate is not None and not validate(val):
            breaker.fail(p.name, "failed validation")
            db.health(p.name, False, "failed validation (implausible values)")
            errors.append(f"{p.name}: failed validation")
            continue
        breaker.ok(p.name)
        db.health(p.name, True)
        res = Sourced(val, p.name, p.tier, db.now_ms(), errors)
        if cache_key and ttl > 0:
            with _mem_lock:
                _mem[cache_key] = (time.time() + ttl, res)
            if persist:
                db.kv_set(cache_key, val, p.name, ttl)
        return res

    if cache_key and persist:  # all providers failed: serve the last good copy, marked stale
        row = db.kv_get(cache_key, allow_stale=True)
        if row:
            val, src, at = row
            return Sourced(val, f"{src} (stale)", None, at, errors)
    return Sourced(None, None, None, db.now_ms(), errors)
