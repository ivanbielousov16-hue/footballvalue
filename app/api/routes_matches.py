"""Маршрути матчів: список, фільтри, пошук, деталі, вибране."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..schemas.models import MatchOut, match_to_out
from ..services.registry import get_registry, ProviderRegistry
from ..services.match_service import MatchService

router = APIRouter()


def _svc() -> MatchService:
    return MatchService(get_registry())


@router.get("/matches", response_model=list[MatchOut])
def list_matches(
    date_filter: str = Query("today", description="today|tomorrow|next3|next7|live|soon|all"),
    status: Optional[str] = None,
    league: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    popular_only: bool = False,
    min_odds: Optional[float] = None,
    max_odds: Optional[float] = None,
    with_odds: bool = False,
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> list[MatchOut]:
    svc = MatchService(registry)
    matches = svc.list_matches(
        date_filter=date_filter, status=status, league=league, country=country,
        search=search, popular_only=popular_only,
        min_odds=min_odds, max_odds=max_odds, db=db,
    )
    out = []
    for m in matches:
        odds = registry.get_odds_for_match(m.id, db) if with_odds else []
        out.append(match_to_out(m, odds=odds))
    return out


@router.get("/matches/{match_id}", response_model=MatchOut)
def get_match(
    match_id: int,
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> MatchOut:
    m = registry.sports.get_match(match_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    odds = registry.get_odds_for_match(match_id, db)
    return match_to_out(m, odds=odds)


@router.post("/favorites/{match_id}")
def add_favorite(match_id: int, db: Session = Depends(get_db),
                 registry: ProviderRegistry = Depends(get_registry)) -> dict:
    if registry.sports.get_match(match_id) is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    MatchService(registry).add_favorite(match_id, db)
    return {"status": "added", "match_id": match_id}


@router.delete("/favorites/{match_id}")
def remove_favorite(match_id: int, db: Session = Depends(get_db),
                    registry: ProviderRegistry = Depends(get_registry)) -> dict:
    MatchService(registry).remove_favorite(match_id, db)
    return {"status": "removed", "match_id": match_id}


@router.get("/favorites", response_model=list[MatchOut])
def list_favorites(db: Session = Depends(get_db),
                   registry: ProviderRegistry = Depends(get_registry)) -> list[MatchOut]:
    matches = MatchService(registry).list_favorites(db)
    return [match_to_out(m, odds=registry.get_odds_for_match(m.id, db)) for m in matches]
