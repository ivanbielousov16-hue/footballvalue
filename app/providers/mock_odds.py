"""MockOddsProvider — демонстраційні коефіцієнти зі штучною маржею.

Генерує коефіцієнти з модельних ймовірностей, додаючи маржу та невеликий шум,
щоб виникали як value-ситуації, так і невигідні лінії. Усі коефіцієнти
позначені source="mock", bookmaker="DEMO" і НЕ є реальними лініями 1win.
"""
from __future__ import annotations

from datetime import datetime

from ..models.domain import OddsQuote
from ..ml.base_model import BaseMatchModel
from ..ml.markets import derive_markets
from .base import OddsProviderBase, SportsProvider
from ..config import get_settings

# Які ринки виставляти в демо-лінії.
_QUOTED_MARKETS = [
    "1x2_home", "1x2_draw", "1x2_away",
    "dc_1x", "dc_x2", "dc_12",
    "dnb_home", "dnb_away",
    "over_1.5", "under_1.5", "over_2.5", "under_2.5", "over_3.5", "under_3.5",
    "btts_yes", "btts_no",
    "team_home_over_1.5", "team_away_over_1.5",
    "ht_over_0.5", "ht_over_1.5",
]


def _rand(seed: str) -> float:
    import hashlib
    h = hashlib.sha256(seed.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class MockOddsProvider(OddsProviderBase):
    name = "mock_odds"
    is_mock = True

    def __init__(self, sports: SportsProvider, margin: float = 0.06) -> None:
        self._sports = sports
        self._margin = margin
        self._model = BaseMatchModel()

    def get_odds(self, match_id: int) -> list[OddsQuote]:
        match = self._sports.get_match(match_id)
        if match is None:
            return []
        home_stats = self._sports.get_team_stats(match.home.id)
        away_stats = self._sports.get_team_stats(match.away.id)
        if home_stats is None or away_stats is None:
            return []

        eg = self._model.expected_goals(home_stats, away_stats)
        settings = get_settings()
        probs = derive_markets(eg.lam_home, eg.lam_away, settings.max_goals, settings.dixon_coles_rho)

        quotes: list[OddsQuote] = []
        now = datetime.now()
        for market in _QUOTED_MARKETS:
            p = probs.get(market)
            if not p or p <= 0.02 or p >= 0.985:
                continue
            # Додаємо маржу + шум. Ширший шум навмисно робить частину ліній
            # переоціненими (value), щоб демо показувало реальні можливості аналізу.
            shade = self._margin + (_rand(f"{match_id}-{market}") - 0.5) * 0.20
            implied = min(0.985, p * (1.0 + shade))
            odds = round(1.0 / implied, 2)
            quotes.append(OddsQuote(
                market=market,
                selection=market,
                decimal_odds=odds,
                source="mock",
                bookmaker="DEMO",
                updated_at=now,
            ))
        return quotes
