"""Match data cleaning, standardization, and parquet serialization."""
import logging
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from football_core.config import RAW_DATA_DIR, PROCESSED_DATA_DIR
from football_core.utils.helpers import normalize_team_name

logger = logging.getLogger(__name__)


def load_raw_league_data(league_key: str) -> pd.DataFrame:
    """Load and concatenate all raw CSV season files for a given league."""
    league_dir = RAW_DATA_DIR / league_key
    if not league_dir.exists():
        logger.warning(f"No directory found for league: {league_key}")
        return pd.DataFrame()

    csv_files = sorted(list(league_dir.glob(f"{league_key}_*.csv")))
    if not csv_files:
        logger.warning(f"No CSV files found in {league_dir}")
        return pd.DataFrame()

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, encoding="latin1", on_bad_lines="skip", low_memory=False)
            if not df.empty and "HomeTeam" in df.columns:
                dfs.append(df)
        except Exception as e:
            logger.error(f"Error reading {f.name}: {e}")

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    logger.info(f"Loaded {len(combined)} raw match rows across {len(dfs)} seasons for {league_key}")
    return combined


def parse_dates_safely(date_series: pd.Series) -> pd.Series:
    """Safely parse various football-data date formats (DD/MM/YY, DD/MM/YYYY, YYYY-MM-DD)."""
    return pd.to_datetime(date_series, format="mixed", dayfirst=True, errors="coerce")


def clean_match_data(df: pd.DataFrame, league_key: str) -> pd.DataFrame:
    """Standardize column names, clean team names, cast types, and compute outcome targets."""
    if df.empty:
        return pd.DataFrame()

    cleaned = df.copy()

    # Drop rows without mandatory fields
    cleaned = cleaned.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "FTHG", "FTAG"])

    # Standardize Team Names
    cleaned["HomeTeam"] = cleaned["HomeTeam"].astype(str).apply(normalize_team_name)
    cleaned["AwayTeam"] = cleaned["AwayTeam"].astype(str).apply(normalize_team_name)

    # Standardize Date
    cleaned["Date"] = parse_dates_safely(cleaned["Date"])
    cleaned = cleaned.dropna(subset=["Date"])
    cleaned = cleaned.sort_values(by=["Date"]).reset_index(drop=True)

    # Cast all statistics & odds columns to numeric
    text_cols = {"HomeTeam", "AwayTeam", "FTR", "Date", "Referee", "league", "Div", "Time"}
    for col in cleaned.columns:
        if col not in text_cols:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
        else:
            if col != "Date":
                cleaned[col] = cleaned[col].astype(str)

    # Filter valid match outcomes
    cleaned = cleaned[cleaned["FTR"].isin(["H", "D", "A"])].copy()

    # Compute Target Columns
    # target_1x2: 0 = Home Win, 1 = Draw, 2 = Away Win
    outcome_map = {"H": 0, "D": 1, "A": 2}
    cleaned["target_1x2"] = cleaned["FTR"].map(outcome_map)

    # Total Goals & Over/Under 2.5
    cleaned["total_goals"] = cleaned["FTHG"] + cleaned["FTAG"]
    cleaned["target_over25"] = (cleaned["total_goals"] > 2.5).astype(int)

    # Both Teams To Score (BTTS)
    cleaned["target_btts"] = ((cleaned["FTHG"] > 0) & (cleaned["FTAG"] > 0)).astype(int)

    # Best available odds fallback
    if "B365H" in cleaned.columns and "AvgH" in cleaned.columns:
        cleaned["odds_home"] = cleaned["B365H"].fillna(cleaned["AvgH"])
        cleaned["odds_draw"] = cleaned["B365D"].fillna(cleaned["AvgD"])
        cleaned["odds_away"] = cleaned["B365A"].fillna(cleaned["AvgA"])
    elif "AvgH" in cleaned.columns:
        cleaned["odds_home"] = cleaned["AvgH"]
        cleaned["odds_draw"] = cleaned["AvgD"]
        cleaned["odds_away"] = cleaned["AvgA"]
    else:
        cleaned["odds_home"] = np.nan
        cleaned["odds_draw"] = np.nan
        cleaned["odds_away"] = np.nan

    cleaned["league"] = league_key
    logger.info(f"Cleaned {len(cleaned)} matches for {league_key} (from {cleaned['Date'].min().strftime('%Y-%m-%d')} to {cleaned['Date'].max().strftime('%Y-%m-%d')})")
    
    return cleaned


def save_processed_data(df: pd.DataFrame, league_key: str) -> Path:
    """Save cleaned dataframe to processed directory."""
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DATA_DIR / f"{league_key}_clean.parquet"
    
    # Ensure all string columns are clean pyarrow strings
    save_df = df.copy()
    for col in save_df.select_dtypes(include=["object"]).columns:
        save_df[col] = save_df[col].astype(str)

    save_df.to_parquet(out_path, index=False)
    logger.info(f"Saved processed data to {out_path.name}")
    return out_path


def load_processed_league_data(league_key: str) -> pd.DataFrame:
    """Load processed parquet data for a league."""
    file_path = PROCESSED_DATA_DIR / f"{league_key}_clean.parquet"
    if file_path.exists():
        try:
            return pd.read_parquet(file_path)
        except Exception as e:
            logger.error(f"Error loading {file_path.name}: {e}")
    return pd.DataFrame()
