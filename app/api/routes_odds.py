"""Маршрути коефіцієнтів: ручне введення, вставка тексту, перегляд, очищення."""
from __future__ import annotations

from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..providers.manual_odds import ManualOddsProvider
from ..providers.odds_paste_parser import parse_odds_text
from ..schemas.models import ManualOddsIn, PasteIn, OddsQuoteOut
from ..services.registry import get_registry, ProviderRegistry

router = APIRouter()


@router.get("/odds/match/{match_id}", response_model=list[OddsQuoteOut])
def get_match_odds(match_id: int, db: Session = Depends(get_db),
                   registry: ProviderRegistry = Depends(get_registry)) -> list[OddsQuoteOut]:
    quotes = registry.get_odds_for_match(match_id, db)
    return [
        OddsQuoteOut(market=q.market, selection=q.selection, decimal_odds=q.decimal_odds,
                     source=q.source, bookmaker=q.bookmaker, updated_at=q.updated_at)
        for q in quotes
    ]


@router.post("/odds/manual", response_model=OddsQuoteOut)
def add_manual_odds(payload: ManualOddsIn, db: Session = Depends(get_db),
                    registry: ProviderRegistry = Depends(get_registry)) -> OddsQuoteOut:
    if registry.sports.get_match(payload.match_id) is None:
        raise HTTPException(status_code=404, detail="Матч не знайдено")
    provider = ManualOddsProvider(db)
    row = provider.add_odds(
        match_id=payload.match_id, market=payload.market,
        decimal_odds=payload.decimal_odds, selection=payload.selection,
        source=payload.source, bookmaker=payload.bookmaker,
    )
    return OddsQuoteOut(market=row.market, selection=row.selection,
                        decimal_odds=row.decimal_odds, source=row.source,
                        bookmaker=row.bookmaker, updated_at=row.created_at)


@router.delete("/odds/match/{match_id}")
def clear_match_odds(match_id: int, db: Session = Depends(get_db)) -> dict:
    provider = ManualOddsProvider(db)
    n = provider.clear_match(match_id)
    return {"status": "cleared", "removed": n}


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# Дзеркальні ринки (для випадку, коли команди у вставленому тексті йдуть у
# зворотному порядку відносно фікстури).
_FLIP = {
    "1x2_home": "1x2_away", "1x2_away": "1x2_home",
    "dc_1x": "dc_x2", "dc_x2": "dc_1x",
    "dnb_home": "dnb_away", "dnb_away": "dnb_home",
    "home_no_lose": "away_no_lose", "away_no_lose": "home_no_lose",
    "team_home_over_0.5": "team_away_over_0.5", "team_away_over_0.5": "team_home_over_0.5",
    "team_home_over_1.5": "team_away_over_1.5", "team_away_over_1.5": "team_home_over_1.5",
    "team_home_over_2.5": "team_away_over_2.5", "team_away_over_2.5": "team_home_over_2.5",
    "ht_1x2_home": "ht_1x2_away", "ht_1x2_away": "ht_1x2_home",
}


def _flip_market(market_key: str) -> str:
    return _FLIP.get(market_key, market_key)


@router.post("/odds/paste")
def paste_odds(payload: PasteIn, date_filter: str = "next7",
               db: Session = Depends(get_db),
               registry: ProviderRegistry = Depends(get_registry)) -> dict:
    """Розбирає вставлений текст і зіставляє події з наявними матчами за назвами команд."""
    parsed = parse_odds_text(payload.text)
    from ..services.match_service import MatchService
    matches = MatchService(registry).list_matches(date_filter=date_filter, db=db)
    provider = ManualOddsProvider(db)

    added = []
    unmatched = []
    for line in parsed:
        # знаходимо найкращий матч за схожістю назв команд
        best_m = None
        best_score = 0.0
        best_reversed = False
        for m in matches:
            score = (_similar(line.home, m.home.name) + _similar(line.away, m.away.name)) / 2
            score_rev = (_similar(line.home, m.away.name) + _similar(line.away, m.home.name)) / 2
            s = max(score, score_rev)
            if s > best_score:
                best_score = s
                best_m = m
                best_reversed = score_rev > score

        if best_m is None or best_score < 0.5 or line.market_key is None or line.decimal_odds is None:
            unmatched.append({
                "home": line.home, "away": line.away, "market_text": line.market_text,
                "market_key": line.market_key, "odds": line.decimal_odds,
                "reason": ("не знайдено матч" if best_score < 0.5 else
                           "не розпізнано ринок" if line.market_key is None else
                           "не вказано коефіцієнт"),
                "match_score": round(best_score, 2),
            })
            continue

        # якщо матч знайдено у зворотному порядку команд — дзеркалимо сторонні ринки
        market_key = _flip_market(line.market_key) if best_reversed else line.market_key
        row = provider.add_odds(
            match_id=best_m.id, market=market_key,
            decimal_odds=line.decimal_odds, selection=line.selection,
            source="paste", bookmaker=payload.bookmaker,
        )
        added.append({
            "match_id": best_m.id,
            "match_label": f"{best_m.home.name} — {best_m.away.name}",
            "market": row.market, "selection": row.selection,
            "odds": row.decimal_odds, "match_score": round(best_score, 2),
        })

    return {"added": added, "unmatched": unmatched,
            "parsed_lines": len(parsed), "added_count": len(added)}
