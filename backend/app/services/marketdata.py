"""Quotes and candles for all three markets, through the source router."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

import app.vendor  # noqa: F401  (vendor path setup)
import askill
import gskill

from app.services import securities as S
from app.services.securities import Sec
from app.sources import finnhub_src, tushare_src
from app.sources.router import Provider, TIER_KEYED, TIER_PERSONAL, route

UA = {"User-Agent": "Mozilla/5.0"}

# --- quotes -----------------------------------------------------------------


def _num(v: str) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def _tencent_batch(secs: list[Sec]) -> dict[str, dict]:
    reqs = {}
    for s in secs:
        code = s.tencent if s.kind == "index" or s.mkt != "US" else "us" + s.code
        reqs[code] = s
    out: dict[str, dict] = {}
    items = list(reqs.items())
    for i in range(0, len(items), 60):
        chunk = items[i:i + 60]
        r = requests.get("https://qt.gtimg.cn/q=" + ",".join(c for c, _ in chunk), headers=UA, timeout=8)
        text = r.content.decode("gbk", "ignore")
        for line in text.split(";"):
            if '="' not in line:
                continue
            var = line.split("=")[0].strip().removeprefix("v_")
            sec = reqs.get(var)
            vals = line.split('"')[1].split("~")
            if not sec or len(vals) < 35 or _num(vals[3]) in (None, 0.0):
                continue
            if sec.mkt == "US" and sec.kind == "stock" and "." in vals[2]:
                suffix = vals[2].split(".")[-1]
                if suffix != sec.us_suffix:
                    S.remember(sec.id, us_suffix=suffix)
            if sec.kind == "stock":
                en = vals[46].strip() if sec.mkt in ("US", "HK") and len(vals) > 46 else ""
                en = en.title() if en.isupper() and len(en) > 4 else en
                if (not sec.name_zh) or (en and en != sec.name):
                    S.remember(sec.id, name=en, name_zh=vals[1])
            out[sec.id] = {
                "price": _num(vals[3]), "prevClose": _num(vals[4]), "open": _num(vals[5]),
                "chg": _num(vals[31]), "pct": _num(vals[32]), "high": _num(vals[33]), "low": _num(vals[34]),
                "volume": _num(vals[6]), "time": vals[30],
            }
    return out


def _sina_batch(secs: list[Sec]) -> dict[str, dict]:
    out = {}
    for s in secs:
        if s.kind == "index":
            continue
        try:
            if s.mkt == "US":
                q = gskill.us_stock_quote_sina(s.code)
            elif s.mkt == "HK":
                q = gskill.hk_stock_quote_sina(s.code)
            else:
                continue
        except Exception:
            continue
        price = q.get("price") or q.get("current")
        if not price:
            continue
        prev = q.get("prev_close") or q.get("last_close")
        out[s.id] = {"price": price, "prevClose": prev, "open": q.get("open"), "high": q.get("high"),
                     "low": q.get("low"), "chg": q.get("change"), "pct": q.get("change_pct"),
                     "volume": q.get("volume"), "time": q.get("timestamp")}
    return out


def _finnhub_batch(secs: list[Sec]) -> dict[str, dict]:
    out = {}
    for s in secs:
        if s.mkt != "US" or s.kind != "stock":
            continue
        q = finnhub_src.quote(s.code)
        if q:
            out[s.id] = {"price": q["c"], "prevClose": q.get("pc"), "open": q.get("o"), "high": q.get("h"),
                         "low": q.get("l"), "chg": q.get("d"), "pct": q.get("dp"), "volume": None,
                         "time": datetime.fromtimestamp(q.get("t", 0), timezone.utc).isoformat()}
    return out


QUOTE_PROVIDERS = [
    Provider("tencent.quote", _tencent_batch, TIER_PERSONAL, 8),
    Provider("sina.quote", _sina_batch, TIER_PERSONAL, 12),
    Provider("finnhub.quote", _finnhub_batch, TIER_KEYED, 20),
]


def quotes(ids: list[str]) -> dict[str, dict]:
    """Batch quotes. Ids missing from the first provider's answer are retried down the chain."""
    secs = [S.get(i) for i in dict.fromkeys(ids)]
    result: dict[str, dict] = {}
    pending = secs
    for p in QUOTE_PROVIDERS:
        if not pending:
            break
        res = route([p], pending)
        for sid, q in (res.data or {}).items():
            q["source"] = res.source
            result[sid] = q
        pending = [s for s in pending if s.id not in result]
    out = {}
    for s in secs:
        q = result.get(s.id)
        if q:
            out[s.id] = {**S.get(s.id).to_api(), **q}
    return out


