"""+EV alerts: Belgian book prices that beat Pinnacle's vig-free price (run by .github/workflows/odds_alerts.yml).

    python scripts/odds_alerts.py [--dry-run] [--min-ev 0.02] [--napoleon-hours 6]

Pinnacle's boards for soccer, tennis and basketball are the reference; Unibet and Bingoal (Kambi)
are read in full, Napoleon (Superbet) in full only for matched games kicking off within
``--napoleon-hours`` (its details are ~1 MB a match) and by its main market otherwise.
"""
import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sports_common.belgian_board import (KAMBI_SPORTS, SUPERBET_SPORTS, fetch_kambi_board, fetch_superbet_details,
                                         fetch_superbet_list, parse_superbet_event)
from sports_common.edges import WITHIN_HOURS, fair_prices, find_edges
from sports_common.matching import match_events, unique_events
from sports_common.pinnacle import BASKETBALL, SOCCER, TENNIS, fetch_board
from sports_common.superbet import split_match_name

PINNACLE_SPORTS = {"Soccer": SOCCER, "Tennis": TENNIS, "Basketball": BASKETBALL}


def superbet_event(e: Dict) -> Dict:
    home, away = split_match_name(e.get("matchName"))
    return {"book": "napoleon", "event_id": e["eventId"], "sport": SUPERBET_SPORTS[e["sportId"]],
            "start": e.get("utcDate"), "home": home, "away": away}


def scan(min_ev: float, napoleon_hours: float) -> List[Dict]:
    now = datetime.now(timezone.utc)
    pinnacle = []
    for sport, sport_id in PINNACLE_SPORTS.items():
        pinnacle += fetch_board(sport_id)
    games = {g["event_id"]: g for g in unique_events(pinnacle, keys=("event_id", "sport", "league", "start", "home", "away"))}

    book_rows = []
    for sport in KAMBI_SPORTS:
        book_rows += fetch_kambi_board(sport, within_hours=WITHIN_HOURS, now=now)
    napoleon = fetch_superbet_list(within_hours=WITHIN_HOURS, now=now)
    events = unique_events(book_rows) + [superbet_event(e) for e in napoleon if split_match_name(e.get("matchName"))[1]]
    matches = match_events(events, list(games.values()))

    soon = now + timedelta(hours=napoleon_hours)
    detailed = [e for e in napoleon if ("napoleon", e["eventId"]) in matches
                and datetime.fromisoformat(e["utcDate"].replace("Z", "+00:00")) <= soon]
    book_rows += fetch_superbet_details(detailed)
    detailed_ids = {e["eventId"] for e in detailed}
    for e in napoleon:
        if e["eventId"] not in detailed_ids and ("napoleon", e["eventId"]) in matches:
            book_rows += parse_superbet_event(e, e.get("odds") or [])
    logging.info(f"{len(games)} Pinnacle games, {len(events)} book events, {len(matches)} matched, "
                 f"{len(detailed)} Napoleon details, {len(book_rows)} book prices")
    return find_edges(book_rows, matches, fair_prices(pinnacle), games, min_ev=min_ev, now=now)


def describe(edge: Dict) -> str:
    """One line: game, selection, book price vs fair, EV, quarter-Kelly stake, Pinnacle limit, kick-off."""
    market = edge["market"].replace("_", " ")
    who = {"home": edge["home"], "away": edge["away"]}.get(edge.get("side") or edge["selection"], edge["selection"])
    if edge["market"] == "moneyline":
        pick = who
    elif edge["market"] == "spread":
        pick = f"{who} {edge['line']:+g}"
    else:
        pick = f"{who + ' ' if edge.get('side') else ''}{edge['selection']} {edge['line']:g}"
    scope = " ".join(filter(None, [edge.get("units"), "1st half" if edge["period"] == 1 else None]))
    return (f"{edge['sport']} · {edge['home']} – {edge['away']} · {market}{' (' + scope + ')' if scope else ''}: {pick} "
            f"@ {edge['book']} {edge['price']:.2f} · fair {edge['fair_odds']:.2f} · EV {edge['ev']:+.1%} · "
            f"stake {edge['stake']:.1%} · Pin limit {edge['limit']} · KO {edge['start'][5:16].replace('T', ' ')} UTC")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print alerts instead of sending them")
    parser.add_argument("--min-ev", type=float, default=0.02)
    parser.add_argument("--napoleon-hours", type=float, default=6)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    edges = scan(args.min_ev, args.napoleon_hours)
    for edge in edges:
        print(describe(edge))
    logging.info(f"{len(edges)} edges")


if __name__ == "__main__":
    main()
