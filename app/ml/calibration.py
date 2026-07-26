"""Просте калібрування ймовірностей.

У MVP застосовуємо м'яке «стиснення» до 0.5 (shrinkage), щоб уникати
надмірно впевнених прогнозів на малих вибірках. Коефіцієнт стиснення залежить
від якості даних: що менше даних — то ближче прогноз до 0.5.

Пізніше сюди можна підключити Platt scaling або isotonic regression на історії.
"""
from __future__ import annotations


def calibrate_probability(probability: float, data_quality: float) -> float:
    """Стискає ймовірність до 0.5 залежно від якості даних (0..1)."""
    probability = max(0.0, min(1.0, probability))
    quality = max(0.0, min(1.0, data_quality))
    # shrink=0 при ідеальних даних, до 0.35 при поганих.
    shrink = 0.35 * (1.0 - quality)
    return probability * (1.0 - shrink) + 0.5 * shrink
