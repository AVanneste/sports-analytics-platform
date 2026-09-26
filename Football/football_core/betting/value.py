"""Betting value algorithms, vig removal, and staking calculators."""
import numpy as np
from typing import List, Dict, Tuple, Optional

from football_core.config import MIN_VALUE_THRESHOLD, MAX_VALUE_ODDS, MIN_VALUE_PROB, DEFAULT_KELLY_FRACTION, MAX_KELLY_STAKE
from football_core.utils.helpers import calculate_ev, calculate_kelly_stake, remove_vig_multiplicative


def evaluate_betting_market(
    model_prob: float,
    bookmaker_odds: Optional[float],
    min_ev: float = MIN_VALUE_THRESHOLD,
    max_odds: float = MAX_VALUE_ODDS,
    min_prob: float = MIN_VALUE_PROB,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake: float = MAX_KELLY_STAKE,
) -> Dict[str, any]:
    """Evaluate single betting selection for value and recommended stake with realistic odds bounding."""
    if not bookmaker_odds or bookmaker_odds <= 1.0 or model_prob <= 0:
        return {
            "has_value": False,
            "ev": 0.0,
            "kelly_stake": 0.0,
            "fair_odds": round(1.0 / max(1e-4, model_prob), 2),
        }

    ev = calculate_ev(model_prob, bookmaker_odds)
    has_value = bool(ev >= min_ev and bookmaker_odds <= max_odds and model_prob >= min_prob)
    kelly_stake = calculate_kelly_stake(
        model_prob,
        bookmaker_odds,
        fraction=kelly_fraction,
        max_stake=max_stake
    ) if has_value else 0.0

    return {
        "has_value": has_value,
        "ev": float(ev),
        "kelly_stake": float(kelly_stake),
        "fair_odds": round(1.0 / max(1e-4, model_prob), 2),
    }


def calculate_portfolio_kelly(
    value_bets: List[Dict],
    bankroll: float = 1000.0,
    max_portfolio_risk: float = 0.20,
    min_stake_amount: float = 5.0
) -> List[Dict]:
    """
    Scale simultaneous value bets proportionally to their Kelly conviction,
    capping aggregate capital at risk to max_portfolio_risk (default 20%).
    """
    if not value_bets:
        return []

    # Calculate raw Kelly fractions
    raw_stakes = [float(b.get("kelly_stake", 0.0)) for b in value_bets]
    total_raw_risk = sum(raw_stakes)

    scaled_bets = []
    # If total risk exceeds cap, normalize stakes proportionally
    scale_factor = min(1.0, max_portfolio_risk / max(1e-6, total_raw_risk))

    for b, raw_s in zip(value_bets, raw_stakes):
        adjusted_frac = raw_s * scale_factor
        stake_amount = round(adjusted_frac * bankroll, 2)
        bet_copy = dict(b)
        bet_copy["portfolio_stake_pct"] = round(adjusted_frac * 100, 2)
        bet_copy["portfolio_stake_amount"] = stake_amount if stake_amount >= min_stake_amount else 0.0
        scaled_bets.append(bet_copy)

    return scaled_bets


