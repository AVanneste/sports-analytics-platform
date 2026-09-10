import logging
import time
import os
from typing import List, Dict, Optional
import pandas as pd
import requests

from tennis_core.utils.helpers import normalize_player_name

logger = logging.getLogger(__name__)

CACHE_DIR = "/home/antoine/Code/AG_sports_data/Tennis/data/sackmann"

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

def compute_player_serve_return_stats(matches_df: pd.DataFrame, player_name: str, surface: Optional[str] = None, n_matches: int = 20) -> Dict[str, float]:
    """
    Computes rolling serve/return averages for a player.
    """
    if matches_df.empty:
        return {}

    # Filter by surface if provided
    if surface:
        # Depending on surface normalization
        # Simple string match for now
        matches_df = matches_df[matches_df['surface'].str.lower() == surface.lower()].copy()

    # Get matches involving the player
    player_matches = matches_df[
        (matches_df['winner_name'] == player_name) | (matches_df['loser_name'] == player_name)
    ].copy()

    if player_matches.empty:
        return {}

    # Sort by date
    if 'tourney_date' in player_matches.columns:
        player_matches = player_matches.sort_values(by='tourney_date', ascending=False)
    
    # Get last n_matches
    player_matches = player_matches.head(n_matches)

    # Initialize stats accumulators
    total_aces = 0
    total_dfs = 0
    total_svpt = 0
    total_1st_in = 0
    total_1st_won = 0
    total_2nd_won = 0
    total_bp_saved = 0
    total_bp_faced = 0
    
    total_return_svpt = 0
    total_return_pt_won = 0
    total_return_bp_won = 0
    total_return_bp_faced = 0 # break points the player had on opponent's serve

    for _, row in player_matches.iterrows():
        is_winner = (row['winner_name'] == player_name)
        
        prefix = 'w_' if is_winner else 'l_'
        opp_prefix = 'l_' if is_winner else 'w_'

        # Serve stats
        ace = row.get(f'{prefix}ace', pd.NA)
        df = row.get(f'{prefix}df', pd.NA)
        svpt = row.get(f'{prefix}svpt', pd.NA)
        fst_in = row.get(f'{prefix}1stIn', pd.NA)
        fst_won = row.get(f'{prefix}1stWon', pd.NA)
        snd_won = row.get(f'{prefix}2ndWon', pd.NA)
        bp_saved = row.get(f'{prefix}bpSaved', pd.NA)
        bp_faced = row.get(f'{prefix}bpFaced', pd.NA)

        # Opponent serve stats (for return stats)
        opp_svpt = row.get(f'{opp_prefix}svpt', pd.NA)
        opp_fst_won = row.get(f'{opp_prefix}1stWon', pd.NA)
        opp_snd_won = row.get(f'{opp_prefix}2ndWon', pd.NA)
        opp_bp_saved = row.get(f'{opp_prefix}bpSaved', pd.NA)
        opp_bp_faced = row.get(f'{opp_prefix}bpFaced', pd.NA)

        # Skip if basic serve stats are missing
        if pd.isna(svpt) or pd.isna(opp_svpt) or svpt == 0 or opp_svpt == 0:
            continue

        total_aces += ace if not pd.isna(ace) else 0
        total_dfs += df if not pd.isna(df) else 0
        total_svpt += svpt
        total_1st_in += fst_in if not pd.isna(fst_in) else 0
        total_1st_won += fst_won if not pd.isna(fst_won) else 0
        total_2nd_won += snd_won if not pd.isna(snd_won) else 0
        total_bp_saved += bp_saved if not pd.isna(bp_saved) else 0
        total_bp_faced += bp_faced if not pd.isna(bp_faced) else 0

        # Return stats (opponent's serve)
        total_return_svpt += opp_svpt
        opp_fst_won_val = opp_fst_won if not pd.isna(opp_fst_won) else 0
        opp_snd_won_val = opp_snd_won if not pd.isna(opp_snd_won) else 0
        
        # Player return points won = Opponent total serve points - Opponent first won - Opponent second won
        total_return_pt_won += (opp_svpt - opp_fst_won_val - opp_snd_won_val)
        
        # Opponent break points saved -> break points faced by opponent, break points won by player
        opp_bp_faced_val = opp_bp_faced if not pd.isna(opp_bp_faced) else 0
        opp_bp_saved_val = opp_bp_saved if not pd.isna(opp_bp_saved) else 0
        
        total_return_bp_faced += opp_bp_faced_val
        total_return_bp_won += (opp_bp_faced_val - opp_bp_saved_val)

    stats = {}
    if total_svpt > 0:
        stats['ace_rate'] = total_aces / total_svpt
        stats['df_rate'] = total_dfs / total_svpt
        stats['first_serve_pct'] = total_1st_in / total_svpt
        
        if total_1st_in > 0:
            stats['first_serve_won_pct'] = total_1st_won / total_1st_in
        else:
            stats['first_serve_won_pct'] = 0.0
            
        second_serves = total_svpt - total_1st_in - total_dfs # Approx second serves in
        second_serves = max(1, second_serves) # Avoid div by zero
        stats['second_serve_won_pct'] = total_2nd_won / second_serves
        
    if total_bp_faced > 0:
        stats['bp_save_pct'] = total_bp_saved / total_bp_faced
    else:
        stats['bp_save_pct'] = 0.0

    if total_return_bp_faced > 0:
        stats['bp_conversion_pct'] = total_return_bp_won / total_return_bp_faced
    else:
        stats['bp_conversion_pct'] = 0.0
        
    if total_return_svpt > 0:
        stats['return_points_won_pct'] = total_return_pt_won / total_return_svpt
    else:
        stats['return_points_won_pct'] = 0.0

    return stats

def update_sackmann_data():
    """
    Main entry point for daily pipeline.
    Downloads current and recent years for ATP and WTA.
    """
    years = list(range(2019, 2027))
    logger.info("Updating ATP data...")
    download_sackmann_data("ATP", years)
    logger.info("Updating WTA data...")
    download_sackmann_data("WTA", years)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_sackmann_data()
