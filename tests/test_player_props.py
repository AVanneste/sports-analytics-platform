from datetime import datetime, timezone

from sports_common.belgian_board import parse_kambi_event
from sports_common.edges import fair_prices, find_edges
from sports_common.pinnacle import parse_board

LEAGUE = {"name": "WNBA", "sport": {"name": "Basketball"}}
GAME = {"id": 10, "type": "matchup", "league": LEAGUE, "startTime": "2026-10-17T19:30:00Z",
        "participants": [{"alignment": "home", "name": "Indiana Fever"}, {"alignment": "away", "name": "Las Vegas Aces"}]}
PROP = {"id": 11, "type": "special", "parentId": 10, "league": LEAGUE, "startTime": "2026-10-17T19:30:00Z",
        "special": {"category": "Player Props", "description": "Allisha Gray Total Points"},
        "participants": [{"id": 1, "name": "Over"}, {"id": 2, "name": "Under"}]}
MARKETS = [{"matchupId": 11, "type": "total", "period": 0, "limits": [{"type": "maxRiskStake", "amount": 150}],
            "prices": [{"participantId": 1, "points": 15.5, "price": -113}, {"participantId": 2, "points": 15.5, "price": -115}]}]


def test_pinnacle_props():
    row = next(r for r in parse_board([GAME, PROP], MARKETS) if r["market"] == "player_prop")
    assert (row["event_id"], row["units"], row["side"], row["line"], row["home"]) == (10, "points", "allisha gray", 15.5, "Indiana Fever")


def test_kambi_prop_priced_against_pinnacle():
    event = {"id": 99, "homeName": "Indiana Fever", "awayName": "Las Vegas Aces", "start": "2026-10-17T19:30:00Z", "group": "WNBA"}
    offer = {"criterion": {"englishLabel": "Points scored by the player - Including Overtime"},
             "betOfferType": {"name": "Player Occurrence Line"},
             "outcomes": [{"type": "OT_OVER", "odds": 2050, "line": 15500, "participant": "Allisha Gray"},
                          {"type": "OT_UNDER", "odds": 1750, "line": 15500, "participant": "Allisha Gray"}]}
    rows = parse_kambi_event(event, [offer], "unibet", "Basketball")
    assert {(r["side"], r["selection"], r["units"]) for r in rows} == {("allisha gray", "over", "points"), ("allisha gray", "under", "points")}
    pin = parse_board([GAME, PROP], MARKETS)
    games = {10: {"sport": "Basketball", "league": "WNBA", "start": "2026-10-17T19:30:00Z", "home": "Indiana Fever", "away": "Las Vegas Aces"}}
    edges = find_edges(rows, {("unibet", 99): (10, False)}, fair_prices(pin), games, now=datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert [(e["selection"], e["price"]) for e in edges] == [("over", 2.05)]  # fair ~1.98


def test_props_match_by_players_when_the_game_is_not_listed():
    from sports_common.matching import match_by_players
    pin = [{"market": "player_prop", "event_id": 10, "side": s, "start": "2026-10-17T19:30:00Z"} for s in ("allisha gray", "angel reese")]
    book = [{"book": "unibet", "event_id": 99, "market": "player_prop", "side": s, "start": "2026-10-17T19:00:00Z"}
            for s in ("allisha gray", "angel reese", "kelsey mitchell")]
    assert match_by_players(book, pin, {}) == {("unibet", 99): (10, False)}
    assert match_by_players(book[:1], pin, {}) == {}  # one shared player is not enough
