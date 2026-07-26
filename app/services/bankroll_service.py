"""BankrollService — облік банкролу (без реальних грошей) та поради щодо ставки.

Реалізує спрощений Kelly для рекомендованого розміру ставки. Це лише
математична підказка з обліку, а НЕ фінансова порада.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.models import BankrollTxn


class BankrollService:
    def add_txn(self, db: Session, kind: str, amount: float, note: str = "") -> BankrollTxn:
        row = BankrollTxn(kind=kind, amount=amount, note=note)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def balance(self, db: Session) -> float:
        rows = db.execute(select(BankrollTxn)).scalars().all()
        total = 0.0
        for r in rows:
            if r.kind in ("deposit", "payout"):
                total += r.amount
            elif r.kind in ("withdraw", "bet"):
                total -= r.amount
        return round(total, 2)

    def summary(self, db: Session) -> dict:
        rows = db.execute(select(BankrollTxn)).scalars().all()
        deposits = sum(r.amount for r in rows if r.kind == "deposit")
        withdraws = sum(r.amount for r in rows if r.kind == "withdraw")
        bets = sum(r.amount for r in rows if r.kind == "bet")
        payouts = sum(r.amount for r in rows if r.kind == "payout")
        return {
            "balance": self.balance(db),
            "deposits": round(deposits, 2),
            "withdraws": round(withdraws, 2),
            "total_bet": round(bets, 2),
            "total_payout": round(payouts, 2),
            "txn_count": len(rows),
        }

    @staticmethod
    def kelly_fraction(model_probability: float, decimal_odds: float,
                       fraction: float = 0.25) -> float:
        """Частка банкролу за критерієм Келлі (за замовчуванням чверть-Келлі).

        b = odds-1; f* = (b*p - (1-p)) / b. Обрізається знизу нулем.
        """
        b = decimal_odds - 1.0
        if b <= 0:
            return 0.0
        p = max(0.0, min(1.0, model_probability))
        f = (b * p - (1 - p)) / b
        return round(max(0.0, f) * fraction, 4)

    def recommended_stake(self, db: Session, model_probability: float,
                          decimal_odds: float, fraction: float = 0.25) -> dict:
        bal = self.balance(db)
        kf = self.kelly_fraction(model_probability, decimal_odds, fraction)
        return {
            "balance": bal,
            "kelly_fraction": kf,
            "recommended_stake": round(bal * kf, 2),
            "note": "Це лише математична підказка (чверть-Келлі), а не фінансова порада.",
        }
