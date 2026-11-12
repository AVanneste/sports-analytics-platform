"""Settle alerts against real results: Napoleon's feed lists finished events with scores, period
scores and corners for every sport (about 15 days back).

``finished_events`` reads them, ``scores`` turns one into the numbers a market is settled on, and
``settle`` gives an alert's outcome and its profit per unit staked. Player props (no player
statistics in the feed), bookings and first-half corners are not settled.
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from sports_common.belgian_board import MONEYLINE_ONLY, REGULATION, SUPERBET_SPORTS
from sports_common.matching import match_events
from sports_common.superbet import split_match_name, superbet_get

RESULT_COLUMNS = ("captured_at", "sport", "start", "home", "away", "market", "period", "units", "side", "line",
                  "selection", "book", "price", "score_home", "score_away", "result", "pnl")
KEY = RESULT_COLUMNS[:12]
_EXTRA = re.compile(r"overtime|extra|penalt", re.I)
_THREE_WAY = {"Soccer", "Handball"}  # a level score loses a home/away moneyline (elsewhere it cannot happen or is a push)


def finished_events(start: datetime, end: datetime, chunk_hours: int = 12) -> List[Dict]:
    """Finished events of our sports kicking off in [start, end) (naive UTC), as
    {event_id, sport, start, home, away, meta}."""
    out, cursor = {}, start
    while cursor < end:
        stop = min(cursor + timedelta(hours=chunk_hours), end)
        payload = superbet_get("events/by-date", {"currentStatus": "finished",
                                                  "startDate": cursor.strftime("%Y-%m-%d %H:%M:%S"),
                                                  "endDate": stop.strftime("%Y-%m-%d %H:%M:%S")})
        for e in payload.get("data") or []:
            meta = e.get("metadata") or {}
            home, away = split_match_name(e.get("matchName"))
            if e.get("sportId") in SUPERBET_SPORTS and meta.get("status") == "FINISHED" and home and away:
                out[e["eventId"]] = {"event_id": e["eventId"], "sport": SUPERBET_SPORTS[e["sportId"]],
                                     "start": e.get("utcDate"), "home": home, "away": away, "meta": meta}
        cursor = stop
    return list(out.values())


def _pair(d: Dict) -> Optional[Tuple[int, int]]:
    try:
        return int(d["homeTeamScore"]), int(d["awayTeamScore"])
    except (KeyError, TypeError, ValueError):
        return None


def scores(sport: str, meta: Dict, period: int, units: Optional[str]) -> Optional[Tuple[int, int]]:
    """(home, away) of the quantity a market counts, or None when the feed cannot tell.

    period 0 is the match (regular time in soccer and handball; overtime and shootout included in
    basketball and hockey), 1 the first half or set, REGULATION hockey's regular time. ``units``:
    None the main score (goals, points; sets in tennis and volleyball), "Games" tennis games,
    "Points" volleyball points, "Corners". Darts, snooker, esports and cricket (winner only): the feed's
    match score (sets, frames, maps; 1-0 in cricket), never its periods, which add up points or rounds."""
    if sport in MONEYLINE_ONLY:
        return _pair(meta) if period == 0 and units is None else None
    periods = [(p.get("type") or "", _pair(p)) for p in meta.get("periods") or []]
    if any(s is None for _, s in periods):
        return None
    regular = [s for t, s in periods if not _EXTRA.search(t)]
    extra = [(t, s) for t, s in periods if _EXTRA.search(t)]
    total = lambda parts: (sum(h for h, _ in parts), sum(a for _, a in parts))
    if units == "Corners":
        corners = (meta.get("homeTeamCorners"), meta.get("awayTeamCorners"))
        return (int(corners[0]), int(corners[1])) if period == 0 and None not in corners and sum(map(int, corners)) > 0 else None
    if units not in (None, "Games", "Points") or not regular:
        return None
    if sport in ("Tennis", "Volleyball"):
        sets = [s for s in regular if sum(s) > 0]
        won = (sum(h > a for h, a in sets), sum(a > h for h, a in sets))
        if max(won) < 2 or (sport == "Tennis" and any(max(s) < 6 for s in sets)):
            return None  # retirement or incomplete score
        if sport == "Tennis":  # a deciding match tie-break ("10-8") counts as one game
            sets = [((1, 0) if h > a else (0, 1)) if max(h, a) > 7 else (h, a) for h, a in sets]
        if period == 1:
            first = sets[0]
            return first if units or sport == "Tennis" else None
        if period != 0:
            return None
        return total(sets) if units in ("Games", "Points") else won
    if units is not None:
        return None
    if sport == "Hockey" and period in (1, 2, 3):  # one period of regular time
        return regular[period - 1] if len(regular) >= 3 else None
    if period == 1:
        half = regular[:len(regular) // 2] if len(regular) in (2, 4) else None
        return total(half) if half else None
    reg = total(regular)
    if sport in _THREE_WAY or period == REGULATION:
        return reg
    if period != 0:
        return None
    home, away = reg
    for t, (h, a) in extra:  # a shootout adds one goal to its winner
        if "penalt" in t.lower():
            home, away = home + (h > a), away + (a > h)
        else:
            home, away = home + h, away + a
    return home, away


def _grade(diff: float) -> float:
    """1 win, 0 push, -1 loss for a margin over the line."""
    return 1.0 if diff > 0 else -1.0 if diff < 0 else 0.0


def settle(alert: Dict, meta: Dict, swapped: bool = False) -> Optional[Dict]:
    """{score_home, score_away, result, pnl} for an alert (pnl per unit staked at its price), with
    scores in the alert's home/away order; None when the market cannot be settled."""
    if alert["market"] == "player_prop":
        return None
    units = alert.get("units") if isinstance(alert.get("units"), str) and alert.get("units") else None
    sc = scores(alert["sport"], meta, int(alert.get("period") or 0), units)
    if sc is None:
        return None
    home, away = (sc[1], sc[0]) if swapped else sc
    sel, line, market = alert["selection"], alert.get("line"), alert["market"]
    line = None if line is None or line != line else float(line)
    if market == "btts":  # regular time, like Pinnacle's
        if sel not in ("yes", "no"):
            return None
        grades = [1.0 if (sel == "yes") == (home > 0 and away > 0) else -1.0]
    elif market == "moneyline":
        if home == away:
            three_way = (alert["sport"] in _THREE_WAY or int(alert.get("period") or 0) == REGULATION
                         or (alert["sport"] == "Hockey" and int(alert.get("period") or 0) in (1, 2, 3)))  # a period can be drawn
            grades = [1.0 if sel == "draw" else -1.0 if three_way else 0.0]
        else:
            grades = [1.0 if sel == ("home" if home > away else "away") else -1.0]
    elif line is None:
        return None
    else:
        # quarter lines are two half stakes on the neighbouring lines
        lines = [line - 0.25, line + 0.25] if abs(line * 4) % 2 == 1 else [line]
        if market == "spread":
            margin = (home - away) if sel == "home" else (away - home)
            grades = [_grade(margin + l) for l in lines]
        else:
            side = alert.get("side") if isinstance(alert.get("side"), str) else None
            count = home + away if market == "total" else {"home": home, "away": away}.get(side)
            if count is None or sel not in ("over", "under"):
                return None
            grades = [_grade((count - l) if sel == "over" else (l - count)) for l in lines]
    price = float(alert["price"])
    pnl = sum((price - 1) if g > 0 else g for g in grades) / len(grades)
    mean = sum(grades) / len(grades)
    result = {1.0: "win", 0.5: "half_win", 0.0: "push", -0.5: "half_loss", -1.0: "loss"}[mean]
    return {"score_home": home, "score_away": away, "result": result, "pnl": round(pnl, 4)}


def settle_alerts(alerts: Iterable[Dict], events: List[Dict]) -> List[Dict]:
    """RESULT_COLUMNS rows for the alerts whose game is among the finished ``events`` (matched by
    sport, kick-off and names, home/away either way round) and whose market can be settled."""
    alerts = list(alerts)
    games = {}
    for a in alerts:
        games.setdefault((a["sport"], a["start"], a["home"], a["away"]), None)
    as_events = [{"book": "alert", "event_id": k, "sport": k[0], "start": k[1], "home": k[2], "away": k[3]} for k in games]
    matched = match_events(as_events, events)
    by_id = {e["event_id"]: e for e in events}
    rows = []
    for a in alerts:
        hit = matched.get(("alert", (a["sport"], a["start"], a["home"], a["away"])))
        outcome = settle(a, by_id[hit[0]]["meta"], hit[1]) if hit else None
        if outcome:
            rows.append({**{k: a.get(k) for k in RESULT_COLUMNS}, **outcome})
    return rows
