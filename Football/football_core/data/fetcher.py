"""Historical football match data fetcher from football-data.co.uk."""
import logging
import requests
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

from football_core.config import LEAGUES, SEASONS, FOOTBALL_DATA_BASE_URL, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def download_league_season(league_key: str, season: str, force: bool = False) -> Optional[Path]:
    """Download a single season CSV for a specific league."""
    league_info = LEAGUES.get(league_key)
    if not league_info:
        logger.error(f"Unknown league key: {league_key}")
        return None

    code = league_info["code"]
    url = FOOTBALL_DATA_BASE_URL.format(season=season, code=code)
    
    league_dir = RAW_DATA_DIR / league_key
    league_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = league_dir / f"{league_key}_{season}.csv"
    if file_path.exists() and not force:
        logger.debug(f"File {file_path.name} already exists. Skipping download.")
        return file_path

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200 and len(response.content) > 100:
            with open(file_path, "wb") as f:
                f.write(response.content)
            logger.info(f"Downloaded {league_key} season {season} ({len(response.content)} bytes)")
            return file_path
        else:
            logger.warning(f"Failed to fetch {league_key} {season} from {url} (Status: {response.status_code})")
            return None
    except Exception as e:
        logger.error(f"Error downloading {league_key} season {season}: {e}")
        return None


def fetch_all_data(force: bool = False) -> Dict[str, List[Path]]:
    """Fetch historical match data for all top 5 leagues across all specified seasons."""
    downloaded = {}
    for league_key in LEAGUES.keys():
        logger.info(f"Fetching data for {LEAGUES[league_key]['name']} ({league_key})...")
        downloaded[league_key] = []
        for season in SEASONS:
            path = download_league_season(league_key, season, force=force)
            if path:
                downloaded[league_key].append(path)
    return downloaded


if __name__ == "__main__":
    fetch_all_data(force=True)

