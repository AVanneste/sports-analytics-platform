"""Belgian prices (Napoleon via Superbet, Unibet.be and Bingoal via Kambi), Pinnacle as a reference,
and closing prices for CLV."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
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
    from football_core.data.kambi import merge_belgian_prices
    fixtures = [{"league": "Belgium", "date": "2026-10-09", "home_team": "Waasland-Beveren", "away_team": "Lommel SK",
                 "odds_home": 1.8, "odds_draw": 3.75, "odds_away": 3.9, "odds_over25": 1.7, "bookmaker": "DraftKings (ESPN)",
                 "reference_odds": {"pinnacle": {"odds_home": 1.85}}}]
    assert merge_belgian_prices(fixtures, [_event("SK Beveren", "Lommel SK", event_id=77)]) == 1
    f = fixtures[0]
    assert (f["odds_home"], f["odds_draw"], f["odds_away"], f["odds_btts_yes"]) == (1.91, 3.75, 4.1, 1.6)
    assert f["odds_over25"] == 1.7  # no Belgian price for it: the earlier price stays
    assert f["bookmaker"] == "Best of Bingoal, Unibet (not on Napoleon)" and f["kambi_event_id"] == 77
    assert f["price_books"]["odds_draw"] == "bingoal" and f["better_elsewhere"] == {}
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


# ------------------------------------------------------------------ closing prices
def test_closing_price_is_the_last_snapshot_before_kickoff_best_across_books(tmp_path):
    from football_core.data.odds_archive import append_snapshot, closing_prices, load_snapshots, snapshot_rows
    ev = lambda h, d, a, b: {"event_id": 5, "league": "Belgium", "start": "2026-10-09T18:45:00Z", "home_team": "SK Beveren",
                             "away_team": "Lommel SK", "books": {"unibet": {"odds_home": h, "odds_draw": d, "odds_away": a},
                                                                 "bingoal": {"odds_home": b, "odds_draw": d, "odds_away": a}}}
    utc = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    append_snapshot(snapshot_rows([ev(1.95, 3.6, 4.0, 1.9)], utc("2026-10-09T17:50:00")), tmp_path)
    append_snapshot(snapshot_rows([ev(1.85, 3.7, 4.3, 1.88)], utc("2026-10-09T18:40:00")), tmp_path)
    append_snapshot(snapshot_rows([ev(1.5, 4.0, 6.0, 1.5)], utc("2026-10-09T18:50:00")), tmp_path)  # in play: ignored
    snaps = load_snapshots(["2026-10-09", "2026-10-08"], tmp_path)
    assert len(snaps) == 6
    close = closing_prices(snaps)[5]
    assert (close["odds_home"], close["odds_draw"], close["odds_away"]) == (1.88, 3.7, 4.3)
    assert close["captured_at"] == "2026-10-09T18:40:00Z" and close["books"] == ["bingoal", "unibet"]


def test_closing_prices_go_on_open_records_and_drive_clv(tmp_path):
    from football_core.betting.tracker import PredictionTracker
    from sports_common.evaluation import evaluate_football_ledger
    tracker = PredictionTracker(storage_file=tmp_path / "ledger.json")
    base = {"home_team": "SK Beveren", "away_team": "Lommel SK", "date": "2026-10-09", "odds_home": 2.0, "odds_draw": 3.6,
            "odds_away": 3.8, "odds_captured_at": "2026-10-09T05:00:00+00:00",
            "first_pick": {"selection": "Home Win", "odds": 2.0, "logged_at": "2026-10-09T05:00:00+00:00"}}
    tracker.predictions = [dict(base, match_id="a", kambi_event_id=5, status="pending"),
                           dict(base, match_id="b", kambi_event_id=6, status="settled"),
                           dict(base, match_id="c", status="pending")]
    closing = {5: {"odds_home": 1.8, "odds_draw": 3.8, "odds_away": 4.6, "captured_at": "2026-10-09T18:40:00Z"},
               6: {"odds_home": 1.8, "odds_draw": 3.8, "odds_away": 4.6, "captured_at": "2026-10-09T18:40:00Z"}}
    assert tracker.attach_closing_odds(closing) == 1  # settled and unlinked records are left alone
    assert tracker.predictions[0]["closing_odds"]["odds_home"] == 1.8 and "closing_odds" not in tracker.predictions[1]
    clv = evaluate_football_ledger([tracker.predictions[0]])["clv"]
    assert clv["price"]["n"] == 1 and clv["price"]["mean_pct"] == pytest.approx(100 * (2.0 / 1.8 - 1), abs=0.01)


# ------------------------------------------------------------------ tennis
def _tennis_item(eid, home, away, o1, o2, state="NOT_STARTED", path=None):
    return {"event": {"id": eid, "homeName": home, "awayName": away, "start": "2026-10-05T07:30:00Z", "state": state,
                      "path": path or []},
            "betOffers": [{"criterion": {"label": "Match Odds"}, "betOfferType": {"name": "Match"},
                           "outcomes": [{"type": "OT_ONE", "odds": o1}, {"type": "OT_TWO", "odds": o2}]}]}


def test_kambi_tennis_list_keeps_upcoming_singles():
    from tennis_core.data.kambi_tennis import parse_list_view
    payload = {"events": [_tennis_item(1, "Alex De Minaur", "Hubert Hurkacz", 1660, 2230),
                          _tennis_item(2, "Carlos Alcaraz", "Jaume Munar", 1100, 6750, state="STARTED"),
                          _tennis_item(3, "Mektic/Pavic", "Arevalo/Pavic", 1800, 1900),
                          _tennis_item(4, "Coco Gauff", "Xinran Sun", 1030, None)]}
    assert [(m["event_id"], m["circuit"], m["odds"]) for m in parse_list_view(payload, "tennis/atp")] == \
        [(1, "ATP", {"p1_odds": 1.66, "p2_odds": 2.23})]
    slam = {"events": [_tennis_item(5, "Iga Swiatek", "Coco Gauff", 1500, 2600, path=[{"termKey": "us_open_women"}])]}
    assert parse_list_view(slam, "tennis/grand_slam")[0]["circuit"] == "WTA"


def test_tennis_belgian_prices_follow_the_fixture_player_order():
    from tennis_core.data.kambi_tennis import merge_belgian_prices
    fixtures = [{"circuit": "WTA", "date": "2026-10-05", "p1_name": "Sun Xinran", "p2_name": "Coco Gauff",
                 "p1_odds": 11.0, "p2_odds": 1.04},
                {"circuit": "ATP", "date": "2026-10-05", "p1_name": "Alex de Minaur", "p2_name": "Hubert Hurkacz"}]
    events = [{"event_id": 9, "start": "2026-10-05T07:30:00Z", "circuit": "WTA", "p1_name": "Coco Gauff", "p2_name": "Xinran Sun",
               "books": {"unibet": {"p1_odds": 1.03, "p2_odds": 12.0}, "bingoal": {"p1_odds": 1.04, "p2_odds": 11.5}}},
              {"event_id": 8, "start": "2026-10-05T07:30:00Z", "circuit": "WTA", "p1_name": "Alex De Minaur",
               "p2_name": "Hubert Hurkacz", "books": {"unibet": {"p1_odds": 1.66, "p2_odds": 2.23}}}]
    assert merge_belgian_prices(fixtures, events) == 1  # the second event is listed under the wrong tour
    f = fixtures[0]
    assert (f["p1_odds"], f["p2_odds"]) == (12.0, 1.04)  # Kambi lists Gauff first
    assert f["reference_odds"]["eu"] == {"p1_odds": 11.0, "p2_odds": 1.04, "bookmaker": None}
    assert f["bookmaker"] == "Best of Bingoal, Unibet (not on Napoleon)" and f["kambi_event_id"] == 9
    assert "p1_odds" not in fixtures[1]


# ------------------------------------------------------------------ Napoleon (Superbet)
def test_superbet_odds_map_to_our_fields():
    from football_core.data.napoleon import parse_odds
    listed = _load("superbet_by_date.json")["data"][0]
    assert parse_odds(listed["odds"]) == {"odds_home": 1.92, "odds_draw": 3.85, "odds_away": 3.9}
    assert parse_odds(_load("superbet_event.json")["data"][0]["odds"]) == {
        "odds_home": 1.92, "odds_draw": 3.85, "odds_away": 3.9, "odds_over25": 1.67, "odds_under25": 2.22,
        "odds_btts_yes": 1.58, "odds_btts_no": 2.22, "odds_corners_over95": 1.65, "odds_corners_under95": 2.1}


def test_superbet_markets_need_every_side_active():
    from football_core.data.napoleon import parse_odds
    odds = [dict(o) for o in _load("superbet_by_date.json")["data"][0]["odds"]]
    odds[1]["status"] = "suspended"
    assert parse_odds(odds) == {}


def test_napoleon_events_take_kambis_shape():
    from football_core.data.napoleon import parse_odds, to_event
    listed = _load("superbet_by_date.json")["data"][0]
    event = to_event(listed, "Belgium", parse_odds(listed["odds"]))
    assert (event["home_team"], event["away_team"], event["start"]) == ("SK Beveren", "Lommel SK", "2026-10-09T18:45:00Z")
    assert event["books"] == {"napoleon": {"odds_home": 1.92, "odds_draw": 3.85, "odds_away": 3.9}}


def test_napoleon_price_first_and_better_prices_elsewhere_noted():
    from sports_common.belgian_prices import choose_prices
    prices, sources, better = choose_prices({"napoleon": {"odds_home": 1.92, "odds_draw": 3.6},
                                             "unibet": {"odds_home": 1.91, "odds_draw": 3.75, "odds_away": 4.1},
                                             "bingoal": {"odds_home": 1.98, "odds_draw": 3.7, "odds_away": 3.95}})
    assert prices == {"odds_home": 1.92, "odds_draw": 3.6, "odds_away": 4.1}
    assert sources == {"odds_home": "napoleon", "odds_draw": "napoleon", "odds_away": "unibet"}
    assert better == {"odds_home": {"book": "bingoal", "odds": 1.98}, "odds_draw": {"book": "unibet", "odds": 3.75}}
    _, _, close_call = choose_prices({"napoleon": {"odds_home": 1.92}, "unibet": {"odds_home": 1.97}})
    assert close_call == {}  # under 3% better: no note


def test_kambi_and_napoleon_prices_combine_on_one_fixture():
    from football_core.data.kambi import merge_belgian_prices
    fixtures = [{"league": "Belgium", "date": "2026-10-09", "home_team": "Waasland-Beveren", "away_team": "Lommel SK",
                 "odds_home": 1.8, "odds_draw": 3.75, "odds_away": 3.9, "bookmaker": "DraftKings (ESPN)"}]
    merge_belgian_prices(fixtures, [_event("SK Beveren", "Lommel SK", event_id=77)])
    napoleon = {"event_id": 14011411, "league": "Belgium", "start": "2026-10-09T18:45:00Z", "home_team": "SK Beveren",
                "away_team": "Lommel SK", "books": {"napoleon": {"odds_home": 1.92, "odds_draw": 3.6, "odds_away": 3.9,
                                                                 "odds_btts_yes": 1.58}}}
    assert merge_belgian_prices(fixtures, [napoleon]) == 1
    f = fixtures[0]
    assert set(f["belgian_books"]) == {"unibet", "bingoal", "napoleon"}
    assert (f["odds_home"], f["odds_draw"], f["odds_away"], f["odds_btts_yes"]) == (1.92, 3.6, 3.9, 1.58)
    assert f["bookmaker"] == "Napoleon"
    assert f["better_elsewhere"] == {"odds_draw": {"book": "bingoal", "odds": 3.75}, "odds_away": {"book": "unibet", "odds": 4.1}}
    assert f["kambi_event_id"] == 77  # the archive key stays Kambi's
    assert f["reference_odds"]["eu"]["odds_home"] == 1.8  # the pre-Belgian price, not Kambi's


def test_napoleon_tennis_prices_pair_in_either_order_and_skip_doubles(monkeypatch):
    from tennis_core.data import kambi_tennis
    monkeypatch.setattr(kambi_tennis, "events_by_date", lambda *a, **k: _load("superbet_by_date.json")["data"][1:])
    events = kambi_tennis.fetch_napoleon_prices()
    assert [(e["p1_name"], e["p2_name"]) for e in events] == [("Laura Svatikova", "Kristina Kovgan")]
    o = events[0]["books"]["napoleon"]
    fixtures = [{"circuit": "WTA", "date": events[0]["start"][:10], "p1_name": "Kristina Kovgan", "p2_name": "Laura Svatikova"}]
    assert kambi_tennis.merge_belgian_prices(fixtures, events) == 1
    assert (fixtures[0]["p1_odds"], fixtures[0]["p2_odds"]) == (o["p2_odds"], o["p1_odds"])
    assert fixtures[0]["bookmaker"] == "Napoleon" and "kambi_event_id" not in fixtures[0]


def test_closing_price_is_napoleons_when_it_has_one(tmp_path):
    from football_core.data.odds_archive import append_snapshot, closing_prices, load_snapshots, snapshot_rows
    ev = {"event_id": 5, "league": "Belgium", "start": "2026-10-09T18:45:00Z", "home_team": "SK Beveren", "away_team": "Lommel SK",
          "books": {"unibet": {"odds_home": 1.95, "odds_draw": 3.6, "odds_away": 4.0},
                    "napoleon": {"odds_home": 1.9, "odds_draw": 3.7, "odds_away": 4.1}}}
    append_snapshot(snapshot_rows([ev], datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)), tmp_path)
    close = closing_prices(load_snapshots(["2026-10-09"], tmp_path))[5]
    assert (close["odds_home"], close["odds_draw"]) == (1.9, 3.7) and close["price_books"]["odds_home"] == "napoleon"


def test_picks_carry_their_book_and_a_better_price_elsewhere():
    from sports_common.belgian_prices import annotate_football_pick, tennis_pick_note
    fixture = {"price_books": {"odds_home": "napoleon", "odds_over25": "unibet"},
               "better_elsewhere": {"odds_home": {"book": "bingoal", "odds": 1.98}}}
    pick = annotate_football_pick({"market": "1X2", "selection": "Home Win", "odds": 1.92}, fixture)
    assert pick["book"] == "Napoleon" and pick["better_elsewhere"] == "Bingoal pays 1.98"
    assert annotate_football_pick({"selection": "Over 2.5 Goals"}, fixture)["book"] == "Unibet"
    assert annotate_football_pick({"selection": "Arsenal (Fav)"}, fixture) == {"selection": "Arsenal (Fav)"}
    tennis = {"price_books": {"p1_odds": "napoleon", "p2_odds": "unibet"}}
    assert tennis_pick_note(tennis, "Sinner J.", ("Jannik Sinner", "Sinner J."), ("Carlos Alcaraz", "Alcaraz C.")) == {"book": "Napoleon"}
    assert tennis_pick_note(tennis, None, ("A",), ("B",)) == {}
