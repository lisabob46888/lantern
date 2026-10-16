"""Cached GLM reads for the index, company and industry pages.

Each read is built from data Lantern already fetched (or from cited web search), cached in
SQLite, and returned with both languages. With no GLM key every function returns None and the
page shows the data without the AI paragraph.
"""
from __future__ import annotations

import json
import logging

from app.config import settings
from app.store import db

log = logging.getLogger("lantern.reads")


def _cached(key: str, ttl_s: float, build):
    hit = db.kv_get(key)
    if hit:
        return hit[0]
    if not settings.llm_enabled:
        return None
    try:
        val = build()
    except Exception as e:
        log.warning("read %s failed: %s", key, e)
        return None
    if val:
        db.kv_set(key, val, "glm", ttl_s)
    return val


def _llm(prompt: str, **kw) -> tuple[dict, list[dict]]:
    from app.enrich import llm
    from app.enrich.prompts import FRAME
    out, sources, _ = llm.chat_json(FRAME, prompt, **kw)
    return out, sources


def index_profile(sec_id: str, name: str, exchange: str) -> dict | None:
    """What the index tracks: methodology and composition, from cited search results."""
    def build():
        from app.enrich import llm
        out, sources = _llm(
            f"From the search results, describe what the {name} index ({exchange}) tracks: how constituents are "
            "chosen and weighted, roughly how many members, which sectors dominate, and what tends to move it. "
            "2-3 sentences per language. Only state figures that appear in the results. Return "
            '{"desc_en": "...", "desc_zh": "...", "members": "e.g. 500 or null", "source_url": "..."}',
            web_search=True, recency="noLimit", search_query=f"{name} index constituents methodology",
            max_tokens=1500)
        if not sources or (not out.get("desc_en") and not out.get("desc_zh")):
            return None   # nothing found: do not cache a "no results" answer
        url = out.get("source_url") or ""
        return {"desc": {"en": out.get("desc_en") or "", "zh": out.get("desc_zh") or ""},
                "members": out.get("members") if out.get("members") not in ("null", None, "") else None,
                "url": url if llm.cited(url, sources) else (sources[0]["url"] if sources else None)}
    return _cached(f"index_profile:{sec_id}", 90 * 86400, build)


def financial_read(sec_id: str, rows: list[dict], dupont: list[dict], checks: list[dict]) -> dict | None:
    if not rows:
        return None
    def build():
        out, _ = _llm(
            "From these annual financials, write two short reads for an investor, each 1-2 sentences, English and "
            "Simplified Chinese. 'fin': earnings quality and the main risk visible in the numbers. 'dupont': what drives "
            "ROE (margin, turnover or leverage) and how it changed. Use only these numbers. Return "
            '{"fin_en": "", "fin_zh": "", "dupont_en": "", "dupont_zh": ""}\n\n'
            + json.dumps({"annual": rows, "dupont": dupont, "checks": checks}, ensure_ascii=False, default=str),
            fast=True, max_tokens=1200)
        return {"fin": {"en": out.get("fin_en", ""), "zh": out.get("fin_zh", "")},
                "dupont": {"en": out.get("dupont_en", ""), "zh": out.get("dupont_zh", "")}}
    return _cached(f"fin_read:{sec_id}:{rows[0].get('period')}", 30 * 86400, build)


def analyst_view(sec_id: str, name: str, analysts: dict, headlines: list[str]) -> dict | None:
    if not analysts.get("n") and not analysts.get("target"):
        return None
    def build():
        out, _ = _llm(
            f"Summarise the sell-side view on {name} from this consensus data and these recent headlines. English and "
            "Simplified Chinese. 'view': 2 sentences on where analysts stand and what the debate is about. 'bull' and "
            "'bear': up to 3 short points each, the arguments behind each side. No buy/sell advice, no new numbers. Return "
            '{"view_en": "", "view_zh": "", "bull_en": [], "bull_zh": [], "bear_en": [], "bear_zh": []}\n\n'
            + json.dumps({"consensus": {k: analysts.get(k) for k in ("n", "buckets", "target", "changes", "eps")},
                          "headlines": headlines[:15]}, ensure_ascii=False, default=str),
            fast=True, max_tokens=1500)
        return {"view": {"en": out.get("view_en", ""), "zh": out.get("view_zh", "")},
                "bull": {"en": out.get("bull_en") or [], "zh": out.get("bull_zh") or []},
                "bear": {"en": out.get("bear_en") or [], "zh": out.get("bear_zh") or []}}
    return _cached(f"analyst_view:{sec_id}", 86400, build)


def journey_events(sec_id: str, name: str, events: list[dict], stats: dict) -> dict | None:
    """Titles and short reads for computed episodes, plus the multi-paragraph trend story."""
    def build():
        out, _ = _llm(
            f"These are computed episodes in {name}'s share-price history (dates and moves are exact). For each, give a "
            "short title naming the widely known company or market event behind it, and one or two sentences of "
            "explanation, in English and Simplified Chinese. If you do not know the cause, say what the price did "
            "without inventing a reason. Also write the overall story of the stock's trend in 2-3 short paragraphs. "
            "Do not add numbers beyond those given. Return "
            '{"events": [{"i": 0, "title_en": "", "title_zh": "", "read_en": "", "read_zh": ""}], '
            '"story_en": ["para"], "story_zh": ["段落"]}\n\n'
            + json.dumps({"stats": stats, "events": [{"i": i, **e} for i, e in enumerate(events)]},
                         ensure_ascii=False, default=str),
            max_tokens=4000)
        by_i = {e.get("i"): e for e in out.get("events") or [] if isinstance(e, dict)}
        return {"events": {str(i): {"title": {"en": e.get("title_en", ""), "zh": e.get("title_zh", "")},
                                    "read": {"en": e.get("read_en", ""), "zh": e.get("read_zh", "")}}
                           for i, e in by_i.items()},
                "story": {"en": out.get("story_en") or [], "zh": out.get("story_zh") or []}}
    key = f"journey_read:{sec_id}:{len(events)}:{events[-1]['date'] if events else ''}"
    return _cached(key, 14 * 86400, build)
