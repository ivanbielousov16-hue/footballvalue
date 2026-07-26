"""NarrativeService — генерує текстовий («людяний») розбір матчу українською.

Вбудований генератор (не зовнішній ШІ): складає зв'язний текст із чисел моделі.
Для LIVE-матчів думає САМЕ про поточний момент (що ставити зараз), а не показує
застарілі доматчеві ринки. Текст залежить від ситуації, тому різниться між матчами.
"""
from __future__ import annotations

from typing import Optional

from ..models.domain import Match, MatchAnalysis, MatchStatus, TeamStats
from ..live.live_reasoning import analyze_live
from ..live.live_service import live_guard
from .insights import kelly_fraction, detect_traps, deep_factors


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def _pred(analysis: MatchAnalysis, market: str):
    for p in analysis.predictions:
        if p.market == market:
            return p
    return None


def _variant(seed: int, options: list[str]) -> str:
    """Детерміновано (стабільно для матчу) обирає варіант фрази — для різноманіття."""
    return options[seed % len(options)]


def _form_readable(form: str) -> str:
    if not form:
        return "немає даних"
    return f"{form} (В{form.count('W')} Н{form.count('D')} П{form.count('L')})"


def _describe_recent(name: str, results: list[dict]) -> Optional[str]:
    """Опис останніх матчів команди: рахунки, серія, тренд."""
    if not results:
        return None
    parts = []
    for r in results:
        vs = "вдома" if r.get("is_home") else "у гостях"
        parts.append(f"{r['gf']}:{r['ga']} з {r['opponent']} ({vs})")
    w = sum(1 for r in results if r["result"] == "W")
    d = sum(1 for r in results if r["result"] == "D")
    l = sum(1 for r in results if r["result"] == "L")
    gf = sum(r["gf"] for r in results)
    ga = sum(r["ga"] for r in results)
    # серія без поразок / поспіль перемог з найновіших
    streak = 0
    for r in results:
        if r["result"] == "L":
            break
        streak += 1
    tail = ""
    if streak >= 3:
        tail = f" Серія без поразок — {streak} матчі."
    elif results[0]["result"] == "L" and len(results) > 1 and results[1]["result"] == "L":
        tail = " Дві поразки поспіль."
    return (f"{name} в останніх {len(results)}: {w} перемог, {d} нічиїх, {l} поразок "
            f"(різниця м'ячів {gf}:{ga}). Останні: " + "; ".join(parts) + "." + tail)


