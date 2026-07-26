"""Деривація ймовірностей усіх ринків зі score-матриці Dixon-Coles."""
from __future__ import annotations

from ..analytics.dixon_coles import dixon_coles_matrix
from ..analytics.poisson import ScoreGrid

# Частка голів, що припадає на перший тайм (емпірично ~0.44).
FIRST_HALF_FRACTION = 0.45

# Людяні назви ринків (українською) для відображення.
MARKET_LABELS: dict[str, str] = {
    "1x2_home": "Перемога господарів (П1)",
    "1x2_draw": "Нічия (X)",
    "1x2_away": "Перемога гостей (П2)",
    "dc_1x": "Подвійний шанс 1X",
    "dc_x2": "Подвійний шанс X2",
    "dc_12": "Подвійний шанс 12",
    "dnb_home": "Ставка без нічиєї — господарі",
    "dnb_away": "Ставка без нічиєї — гості",
    "over_0.5": "Тотал більше 0.5",
    "under_0.5": "Тотал менше 0.5",
    "over_1.5": "Тотал більше 1.5",
    "under_1.5": "Тотал менше 1.5",
    "over_2.5": "Тотал більше 2.5",
    "under_2.5": "Тотал менше 2.5",
    "over_3.5": "Тотал більше 3.5",
    "under_3.5": "Тотал менше 3.5",
    "over_4.5": "Тотал більше 4.5",
    "under_4.5": "Тотал менше 4.5",
    "btts_yes": "Обидві заб'ють — Так",
    "btts_no": "Обидві заб'ють — Ні",
    "team_home_over_0.5": "ІТ господарів більше 0.5",
    "team_home_over_1.5": "ІТ господарів більше 1.5",
    "team_home_over_2.5": "ІТ господарів більше 2.5",
    "team_away_over_0.5": "ІТ гостей більше 0.5",
    "team_away_over_1.5": "ІТ гостей більше 1.5",
    "team_away_over_2.5": "ІТ гостей більше 2.5",
    "home_to_score": "Господарі заб'ють",
    "away_to_score": "Гості заб'ють",
    "home_no_lose": "Господарі не програють (1X)",
    "away_no_lose": "Гості не програють (X2)",
    "ht_1x2_home": "1-й тайм: П1",
    "ht_1x2_draw": "1-й тайм: X",
    "ht_1x2_away": "1-й тайм: П2",
    "ht_over_0.5": "1-й тайм: тотал більше 0.5",
    "ht_over_1.5": "1-й тайм: тотал більше 1.5",
    "ht_under_0.5": "1-й тайм: тотал менше 0.5",
    "ht_under_1.5": "1-й тайм: тотал менше 1.5",
}


def _outcomes(grid: ScoreGrid) -> tuple[float, float, float]:
    """(home_win, draw, away_win)."""
    home = draw = away = 0.0
    n = grid.max_goals
    for i in range(n + 1):
        for j in range(n + 1):
            p = grid.matrix[i][j]
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def _total_over(grid: ScoreGrid, line: float) -> float:
    """Ймовірність тоталу більше line (line — напівціле, напр. 2.5)."""
    threshold = int(line + 0.5)  # напр. 2.5 -> потрібно >=3 голів
    n = grid.max_goals
    p = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            if i + j >= threshold:
                p += grid.matrix[i][j]
    return p


def _team_over(grid: ScoreGrid, line: float, home_team: bool) -> float:
    threshold = int(line + 0.5)
    n = grid.max_goals
    p = 0.0
    for i in range(n + 1):
        for j in range(n + 1):
            goals = i if home_team else j
            if goals >= threshold:
                p += grid.matrix[i][j]
    return p


def _btts_yes(grid: ScoreGrid) -> float:
    n = grid.max_goals
    p = 0.0
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            p += grid.matrix[i][j]
    return p


def derive_markets(lam_home: float, lam_away: float, max_goals: int, rho: float) -> dict[str, float]:
    """Повертає словник market_key -> probability для повного матчу та 1-го тайму."""
    grid = dixon_coles_matrix(lam_home, lam_away, max_goals, rho)
    ht_grid = dixon_coles_matrix(
        lam_home * FIRST_HALF_FRACTION, lam_away * FIRST_HALF_FRACTION, max_goals, rho
    )

    home_win, draw, away_win = _outcomes(grid)
    ht_home, ht_draw, ht_away = _outcomes(ht_grid)

    probs: dict[str, float] = {}

    probs["1x2_home"] = home_win
    probs["1x2_draw"] = draw
    probs["1x2_away"] = away_win

    probs["dc_1x"] = home_win + draw
    probs["dc_x2"] = draw + away_win
    probs["dc_12"] = home_win + away_win
    probs["home_no_lose"] = home_win + draw
    probs["away_no_lose"] = draw + away_win

    hw_aw = home_win + away_win
    probs["dnb_home"] = home_win / hw_aw if hw_aw > 0 else 0.5
    probs["dnb_away"] = away_win / hw_aw if hw_aw > 0 else 0.5

    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        over = _total_over(grid, line)
        probs[f"over_{line}"] = over
        probs[f"under_{line}"] = 1.0 - over

    btts = _btts_yes(grid)
    probs["btts_yes"] = btts
    probs["btts_no"] = 1.0 - btts

    for line in (0.5, 1.5, 2.5):
        probs[f"team_home_over_{line}"] = _team_over(grid, line, home_team=True)
        probs[f"team_away_over_{line}"] = _team_over(grid, line, home_team=False)

    probs["home_to_score"] = _team_over(grid, 0.5, home_team=True)
    probs["away_to_score"] = _team_over(grid, 0.5, home_team=False)

    probs["ht_1x2_home"] = ht_home
    probs["ht_1x2_draw"] = ht_draw
    probs["ht_1x2_away"] = ht_away
    ht_over_05 = _total_over(ht_grid, 0.5)
    ht_over_15 = _total_over(ht_grid, 1.5)
    probs["ht_over_0.5"] = ht_over_05
    probs["ht_under_0.5"] = 1.0 - ht_over_05
    probs["ht_over_1.5"] = ht_over_15
    probs["ht_under_1.5"] = 1.0 - ht_over_15

    # Обрізаємо у [0,1] через можливі похибки округлення.
    return {k: max(0.0, min(1.0, v)) for k, v in probs.items()}
