"""Opta Power Rankings: one 0-100 rating scale for ~14,000 men's clubs, for ties across leagues.

Our club ratings come from each domestic league's own model, so a Belgian and a Turkish club's
strengths are not comparable. Opta rates every club on one scale (updated weekly), published as
the JSON behind theanalyst.com's ranking table. ``goal_scale`` turns rating points into goals by
regressing our domestic Dixon-Coles net strengths on the ratings within each league.

Each new snapshot is also archived (clubs rated 60+), so cup predictions made from it can be
validated against results once a season of snapshots exists.
"""
import functools
import logging
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from football_core.config import RAW_DATA_DIR
from football_core.utils.helpers import normalize_team_name, strip_accents

logger = logging.getLogger(__name__)

RANKINGS_URL = "https://dataviz.theanalyst.com/opta-power-rankings/pr-reference.json"
RANKINGS_PATH = RAW_DATA_DIR / "opta_power_rankings.csv"
ARCHIVE_DIR = RAW_DATA_DIR / "opta_power"
ARCHIVE_MIN_RATING = 60.0  # about 3,900 clubs: every side that reaches European competition
_EXPAND = {"st": "saint", "sp": "sporting", "for": "fortuna"}  # football-data abbreviations
_NOISE = {"fc", "cf", "sc", "kv", "krc", "rsc", "kaa", "afc", "ac", "as", "sv", "sk", "club", "de", "the",
          "royal", "royale", "r", "k", "cd", "ud", "if", "fk", "bk", "ssc", "us", "sl", "cp"}
COLUMNS = ["name", "short_name", "club_name", "rating", "rank", "league_id", "as_of"]


def parse_rankings(payload: list, as_of: str) -> pd.DataFrame:
    rows = [{"name": c.get("contestantName"), "short_name": c.get("contestantShortName"),
             "club_name": c.get("contestantClubName"), "rating": c.get("currentRating"), "rank": c.get("rank"),
             "league_id": c.get("tmcl"), "as_of": as_of}
            for c in payload if c.get("contestantName") and c.get("currentRating") is not None]
    return pd.DataFrame(rows, columns=COLUMNS)


def update_power_rankings() -> int:
    """Download the current rankings (and archive a new snapshot); returns the number of clubs."""
    response = requests.get(RANKINGS_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    modified = pd.Timestamp(response.headers.get("last-modified") or pd.Timestamp.now(tz="UTC"))
    table = parse_rankings(response.json(), modified.strftime("%Y-%m-%d"))
    if table.empty:
        raise ValueError("Opta Power Rankings payload has no clubs")
    RANKINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(RANKINGS_PATH, index=False)
    archive = ARCHIVE_DIR / f"{table['as_of'].iloc[0]}.csv"
    if not archive.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        table[table["rating"] >= ARCHIVE_MIN_RATING].to_csv(archive, index=False)
    _clubs.cache_clear()
    load_power_rankings.cache_clear()
    _token_index.cache_clear()
    club_rating.cache_clear()
    logger.info(f"[Opta Power Rankings] {len(table)} clubs, as of {table['as_of'].iloc[0]}")
    return len(table)


def _key(name: str) -> str:
    return strip_accents(normalize_team_name(str(name)))


def _tokens(name: str) -> frozenset:
    words = re.sub(r"[^a-z0-9 ]", " ", strip_accents(str(name)).replace("'", "")).split()
    return frozenset(_EXPAND.get(w, w) for w in words if w not in _NOISE)


@functools.lru_cache(maxsize=1)
def _clubs() -> List[Tuple[Tuple[str, ...], float, str]]:
    """(spellings, rating, Opta league id) per club."""
    if not RANKINGS_PATH.exists():
        return []
    return [(tuple({n for n in (row.name, row.short_name, row.club_name) if isinstance(n, str) and n}),
             float(row.rating), row.league_id) for row in pd.read_csv(RANKINGS_PATH).itertuples(index=False)]


@functools.lru_cache(maxsize=1)
def load_power_rankings() -> Dict[str, List[Tuple[float, str]]]:
    """Normalised club name (any of its spellings) -> [(rating, Opta league id)]: names are shared
    ("Arsenal", "Racing")."""
    index: Dict[str, List[Tuple[float, str]]] = defaultdict(list)
    for names, rating, league in _clubs():
        for name in {_key(n) for n in names}:
            index[name].append((rating, league))
    return dict(index)


@functools.lru_cache(maxsize=1)
def _token_index() -> List[Tuple[frozenset, Tuple[float, str]]]:
    return [(_tokens(n), (rating, league)) for names, rating, league in _clubs() for n in names]


@functools.lru_cache(maxsize=4096)
def club_rating(team_name: str, league_id: Optional[str] = None) -> Optional[Tuple[float, str]]:
    """(rating, Opta league id) for a club, or None when Opta's table has no match for the name.

    Exact spellings first, else clubs whose name contains every word of ``team_name`` ("Nijmegen"
    is NEC Nijmegen). With ``league_id`` only that league's clubs count; otherwise the
    highest-rated namesake wins."""
    index = load_power_rankings()
    if not index:
        return None
    pick = lambda clubs: max((c for c in clubs if league_id is None or c[1] == league_id), default=None)
    found = pick(index.get(_key(team_name), []))
    if found:
        return found
    wanted = _tokens(team_name)
    if not wanted:
        return None
    return pick([club for tokens, club in _token_index() if wanted <= tokens])


def league_ids(league_teams: Dict[str, Iterable[str]]) -> Dict[str, str]:
    """Our league key -> Opta's id for that league: the one most of its clubs are rated in."""
    ids = {}
    for league, teams in league_teams.items():
        found = [r[1] for r in (club_rating(t) for t in teams) if r is not None]
        if found:
            ids[league] = Counter(found).most_common(1)[0][0]
    return ids


def goal_scale(league_strengths: Dict[str, Dict[str, float]], min_clubs: int = 30) -> Optional[float]:
    """Log-goal supremacy per Opta rating point: the within-league slope of Dixon-Coles net strength
    (attack + defence) on rating, pooled over our leagues. ``league_strengths`` maps each league to
    {team: net strength}; only clubs Opta rates in that league count (relegated clubs drop out).
    None with too few rated clubs."""
    ids = league_ids(league_strengths)
    xs, ys = [], []
    for league, strengths in league_strengths.items():
        pairs = [(club_rating(team, ids.get(league)), net) for team, net in strengths.items()]
        pairs = [(r[0], net) for r, net in pairs if r is not None]
        if len(pairs) < 4:
            continue
        r, n = np.array(pairs).T
        xs.append(r - r.mean())
        ys.append(n - n.mean())
    if sum(len(x) for x in xs) < min_clubs:
        return None
    x, y = np.concatenate(xs), np.concatenate(ys)
    return float(np.dot(x, y) / np.dot(x, x))
