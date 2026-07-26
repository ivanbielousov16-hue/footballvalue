"""Спільні залежності FastAPI."""
from __future__ import annotations

from ..services.registry import get_registry, ProviderRegistry
from ..services.analysis_service import AnalysisService
from ..services.match_service import MatchService
from ..services.history_service import HistoryService
from ..services.bankroll_service import BankrollService


def registry_dep() -> ProviderRegistry:
    return get_registry()


def analysis_service() -> AnalysisService:
    return AnalysisService(get_registry())


def match_service() -> MatchService:
    return MatchService(get_registry())


def history_service() -> HistoryService:
    return HistoryService()


def bankroll_service() -> BankrollService:
    return BankrollService()
