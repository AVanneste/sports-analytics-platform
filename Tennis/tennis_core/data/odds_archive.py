"""Tennis closing prices: the hourly collector's snapshots (``snapshots/tennis/<day>.csv`` on the
``odds-archive`` branch), keyed by Kambi match id and in Kambi's player order. A match's closing
price is its last snapshot before the start: Napoleon's, else the best of Unibet and Bingoal.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from sports_common.belgian_prices import choose_prices
from sports_common.odds_archive import ARCHIVE_ROOT, append_rows, last_before_start, load_days
from tennis_core.data.kambi_tennis import _same_player

ARCHIVE_DIR = ARCHIVE_ROOT / "tennis"
COLUMNS = ["captured_at", "circuit", "event_id", "start", "p1_name", "p2_name", "book", "p1_odds", "p2_odds"]


def pair_napoleon(kambi_events: List[Dict], napoleon_events: List[Dict]) -> int:
    """Add Napoleon's prices to the Kambi match they are (in Kambi's player order, in place)."""
    paired = 0
    for n in napoleon_events:
        odds = n["books"]["napoleon"]
        for k in kambi_events:
            if str(k["start"])[:10] != str(n["start"])[:10]:
                continue
            if _same_player(k["p1_name"], n["p1_name"]) and _same_player(k["p2_name"], n["p2_name"]):
                k["books"]["napoleon"] = dict(odds)
            elif _same_player(k["p1_name"], n["p2_name"]) and _same_player(k["p2_name"], n["p1_name"]):
                k["books"]["napoleon"] = {"p1_odds": odds["p2_odds"], "p2_odds": odds["p1_odds"]}
            else:
                continue
            paired += 1
            break
    return paired


def snapshot_rows(events: Iterable[Dict], captured_at: datetime) -> List[Dict]:
    stamp = captured_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"captured_at": stamp, "circuit": e.get("circuit"), "event_id": e["event_id"], "start": e["start"],
             "p1_name": e["p1_name"], "p2_name": e["p2_name"], "book": book,
             "p1_odds": odds.get("p1_odds"), "p2_odds": odds.get("p2_odds")}
            for e in events for book, odds in e["books"].items()]


def append_snapshot(rows: List[Dict], archive_dir: Path = ARCHIVE_DIR) -> Optional[Path]:
    return append_rows(rows, COLUMNS, archive_dir)


def closing_prices(snapshots: pd.DataFrame) -> Dict[int, Dict]:
    """Kambi match id -> {p1_odds, p2_odds (Kambi's order), captured_at, price_books}."""
    if snapshots.empty:
        return {}
    closing = {}
    for event_id, group in last_before_start(snapshots).groupby("event_id"):
        books = {row["book"]: {k: float(row[k]) for k in ("p1_odds", "p2_odds") if pd.notna(row[k])}
                 for _, row in group.iterrows()}
        prices, sources, _ = choose_prices(books)
        if {"p1_odds", "p2_odds"} <= set(prices):
            closing[int(event_id)] = {**prices, "captured_at": group["captured_at"].iloc[0], "price_books": sources}
    return closing


def recent_closing_prices(today: Optional[datetime] = None, days: int = 4, archive_dir: Path = ARCHIVE_DIR) -> Dict[int, Dict]:
    today = today or datetime.now(timezone.utc)
    return closing_prices(load_days([(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)],
                                    COLUMNS, archive_dir))
