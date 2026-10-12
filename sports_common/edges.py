"""+EV Belgian prices: each matched book price against Pinnacle's vig-free price for the same selection.

Pinnacle's board (sports_common/pinnacle.py) is grouped into complete markets (moneyline
home/draw/away, a total's over/under at one line, a spread's two sides) and de-vigged by the power
method; a Belgian price row (sports_common/belgian_board.py) of a matched event
(sports_common/matching.py) then has a fair probability and an EV.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sports_common.betting import MAX_CREDIBLE_EV, devig_power, expected_value, kelly_fraction

MIN_EV = 0.02
MAX_ODDS = 6.0
WITHIN_HOURS = 36
# Pinnacle's max stake on the market: a low limit is a line Pinnacle itself does not trust yet.
MIN_LIMIT = {"Soccer": 250, "Tennis": 200, "Basketball": 200, "Hockey": 200, "Volleyball": 100, "Handball": 100}
_FLIP = {"home": "away", "away": "home"}
DROP = 0.04  # a rise in Pinnacle's fair probability (4 points) within HISTORY_HOURS is a drop
HISTORY_HOURS = 6
REALERT_EV = 0.02  # a selection is alerted again only once its EV grew this much


def _market_key(row: Dict) -> Tuple:
    """One complete market: the spread's key is the home line, so both sides share it."""
    line = row.get("line")
    if row["market"] == "spread" and line is not None and row["selection"] == "away":
        line = -line
    return row["event_id"], row["market"], row["period"], row.get("units"), row.get("side"), line


def _selection_key(row: Dict) -> Tuple:
    return row["event_id"], row["market"], row["period"], row.get("units"), row.get("side"), row.get("line"), row["selection"]


def fair_prices(pinnacle_rows: Iterable[Dict]) -> Dict[Tuple, Dict]:
    """{selection key: {"prob", "limit", "price"}} from every complete Pinnacle market."""
    markets: Dict[Tuple, List[Dict]] = {}
    for row in pinnacle_rows:
        markets.setdefault(_market_key(row), []).append(row)
    fair = {}
    for key, rows in markets.items():
        expected = 3 if key[1] == "moneyline" and any(r["selection"] == "draw" for r in rows) else 2
        if len(rows) != expected or len({r["selection"] for r in rows}) != expected:
            continue
        probs = devig_power([r["price"] for r in rows])
        if probs is None:
            continue
        for row, prob in zip(rows, probs):
            fair[_selection_key(row)] = {"prob": float(prob), "limit": row.get("limit"), "price": row["price"],
                                         "alternate": bool(row.get("alternate")), "outcomes": expected}
    return fair


def oriented(row: Dict, game_id, swapped: bool) -> Dict:
    """A book row re-keyed onto its Pinnacle game, home and away swapped back when the book lists
    them the other way round (a spread line belongs to its team, so it stays)."""
    out = {**row, "event_id": game_id}
    if swapped:
        out["selection"] = _FLIP.get(row["selection"], row["selection"])
        out["side"] = _FLIP.get(row.get("side"), row.get("side"))
    return out


def _book_outcomes(book_rows: Iterable[Dict]) -> Dict[Tuple, int]:
    """Number of outcomes of each (book, market): a 3-way book market (with a draw) must not be
    priced against a 2-way Pinnacle one (handball, ice hockey with overtime)."""
    count: Dict[Tuple, int] = {}
    for row in book_rows:
        key = (row["book"], _market_key(row))
        count[key] = count.get(key, 0) + 1
    return count


def misread_markets(book_rows: Iterable[Dict]) -> set:
    """(book, market key) of book markets whose sides add up to under 100%: no book prices below
    a zero margin, so such a market was read wrongly (another market under a familiar name)."""
    implied: Dict[Tuple, float] = {}
    for row in book_rows:
        key = (row["book"], _market_key(row))
        implied[key] = implied.get(key, 0.0) + 1 / row["price"]
    return {key for key, total in implied.items() if total < 1.0}


