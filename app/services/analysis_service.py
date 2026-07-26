"""AnalysisService — детальний аналіз матчу та формування прогнозів по ринках."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..analytics.ev import expected_value, edge as edge_fn
from ..analytics.margin import implied_probability, remove_margin
from ..config import get_settings
from ..ml.base_model import BaseMatchModel
from ..ml.calibration import calibrate_probability
from ..ml.markets import derive_markets, MARKET_LABELS
from ..models.domain import (
    DataQuality, Match, MarketPrediction, MatchAnalysis, OddsQuote, TeamStats,
)
from .registry import ProviderRegistry

# Групи взаємовиключних результатів для очищення маржі.
_MARGIN_GROUPS: list[list[str]] = [
    ["1x2_home", "1x2_draw", "1x2_away"],
    ["over_0.5", "under_0.5"],
    ["over_1.5", "under_1.5"],
    ["over_2.5", "under_2.5"],
    ["over_3.5", "under_3.5"],
    ["over_4.5", "under_4.5"],
    ["btts_yes", "btts_no"],
    ["dnb_home", "dnb_away"],
    ["ht_over_0.5", "ht_under_0.5"],
    ["ht_over_1.5", "ht_under_1.5"],
    ["ht_1x2_home", "ht_1x2_draw", "ht_1x2_away"],
]


def _group_of(market: str) -> Optional[list[str]]:
    for g in _MARGIN_GROUPS:
        if market in g:
            return g
    return None


class AnalysisService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry
        self.settings = get_settings()
        self.model = BaseMatchModel(home_advantage=self.settings.home_advantage)

    # ---------- якість даних ----------
    def _data_quality(self, home: Optional[TeamStats], away: Optional[TeamStats]) -> DataQuality:
        reasons: list[str] = []
        if home is None or away is None:
            return DataQuality(score=0.2, reasons=["Немає статистики для однієї з команд"])

        score = 1.0
        min_sample = min(home.sample_size(), away.sample_size())
        if min_sample < 5:
            score -= 0.5
            reasons.append(f"Дуже мала вибірка ({min_sample} матчів)")
        elif min_sample < 10:
            score -= 0.2
            reasons.append(f"Обмежена вибірка ({min_sample} матчів)")

        if home.xg_avg is None or away.xg_avg is None:
            score -= 0.1
            reasons.append("Немає даних xG для однієї з команд")

        if home.goals_for_avg is None or away.goals_for_avg is None:
            score -= 0.3
            reasons.append("Немає даних про забиті голи")

        score = max(0.05, min(1.0, score))
        if not reasons:
            reasons.append("Дані повні та достатні")
        return DataQuality(score=round(score, 2), reasons=reasons)

    # ---------- коефіцієнти -> найкраща ціна на ринок ----------
    def _best_odds(self, quotes: list[OddsQuote]) -> dict[str, OddsQuote]:
        best: dict[str, OddsQuote] = {}
        for q in quotes:
            cur = best.get(q.market)
            if cur is None or q.decimal_odds > cur.decimal_odds:
                best[q.market] = q
        return best

    # ---------- впевненість і ризик ----------
    def _confidence(self, model_prob: float, data_quality: float, ev: Optional[float]) -> float:
        prob_factor = model_prob  # чим вища ймовірність відбору, тим впевненіше
        dq_factor = 0.4 + 0.6 * data_quality
        conf = 10.0 * dq_factor * (0.35 + 0.65 * prob_factor)
        if ev is not None and ev > 0.05:
            conf += 0.5
        if ev is not None and ev < 0:
            conf -= 0.5
        return round(max(1.0, min(10.0, conf)), 1)

    def _risk(self, model_prob: float, odds: Optional[float]) -> str:
        if model_prob >= 0.70:
            base = "low"
        elif model_prob >= 0.50:
            base = "medium"
        else:
            base = "high"
        if odds is not None and odds >= 3.0 and base != "high":
            base = "medium" if base == "low" else "high"
        return base

    # ---------- аргументи ----------
    def _arguments(self, market: str, match: Match, home: TeamStats, away: TeamStats,
                   lam_home: float, lam_away: float) -> tuple[list[str], list[str]]:
        pro: list[str] = []
        con: list[str] = []
        total_lambda = lam_home + lam_away

        if market.startswith("over_"):
            pro.append(f"Сумарний очікуваний тотал {total_lambda:.2f} гола")
            if home.goals_for_avg and away.goals_for_avg:
                pro.append(f"Атаки: {home.goals_for_avg:.2f} + {away.goals_for_avg:.2f} гола за матч")
            if home.clean_sheets_ratio and home.clean_sheets_ratio > 0.4:
                con.append("Господарі часто грають «на нуль»")
        elif market.startswith("under_"):
            pro.append(f"Помірний очікуваний тотал {total_lambda:.2f} гола")
            if home.goals_against_avg and home.goals_against_avg < 1.0:
                pro.append("Надійна оборона господарів")
        elif market == "1x2_home":
            pro.append(f"Домашня форма: {home.home_form or '—'}")
            pro.append(f"Очікувані голи господарів {lam_home:.2f}")
            if away.away_form and away.away_form.count("W") >= 2:
                con.append(f"Гості у добрій виїзній формі ({away.away_form})")
        elif market == "1x2_away":
            pro.append(f"Виїзна форма гостей: {away.away_form or '—'}")
            pro.append(f"Очікувані голи гостей {lam_away:.2f}")
        elif market == "1x2_draw":
            pro.append("Команди близькі за силою — підвищена ймовірність нічиєї")
        elif market.startswith("btts"):
            if market == "btts_yes":
                pro.append(f"Обидві атаки активні ({lam_home:.2f} і {lam_away:.2f})")
            else:
                pro.append("Принаймні одна команда схильна грати «на нуль»")
        elif market.startswith("dc_") or market.endswith("no_lose"):
            pro.append("Подвійне покриття результату знижує ризик")
        elif market.startswith("team_home"):
            pro.append(f"Очікувані голи господарів {lam_home:.2f}")
        elif market.startswith("team_away"):
            pro.append(f"Очікувані голи гостей {lam_away:.2f}")

        # загальні контраргументи
        if home.league_position and away.league_position and abs(home.league_position - away.league_position) <= 2:
            con.append("Команди близькі в таблиці — результат менш передбачуваний")
        if min(home.sample_size(), away.sample_size()) < 10:
            con.append("Обмежена вибірка даних")
        if not con:
            con.append("Футбол непередбачуваний — можливі несподіванки")
        return pro, con

    # ---------- головний метод ----------
    def analyze(self, match: Match, db: Session,
                markets_filter: Optional[list[str]] = None) -> MatchAnalysis:
        sports = self.registry.sports
        home_stats = sports.get_team_stats(match.home.id)
        away_stats = sports.get_team_stats(match.away.id)
        dq = self._data_quality(home_stats, away_stats)

        # очікувані голи
        if home_stats and away_stats:
            eg = self.model.expected_goals(home_stats, away_stats)
            lam_home, lam_away = eg.lam_home, eg.lam_away
        else:
            lam_home, lam_away = 1.35 * self.settings.home_advantage, 1.35

        probs = derive_markets(lam_home, lam_away, self.settings.max_goals, self.settings.dixon_coles_rho)

        # коефіцієнти
        quotes = self.registry.get_odds_for_match(match.id, db)
        best = self._best_odds(quotes)

        predictions: list[MarketPrediction] = []
        for market, raw_prob in probs.items():
            if markets_filter and market not in markets_filter:
                continue
            model_prob = calibrate_probability(raw_prob, dq.score)
            quote = best.get(market)

            pred = MarketPrediction(
                market=market,
                selection=MARKET_LABELS.get(market, market),
                model_probability=round(model_prob, 4),
            )

            if quote is not None:
                odds = quote.decimal_odds
                imp = implied_probability(odds)
                fair = self._fair_probability(market, best)
                ev = expected_value(model_prob, odds)
                pred.decimal_odds = odds
                pred.implied_probability = round(imp, 4)
                pred.fair_probability = round(fair, 4) if fair is not None else None
                pred.edge = round(edge_fn(model_prob, fair), 4) if fair is not None else None
                pred.ev = round(ev, 4)
                pred.confidence = self._confidence(model_prob, dq.score, ev)
                pred.risk = self._risk(model_prob, odds)
                pred.odds_source = f"{quote.source}/{quote.bookmaker}" if quote.bookmaker else quote.source
                pred.updated_at = (quote.updated_at or datetime.utcnow()).isoformat()
            else:
                pred.confidence = self._confidence(model_prob, dq.score, None)
                pred.risk = self._risk(model_prob, None)

            if home_stats and away_stats:
                pro, con = self._arguments(market, match, home_stats, away_stats, lam_home, lam_away)
                pred.args_for, pred.args_against = pro, con

            predictions.append(pred)

        # сортуємо: спочатку ставки з коефіцієнтом і найбільшим EV
        predictions.sort(
            key=lambda p: (p.ev if p.ev is not None else -99, p.confidence),
            reverse=True,
        )

        skip = self._should_skip(dq, predictions)
        summary = self._summary(match, dq, predictions, skip)
        return MatchAnalysis(
            match=match, data_quality=dq,
            expected_home_goals=round(lam_home, 2),
            expected_away_goals=round(lam_away, 2),
            predictions=predictions, skip_recommended=skip, summary=summary,
        )

    def _fair_probability(self, market: str, best: dict[str, OddsQuote]) -> Optional[float]:
        group = _group_of(market)
        if not group:
            # немає групи для очищення — повертаємо неявну ймовірність як наближення
            q = best.get(market)
            return implied_probability(q.decimal_odds) if q else None
        odds_list = []
        for m in group:
            q = best.get(m)
            if q is None:
                # неповна група -> не можемо коректно очистити маржу
                qm = best.get(market)
                return implied_probability(qm.decimal_odds) if qm else None
            odds_list.append(q.decimal_odds)
        fair = remove_margin(odds_list)
        return fair[group.index(market)]

    def _should_skip(self, dq: DataQuality, preds: list[MarketPrediction]) -> bool:
        if dq.score < self.settings.min_data_quality:
            return True
        # чи є хоч одна ставка з позитивним EV та достатньою впевненістю
        good = [
            p for p in preds
            if p.ev is not None and p.ev > self.settings.min_ev and p.confidence >= 6.0
        ]
        return len(good) == 0

    def _summary(self, match: Match, dq: DataQuality, preds: list[MarketPrediction],
                 skip: bool) -> str:
        if skip:
            return "Value не знайдено — переваги над коефіцієнтами немає."
        top = next((p for p in preds if p.ev is not None and p.ev > 0), None)
        if top is None:
            return "Ставок із позитивним EV немає."
        return (f"Найкращий ринок: {top.selection} @ {top.decimal_odds} "
                f"(EV {top.ev:+.2%}, впевненість {top.confidence}/10, якість даних: {dq.label}).")
