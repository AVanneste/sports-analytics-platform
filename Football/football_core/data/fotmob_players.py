"""Season player stats from FotMob (Opta data) for the scouting leagues: one row per player.

A league's FotMob page lists 38 player stat tables (goals, xG and xA per 90, chances created,
line-breaking passes, tackles, recoveries, goals prevented...), each a JSON of every qualifying
player (``fetchAllUrl``). They are pivoted to one row per player and league: per-90 values,
minutes, matches and a position group read from FotMob's pitch-grid position codes. Each team's
squad page adds age, height and market value (one request a team); foot and contract end need a
player's own profile, so ``add_profiles`` fetches those for a shortlist only.
"""
import logging
import time
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from football_core.config import PROCESSED_DATA_DIR
from football_core.data.fotmob_xg import BASE_URL, _get

logger = logging.getLogger(__name__)

SCOUT_LEAGUES = {  # FotMob league id -> name (FotMob's allLeagues, Oct 2026)
    40: "Belgium First Division A", 264: "Belgium First Division B", 57: "Eredivisie", 111: "Eerste Divisie",
    46: "Denmark Superliga", 85: "Denmark 1. Division", 59: "Norway Eliteserien", 203: "Norway OBOS-ligaen",
    67: "Allsvenskan", 168: "Superettan", 69: "Swiss Super League", 163: "Swiss Challenge League",
    38: "Austria Bundesliga", 119: "Austria 2. Liga", 122: "Czech 1. Liga", 196: "Ekstraklasa", 197: "Poland I Liga",
    252: "Croatia HNL", 182: "Serbia Super Liga", 135: "Greece Super League 1", 61: "Liga Portugal",
    185: "Liga Portugal 2", 110: "Ligue 2", 8970: "Ligue 3", 146: "2. Bundesliga", 208: "3. Liga", 140: "LaLiga2",
    8968: "Primera Federacion", 86: "Serie B", 147: "Serie C", 48: "Championship", 108: "League One",
    109: "League Two", 64: "Scottish Premiership", 71: "Turkey Super Lig", 176: "Slovakia 1. liga",
    173: "Slovenia Prva Liga", 212: "Hungary NB I", 189: "Romania Liga I", 270: "Bulgaria First League",
    441: "Ukraine Premier League", 51: "Finland Veikkausliiga", 215: "Iceland Besta deildin",
    126: "Ireland Premier Division", 127: "Israel Ligat ha'Al", 136: "Cyprus 1. Division",
    268: "Brazil Serie A", 8814: "Brazil Serie B", 112: "Argentina Liga Profesional", 8965: "Argentina Primera B Nacional",
    274: "Colombia Primera A", 161: "Uruguay Liga AUF", 246: "Ecuador Serie A", 273: "Chile Liga de Primera",
    199: "Paraguay Division Profesional", 130: "MLS", 8972: "USL Championship", 230: "Liga MX",
    223: "J. League", 8974: "J. League 2", 9080: "K League 1",
}
SCOUT_DIR = PROCESSED_DATA_DIR / "scout"
PAUSE = 0.4


def position_group(code: Optional[int]) -> Optional[str]:
    """FotMob position codes are a pitch grid: tens = line (1 keeper, 3 back four, 5 wing-backs,
    6 holding, 7 central, 8 attacking midfield, 10+ forwards), units = side (2 right ... 8 left)."""
    if code is None:
        return None
    line, side = divmod(int(code), 10)
    if line == 1 and side == 1:
        return "GK"
    if line == 3:
        return "FB" if side in (1, 2, 8, 9) else "CB"
    if line == 5:
        return "FB"
    if line == 6:
        return "DM"
    if line == 7:
        return "W" if side in (1, 2, 8, 9) else "CM"
    if line == 8:
        return "W" if side in (1, 2, 3, 7, 8, 9) else "AM"
    if line >= 10:
        return "ST"
    return None


def stat_urls(league: Dict) -> Dict[str, str]:
    """{stat name: JSON url} of a league payload's player tables ("expected_goals_per_90": ...)."""
    return {p["fetchAllUrl"].rsplit("/", 1)[1].removesuffix(".json"): p["fetchAllUrl"]
            for p in (league.get("stats") or {}).get("players") or [] if p.get("fetchAllUrl")}


