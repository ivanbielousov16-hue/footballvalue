"""ManualOddsProvider — коефіцієнти, введені користувачем, з бази даних."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import ManualOddsRow
from ..models.domain import OddsQuote
from .base import OddsProviderBase


class ManualOddsProvider(OddsProviderBase):
    name = "manual_odds"
    is_mock = False  # це реальні коефіцієнти, введені користувачем

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_odds(self, match_id: int) -> list[OddsQuote]:
        rows = self._db.execute(
            select(ManualOddsRow).where(ManualOddsRow.match_id == match_id)
        ).scalars().all()
        return [
            OddsQuote(
                market=r.market,
                selection=r.selection or r.market,
                decimal_odds=r.decimal_odds,
                source=r.source,
                bookmaker=r.bookmaker,
                updated_at=r.created_at,
            )
            for r in rows
        ]

    def add_odds(self, match_id: int, market: str, decimal_odds: float,
                 selection: str = "", source: str = "manual",
                 bookmaker: str = "1win") -> ManualOddsRow:
        row = ManualOddsRow(
            match_id=match_id, market=market, selection=selection or market,
            decimal_odds=decimal_odds, source=source, bookmaker=bookmaker,
            created_at=datetime.utcnow(),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def clear_match(self, match_id: int) -> int:
        rows = self._db.execute(
            select(ManualOddsRow).where(ManualOddsRow.match_id == match_id)
        ).scalars().all()
        for r in rows:
            self._db.delete(r)
        self._db.commit()
        return len(rows)
