"""MockSportsDataProvider — детерміновані демо-дані без жодного API.

УВАГА: усі дані тут згенеровані штучно й позначені is_mock=True. Вони НЕ є
реальною спортивною статистикою і призначені лише для тестування інтерфейсу
та логіки аналізу.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from ..models.domain import Match, MatchStatus, Team, TeamStats
from .base import SportsProvider


# Ліги: (id, назва, країна, сезон, чи популярна)
_LEAGUES = [
    (1, "Premier League", "England", "2025/2026", True),
    (2, "La Liga", "Spain", "2025/2026", True),
    (3, "Serie A", "Italy", "2025/2026", True),
    (4, "Bundesliga", "Germany", "2025/2026", True),
    (5, "Ligue 1", "France", "2025/2026", False),
    (6, "Premier League (UA)", "Ukraine", "2025/2026", False),
]

# Команди на лігу з базовими рейтингами (attack, defense) у голах за матч.
_TEAMS: dict[int, list[tuple[str, float, float]]] = {
    1: [
        ("Manchester City", 2.25, 0.95), ("Arsenal", 2.05, 0.90),
        ("Liverpool", 2.10, 1.05), ("Chelsea", 1.80, 1.15),
        ("Tottenham", 1.90, 1.30), ("Newcastle", 1.70, 1.20),
        ("Aston Villa", 1.65, 1.25), ("Brighton", 1.55, 1.30),
    ],
    2: [
        ("Real Madrid", 2.20, 0.90), ("Barcelona", 2.15, 1.00),
        ("Atletico Madrid", 1.75, 0.85), ("Girona", 1.80, 1.25),
        ("Athletic Bilbao", 1.55, 1.05), ("Real Sociedad", 1.50, 1.10),
        ("Valencia", 1.30, 1.30), ("Sevilla", 1.35, 1.25),
    ],
    3: [
        ("Inter", 2.10, 0.85), ("Juventus", 1.75, 0.90),
        ("AC Milan", 1.85, 1.10), ("Napoli", 1.80, 1.05),
        ("Atalanta", 1.95, 1.15), ("Roma", 1.65, 1.10),
        ("Lazio", 1.55, 1.05), ("Torino", 1.25, 1.05),
    ],
    4: [
        ("Bayern Munich", 2.35, 1.00), ("Bayer Leverkusen", 2.05, 0.95),
        ("RB Leipzig", 1.90, 1.10), ("Borussia Dortmund", 1.95, 1.25),
        ("Stuttgart", 1.80, 1.20), ("Eintracht Frankfurt", 1.60, 1.30),
        ("Freiburg", 1.45, 1.25), ("Wolfsburg", 1.40, 1.30),
    ],
    5: [
        ("PSG", 2.40, 0.85), ("Monaco", 1.85, 1.15),
        ("Marseille", 1.70, 1.20), ("Lille", 1.60, 1.05),
        ("Lyon", 1.55, 1.20), ("Nice", 1.45, 1.00),
        ("Lens", 1.50, 1.15), ("Rennes", 1.55, 1.25),
    ],
    6: [
        ("Shakhtar Donetsk", 2.00, 1.00), ("Dynamo Kyiv", 1.85, 1.05),
        ("Zorya Luhansk", 1.35, 1.25), ("Dnipro-1", 1.40, 1.20),
        ("Vorskla", 1.20, 1.35), ("Kryvbas", 1.30, 1.30),
    ],
}


def _rand(seed: str) -> float:
    """Детермінований псевдо-random у [0,1) з рядка-сіда."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _jitter(seed: str, spread: float) -> float:
    return (_rand(seed) - 0.5) * 2 * spread  # у [-spread, spread]


