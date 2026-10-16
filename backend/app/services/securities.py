"""Security identity: ids, display tickers, per-provider symbols, index registry, search.

Canonical id = "<MKT>:<code>" with MKT in US | CN | HK, e.g. "US:NVDA", "CN:600519",
"HK:00700". Indices are "IX:<MKT>:<code>". Names come from live sources; the
registry below only defines which index codes exist and how each provider spells them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

from app.sources.router import Provider, TIER_KEYED, TIER_PERSONAL, route
from app.store import db

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
MARKETS = ("US", "CN", "HK")
CCY = {"US": "$", "HK": "HK$", "CN": "¥"}


@dataclass(frozen=True)
class IndexDef:
    code: str
    mkt: str
    name: str
    name_zh: str
    exchange: str
    tencent: str
    yahoo: str


# Reference definitions (codes and official names), not market data.
INDICES: tuple[IndexDef, ...] = (
    IndexDef("SPX", "US", "S&P 500", "标普500", "NYSE", "us.INX", "^GSPC"),
    IndexDef("NDX", "US", "Nasdaq 100", "纳斯达克100", "NASDAQ", "us.NDX", "^NDX"),
    IndexDef("IXIC", "US", "Nasdaq Composite", "纳斯达克综合指数", "NASDAQ", "us.IXIC", "^IXIC"),
    IndexDef("DJI", "US", "Dow Jones", "道琼斯", "NYSE", "usDJI", "^DJI"),
    IndexDef("000001", "CN", "SSE Composite", "上证指数", "SSE", "sh000001", "000001.SS"),
    IndexDef("399001", "CN", "SZSE Component", "深证成指", "SZSE", "sz399001", "399001.SZ"),
    IndexDef("000300", "CN", "CSI 300", "沪深300", "SSE", "sh000300", "000300.SS"),
    IndexDef("399006", "CN", "ChiNext", "创业板指", "SZSE", "sz399006", "399006.SZ"),
    IndexDef("000688", "CN", "STAR 50", "科创50", "SSE", "sh000688", "000688.SS"),
    IndexDef("HSI", "HK", "Hang Seng Index", "恒生指数", "HKEX", "hkHSI", "^HSI"),
    IndexDef("HSTECH", "HK", "Hang Seng TECH", "恒生科技指数", "HKEX", "hkHSTECH", "HSTECH.HK"),
    IndexDef("HSCEI", "HK", "HS China Enterprises", "恒生中国企业指数", "HKEX", "hkHSCEI", "^HSCE"),
)
INDEX_BY_ID = {f"IX:{i.mkt}:{i.code}": i for i in INDICES}


@dataclass
class Sec:
    id: str
    mkt: str
    code: str
    kind: str = "stock"            # stock | index
    name: str = ""
    name_zh: str = ""
    us_suffix: str = ""            # Tencent exchange suffix for US tickers: OQ | N | AM
    extra: dict = field(default_factory=dict)

    @property
    def ticker(self) -> str:
        """Display ticker in the prototype's style: NVDA, 600519, 0700.HK."""
        if self.kind == "index":
            return self.code
        if self.mkt == "HK":
            return f"{int(self.code):04d}.HK"
        return self.code

    @property
    def tencent(self) -> str:
        if self.kind == "index":
            return INDEX_BY_ID[self.id].tencent
        if self.mkt == "CN":
            return ("sh" if self.code.startswith(("6", "9", "5")) else "bj" if self.code.startswith(("8", "4")) else "sz") + self.code
        if self.mkt == "HK":
            return "hk" + self.code
        return "us" + self.code + (f".{self.us_suffix}" if self.us_suffix else "")

    @property
    def yahoo(self) -> str:
        if self.kind == "index":
            return INDEX_BY_ID[self.id].yahoo
        if self.mkt == "CN":
            return self.code + (".SS" if self.code.startswith(("6", "9", "5")) else ".SZ")
        if self.mkt == "HK":
            return f"{int(self.code):04d}.HK"
        return self.code.replace(".", "-")

    def to_api(self) -> dict:
        return {"id": self.id, "mkt": self.mkt, "code": self.code, "ticker": self.ticker,
                "kind": self.kind, "name": self.name, "nameZh": self.name_zh, "ccy": CCY[self.mkt]}