# --- candles ----------------------------------------------------------------
# Range -> (Tencent period, bar count). 1D is intraday, built from minute data.
RANGES = {"1M": ("day", 22), "6M": ("day", 126), "1Y": ("week", 52), "5Y": ("month", 60), "MAX": ("month", 640)}
YAHOO_RANGE = {"1M": ("1d", "1mo"), "6M": ("1d", "6mo"), "1Y": ("1wk", "1y"), "5Y": ("1mo", "5y"), "MAX": ("1mo", "max")}


def _bar(t: str, o, h, lo, c, v) -> dict:
    return {"t": t, "o": float(o), "h": float(h), "l": float(lo), "c": float(c), "v": float(v or 0)}


def _tencent_kline(sec: Sec, rng: str) -> list[dict]:
    period, n = RANGES[rng]
    sym = sec.tencent
    if sec.mkt == "US" and sec.kind == "stock" and not sec.us_suffix:
        quotes([sec.id])  # learns the exchange suffix (OQ / N / AM)
        sym = S.get(sec.id).tencent
    fq = "hfq" if rng == "MAX" else "qfq"   # full history: backward-adjusted keeps early prices positive
    r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                     params={"param": f"{sym},{period},,,{n},{fq}"}, headers=UA, timeout=10)
    d = (r.json().get("data") or {}).get(sym) or {}
    raw = d.get(fq + period) or d.get(period) or []
    return [_bar(it[0], it[1], it[3], it[4], it[2], it[5]) for it in raw if isinstance(it, list) and len(it) >= 6]


def _tencent_minute(sec: Sec) -> list[dict]:
    """Minute prices -> 10-minute OHLC bars (CN and HK; Tencent has no US minute data)."""
    if sec.mkt == "US":
        return []
    sym = sec.tencent
    r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/minute/query", params={"code": sym},
                     headers=UA, timeout=10)
    rows = (((r.json().get("data") or {}).get(sym) or {}).get("data") or {}).get("data") or []
    bars: dict[str, dict] = {}
    prev_vol = 0.0
    for row in rows:
        parts = row.split()
        if len(parts) < 3:
            continue
        hhmm, price, cum_vol = parts[0], float(parts[1]), float(parts[2])
        key = f"{hhmm[:2]}:{int(hhmm[2:]) // 10 * 10:02d}"
        vol = max(0.0, cum_vol - prev_vol)
        prev_vol = cum_vol
        b = bars.get(key)
        if b is None:
            bars[key] = {"t": key, "o": price, "h": price, "l": price, "c": price, "v": vol}
        else:
            b["h"], b["l"], b["c"], b["v"] = max(b["h"], price), min(b["l"], price), price, b["v"] + vol
    return list(bars.values())


def _yahoo(sec: Sec, rng: str) -> list[dict]:
    interval, yr = ("5m", "1d") if rng == "1D" else YAHOO_RANGE[rng]
    r = requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{sec.yahoo}",
                     params={"interval": interval, "range": yr}, headers=UA, timeout=12)
    r.raise_for_status()
    ch = (r.json().get("chart", {}).get("result") or [{}])[0]
    off = (ch.get("meta") or {}).get("gmtoffset", 0)
    q = (ch.get("indicators", {}).get("quote") or [{}])[0]
    out = []
    for i, ts in enumerate(ch.get("timestamp") or []):
        o, h, lo, c = (q.get(k, [None])[i] for k in ("open", "high", "low", "close"))
        if None in (o, h, lo, c):
            continue
        local = datetime.fromtimestamp(ts + off, timezone.utc)
        t = local.strftime("%H:%M") if rng == "1D" else local.strftime("%Y-%m-%d")
        out.append(_bar(t, o, h, lo, c, (q.get("volume") or [0])[i]))
    if rng == "1D":  # 5-minute -> 10-minute
        merged: dict[str, dict] = {}
        for b in out:
            key = b["t"][:3] + f"{int(b['t'][3:]) // 10 * 10:02d}"
            m = merged.get(key)
            if m is None:
                merged[key] = {**b, "t": key}
            else:
                m["h"], m["l"], m["c"], m["v"] = max(m["h"], b["h"]), min(m["l"], b["l"]), b["c"], m["v"] + b["v"]
        out = list(merged.values())
    return out


