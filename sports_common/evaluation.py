"""Model-vs-market evaluation, shared by training (holdout metrics) and the ledger reports.

The bookmaker's vig-free price is the baseline every model has to beat. A model whose log
loss is not below the market's on the same matches has no demonstrated edge, whatever its
accuracy, so every report here puts the two side by side.
"""
import math
from statistics import mean, median
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np

from sports_common.betting import NOTIONAL_BANKROLL, bet_pnl

EPS = 1e-12


def devig(odds: Sequence[Optional[float]]) -> Optional[np.ndarray]:
    """Vig-free implied probabilities (multiplicative normalisation); None unless all prices are > 1."""
    try:
        prices = np.asarray([float(o) for o in odds], dtype=float)
    except (TypeError, ValueError):
        return None
    if prices.size == 0 or not np.all(np.isfinite(prices)) or np.any(prices <= 1.0):
        return None
    implied = 1.0 / prices
    return implied / implied.sum()


def overround(odds: Sequence[float]) -> float:
    """Bookmaker margin: sum of implied probabilities minus one."""
    return float(sum(1.0 / float(o) for o in odds) - 1.0)


def log_loss(probs: np.ndarray, y: np.ndarray) -> float:
    """Mean log loss; ``probs`` is (n, k) with ``y`` class indices, or (n,) P(y=1) with 0/1 labels."""
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y)
    if probs.ndim == 1:
        p = np.clip(probs, EPS, 1 - EPS)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    picked = np.clip(probs[np.arange(len(y)), y.astype(int)], EPS, 1.0)
    return float(-np.mean(np.log(picked)))


