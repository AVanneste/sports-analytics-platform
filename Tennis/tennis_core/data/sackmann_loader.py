"""Jeff Sackmann match-level serve/return statistics (download, cache, leak-free rolling averages)."""
import logging
import math
import time
import os
from collections import deque
from datetime import date
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple
import pandas as pd
import requests

from tennis_core.utils.helpers import normalize_player_name

logger = logging.getLogger(__name__)

CACHE_DIR = str(Path(__file__).resolve().parents[2] / "data" / "sackmann")

def download_sackmann_data(circuit: str, years: List[int]) -> pd.DataFrame:
    """
    Downloads and concatenates Sackmann CSVs for a given circuit (ATP/WTA) and years.
    """
    dfs = []
    circuit_lower = circuit.lower()
    if circuit_lower == 'atp':
        base_url = "https://raw.githubusercontent.com/Kadantte/tennis_atp/master/atp_matches_{year}.csv"
    elif circuit_lower == 'wta':
        base_url = "https://raw.githubusercontent.com/Kadantte/tennis_wta/master/wta_matches_{year}.csv"
    else:
        logger.error(f"Unknown circuit: {circuit}")
        return pd.DataFrame()

    for year in years:
        url = base_url.format(year=year)
        try:
            logger.info(f"Downloading {circuit} data for {year} from {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Save to a temporary file or parse directly
                # Wait, pd.read_csv can read from a StringIO or BytesIO
                from io import StringIO
                df = pd.read_csv(StringIO(response.text))
                
                # Normalize player names
                if 'winner_name' in df.columns:
                    df['winner_name'] = df['winner_name'].apply(normalize_player_name)
                if 'loser_name' in df.columns:
                    df['loser_name'] = df['loser_name'].apply(normalize_player_name)
                    
                dfs.append(df)
            else:
                logger.warning(f"Failed to download {url}. Status code: {response.status_code}")
        except Exception as e:
            logger.warning(f"Exception downloading {url}: {e}")
        
        # Rate limit
        time.sleep(0.5)

    if not dfs:
        return pd.DataFrame()

    combined_df = pd.concat(dfs, ignore_index=True)
    
    # Cache the dataframe
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{circuit_lower}_matches.parquet")
    try:
        combined_df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {circuit} data to {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to cache {circuit} data: {e}")

    return combined_df

def load_cached_sackmann(circuit: str) -> Optional[pd.DataFrame]:
    """
    Loads Sackmann data from cache.
    """
    circuit_lower = circuit.lower()
    cache_path = os.path.join(CACHE_DIR, f"{circuit_lower}_matches.parquet")
    if os.path.exists(cache_path):
        try:
            df = pd.read_parquet(cache_path)
            logger.info(f"Loaded {circuit} data from {cache_path}")
            return df
        except Exception as e:
            logger.error(f"Failed to load cached {circuit} data from {cache_path}: {e}")
            return None
    logger.info(f"Cache file {cache_path} does not exist.")
    return None

_SERVE_COLS = ("ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "bpSaved", "bpFaced")
_RETURN_COLS = ("svpt", "1stWon", "2ndWon", "bpSaved", "bpFaced")
STAT_KEYS = ("ace_rate", "df_rate", "first_serve_pct", "first_serve_won_pct",
             "bp_save_pct", "bp_conversion_pct", "return_points_won_pct")


def _num(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return math.nan
    return f


def _aggregate(contributions) -> Optional[Dict[str, float]]:
    """Serve/return rates from per-match tuples (8 serve counts followed by 5 opponent serve counts)."""
    if not contributions:
        return None
    tot = [0.0] * 13
    for c in contributions:
        for i, v in enumerate(c):
            tot[i] += v
    ace, dbl, svpt, first_in, first_won, _second_won, bp_saved, bp_faced = tot[:8]
    opp_svpt, opp_first_won, opp_second_won, opp_bp_saved, opp_bp_faced = tot[8:]
    if svpt <= 0:
        return None
    return {
        "ace_rate": ace / svpt,
        "df_rate": dbl / svpt,
        "first_serve_pct": first_in / svpt,
        "first_serve_won_pct": first_won / first_in if first_in > 0 else 0.0,
        "bp_save_pct": bp_saved / bp_faced if bp_faced > 0 else 0.0,
        "bp_conversion_pct": (opp_bp_faced - opp_bp_saved) / opp_bp_faced if opp_bp_faced > 0 else 0.0,
        "return_points_won_pct": (opp_svpt - opp_first_won - opp_second_won) / opp_svpt if opp_svpt > 0 else 0.0,
    }


class SackmannRollingStats:
    """Serve/return averages over each player's last ``n_matches`` on a surface, without lookahead.

    Sackmann rows are dated by tournament START, so a row is only used once its tournament
    started at least ``lag_days`` before the query date; a shorter lag would let later rounds of
    the current event (including the match being predicted) leak into its own features.
    """

    def __init__(self, matches: pd.DataFrame, n_matches: int = 20, lag_days: int = 14):
        self.n_matches = n_matches
        self.lag = pd.Timedelta(days=lag_days)
        self._events: List[Tuple[pd.Timestamp, str, str, str, tuple, tuple]] = []
        needed = {"tourney_date", "surface", "winner_name", "loser_name"}
        if matches is not None and not matches.empty and needed.issubset(matches.columns):
            dates = pd.to_datetime(matches["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")
            for d, row in zip(dates, matches.to_dict("records")):
                if pd.isna(d):
                    continue
                w = [_num(row.get(f"w_{c}")) for c in _SERVE_COLS]
                l = [_num(row.get(f"l_{c}")) for c in _SERVE_COLS]
                if not (w[2] > 0 and l[2] > 0):  # serve points missing or zero: no usable stats
                    continue
                w = [0.0 if math.isnan(v) else v for v in w]
                l = [0.0 if math.isnan(v) else v for v in l]
                w_ret = tuple(l[i] for i in (2, 4, 5, 6, 7))
                l_ret = tuple(w[i] for i in (2, 4, 5, 6, 7))
                self._events.append((d, str(row.get("surface") or "").lower(),
                                     row["winner_name"], row["loser_name"],
                                     tuple(w) + w_ret, tuple(l) + l_ret))
        self._events.sort(key=lambda e: e[0])
        self._ptr = 0
        self._windows: Dict[Tuple[str, str], Deque[tuple]] = {}

    def advance_to(self, query_date: pd.Timestamp) -> None:
        """Ingest every event whose tournament started at least ``lag_days`` before ``query_date``."""
        cutoff = pd.Timestamp(query_date) - self.lag
        while self._ptr < len(self._events) and self._events[self._ptr][0] < cutoff:
            _, surface, winner, loser, w_contrib, l_contrib = self._events[self._ptr]
            for player, contrib in ((winner, w_contrib), (loser, l_contrib)):
                self._windows.setdefault((player, surface), deque(maxlen=self.n_matches)).append(contrib)
            self._ptr += 1

    def ingest_all(self) -> None:
        self.advance_to(pd.Timestamp.max - self.lag)

    def get(self, player: str, surface: str) -> Optional[Dict[str, float]]:
        return _aggregate(self._windows.get((player, str(surface).lower())))

    def snapshot(self) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Current stats for every (player, surface), small enough to pickle with the pipeline."""
        out = {}
        for key, window in self._windows.items():
            stats = _aggregate(window)
            if stats:
                out[key] = stats
        return out


def update_sackmann_data():
    """
    Main entry point for daily pipeline.
    Downloads current and recent years for ATP and WTA.
    """
    years = list(range(2019, date.today().year + 1))
    logger.info("Updating ATP data...")
    download_sackmann_data("ATP", years)
    logger.info("Updating WTA data...")
    download_sackmann_data("WTA", years)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_sackmann_data()