def find_edges(book_rows: Iterable[Dict], matches: Dict[Tuple, Tuple], fair: Dict[Tuple, Dict], games: Dict,
               min_ev: float = MIN_EV, now: Optional[datetime] = None, max_ev: float = MAX_CREDIBLE_EV,
               max_odds: float = MAX_ODDS, within_hours: float = WITHIN_HOURS,
               min_limit: Optional[Dict[str, float]] = None) -> List[Dict]:
    """Book prices with EV >= ``min_ev`` against Pinnacle, best first. ``games`` maps a Pinnacle
    event_id to its sport/league/start/home/away. Skipped: misread book markets, EV past MAX_CREDIBLE_EV (a mismatched
    market, not value), odds over MAX_ODDS, kick-off past WITHIN_HOURS, Pinnacle limit under MIN_LIMIT
    (each overridable by its argument)."""
    min_limit = MIN_LIMIT if min_limit is None else min_limit
    now = now or datetime.now(timezone.utc)
    book_rows = list(book_rows)
    misread = misread_markets(book_rows)
    outcomes = _book_outcomes(book_rows)
    edges = []
    for row in book_rows:
        match = matches.get((row["book"], row["event_id"]))
        if match is None or row["price"] > max_odds or (row["book"], _market_key(row)) in misread:
            continue
        game = games[match[0]]
        start = datetime.fromisoformat(str(game["start"]).replace("Z", "+00:00"))
        if not now < start <= now + timedelta(hours=within_hours):
            continue
        priced = oriented(row, *match)
        ref = fair.get(_selection_key(priced))
        if (ref is None or (ref["limit"] or 0) < min_limit.get(game["sport"], 250)
                or outcomes[(row["book"], _market_key(row))] != ref.get("outcomes", outcomes[(row["book"], _market_key(row))])):
            continue
        ev = expected_value(ref["prob"], row["price"])
        if not min_ev <= ev < max_ev:
            continue
        edges.append({**priced, "sport": game["sport"], "league": game.get("league"), "start": game["start"],
                      "home": game["home"], "away": game["away"], "book_event_id": row["event_id"],
                      "fair_prob": ref["prob"], "fair_odds": round(1 / ref["prob"], 3), "pinnacle_price": ref["price"],
                      "limit": ref["limit"], "ev": ev, "stake": kelly_fraction(ref["prob"], row["price"])})
    return sorted(edges, key=lambda e: e["ev"], reverse=True)


def selection_id(key: Tuple) -> str:
    return json.dumps(list(key))


def track_drops(history: Dict[str, List], fair: Dict[Tuple, Dict], games: Iterable, now: datetime) -> Dict[Tuple, float]:
    """Update ``history`` ({selection id: [[unix time, fair prob], ...]}, last HISTORY_HOURS, main
    lines of ``games`` only, a point stored when the probability moved) and return
    {selection key: probability before the drop} for selections whose fair probability rose by
    DROP or more over that window."""
    games, ts = set(games), now.timestamp()
    cutoff = ts - HISTORY_HOURS * 3600
    drops = {}
    for key, ref in fair.items():
        if ref["alternate"] or key[0] not in games:
            continue
        sid = selection_id(key)
        points = [p for p in history.get(sid, []) if p[0] >= cutoff]
        if points and ref["prob"] - min(p[1] for p in points) >= DROP:
            drops[key] = min(p[1] for p in points)
        if not points or abs(points[-1][1] - ref["prob"]) >= 0.005:
            points.append([ts, round(ref["prob"], 4)])
        history[sid] = points
    for sid in [sid for sid, points in history.items() if not points or points[-1][0] < cutoff]:
        del history[sid]
    return drops


def select_alerts(edges: Iterable[Dict], drops: Dict[Tuple, float], sent: Dict[str, Dict], min_ev: float = MIN_EV,
                  now: Optional[datetime] = None) -> List[Dict]:
    """One alert per selection (its best book price, with every book paying it; the best line only
    among a market's lines) that is +EV by
    ``min_ev`` or a Pinnacle drop the books still pay, unless already sent at an EV within
    REALERT_EV. Records what it returns in ``sent`` and forgets games that have started."""
    now = now or datetime.now(timezone.utc)
    for sid in [sid for sid, s in sent.items() if datetime.fromisoformat(s["start"].replace("Z", "+00:00")) <= now]:
        del sent[sid]
    best: Dict[Tuple, Dict] = {}
    for e in edges:
        key = _selection_key(e)
        if e["ev"] < min_ev and key not in drops:
            continue
        group = best.setdefault(key, {**e, "books": {}, "dropped_from": drops.get(key)})
        group["books"][e["book"]] = e["price"]
        if e["price"] > group["price"]:
            group.update({k: e[k] for k in ("book", "price", "ev", "stake")})
    by_line: Dict[Tuple, Tuple] = {}  # one line per market and team: "-2.5" over "-1.5" and "-3.5" when its EV is best
    for key, alert in best.items():
        market = key[:5] + key[6:]
        if market not in by_line or alert["ev"] > by_line[market][1]["ev"]:
            by_line[market] = (key, alert)
    alerts = []
    for key, alert in by_line.values():
        previous = sent.get(selection_id(key))
        if previous and alert["ev"] < previous["ev"] + REALERT_EV:
            continue
        sent[selection_id(key)] = {"ev": alert["ev"], "start": alert["start"]}
        alerts.append(alert)
    return sorted(alerts, key=lambda a: a["ev"], reverse=True)