def brier(probs: np.ndarray, y: np.ndarray) -> float:
    """Mean Brier score (sum over classes for multiclass, the usual 0-2 scale for 1X2)."""
    probs = np.asarray(probs, dtype=float)
    y = np.asarray(y)
    if probs.ndim == 1:
        return float(np.mean((probs - y) ** 2))
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y.astype(int)] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def compare_to_market(model_probs: np.ndarray, market_probs: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """Score model and market on the same rows. ``log_loss_skill`` < 0 means the model beat the market."""
    model_probs = np.asarray(model_probs, dtype=float)
    market_probs = np.asarray(market_probs, dtype=float)
    y = np.asarray(y)
    if len(y) == 0:
        return {"n": 0}
    m_ll, k_ll = log_loss(model_probs, y), log_loss(market_probs, y)
    return {
        "n": int(len(y)),
        "model_log_loss": round(m_ll, 4),
        "market_log_loss": round(k_ll, 4),
        "log_loss_skill": round(m_ll - k_ll, 4),
        "model_brier": round(brier(model_probs, y), 4),
        "market_brier": round(brier(market_probs, y), 4),
    }


def blend(model_probs: np.ndarray, market_probs: np.ndarray, weight: float) -> np.ndarray:
    """``weight * model + (1 - weight) * market`` (rows stay normalised)."""
    return weight * np.asarray(model_probs, dtype=float) + (1.0 - weight) * np.asarray(market_probs, dtype=float)


def fit_market_blend_weight(model_probs: np.ndarray, market_probs: np.ndarray, y: np.ndarray,
                            grid: Optional[Iterable[float]] = None) -> Dict[str, float]:
    """Weight on the model (0..1) that minimises log loss of the model/market blend on ``y``."""
    grid = list(grid) if grid is not None else [round(w, 2) for w in np.linspace(0.0, 1.0, 21)]
    scores = {w: log_loss(blend(model_probs, market_probs, w), y) for w in grid}
    best = min(scores, key=scores.get)
    return {"weight": float(best), "log_loss": round(scores[best], 4), "n": int(len(y))}


def reliability_table(p: Sequence[float], y: Sequence[int], bins: int = 10) -> List[Dict[str, Any]]:
    """Calibration table: predicted vs observed frequency per probability bucket."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mask = (p >= lo) & ((p < hi) if b < bins - 1 else (p <= hi))
        if mask.any():
            rows.append({"bucket": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()),
                         "mean_pred": round(float(p[mask].mean()), 3), "observed": round(float(y[mask].mean()), 3)})
    return rows


def summarize_bets(stakes: Sequence[float], pnls: Sequence[float], claimed_evs: Sequence[float]) -> Dict[str, Any]:
    """ROI of settled bets next to the EV the model claimed when placing them."""
    n = len(pnls)
    staked = float(sum(stakes))
    pnl = float(sum(pnls))
    return {
        "n": n,
        "wins": int(sum(1 for x in pnls if x > 0)),
        "staked": round(staked, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round(100.0 * pnl / staked, 1) if staked > 0 else None,
        "claimed_ev_pct": round(100.0 * mean(claimed_evs), 1) if claimed_evs else None,
        "expected_pnl_if_claims_true": round(sum(s * e for s, e in zip(stakes, claimed_evs)), 2) if claimed_evs and len(claimed_evs) == n else None,
    }


def summarize_clv(values: Sequence[float]) -> Dict[str, Any]:
    """Closing-line value summary (fractions in, percent out)."""
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean_pct": round(100.0 * mean(values), 2),
        "median_pct": round(100.0 * median(values), 2),
        "share_positive_pct": round(100.0 * sum(1 for v in values if v > 0) / len(values), 1),
    }


# ------------------------------------------------------------------ football ledger
_FB_SELECTION_FIELDS = {
    "home win": ("odds_home", ("odds_home", "odds_draw", "odds_away"), 0),
    "draw": ("odds_draw", ("odds_home", "odds_draw", "odds_away"), 1),
    "away win": ("odds_away", ("odds_home", "odds_draw", "odds_away"), 2),
    "over 2.5 goals": ("odds_over25", ("odds_over25", "odds_under25"), 0),
    "under 2.5 goals": ("odds_under25", ("odds_over25", "odds_under25"), 1),
    "btts yes": ("odds_btts_yes", ("odds_btts_yes", "odds_btts_no"), 0),
    "btts no": ("odds_btts_no", ("odds_btts_yes", "odds_btts_no"), 1),
}


def _score_outcome(score: Any) -> Optional[tuple]:
    try:
        h, a = (int(x) for x in str(score).split("-"))
    except (TypeError, ValueError):
        return None
    return h, a


def _clv(first_odds: float, close_prices: Sequence[float], idx: int) -> Optional[Dict[str, float]]:
    close_probs = devig(close_prices)
    if close_probs is None:
        return None
    return {"price": first_odds / float(close_prices[idx]) - 1.0, "ev_at_close": first_odds * float(close_probs[idx]) - 1.0}


def evaluate_football_ledger(records: List[Dict[str, Any]],
                             competition_type: Optional[Callable[[Dict[str, Any]], str]] = None) -> Dict[str, Any]:
    """Model-vs-market quality, bet ROI (by market and competition type) and CLV for the football ledger."""
    settled = [r for r in records if r.get("status") == "settled" and _score_outcome(r.get("actual_score"))]

    # 1X2 and O/U 2.5 probability quality on records that carried market prices
    m1, k1, y1, m2, k2, y2 = [], [], [], [], [], []
    for r in settled:
        h, a = _score_outcome(r["actual_score"])
        market = devig([r.get("odds_home"), r.get("odds_draw"), r.get("odds_away")])
        probs = [r.get("prob_home"), r.get("prob_draw"), r.get("prob_away")]
        if market is not None and None not in probs:
            m1.append(np.asarray(probs, dtype=float) / sum(probs))
            k1.append(market)
            y1.append(0 if h > a else (1 if h == a else 2))
        ou_market = devig([r.get("odds_over25"), r.get("odds_under25")])
        if ou_market is not None and r.get("prob_over25") is not None:
            m2.append(float(r["prob_over25"]))
            k2.append(float(ou_market[0]))
            y2.append(int(h + a > 2.5))

    bets = [r for r in settled if r.get("won") is not None]
    by_market: Dict[str, List[Dict[str, Any]]] = {}
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in bets:
        by_market.setdefault(str((r.get("best_pick") or {}).get("market") or "unknown"), []).append(r)
        if competition_type:
            by_type.setdefault(competition_type(r), []).append(r)

    def _kelly(r):
        if r.get("kelly_stake") is not None:
            return float(r["kelly_stake"]), float(r.get("kelly_pnl") or 0.0)
        pick = r.get("best_pick") or {}  # legacy record written before kelly_stake existed
        stake = round(float(pick.get("kelly") or 0.0) * NOTIONAL_BANKROLL, 2)
        return stake, bet_pnl(stake, pick.get("odds"), r.get("won"))

    def _bet_summary(rows):
        evs = [float((r.get("best_pick") or {}).get("ev") or 0.0) for r in rows]
        flat = summarize_bets([float(r.get("stake") or 100.0) for r in rows], [float(r.get("flat_pnl") or 0.0) for r in rows], evs)
        kelly = [k for k in (_kelly(r) for r in rows) if k[0] > 0]
        flat["kelly"] = summarize_bets([k[0] for k in kelly], [k[1] for k in kelly], [])
        return flat

    # CLV: first value pick vs the latest pre-match prices seen for the same selection
    clv_price, clv_ev = [], []
    for r in records:
        fp = r.get("first_pick") if isinstance(r.get("first_pick"), dict) else None
        if not fp or not fp.get("odds") or not r.get("odds_captured_at"):
            continue
        if str(r["odds_captured_at"]) <= str(fp.get("logged_at") or ""):
            continue  # no later price observed
        spec = _FB_SELECTION_FIELDS.get(str(fp.get("selection") or "").strip().lower())
        if not spec:
            continue
        _, group, idx = spec
        prices = [r.get(f) for f in group]
        res = _clv(float(fp["odds"]), prices, idx) if None not in prices else None
        if res:
            clv_price.append(res["price"])
            clv_ev.append(res["ev_at_close"])

    return {
        "settled": len(settled),
        "pending": sum(1 for r in records if r.get("status") != "settled"),
        "match_odds_1x2": compare_to_market(np.array(m1), np.array(k1), np.array(y1)) if y1 else {"n": 0},
        "over_under_25": compare_to_market(np.array(m2), np.array(k2), np.array(y2)) if y2 else {"n": 0},
        "calibration_1x2": reliability_table(
            [p for row in m1 for p in row], [int(i == y) for y in y1 for i in range(3)]) if y1 else [],
        "bets": _bet_summary(bets),
        "bets_by_market": {k: _bet_summary(v) for k, v in sorted(by_market.items())},
        "bets_by_competition": {k: _bet_summary(v) for k, v in sorted(by_type.items())},
        "clv": {"price": summarize_clv(clv_price), "ev_at_close": summarize_clv(clv_ev)},
    }


# ------------------------------------------------------------------ tennis ledger
def evaluate_tennis_ledger(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Model-vs-market quality, bet ROI and CLV for the tennis ledger (probabilities stored in percent)."""
    graded = [r for r in records if r.get("status") in ("WON", "LOST", "NO_BET") and r.get("actual_winner")]

    m, k, y = [], [], []
    for r in graded:
        market = devig([r.get("p1_odds"), r.get("p2_odds")])
        if market is None or r.get("p1_prob") is None:
            continue
        m.append(float(r["p1_prob"]) / 100.0)
        k.append(float(market[0]))
        y.append(int(r["actual_winner"] == r.get("p1_name")))

    bets = [r for r in graded if r.get("status") in ("WON", "LOST")]
    evs = [float(r.get("best_ev") or 0.0) / 100.0 for r in bets]
    kelly = summarize_bets([float(r.get("best_stake") or r.get("stake") or 0.0) for r in bets],
                           [float(r.get("pnl") or 0.0) for r in bets], evs)
    flat = summarize_bets([20.0] * len(bets), [float(r.get("flat_pnl") or 0.0) for r in bets], evs)

    clv_price, clv_ev = [], []
    for r in records:
        fp = r.get("first_pick") if isinstance(r.get("first_pick"), dict) else None
        if not fp or not fp.get("odds") or str(r.get("updated_at") or "") <= str(fp.get("logged_at") or ""):
            continue
        idx = 0 if fp.get("pick") == r.get("p1_name") else (1 if fp.get("pick") == r.get("p2_name") else None)
        prices = [r.get("p1_odds"), r.get("p2_odds")]
        if idx is None or None in prices:
            continue
        res = _clv(float(fp["odds"]), prices, idx)
        if res:
            clv_price.append(res["price"])
            clv_ev.append(res["ev_at_close"])

    return {
        "graded": len(graded),
        "pending": sum(1 for r in records if r.get("status") == "PENDING"),
        "match_winner": compare_to_market(np.array(m), np.array(k), np.array(y)) if y else {"n": 0},
        "calibration": reliability_table(m, y) if y else [],
        "bets": {**kelly, "flat": flat},
        "clv": {"price": summarize_clv(clv_price), "ev_at_close": summarize_clv(clv_ev)},
    }


def verdict(comparison: Dict[str, Any], min_n: int = 30) -> str:
    """One-line reading of a ``compare_to_market`` result."""
    n = comparison.get("n", 0)
    if n < min_n:
        return f"not enough priced results yet (n={n})"
    skill = comparison["log_loss_skill"]
    if skill < 0:
        return f"model beat the market by {-skill:.4f} log loss over {n} matches"
    return f"model trails the market by {skill:.4f} log loss over {n} matches (no demonstrated edge)"