class MockSportsDataProvider(SportsProvider):
    name = "mock_sports"
    is_mock = True

    def __init__(self, today: date | None = None) -> None:
        self._today = today or datetime.now().date()
        self._teams: dict[int, Team] = {}
        self._team_league: dict[int, int] = {}
        self._team_rating: dict[int, tuple[float, float]] = {}
        self._matches: dict[int, Match] = {}
        self._build_teams()
        self._build_matches()

    # ---- побудова каталогу ----
    def _build_teams(self) -> None:
        tid = 100
        for league_id, teams in _TEAMS.items():
            country = next(l[2] for l in _LEAGUES if l[0] == league_id)
            for name, atk, dfn in teams:
                self._teams[tid] = Team(id=tid, name=name, country=country)
                self._team_league[tid] = league_id
                self._team_rating[tid] = (atk, dfn)
                tid += 1

    def _teams_of_league(self, league_id: int) -> list[int]:
        return [tid for tid, lg in self._team_league.items() if lg == league_id]

    def _build_matches(self) -> None:
        now = datetime.now()
        for league_id, (_, lname, country, season, popular) in {
            l[0]: l for l in _LEAGUES
        }.items():
            team_ids = self._teams_of_league(league_id)
            n = len(team_ids)
            for day_offset in range(0, 8):  # сьогодні .. +7 днів
                match_day = self._today + timedelta(days=day_offset)
                # Ротаційне парування, щоб склад турів різнився за днями.
                rot = day_offset % max(1, n // 2)
                pairs = []
                for k in range(n // 2):
                    home = team_ids[(k + rot) % n]
                    away = team_ids[(n - 1 - k + rot) % n]
                    if home != away:
                        pairs.append((home, away))
                # Беремо максимум 3 матчі на лігу на день.
                for idx, (home_id, away_id) in enumerate(pairs[:3]):
                    match_id = league_id * 10000 + day_offset * 100 + idx
                    hour = 14 + (idx * 2) + (league_id % 3)
                    kickoff = datetime(match_day.year, match_day.month, match_day.day,
                                       min(hour, 21), 0)
                    status, hs, as_, minute = self._match_state(match_id, kickoff, now,
                                                                home_id, away_id)
                    self._matches[match_id] = Match(
                        id=match_id,
                        home=self._teams[home_id],
                        away=self._teams[away_id],
                        league=lname,
                        country=country,
                        season=season,
                        kickoff=kickoff,
                        status=status,
                        home_score=hs,
                        away_score=as_,
                        minute=minute,
                        is_popular=popular and idx == 0,
                    )

    def _match_state(self, match_id, kickoff, now, home_id, away_id):
        delta_min = (now - kickoff).total_seconds() / 60.0
        atk_h, _ = self._team_rating[home_id]
        atk_a, _ = self._team_rating[away_id]
        if delta_min < 0:
            return MatchStatus.SCHEDULED, None, None, None
        if delta_min > 115:
            # завершений
            hs = int(round(atk_h * (0.8 + _rand(f"{match_id}-hs"))))
            as_ = int(round(atk_a * (0.7 + _rand(f"{match_id}-as"))))
            return MatchStatus.FINISHED, hs, as_, None
        # у грі
        minute = int(min(90, delta_min))
        prog = minute / 90.0
        hs = int(round(atk_h * prog * (0.7 + _rand(f"{match_id}-lhs"))))
        as_ = int(round(atk_a * prog * (0.6 + _rand(f"{match_id}-las"))))
        return MatchStatus.LIVE, hs, as_, minute

    # ---- інтерфейс ----
    def list_matches(self, day_from: date, day_to: date) -> list[Match]:
        out = [
            m for m in self._matches.values()
            if day_from <= m.kickoff.date() <= day_to
        ]
        out.sort(key=lambda m: m.kickoff)
        return out

    def get_match(self, match_id: int) -> Match | None:
        return self._matches.get(match_id)

    def get_team_stats(self, team_id: int) -> TeamStats | None:
        if team_id not in self._team_rating:
            return None
        atk, dfn = self._team_rating[team_id]
        league_id = self._team_league[team_id]

        # Кілька команд навмисно мають малу вибірку -> низька якість даних.
        low_sample = (team_id % 7 == 0)
        mp = 4 if low_sample else 20

        gf = atk + _jitter(f"{team_id}-gf", 0.12)
        ga = dfn + _jitter(f"{team_id}-ga", 0.12)

        # позиція в лізі за силою (attack - defense)
        rank = sorted(
            self._teams_of_league(league_id),
            key=lambda t: (self._team_rating[t][0] - self._team_rating[t][1]),
            reverse=True,
        )
        position = rank.index(team_id) + 1

        strength = atk - dfn
        form = self._form_string(team_id, strength, low_sample)

        return TeamStats(
            team_id=team_id,
            matches_played=mp,
            form=form,
            home_form=form[:3],
            away_form=form[2:5],
            goals_for_avg=round(gf, 2),
            goals_against_avg=round(ga, 2),
            home_goals_for_avg=round(gf * 1.15, 2),
            home_goals_against_avg=round(ga * 0.90, 2),
            away_goals_for_avg=round(gf * 0.88, 2),
            away_goals_against_avg=round(ga * 1.12, 2),
            xg_avg=None if low_sample else round(gf * (1.0 + _jitter(f"{team_id}-xg", 0.08)), 2),
            xga_avg=None if low_sample else round(ga * (1.0 + _jitter(f"{team_id}-xga", 0.08)), 2),
            shots_avg=round(10 + atk * 3, 1),
            shots_on_target_avg=round(3.5 + atk * 1.5, 1),
            corners_avg=round(4.5 + atk, 1),
            cards_avg=round(1.8 + _rand(f"{team_id}-cards"), 1),
            possession_avg=round(45 + strength * 8, 1),
            clean_sheets_ratio=round(max(0.05, 0.5 - dfn * 0.2), 2),
            btts_ratio=round(min(0.85, 0.35 + gf * 0.15), 2),
            league_position=position,
            rest_days=3 + (team_id % 4),
        )

    def _form_string(self, team_id, strength, low_sample) -> str:
        n = 5 if not low_sample else 3
        chars = []
        for i in range(n):
            r = _rand(f"{team_id}-form-{i}")
            # сильніші команди частіше виграють
            win_p = 0.5 + strength * 0.18
            if r < win_p:
                chars.append("W")
            elif r < win_p + 0.25:
                chars.append("D")
            else:
                chars.append("L")
        return "".join(chars)

    def list_leagues(self) -> list[dict]:
        return [
            {"id": lid, "name": name, "country": country, "season": season, "popular": popular}
            for (lid, name, country, season, popular) in _LEAGUES
        ]

    def get_recent_results(self, team_id: int, last: int = 5) -> list[dict]:
        if team_id not in self._team_rating:
            return []
        atk, dfn = self._team_rating[team_id]
        league_id = self._team_league[team_id]
        others = [t for t in self._teams_of_league(league_id) if t != team_id]
        out = []
        for i in range(last):
            opp = others[(team_id + i) % len(others)]
            o_atk, o_dfn = self._team_rating[opp]
            is_home = (team_id + i) % 2 == 0
            gf = int(round((atk if is_home else atk * 0.9) * (0.6 + _rand(f"{team_id}-r{i}-gf"))))
            ga = int(round(o_atk * (0.5 + _rand(f"{team_id}-r{i}-ga"))))
            res = "W" if gf > ga else "D" if gf == ga else "L"
            out.append({
                "opponent": self._teams[opp].name,
                "is_home": is_home,
                "gf": gf, "ga": ga, "result": res,
            })
        return out
