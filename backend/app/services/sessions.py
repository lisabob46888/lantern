"""Exchange sessions and trading calendars.

Session hours are exchange rules; trading days come from Tushare calendars when a
token is set, otherwise weekdays only (flagged as unverified so the UI can say so).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.sources import tushare_src
from app.sources.router import Provider, TIER_KEYED, route

# Minutes after local midnight.
RULES = {
    "US": {"city": "NY", "tz": "America/New_York", "sessions": [[570, 960]], "pre": 240, "post": 1200},
    "CN": {"city": "SH", "tz": "Asia/Shanghai", "sessions": [[570, 690], [780, 900]], "pre": 555, "post": 900},
    "HK": {"city": "HK", "tz": "Asia/Hong_Kong", "sessions": [[570, 720], [780, 960]], "pre": 540, "post": 970},
}


def _tushare_days(mkt: str) -> list[str]:
    today = datetime.now(ZoneInfo(RULES[mkt]["tz"])).date()
    return tushare_src.trade_cal(mkt, (today - timedelta(days=40)).strftime("%Y%m%d"),
                                 (today + timedelta(days=40)).strftime("%Y%m%d"))


def trading_days(mkt: str) -> tuple[list[str], str]:
    res = route([Provider(f"tushare.cal.{mkt}", _tushare_days, TIER_KEYED, 15)], mkt,
                cache_key=f"cal:{mkt}", ttl=12 * 3600, persist=True)
    if res.ok and res.data:
        return [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in res.data], res.source or "tushare"
    today = datetime.now(ZoneInfo(RULES[mkt]["tz"])).date()
    days = [(today + timedelta(days=i)) for i in range(-40, 41)]
    return [d.isoformat() for d in days if d.weekday() < 5], "weekdays (unverified)"


def status(mkt: str, now: datetime | None = None) -> dict:
    r = RULES[mkt]
    local = (now or datetime.now(ZoneInfo(r["tz"]))).astimezone(ZoneInfo(r["tz"]))
    days, src = trading_days(mkt)
    today = local.date().isoformat()
    mins = local.hour * 60 + local.minute
    s = r["sessions"]
    if today not in days:
        st = "CLOSED"
    elif any(a <= mins < b for a, b in s):
        st = "OPEN"
    elif r["pre"] <= mins < s[0][0]:
        st = "PRE"
    elif len(s) > 1 and s[0][1] <= mins < s[1][0]:
        st = "LUNCH"
    elif s[-1][1] <= mins < r["post"]:
        st = "POST"
    else:
        st = "CLOSED"
    past = [d for d in days if d <= today]
    # last completed session's trade date: today after the close, else the previous trading day
    last_done = today if (today in days and mins >= s[-1][1]) else next((d for d in reversed(past) if d < today), None)
    return {"mkt": mkt, "city": r["city"], "tz": r["tz"], "sessions": s, "status": st, "localDate": today,
            "tradingDays": days, "lastCompleted": last_done, "calendarSource": src}


def all_status() -> list[dict]:
    return [status(m) for m in RULES]


def is_active(mkt: str) -> bool:
    return status(mkt)["status"] in ("OPEN", "PRE", "LUNCH", "POST")
