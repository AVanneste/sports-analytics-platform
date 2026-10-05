"""Backfill closing BTTS prices from OddsPortal (via OddsHarvester), for validating the BTTS model.

    .venv-scrape/bin/pip install oddsharvester==0.15.0 && .venv-scrape/bin/python -m playwright install chromium
    python scripts/scrape_oddsportal_btts.py [--leagues EPL Belgium] [--seasons 2024-2025 2025-2026 current]

football-data has no BTTS prices, so the BTTS model has never been checked against the market.
OddsPortal lists finished matches with their final (closing) BTTS prices per bookmaker.

* Run from a home connection, not GitHub: OddsPortal refuses datacenter addresses.
* It redirects Belgian visitors, and shows only the bookmakers licensed in the visitor's country
  (France: two; Germany: about seven).
* Match links are collected per season, then scraped in batches; each batch is appended to
  Football/data/raw/oddsportal/<league>.csv, so the run can stop and resume anywhere.
* OddsHarvester lives in its own environment (.venv-scrape) to keep Playwright out of the
  project's dependencies; set ODDSHARVESTER to use another executable.
"""
import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "Football" / "data" / "raw" / "oddsportal"
HARVESTER = os.environ.get("ODDSHARVESTER", str(ROOT / ".venv-scrape" / "bin" / "oddsharvester"))
SLUGS = {"EPL": "england-premier-league", "LaLiga": "spain-laliga", "SerieA": "italy-serie-a",
         "Bundesliga": "germany-bundesliga", "Ligue1": "france-ligue-1", "Belgium": "jupiler-pro-league",
         "Eredivisie": "eredivisie", "PrimeiraLiga": "liga-portugal", "ScottishPrem": "scotland-premiership"}
COLUMNS = ["season", "match_link", "date", "home_team", "away_team", "home_goals", "away_goals",
           "btts_yes", "btts_no", "btts_yes_max", "btts_no_max", "books"]
BATCH = 40


def harvest(args: list, timeout: int = 3600) -> list:
    """Run an OddsHarvester 'historic' command and return its JSON records ([] on failure)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        cmd = [HARVESTER, "-q", "historic", "-s", "football", "-f", "json", "-o", str(out), "--headless", *args]
        try:
            subprocess.run(cmd, check=False, timeout=timeout, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print(f"  timed out: {' '.join(args[:6])}", flush=True)
        if not out.exists():
            return []
        data = json.loads(out.read_text() or "[]")
        return data if isinstance(data, list) else []


def season_links(slug: str, season: str, cache: Path) -> list:
    """All match links of a league season (cached; the current season is always refreshed)."""
    if cache.exists() and season != "current":
        return json.loads(cache.read_text())
    links = sorted({r["match_link"] for r in harvest(["-l", slug, "--season", season, "--links-only"]) if r.get("match_link")})
    if links:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(links))
    return links


def to_row(record: dict, season: str) -> dict:
    offers = [b for b in record.get("btts_market") or [] if b.get("period") in (None, "FullTime")]
    yes = [float(b["btts_yes"]) for b in offers if b.get("btts_yes") not in (None, "", "-")]
    no = [float(b["btts_no"]) for b in offers if b.get("btts_no") not in (None, "", "-")]
    priced = yes and no and len(yes) == len(no)
    return {"season": season, "match_link": record.get("match_link"), "date": str(record.get("match_date") or "")[:16],
            "home_team": record.get("home_team"), "away_team": record.get("away_team"),
            "home_goals": record.get("home_score"), "away_goals": record.get("away_score"),
            "btts_yes": round(statistics.mean(yes), 3) if priced else None,
            "btts_no": round(statistics.mean(no), 3) if priced else None,
            "btts_yes_max": max(yes) if priced else None, "btts_no_max": max(no) if priced else None,
            "books": len(yes) if priced else 0}


def done_links(path: Path) -> set:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["match_link"] for r in csv.DictReader(fh)}


def append(path: Path, rows: list) -> None:
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leagues", nargs="+", default=list(SLUGS), choices=list(SLUGS))
    parser.add_argument("--seasons", nargs="+", default=["2024-2025", "2025-2026", "current"])
    parser.add_argument("--max-matches", type=int, default=None, help="stop each league season after this many (trials)")
    args = parser.parse_args()
    if not Path(HARVESTER).exists():
        sys.exit(f"OddsHarvester not found at {HARVESTER} (see this script's docstring)")

    for league in args.leagues:
        slug, out = SLUGS[league], OUT_DIR / f"{league}.csv"
        for season in args.seasons:
            links = season_links(slug, season, OUT_DIR / "links" / f"{league}_{season}.json")
            todo = [l for l in links if l not in done_links(out)][:args.max_matches]
            print(f"{league} {season}: {len(links)} matches, {len(todo)} to scrape", flush=True)
            for i in range(0, len(todo), BATCH):
                batch = todo[i:i + BATCH]
                with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
                    fh.write("\n".join(batch))
                started = time.time()
                records = harvest(["-l", slug, "--season", season, "-m", "btts", "--match-links-file", fh.name])
                os.unlink(fh.name)
                rows = [to_row(r, season) for r in records if r.get("match_link")]
                append(out, rows)
                priced = sum(1 for r in rows if r["books"])
                print(f"  {i + len(batch)}/{len(todo)}: {len(rows)} saved, {priced} priced ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
