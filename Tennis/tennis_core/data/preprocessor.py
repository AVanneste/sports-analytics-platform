"""Data preprocessing and normalization for historical tennis matches and odds."""
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from tennis_core.config import RAW_DATA_DIR, PRIMARY_SURFACES, START_YEAR, END_YEAR
from tennis_core.utils.helpers import normalize_player_name, normalize_surface

logger = logging.getLogger(__name__)


def load_raw_matches(circuit: str, start_year: int = START_YEAR, end_year: int = END_YEAR,
                     include_espn: bool = True) -> pd.DataFrame:
    """Load raw excel / csv files for a given circuit (ATP or WTA) for the specified year range.

    With ``include_espn``, ESPN results (data/espn_results.py) dated after the last tennis-data match
    are appended: tennis-data cannot be refreshed from the daily run's servers."""
    circuit = circuit.lower()
    
    files = []
    for y in range(start_year, end_year + 1):
        f_xlsx = RAW_DATA_DIR / f"{circuit}_{y}.xlsx"
        f_csv = RAW_DATA_DIR / f"{circuit}_{y}.csv"
        if f_xlsx.exists():
            files.append(f_xlsx)
        elif f_csv.exists():
            files.append(f_csv)

    if not files:
        logger.warning(f"No match files found for {circuit.upper()} ({start_year}-{end_year}) in {RAW_DATA_DIR}")
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            if f.suffix == ".xlsx":
                df = pd.read_excel(f)
            else:
                df = pd.read_csv(f, low_memory=False)
            dfs.append(df)
        except Exception as e:
            logger.warning(f"Error loading {f.name}: {e}")

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    if include_espn:
        combined = _append_espn_results(combined, circuit, end_year)
    logger.info(f"Loaded {len(combined)} raw matches for {circuit.upper()} ({start_year}-{end_year})")
    return combined


def _surname_key(name) -> str:
    """'Davidovich Fokina A.' -> 'davidovich fokina': names minus the initials, for cross-source matching."""
    parts = str(name).replace(".", " ").split()
    keep = [p for p in parts if len(p) > 1] or parts
    return " ".join(keep).lower()


def _append_espn_results(combined: pd.DataFrame, circuit: str, end_year: int) -> pd.DataFrame:
    """Append ESPN results tennis-data does not have yet (same two surnames within two days = same match).

    tennis-data adds a tournament only once it ends, so its file can stop at a date while events
    that started earlier are still missing; matching per match rather than by date keeps those."""
    from tennis_core.data.espn_results import espn_results_path
    path = espn_results_path(circuit)
    if not path.exists() or combined.empty:
        return combined
    espn = pd.read_csv(path)
    espn_dates = pd.to_datetime(espn["Date"], errors="coerce")
    espn = espn[espn_dates.dt.year <= end_year].assign(_date=espn_dates)
    if espn.empty:
        return combined
    td_dates = pd.to_datetime(combined["Date"], errors="coerce")
    recent = combined[td_dates >= espn["_date"].min() - pd.Timedelta(days=3)]
    seen = {}
    for when, w, l in zip(pd.to_datetime(recent["Date"], errors="coerce"), recent["Winner"], recent["Loser"]):
        seen.setdefault(frozenset((_surname_key(w), _surname_key(l))), []).append(when)
    new = [i for i, (when, w, l) in enumerate(zip(espn["_date"], espn["Winner"], espn["Loser"]))
           if not any(abs((when - d).days) <= 2 for d in seen.get(frozenset((_surname_key(w), _surname_key(l))), []))]
    if not new:
        return combined
    add = espn.iloc[new].drop(columns="_date")
    logger.info(f"Adding {len(add)} ESPN {circuit.upper()} results that tennis-data does not have yet")
    return pd.concat([combined, add], ignore_index=True)


