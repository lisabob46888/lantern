"""Event connectors: each returns raw events in one shape, newest first.

RawEvent keys: source, source_id, kind, published_at (epoch ms UTC), title, body,
url, lang, markets (hint), symbols (canonical ids, hint), level (source importance hint).
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone

import requests

import app.vendor  # noqa: F401
import askill
import gskill
import newsradar

from app.config import settings
from app.services import securities as S
from app.sources import finnhub_src

CST = timezone(timedelta(hours=8))
UA = askill.UA


def _cst_ms(s: str) -> int:
    """'YYYY-MM-DD HH:MM:SS' in Beijing time -> epoch ms."""
    s = s.strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s, fmt).replace(tzinfo=CST).timestamp() * 1000)
        except ValueError:
            continue
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _split_title(title: str, body: str) -> tuple[str, str]:
    """Chinese wires often send '【headline】body' with an empty title."""
    body = re.sub(r"^(财联社|新华社|央视新闻|证券时报|每经)?\d{1,2}月\d{1,2}日电[，,]\s*", "", (body or "").strip())
    m = re.match(r"^【([^】]{4,120})】(.*)$", body or "", flags=re.S)
    if m:
        return (title or m.group(1)).strip(), m.group(2).strip()
    return (title or (body or "")[:80]).strip(), (body or "").strip()


_HK_RX = re.compile(r"港股|恒生|港交所|恒指|南向|香港|HKEX|Hang Seng", re.I)
_US_RX = re.compile(r"美股|美联储|纳斯达克|标普|道指|华尔街|美国|美债|Fed\b|Nasdaq|S&P|Dow", re.I)


def _cn_markets(text: str) -> list[str]:
    m = ["CN"]
    if _HK_RX.search(text):
        m.append("HK")
    if _US_RX.search(text):
        m.append("US")
    return m


def _stock_ids(stock_list: list) -> list[str]:
    out = []
    em_mkt = {"1": "CN", "0": "CN", "116": "HK", "105": "US", "106": "US", "107": "US"}
    for s in stock_list or []:
        if isinstance(s, str):  # Eastmoney "secid" form: "1.600519", "116.00700", "105.NVDA"
            m = re.match(r"(\d+)\.(\w+)", s)
            if m and m.group(1) in em_mkt:
                out.append(f"{em_mkt[m.group(1)]}:{m.group(2)}")
            continue
        raw = s.get("StockID") or s.get("secu_code") or s.get("code") or ""
        name = s.get("name") or s.get("secu_name") or ""
        m = re.match(r"(sh|sz|bj)(\d{6})", raw, re.I)
        if m:
            sid = f"CN:{m.group(2)}"
        elif re.match(r"hk\d{5}", raw, re.I):
            sid = f"HK:{raw[2:]}"
        elif re.match(r"us", raw, re.I):
            sid = f"US:{raw[2:].upper()}"
        else:
            sid = S.normalize(raw) if raw else None
        if sid:
            if name:
                S.remember(sid, name_zh=name)
            out.append(sid)
    return out


def cls() -> list[dict]:
    """Cailian Press 7x24 wire (CN/HK focus). Level A/B/C is CLS's own importance mark."""
    params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5",
              "last_time": "", "refresh_type": "1", "rn": "50"}
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    d = requests.get(f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}",
                     headers={"User-Agent": UA, "Referer": "https://www.cls.cn/"}, timeout=10).json()
    out = []
    for it in (d.get("data") or {}).get("roll_data") or []:
        if it.get("is_ad"):
            continue
        title, body = _split_title(it.get("title") or "", it.get("content") or it.get("brief") or "")
        out.append({"source": "cls", "source_id": str(it.get("id")), "kind": "news",
                    "published_at": int(it.get("ctime", 0)) * 1000, "title": title, "body": body,
                    "url": f"https://www.cls.cn/detail/{it.get('id')}", "lang": "zh",
                    "markets": _cn_markets(title + body), "symbols": _stock_ids(it.get("stock_list")),
                    "level": it.get("level")})
    return out


def em_global() -> list[dict]:
    """Eastmoney 7x24 global fast news."""
    r = askill.em_get("https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
                      params={"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "",
                              "pageSize": "50", "req_trace": str(uuid.uuid4())},
                      headers={"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"}, timeout=10)
    out = []
    for it in (r.json().get("data") or {}).get("fastNewsList") or []:
        title, body = _split_title(it.get("title") or "", it.get("summary") or "")
        out.append({"source": "em_global", "source_id": str(it.get("code")), "kind": "news",
                    "published_at": _cst_ms(it.get("showTime", "")), "title": title, "body": body,
                    "url": f"https://finance.eastmoney.com/a/{it.get('code')}.html", "lang": "zh",
                    "markets": _cn_markets(title + body), "symbols": _stock_ids(it.get("stockList")),
                    "level": None})
    return out


def finnhub_news() -> list[dict]:
    out = []
    for it in finnhub_src.general_news("general"):
        syms = [f"US:{t.strip().upper()}" for t in (it.get("related") or "").split(",") if t.strip()]
        out.append({"source": "finnhub", "source_id": str(it.get("id")), "kind": "news",
                    "published_at": int(it.get("datetime", 0)) * 1000, "title": it.get("headline", "").strip(),
                    "body": (it.get("summary") or "").strip(), "url": it.get("url"), "lang": "en",
                    "markets": ["US"], "symbols": syms, "level": None, "publisher": it.get("source")})
    return out


