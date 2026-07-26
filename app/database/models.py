"""ORM-моделі бази даних."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ManualOddsRow(Base):
    """Коефіцієнт, введений користувачем вручну / імпортований / вставлений."""
    __tablename__ = "manual_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, index=True)
    market: Mapped[str] = mapped_column(String(64))
    selection: Mapped[str] = mapped_column(String(128), default="")
    decimal_odds: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    bookmaker: Mapped[str] = mapped_column(String(32), default="1win")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PredictionHistory(Base):
    """Збережений прогноз для перевірки точності."""
    __tablename__ = "prediction_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, index=True)
    match_label: Mapped[str] = mapped_column(String(160), default="")
    league: Mapped[str] = mapped_column(String(80), default="")
    market: Mapped[str] = mapped_column(String(64))
    selection: Mapped[str] = mapped_column(String(128), default="")
    model_probability: Mapped[float] = mapped_column(Float)
    decimal_odds: Mapped[float] = mapped_column(Float, default=0.0)
    ev: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    odds_source: Mapped[str] = mapped_column(String(32), default="")
    model_version: Mapped[str] = mapped_column(String(32), default="0.1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Результат (заповнюється після матчу)
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    won: Mapped[bool] = mapped_column(Boolean, default=False)
    profit: Mapped[float] = mapped_column(Float, default=0.0)  # у одиницях ставки
    stake: Mapped[float] = mapped_column(Float, default=1.0)


class BankrollTxn(Base):
    """Рух банкролу (ставка/поповнення/зняття) — лише облік, без реальних грошей."""
    __tablename__ = "bankroll_txn"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24))  # deposit/withdraw/bet/payout
    amount: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FavoriteRow(Base):
    """Матч у «Вибране»."""
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
