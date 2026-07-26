"""Domain models (dataclasses), не залежать від бази даних."""
from .domain import (
    Team,
    TeamStats,
    Match,
    MatchStatus,
    OddsQuote,
    MarketPrediction,
    MatchAnalysis,
    DataQuality,
)

__all__ = [
    "Team",
    "TeamStats",
    "Match",
    "MatchStatus",
    "OddsQuote",
    "MarketPrediction",
    "MatchAnalysis",
    "DataQuality",
]
