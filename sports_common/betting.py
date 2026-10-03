"""Betting arithmetic shared by both sports: vig removal, market blending, EV/Kelly, backtests."""
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Kelly stakes are recorded as currency on this notional bankroll (tennis has always used 1000).
NOTIONAL_BANKROLL = 1000.0

# Against liquid bookmaker prices an apparent edge this large is far more often a model error
# than real value, so such picks are flagged and never recommended.
MAX_CREDIBLE_EV = 0.15

# Weight on the model (vs the vig-free market) when no weight was fitted for a competition.
# Deliberately small: every model here trails the market on holdout log loss.
DEFAULT_MARKET_MODEL_WEIGHT = 0.30


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


def blend_with_market(model_probs: Sequence[float], odds: Sequence[Optional[float]],
                      model_weight: float) -> Tuple[List[float], Optional[List[float]]]:
    """``model_weight * model + (1 - model_weight) * vig-free market``.

    Returns (final probabilities, market probabilities). Without a complete set of real prices
    the model probabilities are returned unchanged and the market part is None.
    """
    market = devig(odds)
    if market is None:
        return [float(p) for p in model_probs], None
    final = model_weight * np.asarray(model_probs, dtype=float) + (1.0 - model_weight) * market
    final = final / final.sum()
    return [float(p) for p in final], [float(p) for p in market]


def expected_value(prob: float, odds: float) -> float:
    """EV per unit staked: prob * odds - 1."""
    return float(prob) * float(odds) - 1.0


def kelly_fraction(prob: float, odds: float, fraction: float = 0.25, cap: float = 0.05) -> float:
    """Fractional Kelly stake as a share of bankroll (0 when there is no edge)."""
    b = float(odds) - 1.0
    if b <= 0 or prob <= 0:
        return 0.0
    full = (b * prob - (1.0 - prob)) / b
    return float(min(fraction * full, cap)) if full > 0 else 0.0


def bet_pnl(stake: float, odds: Optional[float], won: Optional[bool]) -> float:
    """Profit of a settled single at decimal ``odds``: stake*(odds-1) if won, -stake if lost, 0 if no bet."""
    if won is None or not stake or not odds or odds <= 1.0:
        return 0.0
    return round(stake * (odds - 1.0), 2) if won else round(-stake, 2)


def backtest_value_bets(probs: np.ndarray, odds: np.ndarray, outcomes: np.ndarray, min_ev: float,
                        max_odds: Optional[float] = None, min_prob: Optional[float] = None,
                        max_ev: Optional[float] = None) -> Dict[str, Any]:
    """Flat-stake backtest of "bet the best qualifying selection per event".

    ``probs`` and ``odds`` are (n_events, n_selections); ``outcomes`` holds the index of the
    winning selection. A selection qualifies when ``min_ev <= EV (<= max_ev)`` and the optional
    odds/probability bounds hold; the highest-EV qualifying selection is backed with 1 unit.
    """
    probs = np.asarray(probs, dtype=float)
    odds = np.asarray(odds, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    pnl, evs, wins = [], [], 0
    for p_row, o_row, won_idx in zip(probs, odds, outcomes):
        ev = p_row * o_row - 1.0
        ok = np.isfinite(ev) & (o_row > 1.0) & (ev >= min_ev)
        if max_odds is not None:
            ok &= o_row <= max_odds
        if min_prob is not None:
            ok &= p_row >= min_prob
        if max_ev is not None:
            ok &= ev <= max_ev
        if not ok.any():
            continue
        pick = int(np.argmax(np.where(ok, ev, -np.inf)))
        evs.append(float(ev[pick]))
        if pick == won_idx:
            wins += 1
            pnl.append(float(o_row[pick] - 1.0))
        else:
            pnl.append(-1.0)
    n = len(pnl)
    return {
        "events": int(len(outcomes)),
        "bets": n,
        "wins": wins,
        "roi_pct": round(100.0 * sum(pnl) / n, 1) if n else None,
        "claimed_ev_pct": round(100.0 * float(np.mean(evs)), 1) if n else None,
    }
