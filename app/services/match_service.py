"""MatchService — список, фільтри, пошук, вибране."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import FavoriteRow
from ..models.domain import Match, MatchStatus
from .registry import ProviderRegistry


class MatchService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def _range_for_filter(self, date_filter: str, today: date) -> tuple[date, date]:
        if date_filter == "today":
            return today, today
        if date_filter == "tomorrow":
            d = today + timedelta(days=1)
            return d, d
        if date_filter == "next3":
            return today, today + timedelta(days=3)
        if date_filter == "next7":
            return today, today + timedelta(days=7)
        # live / soon / all -> беремо широке вікно
        return today, today + timedelta(days=7)

    def list_matches(
        self,
        date_filter: str = "today",
        status: Optional[str] = None,
        league: Optional[str] = None,
        country: Optional[str] = None,
        search: Optional[str] = None,
        popular_only: bool = False,
        min_odds: Optional[float] = None,
        max_odds: Optional[float] = None,
        db: Optional[Session] = None,
    ) -> list[Match]:
        today = datetime.now().date()
        now = datetime.now()
        # Live — окремий дешевий шлях (для реального API — один запит live=all).
        if date_filter == "live":
            matches = self.registry.sports.get_live_matches()
        else:
            d_from, d_to = self._range_for_filter(date_filter, today)
            matches = self.registry.sports.list_matches(d_from, d_to)

        out: list[Match] = []
        for m in matches:
            if date_filter == "live" and m.status != MatchStatus.LIVE:
                continue
            if date_filter == "soon":
                delta = (m.kickoff - now).total_seconds() / 60.0
                if not (0 <= delta <= 60):
                    continue
            if status and m.status.value != status:
                continue
            if popular_only and not m.is_popular:
                continue
            if league and league.lower() not in m.league.lower():
                continue
            if country and country.lower() not in m.country.lower():
                continue
            if search:
                s = search.lower()
                hay = f"{m.home.name} {m.away.name} {m.league} {m.country}".lower()
                if s not in hay:
                    continue
            out.append(m)

        # прив'язуємо коефіцієнти для попереднього перегляду (best price only тут не потрібні)
        if db is not None and (min_odds is not None or max_odds is not None):
            filtered = []
            for m in out:
                quotes = self.registry.get_odds_for_match(m.id, db)
                if not quotes:
                    continue
                mx = max(q.decimal_odds for q in quotes)
                mn = min(q.decimal_odds for q in quotes)
                if min_odds is not None and mx < min_odds:
                    continue
                if max_odds is not None and mn > max_odds:
                    continue
                filtered.append(m)
            out = filtered

        return out

    def get_match(self, match_id: int) -> Optional[Match]:
        return self.registry.sports.get_match(match_id)

    # ---- вибране ----
    def add_favorite(self, match_id: int, db: Session) -> None:
        exists = db.execute(
            select(FavoriteRow).where(FavoriteRow.match_id == match_id)
        ).scalar_one_or_none()
        if exists is None:
            db.add(FavoriteRow(match_id=match_id))
            db.commit()

    def remove_favorite(self, match_id: int, db: Session) -> None:
        row = db.execute(
            select(FavoriteRow).where(FavoriteRow.match_id == match_id)
        ).scalar_one_or_none()
        if row is not None:
            db.delete(row)
            db.commit()

    def list_favorites(self, db: Session) -> list[Match]:
        ids = db.execute(select(FavoriteRow.match_id)).scalars().all()
        out = []
        for mid in ids:
            m = self.registry.sports.get_match(mid)
            if m:
                out.append(m)
        out.sort(key=lambda m: m.kickoff)
        return out
