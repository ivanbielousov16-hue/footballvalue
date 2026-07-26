"""Live-«мозок»: контекстні розрахунки для матчу, що йде ЗАРАЗ.

Замість «менший коеф = виграє» тут ідуть справжні міркування за станом гри:
скільки часу минуло, який рахунок, наскільки активна гра (темп), скільки голів
очікувати до кінця, хто ймовірніше заб'є наступним, чи буде гол найближчим часом.

Використовує лише хвилину + рахунок + доматчеві очікувані голи (lambda), тому
працює і на реальних, і на демо-даних, без окремого live-стат-фіда.
"""
from __future__ import annotations

import math
from typing import Optional

FULL_MATCH_MINUTES = 90.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def analyze_live(
    lam_home_full: float,
    lam_away_full: float,
    minute: int,
    home_score: int,
    away_score: int,
    home_name: str,
    away_name: str,
) -> dict:
    minute = int(_clamp(minute, 1, 90))
    remaining_min = max(1.0, FULL_MATCH_MINUTES - minute)
    frac_played = minute / FULL_MATCH_MINUTES
    frac_remaining = remaining_min / FULL_MATCH_MINUTES

    lam_total_full = lam_home_full + lam_away_full
    actual_goals = home_score + away_score
    current_total = actual_goals

    # --- темп: скільки голів мало бути до цієї хвилини vs фактично ---
    expected_by_now = lam_total_full * frac_played
    tempo_ratio = actual_goals / expected_by_now if expected_by_now > 0.3 else 1.0
    if tempo_ratio < 0.7:
        tempo_label = "низький (гра спокійніша за очікувану)"
        tempo_factor = 0.85
    elif tempo_ratio > 1.3:
        tempo_label = "високий (голів більше, ніж мало бути)"
        tempo_factor = 1.15
    else:
        tempo_label = "середній (близько до очікуваного)"
        tempo_factor = 1.0

    # --- очікувані голи до кінця матчу (з поправкою на темп) ---
    lam_h_rem = lam_home_full * frac_remaining * tempo_factor
    lam_a_rem = lam_away_full * frac_remaining * tempo_factor
    lam_rem = lam_h_rem + lam_a_rem

    p_no_more = math.exp(-lam_rem)                 # жодного голу до кінця
    p_any_more = 1.0 - p_no_more

    # --- наступний гол ---
    if lam_rem > 0:
        p_next_home = (lam_h_rem / lam_rem) * p_any_more
        p_next_away = (lam_a_rem / lam_rem) * p_any_more
    else:
        p_next_home = p_next_away = 0.0

    # --- гол у найближчі 10 хвилин ---
    span = min(10.0, remaining_min)
    exp_10 = lam_rem * (span / remaining_min)
    p_goal_10 = 1.0 - math.exp(-exp_10)

    # --- підсумкові тотали матчу (з урахуванням уже забитих) ---
    def p_remaining_at_most(k: int) -> float:
        s = 0.0
        for i in range(k + 1):
            s += math.exp(-lam_rem) * (lam_rem ** i) / math.factorial(i)
        return min(1.0, s)

    live_totals = []
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        need = line - current_total  # скільки ще голів для "більше"
        if need <= 0:
            continue  # тотал більше вже зайшов
        k = int(need - 0.5)  # для "менше line" потрібно <= k голів до кінця
        p_under = p_remaining_at_most(k)
        live_totals.append({
            "line": line,
            "p_under": round(p_under, 3),
            "p_over": round(1 - p_under, 3),
        })

    return {
        "minute": minute,
        "remaining_min": int(remaining_min),
        "score": {"home": home_score, "away": away_score},
        "tempo_label": tempo_label,
        "expected_by_now": round(expected_by_now, 1),
        "expected_remaining": round(lam_rem, 1),
        "p_no_more_goals": round(p_no_more, 3),
        "next_goal": {
            "home": round(p_next_home, 3),
            "away": round(p_next_away, 3),
            "none": round(p_no_more, 3),
        },
        "p_goal_next_10min": round(p_goal_10, 3),
        "live_totals": live_totals,
        "home_name": home_name,
        "away_name": away_name,
    }


def live_reasoning_paragraphs(live: dict, blockers: list[str]) -> tuple[list[str], list[str]]:
    """Повертає (paragraphs, suggestions) — текст міркувань і короткі підказки."""
    h, a = live["home_name"], live["away_name"]
    sc = live["score"]
    paras: list[str] = []
    tips: list[str] = []

    if blockers:
        paras.append("⚠️ Зараз рекомендації ненадійні: " + "; ".join(blockers) +
                     ". Почекай, поки гра й ринок стабілізуються.")

    paras.append(
        f"Матч іде: {live['minute']}', рахунок {sc['home']}:{sc['away']}. "
        f"До цієї хвилини за темпом мало бути ~{live['expected_by_now']} гола, "
        f"фактично {sc['home'] + sc['away']} — темп {live['tempo_label']}."
    )
    paras.append(
        f"До кінця матчу (ще ~{live['remaining_min']} хв) очікуємо приблизно "
        f"{live['expected_remaining']} гола. Ймовірність, що більше голів не буде: "
        f"{round(live['p_no_more_goals'] * 100)}%."
    )

    ng = live["next_goal"]
    paras.append(
        f"Наступний гол: {h} — {round(ng['home'] * 100)}%, {a} — {round(ng['away'] * 100)}%, "
        f"більше голів не буде — {round(ng['none'] * 100)}%."
    )
    p10 = live["p_goal_next_10min"]
    paras.append(
        f"Гол у найближчі 10 хвилин: {round(p10 * 100)}%."
        + (" Тобто найближчим часом голу радше не буде." if p10 < 0.35 else "")
    )

    # підказки (без гарантій)
    if not blockers:
        if ng["home"] - ng["away"] > 0.12:
            tips.append(f"Наступний гол найімовірніше за {h}")
        elif ng["away"] - ng["home"] > 0.12:
            tips.append(f"Наступний гол найімовірніше за {a}")

        # найконкретніший корисний live-тотал: найменша лінія з надійним «менше»
        useful_under = next(
            (t for t in sorted(live["live_totals"], key=lambda x: x["line"])
             if t["p_under"] >= 0.60),
            None,
        )
        if useful_under:
            tips.append(f"Підсумковий тотал «менше {useful_under['line']}» "
                        f"(~{round(useful_under['p_under'] * 100)}%)")
        if p10 < 0.30:
            tips.append("У найближчі 10 хв — радше без голу")

    return paras, tips