def normalize(raw: str) -> str | None:
    """Accept any common spelling and return a canonical id, without network."""
    s = raw.strip().upper()
    if not s:
        return None
    if s.startswith("IX:") and s in INDEX_BY_ID:
        return s
    m = re.fullmatch(r"(US|CN|HK):(.+)", s)
    if m:
        mkt, code = m.groups()
        if mkt == "HK":
            code = code.removesuffix(".HK").zfill(5)
        return f"{mkt}:{code}"
    m = re.fullmatch(r"(\d{1,5})\.HK", s)
    if m:
        return f"HK:{m.group(1).zfill(5)}"
    m = re.fullmatch(r"(?:SH|SZ|BJ)?(\d{6})(?:\.(?:SH|SZ|SS|BJ))?", s)
    if m:
        return f"CN:{m.group(1)}"
    if re.fullmatch(r"\d{5}", s):
        return f"HK:{s}"
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s):
        return f"US:{s}"
    return None


def get(sec_id: str) -> Sec:
    """Build a Sec, filling names/suffix from the security cache when known."""
    if sec_id in INDEX_BY_ID:
        d = INDEX_BY_ID[sec_id]
        return Sec(sec_id, d.mkt, d.code, "index", d.name, d.name_zh)
    mkt, code = sec_id.split(":", 1)
    sec = Sec(sec_id, mkt, code)
    row = db.kv_get(f"sec:{sec_id}", allow_stale=True)
    if row:
        info = row[0]
        sec.name, sec.name_zh, sec.us_suffix = info.get("name", ""), info.get("nameZh", ""), info.get("usSuffix", "")
    return sec


def remember(sec_id: str, name: str = "", name_zh: str = "", us_suffix: str = "") -> None:
    old = db.kv_get(f"sec:{sec_id}", allow_stale=True)
    info = old[0] if old else {}
    for k, v in (("name", name), ("nameZh", name_zh), ("usSuffix", us_suffix)):
        if v:
            info[k] = v
    db.kv_set(f"sec:{sec_id}", info, "securities", 365 * 86400)


# --- search -----------------------------------------------------------------

_SMART_MKT = {"sh": "CN", "sz": "CN", "bj": "CN", "hk": "HK", "us": "US"}


def _search_tencent(q: str) -> list[dict]:
    r = requests.get("https://smartbox.gtimg.cn/s3/", params={"v": 2, "q": q, "t": "all", "c": 1},
                     headers=UA, timeout=8)
    m = re.search(r'v_hint="(.*)"', r.text)
    if not m or m.group(1) in ("", "N;"):
        return []
    text = m.group(1).encode("latin-1", "ignore").decode("unicode_escape", "ignore") if "\\u" in m.group(1) else m.group(1)
    out = []
    for item in text.split("^"):
        parts = item.split("~")
        if len(parts) < 5:
            continue
        mk, code, name, _py, typ = parts[:5]
        mkt = _SMART_MKT.get(mk)
        if not mkt or not typ.startswith("GP"):
            continue
        suffix = ""
        if mkt == "US":
            code, _, suffix = code.upper().partition(".")
            if suffix == "PS":   # OTC pink sheets: skip
                continue
        sec_id = f"{mkt}:{code}"
        has_zh = bool(re.search(r"[一-鿿]", name))
        remember(sec_id, "" if has_zh else name, name if has_zh else "", suffix)
        s = get(sec_id)
        out.append(s.to_api())
    return out


def _search_finnhub(q: str) -> list[dict]:
    from app.sources import finnhub_src
    out = []
    for r in finnhub_src.symbol_lookup(q)[:10]:
        sec_id = normalize(r.get("symbol", ""))
        if not sec_id or not sec_id.startswith("US:"):
            continue
        remember(sec_id, r.get("description", "").title())
        out.append(get(sec_id).to_api())
    return out


def search(q: str) -> list[dict]:
    q = q.strip()
    if not q:
        return []
    ql = q.lower()
    idx = [get(i).to_api() for i, d in INDEX_BY_ID.items()
           if ql in d.name.lower() or q in d.name_zh or ql == d.code.lower()]
    res = route([Provider("tencent.smartbox", _search_tencent, TIER_PERSONAL, 8),
                 Provider("finnhub.lookup", _search_finnhub, TIER_KEYED, 8)],
                q, cache_key=f"search:{ql}", ttl=3600)
    return idx + (res.data or [])
