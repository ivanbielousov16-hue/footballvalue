"""Парсер вставленого тексту зі списком матчів і коефіцієнтів.

Приклад вхідного тексту:

    Arsenal — Chelsea
    Тотал більше 2.5
    Коефіцієнт 1.85

    Real Madrid — Valencia
    Перемога Real Madrid
    Коефіцієнт 1.42

Розуміє українські та російські формулювання ринків. Повертає структуровані
рядки, де ринок уже зіставлений з внутрішнім ключем (market_key), якщо вдалося.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_TEAM_SEP = re.compile(r"\s*(?:—|–|-|vs\.?|:| проти )\s*", re.IGNORECASE)
_ODDS_RE = re.compile(r"(\d+[.,]\d+)")
_LINE_RE = re.compile(r"(\d+[.,]5)")  # напівцілий тотал: 0.5, 1.5, 2.5...


@dataclass
class ParsedOddsLine:
    home: str
    away: str
    market_text: str
    market_key: Optional[str]
    selection: str
    decimal_odds: Optional[float]
    total_line: Optional[float] = None


def _to_float(text: str) -> Optional[float]:
    m = _ODDS_RE.search(text.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def _extract_line(text: str) -> Optional[float]:
    m = _LINE_RE.search(text.replace(",", "."))
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _looks_like_teams(line: str) -> Optional[tuple[str, str]]:
    parts = _TEAM_SEP.split(line.strip(), maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        left, right = parts[0].strip(), parts[1].strip()
        # відкидаємо рядки-ринки, що випадково містять роздільник
        if any(kw in line.lower() for kw in ("тотал", "коеф", "перемога", "фора")):
            return None
        return left, right
    return None


def _resolve_market(text: str, home: str, away: str) -> tuple[Optional[str], Optional[float], str]:
    """Повертає (market_key, total_line, selection_label)."""
    t = text.lower().strip()
    line = _extract_line(t)

    def team_side(s: str) -> Optional[str]:
        if home.lower() in s:
            return "home"
        if away.lower() in s:
            return "away"
        if any(w in s for w in ("господар", "перша", "п1", "хазя")):
            return "home"
        if any(w in s for w in ("гост", "друга", "п2")):
            return "away"
        return None

    # Обидві заб'ють
    if "обидв" in t or "обе заб" in t or "btts" in t:
        if "ні" in t or "нет" in t or " no" in t:
            return "btts_no", None, "Обидві заб'ють — Ні"
        return "btts_yes", None, "Обидві заб'ють — Так"

    # Індивідуальний тотал
    if "індивід" in t or "индивид" in t or "іт " in t or "ит " in t:
        side = team_side(t) or "home"
        ln = line or 1.5
        over = "менше" not in t and "меньше" not in t
        if over:
            return f"team_{side}_over_{ln}", ln, f"ІТ {'господарів' if side=='home' else 'гостей'} більше {ln}"
        # under для індивідуального тоталу у MVP не рахуємо окремо
        return None, ln, text.strip()

    # Тотал (загальний) першого тайму
    if ("тайм" in t or "half" in t) and "тотал" in t:
        ln = line or 0.5
        over = "менше" not in t and "меньше" not in t
        key = f"ht_over_{ln}" if over else f"ht_under_{ln}"
        return key, ln, f"1-й тайм тотал {'більше' if over else 'менше'} {ln}"

    # Загальний тотал
    if "тотал" in t or "total" in t or "over" in t or "under" in t:
        ln = line or 2.5
        over = "більше" in t or "over" in t or ("менше" not in t and "меньше" not in t and "under" not in t)
        key = f"over_{ln}" if over else f"under_{ln}"
        return key, ln, f"Тотал {'більше' if over else 'менше'} {ln}"

    # Подвійний шанс
    if "подвійний" in t or "двойной" in t or "1x" in t or "x2" in t or "12" in t.replace(" ", ""):
        if "1x" in t.replace(" ", ""):
            return "dc_1x", None, "Подвійний шанс 1X"
        if "x2" in t.replace(" ", ""):
            return "dc_x2", None, "Подвійний шанс X2"
        return "dc_12", None, "Подвійний шанс 12"

    # Не програє
    if "не програ" in t or "не проигр" in t:
        side = team_side(t) or "home"
        return (f"{side}_no_lose", None,
                f"{'Господарі' if side=='home' else 'Гості'} не програють")

    # Ставка без нічиєї
    if "без нічи" in t or "без ничь" in t or "dnb" in t:
        side = team_side(t) or "home"
        return f"dnb_{side}", None, f"Без нічиєї — {'господарі' if side=='home' else 'гості'}"

    # Нічия
    if t in ("нічия", "ничья", "x", "х") or "нічи" in t:
        return "1x2_draw", None, "Нічия (X)"

    # Перемога
    if "перемога" in t or "побед" in t or "win" in t or t in ("п1", "п2"):
        side = team_side(t)
        if side == "home":
            return "1x2_home", None, "Перемога господарів (П1)"
        if side == "away":
            return "1x2_away", None, "Перемога гостей (П2)"

    return None, line, text.strip()


def parse_odds_text(text: str) -> list[ParsedOddsLine]:
    lines = [ln.strip() for ln in text.splitlines()]
    results: list[ParsedOddsLine] = []

    cur_home: Optional[str] = None
    cur_away: Optional[str] = None
    cur_market: Optional[str] = None

    def flush(odds: Optional[float]):
        nonlocal cur_market
        if cur_home and cur_away and cur_market:
            key, ln, sel = _resolve_market(cur_market, cur_home, cur_away)
            results.append(ParsedOddsLine(
                home=cur_home, away=cur_away, market_text=cur_market,
                market_key=key, selection=sel, decimal_odds=odds, total_line=ln,
            ))
        cur_market = None

    for raw in lines:
        if not raw:
            continue
        teams = _looks_like_teams(raw)
        if teams:
            # новий блок
            if cur_market is not None:
                flush(None)
            cur_home, cur_away = teams
            cur_market = None
            continue

        low = raw.lower()
        has_odds = bool(_ODDS_RE.search(raw.replace(",", ".")))
        is_odds_line = ("коеф" in low or "kf" in low or "odds" in low or
                        (has_odds and _extract_line(raw) is None and len(raw.split()) <= 2))

        if is_odds_line and cur_market is not None:
            flush(_to_float(raw))
        elif is_odds_line and cur_market is None:
            # коефіцієнт без ринку — ігноруємо
            continue
        else:
            # рядок ринку (можливо з коефіцієнтом у тому ж рядку)
            if cur_market is not None:
                flush(_to_float(raw) if has_odds else None)
            cur_market = raw
            if has_odds and _extract_line(raw) is None:
                # ринок і коефіцієнт в одному рядку
                flush(_to_float(raw))

    if cur_market is not None:
        flush(None)

    return results
