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

    # 2. Known Top Player fallback dictionary with current and career-high rankings
    top_players = {
        # ATP Top & Active Tour Players
        "jannik sinner": (1.0, 1.0),
        "carlos alcaraz": (2.0, 1.0),
        "alexander zverev": (3.0, 2.0),
        "novak djokovic": (4.0, 1.0),
        "daniil medvedev": (5.0, 1.0),
        "andrey rublev": (6.0, 5.0),
        "taylor fritz": (7.0, 5.0),
        "hubert hurkacz": (8.0, 6.0),
        "casper ruud": (9.0, 2.0),
        "grigor dimitrov": (10.0, 3.0),
        "alex de minaur": (11.0, 6.0),
        "stefanos tsitsipas": (12.0, 3.0),
        "tommy paul": (13.0, 12.0),
        "holger rune": (14.0, 4.0),
        "sebastian korda": (15.0, 15.0),
        "frances tiafoe": (16.0, 10.0),
        "ben shelton": (17.0, 14.0),
        "ugo humbert": (18.0, 13.0),
        "lorenzo musetti": (19.0, 15.0),
        "jack draper": (20.0, 20.0),
        "felix auger-aliassime": (21.0, 6.0),
        "alejandro tabilo": (22.0, 19.0),
        "karen khachanov": (23.0, 8.0),
        "alexei popyrin": (24.0, 23.0),
        "arthur fils": (25.0, 20.0),
        "alexander bublik": (27.0, 17.0),
        "nicolas jarry": (28.0, 16.0),
        "jordan thompson": (29.0, 29.0),
        "francisco cerundolo": (31.0, 19.0),
        "flavio cobolli": (32.0, 30.0),
        "tomas martin etcheverry": (34.0, 27.0),
        "brandon nakashima": (36.0, 36.0),
        "tallon griekspoor": (39.0, 21.0),
        "pedro martinez": (42.0, 40.0),
        "zhizhen zhang": (43.0, 31.0),
        "matteo berrettini": (44.0, 6.0),
        "adrian mannarino": (46.0, 17.0),
        "fabian marozsan": (49.0, 36.0),
        "lorenzo sonego": (53.0, 21.0),
        "yoshihito nishioka": (54.0, 24.0),
        "roberto carballes baena": (55.0, 49.0),
        "roman safiullin": (56.0, 36.0),
        "pavel kotov": (63.0, 50.0),
        "juncheng shang": (67.0, 67.0),
        "shang juncheng": (67.0, 67.0),
        "corentin moutet": (68.0, 51.0),
        "botic van de zandschulp": (68.0, 22.0),
        "christopher o'connell": (75.0, 53.0),
        "rinky hijikata": (77.0, 70.0),
        "thanasi kokkinakis": (78.0, 65.0),
        "fabio fognini": (79.0, 9.0),
        "damir dzumhur": (86.0, 23.0),
        "luca nardi": (87.0, 70.0),
        "taro daniel": (90.0, 64.0),
        "yannick hanfmann": (95.0, 45.0),
        "denis shapovalov": (101.0, 10.0),
        "maximilian marterer": (103.0, 45.0),
        "mattia bellucci": (108.0, 102.0),
        "christopher eubanks": (114.0, 29.0),
        "aslan karatsev": (115.0, 14.0),
        "bu yunchaokete": (124.0, 124.0),
        "zachary svajda": (135.0, 102.0),
        "coleman wong": (141.0, 141.0),
        "yasutaka uchiyama": (160.0, 78.0),
        "kei nishikori": (200.0, 4.0),
        "alibek kachmazov": (252.0, 248.0),
        "federico agustin gomez": (174.0, 160.0),
        "giovanni mpetshi perricard": (51.0, 48.0),
        "sun fajing": (379.0, 360.0),
        "marin cilic": (777.0, 3.0),
        
        # WTA Top & Active Tour Players
        "aryna sabalenka": (1.0, 1.0),
        "iga swiatek": (2.0, 1.0),
        "jessica pegula": (3.0, 3.0),
        "elena rybakina": (4.0, 3.0),
        "jasmine paolini": (5.0, 5.0),
        "coco gauff": (6.0, 2.0),
        "qinwen zheng": (7.0, 7.0),
        "zheng qinwen": (7.0, 7.0),
        "emma navarro": (8.0, 8.0),
        "barbora krejcikova": (9.0, 2.0),
        "maria sakkari": (10.0, 3.0),
        "danielle collins": (11.0, 7.0),
        "daria kasatkina": (13.0, 8.0),
        "anna kalinskaya": (14.0, 14.0),
        "ludmilla samsonova": (15.0, 12.0),
        "diana shnaider": (16.0, 16.0),
        "beatriz haddad maia": (17.0, 10.0),
        "marta kostyuk": (18.0, 16.0),
        "paula badosa": (19.0, 2.0),
        "victoria azarenka": (20.0, 1.0),
        "donna vekic": (21.0, 19.0),
        "mirra andreeva": (22.0, 21.0),
        "madison keys": (24.0, 7.0),
        "leylah fernandez": (26.0, 13.0),
        "linda noskova": (27.0, 25.0),
        "elina svitolina": (28.0, 3.0),
        "caroline garcia": (30.0, 4.0),
        "ekaterina alexandrova": (31.0, 15.0),
        "yulia putintseva": (32.0, 27.0),
        "dayana yastremska": (35.0, 21.0),
        "lulu sun": (40.0, 40.0),
        "veronika kudermetova": (42.0, 9.0),
        "marie bouzkova": (45.0, 24.0),
        "camila osorio": (61.0, 33.0),
        "sloane stephens": (65.0, 3.0),
        "clara tauson": (67.0, 33.0),
        "cristina bucsa": (72.0, 56.0),
        "anna bondar": (91.0, 50.0),
        "kayla day": (121.0, 84.0),
        "sofia kenin": (168.0, 4.0),
        "elvina kalieva": (209.0, 168.0),
    }

    for p_name, r_tuple in top_players.items():
        rankings_map.setdefault(p_name, r_tuple)
        norm_key = strip_accents(normalize_player_name(p_name)).lower().strip()
        rankings_map.setdefault(norm_key, r_tuple)

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

