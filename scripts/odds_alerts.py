"""+EV alerts: Belgian book prices that beat Pinnacle's vig-free price (run by .github/workflows/odds_alerts.yml).

    python scripts/odds_alerts.py [--dry-run] [--min-ev 0.02] [--napoleon-hours 6] [--state alerts_state.json.gz]
                                  [--archive odds_archive/snapshots/alerts]

Sends to Telegram one alert per selection a Belgian book prices +EV, or still prices at or above
Pinnacle's fair price after Pinnacle dropped it (``sports_common.edges.DROP``). The state file
(kept between runs by the workflow's cache) holds Pinnacle's recent fair prices and what was sent.
Every sent alert is followed to kick-off and then appended to ``--archive`` (one CSV a day) with
Pinnacle's closing fair price and its EV at the close, the yardstick (scripts/alerts_report.py).

Pinnacle's boards for soccer, tennis and basketball are the reference; Unibet and Bingoal (Kambi)
are read in full, Napoleon (Superbet) in full only for matched games kicking off within
``--napoleon-hours`` (its details are ~1 MB a match) and by its main market otherwise.
"""
import argparse
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from sports_common.belgian_board import (KAMBI_SPORTS, SUPERBET_SPORTS, fetch_kambi_board, fetch_superbet_details,
                                         fetch_superbet_list, parse_superbet_event)
from sports_common.edges import (ALERT_COLUMNS, WITHIN_HOURS, fair_prices, find_edges, select_alerts, track_closing,
                                 track_drops)
from sports_common.notify import send
from sports_common.odds_archive import append_rows
from sports_common.matching import match_events, unique_events
from sports_common.pinnacle import BASKETBALL, SOCCER, TENNIS, fetch_board
from sports_common.superbet import split_match_name

PINNACLE_SPORTS = {"Soccer": SOCCER, "Tennis": TENNIS, "Basketball": BASKETBALL}
ICONS = {"Soccer": "⚽", "Tennis": "🎾", "Basketball": "🏀"}
BRUSSELS = ZoneInfo("Europe/Brussels")
MAX_ALERTS = 15  # per run: the first run after a gap would otherwise flood the chat


def superbet_event(e: Dict) -> Dict:
    home, away = split_match_name(e.get("matchName"))
    return {"book": "napoleon", "event_id": e["eventId"], "sport": SUPERBET_SPORTS[e["sportId"]],
            "start": e.get("utcDate"), "home": home, "away": away}


def scan(napoleon_hours: float, now: datetime) -> Tuple[List[Dict], Dict, set]:
    """(every matched book price at EV >= 0, Pinnacle's fair prices, the matched Pinnacle games)."""
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
    fair = fair_prices(pinnacle)
    return find_edges(book_rows, matches, fair, games, min_ev=0.0, now=now), fair, {g for g, _ in matches.values()}


def describe(alert: Dict) -> str:
    """game, pick @ best book (other books), fair price, EV, quarter-Kelly stake, Pinnacle limit and drop."""
    who = {"home": alert["home"], "away": alert["away"]}.get(alert.get("side") or alert["selection"], alert["selection"])
    if alert["market"] == "moneyline":
        pick = who.capitalize() if who == "draw" else who
    elif alert["market"] == "spread":
        pick = f"{who} {alert['line']:+g}"
    else:
        pick = f"{who + ' ' if alert.get('side') else ''}{alert['selection']} {alert['line']:g}"
    scope = ", ".join(filter(None, [alert.get("units") and alert["units"].lower(), "1st half" if alert["period"] == 1 else None]))
    kickoff = datetime.fromisoformat(alert["start"].replace("Z", "+00:00")).astimezone(BRUSSELS)
    others = ", ".join(f"{b.capitalize()} {p:.2f}" for b, p in sorted(alert["books"].items(), key=lambda bp: -bp[1]) if b != alert["book"])
    lines = [f"{ICONS.get(alert['sport'], '•')} {alert['home']} – {alert['away']} · {kickoff:%a %d/%m %H:%M}",
             f"{pick}{' (' + scope + ')' if scope else ''} @ {alert['price']:.2f} {alert['book'].capitalize()}"
             + (f" ({others})" if others else ""),
             f"fair {alert['fair_odds']:.2f} · EV {alert['ev']:+.1%} · stake {alert['stake']:.1%} · Pin limit {alert['limit']}"]
    if alert.get("dropped_from"):
        lines.append(f"📉 Pinnacle fair {1 / alert['dropped_from']:.2f} → {alert['fair_odds']:.2f}")
    if alert.get("league"):
        lines.append(alert["league"])
    return "\n".join(lines)


def load_state(path: Path) -> Dict:
    try:
        with gzip.open(path, "rt") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print alerts instead of sending them")
    parser.add_argument("--min-ev", type=float, default=0.02)
    parser.add_argument("--napoleon-hours", type=float, default=6)
    parser.add_argument("--state", type=Path, default=Path("alerts_state.json.gz"))
    parser.add_argument("--archive", type=Path, help="log closed alerts here (the odds-archive checkout)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    now = datetime.now(timezone.utc)
    state = load_state(args.state)
    edges, fair, matched_games = scan(args.napoleon_hours, now)
    drops = track_drops(state.setdefault("fair", {}), fair, matched_games, now)
    alerts = select_alerts(edges, drops, state.setdefault("sent", {}), min_ev=args.min_ev, now=now)
    logging.info(f"{len(alerts)} new alerts, {len(drops)} Pinnacle drops")
    messages = [describe(a) for a in alerts[:MAX_ALERTS]]
    if len(alerts) > MAX_ALERTS:
        messages.append(f"…and {len(alerts) - MAX_ALERTS} more (EV {alerts[MAX_ALERTS]['ev']:+.1%} down to {alerts[-1]['ev']:+.1%})")
    if args.dry_run:
        print("\n\n".join(messages))
        return
    if messages and not send(messages):
        raise SystemExit("Telegram send failed")
    closed = track_closing(state.setdefault("open", {}), alerts, fair, now)
    if args.archive and closed:
        logging.info(f"{len(closed)} alerts closed, logged to {append_rows(closed, ALERT_COLUMNS, args.archive)}")
    with gzip.open(args.state, "wt") as f:
        json.dump(state, f)


if __name__ == "__main__":
    main()
