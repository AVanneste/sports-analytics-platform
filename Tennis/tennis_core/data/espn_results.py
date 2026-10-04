"""Recent ATP/WTA tour results from ESPN, converted to tennis-data.co.uk rows.

tennis-data.co.uk (the training source) refuses GitHub's servers, so the daily run cannot refresh
it. ESPN's scoreboard is reachable from anywhere. Its main-draw singles results are converted to
tennis-data rows and added wherever tennis-data does not have the match yet (it adds a tournament
only once it ends), so a later tennis-data refresh takes over automatically.
- Only tournaments tennis-data covers are kept (ATP/WTA 250 and up, no WTA 125s or qualifying).
- Surface, tier and format come from tennis-data's own rows for the same event.
- Player names are mapped to tennis-data's ("Sinner J.").
- Rankings are carried forward from each player's last tennis-data match.
"""
import logging
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from tennis_core.config import RAW_DATA_DIR
from tennis_core.data.espn_tennis import ESPN_TENNIS_BASE_URL, _espn_tennis_get
from tennis_core.utils.helpers import match_player_to_database, strip_accents

logger = logging.getLogger(__name__)

DRAW = {"atp": "mens-singles", "wta": "womens-singles"}
TIER_COLUMN = {"atp": "Series", "wta": "Tier"}
ALIASES = {"roland garros": "french open"}  # ESPN name -> tennis-data tournament
MAX_DAYS_FROM_LAST_EDITION = 21  # same event: within three weeks of last year's calendar date


def espn_results_path(circuit: str):
    return RAW_DATA_DIR / f"{circuit.lower()}_espn.csv"


def _clean(text) -> str:
    return strip_accents(str(text or "")).lower().strip()


def known_events(history: pd.DataFrame, circuit: str) -> List[Dict]:
    """Each tournament's latest tennis-data edition: name, city, date, tier, surface, court, format."""
    tier = TIER_COLUMN[circuit]
    latest = history.dropna(subset=["Tournament", "Date"]).sort_values("Date").groupby("Tournament").tail(1)
    return [{"tournament": r["Tournament"], "location": r.get("Location"), "date": pd.Timestamp(r["Date"]),
             "tier": r.get(tier), "surface": r.get("Surface"), "court": r.get("Court"), "best_of": r.get("Best of")}
            for _, r in latest.iterrows()]


def match_event(espn_name: str, match_date: pd.Timestamp, events: List[Dict]) -> Optional[Dict]:
    """The tennis-data tournament an ESPN event is (its name or city appears, at the same time of year)."""
    name = _clean(espn_name)
    name = ALIASES.get(name, name)

    def same_time_of_year(e) -> bool:
        gap = abs((match_date.dayofyear - e["date"].dayofyear + 183) % 366 - 183)
        return gap <= MAX_DAYS_FROM_LAST_EDITION

    for e in events:
        tournament, city = _clean(e["tournament"]), _clean(e["location"])
        named = len(tournament) >= 6 and tournament in name
        located = len(city) >= 3 and re.search(rf"\b{re.escape(city)}\b", name)
        if (named or located) and same_time_of_year(e):
            return e
    return None


def latest_ranks(history: pd.DataFrame) -> Dict[str, float]:
    """Each player's ranking at their most recent tennis-data match."""
    long = pd.concat([
        history[["Winner", "WRank", "Date"]].set_axis(["name", "rank", "Date"], axis=1),
        history[["Loser", "LRank", "Date"]].set_axis(["name", "rank", "Date"], axis=1),
    ])
    long["rank"] = pd.to_numeric(long["rank"], errors="coerce")
    long = long.dropna().sort_values("Date", kind="mergesort").drop_duplicates("name", keep="last")
    return dict(zip(long["name"], long["rank"].astype(float)))


def _player_name(athlete: Dict, known: List[str]) -> str:
    """tennis-data's name for the player, else 'Surname I.' built from ESPN's short name."""
    full = athlete.get("displayName") or athlete.get("fullName") or ""
    mapped = match_player_to_database(full, known)
    if mapped in known:
        return mapped
    short = athlete.get("shortName") or ""  # "L. Pavlovic"
    initial, _, surname = short.partition(" ")
    return f"{surname} {initial}" if surname and initial.endswith(".") else full


