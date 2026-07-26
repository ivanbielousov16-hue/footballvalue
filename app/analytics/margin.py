"""Робота з букмекерською маржею та неявними ймовірностями."""
from __future__ import annotations


def implied_probability(decimal_odds: float) -> float:
    """implied_probability = 1 / decimal_odds."""
    if decimal_odds is None or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be > 1.0")
    return 1.0 / decimal_odds


def book_margin(decimal_odds_list: list[float]) -> float:
    """Сумарна маржа (overround) для набору взаємовиключних результатів.

    Наприклад для 1X2 передають [odds_home, odds_draw, odds_away].
    Повертає overround - 1 (тобто 0.05 = 5% маржі).
    """
    total = sum(implied_probability(o) for o in decimal_odds_list)
    return total - 1.0


def remove_margin(decimal_odds_list: list[float]) -> list[float]:
    """Очищає маржу пропорційним методом.

    Повертає список «справедливих» ймовірностей, що в сумі дають 1.0.
    """
    implied = [implied_probability(o) for o in decimal_odds_list]
    total = sum(implied)
    if total <= 0:
        raise ValueError("invalid odds set")
    return [p / total for p in implied]


def fair_odds(fair_probability: float) -> float:
    """Справедливий коефіцієнт із ймовірності."""
    if not 0.0 < fair_probability <= 1.0:
        raise ValueError("probability must be in (0, 1]")
    return 1.0 / fair_probability
