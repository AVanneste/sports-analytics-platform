"""Closing BTTS prices from OddsPortal (scripts/scrape_oddsportal_btts.py), joined to football-data.

football-data.co.uk has no BTTS prices, so these are what the BTTS model is fitted and validated
against. Team names are learnt from matches played on the same day with the same score, as for
xG (``xg_scraper._team_name_map``).
"""
from typing import Optional

import numpy as np
import pandas as pd

from football_core.config import RAW_DATA_DIR
from football_core.data.xg_scraper import _team_name_map

ODDSPORTAL_DIR = RAW_DATA_DIR / "oddsportal"
BTTS_COLUMNS = ["odds_btts_yes", "odds_btts_no"]


def load_btts(league_key: str) -> pd.DataFrame:
    """Priced matches: date, teams, goals and the mean closing BTTS prices across bookmakers."""
    path = ODDSPORTAL_DIR / f"{league_key}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "home_team", "away_team", "home_goals", "away_goals", "btts_yes", "btts_no"])
    df = pd.read_csv(path).dropna(subset=["btts_yes", "btts_no", "home_goals", "away_goals"])
    df = df.drop_duplicates(subset="match_link", keep="last")
    df["date"] = df["date"].astype(str).str[:10]
    df[["home_goals", "away_goals"]] = df[["home_goals", "away_goals"]].astype(int)
    return df


def attach_btts_odds(matches: pd.DataFrame, league_key: str, btts: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Football-data matches with closing BTTS prices (NaN where OddsPortal has no priced game)."""
    out = matches.copy()
    for col in BTTS_COLUMNS:
        out[col] = np.nan
    btts = load_btts(league_key) if btts is None else btts
    if btts.empty or out.empty:
        return out
    name_map = _team_name_map(out, btts)
    op = btts.assign(HomeTeam=btts["home_team"].map(name_map), AwayTeam=btts["away_team"].map(name_map),
                     op_date=pd.to_datetime(btts["date"])).dropna(subset=["HomeTeam", "AwayTeam"])
    joined = (out[["Date", "HomeTeam", "AwayTeam"]].assign(pos=np.arange(len(out)))
              .merge(op[["HomeTeam", "AwayTeam", "op_date", "btts_yes", "btts_no"]], on=["HomeTeam", "AwayTeam"]))
    joined = joined[(joined["Date"].dt.normalize() - joined["op_date"]).abs() <= pd.Timedelta(days=2)]
    joined = joined.drop_duplicates(subset="pos")
    out.iloc[joined["pos"].to_numpy(), out.columns.get_indexer(BTTS_COLUMNS)] = joined[["btts_yes", "btts_no"]].to_numpy()
    return out
