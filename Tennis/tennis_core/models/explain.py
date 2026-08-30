"""Matchup explainability and key factor decomposition engine."""
from typing import Dict, List


def explain_matchup_prediction(context: Dict, p1_prob: float, p2_prob: float) -> List[Dict]:
    """
    Generate structured factor cards explaining which components favor Player 1 vs Player 2.
    Includes Serve & Return hold/break differentials, surface Elo, form, and demographics.
    """
    p1 = context.get("p1_name", "Player 1")
    p2 = context.get("p2_name", "Player 2")
    surface = context.get("surface", "Hard")
    
    factors = []

    # 1. Projected Serve Hold & Return Break Matchup Dynamics
    p1_hold = context.get("projected_p1_hold_rate")
    p2_hold = context.get("projected_p2_hold_rate")
    if isinstance(p1_hold, (int, float)) and isinstance(p2_hold, (int, float)):
        hold_gap = p1_hold - p2_hold
        if abs(hold_gap) >= 5.0:
            fav_player = p1 if hold_gap > 0 else p2
            factors.append({
                "title": "Serve Hold & Break Projection",
                "favors": fav_player,
                "impact": "HIGH" if abs(hold_gap) >= 10.0 else "MEDIUM",
                "detail": f"{fav_player} holds a projected service game advantage ({max(p1_hold, p2_hold):.1f}% hold rate vs {min(p1_hold, p2_hold):.1f}% on {surface})."
            })

    # 2. Surface Elo
    p1_s_elo = context.get("p1_surface_elo")
    p2_s_elo = context.get("p2_surface_elo")
    if isinstance(p1_s_elo, (int, float)) and isinstance(p2_s_elo, (int, float)):
        surf_elo_diff = p1_s_elo - p2_s_elo
        if abs(surf_elo_diff) >= 20:
            fav_player = p1 if surf_elo_diff > 0 else p2
            factors.append({
                "title": f"Surface Elo Advantage ({surface})",
                "favors": fav_player,
                "impact": "HIGH" if abs(surf_elo_diff) >= 60 else "MEDIUM",
                "detail": f"{fav_player} holds a {abs(surf_elo_diff):.0f} pt Elo advantage on {surface} ({p1_s_elo} vs {p2_s_elo})."
            })

    # 3. Overall Elo
    p1_elo = context.get("p1_elo")
    p2_elo = context.get("p2_elo")
    if isinstance(p1_elo, (int, float)) and isinstance(p2_elo, (int, float)):
        overall_elo_diff = p1_elo - p2_elo
        if abs(overall_elo_diff) >= 25:
            fav_player = p1 if overall_elo_diff > 0 else p2
            factors.append({
                "title": "Baseline Elo Rating",
                "favors": fav_player,
                "impact": "HIGH" if abs(overall_elo_diff) >= 80 else "MEDIUM",
                "detail": f"{fav_player} leads overall rating by {abs(overall_elo_diff):.0f} Elo pts ({p1_elo} vs {p2_elo})."
            })
    elif isinstance(p1_elo, (int, float)) and not isinstance(p2_elo, (int, float)):
        factors.append({
            "title": "Tour Experience & Rating",
            "favors": p1,
            "impact": "HIGH",
            "detail": f"{p1} has established tour history ({p1_elo} Elo) while {p2} is unrated on the main tour."
        })
    elif isinstance(p2_elo, (int, float)) and not isinstance(p1_elo, (int, float)):
        factors.append({
            "title": "Tour Experience & Rating",
            "favors": p2,
            "impact": "HIGH",
            "detail": f"{p2} has established tour history ({p2_elo} Elo) while {p1} is unrated on the main tour."
        })

    # 4. Games Dominance & Momentum
    p1_dom = context.get("p1_dominance_ratio")
    p2_dom = context.get("p2_dominance_ratio")
    if isinstance(p1_dom, (int, float)) and isinstance(p2_dom, (int, float)):
        dom_diff = p1_dom - p2_dom
        if abs(dom_diff) >= 0.25:
            fav_player = p1 if dom_diff > 0 else p2
            factors.append({
                "title": "Game Dominance Ratio (Won/Lost)",
                "favors": fav_player,
                "impact": "MEDIUM",
                "detail": f"{fav_player} has demonstrated higher game conversion efficiency ({max(p1_dom, p2_dom):.2f}x games won/lost ratio vs {min(p1_dom, p2_dom):.2f}x)."
            })

    # 5. Head-to-Head
    h2h_total = context.get("h2h_total", 0)
    if isinstance(h2h_total, int) and h2h_total > 0:
        p1_h2h = context.get("h2h_p1_wins", 0)
        p2_h2h = context.get("h2h_p2_wins", 0)
        if p1_h2h != p2_h2h:
            h2h_fav = p1 if p1_h2h > p2_h2h else p2
            factors.append({
                "title": "Head-to-Head History",
                "favors": h2h_fav,
                "impact": "MEDIUM" if h2h_total >= 3 else "LOW",
                "detail": f"{h2h_fav} leads the direct matchup {max(p1_h2h, p2_h2h)}-{min(p1_h2h, p2_h2h)} across {h2h_total} previous meetings."
            })

    return factors
