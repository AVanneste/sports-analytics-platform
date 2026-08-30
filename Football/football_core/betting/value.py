"""Betting value algorithms, vig removal, and staking calculators."""
import numpy as np
from typing import List, Dict, Tuple, Optional

from football_core.utils.helpers import calculate_ev, calculate_kelly_stake, remove_vig_multiplicative


def evaluate_betting_market(
    model_prob: float,
    bookmaker_odds: Optional[float],
    min_ev: float = 0.03,
    kelly_fraction: float = 0.25,
    max_stake: float = 0.05,
) -> Dict[str, any]:
    """Evaluate single betting selection for value and recommended stake."""
    if not bookmaker_odds or bookmaker_odds <= 1.0 or model_prob <= 0:
        return {
            "has_value": False,
            "ev": 0.0,
            "kelly_stake": 0.0,
            "fair_odds": round(1.0 / max(1e-4, model_prob), 2),
        }

    ev = calculate_ev(model_prob, bookmaker_odds)
    has_value = bool(ev >= min_ev)
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

