"""Archive of Belgian prices just before kick-off, for closing-line value (CLV).

``scripts/collect_odds.py`` runs hourly (GitHub Actions, dispatched by cron-job.org) and appends
Napoleon, Unibet and Bingoal prices for every match kicking off within the next 75 minutes to a daily CSV on the
``odds-archive`` branch, which the daily run checks out as ``odds_archive/``. A match's closing
price is its last snapshot before kick-off: Napoleon's, else the best of Unibet and Bingoal.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from football_core.data.kambi import ODDS_KEYS
from sports_common.belgian_prices import choose_prices
from sports_common.odds_archive import ARCHIVE_ROOT, append_rows, last_before_start, load_days

logger = logging.getLogger(__name__)

ARCHIVE_DIR = ARCHIVE_ROOT
COLUMNS = ["captured_at", "league", "event_id", "start", "home_team", "away_team", "book", *ODDS_KEYS]


def snapshot_rows(events: Iterable[Dict], captured_at: datetime) -> List[Dict]:
    """One row per match and book (from ``kambi.fetch_league_prices`` events)."""
    stamp = captured_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"captured_at": stamp, "league": e["league"], "event_id": e["event_id"], "start": e["start"],
             "home_team": e["home_team"], "away_team": e["away_team"], "book": book,
             **{k: odds.get(k) for k in ODDS_KEYS}}
            for e in events for book, odds in e["books"].items()]


def append_snapshot(rows: List[Dict], archive_dir: Path = ARCHIVE_DIR) -> Optional[Path]:
    """Append rows to the capture day's CSV; returns its path (None without rows)."""
    return append_rows(rows, COLUMNS, archive_dir)


def load_snapshots(days: Iterable[str], archive_dir: Path = ARCHIVE_DIR) -> pd.DataFrame:
    return load_days(days, COLUMNS, archive_dir)


def closing_prices(snapshots: pd.DataFrame) -> Dict[int, Dict]:
    """Kambi event id -> {price per selection at the last snapshot before kick-off (Napoleon first,
    else the best of Unibet and Bingoal, as for the prices bets are placed at), captured_at}."""
    if snapshots.empty:
        return {}
    closing = {}
    for event_id, group in last_before_start(snapshots).groupby("event_id"):
        books = {row["book"]: {k: float(row[k]) for k in ODDS_KEYS if pd.notna(row[k])} for _, row in group.iterrows()}
        prices, sources, _ = choose_prices(books)
        if {"odds_home", "odds_draw", "odds_away"} <= set(prices):
            closing[int(event_id)] = {**prices, "captured_at": group["captured_at"].iloc[0],
                                      "books": sorted(books), "price_books": sources}
    return closing


def recent_closing_prices(today: Optional[datetime] = None, days: int = 4, archive_dir: Path = ARCHIVE_DIR) -> Dict[int, Dict]:
    """Closing prices for matches captured over the last ``days`` days."""
    today = today or datetime.now(timezone.utc)
    return closing_prices(load_snapshots([(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)],
                                         archive_dir))
