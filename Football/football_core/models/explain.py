"""Model explainability and key match factors breakdown (including Referee, Corners, and Cards)."""
from typing import Dict, List, Any


def get_match_key_drivers(prediction: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return top qualitative drivers explaining the model prediction."""
    drivers = []
    
    home = prediction["home_team"]
    away = prediction["away_team"]
    h_elo = prediction["home_elo"]
    a_elo = prediction["away_elo"]
    elo_diff = h_elo - a_elo
    h_xg = prediction["expected_goals_home"]
    a_xg = prediction["expected_goals_away"]
    ref_info = prediction.get("referee", {})
    exp_corners = prediction.get("expected_corners", 9.5)
    exp_cards = prediction.get("expected_cards", 4.2)

    # 1. Elo Driver
    if abs(elo_diff) > 100:
        stronger = home if elo_diff > 0 else away
        weaker = away if elo_diff > 0 else home
        drivers.append({
            "factor": "Team Strength & Elo Rating",
            "direction": "positive" if elo_diff > 0 else "negative",
            "detail": f"{stronger} holds a significant rating advantage (+{abs(elo_diff):.0f} Elo) over {weaker}.",
        })
    else:
        drivers.append({
            "factor": "Evenly Matched Elo",
            "direction": "neutral",
            "detail": f"Both teams have comparable overall team ratings ({h_elo:.0f} vs {a_elo:.0f}).",
        })

    # 2. Goal Expectancy & Attack/Defense
    if h_xg > a_xg + 0.6:
        drivers.append({
            "factor": "Attack vs Defense Firepower",
            "direction": "positive",
            "detail": f"Dixon-Coles model projects {home} to generate {h_xg:.2f} xG vs {a_xg:.2f} for {away}.",
        })
    elif a_xg > h_xg + 0.4:
        drivers.append({
            "factor": "Away Offensive Edge",
            "direction": "negative",
            "detail": f"{away} carries superior attacking efficiency ({a_xg:.2f} xG vs {h_xg:.2f} conceded).",
        })

    # 3. Referee & Disciplinary Card Outlook
    ref_name = ref_info.get("referee_name", "Assigned Official")
    strictness_idx = ref_info.get("strictness_index", 1.0)
    label = ref_info.get("strictness_label", "Balanced")

    if strictness_idx >= 1.10:
        drivers.append({
            "factor": f"Referee Impact: {ref_name}",
            "direction": "negative",
            "detail": f"Official {ref_name} is strict ({label}, {ref_info.get('avg_cards', 0):.1f} cards/game). Projected cards: {exp_cards:.1f}.",
        })
    elif strictness_idx <= 0.90:
        drivers.append({
            "factor": f"Referee Impact: {ref_name}",
            "direction": "positive",
            "detail": f"Official {ref_name} is lenient ({label}, {ref_info.get('avg_cards', 0):.1f} cards/game). Projected cards: {exp_cards:.1f}.",
        })

    # 4. Corners Outlook
    if exp_corners >= 11.0:
        drivers.append({
            "factor": "High Corner Activity Profile",
            "direction": "positive",
            "detail": f"High wing volume projects {exp_corners:.1f} total match corners (Over 9.5 prob: {prediction.get('prob_corners_over95',0)*100:.1f}%).",
        })
    elif exp_corners <= 8.5:
        drivers.append({
            "factor": "Low Corner Activity Profile",
            "direction": "neutral",
            "detail": f"Central build-up tendencies project only {exp_corners:.1f} match corners.",
        })

    return drivers
