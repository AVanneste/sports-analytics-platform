from datetime import datetime, timezone

from sports_common.betting import devig, devig_power
from sports_common.edges import fair_prices, find_edges

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
GAMES = {1: {"sport": "Soccer", "league": "Belgium - Pro League", "start": "2026-10-12T18:45:00Z", "home": "Union SG", "away": "Genk"}}


def test_devig_power_sums_to_one_and_shades_longshots():
    odds = [1.5, 4.2, 7.0]
    power, mult = devig_power(odds), devig(odds)
    assert abs(power.sum() - 1) < 1e-9
    assert power[2] < mult[2] and power[0] > mult[0]
    assert devig_power([1.0, 2.0]) is None


def pin(selection, price, market="moneyline", line=None, limit=1000):
    return {"event_id": 1, "market": market, "period": 0, "units": None, "side": None, "line": line,
            "selection": selection, "price": price, "limit": limit}


def book(selection, price, event_id="x", market="moneyline", line=None, name="napoleon"):
    return {"book": name, "event_id": event_id, "market": market, "period": 0, "units": None, "side": None,
            "line": line, "selection": selection, "price": price}


def test_find_edges_prices_against_vig_free_pinnacle():
    fair = fair_prices([pin("home", 2.0), pin("draw", 3.6), pin("away", 3.9),
                        pin("home", 1.95, "spread", -0.25), pin("away", 1.95, "spread", 0.25)])
    rows = [book("home", 2.2), book("draw", 3.3), book("away", 3.5),
            book("home", 2.1, market="spread", line=-0.25), book("away", 1.8, market="spread", line=0.25)]
    edges = find_edges(rows, {("napoleon", "x"): (1, False)}, fair, GAMES, now=NOW)
    assert [(e["market"], e["selection"], e["price"]) for e in edges] == [("moneyline", "home", 2.2), ("spread", "home", 2.1)]
    assert edges[0]["ev"] > 0.02 and edges[0]["home"] == "Union SG"


def test_find_edges_swaps_home_away_and_skips_misread_or_thin_markets():
    fair = fair_prices([pin("home", 1.9), pin("away", 1.9)])
    swapped = [book("home", 1.75, "s"), book("away", 2.1, "s")]  # the book lists Genk first: its "away" is Union SG
    edge, = find_edges(swapped, {("napoleon", "s"): (1, True)}, fair, GAMES, now=NOW)
    assert edge["selection"] == "home" and edge["price"] == 2.1
    misread = [book("home", 2.1, "m"), book("away", 2.1, "m")]  # 95% implied: not this market
    assert find_edges(misread, {("napoleon", "m"): (1, False)}, fair, GAMES, now=NOW) == []
    thin = fair_prices([pin("home", 1.9, limit=100), pin("away", 1.9, limit=100)])
    assert find_edges(swapped, {("napoleon", "s"): (1, True)}, thin, GAMES, now=NOW) == []


def test_track_drops_flags_a_shortening_main_line_only():
    from sports_common.edges import track_drops
    history, t0 = {}, datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    key, alt = (1, "moneyline", 0, None, None, None, "home"), (1, "spread", 0, None, None, -2.5, "home")
    ref = lambda p, alternate=False: {"prob": p, "limit": 1000, "price": 1 / p, "alternate": alternate}
    assert track_drops(history, {key: ref(0.50), alt: ref(0.30, True)}, {1}, t0) == {}
    assert len(history) == 1  # alternate lines are not tracked
    later = t0.replace(hour=12)
    assert track_drops(history, {key: ref(0.55)}, {1}, later) == {key: 0.50}
    assert track_drops(history, {key: ref(0.55)}, {1}, t0.replace(hour=17)) == {}  # the 0.50 point is past 6h


