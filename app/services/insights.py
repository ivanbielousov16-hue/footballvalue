"""Розумні надбудови: детектор пасток, порада щодо суми (Келлі),
оцінка цінності ставки та глибші фактори для розбору.
"""
from __future__ import annotations

from typing import Optional

from ..models.domain import MarketPrediction, TeamStats


# ---------------- Келлі ----------------
def kelly_fraction(model_prob: float, decimal_odds: float, fraction: float = 0.25,
                   cap: float = 0.10) -> float:
    """Частка банкролу за критерієм Келлі (за замовч. чверть-Келлі), 0..cap."""
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    p = max(0.0, min(1.0, model_prob))
    f = (b * p - (1 - p)) / b
    return round(min(cap, max(0.0, f) * fraction), 4)


# ---------------- Оцінка цінності ----------------
def value_score(pred: MarketPrediction) -> float:
    """Композитна цінність: поєднує EV та впевненість (щоб не лізли самі лонгшоти)."""
    ev = pred.ev if pred.ev is not None else 0.0
    return ev * (0.4 + 0.06 * pred.confidence)


# ---------------- Детектор пасток ----------------
def detect_traps(pred: MarketPrediction, data_quality: float,
                 min_sample: int) -> list[str]:
    """Повертає список попереджень (порожній, якщо все чисто)."""
    w: list[str] = []
    if pred.ev is not None and pred.ev > 0.5 and pred.model_probability < 0.35:
        w.append("Аномально високий EV на малоймовірному ринку — часто це пастка "
                 "або застарілий коефіцієнт.")
    if data_quality < 0.45:
        w.append("Мало даних для цього матчу — прогноз ненадійний.")
    if min_sample < 6:
        w.append("Дуже мала вибірка матчів у команд — статистика нестабільна.")
    if pred.decimal_odds is not None and pred.decimal_odds >= 4.0:
        w.append("Високий коефіцієнт — велика дисперсія, готуйся до серій невдач.")
    if (pred.fair_probability is not None
            and abs(pred.model_probability - pred.fair_probability) > 0.22):
        w.append("Модель сильно розходиться з букмекером — хтось із них помиляється, "
                 "будь обережний.")
    return w


# ---------------- Глибші фактори ----------------
def deep_factors(home: Optional[TeamStats], away: Optional[TeamStats],
                 home_name: str, away_name: str) -> list[str]:
    """Додаткові контекстні спостереження для тексту розбору."""
    out: list[str] = []
    if home is None or away is None:
        return out

    # відпочинок
    if home.rest_days is not None and away.rest_days is not None:
        if home.rest_days - away.rest_days >= 2:
            out.append(f"{home_name} відпочивав довше ({home.rest_days} дн проти "
                       f"{away.rest_days}) — свіжіші.")
        elif away.rest_days - home.rest_days >= 2:
            out.append(f"{away_name} відпочивав довше ({away.rest_days} дн проти "
                       f"{home.rest_days}) — свіжіші.")

    # позиція в таблиці / мотивація
    if home.league_position is not None and away.league_position is not None:
        hp, ap = home.league_position, away.league_position
        if abs(hp - ap) >= 6:
            higher = home_name if hp < ap else away_name
            lower = away_name if hp < ap else home_name
            out.append(f"{higher} значно вище в таблиці (місця {min(hp, ap)} vs "
                       f"{max(hp, ap)}) — на папері сильніші, але {lower} може бути "
                       f"мотивованішим у ролі андердога.")
        if min(hp, ap) <= 3:
            out.append(f"У грі бере участь команда з топ-3 таблиці — висока мотивація "
                       f"боротися за трофей/єврокубки.")

    # тренд форми (порівнюємо старішу й новішу половину рядка форми)
    for stats, name in ((home, home_name), (away, away_name)):
        f = stats.form or ""
        if len(f) >= 4:
            recent = f[:len(f) // 2]      # новіші (ліворуч)
            older = f[len(f) // 2:]       # старіші
            r = recent.count("W") - recent.count("L")
            o = older.count("W") - older.count("L")
            if r - o >= 2:
                out.append(f"{name} набирає форму (останні матчі кращі за попередні).")
            elif o - r >= 2:
                out.append(f"{name} втрачає форму (результати погіршуються).")

    # домашня перевага
    if home.clean_sheets_ratio is not None and home.clean_sheets_ratio >= 0.4:
        out.append(f"{home_name} вдома надійні в обороні (часто грають «на нуль»).")

    return out