def cninfo(sec_ids: list[str]) -> list[dict]:
    """cninfo announcements for watched A-shares."""
    out = []
    for sid in sec_ids:
        if not sid.startswith("CN:"):
            continue
        code = sid[3:]
        for a in askill.cninfo_announcements(code)[:10]:
            out.append({"source": "cninfo", "source_id": a.get("url") or f"{code}:{a.get('title')}",
                        "kind": "filing", "published_at": _cst_ms(a.get("date", "")), "title": a.get("title", ""),
                        "body": "", "url": a.get("url"), "lang": "zh", "markets": ["CN"], "symbols": [sid],
                        "level": None})
    return out


def company_news(sec_ids: list[str]) -> list[dict]:
    """Per-symbol news for watched US/HK names (Finnhub for US, Yahoo search for HK)."""
    out = []
    for sid in sec_ids:
        sec = S.get(sid)
        if sec.kind != "stock":
            continue
        try:
            if sec.mkt == "US":
                for it in finnhub_src.company_news(sec.code, days=3)[:15]:
                    out.append({"source": "finnhub", "source_id": str(it.get("id")), "kind": "news",
                                "published_at": int(it.get("datetime", 0)) * 1000,
                                "title": it.get("headline", "").strip(), "body": (it.get("summary") or "").strip(),
                                "url": it.get("url"), "lang": "en", "markets": ["US"], "symbols": [sid],
                                "level": None, "publisher": it.get("source")})
            elif sec.mkt == "HK":
                for it in gskill.stock_news(sec.yahoo, 10):
                    if not it.get("publish_time"):
                        continue
                    out.append({"source": "yahoo", "source_id": it.get("link") or it.get("title"),
                                "kind": "news", "published_at": int(it["publish_time"]) * 1000,
                                "title": it.get("title", ""), "body": "", "url": it.get("link"), "lang": "en",
                                "markets": ["HK"], "symbols": [sid], "level": None,
                                "publisher": it.get("publisher")})
        except Exception:
            continue
    return out


def _edgar_ms(d: str) -> int:
    """EDGAR filing date (YYYYMMDD or YYYY-MM-DD, US Eastern) -> epoch ms at 16:00 ET."""
    d = d.replace("-", "")
    try:
        dt = datetime.strptime(d, "%Y%m%d").replace(hour=16, tzinfo=timezone(timedelta(hours=-5)))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return int(datetime.now(timezone.utc).timestamp() * 1000)


_EDGAR_LINE = re.compile(r"^(?P<form>\S+(?: \S+)*?)\s{2,}(?P<company>.+?)\s{2,}(?P<cik>\d+)\s+(?P<date>\d{8})\s+(?P<path>edgar/\S+)\s*$")


def _edgar_daily(forms: set[str]) -> list[dict]:
    """Parse the newest EDGAR daily form index (column widths vary, so match by pattern)."""
    day = datetime.now(timezone(timedelta(hours=-5))).date()
    for back in range(7):
        d = day - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        url = (f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{(d.month - 1) // 3 + 1}/"
               f"form.{d.strftime('%Y%m%d')}.idx")
        try:
            raw = gskill.official_get(url)
        except Exception as e:
            if "SEC_CONTACT" in str(e):
                raise
            continue
        out = []
        for line in raw.splitlines():
            m = _EDGAR_LINE.match(line)
            if m and m.group("form") in forms:
                out.append(m.groupdict())
        if out:
            return out
    return []


def edgar() -> list[dict]:
    """SEC EDGAR daily index: 8-K material events. Needs SEC_CONTACT (SEC's User-Agent rule)."""
    if not settings.sec_contact:
        return []
    out = []
    for f in _edgar_daily({"8-K"})[:300]:
        url = f"https://www.sec.gov/Archives/{f['path']}"
        out.append({"source": "edgar", "source_id": url, "kind": "filing", "published_at": _edgar_ms(f["date"]),
                    "title": f"8-K: {f['company'].title()}", "body": "", "url": url, "lang": "en",
                    "markets": ["US"], "symbols": [], "level": None, "cik": f["cik"]})
    return out


def rss() -> list[dict]:
    """108 curated RSS feeds across 12 industry tracks (Vibe-Research news radar)."""
    radar = newsradar.fetch_radar()
    out = []
    for ind in radar.get("industries") or []:
        for it in ind.get("items") or []:
            if not it.get("ts"):
                continue  # undated items cannot be placed on the wire
            title = (it.get("title") or "").strip()
            out.append({"source": "rss", "source_id": it.get("url") or title, "kind": "rss",
                        "published_at": int(it["ts"]) * 1000, "title": title,
                        "body": (it.get("summary") or "").strip(), "url": it.get("url"),
                        "lang": "zh" if re.search(r"[\u4e00-\u9fff]", title) else "en",
                        "markets": [], "symbols": [], "level": None, "industry": ind.get("key"),
                        "publisher": it.get("source")})
    return out
