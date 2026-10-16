"""Company view data: profile, annual financials (+ DuPont, quality checks), analysts,
holders, peers, journey since listing. Each block names its source; blocks a source
cannot fill come back empty, never guessed."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

import app.vendor  # noqa: F401
import askill
import gskill

from app.config import settings
from app.services import marketdata
from app.services import securities as S
from app.services.securities import Sec
from app.sources import finnhub_src, tushare_src
from app.sources.router import Provider, TIER_AI, TIER_KEYED, TIER_PERSONAL, route
from app.store import db

UA = {"User-Agent": "Mozilla/5.0"}


def _em_secucode(sec: Sec) -> str:
    if sec.mkt == "HK":
        return f"{sec.code}.HK"
    if not sec.us_suffix:
        marketdata.quotes([sec.id])
        sec = S.get(sec.id)
    return f"{sec.code}.{'O' if sec.us_suffix in ('OQ', '') else 'N' if sec.us_suffix == 'N' else 'A'}"


def _f(v) -> float | None:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


# --- profile ------------------------------------------------------------------

def _profile_yahoo(sec: Sec) -> dict:
    p = (gskill.yahoo_quote_summary(sec.yahoo, ["assetProfile"]) or {}).get("assetProfile") or {}
    if not p.get("longBusinessSummary"):
        return {}
    ceo = next((o.get("name") for o in p.get("companyOfficers") or [] if "CEO" in (o.get("title") or "").upper()
                or "CHIEF EXECUTIVE" in (o.get("title") or "").upper()), None)
    return {"desc": p.get("longBusinessSummary"), "descLang": "en", "sector": p.get("sectorDisp") or p.get("sector"),
            "industry": p.get("industryDisp") or p.get("industry"),
            "hq": ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x),
            "staff": p.get("fullTimeEmployees"), "ceo": ceo, "website": p.get("website")}


def _profile_finnhub(sec: Sec) -> dict:
    if sec.mkt != "US":
        return {}
    p = finnhub_src.profile(sec.code)
    if not p:
        return {}
    ex = p.get("exchange") or ""
    ex = "NASDAQ" if "NASDAQ" in ex.upper() else "NYSE" if "NEW YORK" in ex.upper() or "NYSE" in ex.upper() else ex
    return {"name": p.get("name"), "industry": p.get("finnhubIndustry"), "hq": p.get("country"),
            "ipo": p.get("ipo"), "website": p.get("weburl"), "exchange": ex}


def _profile_sina_cn(sec: Sec) -> dict:
    if sec.mkt != "CN":
        return {}
    t = requests.get(f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpInfo/stockid/{sec.code}.phtml",
                     headers=UA, timeout=10).content.decode("gbk", "ignore")
    i = t.find('id="comInfo1"')
    if i < 0:
        return {}
    cells = [re.sub(r"<[^>]+>|&nbsp;|\s+", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", t[i:i + 12000], re.S)]
    kv = {cells[j].rstrip("：:"): cells[j + 1] for j in range(len(cells) - 1) if cells[j].endswith(("：", ":"))}
    if not kv.get("公司名称"):
        return {}
    if kv.get("公司英文名称"):
        S.remember(sec.id, name=kv["公司英文名称"])
    return {"desc": kv.get("公司简介"), "descLang": "zh", "business": kv.get("主营业务"), "hq": kv.get("办公地址"),
            "founded": kv.get("成立日期"), "ipo": kv.get("上市日期"), "ipoPrice": _f(kv.get("发行价格")),
            "website": kv.get("公司网址"), "exchange": kv.get("上市市场"), "legalName": kv.get("公司名称"),
            "nameEn": kv.get("公司英文名称")}


def _profile_tushare_cn(sec: Sec) -> dict:
    if sec.mkt != "CN":
        return {}
    rows = tushare_src.call("stock_company", ts_code=tushare_src.ts_code("CN", sec.code))
    if not rows:
        return {}
    r = rows[0]
    return {"desc": r.get("introduction"), "descLang": "zh", "business": r.get("main_business"),
            "hq": ", ".join(x for x in (r.get("province"), r.get("city")) if x), "staff": r.get("employees"),
            "ceo": r.get("manager"), "founded": r.get("setup_date"), "website": r.get("website")}


def profile(sec_id: str) -> dict:
    sec = S.get(sec_id)
    chain = ([Provider("sina.corpinfo", _profile_sina_cn), Provider("tushare.stock_company", _profile_tushare_cn, TIER_KEYED)]
             if sec.mkt == "CN" else [Provider("yahoo.profile", _profile_yahoo)])
    res = route(chain, sec, cache_key=f"profile:{sec_id}", ttl=7 * 86400, persist=True)
    out = dict(res.data or {})
    if sec.mkt == "US":  # Finnhub adds the IPO date Yahoo lacks
        extra = route([Provider("finnhub.profile", _profile_finnhub, TIER_KEYED)], sec,
                      cache_key=f"fprofile:{sec_id}", ttl=7 * 86400, persist=True)
        for k, v in (extra.data or {}).items():
            out.setdefault(k, v)
    out["descI18n"] = _translate_desc(sec_id, out.get("desc"), out.get("descLang")) if out.get("desc") else None
    return {**S.get(sec_id).to_api(), "profile": out, **res.meta()}


def _translate_desc(sec_id: str, text: str, lang: str | None) -> dict:
    """Company description in both languages; translation by GLM, cached, when a key is set."""
    base = {"en": text if lang == "en" else "", "zh": text if lang == "zh" else ""}
    if not settings.llm_enabled:
        return base
    key = f"desc_i18n:{sec_id}"
    hit = db.kv_get(key)
    if hit:
        return hit[0]
    from app.enrich import llm
    from app.enrich.prompts import FRAME
    try:
        out, _, _ = llm.chat_json(FRAME, "Translate this company description faithfully and summarise it to at most 3 "
                                  "sentences in each language. Return {\"en\": \"...\", \"zh\": \"...\"}.\n\n" + text[:3000],
                                  fast=True, max_tokens=1500)
        val = {"en": out.get("en") or base["en"], "zh": out.get("zh") or base["zh"]}
        db.kv_set(key, val, "glm", 90 * 86400)
        return val
    except Exception:
        return base


# --- financials -----------------------------------------------------------------

def _annual_em(sec: Sec) -> list[dict]:
    if sec.mkt == "CN":
        return []
    code = _em_secucode(sec)
    ind = [r for r in gskill.key_indicators_eastmoney(code, 40) if (r.get("DATE_TYPE") or "") == "年报"]
    if not ind:
        return []
    cf = gskill.financial_statements_eastmoney(code, "cashflow", page_size=1200)
    bal = gskill.financial_statements_eastmoney(code, "balance", page_size=1200)

    def items(rows: list[dict], date: str) -> dict:
        return {r["ITEM_NAME"]: r.get("AMOUNT") for r in rows
                if (r.get("REPORT_DATE") or "")[:10] == date and "年报" in (r.get("REPORT_TYPE") or "")}

    out = []
    for r in ind[:5]:
        d = (r.get("REPORT_DATE") or "")[:10]
        c, b = items(cf, d), items(bal, d)
        ocf = _f(c.get("经营活动产生的现金流量净额") or c.get("经营业务现金净额"))
        capex = _f(c.get("购买固定资产") or c.get("购建固定资产") or c.get("购买物业、厂房及设备") or c.get("购建物业、厂房及设备"))
        assets = _f(b.get("总资产"))
        equity = _f(b.get("归属于母公司股东权益") or b.get("股东权益") or b.get("股东权益合计"))
        out.append({"period": d, "year": d[:4], "currency": r.get("CURRENCY_ABBR"),
                    "revenue": _f(r.get("OPERATE_INCOME")), "revenueYoy": _f(r.get("OPERATE_INCOME_YOY")),
                    "grossProfit": _f(r.get("GROSS_PROFIT")),
                    "netIncome": _f(r.get("PARENT_HOLDER_NETPROFIT") or r.get("HOLDER_PROFIT")),
                    "grossMargin": _f(r.get("GROSS_PROFIT_RATIO")), "netMargin": _f(r.get("NET_PROFIT_RATIO")),
                    "roe": _f(r.get("ROE_AVG")), "roa": _f(r.get("ROA")), "debtRatio": _f(r.get("DEBT_ASSET_RATIO")),
                    "ocf": ocf, "capex": abs(capex) if capex else None, "totalAssets": assets, "equity": equity,
                    "eps": _f(r.get("BASIC_EPS"))})
    return out


def _annual_sina(sec: Sec) -> list[dict]:
    if sec.mkt != "CN":
        return []
    lrb, fzb, llb = (askill.sina_financial_report(sec.code, t) for t in ("lrb", "fzb", "llb"))
    by = lambda rows: {r["报告期"]: r for r in rows if str(r.get("报告期", "")).endswith("12-31")}  # noqa: E731
    L, F, C = by(lrb), by(fzb), by(llb)
    out = []
    for d in sorted(L, reverse=True)[:5]:
        i, b, c = L[d], F.get(d, {}), C.get(d, {})
        rev = _f(i.get("营业总收入") or i.get("营业收入"))
        cost = _f(i.get("营业成本"))
        ni = _f(i.get("归属于母公司所有者的净利润") or i.get("净利润"))
        assets = _f(b.get("资产总计"))
        equity = _f(b.get("归属于母公司股东权益合计") or b.get("所有者权益合计"))
        ocf = _f(c.get("经营活动产生的现金流量净额"))
        capex = _f(c.get("购建固定资产、无形资产和其他长期资产所支付的现金"))
        out.append({"period": d, "year": d[:4], "currency": "CNY", "revenue": rev,
                    "revenueYoy": (_f(i.get("营业总收入_同比")) or 0) * 100 if i.get("营业总收入_同比") is not None else None,
                    "grossProfit": rev - cost if rev and cost else None, "netIncome": ni,
                    "grossMargin": (rev - cost) / rev * 100 if rev and cost else None,
                    "netMargin": ni / rev * 100 if ni and rev else None,
                    "roe": ni / equity * 100 if ni and equity else None, "roa": ni / assets * 100 if ni and assets else None,
                    "debtRatio": (1 - equity / assets) * 100 if equity and assets else None,
                    "ocf": ocf, "capex": capex, "totalAssets": assets, "equity": equity,
                    "eps": _f(i.get("基本每股收益"))})
    return out


def _annual_tushare(sec: Sec) -> list[dict]:
    if sec.mkt != "CN":
        return []
    rows = tushare_src.call("fina_indicator", ts_code=tushare_src.ts_code("CN", sec.code))
    rows = [r for r in rows if str(r.get("end_date", "")).endswith("1231")][:5]
    return [{"period": f"{r['end_date'][:4]}-12-31", "year": r["end_date"][:4], "currency": "CNY",
             "revenue": None, "revenueYoy": _f(r.get("or_yoy")), "grossProfit": None, "netIncome": None,
             "grossMargin": _f(r.get("grossprofit_margin")), "netMargin": _f(r.get("netprofit_margin")),
             "roe": _f(r.get("roe")), "roa": _f(r.get("roa")), "debtRatio": _f(r.get("debt_to_assets")),
             "ocf": None, "capex": None, "totalAssets": None, "equity": None, "eps": _f(r.get("eps"))} for r in rows]


def _dupont(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        ni, rev, a, e = r.get("netIncome"), r.get("revenue"), r.get("totalAssets"), r.get("equity")
        if not all((ni, rev, a, e)):
            continue
        out.append({"year": r["year"], "netMargin": ni / rev * 100, "assetTurnover": rev / a,
                    "equityMultiplier": a / e, "roe": ni / e * 100})
    return out


def _checks(rows: list[dict]) -> list[dict]:
    """Rule-based quality checks on the latest fiscal year (thresholds are stated in each note)."""
    if not rows:
        return []
    r, prev = rows[0], rows[1] if len(rows) > 1 else {}
    out = []

    def add(key: str, ok: bool | None, note: str) -> None:
        if ok is not None:
            out.append({"k": key, "status": "pass" if ok else "watch", "note": note})

    if r.get("ocf") and r.get("netIncome"):
        add("Cash conversion", r["ocf"] >= r["netIncome"], f"Operating cash flow / net income = {r['ocf'] / r['netIncome']:.2f} (pass at ≥ 1.0)")
    if r.get("ocf") is not None and r.get("capex") is not None:
        fcf = r["ocf"] - r["capex"]
        add("Free cash flow", fcf > 0, "Positive free cash flow" if fcf > 0 else "Capex exceeded operating cash flow")
    if r.get("debtRatio") is not None:
        add("Leverage", r["debtRatio"] < 60, f"Liabilities / assets = {r['debtRatio']:.0f}% (pass below 60%)")
    if r.get("revenueYoy") is not None:
        add("Growth", r["revenueYoy"] > 0, f"Revenue {r['revenueYoy']:+.1f}% year on year")
    if r.get("grossMargin") is not None and prev.get("grossMargin") is not None:
        add("Margin trend", r["grossMargin"] >= prev["grossMargin"] - 1,
            f"Gross margin {prev['grossMargin']:.1f}% → {r['grossMargin']:.1f}% (pass if down < 1 pt)")
    return out


def financials(sec_id: str) -> dict:
    sec = S.get(sec_id)
    chain = ([Provider("sina.statements", _annual_sina), Provider("tushare.fina_indicator", _annual_tushare, TIER_KEYED)]
             if sec.mkt == "CN" else [Provider("eastmoney.datacenter", _annual_em, TIER_PERSONAL, 20)])
    res = route(chain, sec, cache_key=f"fin:{sec_id}", ttl=86400, persist=True)
    rows = res.data or []
    dp, ck = _dupont(rows), _checks(rows)
    from app.services import reads
    return {"id": sec_id, "annual": rows, "dupont": dp, "checks": ck, "read": reads.financial_read(sec_id, rows, dp, ck),
            **res.meta()}


# --- analysts ---------------------------------------------------------------------

def _analysts_yahoo(sec: Sec) -> dict:
    a = gskill.analyst_estimates(sec.yahoo) or {}
    k = gskill.key_statistics(sec.yahoo) or {}
    rt = (a.get("rating_trend") or [{}])[0]
    buckets = [{"k": "Strong buy", "n": rt.get("strong_buy", 0)}, {"k": "Buy", "n": rt.get("buy", 0)},
               {"k": "Hold", "n": rt.get("hold", 0)}, {"k": "Sell", "n": rt.get("sell", 0)},
               {"k": "Strong sell", "n": rt.get("strong_sell", 0)}]
    n = sum(b["n"] for b in buckets)
    if not n and not k.get("target_mean"):
        return {}
    changes = [{"date": datetime.fromtimestamp(u["date"], timezone.utc).date().isoformat(), "firm": u.get("firm"),
                "action": u.get("action"), "from": u.get("from_grade"), "to": u.get("to_grade")}
               for u in (a.get("upgrade_downgrade") or [])[:8] if u.get("date")]
    return {"n": n, "buckets": buckets, "recommendation": k.get("recommendation"),
            "target": {"lo": k.get("target_low"), "avg": k.get("target_mean"), "hi": k.get("target_high")},
            "eps": [{"period": e.get("period"), "end": e.get("end_date"), "avg": e.get("eps_estimate"),
                     "lo": e.get("eps_low"), "hi": e.get("eps_high"), "n": e.get("num_analysts")} for e in a.get("eps_trend") or []],
            "changes": changes,
            "valuation": {"forwardPe": k.get("forward_pe"), "trailingPe": k.get("trailing_pe"), "pb": k.get("price_to_book"),
                          "evEbitda": k.get("ev_to_ebitda"), "evRevenue": k.get("ev_to_revenue"), "peg": k.get("peg_ratio"),
                          "dividendYield": k.get("dividend_yield"), "beta": k.get("beta")}}


_CN_RATING = {"买入": "Buy", "增持": "Buy", "强烈推荐": "Strong buy", "推荐": "Buy", "持有": "Hold", "中性": "Hold",
              "减持": "Sell", "卖出": "Sell"}


def _analysts_cn(sec: Sec) -> dict:
    reps = askill.eastmoney_reports(sec.code)
    fc = askill.ths_eps_forecast(sec.code)
    if not reps and (fc is None or fc.empty):
        return {}
    recent = [r for r in reps if (r.get("publishDate") or "") >= (datetime.now().replace(year=datetime.now().year - 1)).strftime("%Y-%m-%d")]
    counts: dict[str, int] = {}
    for r in recent:
        k = _CN_RATING.get(r.get("emRatingName") or "", None)
        if k:
            counts[k] = counts.get(k, 0) + 1
    buckets = [{"k": k, "n": counts.get(k, 0)} for k in ("Strong buy", "Buy", "Hold", "Sell", "Strong sell")]
    eps = []
    if fc is not None and not fc.empty:
        for _, row in fc.iterrows():
            eps.append({"period": str(row.get("年度")), "avg": _f(row.get("均值")), "lo": _f(row.get("最小值")),
                        "hi": _f(row.get("最大值")), "n": int(row.get("预测机构数") or 0)})
    targets = [t for t in (_f(r.get("indvAimPriceT")) for r in recent) if t]
    changes = [{"date": (r.get("publishDate") or "")[:10], "firm": r.get("orgSName"), "action": r.get("emRatingName"),
                "title": r.get("title"), "url": askill.PDF_TPL.format(info_code=r["infoCode"]) if r.get("infoCode") else None}
               for r in reps[:8]]
    return {"n": sum(counts.values()), "buckets": buckets, "recommendation": None,
            "target": {"lo": min(targets), "avg": sum(targets) / len(targets), "hi": max(targets)} if targets else None,
            "eps": eps, "changes": changes, "valuation": None}


def analysts(sec_id: str) -> dict:
    sec = S.get(sec_id)
    chain = [Provider("eastmoney.reports+ths", _analysts_cn, TIER_PERSONAL, 20)] if sec.mkt == "CN" \
        else [Provider("yahoo.analysts", _analysts_yahoo, TIER_PERSONAL, 15)]
    res = route(chain, sec, cache_key=f"analysts:{sec_id}", ttl=6 * 3600, persist=True)
    return {"id": sec_id, **(res.data or {}), **res.meta()}


# --- holders ------------------------------------------------------------------------

def _holders_yahoo(sec: Sec) -> dict:
    h = gskill.institutional_holders(sec.yahoo) or {}
    if not h.get("overview") and not h.get("top_holders"):
        return {}
    ov = h.get("overview") or {}
    return {"overview": {"institutionsPct": ov.get("institutions_pct"), "insidersPct": ov.get("insiders_pct"),
                         "institutionsCount": ov.get("institutions_count")},
            "top": [{"name": t.get("name"), "shares": t.get("shares"), "pct": t.get("pct_held"), "date": t.get("report_date")}
                    for t in h.get("top_holders") or []][:10]}


def _holders_cn(sec: Sec) -> dict:
    out: dict = {}
    hn = askill.holder_num_change(sec.code)
    if hn:
        out["holderCount"] = [{"date": r.get("date"), "n": r.get("holder_num"), "chgPct": r.get("change_ratio")} for r in hn[:6]]
    if settings.tushare_token:
        try:
            rows = tushare_src.call("top10_holders", ts_code=tushare_src.ts_code("CN", sec.code))
            if rows:
                last = max(r["end_date"] for r in rows)
                out["top"] = [{"name": r["holder_name"], "shares": r.get("hold_amount"), "pct": (r.get("hold_ratio") or 0) / 100,
                               "date": last} for r in rows if r["end_date"] == last][:10]
        except Exception:
            pass
    try:
        mt = askill.margin_trading(sec.code)
        if mt:
            out["margin"] = mt[:10]
    except Exception:
        pass
    return out


def holders(sec_id: str) -> dict:
    sec = S.get(sec_id)
    chain = [Provider("eastmoney.holders", _holders_cn, TIER_PERSONAL, 20)] if sec.mkt == "CN" \
        else [Provider("yahoo.holders", _holders_yahoo, TIER_PERSONAL, 15)]
    res = route(chain, sec, cache_key=f"holders:{sec_id}", ttl=12 * 3600, persist=True)
    return {"id": sec_id, **(res.data or {}), **res.meta()}


# --- peers --------------------------------------------------------------------------

def _peers_finnhub(sec: Sec) -> list[str]:
    if sec.mkt != "US":
        return []
    return [f"US:{p}" for p in finnhub_src.peers(sec.code) if p and p != sec.code][:8]


def _peers_glm(sec: Sec) -> list[str]:
    """Cross-market peers named by GLM with web search, validated against live quotes."""
    if not settings.llm_enabled:
        return []
    from app.enrich import llm
    from app.enrich.prompts import FRAME
    q = (f"List up to 8 listed peer companies of {sec.name or sec.name_zh} ({sec.ticker}, {sec.mkt}) across the US, "
         "China A-share and Hong Kong markets that compete in the same main business. Return "
         '{"peers": [{"symbol": "...", "market": "US"|"CN"|"HK", "name": "..."}]} using exchange codes '
         "(US ticker, 6-digit A-share code, 5-digit HK code).")
    out, _, _ = llm.chat_json(FRAME, q, web_search=True, max_tokens=1500, recency="oneYear",
                              search_query=f"{sec.name or sec.name_zh} competitors peers listed companies")
    from app.enrich.worker import _sec_id, name_matches
    named = [(i, p.get("name") or "") for p in out.get("peers") or [] if (i := _sec_id(p)) and i != sec.id]
    live = marketdata.quotes([i for i, _ in named])
    return [i for i, nm in named if i in live and name_matches(nm, live[i])]   # drop wrong or dead tickers


def peers(sec_id: str) -> dict:
    sec = S.get(sec_id)
    res = route([Provider("glm.peers", _peers_glm, TIER_AI, 90), Provider("finnhub.peers", _peers_finnhub, TIER_KEYED)],
                sec, cache_key=f"peers:{sec_id}", ttl=30 * 86400, persist=True)
    ids = res.data or []
    qs = marketdata.quotes(ids) if ids else {}
    return {"id": sec_id, "peers": [qs[i] for i in ids if i in qs], **res.meta()}


# --- journey since listing ------------------------------------------------------------

def journey(sec_id: str) -> dict:
    b = marketdata.bars(sec_id, "MAX")
    rows = b["bars"]
    if len(rows) < 3:
        return {"id": sec_id, "bars": rows, "stats": None, "episodes": [], "story": None, **{k: b[k] for k in ("source", "tier", "fetchedAt")}}
    first, last = rows[0], rows[-1]
    peak, peak_t, episodes = rows[0]["c"], rows[0]["t"], []
    trough, trough_t = peak, peak_t
    # drawdowns of 40% or more from a running peak, and the recovery high after them
    for r in rows:
        if r["c"] > peak:
            if trough / peak - 1 <= -0.4:
                episodes.append({"kind": "drawdown", "from": peak_t, "to": trough_t, "pct": round((trough / peak - 1) * 100, 1)})
            peak, peak_t, trough, trough_t = r["c"], r["t"], r["c"], r["t"]
        elif r["c"] < trough:
            trough, trough_t = r["c"], r["t"]
    if trough / peak - 1 <= -0.4:
        episodes.append({"kind": "drawdown", "from": peak_t, "to": trough_t, "pct": round((trough / peak - 1) * 100, 1),
                         "unrecovered": True})
    moves = sorted(({"t": cur["t"], "pct": round((cur["c"] / prev["c"] - 1) * 100, 1)} for prev, cur in zip(rows, rows[1:]) if prev["c"]),
                   key=lambda m: -abs(m["pct"]))[:6]
    years = max(1e-9, (datetime.fromisoformat(last["t"]) - datetime.fromisoformat(first["t"])).days / 365.25)
    stats = {"since": first["t"], "firstClose": first["c"], "lastClose": last["c"],
             "multiple": round(last["c"] / first["c"], 1) if first["c"] > 0 else None,
             "totalPct": round((last["c"] / first["c"] - 1) * 100, 1) if first["c"] else None,
             "cagrPct": round(((last["c"] / first["c"]) ** (1 / years) - 1) * 100, 1) if first["c"] > 0 else None,
             "years": round(years, 1),
             "worstDrawdown": min((e["pct"] for e in episodes), default=None),
             "worstDrawdownAt": min(episodes, key=lambda e: e["pct"])["to"] if episodes else None,
             "adjusted": "backward-adjusted (hfq)" if b["source"] == "tencent.kline" else "split-adjusted",
             "note": "History starts at the first bar the source holds, which can be later than the IPO."}
    # Major events = first bar + the largest episodes (>=40% drawdowns at their trough, >=15% one-month moves),
    # ranked by size, at most one per calendar year so they spread across the whole history
    cands = [{"kind": "drawdown", "date": e["to"], "from": e["from"], "pct": e["pct"],
              "move": f"{e['pct']:+.0f}% from peak"} for e in episodes]
    cands += [{"kind": "move", "date": m["t"], "pct": m["pct"], "move": f"{m['pct']:+.0f}% in a month"}
              for m in sorted(({"t": cur["t"], "pct": round((cur["c"] / prev["c"] - 1) * 100, 1)}
                               for prev, cur in zip(rows, rows[1:]) if prev["c"]), key=lambda m: -abs(m["pct"]))[:60]
              if abs(m["pct"]) >= 15]
    years_used = {first["t"][:4]}
    ev = [{"kind": "listing", "date": first["t"], "move": "first bar"}]
    for c in sorted(cands, key=lambda c: (c["kind"] != "drawdown", -abs(c["pct"]))):
        if c["date"][:4] not in years_used and len(ev) < 12:
            ev.append(c)
            years_used.add(c["date"][:4])
    ev = sorted(ev, key=lambda e: e["date"])
    from app.services import reads
    sec = S.get(sec_id)
    rd = reads.journey_events(sec_id, sec.name or sec.name_zh, ev, stats) or {}
    for i, e in enumerate(ev):
        e["label"] = f"J{i + 1}"
        info = (rd.get("events") or {}).get(str(i)) or {}
        e["title"] = info.get("title")
        e["read"] = info.get("read")
    return {"id": sec_id, "bars": rows, "stats": stats, "episodes": episodes, "events": ev, "story": rd.get("story"),
            **{k: b[k] for k in ("source", "tier", "fetchedAt")}}


def views(sec_id: str) -> dict:
    """Analyst consensus + the AI agent view with bull/bear arguments."""
    from app.services import reads
    a = analysts(sec_id)
    sec = S.get(sec_id)
    heads = [r["title"] for r in db.query("SELECT title FROM events WHERE symbols LIKE ? ORDER BY published_at DESC LIMIT 15",
                                          (f'%"{sec_id}"%',))]
    return {**a, "agent": reads.analyst_view(sec_id, sec.name or sec.name_zh, a, heads)}