class NarrativeService:
    def build(self, match: Match, analysis: MatchAnalysis,
              home: Optional[TeamStats], away: Optional[TeamStats],
              recent_home: Optional[list[dict]] = None,
              recent_away: Optional[list[dict]] = None) -> dict:
        if match.status == MatchStatus.LIVE and match.minute is not None:
            return self._build_live(match, analysis, home, away)
        return self._build_prematch(match, analysis, home, away, recent_home, recent_away)

    # ==================== LIVE ====================
    def _build_live(self, match, analysis, home, away) -> dict:
        h, a = match.home.name, match.away.name
        hs = match.home_score or 0
        as_ = match.away_score or 0
        total = hs + as_
        _, blockers = live_guard(match)

        live = analyze_live(
            lam_home_full=analysis.expected_home_goals,
            lam_away_full=analysis.expected_away_goals,
            minute=match.minute, home_score=hs, away_score=as_,
            home_name=h, away_name=a,
        )
        ng = live["next_goal"]
        p_no_more = live["p_no_more_goals"]
        p_more = 1 - p_no_more
        p10 = live["p_goal_next_10min"]

        paras: list[str] = []
        headline = f"LIVE {hs}:{as_}, {match.minute}' — темп {live['tempo_label'].split('(')[0].strip()}"

        if blockers:
            paras.append("⚠️ Зараз рекомендації ненадійні: " + "; ".join(blockers)
                         + ". Почекай, поки гра й ринок стабілізуються.")

        # 1. поточний стан + темп
        state = _variant(match.id, [
            f"Рахунок {hs}:{as_} на {match.minute}'. Забито {total} гол(и); за темпом мало бути "
            f"~{live['expected_by_now']} — гра {live['tempo_label']}.",
            f"{match.minute}' зіграно, на табло {hs}:{as_}. Модель чекала до цієї хвилини "
            f"~{live['expected_by_now']} гола, фактично {total} — темп {live['tempo_label']}.",
        ])
        paras.append(state)

        # 2. що попереду
        paras.append(
            f"До кінця ще ~{live['remaining_min']} хв, очікуємо приблизно "
            f"{live['expected_remaining']} гола. Ще хоча б один гол: {_pct(p_more)}; "
            f"рахунок залишиться незмінним: {_pct(p_no_more)}."
        )
        # 3. наступний гол
        paras.append(
            f"Наступний гол найімовірніше за {h if ng['home'] >= ng['away'] else a} "
            f"({h}: {_pct(ng['home'])}, {a}: {_pct(ng['away'])})."
        )
        # 4. найближчі 10 хв
        paras.append(
            f"Гол у наступні 10 хвилин: {_pct(p10)}"
            + (" — найближчим часом радше тихо." if p10 < 0.35
               else " — гра гостра, момент може бути будь-коли." if p10 > 0.55 else ".")
        )

        # ---- на що дивитись ЗАРАЗ (правильно оформлені live-ставки) ----
        ideas: list[str] = []
        if not blockers:
            if ng["home"] - ng["away"] > 0.12:
                ideas.append(f"Наступний гол — {h} (~{_pct(ng['home'])})")
            elif ng["away"] - ng["home"] > 0.12:
                ideas.append(f"Наступний гол — {a} (~{_pct(ng['away'])})")

            if p_no_more >= 0.62:
                ideas.append(f"Більше голів не буде — тотал матчу менше {total + 0.5} "
                             f"(рахунок {hs}:{as_} до кінця, ~{_pct(p_no_more)})")
            elif p_more >= 0.75:
                ideas.append(f"Буде ще гол — тотал матчу більше {total + 0.5} (~{_pct(p_more)})")

            if p10 < 0.30:
                ideas.append("У наступні 10 хв — без голу")
            elif p10 > 0.55:
                ideas.append("Гол у наступні 10 хв — цілком реально")

        if ideas:
            paras.append("На що дивитись зараз: " + "; ".join(ideas) + ".")
            verdict = "Live-ідея: " + ideas[0] + "."
        else:
            verdict = ("Чіткої live-переваги немає"
                       + (" (щойно була подія — дані нестабільні)" if blockers else "")
                       + ".")

        dq_note = (f"Якість даних: {analysis.data_quality.label} "
                   f"({round(analysis.data_quality.score * 100)}%). "
                   + "; ".join(analysis.data_quality.reasons) + ".")

        return {
            "match_id": match.id,
            "match_label": f"{h} — {a}",
            "status": "live",
            "headline": headline,
            "paragraphs": paras,
            "best_bets": [],            # для live доматчеві ставки не показуємо
            "live_suggestions": ideas,
            "traps": [],
            "verdict": verdict,
            "data_quality_note": dq_note,
            "disclaimer": "",
        }

    # ==================== PREMATCH ====================
    def _build_prematch(self, match, analysis, home, away,
                        recent_home=None, recent_away=None) -> dict:
        h, a = match.home.name, match.away.name
        paras: list[str] = []

        p_home = _pred(analysis, "1x2_home")
        p_draw = _pred(analysis, "1x2_draw")
        p_away = _pred(analysis, "1x2_away")
        mh = p_home.model_probability if p_home else 0.34
        md = p_draw.model_probability if p_draw else 0.33
        ma = p_away.model_probability if p_away else 0.33
        gap = abs(mh - ma)

        if mh - ma > 0.22:
            fav, headline = h, f"Явний фаворит — господарі ({h})"
        elif ma - mh > 0.22:
            fav, headline = a, f"Явний фаворит — гості ({a})"
        elif mh - ma > 0.10:
            fav, headline = h, f"Невеликий фаворит — господарі ({h})"
        elif ma - mh > 0.10:
            fav, headline = a, f"Невеликий фаворит — гості ({a})"
        else:
            fav, headline = None, "Рівний матч без явного фаворита"

        intro = _variant(match.id, [
            f"Ймовірності за моделлю: {h} — {_pct(mh)}, нічия — {_pct(md)}, {a} — {_pct(ma)}.",
            f"Наш розрахунок дає: перемога {h} {_pct(mh)}, X {_pct(md)}, перемога {a} {_pct(ma)}.",
        ])
        # порівняння з коефіцієнтами
        odds_bits = []
        if p_home and p_home.decimal_odds:
            odds_bits.append((h, p_home.decimal_odds))
        if p_away and p_away.decimal_odds:
            odds_bits.append((a, p_away.decimal_odds))
        if len(odds_bits) == 2:
            fav_odds = min(odds_bits, key=lambda x: x[1])
            intro += f" Букмекер фаворитом бачить {fav_odds[0]} (коеф {fav_odds[1]:.2f})."
            if fav and fav_odds[0] == fav:
                intro += " Модель і букмекер збігаються — сигнал міцніший."
            elif fav and fav_odds[0] != fav:
                intro += " Модель і букмекер розходяться — обережніше."
        paras.append(headline + ". " + intro)

        # як зіграли останні матчі (реальні результати)
        rh = _describe_recent(h, recent_home or [])
        ra = _describe_recent(a, recent_away or [])
        if rh:
            paras.append(rh)
        if ra:
            paras.append(ra)

        # форма й голи
        if home and away:
            paras.append(f"Форма: {h} — {_form_readable(home.form)}; {a} — {_form_readable(away.form)}.")
            if home.goals_for_avg is not None and away.goals_for_avg is not None:
                paras.append(
                    f"{h}: {home.goals_for_avg:.2f} забитих / {home.goals_against_avg:.2f} пропущених; "
                    f"{a}: {away.goals_for_avg:.2f} / {away.goals_against_avg:.2f}. "
                    f"Очікуваний рахунок ≈ {analysis.expected_home_goals:.1f} : "
                    f"{analysis.expected_away_goals:.1f}."
                )

        # тотал
        total = analysis.expected_home_goals + analysis.expected_away_goals
        over25 = _pred(analysis, "over_2.5")
        under25 = _pred(analysis, "under_2.5")
        if over25 and total >= 2.8:
            paras.append(f"Голів очікується багато (~{total:.1f}). «Тотал більше 2.5» — "
                         f"{_pct(over25.model_probability)}.")
        elif under25 and total <= 2.2:
            paras.append(f"Матч радше «низовий» (~{total:.1f} гола). «Тотал менше 2.5» — "
                         f"{_pct(under25.model_probability)}.")
        elif over25:
            paras.append(f"Тотал очікується середній (~{total:.1f}) — без чіткого перекосу.")

        # обидві заб'ють
        btts = _pred(analysis, "btts_yes")
        if btts and btts.model_probability >= 0.58:
            paras.append(f"Атаки активні — «обидві заб'ють: Так» {_pct(btts.model_probability)}.")
        elif btts and btts.model_probability <= 0.42:
            paras.append(f"Схоже на «суху» гру однієї зі сторін — «обидві заб'ють: Ні» "
                         f"{_pct(1 - btts.model_probability)}.")

        # глибші фактори
        factors = deep_factors(home, away, h, a)
        if factors:
            paras.append("Фактори: " + " ".join(factors))

        # найкращі ставки + Келлі + попередження
        min_sample = min(home.sample_size(), away.sample_size()) if (home and away) else 0
        best = [p for p in analysis.predictions
                if p.decimal_odds is not None and p.ev is not None and p.ev > 0 and p.confidence >= 5.5]
        best = sorted(best, key=lambda p: (p.confidence, p.ev or 0), reverse=True)[:3]
        best_bets = []
        for p in best:
            best_bets.append({
                "selection": p.selection, "decimal_odds": p.decimal_odds,
                "model_probability": p.model_probability, "confidence": p.confidence,
                "ev": p.ev, "risk": p.risk,
                "reason": p.args_for[0] if p.args_for else "статистична перевага моделі",
                "kelly_pct": round(kelly_fraction(p.model_probability, p.decimal_odds) * 100, 1),
                "warnings": detect_traps(p, analysis.data_quality.score, min_sample),
            })

        # пастки
        traps = []
        for p in analysis.predictions:
            if p.decimal_odds is None or p.ev is None or p.ev <= 0.3:
                continue
            w = detect_traps(p, analysis.data_quality.score, min_sample)
            if w:
                traps.append({"selection": p.selection, "decimal_odds": p.decimal_odds,
                              "ev": p.ev, "warnings": w})
        if traps:
            names = ", ".join(f"«{t['selection']}»" for t in traps[:3])
            paras.append(f"⚠️ Можливі пастки: {names} — виглядають надто вигідно. Двічі подумай.")

        # вердикт (сухо, без «порад» — лише висновок аналізу)
        if analysis.skip_recommended or not best_bets:
            verdict = _variant(match.id, [
                "Value не знайдено: жодна ставка не має переваги над коефіцієнтами.",
                "Статистичної переваги немає — модель не бачить value на цьому матчі.",
            ])
        else:
            top = best_bets[0]
            verdict = (f"Найсильніший варіант: «{top['selection']}» @ {top['decimal_odds']:.2f} "
                       f"(впевненість {top['confidence']}/10, розмір за Келлі ~{top['kelly_pct']}% банку).")

        dq_note = (f"Якість даних: {analysis.data_quality.label} "
                   f"({round(analysis.data_quality.score * 100)}%). "
                   + "; ".join(analysis.data_quality.reasons) + ".")
        if analysis.data_quality.score < 0.45:
            dq_note += " Даних мало — довіряй прогнозу обережно."

        return {
            "match_id": match.id,
            "match_label": f"{h} — {a}",
            "status": match.status.value,
            "headline": headline,
            "paragraphs": paras,
            "best_bets": best_bets,
            "live_suggestions": [],
            "traps": traps,
            "verdict": verdict,
            "data_quality_note": dq_note,
            "disclaimer": "",
        }
