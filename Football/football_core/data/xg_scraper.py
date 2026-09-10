import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Map Understat league names to project's league keys
LEAGUE_MAPPING = {
    'EPL': 'EPL',
    'La_Liga': 'LaLiga',
    'Serie_A': 'SerieA',
    'Bundesliga': 'Bundesliga',
    'Ligue_1': 'Ligue1'
}

# Mapping for common mismatches
TEAM_MAPPING = {
    'Manchester United': 'Man United',
    'Manchester City': 'Man City',
    'Newcastle United': 'Newcastle',
    'Wolverhampton Wanderers': 'Wolves',
    'Tottenham Hotspur': 'Tottenham',
    'West Ham United': 'West Ham',
    'Brighton & Hove Albion': 'Brighton',
    'Nottingham Forest': 'Nott\'m Forest',
    'Sheffield United': 'Sheffield Weds', # example
    # add other mappings if necessary
}

CACHE_DIR = Path('/home/antoine/Code/AG_sports_data/Football/data/xg')

def load_cached_xg(league_key: str) -> Optional[pd.DataFrame]:
    """Loads cached xG data for a given league."""
    cache_path = CACHE_DIR / f"{league_key}_xg.parquet"
    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load cache from {cache_path}: {e}")
            return None
    return None

def _save_cache(df: pd.DataFrame, league_key: str):
    """Saves DataFrame to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{league_key}_xg.parquet"
    try:
        df.to_parquet(cache_path, index=False)
        logger.info(f"Saved {len(df)} records to {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to save cache to {cache_path}: {e}")

def scrape_league_xg(league_name: str, season: int) -> pd.DataFrame:
    """Scrapes match-level xG data for a given league and season from Understat."""
    if league_name not in LEAGUE_MAPPING:
        logger.warning(f"League {league_name} not supported.")
        return pd.DataFrame()
        
    url = f"https://understat.com/league/{league_name}/{season}"
    logger.info(f"Scraping Understat for {league_name} season {season}")
    
    try:
        # Rate limiting: wait 1 second minimum
        time.sleep(1)
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch data from {url}: {e}")
        return pd.DataFrame()
        
    html = response.text
    # Parse JSON from datesData using regex
    match = re.search(r"var datesData\s*=\s*JSON\.parse\('([^']+)'\)", html)
    if not match:
        logger.warning(f"Could not find datesData in HTML from {url}")
        return pd.DataFrame()
        
    try:
        # Understat uses unicode escape sequences in JSON.parse('...')
        json_data = match.group(1).encode('utf-8').decode('unicode_escape')
        dates_data = json.loads(json_data)
    except Exception as e:
        logger.warning(f"Failed to parse datesData JSON from {url}: {e}")
        return pd.DataFrame()
        
    records = []
    # datesData is a list of match dictionaries
    for match_info in dates_data:
        try:
            date = match_info.get('datetime', '').split(' ')[0]
            home_team = match_info.get('h', {}).get('title', '')
            away_team = match_info.get('a', {}).get('title', '')
            
            # xG fields can be missing or null for unplayed matches
            home_xg = match_info.get('xG', {}).get('h')
            away_xg = match_info.get('xG', {}).get('a')
            home_goals = match_info.get('goals', {}).get('h')
            away_goals = match_info.get('goals', {}).get('a')
            
            # Skip unplayed matches where xG or goals is None
            if home_xg is None or away_xg is None or home_goals is None or away_goals is None:
                continue
                
            home_xg = float(home_xg)
            away_xg = float(away_xg)
            home_goals = int(home_goals)
            away_goals = int(away_goals)
            
            # Apply team name mappings
            home_team = TEAM_MAPPING.get(home_team, home_team)
            away_team = TEAM_MAPPING.get(away_team, away_team)
            
            records.append({
                'date': date,
                'home_team': home_team,
                'away_team': away_team,
                'home_xg': home_xg,
                'away_xg': away_xg,
                'home_goals': home_goals,
                'away_goals': away_goals
            })
        except Exception as e:
            logger.warning(f"Error parsing match record: {e}")
            
    df = pd.DataFrame(records)
    if df.empty:
         # Return empty dataframe with correct columns
         df = pd.DataFrame(columns=['date', 'home_team', 'away_team', 'home_xg', 'away_xg', 'home_goals', 'away_goals'])
    else:
        df['date'] = pd.to_datetime(df['date']).dt.date
        
    return df

def scrape_all_leagues_xg(seasons: List[int] = None) -> Dict[str, pd.DataFrame]:
    """Scrapes all supported leagues for given seasons."""
    if seasons is None:
        # Default to previous and current year for updates
        from datetime import datetime
        current_year = datetime.now().year
        seasons = [current_year - 1, current_year]
        
    all_data = {}
    for league_name, league_key in LEAGUE_MAPPING.items():
        league_dfs = []
        for season in seasons:
            df = scrape_league_xg(league_name, season)
            if not df.empty:
                league_dfs.append(df)
                
        if league_dfs:
            combined_df = pd.concat(league_dfs, ignore_index=True)
            all_data[league_key] = combined_df
        else:
            all_data[league_key] = pd.DataFrame(columns=['date', 'home_team', 'away_team', 'home_xg', 'away_xg', 'home_goals', 'away_goals'])
            
    return all_data

def update_xg_data():
    """Main entry point for daily pipeline: scrapes latest season for all leagues, merges with cache."""
    import datetime
    # The football season year generally refers to the year it started.
    current_year = datetime.datetime.now().year
    month = datetime.datetime.now().month
    # If before July, the current season started last year.
    latest_season = current_year if month >= 7 else current_year - 1
    
    logger.info(f"Updating xG data starting from season {latest_season}...")
    new_data = scrape_all_leagues_xg(seasons=[latest_season])
    
    for league_name, league_key in LEAGUE_MAPPING.items():
        new_df = new_data.get(league_key, pd.DataFrame())
        cached_df = load_cached_xg(league_key)
        
        if cached_df is not None and not cached_df.empty:
            if not new_df.empty:
                # Merge logic - concat and drop duplicates
                combined_df = pd.concat([cached_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
                # Sort by date
                combined_df = combined_df.sort_values('date')
                _save_cache(combined_df, league_key)
        else:
            if not new_df.empty:
                new_df = new_df.sort_values('date')
                _save_cache(new_df, league_key)
                
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    update_xg_data()
