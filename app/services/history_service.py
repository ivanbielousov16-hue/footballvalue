"""HistoryService — збереження прогнозів і статистика точності моделі."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import PredictionHistory


class HistoryService:
    def __init__(self, model_version: str = "0.1.0") -> None:
        self.model_version = model_version

    def save(self, db: Session, *, match_id: int, match_label: str, league: str,
             market: str, selection: str, model_probability: float,
             decimal_odds: float, ev: float, confidence: float,
             odds_source: str, stake: float = 1.0) -> PredictionHistory:
        row = PredictionHistory(
            match_id=match_id, match_label=match_label, league=league,
            market=market, selection=selection, model_probability=model_probability,
            decimal_odds=decimal_odds, ev=ev, confidence=confidence,
            odds_source=odds_source, model_version=self.model_version,
            created_at=datetime.utcnow(), stake=stake,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list(self, db: Session, settled: Optional[bool] = None) -> list[PredictionHistory]:
        stmt = select(PredictionHistory).order_by(PredictionHistory.created_at.desc())
        if settled is not None:
            stmt = stmt.where(PredictionHistory.settled == settled)
        return list(db.execute(stmt).scalars().all())

    def settle(self, db: Session, history_id: int, won: bool) -> Optional[PredictionHistory]:
        row = db.get(PredictionHistory, history_id)
        if row is None:
            return None
        row.settled = True
        row.won = won
        row.profit = (row.decimal_odds - 1.0) * row.stake if won else -row.stake
        db.commit()
        db.refresh(row)
        return row

    def stats(self, db: Session) -> dict:
        rows = self.list(db, settled=True)
        total = len(rows)
        if total == 0:
            return {
                "settled": 0, "wins": 0, "win_rate": 0.0, "roi": 0.0, "yield": 0.0,
                "total_staked": 0.0, "total_profit": 0.0, "max_drawdown": 0.0,
                "by_league": {}, "by_market": {}, "by_confidence": {},
                "note": "Ще немає завершених прогнозів для оцінки.",
            }
        wins = sum(1 for r in rows if r.won)
        staked = sum(r.stake for r in rows)
        profit = sum(r.profit for r in rows)

        # максимальна просадка по кумулятивному P/L (хронологічно)
        chrono = sorted(rows, key=lambda r: r.created_at)
        cum = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in chrono:
            cum += r.profit
            peak = max(peak, cum)
            max_dd = max(max_dd, peak - cum)

        def bucket(key_fn) -> dict:
            groups: dict[str, list[PredictionHistory]] = {}
            for r in rows:
                groups.setdefault(str(key_fn(r)), []).append(r)
            res = {}
            for k, items in groups.items():
                st = sum(i.stake for i in items)
                pr = sum(i.profit for i in items)
                res[k] = {
                    "count": len(items),
                    "wins": sum(1 for i in items if i.won),
                    "win_rate": round(sum(1 for i in items if i.won) / len(items), 3),
                    "roi": round(pr / st, 4) if st else 0.0,
                    "profit": round(pr, 2),
                }
            return res

        def conf_bucket(r: PredictionHistory) -> str:
            c = r.confidence
            if c >= 8:
                return "8-10"
            if c >= 6:
                return "6-8"
            if c >= 4:
                return "4-6"
            return "1-4"

        return {
            "settled": total,
            "wins": wins,
            "win_rate": round(wins / total, 3),
            "roi": round(profit / staked, 4) if staked else 0.0,
            "yield": round(profit / staked, 4) if staked else 0.0,
            "total_staked": round(staked, 2),
            "total_profit": round(profit, 2),
            "max_drawdown": round(max_dd, 2),
            "by_league": bucket(lambda r: r.league or "—"),
            "by_market": bucket(lambda r: r.market),
            "by_confidence": bucket(conf_bucket),
        }
