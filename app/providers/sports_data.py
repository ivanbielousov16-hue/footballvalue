"""SportsDataProvider — реальний провайдер даних на основі API-Football (v3).

Активується, коли задано ключ FV_API_FOOTBALL_KEY. Підтримує два способи доступу:
  * "apisports" — прямий доступ (v3.football.api-sports.io, заголовок x-apisports-key)
  * "rapidapi"  — через RapidAPI (api-football-v1.p.rapidapi.com)

Провайдер отримує:
  * розклад матчів (fixtures) із рахунком/статусом/хвилиною;
  * статистику команд (форма, зіграні матчі, середні забиті/пропущені total/home/away,
    «сухі» матчі) через /teams/statistics;
  * позицію в таблиці через /standings.

xG/удари/кутики у стандартному /teams/statistics відсутні — вони лишаються None,
і аналіз чесно це враховує (не вигадуємо відсутню статистику).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import httpx

from ..models.domain import Match, MatchStatus, Team, TeamStats
from .base import SportsProvider

_STATUS_MAP = {
    "NS": MatchStatus.SCHEDULED, "TBD": MatchStatus.SCHEDULED,
    "1H": MatchStatus.LIVE, "2H": MatchStatus.LIVE, "ET": MatchStatus.LIVE,
    "P": MatchStatus.LIVE, "LIVE": MatchStatus.LIVE, "INT": MatchStatus.LIVE,
    "HT": MatchStatus.PAUSED, "BREAK": MatchStatus.PAUSED, "SUSP": MatchStatus.PAUSED,
    "FT": MatchStatus.FINISHED, "AET": MatchStatus.FINISHED, "PEN": MatchStatus.FINISHED,
    "PST": MatchStatus.POSTPONED, "CANC": MatchStatus.POSTPONED, "ABD": MatchStatus.POSTPONED,
}


def _f(value) -> Optional[float]:
    """Безпечне перетворення значення (часто рядок) у float."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class SportsDataProvider(SportsProvider):
    name = "api_football"
    is_mock = False

    def __init__(self, api_key: str, host: str = "apisports",
                 default_season: int = 0, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.host = host
        self.available = bool(api_key)
        self.default_season = default_season
        self._timeout = timeout

        if host == "rapidapi":
            self._base = "https://api-football-v1.p.rapidapi.com/v3"
            self._headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
            }
        else:
            self._base = "https://v3.football.api-sports.io"
            self._headers = {"x-apisports-key": api_key}

        # кеші
        self._fixtures: dict[int, Match] = {}
        self._team_ctx: dict[int, tuple[int, int]] = {}   # team_id -> (league_id, season)
        self._stats_cache: dict[tuple[int, int, int], Optional[TeamStats]] = {}
        self._standings_cache: dict[tuple[int, int], dict[int, int]] = {}

    # ---------- низькорівневий запит ----------
    def _get(self, path: str, params: dict) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(f"{self._base}{path}", headers=self._headers, params=params)
            resp.raise_for_status()
            return resp.json()

    def account_status(self) -> dict:
        """Діагностика підписки (для тесту з'єднання)."""
        return self._get("/status", {})

    # ---------- fixtures ----------
    def _parse_fixture(self, item: dict) -> Match:
        fx = item["fixture"]
        teams = item["teams"]
        league = item["league"]
        goals = item.get("goals", {})
        kickoff = datetime.fromisoformat(fx["date"].replace("Z", "+00:00"))
        status_short = fx.get("status", {}).get("short", "NS")
        league_id = int(league.get("id", 0))
        season = int(league.get("season", 0) or self.default_season or kickoff.year)

        home_id = int(teams["home"]["id"])
        away_id = int(teams["away"]["id"])
        # запам'ятовуємо контекст ліги/сезону для отримання статистики
        self._team_ctx[home_id] = (league_id, season)
        self._team_ctx[away_id] = (league_id, season)

        match = Match(
            id=int(fx["id"]),
            home=Team(id=home_id, name=teams["home"]["name"], country=league.get("country", "")),
            away=Team(id=away_id, name=teams["away"]["name"], country=league.get("country", "")),
            league=league.get("name", ""),
            country=league.get("country", ""),
            season=str(season),
            kickoff=kickoff,
            status=_STATUS_MAP.get(status_short, MatchStatus.SCHEDULED),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            minute=fx.get("status", {}).get("elapsed"),
            is_popular=False,
        )
        self._fixtures[match.id] = match
        return match

    def list_matches(self, day_from: date, day_to: date) -> list[Match]:
        if not self.available:
            return []
        matches: list[Match] = []
        cur = day_from
        while cur <= day_to:
            try:
                data = self._get("/fixtures", {"date": cur.isoformat()})
                for item in data.get("response", []):
                    matches.append(self._parse_fixture(item))
            except Exception:
                pass  # не валимо весь запит через одну невдалу дату/ліміт
            cur = date.fromordinal(cur.toordinal() + 1)
        matches.sort(key=lambda m: m.kickoff)
        return matches

    def get_live_matches(self) -> list[Match]:
        """Усі матчі, що йдуть ЗАРАЗ — одним дешевим запитом (/fixtures?live=all)."""
        if not self.available:
            return []
        try:
            data = self._get("/fixtures", {"live": "all"})
        except Exception:
            return []
        out = [self._parse_fixture(item) for item in data.get("response", [])]
        out.sort(key=lambda m: m.kickoff)
        return out

    def get_match(self, match_id: int) -> Match | None:
        if match_id in self._fixtures:
            return self._fixtures[match_id]
        if not self.available:
            return None
        data = self._get("/fixtures", {"id": match_id})
        resp = data.get("response", [])
        return self._parse_fixture(resp[0]) if resp else None

    # ---------- standings ----------
    def _league_positions(self, league_id: int, season: int) -> dict[int, int]:
        key = (league_id, season)
        if key in self._standings_cache:
            return self._standings_cache[key]
        positions: dict[int, int] = {}
        try:
            data = self._get("/standings", {"league": league_id, "season": season})
            resp = data.get("response", [])
            if resp:
                groups = resp[0]["league"]["standings"]
                for group in groups:
                    for row in group:
                        positions[int(row["team"]["id"])] = int(row["rank"])
        except Exception:
            pass
        self._standings_cache[key] = positions
        return positions

    # ---------- team statistics ----------
    def get_team_stats(self, team_id: int) -> TeamStats | None:
        if not self.available:
            return None
        ctx = self._team_ctx.get(team_id)
        if ctx is None:
            # без контексту ліги/сезону статистику отримати не можна
            return None
        league_id, season = ctx
        cache_key = (team_id, league_id, season)
        if cache_key in self._stats_cache:
            return self._stats_cache[cache_key]

        stats: Optional[TeamStats] = None
        try:
            data = self._get("/teams/statistics",
                             {"team": team_id, "league": league_id, "season": season})
            resp = data.get("response")
            if resp:
                stats = self._parse_team_stats(team_id, resp, league_id, season)
        except Exception:
            stats = None

        self._stats_cache[cache_key] = stats
        return stats

    def _parse_team_stats(self, team_id: int, r: dict, league_id: int, season: int) -> TeamStats:
        fixtures = r.get("fixtures", {})
        played = fixtures.get("played", {})
        played_total = int(played.get("total") or 0)
        played_home = int(played.get("home") or 0)
        played_away = int(played.get("away") or 0)

        goals = r.get("goals", {})
        gf_avg = goals.get("for", {}).get("average", {})
        ga_avg = goals.get("against", {}).get("average", {})

        clean = r.get("clean_sheet", {})
        clean_total = int(clean.get("total") or 0)

        form = (r.get("form") or "")
        # API-Football: форма у хронологічному порядку (старіші ліворуч) —
        # беремо останні матчі й показуємо найновіші ліворуч.
        form_recent = form[-10:][::-1]

        positions = self._league_positions(league_id, season)

        return TeamStats(
            team_id=team_id,
            matches_played=played_total,
            form=form_recent,
            home_form=form_recent[:5],
            away_form=form_recent[:5],
            goals_for_avg=_f(gf_avg.get("total")),
            goals_against_avg=_f(ga_avg.get("total")),
            home_goals_for_avg=_f(gf_avg.get("home")),
            home_goals_against_avg=_f(ga_avg.get("home")),
            away_goals_for_avg=_f(gf_avg.get("away")),
            away_goals_against_avg=_f(ga_avg.get("away")),
            xg_avg=None,   # немає у стандартному /teams/statistics
            xga_avg=None,
            shots_avg=None,
            shots_on_target_avg=None,
            corners_avg=None,
            cards_avg=None,
            possession_avg=None,
            clean_sheets_ratio=round(clean_total / played_total, 3) if played_total else None,
            btts_ratio=None,
            league_position=positions.get(team_id),
            rest_days=None,
        )

    # ---------- leagues ----------
    def get_recent_results(self, team_id: int, last: int = 5) -> list[dict]:
        if not self.available:
            return []
        try:
            data = self._get("/fixtures", {"team": team_id, "last": last})
        except Exception:
            return []
        out = []
        for item in data.get("response", []):
            teams = item.get("teams", {})
            goals = item.get("goals", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            is_home = bool(home.get("id") == team_id)
            gh = goals.get("home")
            ga = goals.get("away")
            if gh is None or ga is None:
                continue
            gf, gag = (gh, ga) if is_home else (ga, gh)
            opponent = (away if is_home else home).get("name", "")
            res = "W" if gf > gag else "D" if gf == gag else "L"
            out.append({"opponent": opponent, "is_home": is_home,
                        "gf": gf, "ga": gag, "result": res})
        return out

    def list_leagues(self) -> list[dict]:
        if not self.available:
            return []
        data = self._get("/leagues", {"current": "true"})
        out = []
        for item in data.get("response", []):
            lg = item["league"]
            country = item.get("country", {}).get("name", "")
            seasons = item.get("seasons", [])
            season = seasons[-1]["year"] if seasons else ""
            out.append({"id": lg["id"], "name": lg["name"], "country": country,
                        "season": str(season), "popular": False})
        return out
