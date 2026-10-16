"""Tushare Pro provider (your own token). Endpoints the token's points level does
not cover raise a permission error, and the router parks them for hours."""
from __future__ import annotations

import threading

from app.config import settings

_pro = None
_lock = threading.Lock()


class NotConfigured(RuntimeError):
    pass


def pro():
    global _pro
    if not settings.tushare_token:
        raise NotConfigured("TUSHARE_TOKEN not set")
    with _lock:
        if _pro is None:
            import tushare as ts
            _pro = ts.pro_api(settings.tushare_token)
    return _pro


def call(api: str, **params) -> list[dict]:
    """Generic call: `call('daily', ts_code='600519.SH', start_date='20260101')`."""
    df = pro().query(api, **params)
    if df is None or df.empty:
        return []
    return df.where(df.notna(), None).to_dict("records")


def ts_code(mkt: str, code: str) -> str:
    if mkt == "CN":
        return code + (".SH" if code.startswith(("6", "9", "5")) else ".BJ" if code.startswith(("8", "4")) else ".SZ")
    if mkt == "HK":
        return code.zfill(5) + ".HK"
    return code


def trade_cal(mkt: str, start: str, end: str) -> list[str]:
    """Open trading days (YYYYMMDD) for a market between start and end."""
    if mkt == "CN":
        rows = call("trade_cal", exchange="SSE", start_date=start, end_date=end, is_open="1")
    elif mkt == "HK":
        rows = call("hk_tradecal", start_date=start, end_date=end, is_open="1")
    else:
        rows = call("us_tradecal", start_date=start, end_date=end, is_open="1")
    return sorted(r["cal_date"] for r in rows)
