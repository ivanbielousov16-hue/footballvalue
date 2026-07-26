"""Агрегація всіх API-маршрутів."""
from fastapi import APIRouter

from .routes_meta import router as meta_router
from .routes_matches import router as matches_router
from .routes_analysis import router as analysis_router
from .routes_odds import router as odds_router
from .routes_accumulator import router as accumulator_router
from .routes_history import router as history_router
from .routes_bankroll import router as bankroll_router
from .routes_live import router as live_router

api_router = APIRouter()
api_router.include_router(meta_router, tags=["meta"])
api_router.include_router(matches_router, tags=["matches"])
api_router.include_router(analysis_router, tags=["analysis"])
api_router.include_router(odds_router, tags=["odds"])
api_router.include_router(accumulator_router, tags=["accumulator"])
api_router.include_router(history_router, tags=["history"])
api_router.include_router(bankroll_router, tags=["bankroll"])
api_router.include_router(live_router, tags=["live"])

__all__ = ["api_router"]
