"""Daily CSVs of pre-kick-off prices on the ``odds-archive`` branch (checked out as ``odds_archive/``).

Football snapshots are ``snapshots/<day>.csv``, tennis ``snapshots/tennis/<day>.csv``; see
football_core/data/odds_archive.py and tennis_core/data/odds_archive.py.
"""
import csv
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

ARCHIVE_ROOT = Path(os.environ.get("ODDS_ARCHIVE_DIR", Path(__file__).resolve().parent.parent / "odds_archive" / "snapshots"))


def append_rows(rows: List[Dict], columns: Sequence[str], archive_dir: Path) -> Optional[Path]:
    """Append rows to the capture day's CSV (day from the first row's ``captured_at``); returns its path."""
    if not rows:
        return None
    path = archive_dir / f"{rows[0]['captured_at'][:10]}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    if not new:  # a file written before a column was added: rewrite it with the wider header
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            old_header, old_rows = reader.fieldnames or [], list(reader)
        if old_header != list(columns):
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
                writer.writeheader()
                writer.writerows(old_rows)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        if new:
            writer.writeheader()
        writer.writerows(rows)
    return path


def load_days(days: Iterable[str], columns: Sequence[str], archive_dir: Path) -> pd.DataFrame:
    frames = [pd.read_csv(archive_dir / f"{d}.csv") for d in sorted(set(days)) if (archive_dir / f"{d}.csv").exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=list(columns))


def last_before_start(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Each match's rows (one per book) from its last snapshot before kick-off."""
    df = snapshots[snapshots["captured_at"] < snapshots["start"]]
    return df[df["captured_at"] == df.groupby("event_id")["captured_at"].transform("max")]
