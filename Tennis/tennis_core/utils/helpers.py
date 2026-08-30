"""Utility functions for data normalization, string formatting, and mathematical operations."""
import re
import unicodedata
from typing import Dict, Iterable, Optional, Tuple


def strip_accents(text: str) -> str:
    """Remove accents and diacritics from text."""
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")


def normalize_player_name(name: str) -> str:
    """
    Standardize player name format.
    """
    if not isinstance(name, str) or not name.strip():
        return "Unknown"
    
    name = strip_accents(name.strip())
    
    # Handle 'Lastname, Firstname'
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}"
    
    # Remove extra spaces
    name = re.sub(r"\s+", " ", name)
    return name


def match_player_to_database(name: str, known_players: Iterable[str]) -> str:
    """
    Find best matching player name in the historical dataset.
    Handles 'First Last' -> 'Last F.' or exact matches, diacritics, compound surnames, Asian name orders,
    and disambiguates players with identical surnames (e.g. Wang Xinyu -> Wang Xin., Wang Xiyu -> Wang Xiy.).
    """
    if not name or not known_players:
        return name
        
    clean_target = strip_accents(name).lower().strip()
    
    # 1. Exact match (case/accent insensitive)
    for p in known_players:
        if strip_accents(p).lower().strip() == clean_target:
            return p

    # 2. Known full name disambiguation table
    disambig = {
        "xinyu wang": "Wang Xin.",
        "wang xinyu": "Wang Xin.",
        "xiyu wang": "Wang Xiy.",
        "wang xiyu": "Wang Xiy.",
        "yafan wang": "Wang Y.",
        "wang yafan": "Wang Y.",
        "qiang wang": "Wang Q.",
        "wang qiang": "Wang Q.",
        "emiliana arango": "Arango E.",
        "arango emiliana": "Arango E.",
        "wang": "Wang Xin.",  # Default ambiguous 'Wang' in active WTA draw to top tour player
        "arango": "Arango E.",
    }
    if clean_target in disambig and disambig[clean_target] in known_players:
        return disambig[clean_target]

    parts = re.split(r"[\s\-]+", clean_target)
    if len(parts) >= 2:
        pairs = []
        for i in range(1, len(parts)):
            pairs.append((" ".join(parts[i:]), parts[0]))
            pairs.append((" ".join(parts[i:]).replace(" ", "-"), parts[0]))
        pairs.append((parts[-1], " ".join(parts[:-1])))
        pairs.append((parts[0], " ".join(parts[1:])))
        pairs.append((parts[0], parts[-1]))

        matches = []
        for s_cand, g_cand in pairs:
            for k in known_players:
                k_clean = strip_accents(k).lower().strip()
                k_parts = k_clean.rsplit(" ", 1)
                if len(k_parts) == 2:
                    k_surname, k_inits = k_parts[0], k_parts[1].replace(".", "")
                    if s_cand == k_surname or s_cand.replace("-", " ") == k_surname.replace("-", " "):
                        if g_cand.startswith(k_inits) or k_inits.startswith(g_cand[0]):
                            prefix_len = 0
                            for c1, c2 in zip(g_cand, k_inits):
                                if c1 == c2:
                                    prefix_len += 1
                                else:
                                    break
                            matches.append((prefix_len, len(k_inits), k))

        if matches:
            matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return matches[0][2]

    # Single word surname fallback
    if len(parts) == 1:
        s_matches = [k for k in known_players if strip_accents(k).lower().startswith(clean_target + " ")]
        if len(s_matches) == 1:
            return s_matches[0]
        elif len(s_matches) > 1:
            return s_matches[0]

    return name


def normalize_surface(surface: Optional[str]) -> str:
    """Normalize surface string to 'Hard', 'Clay', or 'Grass'."""
    if not surface or not isinstance(surface, str):
        return "Hard"
    s = surface.strip().lower()
    if "clay" in s:
        return "Clay"
    elif "grass" in s:
        return "Grass"
    elif "carpet" in s or "hard" in s or "indoor" in s:
        return "Hard"
    return "Hard"


