"""Очікувана цінність (EV) та математична перевага (edge)."""
from __future__ import annotations


def expected_value(predicted_probability: float, decimal_odds: float) -> float:
    """EV = predicted_probability * decimal_odds - 1.

    Значення на одиницю ставки. EV=0.05 означає +5% очікуваної цінності.
    """
    if decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be > 1.0")
    if not 0.0 <= predicted_probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    return predicted_probability * decimal_odds - 1.0


def edge(predicted_probability: float, fair_probability: float) -> float:
    """Перевага моделі над справедливою (очищеною від маржі) ймовірністю ринку."""
    return predicted_probability - fair_probability
