"""Poisson-модель футбольних рахунків."""
from __future__ import annotations

import math
from dataclasses import dataclass


def poisson_pmf(k: int, lam: float) -> float:
    """Ймовірність рівно k голів при середньому lam (розподіл Пуассона)."""
    if lam < 0:
        raise ValueError("lambda must be >= 0")
    if k < 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


@dataclass
class ScoreGrid:
    """Матриця ймовірностей рахунків home_goals x away_goals."""
    matrix: list[list[float]]
    lam_home: float
    lam_away: float

    @property
    def max_goals(self) -> int:
        return len(self.matrix) - 1

    def prob(self, home_goals: int, away_goals: int) -> float:
        return self.matrix[home_goals][away_goals]

    def normalized(self) -> "ScoreGrid":
        total = sum(sum(row) for row in self.matrix)
        if total <= 0:
            return self
        m = [[c / total for c in row] for row in self.matrix]
        return ScoreGrid(m, self.lam_home, self.lam_away)


def score_matrix(lam_home: float, lam_away: float, max_goals: int = 10) -> ScoreGrid:
    """Незалежна Poisson-матриця рахунків."""
    home = [poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    away = [poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
    matrix = [[home[i] * away[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    return ScoreGrid(matrix, lam_home, lam_away).normalized()
