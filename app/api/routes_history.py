"""Маршрути історії прогнозів і статистики моделі."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..schemas.models import HistorySaveIn, SettleIn
from ..services.analysis_service import AnalysisService
from ..services.history_service import HistoryService
from ..services.registry import get_registry, ProviderRegistry

router = APIRouter()


def _row_view(r) -> dict:
    return {
        "id": r.id, "match_id": r.match_id, "match_label": r.match_label,
        "league": r.league, "market": r.market, "selection": r.selection,
        "model_probability": r.model_probability, "decimal_odds": r.decimal_odds,
        "ev": r.ev, "confidence": r.confidence, "odds_source": r.odds_source,
        "model_version": r.model_version, "created_at": r.created_at.isoformat(),
        "settled": r.settled, "won": r.won, "profit": r.profit, "stake": r.stake,
    }


@router.post("/history")
def save_prediction(payload: HistorySaveIn, db: Session = Depends(get_db),
                    registry: ProviderRegistry = Depends(get_registry)) -> dict:
    match = registry.sports.get_match(payload.match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    analysis = AnalysisService(registry).analyze(match, db, markets_filter=[payload.market])
    pred = next((p for p in analysis.predictions if p.market == payload.market), None)
    if pred is None:
        raise HTTPException(status_code=400, detail="Невідомий ринок")
    if pred.decimal_odds is None:
        raise HTTPException(status_code=400, detail="Для цього ринку немає коефіцієнта. "
                                                    "Спочатку введіть коефіцієнт.")
    row = HistoryService().save(
        db, match_id=match.id,
        match_label=f"{match.home.name} — {match.away.name}", league=match.league,
        market=pred.market, selection=pred.selection,
        model_probability=pred.model_probability, decimal_odds=pred.decimal_odds,
        ev=pred.ev or 0.0, confidence=pred.confidence,
        odds_source=pred.odds_source or "", stake=payload.stake,
    )
    return _row_view(row)


@router.get("/history")
def list_history(settled: Optional[bool] = None, db: Session = Depends(get_db)) -> list[dict]:
    rows = HistoryService().list(db, settled=settled)
    return [_row_view(r) for r in rows]


@router.post("/history/{history_id}/settle")
def settle(history_id: int, payload: SettleIn, db: Session = Depends(get_db)) -> dict:
    row = HistoryService().settle(db, history_id, payload.won)
    if row is None:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    return _row_view(row)


@router.get("/history/stats")
def history_stats(db: Session = Depends(get_db)) -> dict:
    return HistoryService().stats(db)
