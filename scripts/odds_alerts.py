"""+EV alerts: Belgian book prices that beat Pinnacle's vig-free price (run by .github/workflows/odds_alerts.yml).

    python scripts/odds_alerts.py [--dry-run] [--min-ev 0.02] [--napoleon-hours 6] [--state alerts_state.json.gz]
                                  [--archive odds_archive/snapshots/alerts]

Sends to Telegram one alert per selection a Belgian book prices +EV, or still prices at or above
Pinnacle's fair price after Pinnacle dropped it (``sports_common.edges.DROP``). The state file
(kept between runs by the workflow's cache) holds Pinnacle's recent fair prices and what was sent.
What is alerted is set in alerts_settings.json (repository root; edit it on GitHub, the next run
uses it): EV and odds ranges, sports, markets, corners and first halves, books, hours to kick-off,
alerts per run, drop alerts on/off and Pinnacle's minimum limit per sport. Commands sent to the
bot (/settings, /set, /reset: sports_common/bot_settings.py) override it from the next run; the
overrides live in ``--overrides`` (the workflow keeps it on the odds-archive branch).
Every sent alert is followed to kick-off and then appended to ``--archive`` (one CSV a day) with
Pinnacle's closing fair price and its EV at the close, the yardstick (scripts/alerts_report.py).

Pinnacle's boards for soccer, tennis and basketball are the reference; Unibet and Bingoal (Kambi)
are read in full, Napoleon (Superbet) in full only for matched games kicking off within
``--napoleon-hours`` (its details are ~1 MB a match) and by its main market otherwise.
"""
import argparse
import csv
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from sports_common.belgian_board import (KAMBI_SPORTS, SUPERBET_SPORTS, fetch_kambi_board, fetch_superbet_details,
                                         fetch_superbet_list, parse_superbet_event)
from sports_common.edges import (ALERT_COLUMNS, fair_prices, find_edges, select_alerts, track_closing,
                                 track_drops, web_payload)
from sports_common.bot_settings import apply as apply_commands
from sports_common.bot_settings import read_commands
from sports_common.notify import send
from sports_common.odds_archive import append_rows
from sports_common.matching import match_events, unique_events
from sports_common.pinnacle import BASKETBALL, HANDBALL, HOCKEY, SOCCER, TENNIS, VOLLEYBALL, fetch_board
from sports_common.superbet import split_match_name

PINNACLE_SPORTS = {"Soccer": SOCCER, "Tennis": TENNIS, "Basketball": BASKETBALL, "Hockey": HOCKEY,
                   "Volleyball": VOLLEYBALL, "Handball": HANDBALL}
ICONS = {"Soccer": "⚽", "Tennis": "🎾", "Basketball": "🏀", "Hockey": "🏒", "Volleyball": "🏐", "Handball": "🤾"}
BRUSSELS = ZoneInfo("Europe/Brussels")
SETTINGS = Path(__file__).resolve().parent.parent / "alerts_settings.json"


def superbet_event(e: Dict) -> Dict:
    home, away = split_match_name(e.get("matchName"))
    return {"book": "napoleon", "event_id": e["eventId"], "sport": SUPERBET_SPORTS[e["sportId"]],
            "start": e.get("utcDate"), "home": home, "away": away}


def wanted(edge: Dict, settings: Dict) -> bool:
    """Whether an edge passes the settings' sport, book, market, corners, first-half and odds filters."""
    return (edge["sport"] in settings["sports"] and edge["book"] in settings["books"]
            and edge["market"] in settings["markets"] and settings["min_odds"] <= edge["price"] <= settings["max_odds"]
            and (settings["corners"] or edge.get("units") != "Corners") and (settings["first_half"] or edge["period"] != 1))


def scan(napoleon_hours: float, now: datetime, settings: Dict) -> Tuple[List[Dict], Dict, set]:
    """(every matched book price at EV >= 0 within the settings' limits, Pinnacle's fair prices, the matched games)."""
    pinnacle = []
    for sport, sport_id in PINNACLE_SPORTS.items():
        if sport in settings["sports"]:
            pinnacle += fetch_board(sport_id)
    games = {g["event_id"]: g for g in unique_events(pinnacle, keys=("event_id", "sport", "league", "start", "home", "away"))}

    book_rows = []
    hours = settings["max_hours_to_kickoff"]
    for sport in KAMBI_SPORTS:
        if sport in settings["sports"] and {"unibet", "bingoal"} & set(settings["books"]):
            book_rows += fetch_kambi_board(sport, within_hours=hours, now=now)
    napoleon = ([e for e in fetch_superbet_list(within_hours=hours, now=now) if SUPERBET_SPORTS[e["sportId"]] in settings["sports"]]
                if "napoleon" in settings["books"] else [])
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
    edges = find_edges(book_rows, matches, fair, games, min_ev=0.0, now=now, max_ev=settings["max_ev_pct"] / 100,
                       max_odds=settings["max_odds"], within_hours=hours, min_limit=settings["min_pinnacle_limit"])
    return [e for e in edges if wanted(e, settings)], fair, {g for g, _ in matches.values()}


def stake_text(stake: float, bankroll: float) -> str:
    """'stake €8 (1.6%)' with a bankroll set, else 'stake 1.6%'."""
    return f"stake €{stake * bankroll:.0f} ({stake:.1%})" if bankroll else f"stake {stake:.1%}"


