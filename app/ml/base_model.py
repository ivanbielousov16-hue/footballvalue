"""Базова статистична модель: перетворює статистику команд на очікувані голи.

Використовує підхід сили атаки/захисту відносно середнього ліги (ratio strengths),
за бажанням змішує з xG. Далі очікувані голи (lambda) подаються у Dixon-Coles.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models.domain import TeamStats

LEAGUE_AVG_GOALS = 1.35  # середні голи однієї команди за матч (базова лінія)
MIN_LAMBDA = 0.15
MAX_LAMBDA = 5.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pick(*values: Optional[float]) -> Optional[float]:
    """Повертає перше не-None значення."""
    for v in values:
        if v is not None:
            return v
    return None


@dataclass
class ExpectedGoals:
    lam_home: float
    lam_away: float
    used_xg: bool
    home_attack: float
    away_attack: float
    home_defense: float
    away_defense: float


class BaseMatchModel:
    def __init__(
        self,
        league_avg_goals: float = LEAGUE_AVG_GOALS,
        home_advantage: float = 1.10,
        xg_weight: float = 0.35,
    ) -> None:
        self.league_avg = league_avg_goals
        self.home_advantage = home_advantage
        self.xg_weight = xg_weight

    def _blend_xg(self, goals_avg: Optional[float], xg_avg: Optional[float]) -> Optional[float]:
        """Змішує фактичні голи з xG, якщо xG доступний."""
        if goals_avg is None and xg_avg is None:
            return None
        if xg_avg is None:
            return goals_avg
        if goals_avg is None:
            return xg_avg
        return (1 - self.xg_weight) * goals_avg + self.xg_weight * xg_avg

    def expected_goals(self, home: TeamStats, away: TeamStats) -> ExpectedGoals:
        avg = self.league_avg

        home_scored = self._blend_xg(
            _pick(home.home_goals_for_avg, home.goals_for_avg, avg), home.xg_avg
        )
        away_conceded = _pick(away.away_goals_against_avg, away.goals_against_avg, avg)
        away_scored = self._blend_xg(
            _pick(away.away_goals_for_avg, away.goals_for_avg, avg), away.xg_avg
        )
        home_conceded = _pick(home.home_goals_against_avg, home.goals_against_avg, avg)

        used_xg = home.xg_avg is not None or away.xg_avg is not None

        home_attack = (home_scored or avg) / avg
        away_defense = (away_conceded or avg) / avg
        away_attack = (away_scored or avg) / avg
        home_defense = (home_conceded or avg) / avg

        lam_home = _clamp(avg * home_attack * away_defense * self.home_advantage, MIN_LAMBDA, MAX_LAMBDA)
        lam_away = _clamp(avg * away_attack * home_defense, MIN_LAMBDA, MAX_LAMBDA)

        return ExpectedGoals(
            lam_home=lam_home,
            lam_away=lam_away,
            used_xg=used_xg,
            home_attack=home_attack,
            away_attack=away_attack,
            home_defense=home_defense,
            away_defense=away_defense,
        )
