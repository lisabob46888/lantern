"""Industry view endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import industry

router = APIRouter(prefix="/api/v1/industries")


@router.get("")
def list_industries(market: str = "ALL") -> list[dict]:
    return industry.catalog(market.upper())


@router.get("/{ind}")
def get_industry(ind: str, market: str = "ALL") -> dict:
    try:
        return industry.industry(ind, market.upper())
    except KeyError as e:
        raise HTTPException(404, f"unknown industry {ind}") from e
