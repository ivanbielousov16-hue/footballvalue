"""Абстрактні інтерфейси провайдерів."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from datetime import date as _date

from ..models.domain import Match, MatchStatus, TeamStats, OddsQuote


class SportsProvider(ABC):
    """Джерело матчів та статистики команд."""

    name: str = "abstract"
    is_mock: bool = True

    @abstractmethod
    def list_matches(self, day_from: date, day_to: date) -> list[Match]:
        ...

    @abstractmethod
    def get_match(self, match_id: int) -> Match | None:
        ...

    @abstractmethod
    def get_team_stats(self, team_id: int) -> TeamStats | None:
        ...

    @abstractmethod
    def list_leagues(self) -> list[dict]:
        ...

    def get_recent_results(self, team_id: int, last: int = 5) -> list[dict]:
        """Останні матчі команди: [{opponent, is_home, gf, ga, result}].

        Необов'язковий метод — за замовчуванням порожньо. Провайдери, що вміють,
        перевизначають його.
        """
        return []

    def get_live_matches(self) -> list[Match]:
        """Матчі, що йдуть зараз. За замовчуванням — фільтр сьогоднішніх."""
        today = _date.today()
        try:
            return [m for m in self.list_matches(today, today)
                    if m.status == MatchStatus.LIVE]
        except Exception:
            return []


class OddsProviderBase(ABC):
    """Джерело коефіцієнтів."""

    name: str = "abstract"
    is_mock: bool = True

    @abstractmethod
    def get_odds(self, match_id: int) -> list[OddsQuote]:
        ...
