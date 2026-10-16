# Lantern

Personal research workbench for US, China A-share and Hong Kong markets: live wire, Need to know,
AI reads, index and company views, industry research, post-market reports. Every value on screen
comes from a live source and names it; when no source answers, the UI shows an empty state.

**Personal use only.** Most market data comes from site front-end APIs (Tencent, Sina, Eastmoney,
Yahoo, THS, CLS) via Vibe-Research's data layer. Those are licensed for private research, not
redistribution, so billing and accounts are deliberately absent.

## Run

```sh
cp .env.example .env    # then fill in keys (see below)
./run.sh                # builds the frontend, serves everything on http://localhost:8910
./run.sh dev            # backend :8910 + Vite dev server with hot reload on http://localhost:5899
```

If your shell exports `HTTP_PROXY`, open the app in a browser that bypasses the proxy for localhost
(`curl --noproxy '*'` for API calls).

## Keys (`.env`)

| Key | Used for | Without it |
| --- | --- | --- |
| `GLM_API_KEY` (+ `GLM_BASE_URL`, `GLM_MODEL`) | Impact scores, translations, AI reads, post-market analysis, industry packs, macro calendar, peers | Raw wire only; AI panels say AI is off |
| `GLM_DEEP_EFFORT` (`low` default, `high`, `max`) | Reasoning effort for deep reads; `low` ≈ 20 s per read, default effort took ~4 min | — |
| `GLM_SEARCH_ENGINE` (`search_pro_quark` default) | Zhipu web-search engine for calendars, industry packs, peers | — |
| `FINNHUB_KEY` | US market news, company news, profiles, peers, fallbacks | Those fallbacks are skipped |
| `TUSHARE_TOKEN` | Trading calendars (holidays), CN fundamentals and holders fallbacks | Sessions assume weekdays (flagged "unverified") |
| `SEC_CONTACT` (`Name email`) | SEC EDGAR 8-K filing stream (SEC requires a declared User-Agent) | EDGAR poller stays off |

## Layout

- `backend/` FastAPI app. `app/sources/router.py` tries providers in order (Vibe-Research first,
  then Finnhub, Tushare, GLM web search) with a validation gate and circuit breakers.
  `app/pipeline/` ingests wires into SQLite, dedupes and clusters stories; `app/enrich/` runs GLM;
  `app/scheduler.py` holds the pollers. `app/vendor/` is Vibe-Research's data layer (MIT).
  Regenerate `askill.py` / `gskill.py` from the two `SKILL.md` files rather than editing them.
- `frontend/` React 19 + Vite + Tailwind. `npm run i18n` rebuilds `zh.json` from the prototype's
  dictionary plus `zh.extra.json`.
- Tests: `cd backend && .venv/bin/python -m pytest -q tests`

System design and architecture diagrams: the "Lantern — System Design" doc (Implementation architecture tab).
