"""Статистична аналітика: Poisson, Dixon-Coles, маржа, EV."""
from .margin import implied_probability, remove_margin, book_margin
from .poisson import poisson_pmf, score_matrix, ScoreGrid
from .dixon_coles import dixon_coles_matrix
from .ev import expected_value, edge

__all__ = [
    "implied_probability",
    "remove_margin",
    "book_margin",
    "poisson_pmf",
    "score_matrix",
    "ScoreGrid",
    "dixon_coles_matrix",
    "expected_value",
    "edge",
]
