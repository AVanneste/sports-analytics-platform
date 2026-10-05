"""Archive of Belgian prices just before kick-off, for closing-line value (CLV).

``scripts/collect_odds.py`` runs hourly (GitHub Actions, dispatched by cron-job.org) and appends
Kambi prices for every match kicking off within the next 75 minutes to a daily CSV on the
``odds-archive`` branch, which the daily run checks out as ``odds_archive/``. A match's closing
price is its last snapshot before kick-off, best across books.
"""
import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from football_core.config import PROJECT_ROOT
from football_core.data.kambi import ODDS_KEYS

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path(os.environ.get("ODDS_ARCHIVE_DIR", PROJECT_ROOT.parent / "odds_archive" / "snapshots"))
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
    if not rows:
        return None
    path = archive_dir / f"{rows[0]['captured_at'][:10]}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)
    return path


def load_snapshots(days: Iterable[str], archive_dir: Path = ARCHIVE_DIR) -> pd.DataFrame:
    frames = [pd.read_csv(archive_dir / f"{d}.csv") for d in sorted(set(days)) if (archive_dir / f"{d}.csv").exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def closing_prices(snapshots: pd.DataFrame) -> Dict[int, Dict]:
    """Kambi event id -> {best price per selection at the last snapshot before kick-off, captured_at}."""
    if snapshots.empty:
        return {}
    df = snapshots[snapshots["captured_at"] < snapshots["start"]]
    df = df[df["captured_at"] == df.groupby("event_id")["captured_at"].transform("max")]
    closing = {}
    for event_id, group in df.groupby("event_id"):
        best = {k: float(group[k].max()) for k in ODDS_KEYS if group[k].notna().any()}
        if {"odds_home", "odds_draw", "odds_away"} <= set(best):
            closing[int(event_id)] = {**best, "captured_at": group["captured_at"].iloc[0],
                                      "books": sorted(group["book"].unique())}
    return closing


def recent_closing_prices(today: Optional[datetime] = None, days: int = 4, archive_dir: Path = ARCHIVE_DIR) -> Dict[int, Dict]:
    """Closing prices for matches captured over the last ``days`` days."""
    today = today or datetime.now(timezone.utc)
    return closing_prices(load_snapshots([(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)],
                                         archive_dir))
