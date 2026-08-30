"""Automated 48-hour data sync and model retraining pipeline."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from tennis_core.config import RAW_DATA_DIR, UPCOMING_DATA_DIR, MODELS_DIR
from tennis_core.data.fetcher import download_tennis_data_year
from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
from tennis_core.data.scraper import fetch_live_upcoming_fixtures, load_upcoming_matches
from tennis_core.features.builder import TennisFeaturePipeline
from tennis_core.models.train import train_tennis_model, save_trained_pipeline

logger = logging.getLogger(__name__)

METADATA_FILE = UPCOMING_DATA_DIR / "update_metadata.json"
MAX_AGE_SECONDS = 48 * 3600  # 48 hours threshold


def get_update_metadata() -> Dict:
    """Read data update timestamps and record counts."""
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_upcoming_update": 0,
        "last_historical_update": 0,
        "last_upcoming_update_iso": "Never",
        "last_historical_update_iso": "Never",
        "historical_atp_matches": 0,
        "historical_wta_matches": 0,
    }


def save_update_metadata(metadata: Dict):
    """Save updated timestamps and metadata."""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def is_older_than_48h(timestamp: float) -> bool:
    """Check if a unix timestamp is older than 48 hours."""
    if not timestamp or timestamp <= 0:
        return True
    return (time.time() - timestamp) > MAX_AGE_SECONDS


def retrain_circuit_pipeline(circuit: str) -> Dict:
    """Process historical matches and retrain pipeline + model for a circuit."""
    logger.info(f"Retraining {circuit.upper()} pipeline with updated matches...")
    raw_df = load_raw_matches(circuit)
    clean_df = clean_match_data(raw_df, circuit)

    pipeline = TennisFeaturePipeline(circuit=circuit)
    X, y = pipeline.process_historical_matches(clean_df)

    model, metrics = train_tennis_model(X, y, circuit=circuit)
    save_trained_pipeline(pipeline, model, metrics, circuit=circuit)

    logger.info(f"{circuit.upper()} pipeline retrained on {len(clean_df)} matches. Acc: {metrics['accuracy']}%")
    return {"matches": len(clean_df), "metrics": metrics}



def update_historical_data_if_stale(force: bool = False) -> Dict:
    """
    Check if historical match data (2026) is older than 48h.
    If stale, download latest files from Tennis-Data.co.uk and retrain if updated.
    """
    meta = get_update_metadata()
    current_year = datetime.now().year
    
    # Check file modification time of current year raw files
    atp_raw = RAW_DATA_DIR / f"atp_{current_year}.xlsx"
    wta_raw = RAW_DATA_DIR / f"wta_{current_year}.xlsx"

    last_check = meta.get("last_historical_update", 0)
    should_update = force or is_older_than_48h(last_check)

    if not should_update and atp_raw.exists() and wta_raw.exists():
        logger.info("Historical datasets are within 48h freshness window.")
        return {"updated": False, "reason": "Fresh (less than 48h old)"}

    logger.info("Historical data is older than 48h or force update requested. Fetching newest 2026 data...")
    p1 = download_tennis_data_year("atp", current_year, force=True)
    p2 = download_tennis_data_year("wta", current_year, force=True)

    # Check if match counts increased
    retrained = False
    try:
        atp_res = retrain_circuit_pipeline("atp")
        wta_res = retrain_circuit_pipeline("wta")
        meta["historical_atp_matches"] = atp_res["matches"]
        meta["historical_wta_matches"] = wta_res["matches"]
        retrained = True
    except Exception as e:
        logger.warning(f"Error during pipeline retraining: {e}")

    now_ts = time.time()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta["last_historical_update"] = now_ts
    meta["last_historical_update_iso"] = now_iso
    save_update_metadata(meta)

    return {
        "updated": True,
        "retrained": retrained,
        "timestamp_iso": now_iso,
        "atp_matches": meta.get("historical_atp_matches", 0),
        "wta_matches": meta.get("historical_wta_matches", 0),
    }


def update_upcoming_fixtures_if_stale(force: bool = False) -> Dict:
    """
    Check if upcoming fixtures cache is older than 48h.
    If stale, query The Odds API and update local fixtures.
    """
    meta = get_update_metadata()
    last_check = meta.get("last_upcoming_update", 0)
    upcoming_file = UPCOMING_DATA_DIR / "upcoming_matches.json"

    file_mtime = upcoming_file.stat().st_mtime if upcoming_file.exists() else 0
    effective_last = max(last_check, file_mtime)

    if not force and not is_older_than_48h(effective_last) and upcoming_file.exists():
        logger.info("Upcoming matches feed is within 48h freshness window.")
        return {"updated": False, "reason": "Fresh (less than 48h old)"}

    logger.info("Upcoming matches data is older than 48h or forced. Syncing live fixtures...")
    try:
        matches = fetch_live_upcoming_fixtures()
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        meta["last_upcoming_update"] = now_ts
        meta["last_upcoming_update_iso"] = now_iso
        meta["upcoming_matches_count"] = len(matches)
        save_update_metadata(meta)
        return {"updated": True, "count": len(matches), "timestamp_iso": now_iso}
    except Exception as e:
        logger.warning(f"Error updating upcoming fixtures: {e}")
        return {"updated": False, "error": str(e)}


def check_and_auto_update(force: bool = False) -> Dict:
    """
    Master 48-hour auto-updater:
    1. Checks & syncs upcoming odds/fixtures if > 48h old.
    2. Checks & downloads historical match results if > 48h old.
    """
    up_res = update_upcoming_fixtures_if_stale(force=force)
    hist_res = update_historical_data_if_stale(force=force)
    return {
        "upcoming": up_res,
        "historical": hist_res,
        "metadata": get_update_metadata(),
    }
