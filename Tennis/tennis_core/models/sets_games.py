"""Analytical Sets Scoring, Set Win Probabilities, and Total Games (Over/Under) Engine for Tennis."""
import math
from typing import Dict, List, Any, Optional
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


def solve_single_set_prob(p_match: float, best_of: int = 3) -> float:
    """
    Invert the match win probability P(Match) to find the underlying single-set win probability s in [0, 1].
    
    For Best-of-3:
        P(Match) = 3s^2 - 2s^3
    For Best-of-5:
        P(Match) = s^3 * (10 - 15s + 6s^2) = 10s^3 - 15s^4 + 6s^5
    """
    p_clamped = max(0.001, min(0.999, float(p_match)))
    
    if abs(p_clamped - 0.5) < 1e-6:
        return 0.5
        
    if best_of == 5:
        def f(s):
            return (10.0 * (s**3) - 15.0 * (s**4) + 6.0 * (s**5)) - p_clamped
    else:
        # Best-of-3
        def f(s):
            return (3.0 * (s**2) - 2.0 * (s**3)) - p_clamped
            
    try:
        s_solution = brentq(f, 0.0, 1.0)
        return float(np.clip(s_solution, 0.001, 0.999))
    except Exception:
        # Fallback linear approximation if solver fails
        return float(np.clip(0.5 + (p_clamped - 0.5) * 0.70, 0.01, 0.99))


