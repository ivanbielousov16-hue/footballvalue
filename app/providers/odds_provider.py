"""OddsProvider — реальні коефіцієнти через The Odds API (легальний Odds API).

Активується ЛИШЕ якщо задано FV_THE_ODDS_API_KEY. Без ключа `available` = False.

The Odds API НЕ надає ліній конкретно 1win, але містить схожі букмекерські лінії
(1X2, totals, spreads) багатьох легальних букмекерів. Джерело кожного коефіцієнта
завжди позначається у полі bookmaker/source, щоб користувач бачив походження.
Для точного порівняння саме з 1win використовуйте ручне введення.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from ..models.domain import OddsQuote
from .base import OddsProviderBase

_BASE = "https://api.the-odds-api.com/v4"


class OddsProvider(OddsProviderBase):
    name = "the_odds_api"
    is_mock = False

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.available = bool(api_key)
        self._timeout = timeout

    def get_odds(self, match_id: int) -> list[OddsQuote]:
        # The Odds API використовує власні event_id, не збігаються з API-Football.
        # Тому пряме зіставлення за match_id у MVP не виконується; метод повертає
        # порожньо, а зіставлення реалізується на рівні сервісу за назвами команд
        # (наступний крок). Це запобігає видачі невідповідних коефіцієнтів.
        return []

    def list_sport_odds(self, sport_key: str = "soccer",
                        regions: str = "eu", markets: str = "h2h,totals") -> list[dict]:
        """Повертає сирі події з коефіцієнтами для подальшого зіставлення."""
        if not self.available:
            return []
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{_BASE}/sports/{sport_key}/odds", params=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()
