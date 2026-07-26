"""Маршрути live-аналізу."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..models.domain import MatchStatus
from ..live.live_service import LiveService
from ..schemas.models import MatchOut, match_to_out
from ..services.registry import get_registry, ProviderRegistry

router = APIRouter()


@router.get("/live", response_model=list[MatchOut])
def live_matches(db: Session = Depends(get_db),
                 registry: ProviderRegistry = Depends(get_registry)) -> list[MatchOut]:
    from ..services.match_service import MatchService
    matches = MatchService(registry).list_matches(date_filter="live", db=db)
    return [match_to_out(m, odds=registry.get_odds_for_match(m.id, db)) for m in matches]


@router.get("/live/{match_id}")
def live_state(match_id: int, db: Session = Depends(get_db),
               registry: ProviderRegistry = Depends(get_registry)) -> dict:
    m = registry.sports.get_match(match_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    return LiveService(registry).live_state(m)
