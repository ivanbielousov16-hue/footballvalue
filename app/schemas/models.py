"""Схеми даних API (Pydantic v2)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..models.domain import Match, MatchAnalysis


# ---------------- Response ----------------
class TeamOut(BaseModel):
    id: int
    name: str
    country: str = ""


class OddsQuoteOut(BaseModel):
    market: str
    selection: str
    decimal_odds: float
    source: str
    bookmaker: str = ""
    updated_at: Optional[datetime] = None


class MatchOut(BaseModel):
    id: int
    home: TeamOut
    away: TeamOut
    league: str
    country: str
    season: str
    kickoff: datetime
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    minute: Optional[int] = None
    is_popular: bool = False
    odds: list[OddsQuoteOut] = Field(default_factory=list)


class DataQualityOut(BaseModel):
    score: float
    label: str
    reasons: list[str]


class MarketPredictionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    market: str
    selection: str
    model_probability: float
    decimal_odds: Optional[float] = None
    implied_probability: Optional[float] = None
    fair_probability: Optional[float] = None
    edge: Optional[float] = None
    ev: Optional[float] = None
    confidence: float
    risk: str
    args_for: list[str] = Field(default_factory=list)
    args_against: list[str] = Field(default_factory=list)
    odds_source: Optional[str] = None
    updated_at: Optional[str] = None


class MatchAnalysisOut(BaseModel):
    match: MatchOut
    data_quality: DataQualityOut
    expected_home_goals: float
    expected_away_goals: float
    predictions: list[MarketPredictionOut]
    skip_recommended: bool
    summary: str


class LeagueOut(BaseModel):
    id: int
    name: str
    country: str
    season: str = ""
    popular: bool = False


# ---------------- Request ----------------
class ManualOddsIn(BaseModel):
    match_id: int
    market: str = Field(..., description="Ключ ринку, напр. over_2.5, 1x2_home")
    decimal_odds: float = Field(..., gt=1.0)
    selection: str = ""
    bookmaker: str = "1win"
    source: str = "manual"


class PasteIn(BaseModel):
    text: str
    bookmaker: str = "1win"


class AccaBuildIn(BaseModel):
    mode: str = "balanced"
    match_ids: Optional[list[int]] = None      # None => програма обирає сама
    count: Optional[int] = None
    target_odds: Optional[float] = None
    min_confidence: Optional[float] = None
    min_ev: Optional[float] = None
    allowed_markets: Optional[list[str]] = None
    excluded_leagues: Optional[list[str]] = None
    date_filter: str = "next3"
    lenient: bool = False


class HistorySaveIn(BaseModel):
    match_id: int
    market: str
    stake: float = 1.0


class SettleIn(BaseModel):
    won: bool


class BankrollTxnIn(BaseModel):
    kind: str = Field(..., description="deposit/withdraw/bet/payout")
    amount: float = Field(..., gt=0)
    note: str = ""


# ---------------- Converters ----------------
def match_to_out(match: Match, odds=None) -> MatchOut:
    return MatchOut(
        id=match.id,
        home=TeamOut(id=match.home.id, name=match.home.name, country=match.home.country),
        away=TeamOut(id=match.away.id, name=match.away.name, country=match.away.country),
        league=match.league,
        country=match.country,
        season=match.season,
        kickoff=match.kickoff,
        status=match.status.value,
        home_score=match.home_score,
        away_score=match.away_score,
        minute=match.minute,
        is_popular=match.is_popular,
        odds=[
            OddsQuoteOut(
                market=q.market, selection=q.selection, decimal_odds=q.decimal_odds,
                source=q.source, bookmaker=q.bookmaker, updated_at=q.updated_at,
            ) for q in (odds or match.odds)
        ],
    )


def analysis_to_out(analysis: MatchAnalysis) -> MatchAnalysisOut:
    return MatchAnalysisOut(
        match=match_to_out(analysis.match),
        data_quality=DataQualityOut(
            score=analysis.data_quality.score,
            label=analysis.data_quality.label,
            reasons=analysis.data_quality.reasons,
        ),
        expected_home_goals=analysis.expected_home_goals,
        expected_away_goals=analysis.expected_away_goals,
        predictions=[
            MarketPredictionOut(
                market=p.market, selection=p.selection,
                model_probability=p.model_probability,
                decimal_odds=p.decimal_odds, implied_probability=p.implied_probability,
                fair_probability=p.fair_probability, edge=p.edge, ev=p.ev,
                confidence=p.confidence, risk=p.risk,
                args_for=p.args_for, args_against=p.args_against,
                odds_source=p.odds_source, updated_at=p.updated_at,
            ) for p in analysis.predictions
        ],
        skip_recommended=analysis.skip_recommended,
        summary=analysis.summary,
    )
