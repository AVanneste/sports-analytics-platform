"""Player birth dates from Wikidata, matched to tennis-data names, for the age features.

One SPARQL query returns every person with an ATP or WTA player ID and a birth date. Each
tennis-data name ("Auger-Aliassime F.", "Wang Xin.", "Fernandez L.A.") is matched to the people of
the same tour whose name ends (else, for Chinese/Korean order, starts) with that surname and whose
given names fit the initials, and who were 14-50 years old over the player's matches. When several
people remain, the one with at least twice the Wikipedia articles (sitelinks) of the next is taken;
otherwise the name is left unmatched, so an age is missing rather than wrong.
"""
import functools
import logging
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests

from tennis_core.config import RAW_DATA_DIR
from tennis_core.utils.helpers import match_player_to_database, strip_accents

logger = logging.getLogger(__name__)

BIRTHDATES_PATH = RAW_DATA_DIR / "player_birthdates.csv"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
REFRESH_DAYS = 7
QUERY = """SELECT ?p ?label ?dob ?atp ?wta ?links WHERE {
  { ?p wdt:P536 ?atp } UNION { ?p wdt:P597 ?wta }
  ?p wdt:P569 ?dob . FILTER(YEAR(?dob) >= 1965)
  ?p rdfs:label ?label FILTER(LANG(?label) = "en" || LANG(?label) = "mul")
  ?p wikibase:sitelinks ?links .
}"""
MIN_AGE, MAX_AGE = 14, 50  # Venus Williams still played at 45
_GERMAN = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
# letters accent stripping leaves alone ("Đere" is "Djere" in tennis-data, "Łukasz" is "L.")
_LATIN = str.maketrans({"Đ": "Dj", "đ": "dj", "Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "Æ": "Ae", "æ": "ae",
                        "ı": "i", "Ð": "D", "ð": "d", "Þ": "Th", "þ": "th"})


def _tokens(text: str) -> List[str]:
    text = strip_accents(text.translate(_LATIN)).lower().replace("-", " ").replace("'", " ").replace(".", " ")
    return re.sub(r"[^a-z ]", "", text).split()


def _spellings(label: str) -> List[List[str]]:
    """Token lists for a name, plus the German transliteration ("Görges" is "Goerges" in tennis-data)."""
    plain, german = _tokens(label), _tokens(label.translate(_GERMAN))
    return [plain] if german == plain else [plain, german]


def fetch_wikidata_people() -> List[Dict]:
    """Everyone Wikidata gives an ATP or WTA player ID and a birth date: tour, names, birth date, sitelinks."""
    response = requests.get(WIKIDATA_SPARQL, params={"query": QUERY, "format": "json"}, timeout=120,
                            headers={"User-Agent": "AG-sports-data/1.0 (personal research)"})
    response.raise_for_status()
    people: Dict[Tuple[str, str], Dict] = {}
    for b in response.json()["results"]["bindings"]:
        qid = b["p"]["value"].rsplit("/", 1)[-1]
        tour = "atp" if "atp" in b else "wta"
        person = people.setdefault((qid, tour), {"qid": qid, "tour": tour, "labels": set(),
                                                 "dob": b["dob"]["value"][:10], "links": int(b["links"]["value"])})
        person["labels"].add(b["label"]["value"])
    return list(people.values())


def parse_name(name: str) -> Tuple[List[str], str, bool]:
    """tennis-data name -> (surname tokens, initials, one-letter-per-given-name initials?)."""
    parts = str(name).split()
    if len(parts) < 2:
        return _tokens(name), "", False
    initials = parts[-1]
    letters = re.sub(r"[^a-z]", "", strip_accents(initials).lower())
    return _tokens(" ".join(parts[:-1])), letters, initials.count(".") > 1


def _given_fits(given: List[str], initials: str, per_name: bool) -> bool:
    if not initials:
        return True
    if not given:
        return False
    if per_name:  # "L.A." -> Leylah Annie (a missing middle name is fine)
        return given[0].startswith(initials[0]) and all(
            i >= len(given) or given[i].startswith(c) for i, c in enumerate(initials[1:], start=1))
    return "".join(given).startswith(initials) or given[0].startswith(initials)


def _surname_last(tokens: List[str], surname: List[str], initials: str, per_name: bool) -> bool:
    """"Felix Auger-Aliassime"; spacing may differ ("O Connell" is "O'Connell")."""
    return any("".join(tokens[j:]) == "".join(surname) and _given_fits(tokens[:j], initials, per_name)
               for j in range(1, len(tokens)))


def _surname_first(tokens: List[str], surname: List[str], initials: str, per_name: bool) -> bool:
    """Chinese/Korean order: "Wang Xinyu"."""
    return any("".join(tokens[:j]) == "".join(surname) and _given_fits(tokens[j:], initials, per_name)
               for j in range(1, len(tokens)))


