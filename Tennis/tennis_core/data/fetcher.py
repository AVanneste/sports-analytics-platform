"""Data fetcher for ATP and WTA historical match records and betting odds from Tennis-Data.co.uk."""
import logging
from pathlib import Path
from typing import List, Optional
import requests

from tennis_core.config import RAW_DATA_DIR, START_YEAR, END_YEAR, CIRCUITS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TENNIS_DATA_URLS = {
    "atp": "http://www.tennis-data.co.uk/{year}/{year}.xlsx",
    "wta": "http://www.tennis-data.co.uk/{year}w/{year}.xlsx",
}


def download_tennis_data_year(circuit: str, year: int, force: bool = False) -> Optional[Path]:
    """Download single year spreadsheet for ATP or WTA."""
    circuit = circuit.lower()
    target_path = RAW_DATA_DIR / f"{circuit}_{year}.xlsx"
    
    if target_path.exists() and not force and target_path.stat().st_size > 0:
        logger.info(f"Using cached {target_path.name}")
        return target_path

    url_template = TENNIS_DATA_URLS.get(circuit)
    if not url_template:
        return None
        
    url = url_template.format(year=year)
    try:
        logger.info(f"Downloading {circuit.upper()} {year}: {url}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"Saved {target_path.name} ({len(resp.content)} bytes)")
            return target_path
        else:
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return None


def fetch_all_data(start_year: int = START_YEAR, end_year: int = END_YEAR, force: bool = False) -> List[Path]:
    """Download historical match spreadsheets for all circuits and years."""
    logger.info(f"Fetching tennis datasets from {start_year} to {end_year}...")
    saved_paths = []
    for circuit in CIRCUITS:
        for year in range(start_year, end_year + 1):
            p = download_tennis_data_year(circuit, year, force=force)
            if p:
                saved_paths.append(p)
    logger.info(f"Successfully retrieved {len(saved_paths)} datasets.")
    return saved_paths


if __name__ == "__main__":
    fetch_all_data()

