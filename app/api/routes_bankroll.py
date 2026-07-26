"""Маршрути банкролу (облік без реальних грошей)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.db import get_db
from ..schemas.models import BankrollTxnIn
from ..services.bankroll_service import BankrollService

router = APIRouter()


@router.get("/bankroll")
def bankroll_summary(db: Session = Depends(get_db)) -> dict:
    return BankrollService().summary(db)


@router.post("/bankroll/txn")
def add_txn(payload: BankrollTxnIn, db: Session = Depends(get_db)) -> dict:
    row = BankrollService().add_txn(db, payload.kind, payload.amount, payload.note)
    return {"id": row.id, "kind": row.kind, "amount": row.amount,
            "balance": BankrollService().balance(db)}


@router.get("/bankroll/recommend")
def recommend_stake(model_probability: float = Query(..., gt=0, lt=1),
                    decimal_odds: float = Query(..., gt=1.0),
                    fraction: float = Query(0.25, gt=0, le=1),
                    db: Session = Depends(get_db)) -> dict:
    return BankrollService().recommended_stake(db, model_probability, decimal_odds, fraction)