def describe(alert: Dict, bankroll: float = 0) -> str:
    """game, pick @ best book (other books), fair price, EV, quarter-Kelly stake, Pinnacle limit and drop."""
    who = {"home": alert["home"], "away": alert["away"]}.get(alert.get("side") or alert["selection"], alert["selection"])
    if alert["market"] == "moneyline":
        pick = who.capitalize() if who == "draw" else who
    elif alert["market"] == "spread":
        pick = f"{who} {alert['line']:+g}"
    else:
        pick = f"{who + ' ' if alert.get('side') else ''}{alert['selection']} {alert['line']:g}"
    period = {1: "1st half", 6: "regular time"}.get(alert["period"])
    scope = ", ".join(filter(None, [alert.get("units") and alert["units"].lower(), period]))
    kickoff = datetime.fromisoformat(alert["start"].replace("Z", "+00:00")).astimezone(BRUSSELS)
    others = ", ".join(f"{b.capitalize()} {p:.2f}" for b, p in sorted(alert["books"].items(), key=lambda bp: -bp[1]) if b != alert["book"])
    lines = [f"{ICONS.get(alert['sport'], '•')} {alert['home']} – {alert['away']} · {kickoff:%a %d/%m %H:%M}",
             f"{pick}{' (' + scope + ')' if scope else ''} @ {alert['price']:.2f} {alert['book'].capitalize()}"
             + (f" ({others})" if others else ""),
             f"fair {alert['fair_odds']:.2f} · EV {alert['ev']:+.1%} · {stake_text(alert['stake'], bankroll)} · Pin limit {alert['limit']}"]
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
    parser.add_argument("--min-ev", type=float, help="override the settings' min_ev_pct (0.02 = 2%%)")
    parser.add_argument("--settings", type=Path, default=SETTINGS)
    parser.add_argument("--web-out", type=Path, help="write the app's Alerts payload here (JSON)")
    parser.add_argument("--overrides", type=Path, help="settings changed from Telegram (read and written)")
    parser.add_argument("--napoleon-hours", type=float, default=6)
    parser.add_argument("--state", type=Path, default=Path("alerts_state.json.gz"))
    parser.add_argument("--archive", type=Path, help="log closed alerts here (the odds-archive checkout)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    now = datetime.now(timezone.utc)
    defaults = json.loads(args.settings.read_text())
    state = load_state(args.state)
    overrides = json.loads(args.overrides.read_text()) if args.overrides and args.overrides.exists() else {}
    if args.overrides and not args.dry_run:
        try:
            commands, state["tg_offset"] = read_commands(state.get("tg_offset", 0))
        except Exception as e:  # never let the bot's inbox stop the alerts
            logging.warning(f"Telegram commands unavailable: {type(e).__name__}")
            commands = []
        if commands:
            overrides, replies = apply_commands(commands, defaults, overrides)
            args.overrides.parent.mkdir(parents=True, exist_ok=True)
            args.overrides.write_text(json.dumps(overrides, indent=1))
            send(replies)
    settings = {**defaults, **overrides}
    min_ev = args.min_ev if args.min_ev is not None else settings["min_ev_pct"] / 100
    edges, fair, matched_games = scan(args.napoleon_hours, now, settings)
    drops = track_drops(state.setdefault("fair", {}), fair, matched_games, now)
    alerts = select_alerts(edges, drops if settings["drop_alerts"] else {}, state.setdefault("sent", {}), min_ev=min_ev, now=now)
    logging.info(f"{len(alerts)} new alerts, {len(drops)} Pinnacle drops")
    cap = settings["max_alerts_per_run"]
    messages = [describe(a, settings.get("bankroll") or 0) for a in alerts[:cap]]
    if len(alerts) > cap:
        messages.append(f"…and {len(alerts) - cap} more (EV {alerts[cap]['ev']:+.1%} down to {alerts[-1]['ev']:+.1%})")
    if args.dry_run:
        print("\n\n".join(messages))
        return
    if messages and not send(messages):
        raise SystemExit("Telegram send failed")
    closed = track_closing(state.setdefault("open", {}), alerts, fair, now)
    if args.archive and closed:
        logging.info(f"{len(closed)} alerts closed, logged to {append_rows(closed, ALERT_COLUMNS, args.archive)}")
    # the payload changes every run (EVs move): rewrite it when alerts open or close, else every 30 min,
    # so the odds-archive branch does not get a commit every 5 minutes
    signature = sorted(state["open"])
    due = now.timestamp() - state.get("web_written_at", 0) >= 30 * 60
    if args.web_out and args.archive and (due or closed or signature != state.get("web_signature")):
        state["web_written_at"], state["web_signature"] = now.timestamp(), signature
        since = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        history = []
        for path in sorted(args.archive.glob("*.csv")):
            if path.stem >= since:
                with open(path, newline="", encoding="utf-8") as fh:
                    history += list(csv.DictReader(fh))
        for row in history:
            for k in ("price", "ev", "fair_prob", "stake", "close_prob", "ev_at_close", "line", "limit", "dropped_from"):
                row[k] = float(row[k]) if row.get(k) not in (None, "") else None
            row["period"] = int(float(row.get("period") or 0))
            for k in ("units", "side", "league"):
                row[k] = row.get(k) or None
        args.web_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {**web_payload(state["open"], history, now), "bankroll": settings.get("bankroll") or 0}
        args.web_out.write_text(json.dumps(payload, allow_nan=False))
    with gzip.open(args.state, "wt") as f:
        json.dump(state, f)


if __name__ == "__main__":
    main()
