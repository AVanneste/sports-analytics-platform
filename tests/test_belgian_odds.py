"""Belgian prices (Kambi: Unibet.be, Bingoal) and Pinnacle as a reference."""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Kambi parsing
def test_kambi_bet_offers_map_to_our_fields():
    from football_core.data.kambi import parse_bet_offers
    odds = parse_bet_offers(_load("kambi_betoffers.json")["betOffers"])
    assert odds == {"odds_home": 1.91, "odds_draw": 3.7, "odds_away": 4.1, "odds_over25": 1.74, "odds_under25": 2.05,
                    "odds_btts_yes": 1.63, "odds_btts_no": 2.12, "odds_corners_over95": 1.68, "odds_corners_under95": 2.0}


def test_kambi_markets_need_every_side_open():
    from football_core.data.kambi import parse_bet_offers
    offer = {"criterion": {"label": "Full Time"}, "betOfferType": {"name": "Match"},
             "outcomes": [{"type": "OT_ONE", "odds": 1900}, {"type": "OT_CROSS", "odds": 3500, "status": "SUSPENDED"},
                          {"type": "OT_TWO", "odds": 4000}]}
    assert parse_bet_offers([offer]) == {}


def test_kambi_list_view_keeps_upcoming_matches():
    from football_core.data.kambi import parse_list_view
    matches = parse_list_view(_load("kambi_listview.json"))
    assert [(m["home_team"], m["away_team"]) for m in matches] == [("SK Beveren", "Lommel SK"), ("Cercle Brugge", "Anderlecht")]
    assert matches[0]["odds"]["odds_home"] == 1.91 and matches[0]["start"] == "2026-10-09T18:45:00Z"
    live = {"events": [{"event": {**_load("kambi_listview.json")["events"][0]["event"], "state": "STARTED"}, "betOffers": []}]}
    assert parse_list_view(live) == []


def test_best_price_is_taken_per_selection():
    from football_core.data.kambi import best_prices
    assert best_prices({"unibet": {"odds_home": 1.91, "odds_draw": 3.7}, "bingoal": {"odds_home": 1.87, "odds_draw": 3.75}}) \
        == {"odds_home": 1.91, "odds_draw": 3.75}


# ------------------------------------------------------------------ merging into fixtures
def _event(home, away, start="2026-10-09T18:45:00Z", league="Belgium", event_id=1):
    return {"event_id": event_id, "league": league, "start": start, "home_team": home, "away_team": away,
            "books": {"unibet": {"odds_home": 1.91, "odds_draw": 3.7, "odds_away": 4.1},
                      "bingoal": {"odds_home": 1.87, "odds_draw": 3.75, "odds_away": 3.95, "odds_btts_yes": 1.6}}}


def test_kambi_names_match_our_fixtures_within_league_and_day():
    from football_core.data.kambi import match_event
    fixtures = [{"league": "Belgium", "date": "2026-10-09", "home_team": "Genk", "away_team": "Gent"},
                {"league": "Belgium", "date": "2026-10-09", "home_team": "Waasland-Beveren", "away_team": "Lommel SK"},
                {"league": "Belgium", "date": "2026-10-10", "home_team": "St Truiden", "away_team": "Standard"},
                {"league": "Eredivisie", "date": "2026-10-09", "home_team": "Beveren", "away_team": "Lommel"}]
    assert match_event(_event("SK Beveren", "Lommel SK"), fixtures) == 1
    assert match_event(_event("Sint-Truiden", "Standard de Liège", start="2026-10-10T14:00:00Z"), fixtures) == 2
    assert match_event(_event("Club Brugge", "Anderlecht"), fixtures) is None  # not one of our fixtures


def test_belgian_price_replaces_the_fixture_price_and_keeps_the_old_one_as_reference():
    from football_core.data.kambi import BOOKMAKER_LABEL, merge_belgian_prices
    fixtures = [{"league": "Belgium", "date": "2026-10-09", "home_team": "Waasland-Beveren", "away_team": "Lommel SK",
                 "odds_home": 1.8, "odds_draw": 3.75, "odds_away": 3.9, "odds_over25": 1.7, "bookmaker": "DraftKings (ESPN)",
                 "reference_odds": {"pinnacle": {"odds_home": 1.85}}}]
    assert merge_belgian_prices(fixtures, [_event("SK Beveren", "Lommel SK", event_id=77)]) == 1
    f = fixtures[0]
    assert (f["odds_home"], f["odds_draw"], f["odds_away"], f["odds_btts_yes"]) == (1.91, 3.75, 4.1, 1.6)
    assert f["odds_over25"] == 1.7  # no Belgian price for it: the earlier price stays
    assert f["bookmaker"] == BOOKMAKER_LABEL and f["kambi_event_id"] == 77
    assert f["reference_odds"]["eu"]["odds_home"] == 1.8 and f["reference_odds"]["eu"]["bookmaker"] == "DraftKings (ESPN)"
    assert f["reference_odds"]["pinnacle"] == {"odds_home": 1.85}


# ------------------------------------------------------------------ Pinnacle via The Odds API
def test_pinnacle_prices_are_kept_beside_the_european_median(monkeypatch):
    from football_core.data import odds_api
    book = lambda key, h, d, a, o, u: {"key": key, "markets": [
        {"key": "h2h", "outcomes": [{"name": "Arsenal", "price": h}, {"name": "Draw", "price": d}, {"name": "Chelsea", "price": a}]},
        {"key": "totals", "outcomes": [{"name": "Over", "point": 2.5, "price": o}, {"name": "Under", "point": 2.5, "price": u}]}]}
    payload = [{"id": "x", "home_team": "Arsenal", "away_team": "Chelsea", "commence_time": "2026-10-10T14:00:00Z",
                "bookmakers": [book("pinnacle", 2.05, 3.6, 3.9, 1.95, 1.95), book("unibet", 2.0, 3.5, 3.7, 1.9, 1.9),
                               book("betclic", 1.95, 3.4, 3.6, 1.85, 1.95)]}]
    monkeypatch.setattr(odds_api.requests, "get", lambda *a, **k: type("R", (), {"status_code": 200, "headers": {}, "json": lambda self: payload})())
    monkeypatch.setattr(odds_api, "save_quota_headers", lambda resp: None)
    m = odds_api._odds_api_matches("EPL", {"name": "Premier League", "flag": "x"}, "soccer_epl", "k" * 32)[0]
    assert m["odds_home"] == 2.0  # median
    assert m["reference_odds"]["pinnacle"] == {"odds_home": 2.05, "odds_draw": 3.6, "odds_away": 3.9,
                                               "odds_over25": 1.95, "odds_under25": 1.95}
    merged = odds_api.merge_odds([{"home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-10-10"}], [m])
    assert merged[0]["reference_odds"]["pinnacle"]["odds_home"] == 2.05
