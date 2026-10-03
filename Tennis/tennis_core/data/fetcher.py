"""Data fetcher for ATP and WTA historical match records and betting odds from Tennis-Data.co.uk."""
import logging
from pathlib import Path
from typing import List, Optional
import requests

from tennis_core.config import RAW_DATA_DIR, START_YEAR, END_YEAR, CIRCUITS

logger = logging.getLogger(__name__)

TENNIS_DATA_URLS = {
    "atp": "https://tennis-data.co.uk/{year}/{year}.xlsx",
    "wta": "https://tennis-data.co.uk/{year}w/{year}.xlsx",
}


def _is_xlsx(content: bytes) -> bool:
    """tennis-data.co.uk files are .xlsx (ZIP containers); 404/error pages are HTML."""
    return content[:4] == b"PK\x03\x04"


def _keep_valid(target_path: Path) -> Optional[Path]:
    """The previously downloaded file, if it is a real spreadsheet."""
    if target_path.exists() and _is_xlsx(target_path.read_bytes()[:4]):
        return target_path
    return None


def _write_atomic(target_path: Path, content: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(target_path)


def download_tennis_data_year(circuit: str, year: int, force: bool = False) -> Optional[Path]:
    """Download single year spreadsheet for ATP or WTA (never saves an HTML error page as data)."""
    circuit = circuit.lower()
    target_path = RAW_DATA_DIR / f"{circuit}_{year}.xlsx"
    
    if not force and _keep_valid(target_path):
        logger.info(f"Using cached {target_path.name}")
        return target_path

    url_template = TENNIS_DATA_URLS.get(circuit)
    if not url_template:
        return None
        
    url = url_template.format(year=year)
    try:
        logger.info(f"Downloading {circuit.upper()} {year}: {url}...")
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200 and _is_xlsx(resp.content):
            _write_atomic(target_path, resp.content)
            logger.info(f"Saved {target_path.name} ({len(resp.content)} bytes)")
            return target_path
        logger.warning(f"{url} returned HTTP {resp.status_code} without a spreadsheet")
        return _keep_valid(target_path)
    except Exception as e:
        logger.debug(f"Requests failed for {url}: {e}, trying curl fallback...")

    # Fallback to curl
    try:
        import subprocess
        cmd = ["curl", "-fsL", "-A", "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0", url]
        res = subprocess.run(cmd, capture_output=True, timeout=35)
        if res.returncode == 0 and _is_xlsx(res.stdout):
            _write_atomic(target_path, res.stdout)
            logger.info(f"Saved {target_path.name} via curl ({len(res.stdout)} bytes)")
            return target_path
        logger.warning(f"Failed to fetch {circuit} {year} from {url}")
        return _keep_valid(target_path)
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return _keep_valid(target_path)


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

