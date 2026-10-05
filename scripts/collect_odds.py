"""Snapshot Belgian prices for matches kicking off soon (run hourly by .github/workflows/odds_collector.yml).

    python scripts/collect_odds.py [--within-minutes 75] [--out odds_archive/snapshots]

Every Kambi league we model is read for Unibet.be and Bingoal; matches starting within the window
get their full prices (1X2, O/U 2.5, BTTS, corners 9.5) appended to the day's CSV. The last
snapshot before kick-off is the closing price used for CLV.
"""
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from football_core.data.kambi import KAMBI_PATHS, fetch_league_prices
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
    path = append_snapshot(snapshot_rows(events, now), args.out)
    print(f"{len(events)} matches kicking off within {args.within_minutes:.0f} min" + (f" -> {path}" if path else ""))


if __name__ == "__main__":
    main()
