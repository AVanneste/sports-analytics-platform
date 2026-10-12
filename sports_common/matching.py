"""Which Pinnacle game is a Belgian book's event: same sport, close kick-off, both names agreeing.

Names differ across feeds ("KRC Genk" / "Genk", "Zheng Qinwen" / "Qinwen Zheng"), so each name
becomes a set of words without accents or club noise and two names score by overlap. Markers that
make it another team (U21, women, reserves) must agree. Tennis times are loose (books show the
expected court time, Pinnacle the slot), so tennis gets a wide window and relies on the names.
A book event pairs only with a clear best game; anything doubtful stays unmatched.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

WINDOW_MINUTES = {"Tennis": 12 * 60}  # other sports: DEFAULT_WINDOW
DEFAULT_WINDOW = 90
MIN_SCORE = 0.5

_EXPAND = {"st": "saint", "sint": "saint", "internazionale": "inter", "praha": "prague", "kobenhavn": "copenhagen",
           "munchen": "munich", "bayern": "bayern", "utd": "united", "women": "w", "reserves": "ii", "jong": "ii"}
_NOISE = {"fc", "cf", "sc", "afc", "ac", "as", "sv", "sk", "kv", "krc", "kaa", "rsc", "club", "de", "the", "royal",
          "royale", "cd", "ud", "fk", "bk", "if", "ssc", "us", "cp", "bc", "kk", "hc", "fsv", "vfb", "vfl", "tsv", "rc"}
_MARKERS = {"u17", "u18", "u19", "u20", "u21", "u23", "w", "ii", "b"}


def tokens(name: str) -> frozenset:
    plain = "".join(c for c in unicodedata.normalize("NFD", str(name or "")) if unicodedata.category(c) != "Mn").lower()
    words = re.sub(r"[^a-z0-9 ]", " ", plain.replace("'", "")).split()
    return frozenset(_EXPAND.get(w, w) for w in words if w not in _NOISE)


def _same_word(a: str, b: str) -> bool:
    """Equal, an abbreviation ("go" / "goianiense"), or a spelling variant ("warszawa" / "warsaw")."""
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 2 and long_.startswith(short)) or (
        len(short) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.8)


def player_key(name: str) -> str:
    """A player's name as books and Pinnacle both spell it: lower case, no accents or punctuation."""
    plain = "".join(c for c in unicodedata.normalize("NFD", str(name or "")) if unicodedata.category(c) != "Mn").lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", plain).split())


def name_score(a: str, b: str) -> float:
    """0..1: share of agreeing words (1 when one name's words all appear in the other), 0 when markers differ."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb or (ta & _MARKERS) != (tb & _MARKERS):
        return 0.0
    ta, tb = ta - _MARKERS or ta, tb - _MARKERS or tb
    common = sum(any(_same_word(x, y) for y in tb) for x in ta)
    if common >= min(len(ta), len(tb)):
        return 1.0
    return common / (len(ta) + len(tb) - common)


def _minutes_apart(a: str, b: str) -> float:
    parse = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return abs((parse(a) - parse(b)).total_seconds()) / 60


def pair_score(event: Dict, game: Dict) -> Tuple[float, bool]:
    """(score, swapped): the weaker of the two names' scores, home/away either way round."""
    straight = min(name_score(event["home"], game["home"]), name_score(event["away"], game["away"]))
    swapped = min(name_score(event["home"], game["away"]), name_score(event["away"], game["home"]))
    return (swapped, True) if swapped > straight else (straight, False)


def match_events(events: Iterable[Dict], games: List[Dict]) -> Dict[Tuple[str, object], Tuple[object, bool]]:
    """{(book, event_id): (Pinnacle event_id, swapped)} for each book event (dicts with book,
    event_id, sport, start, home, away) whose best game scores at least MIN_SCORE and clearly
    beats the runner-up."""
    by_sport: Dict[str, List[Dict]] = {}
    for g in games:
        by_sport.setdefault(g["sport"], []).append(g)
    matched = {}
    for e in events:
        window = WINDOW_MINUTES.get(e["sport"], DEFAULT_WINDOW)
        scored = sorted(((*pair_score(e, g), g["event_id"]) for g in by_sport.get(e["sport"], [])
                         if _minutes_apart(e["start"], g["start"]) <= window), key=lambda s: s[0], reverse=True)
        if not scored or scored[0][0] < MIN_SCORE or (len(scored) > 1 and scored[1][0] >= scored[0][0] - 0.2):
            continue
        score, swapped, game_id = scored[0]
        matched[(e["book"], e["event_id"])] = (game_id, swapped)
    return matched


def unique_events(rows: Iterable[Dict], keys=("book", "event_id", "sport", "start", "home", "away")) -> List[Dict]:
    """One dict per event out of price rows."""
    seen: Dict[Tuple, Dict] = {}
    for r in rows:
        seen.setdefault((r.get("book"), r["event_id"]), {k: r.get(k) for k in keys})
    return list(seen.values())


def match_by_players(book_rows: Iterable[Dict], pinnacle_rows: Iterable[Dict], matched: Dict) -> Dict:
    """{(book, event_id): (Pinnacle event_id, False)} for book events with player props that
    ``match_events`` could not pair (Pinnacle lists props before the game itself): the Pinnacle
    event with the same props players (two or more in common) kicking off within 12 hours."""
    players: Dict[Tuple, set] = {}
    starts: Dict[Tuple, str] = {}
    for r in book_rows:
        if r["market"] == "player_prop" and (r["book"], r["event_id"]) not in matched:
            players.setdefault((r["book"], r["event_id"]), set()).add(r["side"])
            starts[(r["book"], r["event_id"])] = r["start"]
    pin_players: Dict[object, set] = {}
    pin_starts: Dict[object, str] = {}
    for r in pinnacle_rows:
        if r["market"] == "player_prop":
            pin_players.setdefault(r["event_id"], set()).add(r["side"])
            pin_starts[r["event_id"]] = r["start"]
    found = {}
    for key, names in players.items():
        best = max(((len(names & ps), eid) for eid, ps in pin_players.items()
                    if _minutes_apart(starts[key], pin_starts[eid]) <= 12 * 60), default=(0, None))
        if best[0] >= 2:
            found[key] = (best[1], False)
    return found
