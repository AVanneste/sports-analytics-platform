"""Snapshot Belgian prices for matches kicking off soon (run hourly by .github/workflows/odds_collector.yml).

    python scripts/collect_odds.py [--within-minutes 75] [--out odds_archive/snapshots]

Every competition we model is read for Unibet.be and Bingoal (Kambi) and Napoleon (Superbet);
matches starting within the window get their full prices (1X2, O/U 2.5, BTTS, corners 9.5)
appended to the day's CSV, Napoleon's under the matching Kambi match id. The last snapshot before
kick-off is the closing price used for CLV.
"""
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from football_core.data.kambi import KAMBI_PATHS, fetch_league_prices, match_event
from football_core.data.napoleon import fetch_napoleon_prices
from football_core.data.odds_archive import ARCHIVE_DIR, append_snapshot, snapshot_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--within-minutes", type=float, default=75)
    parser.add_argument("--out", type=Path, default=ARCHIVE_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    now = datetime.now(timezone.utc)
    hours = args.within_minutes / 60
    events = []
    for league_key in KAMBI_PATHS:
        events += fetch_league_prices(league_key, details_hours=hours, within_hours=hours, now=now)
    paired = 0
    try:
        as_fixtures = [{"league": e["league"], "date": e["start"], "home_team": e["home_team"],
                        "away_team": e["away_team"]} for e in events]
        napoleon = fetch_napoleon_prices(details_hours=hours, within_hours=hours, now=now)
        logging.info(f"[Napoleon] {len(napoleon)} matches of our competitions within the window")
        for n in napoleon:
            i = match_event(n, as_fixtures)
            if i is not None:
                events[i]["books"].update(n["books"])
                paired += 1
    except Exception as e:  # Napoleon is optional: keep the Kambi snapshot
        logging.warning(f"[Napoleon] {e}")
    path = append_snapshot(snapshot_rows(events, now), args.out)
    print(f"{len(events)} matches kicking off within {args.within_minutes:.0f} min, {paired} also on Napoleon"
          + (f" -> {path}" if path else ""))


if __name__ == "__main__":
    main()
