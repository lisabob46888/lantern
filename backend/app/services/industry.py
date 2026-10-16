"""Industry view: tagged news from the pipeline + a weekly GLM web-search research pack.

Every number in the research pack must carry a source URL from the search results;
sections without a citation are dropped. There is no "prosperity index": no reachable
source publishes one, so the view leaves it out rather than invent it.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.config import settings
from app.hub import hub
from app.pipeline.ingest import event_to_api
from app.services import marketdata
from app.store import db

log = logging.getLogger("lantern.industry")

INDUSTRIES = {
    "ai": ("AI & large models", "AI / 大模型"),
    "semi": ("Semiconductors", "半导体 / 芯片"),
    "robot": ("Robotics & automation", "机器人 / 自动化"),
    "auto": ("Autos & EVs", "汽车 / 新能源车"),
    "energy": ("Energy & renewables", "能源 / 新能源"),
    "bio": ("Biotech & healthcare", "生物医药 / 健康"),
    "space": ("Aerospace & space", "航天 / 太空"),
    "security": ("Cybersecurity", "网络安全"),
    "tech": ("Internet platforms", "科技 / 互联网"),
    "consumer": ("Consumer electronics", "消费电子 / 数码"),
}
MKT_NAME = {"US": "United States", "CN": "mainland China (A-shares)", "HK": "Hong Kong"}
CODE = {"ai": "AIM", "semi": "SEM", "robot": "ROB", "auto": "EVA", "energy": "ENR", "bio": "BIO", "space": "SPC",
        "security": "CYB", "tech": "NET", "consumer": "CEL"}

PACK_PROMPT = """Research the {name} industry as it relates to listed companies in {market}, as of {today}.
Use web search. Every figure must come from a search result and carry its URL. Return:
{{
 "stance_en","stance_zh": one short phrase on current conditions,
 "view_en","view_zh": 2-3 sentences on the state of the industry and what moves the stocks,
 "view_points": [{{"en","zh"}}] 3 short supporting points,
 "week_head_en","week_head_zh": one line summarising the past 7 days,
 "week_points": [{{"en","zh"}}] 3 short points on what happened in the past 7 days,
 "drivers": [{{"k_en","k_zh","v_en","v_zh"}}] up to 4 bull-case drivers,
 "risks": [{{"k_en","k_zh","v_en","v_zh"}}] up to 4 bear-case risks,
 "size": {{"title_en","title_zh","unit","series": [{{"year": "2024", "value": 0, "estimate": false}}], "cagr": "x% (yyyy-yyyy)", "url": "..."}} or null,
 "chain": [{{"tier_en","tier_zh","segments": [{{"name_en","name_zh","products_en","products_zh",
            "companies": [{{"symbol","market":"US"|"CN"|"HK","name","tags_en":[],"tags_zh":[]}}]}}]}}]
            exactly 3 tiers (upstream, midstream, downstream), 1-3 segments each, 2-4 companies per segment,
            tags = up to 2 two-word roles such as "GPU leader",
 "share": {{"title_en","title_zh","items": [{{"k","v": percent number}}], "note_en","note_zh","url": "..."}} or null,
 "metrics": [{{"name_en","name_zh","value","chg","note_en","note_zh","url"}}] up to 6 industry metrics with their
            latest reading; note = one sentence on what the metric says now,
 "plans": [{{"who","what_en","what_zh","cap","when","url"}}] up to 5 capacity or investment plans,
 "peers": [{{"symbol","market":"US"|"CN"|"HK","name"}}] up to 10 listed leaders in this market (any market for "ALL")
}}
Use exchange codes (US ticker, 6-digit A-share code, 5-digit HK code). Omit any section you cannot cite."""


def _pack(ind: str, mkt: str) -> dict | None:
    key = f"industry_pack:{ind}:{mkt}"
    hit = db.kv_get(key)
    if hit:
        return hit[0]
    if not settings.llm_enabled:
        return None
    from app.enrich import llm
    from app.enrich.prompts import FRAME
    from app.enrich.worker import _sec_id, name_matches
    name = INDUSTRIES[ind][0]
    out, sources, model = llm.chat_json(
        FRAME, PACK_PROMPT.format(name=name, market=MKT_NAME.get(mkt, "the US, China A-share and Hong Kong markets"),
                                  today=datetime.now(timezone.utc).date().isoformat()),
        web_search=True, max_tokens=6000, recency="oneYear",
        search_query=f"{name} industry {mkt if mkt != 'ALL' else 'global'} market size share leaders capacity 2026")

    def ok(url: str | None) -> bool:
        return llm.cited(url, sources)

    # One search rarely covers every section: fill the value chain and market size with focused searches.
    region = mkt if mkt != "ALL" else "global"
    for key_, query, ask in (
        ("chain", f"{name} industry value chain upstream midstream downstream companies",
         '"chain" exactly as specified above'),
        ("size", f"{name} market size {region} 2025 2026 forecast",
         '"size" exactly as specified above'),
    ):
        if out.get(key_):
            continue
        try:
            extra, more, _ = llm.chat_json(FRAME, PACK_PROMPT.format(name=name, market=MKT_NAME.get(mkt, region),
                                                                      today=datetime.now(timezone.utc).date().isoformat())
                                           + f"\nReturn ONLY the key {ask}.", web_search=True, max_tokens=4000,
                                           recency="oneYear", search_query=query)
            if extra.get(key_):
                out[key_] = extra[key_]
                sources = sources + [m for m in more if m["url"] not in {x["url"] for x in sources}]
        except Exception as e:
            log.info("pack follow-up %s/%s %s: %s", ind, mkt, key_, e)

    if out.get("size") and not ok(out["size"].get("url")):
        out["size"] = None
    if out.get("share") and not ok(out["share"].get("url")):
        out["share"] = None
    out["metrics"] = [m for m in out.get("metrics") or [] if ok(m.get("url"))]
    out["plans"] = [p for p in out.get("plans") or [] if ok(p.get("url"))]
    named = [(sid, c.get("name") or "") for tier in out.get("chain") or [] for seg in tier.get("segments") or []
             for c in seg.get("companies") or [] if (sid := _sec_id(c))]
    named += [(sid, p.get("name") or "") for p in out.get("peers") or [] if (sid := _sec_id(p))]
    live = marketdata.quotes([sid for sid, _ in named])
    good = {sid for sid, nm in named if sid in live and name_matches(nm, live[sid])}   # drop wrong/unknown tickers
    for tier in out.get("chain") or []:
        for seg in tier.get("segments") or []:
            seg["companies"] = [{"id": sid, "name": c.get("name")} for c in seg.get("companies") or []
                                if (sid := _sec_id(c)) in good]
    out["peerIds"] = [sid for p in out.pop("peers", []) or [] if (sid := _sec_id(p)) in good]
    out["sources"], out["model"], out["generatedAt"] = sources, model, db.now_ms()
    db.kv_set(key, out, "glm.websearch", 7 * 86400)
    return out


_inflight: set[str] = set()
_errors: dict[str, str] = {}
_lock = threading.Lock()


def _pack_async(ind: str, mkt: str) -> tuple[dict | None, str]:
    """Cached pack, or start building it in the background (it takes a minute of search + reasoning)."""
    key = f"{ind}:{mkt}"
    hit = db.kv_get(f"industry_pack:{key}")
    if hit:
        return hit[0], "ready"
    if not settings.llm_enabled:
        return None, "disabled"
    with _lock:
        if key in _inflight:
            return None, "pending"
        if key in _errors:
            return None, "failed"
        _inflight.add(key)

    def job() -> None:
        try:
            _pack(ind, mkt)
            hub.publish("industry", "industry_pack", {"id": ind, "mkt": mkt})
        except Exception as e:
            log.warning("industry pack %s failed: %s", key, e)
            _errors[key] = str(e)[:200]
        finally:
            with _lock:
                _inflight.discard(key)

    threading.Thread(target=job, daemon=True, name=f"pack-{key}").start()
    return None, "pending"


def _one_month(sid: str) -> float | None:
    rows = marketdata.bars(sid, "1M")["bars"]
    return round((rows[-1]["c"] / rows[0]["o"] - 1) * 100, 2) if len(rows) > 1 and rows[0]["o"] else None


def _peer_row(sid: str) -> dict:
    """One peer-table row: live quote + market cap / P/E / growth / margin where a source has them."""
    hit = db.kv_get(f"peer_row:{sid}")
    if hit:
        return hit[0]
    import app.vendor  # noqa: F401
    import gskill
    from app.services import securities as S
    q = marketdata.detail_quote(sid)
    row = {"id": sid, "ticker": q.get("ticker"), "name": q.get("name"), "nameZh": q.get("nameZh"), "mkt": q.get("mkt"),
           "ccy": q.get("ccy"), "price": q.get("price"), "pct": q.get("pct"), "mcap": q.get("mcap"),
           "pe": q.get("peTtm"), "revGrowth": None, "grossMargin": None, "fwdPe": None, "m1": _one_month(sid)}
    sec = S.get(sid)
    if sec.mkt in ("US", "HK"):
        try:
            k = gskill.key_statistics(sec.yahoo) or {}
            row.update({"revGrowth": (k.get("revenue_growth") or 0) * 100 if k.get("revenue_growth") is not None else None,
                        "grossMargin": (k.get("gross_margin") or 0) * 100 if k.get("gross_margin") is not None else None,
                        "fwdPe": k.get("forward_pe"), "mcap": row["mcap"] or k.get("market_cap")})
        except Exception:
            pass
    db.kv_set(f"peer_row:{sid}", row, "peer_row", 6 * 3600)
    return row


def peer_table(ids: list[str]) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        return [r for r in ex.map(_peer_row, ids[:12]) if r.get("price") is not None]


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None and x > 0)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _news_counts(ind: str, mkt: str) -> tuple[int, int]:
    now = db.now_ms()
    cond = "industries LIKE ? AND enrich_state='done'" + ("" if mkt == "ALL" else " AND markets LIKE ?")
    args = [f'%"{ind}"%'] + ([] if mkt == "ALL" else [f'%"{mkt}"%'])
    cur = db.one(f"SELECT count(*) n FROM events WHERE {cond} AND published_at>=?", (*args, now - 7 * 86400_000))["n"]
    prev = db.one(f"SELECT count(*) n FROM events WHERE {cond} AND published_at>=? AND published_at<?",
                  (*args, now - 14 * 86400_000, now - 7 * 86400_000))["n"]
    return cur, prev


def industry(ind: str, mkt: str = "ALL") -> dict:
    if ind not in INDUSTRIES:
        raise KeyError(ind)
    since = db.now_ms() - 14 * 86400_000
    rows = db.query("SELECT * FROM events WHERE industries LIKE ? AND published_at>=? AND enrich_state='done' "
                    "ORDER BY published_at DESC LIMIT 80", (f'%"{ind}"%', since))
    events = [event_to_api(r) for r in rows]
    if mkt != "ALL":
        events = [e for e in events if not e["mkts"] or mkt in e["mkts"]]
    pack, state = _pack_async(ind, mkt)
    err = _errors.pop(f"{ind}:{mkt}", None) if state == "failed" else None
    peers = peer_table((pack or {}).get("peerIds") or [])
    m1 = [p["m1"] for p in peers if p.get("m1") is not None]
    ret1m = round(sum(m1) / len(m1), 2) if m1 else None
    if ret1m is not None:
        db.kv_set(f"ind_ret1m:{ind}:{mkt}", ret1m, "peers", 3600)
    n7, prev7 = _news_counts(ind, mkt)
    size = (pack or {}).get("size") or None
    en, zh = INDUSTRIES[ind]
    return {"id": ind, "code": CODE[ind] + ("" if mkt == "ALL" else mkt), "name": en, "nameZh": zh, "mkt": mkt,
            "developments": events[:25], "pack": pack, "packState": state, "packError": err, "peers": peers,
            "stats": {"ret1m": ret1m, "ret1mBasis": f"equal-weight average of {len(m1)} leaders" if m1 else None,
                      "news7d": n7, "news7dPrev": prev7,
                      "size": ({"value": size["series"][-1]["value"] if size.get("series") else None,
                                "year": size["series"][-1]["year"] if size.get("series") else None,
                                "estimate": size["series"][-1].get("estimate") if size.get("series") else None,
                                "unit": size.get("unit"), "cagr": size.get("cagr")} if size else None),
                      "medianPe": _median([p.get("fwdPe") or p.get("pe") for p in peers]),
                      "peBasis": f"{len([p for p in peers if p.get('fwdPe') or p.get('pe')])} listed peers"}}


def catalog(market: str = "ALL") -> list[dict]:
    """One row per industry x market (the prototype's list), with 1M return once its leaders are known."""
    since = db.now_ms() - 7 * 86400_000
    out = []
    mkts = ["US", "CN", "HK"] if market == "ALL" else [market]
    for k, (en, zh) in INDUSTRIES.items():
        for m in mkts:
            n = db.one("SELECT count(*) AS n FROM events WHERE industries LIKE ? AND published_at>=? "
                       "AND enrich_state='done' AND markets LIKE ?", (f'%"{k}"%', since, f'%"{m}"%'))["n"]
            r = db.kv_get(f"ind_ret1m:{k}:{m}", allow_stale=True)
            out.append({"id": f"{k}:{m}", "ind": k, "mkt": m, "code": CODE[k] + m, "name": en, "nameZh": zh,
                        "events7d": n, "ret1m": r[0] if r else None})
    return out
