"""LiveService — аналіз live-матчів із захисними guard'ами.

Не показуємо live-рекомендацію, якщо дані ненадійні або щойно сталася подія,
що різко змінює ситуацію (гол, пенальті, червона картка, VAR, пауза).
"""
from __future__ import annotations

from ..models.domain import Match, MatchStatus


def live_guard(match: Match) -> tuple[bool, list[str]]:
    """Повертає (allowed, reasons). allowed=False => рекомендацію показувати НЕ можна."""
    blockers: list[str] = []
    if match.status == MatchStatus.PAUSED:
        blockers.append("Матч призупинено")
    if match.status != MatchStatus.LIVE and match.status != MatchStatus.PAUSED:
        blockers.append("Матч не у стані live")
    if match.data_stale:
        blockers.append("Дані застаріли")
    if match.var_in_progress:
        blockers.append("Триває перегляд VAR")
    if match.recent_goal:
        blockers.append("Щойно стався гол — ринок нестабільний")
    if match.recent_penalty:
        blockers.append("Щойно призначено пенальті")
    if match.red_cards > 0:
        blockers.append("Була червона картка — потрібна переоцінка")
    return (len(blockers) == 0, blockers)


class LiveService:
    def __init__(self, registry) -> None:
        self.registry = registry

    def live_state(self, match: Match) -> dict:
        allowed, blockers = live_guard(match)
        return {
            "match_id": match.id,
            "status": match.status.value,
            "minute": match.minute,
            "score": {"home": match.home_score, "away": match.away_score},
            "recommendation_allowed": allowed,
            "blockers": blockers,
            "note": ("Live-рекомендації тимчасово недоступні для цього матчу."
                     if not allowed else
                     "Live-стан стабільний. Аналіз можливий, але завжди перевіряйте актуальність."),
        }
