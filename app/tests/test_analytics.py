"""Тести статистичної аналітики."""
import math

from app.analytics.poisson import poisson_pmf, score_matrix
from app.analytics.dixon_coles import dixon_coles_matrix
from app.analytics.margin import implied_probability, remove_margin, book_margin
from app.analytics.ev import expected_value, edge
from app.ml.base_model import BaseMatchModel
from app.ml.markets import derive_markets
from app.models.domain import TeamStats


def test_poisson_pmf_sums_to_one():
    lam = 1.4
    total = sum(poisson_pmf(k, lam) for k in range(0, 30))
    assert abs(total - 1.0) < 1e-6


def test_score_matrix_normalized():
    grid = score_matrix(1.5, 1.2, max_goals=10)
    total = sum(sum(row) for row in grid.matrix)
    assert abs(total - 1.0) < 1e-6


def test_dixon_coles_normalized_and_shifts_draws():
    lam_h, lam_a = 1.3, 1.1
    base = score_matrix(lam_h, lam_a, 10)
    dc = dixon_coles_matrix(lam_h, lam_a, 10, rho=-0.13)
    assert abs(sum(sum(r) for r in dc.matrix) - 1.0) < 1e-6
    # DC з від'ємним rho підвищує ймовірність рахунку 0:0 і 1:1
    assert dc.prob(0, 0) > base.prob(0, 0)


def test_implied_probability():
    assert abs(implied_probability(2.0) - 0.5) < 1e-9


def test_remove_margin_sums_to_one():
    fair = remove_margin([2.0, 3.5, 4.0])
    assert abs(sum(fair) - 1.0) < 1e-9
    assert book_margin([2.0, 3.5, 4.0]) > 0


def test_expected_value_and_edge():
    assert abs(expected_value(0.5, 2.2) - 0.1) < 1e-9
    assert abs(edge(0.6, 0.55) - 0.05) < 1e-9


def test_derive_markets_consistency():
    probs = derive_markets(1.6, 1.1, 10, -0.13)
    # 1X2 у сумі = 1
    assert abs(probs["1x2_home"] + probs["1x2_draw"] + probs["1x2_away"] - 1.0) < 1e-6
    # over + under = 1
    assert abs(probs["over_2.5"] + probs["under_2.5"] - 1.0) < 1e-6
    # подвійний шанс 1X = home + draw
    assert abs(probs["dc_1x"] - (probs["1x2_home"] + probs["1x2_draw"])) < 1e-6
    # сильніша домашня команда -> P1 > P2
    assert probs["1x2_home"] > probs["1x2_away"]


def test_model_expected_goals_home_advantage():
    strong = TeamStats(team_id=1, matches_played=20, goals_for_avg=2.0, goals_against_avg=0.8,
                       home_goals_for_avg=2.3, home_goals_against_avg=0.7)
    weak = TeamStats(team_id=2, matches_played=20, goals_for_avg=1.0, goals_against_avg=1.6,
                     away_goals_for_avg=0.9, away_goals_against_avg=1.8)
    eg = BaseMatchModel().expected_goals(strong, weak)
    assert eg.lam_home > eg.lam_away
