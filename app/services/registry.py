"""Реєстр провайдерів: обирає реальні провайдери за наявності ключів, інакше mock.

Чітко розділяє реальні та mock-джерела. Кожен коефіцієнт зберігає своє джерело.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.domain import OddsQuote
from ..providers.base import SportsProvider
from ..providers.mock_sports import MockSportsDataProvider
from ..providers.mock_odds import MockOddsProvider
from ..providers.manual_odds import ManualOddsProvider
from ..providers.sports_data import SportsDataProvider
from ..providers.odds_provider import OddsProvider


class ProviderRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings

        # --- Sports provider ---
        if settings.api_football_key:
            real = SportsDataProvider(
                settings.api_football_key,
                host=settings.api_football_host,
                default_season=settings.api_football_season,
            )
            self.sports: SportsProvider = real if real.available else MockSportsDataProvider()
            self.sports_is_mock = not getattr(real, "available", False)
        else:
            self.sports = MockSportsDataProvider()
            self.sports_is_mock = True

        # --- Real odds provider (optional) ---
        self.real_odds = (
            OddsProvider(settings.the_odds_api_key)
            if settings.the_odds_api_key else None
        )

        # --- Mock odds завжди доступні (демо) ---
        self.mock_odds = MockOddsProvider(self.sports)

    def data_source_info(self) -> dict:
        return {
            "sports_provider": self.sports.name,
            "sports_is_mock": self.sports_is_mock,
            "real_odds_provider": self.real_odds.name if self.real_odds else None,
            "mock_odds_enabled": True,
        }

    def get_odds_for_match(self, match_id: int, db: Session,
                           include_mock: bool = True) -> list[OddsQuote]:
        """Об'єднує коефіцієнти: спочатку ручні (1win), потім реальні, потім mock."""
        quotes: list[OddsQuote] = []

        # 1) ручні коефіцієнти користувача (найвищий пріоритет — це саме те, що бачить
        #    користувач у 1win)
        manual = ManualOddsProvider(db)
        quotes.extend(manual.get_odds(match_id))

        # 2) реальні коефіцієнти (якщо провайдер налаштований і вміє зіставляти)
        if self.real_odds is not None:
            try:
                quotes.extend(self.real_odds.get_odds(match_id))
            except Exception:
                pass

        # 3) демо-коефіцієнти (лише якщо немає інших і дозволено)
        has_real = any(q.source != "mock" for q in quotes)
        if include_mock and not has_real:
            quotes.extend(self.mock_odds.get_odds(match_id))

        return quotes


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry()
