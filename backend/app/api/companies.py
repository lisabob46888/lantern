"""Company view endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.pipeline import connectors as C
from app.pipeline.ingest import event_to_api, ingest
from app.services import calendar, company
from app.services import securities as S
from app.store import db

router = APIRouter(prefix="/api/v1/companies")


def _id(sec_id: str) -> str:
    sid = S.normalize(sec_id)
    if not sid or sid.startswith("IX:"):
        raise HTTPException(400, f"not a company id: {sec_id}")
    return sid


@router.get("/{sec_id}/profile")
def get_profile(sec_id: str) -> dict:
    return company.profile(_id(sec_id))


@router.get("/{sec_id}/financials")
def get_financials(sec_id: str) -> dict:
    return company.financials(_id(sec_id))


@router.get("/{sec_id}/analysts")
def get_analysts(sec_id: str) -> dict:
    return company.analysts(_id(sec_id))


@router.get("/{sec_id}/holders")
def get_holders(sec_id: str) -> dict:
    return company.holders(_id(sec_id))


@router.get("/{sec_id}/peers")
def get_peers(sec_id: str) -> dict:
    return company.peers(_id(sec_id))


@router.get("/{sec_id}/views")
def get_views(sec_id: str) -> dict:
    return company.views(_id(sec_id))


@router.get("/{sec_id}/journey")
def get_journey(sec_id: str) -> dict:
    return company.journey(_id(sec_id))


@router.get("/{sec_id}/news")
def get_news(sec_id: str, refresh: bool = True, limit: int = 40) -> dict:
    """Company news and filings: fetched live for this symbol, stored, then read back with AI fields."""
    sid = _id(sec_id)
    if refresh:
        try:
            # per-company history: keep 180 days, and do not push old items onto the live wire
            ingest(C.cninfo([sid]) if sid.startswith("CN:") else C.company_news([sid]), publish=False,
                   max_age_ms=180 * 86400_000)
        except Exception:
            pass
    rows = db.query("SELECT * FROM events WHERE symbols LIKE ? AND enrich_state != 'skipped' "
                    "ORDER BY published_at DESC LIMIT ?", (f'%"{sid}"%', limit))
    return {"id": sid, "items": [event_to_api(r) for r in rows], "catalysts": calendar.for_symbol(sid)}
