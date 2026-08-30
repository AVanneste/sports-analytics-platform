"""Auto-update routines to keep football datasets and models fresh."""
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any

from football_core.config import LEAGUES, CACHE_DIR, PROCESSED_DATA_DIR
from football_core.data.fetcher import download_league_season
from football_core.data.preprocessor import clean_match_data, load_raw_league_data, save_processed_data

logger = logging.getLogger(__name__)
UPDATE_META_FILE = CACHE_DIR / "auto_update_meta.json"
MAX_DATA_AGE_HOURS = 48


def get_update_metadata() -> Dict:
    """Read metadata about the last data and model updates."""
    if UPDATE_META_FILE.exists():
        try:
            with open(UPDATE_META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_data_update": 0, "last_model_update": 0}


def save_update_metadata(meta: Dict):
    """Write update timestamps to metadata file."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(UPDATE_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write update metadata: {e}")


def check_and_auto_update(force: bool = False) -> Dict[str, Any]:
    """Check if data is older than threshold, and re-download current season."""
    meta = get_update_metadata()
    last_update = meta.get("last_data_update", 0)
    hours_since = (time.time() - last_update) / 3600.0

    if not force and hours_since < MAX_DATA_AGE_HOURS:
        logger.info(f"Data is up to date (updated {hours_since:.1f}h ago).")
        return {"updated": False, "total_leagues_updated": 0, "message": "Data already up to date"}

    logger.info("Updating current football season data for all national leagues...")
    current_season = "2425"
    leagues_updated = 0

    for league_key, league_info in LEAGUES.items():
        if league_info.get("is_cup"):
            continue
        p = download_league_season(league_key, current_season, force=True)
        if p:
            raw_df = load_raw_league_data(league_key)
            if not raw_df.empty:
                cleaned = clean_match_data(raw_df, league_key)
                if not cleaned.empty:
                    save_processed_data(cleaned, league_key)
                    leagues_updated += 1

    meta["last_data_update"] = time.time()
    save_update_metadata(meta)
    return {
        "updated": bool(leagues_updated > 0),
        "total_leagues_updated": leagues_updated,
        "message": f"Successfully updated {leagues_updated} leagues",
    }