def test_select_alerts_groups_books_and_does_not_repeat():
    from sports_common.edges import select_alerts
    base = {"event_id": 1, "market": "moneyline", "period": 0, "units": None, "side": None, "line": None,
            "selection": "home", "start": "2026-10-12T18:45:00Z", "stake": 0.01}
    edges = [{**base, "book": "unibet", "price": 2.10, "ev": 0.03}, {**base, "book": "napoleon", "price": 2.20, "ev": 0.08},
             {**base, "selection": "draw", "book": "napoleon", "price": 3.3, "ev": 0.005}]
    sent = {}
    alert, = select_alerts(edges, {}, sent, now=NOW)
    assert (alert["book"], alert["price"], alert["books"]) == ("napoleon", 2.2, {"unibet": 2.1, "napoleon": 2.2})
    assert select_alerts(edges, {}, sent, now=NOW) == []  # already sent at this EV
    draw_key = (1, "moneyline", 0, None, None, None, "draw")
    dropped, = select_alerts(edges, {draw_key: 0.25}, sent, now=NOW)  # under 2% EV, but Pinnacle dropped it
    assert dropped["selection"] == "draw" and dropped["dropped_from"] == 0.25
    select_alerts([], {}, sent, now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert sent == {}  # forgotten after kick-off


def test_select_alerts_keeps_the_best_line_of_a_market():
    from sports_common.edges import select_alerts
    spread = lambda line, ev: {"event_id": 1, "market": "spread", "period": 0, "units": None, "side": None, "line": line,
                               "selection": "away", "start": "2026-10-12T18:45:00Z", "stake": 0.01, "book": "unibet",
                               "price": 1.9, "ev": ev}
    alert, = select_alerts([spread(-1.5, 0.05), spread(-2.5, 0.07), spread(-3.5, 0.06)], {}, {}, now=NOW)
    assert alert["line"] == -2.5


def test_track_closing_follows_the_fair_price_to_kick_off():
    from sports_common.edges import ALERT_COLUMNS, track_closing
    key = (1, "moneyline", 0, None, None, None, "home")
    alert = {"event_id": 1, "market": "moneyline", "period": 0, "units": None, "side": None, "line": None,
             "selection": "home", "start": "2026-10-12T18:45:00Z", "book": "napoleon", "price": 2.2, "books": {"napoleon": 2.2},
             "fair_prob": 0.48, "ev": 0.056, "stake": 0.01, "limit": 1000, "sport": "Soccer", "home": "Union SG", "away": "Genk"}
    fair = lambda p: {key: {"prob": p, "limit": 1000, "price": 1 / p, "alternate": False}}
    open_alerts = {}
    assert track_closing(open_alerts, [alert], fair(0.48), NOW) == []
    assert track_closing(open_alerts, [], fair(0.50), NOW.replace(hour=18, minute=40)) == []  # last look before kick-off
    row, = track_closing(open_alerts, [], {}, NOW.replace(hour=18, minute=50))
    assert set(row) == set(ALERT_COLUMNS) and open_alerts == {}
    assert (row["close_prob"], row["ev_at_close"], row["captured_at"]) == (0.5, 0.1, "2026-10-12T12:00:00Z")


def test_three_way_book_market_is_not_priced_against_two_way_pinnacle():
    fair = fair_prices([pin("home", 1.9), pin("away", 1.9)])  # Pinnacle: 2-way (handball, hockey incl. OT)
    three_way = [book("home", 2.4, "h"), book("draw", 8.0, "h"), book("away", 2.4, "h")]
    assert find_edges(three_way, {("napoleon", "h"): (1, False)}, fair, GAMES, now=NOW) == []


def test_web_payload_open_ev_now_and_clv_summary():
    from sports_common.edges import web_payload
    open_alerts = {"a": {"sport": "Soccer", "start": "2026-10-12T18:45:00Z", "home": "Union SG", "away": "Genk",
                         "market": "moneyline", "selection": "home", "book": "napoleon", "price": 2.2, "ev": 0.056,
                         "fair_prob": 0.48, "close_prob": 0.5, "books": '{"napoleon": 2.2}'}}
    closed = [{"sport": "Soccer", "market": "total", "units": "Corners", "book": "napoleon", "ev": 0.05, "ev_at_close": 0.03,
               "dropped_from": None, "start": "2026-10-11T18:00:00Z"},
              {"sport": "Tennis", "market": "moneyline", "units": None, "book": "unibet", "ev": 0.03, "ev_at_close": -0.01,
               "dropped_from": 0.4, "start": "2026-10-11T12:00:00Z"}]
    p = web_payload(open_alerts, closed, NOW)
    assert p["open"][0]["ev_now"] == 0.1 and p["open"][0]["books"] == {"napoleon": 2.2}
    assert p["summary"] == {"alerts": 2, "ev_sent_pct": 4.0, "ev_close_pct": 1.0, "beat_close_pct": 50.0}
    assert {g["group"] for g in p["by_market"]} == {"total (corners)", "moneyline"}
    assert {g["group"] for g in p["by_kind"]} == {"ev", "drop"}
