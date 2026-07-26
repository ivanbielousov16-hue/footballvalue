"""AccumulatorBuilder — розумне формування експресів.

Правила:
- не більше однієї події з одного матчу (уникнення сильної кореляції);
- не додавати подію лише заради збільшення коефіцієнта;
- рахувати приблизну ймовірність проходження;
- показувати слабку ланку та пропонувати альтернативу;
- ніколи не називати експрес «гарантованим».
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AccaLeg:
    match_id: int
    match_label: str
    league: str
    market: str
    selection: str
    decimal_odds: float
    model_probability: float
    confidence: float
    ev: Optional[float]
    risk: str
    reason: str = ""


# Конфігурація режимів.
ACCA_MODES: dict[str, dict] = {
    "careful": {
        "title": "Обережний",
        "min_events": 2, "max_events": 3,
        "leg_odds_min": 1.15, "leg_odds_max": 1.65,
        "min_confidence": 7.0, "min_model_prob": 0.70,
        "require_positive_ev": False,
        "allowed_risk": {"low"},
    },
    "balanced": {
        "title": "Збалансований",
        "min_events": 2, "max_events": 4,
        "leg_odds_min": 1.15, "leg_odds_max": 2.20,
        "min_confidence": 6.5, "min_model_prob": 0.55,
        "require_positive_ev": True,
        "allowed_risk": {"low", "medium"},
    },
    "risky": {
        "title": "Ризиковий",
        "min_events": 2, "max_events": 5,
        "leg_odds_min": 1.20, "leg_odds_max": 4.0,
        "min_confidence": 5.0, "min_model_prob": 0.40,
        "require_positive_ev": False,
        "allowed_risk": {"low", "medium", "high"},
    },
}


class AccumulatorBuilder:
    def _score(self, leg: AccaLeg) -> float:
        ev = leg.ev if leg.ev is not None else 0.0
        return leg.confidence + leg.model_probability * 3 + ev * 5

    def build(
        self,
        legs: list[AccaLeg],
        mode: str = "balanced",
        count: Optional[int] = None,
        target_odds: Optional[float] = None,
        min_confidence: Optional[float] = None,
        min_ev: Optional[float] = None,
        allowed_markets: Optional[list[str]] = None,
        excluded_leagues: Optional[list[str]] = None,
        lenient: bool = False,
    ) -> dict:
        cfg = ACCA_MODES.get(mode, ACCA_MODES["balanced"])

        conf_gate = min_confidence if min_confidence is not None else cfg["min_confidence"]
        ev_gate = min_ev if min_ev is not None else (0.0 if cfg["require_positive_ev"] else None)

        # 1) фільтрація кандидатів.
        # lenient=True (напр. експрес із вибраних матчів): пом'якшуємо пороги, щоб
        # завжди зібрати експрес із того, що обрав користувач — беремо найнадійніший
        # ринок кожного матчу без вимоги позитивного EV.
        candidates: list[AccaLeg] = []
        for leg in legs:
            if leg.decimal_odds is None:
                continue
            if not lenient:
                if not (cfg["leg_odds_min"] <= leg.decimal_odds <= cfg["leg_odds_max"]):
                    continue
                if leg.confidence < conf_gate:
                    continue
                if leg.model_probability < cfg["min_model_prob"]:
                    continue
                if leg.risk not in cfg["allowed_risk"]:
                    continue
                if ev_gate is not None and (leg.ev is None or leg.ev < ev_gate):
                    continue
            else:
                # у м'якому режимі — лише розсудлива нижня межа коефіцієнта
                if leg.decimal_odds < 1.05:
                    continue
            if allowed_markets and leg.market not in allowed_markets:
                continue
            if excluded_leagues and any(x.lower() in leg.league.lower() for x in excluded_leagues):
                continue
            candidates.append(leg)

        # 2) не більше однієї події з матчу — залишаємо найкращу.
        # У м'якому режимі пріоритет — НАДІЙНІСТЬ (найвища ймовірність моделі),
        # а не EV, щоб не лізли лонгшоти з роздутим коефіцієнтом.
        score_fn = (lambda l: l.model_probability) if lenient else self._score
        best_per_match: dict[int, AccaLeg] = {}
        for leg in candidates:
            cur = best_per_match.get(leg.match_id)
            if cur is None or score_fn(leg) > score_fn(cur):
                best_per_match[leg.match_id] = leg
        pool = sorted(best_per_match.values(), key=score_fn, reverse=True)

        # Мінімум для експресу — 2 події. У м'якому режимі не блокуємо збірку
        # «через якість» — беремо все доступне. Порожньо лише коли подій фізично
        # менше двох (тоді просто немає з чого зібрати експрес).
        need = 2 if lenient else cfg["min_events"]
        if len(pool) < 2:
            return {
                "mode": mode, "title": cfg["title"], "legs": [],
                "combined_odds": 0.0, "pass_probability": 0.0,
                "risk_level": "—", "weakest_leg": None, "alternative": None,
                "warning": None,
                "message": None,
            }
        if len(pool) < need:
            need = len(pool)

        # 3) вибір кількості подій.
        # Якщо користувач явно задав count — поважаємо його (навіть якщо більше за
        # типовий максимум режиму), обмежуючи лише кількістю доступних подій.
        max_ev = cfg["max_events"]
        min_ev_count = need
        if count is not None:
            n = max(2, min(count, len(pool)))
        else:
            n = min(max_ev, len(pool))

        selected = pool[:n]

        # 4) підгонка під бажаний загальний коефіцієнт (якщо задано)
        if target_odds is not None:
            selected = self._fit_target(pool, target_odds, min_ev_count, max_ev)

        # 5) метрики
        combined = 1.0
        pass_prob = 1.0
        for leg in selected:
            combined *= leg.decimal_odds
            pass_prob *= leg.model_probability

        weakest = min(selected, key=lambda l: l.model_probability) if selected else None
        alternative = None
        if weakest and len(selected) > cfg["min_events"]:
            remaining = [l for l in selected if l is not weakest]
            alt_odds = 1.0
            alt_prob = 1.0
            for l in remaining:
                alt_odds *= l.decimal_odds
                alt_prob *= l.model_probability
            alternative = {
                "action": "Видалити найслабшу подію",
                "removed": weakest.match_label + " — " + weakest.selection,
                "legs_left": len(remaining),
                "combined_odds": round(alt_odds, 2),
                "pass_probability": round(alt_prob, 4),
            }

        risk_level = self._risk_level(mode, pass_prob, len(selected))
        warning = None

        return {
            "mode": mode,
            "title": cfg["title"],
            "legs": [self._leg_view(l) for l in selected],
            "combined_odds": round(combined, 2),
            "pass_probability": round(pass_prob, 4),
            "risk_level": risk_level,
            "weakest_leg": self._leg_view(weakest) if weakest else None,
            "alternative": alternative,
            "warning": warning,
            "message": None,
        }

    def _fit_target(self, pool: list[AccaLeg], target: float,
                    min_events: int, max_events: int) -> list[AccaLeg]:
        """Жадібно набирає події, щоб наблизити загальний коеф до target."""
        selected: list[AccaLeg] = []
        combined = 1.0
        for leg in pool:
            if len(selected) >= max_events:
                break
            if combined >= target and len(selected) >= min_events:
                break
            selected.append(leg)
            combined *= leg.decimal_odds
        # гарантуємо мінімум подій
        while len(selected) < min_events and len(selected) < len(pool):
            selected.append(pool[len(selected)])
        return selected

    def _risk_level(self, mode: str, pass_prob: float, n: int) -> str:
        if mode == "careful":
            return "низький"
        if mode == "risky":
            return "високий"
        if pass_prob >= 0.55:
            return "середній"
        return "середній-високий"

    @staticmethod
    def _leg_view(leg: AccaLeg) -> dict:
        d = asdict(leg)
        d["model_probability"] = round(leg.model_probability, 4)
        return d
