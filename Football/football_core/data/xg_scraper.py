"""Match-level expected goals (xG) from Understat for the top five leagues.

Understat serves each league season as JSON at /getLeagueData/<league>/<season> (season = the year
it starts). Played matches are cached per league as CSV under data/raw/xg/ and joined to the
football-data matches by ``attach_xg``, which learns the team-name mapping from matches played on
the same day with the same score instead of relying on a hand-written alias table.
"""
import logging
import time
from datetime import datetime
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd
import requests

from football_core.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)

UNDERSTAT_LEAGUES = {"EPL": "EPL", "LaLiga": "La_Liga", "SerieA": "Serie_A", "Bundesliga": "Bundesliga",
                     "Ligue1": "Ligue_1"}
FIRST_SEASON = 2014  # first season Understat covers
XG_DIR = RAW_DATA_DIR / "xg"
COLUMNS = ["date", "home_team", "away_team", "home_xg", "away_xg", "home_goals", "away_goals"]


def current_season(today: Optional[datetime] = None) -> int:
    today = today or datetime.now()
    return today.year if today.month >= 7 else today.year - 1


def fetch_season(league_key: str, season: int) -> pd.DataFrame:
    """Played matches with xG for one league season."""
    name = UNDERSTAT_LEAGUES[league_key]
    response = requests.get(
        f"https://understat.com/getLeagueData/{name}/{season}", timeout=20,
        headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0",
                 "Referer": f"https://understat.com/league/{name}/{season}"})
    response.raise_for_status()
    rows = []
    for m in response.json().get("dates", []):
        if not m.get("isResult"):
            continue
        try:
            rows.append({"date": m["datetime"][:10], "home_team": m["h"]["title"], "away_team": m["a"]["title"],
                         "home_xg": float(m["xG"]["h"]), "away_xg": float(m["xG"]["a"]),
                         "home_goals": int(m["goals"]["h"]), "away_goals": int(m["goals"]["a"])})
        except (KeyError, TypeError, ValueError):
            continue
    return pd.DataFrame(rows, columns=COLUMNS)


def load_xg(league_key: str) -> pd.DataFrame:
    path = XG_DIR / f"{league_key}.csv"
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def update_xg_data(seasons: Optional[Iterable[int]] = None, pause: float = 1.5) -> Dict[str, int]:
    """Refresh the xG cache: the current season by default, every season when a league has no cache yet."""
    counts = {}
    for league_key in UNDERSTAT_LEAGUES:
        cached = load_xg(league_key)
        todo = list(seasons) if seasons is not None else (
            [current_season()] if not cached.empty else list(range(FIRST_SEASON, current_season() + 1)))
        frames = [cached]
        for season in todo:
            try:
                frames.append(fetch_season(league_key, season))
            except (requests.RequestException, ValueError) as e:
                logger.warning(f"[xG] {league_key} {season}: {e}")
            time.sleep(pause)
        merged = (pd.concat(frames, ignore_index=True)
                  .drop_duplicates(subset=["date", "home_team", "away_team"], keep="last")
                  .sort_values(["date", "home_team"]))
        if len(merged):
            XG_DIR.mkdir(parents=True, exist_ok=True)
            merged.to_csv(XG_DIR / f"{league_key}.csv", index=False)
        counts[league_key] = len(merged)
        logger.info(f"[xG] {league_key}: {len(merged)} matches cached")
    return counts


def _team_name_map(matches: pd.DataFrame, xg: pd.DataFrame, min_matches: int = 2) -> Dict[str, str]:
    """Understat team name -> football-data team name, from matches on the same day with the same score.

    Pairings are accepted most frequent first and each football-data name is used once, so the odd
    coincidental pairing cannot displace a team's true name.
    """
    fd = matches[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].assign(day=matches["Date"].dt.normalize())
    us = xg.assign(day=pd.to_datetime(xg["date"]))
    pairs = []
    for shift in (0, 1, -1):  # kick-off dates can differ by a day across time zones
        j = us.assign(day=us["day"] + pd.Timedelta(days=shift)).merge(
            fd, left_on=["day", "home_goals", "away_goals"], right_on=["day", "FTHG", "FTAG"])
        pairs += [j[["home_team", "HomeTeam"]].set_axis(["us", "fd"], axis=1),
                  j[["away_team", "AwayTeam"]].set_axis(["us", "fd"], axis=1)]
    if not pairs:
        return {}
    counts = pd.concat(pairs).value_counts()
    name_map: Dict[str, str] = {}
    for (us_name, fd_name), n in counts.items():  # most frequent pairing first
        if n >= min_matches and us_name not in name_map and fd_name not in name_map.values():
            name_map[us_name] = fd_name
    return name_map


def attach_xg(matches: pd.DataFrame, league_key: str, xg: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Football-data matches with HxG / AxG columns (NaN where Understat has no matching game)."""
    out = matches.copy()
    out["HxG"], out["AxG"] = np.nan, np.nan
    if league_key not in UNDERSTAT_LEAGUES:
        return out
    xg = load_xg(league_key) if xg is None else xg
    if xg.empty or out.empty:
        return out
    name_map = _team_name_map(out, xg)
    us = xg.assign(HomeTeam=xg["home_team"].map(name_map), AwayTeam=xg["away_team"].map(name_map),
                   us_date=pd.to_datetime(xg["date"])).dropna(subset=["HomeTeam", "AwayTeam"])
    joined = (out[["Date", "HomeTeam", "AwayTeam"]].assign(pos=np.arange(len(out)))
              .merge(us[["HomeTeam", "AwayTeam", "us_date", "home_xg", "away_xg"]], on=["HomeTeam", "AwayTeam"]))
    joined = joined[(joined["Date"].dt.normalize() - joined["us_date"]).abs() <= pd.Timedelta(days=2)]
    joined = joined.drop_duplicates(subset="pos")
    out.iloc[joined["pos"].to_numpy(), out.columns.get_indexer(["HxG", "AxG"])] = joined[["home_xg", "away_xg"]].to_numpy()
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_xg_data()
