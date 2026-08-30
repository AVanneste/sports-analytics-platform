"""Official ATP & WTA Player Rankings Registry and Live Rank Resolution."""
import logging
import pickle
from typing import Dict, Tuple, Optional
from pathlib import Path

from tennis_core.config import MODELS_DIR, RAW_DATA_DIR
from tennis_core.utils.helpers import normalize_player_name, strip_accents, match_player_to_database

logger = logging.getLogger(__name__)

# Cached rankings in memory: {player_clean: (current_rank, career_high)}
_RANKINGS_CACHE: Optional[Dict[str, Tuple[float, float]]] = None


def _load_rankings_from_pipelines() -> Dict[str, Tuple[float, float]]:
    """Extract latest rankings and career-high rankings from trained pipelines and raw match data."""
    rankings_map: Dict[str, Tuple[float, float]] = {}

    # 1. Load from saved model pipelines
    for circuit in ["atp", "wta"]:
        pipe_path = MODELS_DIR / f"{circuit}_pipeline.pkl"
        if pipe_path.exists():
            try:
                with open(pipe_path, "rb") as f:
                    pipe = pickle.load(f)
                    
                cur_ranks = getattr(pipe, "current_ranks", {})
                car_highs = getattr(pipe, "career_highs", {})
                
                for p_name, r_val in cur_ranks.items():
                    if r_val and r_val > 0:
                        c_val = car_highs.get(p_name, r_val)
                        norm = strip_accents(normalize_player_name(p_name)).lower().strip()
                        raw_key = strip_accents(p_name).lower().strip()
                        rankings_map[norm] = (float(r_val), float(c_val))
                        rankings_map[raw_key] = (float(r_val), float(c_val))
                        
            except Exception as e:
                logger.debug(f"Could not load rankings from {pipe_path.name}: {e}")

    # 2. Known Top Player fallback dictionary
    top_players = {
        "jannik sinner": (1.0, 1.0),
        "carlos alcaraz": (2.0, 1.0),
        "novak djokovic": (3.0, 1.0),
        "alexander zverev": (4.0, 2.0),
        "daniil medvedev": (5.0, 1.0),
        "andrey rublev": (6.0, 5.0),
        "taylor fritz": (7.0, 5.0),
        "casper ruud": (8.0, 2.0),
        "grigor dimitrov": (9.0, 3.0),
        "alex de minaur": (10.0, 6.0),
        "stefanos tsitsipas": (11.0, 3.0),
        "tommy paul": (12.0, 12.0),
        "holger rune": (13.0, 4.0),
        "sebastian korda": (15.0, 15.0),
        "frances tiafoe": (16.0, 10.0),
        "ben shelton": (17.0, 14.0),
        "arthur fils": (20.0, 20.0),
        "hubert hurkacz": (7.0, 6.0),
        
        # WTA
        "aryna sabalenka": (1.0, 1.0),
        "iga swiatek": (2.0, 1.0),
        "coco gauff": (3.0, 2.0),
        "elena rybakina": (4.0, 3.0),
        "jessica pegula": (5.0, 3.0),
        "jasmine paolini": (6.0, 5.0),
        "qinwen zheng": (7.0, 7.0),
        "zheng qinwen": (7.0, 7.0),
        "emma navarro": (8.0, 8.0),
        "barbora krejcikova": (10.0, 2.0),
        "daria kasatkina": (11.0, 8.0),
        "paula badosa": (12.0, 2.0),
        "danielle collins": (9.0, 7.0),
        "mirra andreeva": (19.0, 19.0),
    }

    for p_name, r_tuple in top_players.items():
        rankings_map.setdefault(p_name, r_tuple)

    return rankings_map


def get_official_player_rank(player_name: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Lookup official current rank and career-high rank for an ATP or WTA player.
    Returns: (current_rank, career_high) or (None, None) if not found.
    """
    global _RANKINGS_CACHE
    if _RANKINGS_CACHE is None:
        _RANKINGS_CACHE = _load_rankings_from_pipelines()

    if not player_name or not isinstance(player_name, str):
        return None, None

    clean_target = strip_accents(player_name).lower().strip()
    norm_target = strip_accents(normalize_player_name(player_name)).lower().strip()

    if clean_target in _RANKINGS_CACHE:
        return _RANKINGS_CACHE[clean_target]
    if norm_target in _RANKINGS_CACHE:
        return _RANKINGS_CACHE[norm_target]

    # Database matching against known keys
    matched = match_player_to_database(player_name, list(_RANKINGS_CACHE.keys()))
    if matched and matched.lower() in _RANKINGS_CACHE:
        return _RANKINGS_CACHE[matched.lower()]

    # Partial substring search
    for key, val in _RANKINGS_CACHE.items():
        if len(key) > 4 and (key in clean_target or clean_target in key):
            return val

    return None, None

