"""Корекція Dixon-Coles для низьких рахунків (0:0, 1:0, 0:1, 1:1).

Класична модель Пуассона недооцінює нічиї та занижує залежність між кількістю
голів у низьких рахунках. Функція tau коригує чотири комірки матриці.
"""
from __future__ import annotations

from .poisson import score_matrix, ScoreGrid


def _tau(home_goals: int, away_goals: int, lam_home: float, lam_away: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lam_home * lam_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lam_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lam_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_matrix(
    lam_home: float,
    lam_away: float,
    max_goals: int = 10,
    rho: float = -0.13,
) -> ScoreGrid:
    """Матриця рахунків з корекцією Dixon-Coles."""
    base = score_matrix(lam_home, lam_away, max_goals)
    m = [row[:] for row in base.matrix]
    for i in range(min(2, max_goals + 1)):
        for j in range(min(2, max_goals + 1)):
            m[i][j] *= _tau(i, j, lam_home, lam_away, rho)
    grid = ScoreGrid(m, lam_home, lam_away)
    return grid.normalized()
