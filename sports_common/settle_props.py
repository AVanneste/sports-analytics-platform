"""Settle basketball player props (points, rebounds, assists, threes, points+rebounds+assists) from
ESPN's free box scores. Napoleon's finished-events feed has no player statistics, so props use this.

``espn_games`` reads a day's finished games with every player's line, ``settle_props`` settles alert
rows against them. A player with no minutes (did not play) voids the bet: result "void", pnl 0.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional

import requests

from sports_common.matching import match_events, player_key, tokens

logger = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball"
LEAGUES = {"NBA": "nba", "WNBA": "wnba"}  # the alert's league name -> ESPN's path
STATS = ("points", "rebounds", "assists", "threes", "pts+reb+ast")


def _get(url: str, params: Dict) -> Dict:
    return requests.get(url, params=params, timeout=30).json()


def player_line(names: List[str], values: List[str]) -> Optional[Dict[str, float]]:
    """One player's counted stats from ESPN's parallel name/value lists; None when he did not play."""
    row = dict(zip(names, values))
    try:
        minutes = float(row.get("MIN", 0) or 0)
        points, rebounds, assists = float(row["PTS"]), float(row["REB"]), float(row["AST"])
        threes = float(str(row["3PT"]).split("-")[0])
    except (KeyError, ValueError):
        return None
    if minutes <= 0:
        return None
    return {"points": points, "rebounds": rebounds, "assists": assists, "threes": threes, "pts+reb+ast": points + rebounds + assists}


def espn_games(league: str, day: datetime) -> List[Dict]:
    """Finished games of an ESPN calendar day: {event_id, sport, start, home, away, players}, where
    players maps ``player_key`` to a line (``player_line``); players who did not play are absent."""
    path = LEAGUES[league]
    games = []
    for event in _get(f"{BASE}/{path}/scoreboard", {"dates": day.strftime("%Y%m%d")}).get("events", []):
        if not event.get("status", {}).get("type", {}).get("completed"):
            continue
        teams = {c["homeAway"]: c["team"]["displayName"] for c in event["competitions"][0]["competitors"]}
        players: Dict[str, Dict[str, float]] = {}
        try:
            box = _get(f"{BASE}/{path}/summary", {"event": event["id"]}).get("boxscore", {}).get("players", [])
        except requests.RequestException as e:
            logger.warning(f"ESPN box score {event['id']}: {e}")
            continue
        for team in box:
            for block in team.get("statistics", []):
                for a in block.get("athletes", []):
                    line = player_line(block.get("names") or block.get("labels") or [], a.get("stats") or [])
                    if line:
                        players[player_key(a["athlete"]["displayName"])] = line
        known = {player_key(a["athlete"]["displayName"]) for t in box for b in t.get("statistics", []) for a in b.get("athletes", [])}
        games.append({"event_id": event["id"], "sport": "Basketball", "start": event["date"].replace("Z", "+00:00") if "T" in event["date"] else event["date"],
                      "home": teams.get("home", ""), "away": teams.get("away", ""), "players": players, "roster": known})
    return games


def _find(players: Dict[str, Dict], roster: set, wanted: str) -> Optional[str]:
    """The box score's key for an alert's player: exact, else the one roster name containing all of his
    words (or contained in them); None when absent or ambiguous."""
    if wanted in roster:
        return wanted
    mine = tokens(wanted)
    hits = [k for k in roster if mine and (mine <= tokens(k) or tokens(k) <= mine)]
    return hits[0] if len(hits) == 1 else None


def settle_props(alerts: Iterable[Dict], games: List[Dict]) -> List[Dict]:
    """Result rows (``sports_common.settle.RESULT_COLUMNS``) for the prop alerts whose game is in
    ``games`` (matched by team names and kick-off) and whose player is on its roster."""
    from sports_common.settle import RESULT_COLUMNS
    alerts = [a for a in alerts if a["market"] == "player_prop" and a.get("units") in STATS and a.get("line") is not None]
    keys = {(a["start"], a["home"], a["away"]) for a in alerts}
    as_events = [{"book": "alert", "event_id": k, "sport": "Basketball", "start": k[0], "home": k[1], "away": k[2]} for k in keys]
    matched = match_events(as_events, games)
    by_id = {g["event_id"]: g for g in games}
    rows = []
    for a in alerts:
        hit = matched.get(("alert", (a["start"], a["home"], a["away"])))
        if not hit:
            continue
        game = by_id[hit[0]]
        who = _find(game["players"], game["roster"], a["side"])
        if who is None:
            continue
        line = game["players"].get(who)
        if line is None:  # on the roster but did not play: the bet is void
            result, pnl, count = "void", 0.0, None
        else:
            count = line[a["units"]]
            diff = (count - float(a["line"])) if a["selection"] == "over" else (float(a["line"]) - count)
            result = "win" if diff > 0 else "loss" if diff < 0 else "push"
            pnl = float(a["price"]) - 1 if diff > 0 else -1.0 if diff < 0 else 0.0
        rows.append({**{k: a.get(k) for k in RESULT_COLUMNS}, "score_home": None if count is None else int(count), "score_away": None, "result": result, "pnl": round(pnl, 4)})
    return rows


def days_needed(alerts: Iterable[Dict]) -> List[datetime]:
    """ESPN calendar days (US dates) that can hold these alerts' games: the start's UTC date and the day before."""
    out = set()
    for a in alerts:
        start = datetime.fromisoformat(a["start"].replace("Z", "+00:00")).replace(tzinfo=None)
        out |= {start.replace(hour=0, minute=0, second=0, microsecond=0), start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)}
    return sorted(out)
