"""GLM-5.3 client (OpenAI-compatible Zhipu endpoint), JSON-only calls, optional web search."""
from __future__ import annotations

import json
import logging
import re
import threading

from openai import OpenAI

from app.config import settings

log = logging.getLogger("lantern.llm")
_client: OpenAI | None = None
_lock = threading.Lock()
REASONING_HEADROOM = 6000    # GLM-5.x always reasons; its thinking tokens count against max_tokens


class LLMDisabled(RuntimeError):
    pass


def client() -> OpenAI:
    global _client
    if not settings.glm_api_key:
        raise LLMDisabled("GLM_API_KEY not set")
    with _lock:
        if _client is None:
            _client = OpenAI(api_key=settings.glm_api_key, base_url=settings.glm_base_url, timeout=120)
    return _client


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("model returned no JSON")
    return json.loads(m.group(1))


def chat_json(system: str, user: str, *, fast: bool = False, web_search: bool = False,
              max_tokens: int = 4000, temperature: float = 0.2,
              recency: str = "oneMonth", search_query: str | None = None) -> tuple[dict, list[dict], str]:
    """Returns (parsed JSON, web sources [{title, url, date}], model id).

    Fast calls ask for low reasoning effort; every call adds headroom for reasoning tokens and
    retries once with a larger budget if the answer was cut off before any content appeared."""
    model = settings.glm_fast_model if fast else settings.glm_model
    kwargs: dict = {
        "model": model, "temperature": temperature,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if web_search:
        # GLM only searches reliably when given an explicit query; with a system prompt it often skips it.
        ws = {"enable": True, "search_result": True, "count": 10, "search_engine": settings.glm_search_engine,
              "search_recency_filter": recency}
        if search_query:
            ws["search_query"] = search_query[:70]
        kwargs["tools"] = [{"type": "web_search", "web_search": ws}]
    else:
        kwargs["response_format"] = {"type": "json_object"}
    kwargs["extra_body"] = {"reasoning_effort": "low" if fast else settings.glm_deep_effort}
    budget = max_tokens + (2000 if fast else REASONING_HEADROOM)
    for attempt in range(2):
        resp = client().chat.completions.create(max_tokens=budget, **kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""
        if content.strip() or choice.finish_reason != "length" or attempt:
            break
        budget *= 2
    sources = []
    for s in (resp.model_extra or {}).get("web_search") or []:
        url = s.get("link") or s.get("url")
        if url:
            sources.append({"title": s.get("title") or s.get("media") or url, "url": url,
                            "date": s.get("publish_date")})
    return _extract_json(content), sources, resp.model or model


_url_cache: dict[str, bool] = {}


def cited(url: str | None, sources: list[dict]) -> bool:
    """A model-cited URL counts only if it was a search hit or it actually resolves (checked once, cached)."""
    if not url or not url.startswith("http"):
        return False
    if any(s["url"] == url for s in sources):
        return True
    if url not in _url_cache:
        import requests
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
            _url_cache[url] = r.status_code < 400
            r.close()
        except Exception:
            _url_cache[url] = False
    return _url_cache[url]
