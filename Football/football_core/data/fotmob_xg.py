"""Match-level expected goals (Opta xG) from FotMob for the leagues Understat does not cover.

A league season's fixture page embeds every match (id, date, teams, score) in its __NEXT_DATA__
JSON. Each played match's team xG comes from FotMob's public match-details JSON. Matches are cached
per league under data/raw/xg/ in the Understat layout (plus FotMob's match id, so a match is fetched
once), and ``xg_scraper.attach_xg`` joins them to the football-data matches the same way.
"""
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from football_core.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)

FOTMOB_LEAGUES = {"Belgium": (40, "first-division-a"), "Eredivisie": (57, "eredivisie"),
                  "PrimeiraLiga": (61, "liga-portugal"), "ScottishPrem": (64, "premiership")}
FIRST_SEASON = 2020  # enough history for the ratings' time decay before the backtest windows
RECHECK_DAYS = 7  # a recent match without xG is fetched again for this long (stats can arrive late)
XG_DIR = RAW_DATA_DIR / "xg"
COLUMNS = ["date", "home_team", "away_team", "home_xg", "away_xg", "home_goals", "away_goals", "match_id"]
BASE_URL = "https://www.fotmob.com"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
                         "Accept-Language": "en-GB,en;q=0.9"})
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def current_season(today: Optional[datetime] = None) -> int:
    today = today or datetime.now()
    return today.year if today.month >= 7 else today.year - 1


def _get(url: str, params: Optional[Dict] = None, retries: int = 2) -> requests.Response:
    for attempt in range(retries + 1):
        try:
            response = _SESSION.get(url, params=params, timeout=30)
        except requests.ConnectionError:  # dropped connections happen; retry like a 5xx
            if attempt == retries:
                raise
            time.sleep(10 * (attempt + 1))
            continue
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            response.raise_for_status()
            return response
        time.sleep(10 * (attempt + 1))


def parse_fixtures(next_data: Dict) -> List[Dict]:
    """Finished matches (id, date, teams, score) from a league fixture page's __NEXT_DATA__."""
    rows = []
    for m in next_data["props"]["pageProps"].get("fixtures", {}).get("allMatches", []):
        status = m.get("status") or {}
        score = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", status.get("scoreStr") or "")
        if not status.get("finished") or status.get("cancelled") or status.get("awarded") or not score:
            continue
        rows.append({"match_id": int(m["id"]), "date": status["utcTime"][:10],
                     "home_team": m["home"]["name"], "away_team": m["away"]["name"],
                     "home_goals": int(score.group(1)), "away_goals": int(score.group(2))})
    return rows


def season_matches(league_key: str, season: int) -> List[Dict]:
    league_id, slug = FOTMOB_LEAGUES[league_key]
    html = _get(f"{BASE_URL}/leagues/{league_id}/fixtures/{slug}", {"season": f"{season}/{season + 1}"}).text
    found = _NEXT_DATA.search(html)
    if not found:
        raise ValueError(f"no __NEXT_DATA__ on the {league_key} {season} fixture page")
    return parse_fixtures(json.loads(found.group(1)))


def parse_match_xg(details: Dict, league_id: int) -> Optional[Tuple[float, float]]:
    """(home xG, away xG) from a match-details payload; None without xG or for another competition."""
    if int((details.get("general") or {}).get("parentLeagueId") or -1) != league_id:
        return None
    try:
        groups = details["content"]["stats"]["Periods"]["All"]["stats"]
    except (KeyError, TypeError):
        return None
    for group in groups:
        for stat in group.get("stats") or []:
            values = stat.get("stats") or []
            if stat.get("key") == "expected_goals" and len(values) == 2 and None not in values:
                try:
                    return float(values[0]), float(values[1])
                except (TypeError, ValueError):
                    return None
    return None


def match_xg(match_id: int, league_id: int) -> Optional[Tuple[float, float]]:
    details = _get(f"{BASE_URL}/api/data/matchDetails", {"matchId": match_id}).json()
    return parse_match_xg(details, league_id)


def load_fotmob_xg(league_key: str) -> pd.DataFrame:
    path = XG_DIR / f"{league_key}.csv"
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def update_fotmob_xg(seasons: Optional[Iterable[int]] = None, leagues: Optional[Iterable[str]] = None,
                     pause: float = 1.0, today: Optional[datetime] = None) -> Dict[str, int]:
    """Fetch xG for played matches not cached yet: the current season by default, every season from
    FIRST_SEASON when a league has no cache. Progress is saved after each season."""
    today = today or datetime.now(timezone.utc).replace(tzinfo=None)
    counts = {}
    for league_key in leagues or FOTMOB_LEAGUES:
        league_id = FOTMOB_LEAGUES[league_key][0]
        cached = load_fotmob_xg(league_key)
        todo = list(seasons) if seasons is not None else (
            [current_season(today)] if not cached.empty else list(range(FIRST_SEASON, current_season(today) + 1)))
        recheck_from = (today - pd.Timedelta(days=RECHECK_DAYS)).strftime("%Y-%m-%d")
        done = set(cached.loc[cached["home_xg"].notna() | (cached["date"] < recheck_from), "match_id"].astype(int))
        for season in todo:
            try:
                matches = [m for m in season_matches(league_key, season) if m["match_id"] not in done]
            except (requests.RequestException, ValueError, KeyError) as e:
                logger.warning(f"[FotMob xG] {league_key} {season}: {e}")
                continue
            rows = []
            for m in matches:
                time.sleep(pause)
                try:
                    xg = match_xg(m["match_id"], league_id)
                except (requests.RequestException, ValueError) as e:
                    logger.warning(f"[FotMob xG] match {m['match_id']}: {e}")
                    continue
                rows.append({**m, "home_xg": xg[0] if xg else np.nan, "away_xg": xg[1] if xg else np.nan})
            if rows:
                cached = (pd.concat([cached, pd.DataFrame(rows, columns=COLUMNS)], ignore_index=True)
                          .drop_duplicates(subset="match_id", keep="last").sort_values(["date", "home_team"]))
                XG_DIR.mkdir(parents=True, exist_ok=True)
                cached[COLUMNS].to_csv(XG_DIR / f"{league_key}.csv", index=False)
            with_xg = sum(r["home_xg"] == r["home_xg"] for r in rows)
            logger.info(f"[FotMob xG] {league_key} {season}: {len(rows)} new matches, {with_xg} with xG")
        counts[league_key] = int(cached["home_xg"].notna().sum())
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    update_fotmob_xg()