def pivot_tables(tables: Dict[str, Dict], league_id: int, season: str) -> pd.DataFrame:
    """One row per player from the stat tables: each table's value under its name."""
    players: Dict[int, Dict] = {}
    for stat, payload in tables.items():
        for row in ((payload.get("TopLists") or [{}])[0].get("StatList") or []):
            pid = row.get("ParticiantId") or row.get("ParticipantId")  # FotMob's own typo, both seen
            if pid is None:
                continue
            p = players.setdefault(pid, {"player_id": pid, "name": row.get("ParticipantName"), "team_id": row.get("TeamId"),
                                         "team": row.get("TeamName"), "nationality": row.get("ParticipantCountryCode"),
                                         "league_id": league_id, "league": SCOUT_LEAGUES.get(league_id), "season": season,
                                         "position_code": (row.get("Positions") or [None])[0], "minutes": 0, "matches": 0})
            p[stat] = row.get("StatValue")
            p["minutes"] = max(p["minutes"], row.get("MinutesPlayed") or 0)
            p["matches"] = max(p["matches"], row.get("MatchesPlayed") or 0)
    df = pd.DataFrame(list(players.values()))
    if not df.empty:
        df["position"] = df["position_code"].map(position_group)
    return df


def fetch_league(league_id: int) -> pd.DataFrame:
    """Every qualifying player of a league's current season (1 + 38 requests)."""
    league = _get(f"{BASE_URL}/api/data/leagues", {"id": league_id}).json()
    urls = stat_urls(league)
    season = str((league.get("details") or {}).get("selectedSeason") or "")
    tables = {}
    for stat, url in urls.items():
        time.sleep(PAUSE)
        try:
            tables[stat] = _get(url).json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[FotMob] league {league_id} {stat}: {e}")
    return pivot_tables(tables, league_id, season)


def parse_squad(team: Dict) -> List[Dict]:
    """Age, birth date, height, market value and listed positions of a team page's squad."""
    return [{"player_id": m["id"], "age": m.get("age"), "birth_date": m.get("dateOfBirth"), "height_cm": m.get("height"),
             "market_value_eur": m.get("transferValue"), "listed_positions": m.get("positionIdsDesc")}
            for group in ((team.get("squad") or {}).get("squad") or []) for m in group.get("members") or [] if m.get("id")]


def fetch_squads(team_ids: Iterable[int]) -> pd.DataFrame:
    rows: List[Dict] = []
    for team_id in sorted(set(int(t) for t in team_ids)):
        time.sleep(PAUSE)
        try:
            rows += parse_squad(_get(f"{BASE_URL}/api/data/teams", {"id": team_id}).json())
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[FotMob] team {team_id}: {e}")
    return pd.DataFrame(rows).drop_duplicates("player_id", keep="last") if rows else pd.DataFrame(columns=["player_id"])


def parse_profile(data: Dict) -> Dict:
    """Foot and contract end from a player's profile (the rest comes from squad pages)."""
    info = {x.get("title"): x.get("value") for x in data.get("playerInformation") or []}
    foot = info.get("Preferred foot")
    contract = (data.get("contractEnd") or {}).get("utcTime")
    return {"player_id": data.get("id"), "foot": foot.get("fallback") if isinstance(foot, dict) else foot,
            "contract_end": contract[:10] if contract else None}


def add_profiles(players: pd.DataFrame, known: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """``players`` with foot and contract end, fetching only those not in ``known`` (cached profiles)."""
    known = known if known is not None and not known.empty else pd.DataFrame(columns=["player_id", "foot", "contract_end"])
    fetched = []
    for pid in sorted(set(players["player_id"]) - set(known["player_id"])):
        time.sleep(PAUSE)
        try:
            fetched.append(parse_profile(_get(f"{BASE_URL}/api/data/playerData", {"id": int(pid)}).json()))
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"[FotMob] player {pid}: {e}")
    profiles = pd.concat([known, pd.DataFrame(fetched)], ignore_index=True).drop_duplicates("player_id", keep="last")
    return players.merge(profiles, on="player_id", how="left")


def update_scout(leagues: Optional[Iterable[int]] = None) -> pd.DataFrame:
    """Every scouted league's players with their squad details, saved to data/processed/scout/players.parquet."""
    frames: List[pd.DataFrame] = []
    for league_id in leagues or SCOUT_LEAGUES:
        try:
            df = fetch_league(league_id)
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning(f"[FotMob] league {league_id}: {e}")
            continue
        logger.info(f"[FotMob] {SCOUT_LEAGUES.get(league_id, league_id)}: {len(df)} players")
        frames.append(df)
    players = pd.concat(frames, ignore_index=True)
    players = players.merge(fetch_squads(players["team_id"].dropna()), on="player_id", how="left")
    SCOUT_DIR.mkdir(parents=True, exist_ok=True)
    players.to_parquet(SCOUT_DIR / "players.parquet", index=False)
    return players