def _sina_us(sec: Sec, rng: str) -> list[dict]:
    if sec.mkt != "US" or sec.kind != "stock" or rng not in ("1M", "6M"):
        return []
    rows = gskill.us_stock_kline_sina(sec.code, RANGES[rng][1])
    return [_bar(r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows]


def _tushare(sec: Sec, rng: str) -> list[dict]:
    if sec.kind == "index" or rng == "1D":
        return []
    api = {"CN": {"day": "daily", "week": "weekly", "month": "monthly"},
           "HK": {"day": "hk_daily"}, "US": {"day": "us_daily"}}[sec.mkt].get(RANGES[rng][0])
    if not api:
        return []
    days = {"1M": 45, "6M": 200, "1Y": 400, "5Y": 1900, "MAX": 12000}[rng]
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    rows = tushare_src.call(api, ts_code=tushare_src.ts_code(sec.mkt, sec.code), start_date=start)
    rows.sort(key=lambda r: r["trade_date"])
    return [_bar(f"{r['trade_date'][:4]}-{r['trade_date'][4:6]}-{r['trade_date'][6:]}", r["open"], r["high"],
                 r["low"], r["close"], r.get("vol")) for r in rows][-RANGES[rng][1]:]


def _finnhub(sec: Sec, rng: str) -> list[dict]:
    if sec.mkt != "US" or sec.kind != "stock":
        return []
    res, days = {"1D": ("5", 1), "1M": ("D", 32), "6M": ("D", 190), "1Y": ("W", 370), "5Y": ("M", 1830), "MAX": ("M", 12000)}[rng]
    end = int(time.time())
    rows = finnhub_src.candles(sec.code, res, end - days * 86400, end)
    fmt = "%H:%M" if rng == "1D" else "%Y-%m-%d"
    return [{**r, "t": datetime.fromtimestamp(r["t"] / 1000, timezone.utc).strftime(fmt)} for r in rows]


def bars(sec_id: str, rng: str) -> dict:
    rng = rng.upper()
    if rng not in RANGES and rng != "1D":
        rng = "6M"
    sec = S.get(sec_id)
    if rng == "1D":
        providers = [Provider("tencent.minute", lambda s, r: _tencent_minute(s), TIER_PERSONAL, 10),
                     Provider("yahoo.chart", _yahoo, TIER_PERSONAL, 12),
                     Provider("finnhub.candles", _finnhub, TIER_KEYED, 15)]
        ttl = 30
    elif rng == "MAX" and sec.mkt != "CN":
        providers = [Provider("yahoo.chart", _yahoo, TIER_PERSONAL, 15),
                     Provider("tencent.kline", _tencent_kline, TIER_PERSONAL, 10)]
        ttl = 3600 * 12
    else:
        providers = [Provider("tencent.kline", _tencent_kline, TIER_PERSONAL, 10),
                     Provider("yahoo.chart", _yahoo, TIER_PERSONAL, 12),
                     Provider("sina.kline", _sina_us, TIER_PERSONAL, 12),
                     Provider("tushare.daily", _tushare, TIER_KEYED, 15),
                     Provider("finnhub.candles", _finnhub, TIER_KEYED, 15)]
        ttl = 600 if rng in ("1M", "6M") else 3600 * 6
    live = (quotes([sec_id]).get(sec_id) or {}).get("price")

    def plausible(rows: list[dict]) -> bool:
        """Quality gate: last close near the live quote, no >60% bar-to-bar jumps (daily/weekly)."""
        if any(r["c"] <= 0 for r in rows):
            return False
        if rng != "MAX" and live and rows and abs(rows[-1]["c"] / live - 1) > 0.25:
            return False
        if rng in ("1M", "6M", "1Y"):
            for a, b in zip(rows, rows[1:]):
                if a["c"] and abs(b["c"] / a["c"] - 1) > 0.6:
                    return False
        return True

    res = route(providers, sec, rng, cache_key=f"bars:{sec_id}:{rng}", ttl=ttl, persist=rng != "1D",
                validate=plausible)
    return {"id": sec_id, "range": rng, "unit": "i" if rng == "1D" else RANGES[rng][0][0],
            "bars": res.data or [], **res.meta()}


def detail_quote(sec_id: str) -> dict:
    """Rich quote for the company header: valuation fields where the source has them."""
    sec = S.get(sec_id)
    base = quotes([sec_id]).get(sec_id) or {}
    extra: dict = {}
    try:
        if sec.mkt == "CN" and sec.kind == "stock":
            q = askill.tencent_quote([sec.code]).get(sec.code) or {}
            extra = {"peTtm": q.get("pe_ttm"), "pb": q.get("pb"), "mcap": (q.get("mcap_yi") or 0) * 1e8 or None,
                     "turnoverPct": q.get("turnover_pct"), "limitUp": q.get("limit_up"), "limitDown": q.get("limit_down")}
        elif sec.kind == "stock":
            q = (gskill.hk_stock_quote_tencent(sec.code) if sec.mkt == "HK" else gskill.us_stock_quote_tencent(sec.code)) or {}
            if q.get("name_en"):
                S.remember(sec.id, name=q["name_en"].title() if q["name_en"].isupper() else q["name_en"])
            extra = {"peTtm": q.get("pe"), "pb": q.get("pb"), "eps": q.get("eps"),
                     "mcap": (q.get("market_cap") or 0) * 1e8 or None,  # Tencent reports 亿
                     "hi52": q.get("high_52w"), "lo52": q.get("low_52w")}
    except Exception:
        extra = {}
    base = {**base, **S.get(sec_id).to_api()} if base else base
    return {**base, **{k: v for k, v in extra.items() if v not in (None, 0, "")}}
