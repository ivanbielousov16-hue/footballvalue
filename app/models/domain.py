"""Domain dataclasses для матчів, статистики, ринків та аналізу."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    PAUSED = "paused"        # призупинено
    FINISHED = "finished"
    POSTPONED = "postponed"


@dataclass
class Team:
    id: int
    name: str
    country: str = ""


@dataclass
class TeamStats:
    """Агрегована статистика команди. Значення None означає «даних немає»."""
    team_id: int
    matches_played: int = 0
    # Останні N матчів (форма) — рядок з символів W/D/L, найновіший ліворуч.
    form: str = ""
    home_form: str = ""
    away_form: str = ""

    goals_for_avg: Optional[float] = None       # середні забиті
    goals_against_avg: Optional[float] = None   # середні пропущені
    home_goals_for_avg: Optional[float] = None
    home_goals_against_avg: Optional[float] = None
    away_goals_for_avg: Optional[float] = None
    away_goals_against_avg: Optional[float] = None

    xg_avg: Optional[float] = None
    xga_avg: Optional[float] = None
    shots_avg: Optional[float] = None
    shots_on_target_avg: Optional[float] = None
    corners_avg: Optional[float] = None
    cards_avg: Optional[float] = None
    possession_avg: Optional[float] = None
    clean_sheets_ratio: Optional[float] = None
    btts_ratio: Optional[float] = None           # частка матчів «обидві забили»

    league_position: Optional[int] = None
    rest_days: Optional[int] = None

    def sample_size(self) -> int:
        return self.matches_played


@dataclass
class OddsQuote:
    """Один коефіцієнт на конкретний ринок від конкретного джерела."""
    market: str            # ключ ринку, напр. "over_2.5", "1x2_home"
    selection: str         # людяна назва вибору
    decimal_odds: float
    source: str            # "manual", "mock", "the_odds_api", "paste", ...
    bookmaker: str = ""    # напр. "1win"
    updated_at: Optional[datetime] = None


@dataclass
class Match:
    id: int
    home: Team
    away: Team
    league: str
    country: str
    season: str
    kickoff: datetime
    status: MatchStatus = MatchStatus.SCHEDULED
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    minute: Optional[int] = None
    is_popular: bool = False
    # Live-події, важливі для guard'ів.
    red_cards: int = 0
    recent_goal: bool = False       # гол у останні ~2 хв
    recent_penalty: bool = False
    var_in_progress: bool = False
    data_stale: bool = False
    odds: list[OddsQuote] = field(default_factory=list)


@dataclass
class DataQuality:
    """Оцінка повноти й свіжості даних (0..1) з поясненнями."""
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 0.75:
            return "high"
        if self.score >= 0.45:
            return "medium"
        return "low"


@dataclass
class MarketPrediction:
    """Прогноз по одному ринку з усіма похідними метриками."""
    market: str
    selection: str
    model_probability: float
    # Нижче — заповнюється тільки якщо є коефіцієнт.
    decimal_odds: Optional[float] = None
    implied_probability: Optional[float] = None       # 1/odds
    fair_probability: Optional[float] = None          # очищена від маржі
    edge: Optional[float] = None                       # model - fair
    ev: Optional[float] = None                          # model*odds - 1
    confidence: float = 0.0                             # 1..10
    risk: str = "medium"                                # low/medium/high
    args_for: list[str] = field(default_factory=list)
    args_against: list[str] = field(default_factory=list)
    odds_source: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MatchAnalysis:
    match: Match
    data_quality: DataQuality
    expected_home_goals: float
    expected_away_goals: float
    predictions: list[MarketPrediction]
    skip_recommended: bool
    summary: str