def _name_starts(tokens: List[str], surname: List[str], initials: str, per_name: bool) -> bool:
    """Shortened surnames: "Bautista R." is Roberto Bautista Agut, "Mpetshi G." Giovanni Mpetshi Perricard."""
    k = len(surname)
    return any(tokens[j:j + k] == surname and len(tokens) > j + k and _given_fits(tokens[:j], initials, per_name)
               for j in range(1, len(tokens) - k))


def match_players(players: pd.DataFrame, people: List[Dict]) -> pd.DataFrame:
    """Birth dates for tennis-data players (columns name, tour, first, last: match date span)."""
    index = defaultdict(list)  # (tour, last token) -> people, to keep the search small
    for p in people:
        p["spellings"] = [t for label in p["labels"] for t in _spellings(label)]
        for tokens in p["spellings"]:
            for token in tokens:
                index[(p["tour"], token)].append(p)
    rows = []
    for r in players.itertuples(index=False):
        surname, initials, per_name = parse_name(r.name)
        if not surname:
            continue
        pool = {id(p): p for key in {surname[0], "".join(surname)} for p in index[(r.tour, key)]}.values()

        def plausible(p) -> bool:
            dob = pd.Timestamp(p["dob"])
            return (pd.Timestamp(r.first) - dob).days / 365.25 >= MIN_AGE and (pd.Timestamp(r.last) - dob).days / 365.25 <= MAX_AGE

        for rule in (_surname_last, _surname_first, _name_starts):
            found = [p for p in pool if plausible(p) and any(rule(t, surname, initials, per_name) for t in p["spellings"])]
            if found:
                break
        chosen = None
        if len({p["dob"] for p in found}) == 1:
            chosen = found[0]
        elif found:
            ranked = sorted(found, key=lambda p: -p["links"])
            if ranked[0]["links"] >= 2 * ranked[1]["links"]:
                chosen = ranked[0]
        if chosen:
            rows.append({"name": r.name, "tour": r.tour, "birthdate": chosen["dob"], "wikidata": chosen["qid"]})
    return pd.DataFrame(rows, columns=["name", "tour", "birthdate", "wikidata"])


def player_spans(histories: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Each tennis-data player's first and last match date, per tour."""
    frames = []
    for tour, df in histories.items():
        dates = pd.to_datetime(df["Date"])
        for col in ("Winner", "Loser"):
            frames.append(pd.DataFrame({"name": df[col], "tour": tour, "date": dates}))
    long = pd.concat(frames).dropna()
    return long.groupby(["name", "tour"])["date"].agg(first="min", last="max").reset_index()


def update_birthdates(histories: Dict[str, pd.DataFrame], force: bool = False,
                      today: Optional[pd.Timestamp] = None) -> int:
    """Rebuild data/raw/player_birthdates.csv when its query date is REFRESH_DAYS old; returns the
    players dated. The date is stored in the file: a fresh git checkout makes every file look new."""
    today = pd.Timestamp(today or pd.Timestamp.now(tz="UTC").date())
    if not force and BIRTHDATES_PATH.exists():
        current = pd.read_csv(BIRTHDATES_PATH)
        queried = pd.to_datetime(current.get("queried", pd.Series(dtype=str))).max()
        if pd.notna(queried) and today - queried < pd.Timedelta(days=REFRESH_DAYS):
            return len(current)
    table = match_players(player_spans(histories), fetch_wikidata_people())
    if table.empty:
        return 0
    BIRTHDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.assign(queried=today.strftime("%Y-%m-%d")).sort_values(["tour", "name"]).to_csv(BIRTHDATES_PATH, index=False)
    load_birthdates.cache_clear()
    birthdate_for.cache_clear()
    logger.info(f"[Wikidata] birth dates for {len(table)} players")
    return len(table)


@functools.lru_cache(maxsize=1)
def load_birthdates() -> Dict[str, str]:
    """tennis-data name -> birth date (YYYY-MM-DD); a name dated differently on both tours is dropped."""
    if not BIRTHDATES_PATH.exists():
        return {}
    table = pd.read_csv(BIRTHDATES_PATH).drop_duplicates(subset=["name", "birthdate"])
    table = table[~table["name"].duplicated(keep=False)]
    return dict(zip(table["name"], table["birthdate"]))


@functools.lru_cache(maxsize=4096)
def birthdate_for(player_name: str) -> Optional[str]:
    """Birth date for a tennis-data name, or another spelling of it ("Jannik Sinner")."""
    births = load_birthdates()
    if player_name in births or player_name.endswith("."):  # an unmatched tennis-data name stays unknown
        return births.get(player_name)
    return births.get(match_player_to_database(player_name, list(births)))
