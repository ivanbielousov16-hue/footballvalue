"""Метадані: health, ліги, джерела даних, дисклеймер."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services.registry import get_registry, ProviderRegistry
from ..schemas.models import LeagueOut

router = APIRouter()

DISCLAIMER = ""


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/meta/data-source")
def data_source(registry: ProviderRegistry = Depends(get_registry)) -> dict:
    info = registry.data_source_info()
    info["disclaimer"] = DISCLAIMER
    return info


@router.get("/leagues", response_model=list[LeagueOut])
def leagues(registry: ProviderRegistry = Depends(get_registry)) -> list[LeagueOut]:
    return [LeagueOut(**lg) for lg in registry.sports.list_leagues()]


@router.get("/meta/markets")
def markets() -> dict:
    from ..ml.markets import MARKET_LABELS
    return {"markets": MARKET_LABELS}
