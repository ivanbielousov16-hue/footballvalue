"""Маршрути аналізу: аналіз одного матчу та «Проаналізувати всі матчі»."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..accumulator.builder import AccumulatorBuilder, AccaLeg
from ..database.db import get_db
from ..models.domain import MatchAnalysis, MatchStatus
from ..schemas.models import MatchAnalysisOut, analysis_to_out
from ..services.analysis_service import AnalysisService
from ..services.match_service import MatchService
from ..services.narrative import NarrativeService
from ..services.insights import kelly_fraction, detect_traps, value_score
from ..services.registry import get_registry, ProviderRegistry

router = APIRouter()

# Обмежуємо кількість матчів для «Проаналізувати всі» / «ТОП дня»:
# на реальному API кожен матч — це кілька запитів, тож тримаємось у межах
# добового ліміту й робимо аналіз швидким. Пріоритет — популярні та найближчі.
MAX_MATCHES_ANALYZE = 12
TAB_LIMIT = 25


def _prioritize(matches):
    """Спочатку популярні, далі — за часом початку (найближчі раніше)."""
    return sorted(matches, key=lambda m: (0 if m.is_popular else 1, m.kickoff))


def _safe_analyze(asvc, matches, db):
    """Аналізує матчі, пропускаючи ті, де API дав збій (щоб не було помилки 500)."""
    out = []
    for m in matches:
        try:
            out.append(asvc.analyze(m, db))
        except Exception:
            continue
    return out


@router.post("/matches/{match_id}/analyze", response_model=MatchAnalysisOut)
def analyze_match(
    match_id: int,
    markets: Optional[list[str]] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> MatchAnalysisOut:
    match = registry.sports.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    svc = AnalysisService(registry)
    analysis = svc.analyze(match, db, markets_filter=markets)
    return analysis_to_out(analysis)


@router.post("/matches/{match_id}/explain")
def explain_match(
    match_id: int,
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> dict:
    """Генерує текстовий («людяний») розбір матчу українською."""
    match = registry.sports.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    analysis = AnalysisService(registry).analyze(match, db)
    home = registry.sports.get_team_stats(match.home.id)
    away = registry.sports.get_team_stats(match.away.id)
    recent_home = registry.sports.get_recent_results(match.home.id)
    recent_away = registry.sports.get_recent_results(match.away.id)
    return NarrativeService().build(match, analysis, home, away, recent_home, recent_away)


def _pick_view(analysis: MatchAnalysis, pred) -> dict:
    m = analysis.match
    return {
        "match_id": m.id,
        "match_label": f"{m.home.name} — {m.away.name}",
        "league": m.league,
        "kickoff": m.kickoff.isoformat(),
        "status": m.status.value,
        "market": pred.market,
        "selection": pred.selection,
        "decimal_odds": pred.decimal_odds,
        "model_probability": pred.model_probability,
        "implied_probability": pred.implied_probability,
        "fair_probability": pred.fair_probability,
        "edge": pred.edge,
        "ev": pred.ev,
        "confidence": pred.confidence,
        "risk": pred.risk,
        "odds_source": pred.odds_source,
        "data_quality": analysis.data_quality.label,
    }


@router.post("/top-picks")
def top_picks(
    date_filter: str = Query("next3"),
    league: Optional[str] = Query(None),
    limit: int = Query(8),
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> dict:
    """«ТОП дня»: сканує матчі й повертає найцінніші ставки + надійні експреси."""
    msvc = MatchService(registry)
    asvc = AnalysisService(registry)
    matches = msvc.list_matches(date_filter=date_filter, league=league, db=db)
    matches = _prioritize([m for m in matches if m.status != MatchStatus.FINISHED])[:MAX_MATCHES_ANALYZE]

    analyses = _safe_analyze(asvc, matches, db)
    scored: list[dict] = []
    legs: list[AccaLeg] = []
    for a in analyses:
        min_sample = 0
        hs = registry.sports.get_team_stats(a.match.home.id)
        as_ = registry.sports.get_team_stats(a.match.away.id)
        if hs and as_:
            min_sample = min(hs.sample_size(), as_.sample_size())
        for p in a.predictions:
            if p.decimal_odds is None or p.ev is None or p.ev <= 0:
                continue
            warnings = detect_traps(p, a.data_quality.score, min_sample)
            view = _pick_view(a, p)
            view["value_score"] = round(value_score(p), 4)
            view["kelly_pct"] = round(kelly_fraction(p.model_probability, p.decimal_odds) * 100, 1)
            view["warnings"] = warnings
            view["is_trap"] = len(warnings) > 0
            scored.append(view)
            legs.append(AccaLeg(
                match_id=a.match.id,
                match_label=f"{a.match.home.name} — {a.match.away.name}",
                league=a.match.league,
                market=p.market, selection=p.selection,
                decimal_odds=p.decimal_odds, model_probability=p.model_probability,
                confidence=p.confidence, ev=p.ev, risk=p.risk,
                reason=(p.args_for[0] if p.args_for else f"модель {round(p.model_probability * 100)}%"),
            ))

    # найкращі: спочатку без пасток, за композитною цінністю
    scored.sort(key=lambda x: (0 if x["is_trap"] else 1, x["value_score"]), reverse=True)
    top = scored[:limit]

    builder = AccumulatorBuilder()
    return {
        "analyzed": len(analyses),
        "top_bets": top,
        "safest_express": builder.build(legs, mode="careful"),
        "balanced_express": builder.build(legs, mode="balanced"),
        "data_source": registry.data_source_info(),
    }


@router.post("/analyze-all")
def analyze_all(
    date_filter: str = Query("next3"),
    league: Optional[str] = Query(None),
    only_value: bool = Query(True, description="Лише ставки з позитивним EV у вкладці «найкращі»"),
    match_ids: Optional[list[int]] = Body(default=None, embed=True),
    db: Session = Depends(get_db),
    registry: ProviderRegistry = Depends(get_registry),
) -> dict:
    msvc = MatchService(registry)
    asvc = AnalysisService(registry)

    if match_ids:
        matches = [registry.sports.get_match(mid) for mid in match_ids]
        matches = [m for m in matches if m is not None]
    else:
        matches = msvc.list_matches(date_filter=date_filter, league=league, db=db)
        matches = [m for m in matches if m.status != MatchStatus.FINISHED]

    matches = _prioritize(matches)[:MAX_MATCHES_ANALYZE]

    analyses = _safe_analyze(asvc, matches, db)

    picks: list[dict] = []
    skip_list: list[dict] = []
    legs: list[AccaLeg] = []

    for a in analyses:
        if a.skip_recommended:
            skip_list.append({
                "match_id": a.match.id,
                "match_label": f"{a.match.home.name} — {a.match.away.name}",
                "league": a.match.league,
                "reason": a.summary,
                "data_quality": a.data_quality.label,
            })
        for p in a.predictions:
            if p.decimal_odds is None or p.ev is None:
                continue
            view = _pick_view(a, p)
            picks.append(view)
            legs.append(AccaLeg(
                match_id=a.match.id,
                match_label=f"{a.match.home.name} — {a.match.away.name}",
                league=a.match.league,
                market=p.market, selection=p.selection,
                decimal_odds=p.decimal_odds, model_probability=p.model_probability,
                confidence=p.confidence, ev=p.ev, risk=p.risk,
                reason=(p.args_for[0] if p.args_for else f"модель {round(p.model_probability * 100)}%"),
            ))

    def by_ev(items):
        return sorted(items, key=lambda x: (x["ev"] if x["ev"] is not None else -99,
                                            x["confidence"]), reverse=True)

    value_picks = [p for p in picks if p["ev"] is not None and p["ev"] > 0]
    # «Найкращі» — це value-ставки з достатньою впевненістю (не лише лонгшоти
    # з роздутим EV на малоймовірних ринках), відсортовані за EV.
    best_pool = [p for p in (value_picks if only_value else picks) if p["confidence"] >= 5.5]
    best = by_ev(best_pool)[:TAB_LIMIT]

    def tab(pred_filter):
        return by_ev([p for p in picks if pred_filter(p)])[:TAB_LIMIT]

    tabs = {
        "best": best,
        "low_risk": tab(lambda p: p["risk"] == "low" and p["confidence"] >= 6.5),
        "medium_risk": tab(lambda p: p["risk"] == "medium"),
        "high_risk": tab(lambda p: p["risk"] == "high"),
        "totals": tab(lambda p: p["market"].startswith(("over_", "under_"))),
        "btts": tab(lambda p: p["market"].startswith("btts")),
        "match_result": tab(lambda p: p["market"].startswith(("1x2_", "dc_", "dnb_"))
                            or p["market"].endswith("no_lose")),
        "team_totals": tab(lambda p: p["market"].startswith(("team_home", "team_away"))),
        "live": tab(lambda p: p["status"] == MatchStatus.LIVE.value),
        "skip": skip_list,
    }

    builder = AccumulatorBuilder()
    accumulators = {
        mode: builder.build(legs, mode=mode)
        for mode in ("careful", "balanced", "risky")
    }

    return {
        "analyzed": len(analyses),
        "skipped": len(skip_list),
        "value_count": len(value_picks),
        "data_source": registry.data_source_info(),
        "tabs": tabs,
        "accumulators": accumulators,
    }
