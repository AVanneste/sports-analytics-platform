"""Betting odds analysis, Vig removal, Expected Value (EV), and Kelly Staking.

STRICT RULE: If no real bookmaker odds are provided, NO betting analysis is performed.
We never fabricate or estimate odds from the model itself.
"""
from typing import Dict, Optional, Tuple
from tennis_core.config import DEFAULT_BANKROLL, KELLY_FRACTION, MIN_VALUE_THRESHOLD, MAX_KELLY_BET_PCT
from tennis_core.utils.helpers import odds_to_implied_prob, remove_vig, prob_to_decimal_odds


def no_odds_result(p1_name: str, p2_name: str) -> Dict:
    """Return a clean 'no odds available' result — never fabricate anything."""
    return {
        "has_odds": False,
        "p1_name": p1_name,
        "p2_name": p2_name,
        "p1_odds": None,
        "p2_odds": None,
        "fair_model_odds_p1": None,
        "fair_model_odds_p2": None,
        "raw_implied_p1": None,
        "raw_implied_p2": None,
        "bookmaker_vig_pct": None,
        "ev_p1": None,
        "ev_p2": None,
        "p1_kelly_pct": None,
        "p2_kelly_pct": None,
        "p1_stake": None,
        "p2_stake": None,
        "has_value": False,
        "recommended_pick": None,
        "best_ev": None,
        "best_edge": None,
        "best_stake": None,
        "best_odds": None,
    }


def analyze_betting_value(
    p1_name: str,
    p2_name: str,
    p1_model_prob: float,
    p2_model_prob: float,
    p1_odds: Optional[float] = None,
    p2_odds: Optional[float] = None,
    bankroll: float = DEFAULT_BANKROLL,
    kelly_fraction: float = KELLY_FRACTION,
) -> Dict:
    """
    Comprehensive betting analysis comparing model probabilities against bookmaker odds.
    Calculates EV, market edge, vig-adjusted fair odds, and suggested Kelly stake.

    Returns no_odds_result() immediately if odds are not provided — no estimation.
    """
    # STRICT: if either odds are missing or invalid, return no-odds result
    p1_valid = p1_odds is not None and p1_odds > 1.0
    p2_valid = p2_odds is not None and p2_odds > 1.0

    if not p1_valid or not p2_valid:
        return no_odds_result(p1_name, p2_name)

    # Implied Probabilities from real bookmaker odds
    raw_implied_p1 = odds_to_implied_prob(p1_odds)
    raw_implied_p2 = odds_to_implied_prob(p2_odds)
    bookmaker_vig = (raw_implied_p1 + raw_implied_p2) - 1.0
    fair_market_p1, fair_market_p2 = remove_vig(p1_odds, p2_odds)

    # Fair model odds (what the model thinks the "true" odds should be)
    fair_model_odds_p1 = prob_to_decimal_odds(p1_model_prob)
    fair_model_odds_p2 = prob_to_decimal_odds(p2_model_prob)

    # Expected Value (EV) = (P_model * Odds) - 1
    ev_p1 = (p1_model_prob * p1_odds) - 1.0
    ev_p2 = (p2_model_prob * p2_odds) - 1.0

    # Kelly Criterion: f* = (b*p - q) / b where b = odds - 1, q = 1 - p
    def calc_kelly_stake(prob: float, odds: float) -> Tuple[float, float]:
        b = odds - 1.0
        if b <= 0:
            return 0.0, 0.0
        q = 1.0 - prob
        full_kelly = (b * prob - q) / b
        if full_kelly <= 0:
            return 0.0, 0.0
        frac_kelly = min(full_kelly * kelly_fraction, MAX_KELLY_BET_PCT)
        stake_amount = round(frac_kelly * bankroll, 2)
        return round(frac_kelly * 100, 2), stake_amount

    p1_kelly_pct, p1_stake = calc_kelly_stake(p1_model_prob, p1_odds)
    p2_kelly_pct, p2_stake = calc_kelly_stake(p2_model_prob, p2_odds)

    # Determine recommended value bet
    recommended_pick = None
    best_ev = 0.0
    best_stake = 0.0
    best_odds = 0.0
    best_edge = 0.0

    if ev_p1 >= MIN_VALUE_THRESHOLD and ev_p1 > ev_p2:
        recommended_pick = p1_name
        best_ev = ev_p1
        best_stake = p1_stake
        best_odds = p1_odds
        best_edge = p1_model_prob - raw_implied_p1
    elif ev_p2 >= MIN_VALUE_THRESHOLD:
        recommended_pick = p2_name
        best_ev = ev_p2
        best_stake = p2_stake
        best_odds = p2_odds
        best_edge = p2_model_prob - raw_implied_p2

    return {
        "has_odds": True,
        "p1_name": p1_name,
        "p2_name": p2_name,
        "p1_odds": round(p1_odds, 2),
        "p2_odds": round(p2_odds, 2),
        "fair_model_odds_p1": fair_model_odds_p1,
        "fair_model_odds_p2": fair_model_odds_p2,
        "raw_implied_p1": round(raw_implied_p1 * 100, 1),
        "raw_implied_p2": round(raw_implied_p2 * 100, 1),
        "bookmaker_vig_pct": round(bookmaker_vig * 100, 1),
        "ev_p1": round(ev_p1 * 100, 1),
        "ev_p2": round(ev_p2 * 100, 1),
        "p1_kelly_pct": p1_kelly_pct,
        "p2_kelly_pct": p2_kelly_pct,
        "p1_stake": p1_stake,
        "p2_stake": p2_stake,
        "has_value": (ev_p1 >= MIN_VALUE_THRESHOLD or ev_p2 >= MIN_VALUE_THRESHOLD),
        "recommended_pick": recommended_pick,
        "best_ev": round(best_ev * 100, 1),
        "best_edge": round(best_edge * 100, 1),
        "best_stake": best_stake,
        "best_odds": best_odds,
    }
