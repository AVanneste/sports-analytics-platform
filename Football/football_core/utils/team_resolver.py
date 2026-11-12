"""Match a fixture's team name to the name the models know the team by.

Fixtures come from ESPN and the Belgian books ("Racing Genk", "Birmingham City"); the models are
trained on football-data.co.uk names ("Genk", "Birmingham"). A name that is not recognised used to fall
back to league-average ratings silently: half of all predictions in Oct-Nov 2026, 0.10 log loss worse
than the market against 0.02 when both teams were known.

``resolve`` tries, in order: the exact name, the hand-kept table, aliases learned from graded matches
or asked of Gemini (cached in ``ALIASES_FILE``), then a unique whole-word match
(``sports_common.matching.name_score``). Anything else is unresolved and the prediction says so.
"""
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

from football_core.config import CACHE_DIR
from football_core.utils.helpers import normalize_team_name, strip_accents
from sports_common.matching import name_score, tokens
from sports_common.secrets import get_secret, is_usable_key, redact

logger = logging.getLogger(__name__)

ALIASES_FILE = CACHE_DIR / "team_aliases.json"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
MIN_PAIRINGS = 2  # same-day, same-score matches needed to accept a learned pairing


def _key(name: str) -> str:
    return strip_accents(str(name or "")).lower().strip()


def resolve(name: str, known: Iterable[str], aliases: Optional[Dict[str, str]] = None,
            table: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The known team ``name`` refers to, or None. ``aliases`` and ``table`` map lower-case,
    accent-free names to known names (``table`` is the hand-kept one, ``aliases`` the learned one)."""
    known = set(known)
    if not name:
        return None
    if name in known:
        return name
    norm = normalize_team_name(name)
    if norm in known:
        return norm
    for mapping in (table or {}, aliases or {}):
        mapping = {_key(k): v for k, v in mapping.items()}
        for candidate in (_key(name), _key(norm)):
            target = mapping.get(candidate)
            if target in known:
                return target
    # a unique whole-word match that shares an identical word (not just a prefix: "Istanbul Basaksehir" is
    # not "Istanbulspor")
    mine = tokens(name)
    full = [k for k in known if name_score(name, k) >= 1.0 and mine & tokens(k)]
    return full[0] if len(full) == 1 else None


def learn_aliases(pairs: pd.DataFrame, known: Iterable[str]) -> Dict[str, str]:
    """Fixture name -> known name from matches seen in both places.

    ``pairs`` has one row per match with the fixture's names (``home``, ``away``), the results
    table's names (``fd_home``, ``fd_away``), nothing else needed: callers join the graded ledger to the
    results on the same day and score. Pairings are accepted most frequent first (at least MIN_PAIRINGS),
    each known name once, so a coincidental pairing cannot displace a team's real name."""
    known = set(known)
    both = pd.concat([pairs[["home", "fd_home"]].set_axis(["fixture", "known"], axis=1),
                      pairs[["away", "fd_away"]].set_axis(["fixture", "known"], axis=1)])
    both = both[both["known"].isin(known) & (both["fixture"] != both["known"])]
    counts = Counter(zip(both["fixture"], both["known"]))
    out: Dict[str, str] = {}
    used = set()
    for (fixture, target), n in counts.most_common():
        if n >= MIN_PAIRINGS and _key(fixture) not in out and target not in used:
            out[_key(fixture)] = target
            used.add(target)
    return out


def ledger_pairs(ledger: List[Dict], results: pd.DataFrame) -> pd.DataFrame:
    """Graded ledger entries of one league joined to the results table on the same day (+-1) and score."""
    rows = []
    for m in ledger:
        try:
            h, a = [int(x) for x in str(m["actual_score"]).replace(" ", "").split("-")[:2]]
            rows.append({"day": pd.Timestamp(str(m["date"])[:10]), "home": m["home_team"], "away": m["away_team"], "FTHG": h, "FTAG": a})
        except (KeyError, ValueError, TypeError):
            continue
    if not rows or results.empty:
        return pd.DataFrame(columns=["home", "away", "fd_home", "fd_away"])
    fixtures = pd.DataFrame(rows)
    fd = results[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].assign(day=results["Date"].dt.normalize())
    parts = []
    for shift in (0, 1, -1):
        j = fixtures.assign(day=fixtures["day"] + pd.Timedelta(days=shift)).merge(fd, on=["day", "FTHG", "FTAG"], suffixes=("", "_fd"))
        parts.append(j[["home", "away", "HomeTeam", "AwayTeam"]].rename(columns={"HomeTeam": "fd_home", "AwayTeam": "fd_away"}))
    return pd.concat(parts, ignore_index=True)


def ask_gemini(league: str, unresolved: List[str], known: List[str], key: str) -> Dict[str, str]:
    """Known names for the unresolved fixture names, asked of Gemini once (no web search); only
    answers that are in ``known`` are kept."""
    prompt = (f"League: {league}. These football team names come from a fixtures feed and do not match our records. "
              f"Allowed answers (our records): {json.dumps(sorted(known), ensure_ascii=False)}. For each unmatched name below, "
              f"answer with the allowed name of the SAME club, or null if no allowed name is that club (a reserve or youth "
              f"side is a different club). Reply with a JSON object {{unmatched name: allowed name or null}} and nothing else.\n"
              f"Unmatched: {json.dumps(unresolved, ensure_ascii=False)}")
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
    try:
        r = requests.post(GEMINI_URL, params={"key": key}, json=body, timeout=90)
        r.raise_for_status()
        answer = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        logger.warning(f"Team-name matching via Gemini unavailable for {league}: {redact(e)}")
        return {}
    allowed = set(known)
    return {_key(k): v for k, v in answer.items() if isinstance(v, str) and v in allowed and k in unresolved}


def load_aliases(path: Path = ALIASES_FILE) -> Dict[str, Dict[str, str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_aliases(aliases: Dict[str, Dict[str, str]], path: Path = ALIASES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aliases, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def update_aliases(known_by_league: Dict[str, Iterable[str]], fixture_names: Dict[str, Iterable[str]],
                   ledger_by_league: Dict[str, List[Dict]], results_by_league: Dict[str, pd.DataFrame],
                   table: Optional[Dict[str, str]] = None, path: Path = ALIASES_FILE,
                   ask_ai: bool = True) -> Dict[str, Dict]:
    """Refresh the alias cache, one league at a time: learn from graded matches, then ask Gemini about
    the names still unresolved. Returns {league: {"teams": n, "unresolved": [names]}}."""
    aliases = load_aliases(path)
    key = get_secret("GEMINI_API_KEY")
    report: Dict[str, Dict] = {}
    for league, known in known_by_league.items():
        known = set(known)
        mine = aliases.setdefault(league, {})
        mine.update({k: v for k, v in learn_aliases(ledger_pairs(ledger_by_league.get(league, []),
                                                                 results_by_league.get(league, pd.DataFrame())), known).items()
                     if k not in mine})
        names = sorted(set(fixture_names.get(league, [])))
        unresolved = [n for n in names if resolve(n, known, mine, table) is None]
        if unresolved and ask_ai and is_usable_key(key):
            mine.update(ask_gemini(league, unresolved, sorted(known), key))
            unresolved = [n for n in unresolved if resolve(n, known, mine, table) is None]
        report[league] = {"teams": len(names), "unresolved": unresolved}
    save_aliases(aliases, path)
    return report
