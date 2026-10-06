"""The Odds API clients: lean, valid requests; ESPN keeps the schedule; a bad request is not an empty quota."""
import json

import pytest


def test_odds_window_covers_the_next_hours():
    from datetime import datetime
    from sports_common.odds_api import odds_window_params
    w = odds_window_params(36)
    start, end = (datetime.strptime(w[k], "%Y-%m-%dT%H:%M:%SZ") for k in ("commenceTimeFrom", "commenceTimeTo"))
    assert (end - start).total_seconds() == 36 * 3600


def test_priced_matches_reprice_espn_fixtures_and_unknown_ones_are_kept():
    from football_core.data.odds_api import merge_odds
    espn = [{"home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-10-04", "odds_home": 2.1, "odds_over25": 1.8,
             "bookmaker": "DraftKings (ESPN)", "referee": "M Oliver"},
            {"home_team": "Everton", "away_team": "Fulham", "date": "2026-10-11", "odds_home": 2.5}]
    priced = [{"home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-10-05", "odds_home": 2.05, "odds_over25": None,
               "bookmaker": "The Odds API (European median)", "bookmakers_count": 9},
              {"home_team": "Leeds", "away_team": "Wolves", "date": "2026-10-04", "odds_home": 1.9}]
    merged = merge_odds(espn, priced)
    assert merged[0]["odds_home"] == 2.05 and merged[0]["bookmakers_count"] == 9
    assert merged[0]["odds_over25"] == 1.8  # a market The Odds API did not price keeps ESPN's price
    assert merged[0]["referee"] == "M Oliver"  # ESPN-only fields survive
    assert merged[1]["odds_home"] == 2.5  # outside the odds window: untouched
    assert [m["home_team"] for m in merged] == ["Arsenal", "Everton", "Leeds"]


class _Resp:
    def __init__(self, status, remaining):
        self.status_code, self.headers = status, {"x-requests-remaining": remaining, "x-requests-used": "45"}


@pytest.mark.parametrize("status,ok", [(422, True), (200, True), (401, False), (429, False)])
def test_only_key_or_quota_errors_mark_the_quota_unusable(tmp_path, monkeypatch, status, ok):
    from football_core.data import odds_api
    monkeypatch.setattr(odds_api, "QUOTA_FILE", tmp_path / "quota.json")
    odds_api.save_quota_headers(_Resp(status, "455"))
    stored = json.loads((tmp_path / "quota.json").read_text())
    assert stored["ok"] is ok and odds_api._quota_exhausted() is (not ok)


def test_football_requests_only_supported_markets(monkeypatch):
    from football_core.data import odds_api
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen.update(params)
        return type("R", (), {"status_code": 200, "headers": {}, "json": lambda self: []})()
    monkeypatch.setattr(odds_api.requests, "get", fake_get)
    monkeypatch.setattr(odds_api, "save_quota_headers", lambda resp: None)
    assert odds_api._odds_api_matches("EPL", {"name": "Premier League", "flag": "x"}, "soccer_epl", "k" * 32) == []
    assert set(seen["markets"].split(",")) == {"h2h", "totals"} and seen["regions"] == "eu"
    assert "commenceTimeTo" in seen


def test_espn_falls_back_to_daily_queries_when_the_range_finds_nothing_upcoming(monkeypatch):
    from football_core.data import espn_client
    def event(eid, completed, date="2026-10-06T18:45Z"):
        team = lambda name, side: {"homeAway": side, "team": {"displayName": name}}
        return {"id": eid, "date": date, "competitions": [{"status": {"type": {"completed": completed}},
                "competitors": [team(f"Home{eid}", "home"), team(f"Away{eid}", "away")]}]}
    calls = []

    def fake_get(url, params=None):
        calls.append(params)
        if params is None:  # default scoreboard: last matchday, already played
            return {"events": [event("old", True)]}
        if "-" in params["dates"]:  # range query: ESPN returns nothing for this competition
            return {"events": []}
        return {"events": [event("today", False)]} if params["dates"].endswith("06") else {"events": []}

    monkeypatch.setattr(espn_client, "_espn_get_json", fake_get)
    monkeypatch.setattr(espn_client, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: __import__("datetime").datetime(2026, 10, 6, 8, tzinfo=tz))}))
    fixtures = espn_client.fetch_espn_upcoming_fixtures("NationsLeague")
    assert [f["home_team"] for f in fixtures] == ["Hometoday"]
    assert sum(1 for p in calls if p and "-" not in p["dates"]) == 14  # two weeks, day by day