ALERT_COLUMNS = ("captured_at", "sport", "league", "start", "home", "away", "market", "period", "units", "side", "line",
                 "selection", "book", "price", "books", "fair_prob", "ev", "stake", "limit", "dropped_from",
                 "close_prob", "ev_at_close")


def track_closing(open_alerts: Dict[str, Dict], sent: Iterable[Dict], fair: Dict[Tuple, Dict], now: datetime) -> List[Dict]:
    """Follow every sent alert to kick-off: ``open_alerts`` (kept in the state) gets the newly
    ``sent`` ones, each open alert's ``close_prob`` becomes Pinnacle's current fair probability
    while its game has not started (the last one seen is the closing price), and alerts whose game
    started are returned as ALERT_COLUMNS rows with their EV at the close (the CLV) and dropped."""
    stamp = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    for a in sent:
        row = {c: a.get(c) for c in ALERT_COLUMNS if c not in ("captured_at", "close_prob", "ev_at_close")}
        open_alerts[f"{selection_id(_selection_key(a))}@{stamp}"] = {
            **row, "event_id": a["event_id"], "captured_at": stamp, "books": json.dumps(a.get("books") or {}), "close_prob": None}
    closed = []
    for alert_id, a in list(open_alerts.items()):
        if datetime.fromisoformat(a["start"].replace("Z", "+00:00")) > now:
            ref = fair.get(_selection_key(a))
            if ref:
                a["close_prob"] = round(ref["prob"], 4)
            continue
        close = a.get("close_prob")
        closed.append({**{c: a.get(c) for c in ALERT_COLUMNS},
                       "ev_at_close": round(a["price"] * close - 1, 4) if close else None})
        del open_alerts[alert_id]
    return closed


def web_payload(open_alerts: Dict[str, Dict], closed: List[Dict], now: datetime) -> Dict:
    """The app's Alerts tab: open alerts with their EV now (alert price against Pinnacle's latest
    fair price) and the closed alerts' CLV, overall and by sport, market, book and kind."""
    latest: Dict[Tuple, Dict] = {}  # a re-alerted selection (its EV grew) shows once, as last sent
    for a in open_alerts.values():
        key = tuple(a.get(k) for k in ("event_id", "home", "market", "period", "units", "side", "line", "selection"))
        if key not in latest or a["captured_at"] > latest[key]["captured_at"]:
            latest[key] = a
    open_rows = []
    for a in latest.values():
        prob = a.get("close_prob") or a.get("fair_prob")
        open_rows.append({**{k: a.get(k) for k in ALERT_COLUMNS if k not in ("close_prob", "ev_at_close")},
                          "books": json.loads(a["books"]) if isinstance(a.get("books"), str) else a.get("books"),
                          "fair_prob_now": prob, "ev_now": round(a["price"] * prob - 1, 4) if prob else None})
    done = [r for r in closed if r.get("ev_at_close") not in (None, "")]

    def summary(rows: List[Dict]) -> Dict:
        if not rows:
            return {"alerts": 0}
        ev_sent = [float(r["ev"]) for r in rows]
        ev_close = [float(r["ev_at_close"]) for r in rows]
        return {"alerts": len(rows), "ev_sent_pct": round(100 * sum(ev_sent) / len(rows), 2),
                "ev_close_pct": round(100 * sum(ev_close) / len(rows), 2),
                "beat_close_pct": round(100 * sum(e > 0 for e in ev_close) / len(rows), 1)}

    def by(field) -> List[Dict]:
        groups: Dict[str, List[Dict]] = {}
        for r in done:
            groups.setdefault(field(r), []).append(r)
        return sorted(({"group": g, **summary(rows)} for g, rows in groups.items()), key=lambda x: -x["alerts"])

    market = lambda r: r["market"] + (f" ({str(r['units']).lower()})" if r.get("units") not in (None, "", "nan") else "")
    return {"generated_at": now.isoformat(timespec="seconds"),
            "open": sorted(open_rows, key=lambda r: r["start"]),
            "summary": summary(done),
            "by_sport": by(lambda r: r["sport"]), "by_market": by(market), "by_book": by(lambda r: r["book"]),
            "by_kind": by(lambda r: "drop" if r.get("dropped_from") not in (None, "", "nan") else "ev"),
            "recent": sorted(done, key=lambda r: r["start"], reverse=True)[:150]}