def played_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop walkovers and awarded matches: never played, so they say nothing about the players."""
    if df.empty or "Comment" not in df.columns:
        return df
    return df[~df["Comment"].astype(str).str.strip().str.lower().isin(["walkover", "awarded"])]


def clean_match_data(df: pd.DataFrame, circuit: str, start_year: int = START_YEAR) -> pd.DataFrame:
    """Clean, filter (matches from ``start_year`` on), and format tennis match records."""
    if df.empty:
        return df

    data = df.copy()

    # Column mapping between tennis-data format and standard format
    col_map = {
        "Winner": "winner_name",
        "Loser": "loser_name",
        "Date": "tourney_date",
        "Surface": "surface",
        "Tournament": "tourney_name",
        "Series": "tourney_level",
        "Tier": "tourney_level",
        "Round": "round",
        "WRank": "winner_rank",
        "LRank": "loser_rank",
        "WPts": "winner_rank_points",
        "LPts": "loser_rank_points",
        "Best of": "best_of",
        "B365W": "winner_odds",
        "B365L": "loser_odds",
        "PSW": "pinnacle_winner_odds",
        "PSL": "pinnacle_loser_odds",
        "MaxW": "max_winner_odds",
        "MaxL": "max_loser_odds",
    }
    
    # Rename matching columns
    for orig, standard in col_map.items():
        if orig in data.columns and standard not in data.columns:
            data = data.rename(columns={orig: standard})

    # Drop rows without essentials
    data = data.dropna(subset=["winner_name", "loser_name", "tourney_date"])

    # Clean player names
    data["winner_name"] = data["winner_name"].apply(normalize_player_name)
    data["loser_name"] = data["loser_name"].apply(normalize_player_name)

    # Standardize surfaces
    data["surface"] = data["surface"].apply(normalize_surface)

    # Parse Dates
    data["tourney_date"] = pd.to_datetime(data["tourney_date"], errors="coerce")
    data = data.dropna(subset=["tourney_date"])

    # Standardize tournament level
    if "tourney_level" not in data.columns:
        data["tourney_level"] = "A"
    else:
        def map_level(x):
            if not isinstance(x, str):
                return "A"
            xl = x.lower()
            if "grand slam" in xl:
                return "G"
            elif "master" in xl or "1000" in xl:
                return "M"
            elif "challenger" in xl:
                return "C"
            elif "finals" in xl:
                return "F"
            return "A"
        data["tourney_level"] = data["tourney_level"].apply(map_level)

    # Clean Rankings
    data["winner_rank"] = pd.to_numeric(data.get("winner_rank"), errors="coerce").fillna(250.0)
    data["loser_rank"] = pd.to_numeric(data.get("loser_rank"), errors="coerce").fillna(250.0)
    
    # Construct score string if W1, L1, etc. exist
    def construct_score(row):
        score_parts = []
        for s in range(1, 6):
            w_col = f"W{s}"
            l_col = f"L{s}"
            if w_col in row and l_col in row and pd.notna(row[w_col]) and pd.notna(row[l_col]):
                try:
                    score_parts.append(f"{int(row[w_col])}-{int(row[l_col])}")
                except (ValueError, TypeError):
                    pass
        return " ".join(score_parts) if score_parts else None  # walkovers etc.: no score, not an invented one

    if "score" not in data.columns:
        data["score"] = data.apply(construct_score, axis=1)

    # Clean Odds
    if "winner_odds" in data.columns:
        data["winner_odds"] = pd.to_numeric(data["winner_odds"], errors="coerce")
    if "loser_odds" in data.columns:
        data["loser_odds"] = pd.to_numeric(data["loser_odds"], errors="coerce")

    # Sort chronologically
    data = data[data["tourney_date"] >= f"{start_year}-01-01"]

    data = data.sort_values(by="tourney_date", kind="mergesort").reset_index(drop=True)
    data["circuit"] = circuit.lower()

    logger.info(f"Cleaned {len(data)} matches for {circuit.upper()} from {data['tourney_date'].min().date()} to {data['tourney_date'].max().date()}")
    return data