def odds_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 1.0:
        return 1.0
    return 1.0 / decimal_odds


def prob_to_decimal_odds(probability: float) -> float:
    """Convert probability to fair decimal odds."""
    if probability <= 0.001:
        return 1000.0
    return round(1.0 / probability, 2)


def remove_vig(odds1: float, odds2: float) -> Tuple[float, float]:
    """Calculate true no-vig fair market probabilities from 2-way moneyline odds."""
    if odds1 <= 1.0 or odds2 <= 1.0:
        return 0.5, 0.5
    raw_p1 = 1.0 / odds1
    raw_p2 = 1.0 / odds2
    total = raw_p1 + raw_p2
    if total <= 0:
        return 0.5, 0.5
    return raw_p1 / total, raw_p2 / total


def parse_score_details(score_str: str) -> Dict:
    """
    Comprehensive tennis scoreline parser.
    Extracts games won/lost, sets won/lost, tiebreaks, straight-set indicators, and deciders.
    Example: '6-4 3-6 7-6(5)' ->
      w_sets: 2, l_sets: 1, w_games: 16, l_games: 16,
      tiebreaks_played: 1, w_tiebreaks_won: 1, deciding_set: True, straight_sets: False
    """
    if not isinstance(score_str, str) or not score_str.strip():
        return {
            "w_sets": 2, "l_sets": 0,
            "w_games": 12, "l_games": 8, "total_games": 20,
            "tiebreaks_played": 0, "w_tiebreaks_won": 0,
            "deciding_set": False, "straight_sets": True,
        }

    w_sets = 0
    l_sets = 0
    w_games = 0
    l_games = 0
    tb_played = 0
    w_tb_won = 0

    sets = score_str.strip().split()
    for s in sets:
        # Ignore non-score annotations like RET, W/O, DEF
        if any(tok in s.upper() for tok in ["RET", "W/O", "DEF", "ABN"]):
            continue
        parts = s.split("-")
        if len(parts) == 2:
            try:
                # Remove tiebreak subscores like 7-6(5)
                g1_raw = parts[0].split("(")[0].strip()
                g2_raw = parts[1].split("(")[0].strip()
                g1 = int(g1_raw)
                g2 = int(g2_raw)

                w_games += g1
                l_games += g2

                if g1 > g2:
                    w_sets += 1
                elif g2 > g1:
                    l_sets += 1

                # Check if tiebreak occurred (e.g. 7-6 or 6-7)
                if (g1 == 7 and g2 == 6) or (g1 == 6 and g2 == 7):
                    tb_played += 1
                    if g1 == 7:
                        w_tb_won += 1
            except ValueError:
                continue

    total_sets = w_sets + l_sets
    straight_sets = (l_sets == 0 and w_sets >= 2)
    deciding_set = (total_sets == 3 or total_sets == 5)

    return {
        "w_sets": max(1, w_sets),
        "l_sets": l_sets,
        "w_games": max(6, w_games),
        "l_games": l_games,
        "total_games": w_games + l_games,
        "tiebreaks_played": tb_played,
        "w_tiebreaks_won": w_tb_won,
        "deciding_set": deciding_set,
        "straight_sets": straight_sets,
    }


def detect_match_format(tourney_name: Optional[str], circuit: str = "ATP") -> int:
    """
    Detects whether a tennis match is Best-of-5 sets (Men's Grand Slams) or Best-of-3 sets (Standard Tour/WTA).
    
    Returns:
        5 for ATP Men's Grand Slam main draw matches (US Open, Wimbledon, Roland Garros, Australian Open),
        3 for all WTA matches and standard ATP tour matches (Masters 1000, 500, 250, Challenger, etc.).
    """
    if not tourney_name:
        return 3
    t_lower = str(tourney_name).lower()
    c_upper = str(circuit).upper()
    
    if c_upper == "ATP":
        grand_slams = [
            "us open", "u.s. open", "wimbledon", "roland garros", "french open", 
            "australian open", "aus open", "flushing meadows"
        ]
        if any(gs in t_lower for gs in grand_slams):
            if "qual" in t_lower:
                return 3
            return 5
    return 3