def convert_competition(comp: Dict, event: Dict, circuit: str, known: List[str],
                        ranks: Dict[str, float]) -> Optional[Dict]:
    """A tennis-data row for one completed ESPN singles match (None for walkovers and odd records)."""
    competitors = comp.get("competitors") or []
    if len(competitors) != 2 or not comp.get("status", {}).get("type", {}).get("completed"):
        return None
    winner = next((c for c in competitors if c.get("winner")), None)
    loser = next((c for c in competitors if not c.get("winner")), None)
    if winner is None or loser is None or not winner.get("athlete") or not loser.get("athlete"):
        return None
    w_sets, l_sets = winner.get("linescores") or [], loser.get("linescores") or []
    if not w_sets:  # walkover: never played
        return None
    best_of = int(event.get("best_of") or 3)
    w_name, l_name = _player_name(winner["athlete"], known), _player_name(loser["athlete"], known)
    row = {
        "Tournament": event["tournament"], "Location": event["location"], "Date": comp.get("date", "")[:10],
        TIER_COLUMN[circuit]: event["tier"], "Court": event["court"], "Surface": event["surface"],
        "Round": (comp.get("round") or {}).get("displayName"), "Best of": best_of,
        "Winner": w_name, "Loser": l_name, "WRank": ranks.get(w_name), "LRank": ranks.get(l_name),
        "Source": "ESPN",
    }
    games = [(int(sw.get("value") or 0), int(sl.get("value") or 0)) for sw, sl in zip(w_sets, l_sets)][:5]
    for i, (gw, gl) in enumerate(games, start=1):
        row[f"W{i}"], row[f"L{i}"] = gw, gl
    finished = lambda a, b: a >= 6 and (a - b >= 2 or a == 7)  # an unfinished set at a retirement does not count
    row["Wsets"] = sum(finished(gw, gl) for gw, gl in games)
    row["Lsets"] = sum(finished(gl, gw) for gw, gl in games)
    row["Comment"] = "Completed" if row["Wsets"] >= (best_of + 1) // 2 else "Retired"
    return row


def fetch_espn_rows(circuit: str, start: date, end: date, history: pd.DataFrame) -> List[Dict]:
    """tennis-data rows for the circuit's covered main-draw singles completed on ESPN in [start, end]."""
    circuit = circuit.lower()
    recent = history[pd.to_datetime(history["Date"]) >= pd.Timestamp(start) - pd.DateOffset(years=3)]
    events = known_events(recent, circuit)  # active tournaments and players only
    known = sorted(set(recent["Winner"].dropna()) | set(recent["Loser"].dropna()))
    ranks = latest_ranks(history)
    rows, day = [], start
    while day <= end:  # ESPN answers date ranges; two weeks at a time keeps responses small
        chunk_end = min(day + timedelta(days=13), end)
        data = _espn_tennis_get(f"{ESPN_TENNIS_BASE_URL}/{circuit}/scoreboard",
                                {"dates": f"{day:%Y%m%d}-{chunk_end:%Y%m%d}"}) or {}
        for e in data.get("events", []):
            for g in e.get("groupings", []):
                for comp in g.get("competitions", []):
                    if (comp.get("type") or {}).get("slug") != DRAW[circuit]:
                        continue
                    if "qualif" in _clean((comp.get("round") or {}).get("displayName")):
                        continue
                    when = pd.Timestamp(comp.get("date", "")[:10] or day)
                    event = match_event(e.get("name", ""), when, events)
                    if event is None:
                        continue
                    row = convert_competition(comp, event, circuit, known, ranks)
                    if row:
                        rows.append(row)
        day = chunk_end + timedelta(days=1)
    return rows


def update_espn_results(circuit: str, history: pd.DataFrame, today: Optional[date] = None) -> int:
    """Refresh data/raw/<circuit>_espn.csv with ESPN results from two weeks before the last tennis-data
    match (tournaments still running then are not in tennis-data yet) to today; returns its row count."""
    today = today or date.today()
    last = pd.Timestamp(history["Date"].max()).date()
    rows = fetch_espn_rows(circuit, last - timedelta(days=14), today, history)
    path = espn_results_path(circuit)
    frames = [pd.DataFrame(rows)]
    if path.exists():
        frames.insert(0, pd.read_csv(path))
    merged = pd.concat(frames, ignore_index=True)
    if merged.empty:
        return 0
    merged["Date"] = pd.to_datetime(merged["Date"]).dt.strftime("%Y-%m-%d")
    merged = merged.drop_duplicates(subset=["Date", "Winner", "Loser"], keep="last").sort_values("Date")
    merged = merged[pd.to_datetime(merged["Date"]) > pd.Timestamp(last) - pd.Timedelta(days=30)]  # keep it short
    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(path, index=False)
    logger.info(f"[ESPN results] {circuit.upper()}: {len(merged)} recent matches stored (tennis-data ends {last})")
    return len(merged)
