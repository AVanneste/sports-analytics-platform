"""Data fetcher for ATP and WTA historical match records and betting odds from Tennis-Data.co.uk."""
import functools
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from tennis_core.config import RAW_DATA_DIR, START_YEAR, END_YEAR, CIRCUITS

logger = logging.getLogger(__name__)

# The page that lists the yearly spreadsheets. Since 2025 the site serves them from a directory
# whose name it chose to obscure (".../<random>/2026/2026.xlsx" instead of ".../2026/2026.xlsx"),
# so download links are read from this page rather than hard-coded.
DATA_PAGE_URL = "https://tennis-data.co.uk/data.php"
# A browser's request headers: the site sits behind Cloudflare, which refuses bare scripted requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}
_SESSION = requests.Session()  # keeps any cookie the data page sets for the file downloads
_SESSION.headers.update(HEADERS)
_LINK = re.compile(r"""href\s*=\s*['"]?([^'" >]*?(\d{4})(w?)/\d{4}\.xlsx)""", re.IGNORECASE)


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


def parse_file_links(html: str, base_url: str = DATA_PAGE_URL) -> Dict[Tuple[str, int], str]:
    """(circuit, year) -> absolute spreadsheet URL, from the data page's links ("2026w/" is WTA)."""
    links = {}
    for href, year, wta in _LINK.findall(html):
        links[("wta" if wta else "atp", int(year))] = urljoin(base_url, href)
    return links


@functools.lru_cache(maxsize=1)
def file_links() -> Dict[Tuple[str, int], str]:
    """The data page's current download links (fetched once per process)."""
    resp = _SESSION.get(DATA_PAGE_URL, timeout=30)
    if resp.status_code != 200:
        blocked = "cloudflare" in resp.headers.get("server", "").lower()
        raise requests.HTTPError(f"{DATA_PAGE_URL} returned HTTP {resp.status_code}"
                                 + (" (Cloudflare refused the request)" if blocked else ""), response=resp)
    links = parse_file_links(resp.text, resp.url)
    if not links:
        logger.warning(f"No spreadsheet links found on {DATA_PAGE_URL}")
    return links


def download_tennis_data_year(circuit: str, year: int, force: bool = False) -> Optional[Path]:
    """Download single year spreadsheet for ATP or WTA (never saves an HTML error page as data)."""
    circuit = circuit.lower()
    target_path = RAW_DATA_DIR / f"{circuit}_{year}.xlsx"

    if not force and _keep_valid(target_path):
        logger.info(f"Using cached {target_path.name}")
        return target_path

    try:
        url = file_links().get((circuit, year))
    except requests.RequestException as e:
        logger.warning(f"Could not read {DATA_PAGE_URL}: {e}")
        return _keep_valid(target_path)
    if url is None:
        logger.warning(f"{DATA_PAGE_URL} lists no {circuit.upper()} {year} spreadsheet")
        return _keep_valid(target_path)

    try:
        logger.info(f"Downloading {circuit.upper()} {year}: {url}...")
        resp = _SESSION.get(url, headers={"Referer": DATA_PAGE_URL}, timeout=60)
        if resp.status_code == 200 and _is_xlsx(resp.content):
            _write_atomic(target_path, resp.content)
            logger.info(f"Saved {target_path.name} ({len(resp.content)} bytes)")
            return target_path
        logger.warning(f"{url} returned HTTP {resp.status_code} without a spreadsheet")
    except requests.RequestException as e:
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