def calculate_sets_and_games_probabilities(
    p1_match_prob: float,
    circuit: str = "ATP",
    surface: str = "Hard",
    best_of: int = 3,
    p1_name: str = "Player 1",
    p2_name: str = "Player 2",
    p1_hold_rate: Optional[float] = None,
    p2_hold_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate full set betting distribution, probability for each player to win >= 1 set,
    and dynamic total games over/under probabilities across standard market lines.
    
    Accounts for:
    - Best of 3 vs Best of 5 Grand Slam format.
    - Player serve hold strength and break ability.
    - Set momentum and split-set reaction factors (allowing decider rate to exceed 50% for close matches).
    - Surface pace (Grass > Hard > Clay).
    """
    circuit = circuit.upper()
    surf = surface.capitalize()
    
    # 1. Single Set Win Probabilities
    s1 = solve_single_set_prob(p1_match_prob, best_of=best_of)
    s2 = 1.0 - s1
    
    closeness = 1.0 - abs(s1 - s2)  # 1.0 for 50/50, 0.0 for extreme blowout
    
    # Default hold rates if not provided
    base_hold = 0.79 if circuit == "ATP" else 0.66
    h1 = float(p1_hold_rate) if (p1_hold_rate is not None and 0.40 <= p1_hold_rate <= 0.98) else base_hold
    h2 = float(p2_hold_rate) if (p2_hold_rate is not None and 0.40 <= p2_hold_rate <= 0.98) else base_hold
    avg_hold = (h1 + h2) / 2.0
    
    # Hold adjustment: Higher serve hold rates create longer sets and more tiebreaks (7-6, 7-5)
    hold_effect = (avg_hold - base_hold) * 10.0
    
    # Surface adjustment
    surf_adj = 0.6 if surf == "Grass" else (-0.5 if surf == "Clay" else 0.0)
    circ_adj = 0.0 if circuit == "ATP" else -0.8
    
    # 2. Set Scoreline Probabilities with Split-Set Momentum Factor
    if best_of == 3:
        # In real tennis, close matches have set reaction/fatigue dynamics where the set-1 loser fights back.
        # Momentum factor gamma inflates split set probability (1-1) up to 58-62% for evenly matched players.
        gamma = 1.0 + 0.22 * (closeness ** 1.5)
        
        # Split set probability P(2-1 or 1-2)
        raw_p_split = 2.0 * s1 * s2
        p_split = float(np.clip(raw_p_split * gamma, 0.05, 0.65))
        p_straight = 1.0 - p_split
        
        # Relative strength allocation for straight and split sets
        p_2_0 = p_straight * (s1 / (s1 + s2 * 0.85 if s1 >= s2 else s1 * 0.85 + s2))
        p_0_2 = p_straight - p_2_0
        
        p_2_1 = p_split * s1
        p_1_2 = p_split * s2
        
        score_probs = {
            f"{p1_name} 2-0": round(float(p_2_0), 4),
            f"{p1_name} 2-1": round(float(p_2_1), 4),
            f"{p2_name} 2-1": round(float(p_1_2), 4),
            f"{p2_name} 2-0": round(float(p_0_2), 4),
        }
        
        # Player to win at least 1 set
        p1_win_set = p_2_0 + p_2_1 + p_1_2  # 1.0 - p_0_2
        p2_win_set = p_0_2 + p_1_2 + p_2_1  # 1.0 - p_2_0
        
        # 3rd Set Decider Probability
        p_decider = p_split
        
        # Games per set parameterized by closeness, serve hold, and surface
        games_per_set_2s = 9.3 + 0.7 * closeness + hold_effect + surf_adj + circ_adj
        games_per_set_3s = 9.6 + 1.1 * closeness + hold_effect + surf_adj + circ_adj
        
        mu_2sets = 2.0 * games_per_set_2s
        sigma_2sets = 2.5
        
        mu_3sets = 3.0 * games_per_set_3s
        sigma_3sets = 3.2
        
        exp_games = float((p_2_0 + p_0_2) * mu_2sets + (p_2_1 + p_1_2) * mu_3sets)
        
        # Standard lines for Bo3
        standard_lines = [18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5, 25.5]
        
        def prob_games_over(L):
            p_over_2 = 1.0 - norm.cdf(L, loc=mu_2sets, scale=sigma_2sets)
            p_over_3 = 1.0 - norm.cdf(L, loc=mu_3sets, scale=sigma_3sets)
            return float((p_2_0 + p_0_2) * p_over_2 + (p_2_1 + p_1_2) * p_over_3)

    else:
        # Best of 5 (Men's Grand Slams)
        raw_p_3_0 = s1 ** 3
        raw_p_0_3 = s2 ** 3
        
        p_straight = float(raw_p_3_0 + raw_p_0_3)
        p_extended = 1.0 - p_straight  # Matches with 4 or 5 sets
        
        # Allocate 4-set and 5-set outcomes
        p_3_0 = raw_p_3_0
        p_0_3 = raw_p_0_3
        
        # 4-set matches
        p_3_1 = 3.0 * (s1 ** 3) * s2
        p_1_3 = 3.0 * (s2 ** 3) * s1
        
        # 5-set deciders
        p_3_2 = 6.0 * (s1 ** 3) * (s2 ** 2)
        p_2_3 = 6.0 * (s2 ** 3) * (s1 ** 2)
        
        total_p = p_3_0 + p_3_1 + p_3_2 + p_2_3 + p_1_3 + p_0_3
        p_3_0 /= total_p
        p_3_1 /= total_p
        p_3_2 /= total_p
        p_2_3 /= total_p
        p_1_3 /= total_p
        p_0_3 /= total_p
        
        score_probs = {
            f"{p1_name} 3-0": round(float(p_3_0), 4),
            f"{p1_name} 3-1": round(float(p_3_1), 4),
            f"{p1_name} 3-2": round(float(p_3_2), 4),
            f"{p2_name} 3-2": round(float(p_2_3), 4),
            f"{p2_name} 3-1": round(float(p_1_3), 4),
            f"{p2_name} 3-0": round(float(p_0_3), 4),
        }
        
        p1_win_set = 1.0 - p_0_3
        p2_win_set = 1.0 - p_3_0
        
        # In Bo5, decider refers to 5th set, while extended match is Over 3.5 Sets
        p_decider = p_3_2 + p_2_3
        p_over_3_5_sets = 1.0 - (p_3_0 + p_0_3)
        
        games_per_set = 9.7 + 0.9 * closeness + hold_effect + surf_adj
        
        mu_3sets = 3.0 * (games_per_set - 0.3)
        mu_4sets = 4.0 * games_per_set
        mu_5sets = 5.0 * (games_per_set + 0.2)
        
        p_3s = p_3_0 + p_0_3
        p_4s = p_3_1 + p_1_3
        p_5s = p_3_2 + p_2_3
        
        exp_games = float(p_3s * mu_3sets + p_4s * mu_4sets + p_5s * mu_5sets)
        standard_lines = [33.5, 35.5, 36.5, 37.5, 38.5, 39.5, 40.5, 42.5]
        
        def prob_games_over(L):
            p_o3 = 1.0 - norm.cdf(L, loc=mu_3sets, scale=3.2)
            p_o4 = 1.0 - norm.cdf(L, loc=mu_4sets, scale=3.8)
            p_o5 = 1.0 - norm.cdf(L, loc=mu_5sets, scale=4.2)
            return float(p_3s * p_o3 + p_4s * p_o4 + p_5s * p_o5)

    # Compute line table with probabilities and fair odds
    games_market_lines = []
    main_line = None
    min_diff = 999.0
    
    for line in standard_lines:
        p_over = max(0.01, min(0.99, prob_games_over(line)))
        p_under = 1.0 - p_over
        fair_over = round(1.0 / p_over, 2)
        fair_under = round(1.0 / p_under, 2)
        
        diff = abs(p_over - 0.50)
        if diff < min_diff:
            min_diff = diff
            main_line = {
                "line": line,
                "prob_over": round(p_over * 100, 1),
                "prob_under": round(p_under * 100, 1),
                "fair_odds_over": fair_over,
                "fair_odds_under": fair_under,
            }
            
        games_market_lines.append({
            "Line": f"O/U {line}",
            "P(Over) %": f"{round(p_over * 100, 1)}%",
            "Fair Odds (Over)": fair_over,
            "P(Under) %": f"{round(p_under * 100, 1)}%",
            "Fair Odds (Under)": fair_under,
        })
        
    p1_set_prob_pct = round(p1_win_set * 100.0, 1)
    p2_set_prob_pct = round(p2_win_set * 100.0, 1)
    
    fair_p1_set_odds = round(1.0 / max(0.01, p1_win_set), 2)
    fair_p2_set_odds = round(1.0 / max(0.01, p2_win_set), 2)
    
    p_decider_pct = round(p_decider * 100.0, 1)
    fair_decider_odds = round(1.0 / max(0.01, p_decider), 2)

    return {
        "best_of": best_of,
        "single_set_prob_p1": round(s1, 4),
        "single_set_prob_p2": round(s2, 4),
        "p1_win_at_least_1_set_prob": p1_set_prob_pct,
        "p2_win_at_least_1_set_prob": p2_set_prob_pct,
        "p1_win_at_least_1_set_odds": fair_p1_set_odds,
        "p2_win_at_least_1_set_odds": fair_p2_set_odds,
        "prob_deciding_set": p_decider_pct,
        "fair_odds_deciding_set": fair_decider_odds,
        "scoreline_probabilities": score_probs,
        "expected_total_games": round(exp_games, 1),
        "main_games_line": main_line,
        "games_market_table": games_market_lines,
    }
