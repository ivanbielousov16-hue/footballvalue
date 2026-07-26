"""Маршрути конструктора експресів."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..accumulator.builder import AccumulatorBuilder, AccaLeg
from ..database.db import get_db
from ..schemas.models import AccaBuildIn
from ..services.analysis_service import AnalysisService
from ..services.match_service import MatchService
from ..services.registry import get_registry, ProviderRegistry

router = APIRouter()

MAX_MATCHES = 40


def _gather_legs(payload: AccaBuildIn, db: Session, registry: ProviderRegistry,
                 include_all: bool = False) -> list[AccaLeg]:
    if payload.match_ids:
        matches = [registry.sports.get_match(mid) for mid in payload.match_ids]
        matches = [m for m in matches if m is not None]
    else:
        matches = MatchService(registry).list_matches(date_filter=payload.date_filter, db=db)
    matches = matches[:MAX_MATCHES]

    asvc = AnalysisService(registry)
    legs: list[AccaLeg] = []
    for m in matches:
        try:
            a = asvc.analyze(m, db)
        except Exception:
            continue  # пропускаємо матч, якщо API дав збій — не валимо весь експрес
        if a.skip_recommended and not include_all:
            continue
        for p in a.predictions:
            if p.decimal_odds is None:
                continue
            legs.append(AccaLeg(
                match_id=m.id,
                match_label=f"{m.home.name} — {m.away.name}",
                league=m.league,
                market=p.market, selection=p.selection,
                decimal_odds=p.decimal_odds, model_probability=p.model_probability,
                confidence=p.confidence, ev=p.ev, risk=p.risk,
                reason=(p.args_for[0] if p.args_for else f"модель {round(p.model_probability * 100)}%"),
            ))
    return legs


@router.post("/accumulator/build")
def build_accumulator(payload: AccaBuildIn, db: Session = Depends(get_db),
                      registry: ProviderRegistry = Depends(get_registry)) -> dict:
    # З вибраних матчів (або явний lenient) — складаємо завжди, м'якший режим.
    lenient = payload.lenient or bool(payload.match_ids)
    legs = _gather_legs(payload, db, registry, include_all=lenient)
    builder = AccumulatorBuilder()
    result = builder.build(
        legs, mode=payload.mode, count=payload.count, target_odds=payload.target_odds,
        min_confidence=payload.min_confidence, min_ev=payload.min_ev,
        allowed_markets=payload.allowed_markets, excluded_leagues=payload.excluded_leagues,
        lenient=lenient,
    )
    if lenient and result.get("legs"):
        result["note_lenient"] = "Зібрано з обраних матчів (без фільтра по value)."
    return result


@router.post("/accumulator/recommended")
def recommended_accumulators(payload: AccaBuildIn, db: Session = Depends(get_db),
                             registry: ProviderRegistry = Depends(get_registry)) -> dict:
    legs = _gather_legs(payload, db, registry)
    builder = AccumulatorBuilder()
    return {
        "careful": builder.build(legs, mode="careful"),
        "balanced": builder.build(legs, mode="balanced"),
        "risky": builder.build(legs, mode="risky"),
    }
