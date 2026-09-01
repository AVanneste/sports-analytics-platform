"""Helper utilities: team normalization, odds conversion, vig removal, and math tools."""
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

# Team Name Normalization Map (Harmonizes names across football-data, Odds API, and news feeds)
TEAM_NAME_MAP = {
    # Premier League
    "Arsenal FC": "Arsenal",
    "Aston Villa FC": "Aston Villa",
    "Bournemouth": "Bournemouth",
    "AFC Bournemouth": "Bournemouth",
    "Brentford FC": "Brentford",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "Chelsea FC": "Chelsea",
    "Crystal Palace FC": "Crystal Palace",
    "Everton FC": "Everton",
    "Fulham FC": "Fulham",
    "Ipswich Town FC": "Ipswich",
    "Ipswich Town": "Ipswich",
    "Leicester City FC": "Leicester",
    "Leicester City": "Leicester",
    "Liverpool FC": "Liverpool",
    "Manchester City FC": "Man City",
    "Manchester City": "Man City",
    "Manchester United FC": "Man United",
    "Manchester United": "Man United",
    "Newcastle United FC": "Newcastle",
    "Newcastle United": "Newcastle",
    "Nottingham Forest FC": "Nott'm Forest",
    "Nottingham Forest": "Nott'm Forest",
    "Southampton FC": "Southampton",
    "Tottenham Hotspur FC": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United FC": "West Ham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers FC": "Wolves",
    "Wolverhampton Wanderers": "Wolves",
    "Wolverhampton": "Wolves",
    "Leeds United": "Leeds",
    "Burnley FC": "Burnley",
    "Sheffield United": "Sheffield United",
    "Luton Town": "Luton",

    # La Liga
    "Athletic Club": "Ath Bilbao",
    "Athletic Bilbao": "Ath Bilbao",
    "Club Atlético de Madrid": "Ath Madrid",
    "Atletico Madrid": "Ath Madrid",
    "Atlético Madrid": "Ath Madrid",
    "FC Barcelona": "Barcelona",
    "Real Betis Balompié": "Betis",
    "Real Betis": "Betis",
    "RC Celta de Vigo": "Celta",
    "Celta Vigo": "Celta",
    "Celta de Vigo": "Celta",
    "RCD Espanyol": "Espanyol",
    "Getafe CF": "Getafe",
    "Girona FC": "Girona",
    "UD Las Palmas": "Las Palmas",
    "CD Leganés": "Leganes",
    "CD Leganes": "Leganes",
    "RCD Mallorca": "Mallorca",
    "CA Osasuna": "Osasuna",
    "Rayo Vallecano": "Vallecano",
    "Real Madrid CF": "Real Madrid",
    "Real Sociedad": "Sociedad",
    "Sevilla FC": "Sevilla",
    "Valencia CF": "Valencia",
    "Real Valladolid CF": "Valladolid",
    "Real Valladolid": "Valladolid",
    "Villarreal CF": "Villarreal",
    "Deportivo Alavés": "Alaves",
    "Deportivo Alaves": "Alaves",

    # Serie A
    "Atalanta BC": "Atalanta",
    "Bologna FC 1909": "Bologna",
    "Cagliari Calcio": "Cagliari",
    "Como 1907": "Como",
    "Empoli FC": "Empoli",
    "ACF Fiorentina": "Fiorentina",
    "Genoa CFC": "Genoa",
    "FC Internazionale Milano": "Inter",
    "Inter Milan": "Inter",
    "Juventus FC": "Juventus",
    "SS Lazio": "Lazio",
    "US Lecce": "Lecce",
    "AC Milan": "Milan",
    "AC Monza": "Monza",
    "SSC Napoli": "Napoli",
    "Parma Calcio 1913": "Parma",
    "AS Roma": "Roma",
    "Torino FC": "Torino",
    "Udinese Calcio": "Udinese",
    "Venezia FC": "Venezia",
    "Hellas Verona FC": "Verona",
    "Hellas Verona": "Verona",

    # Bundesliga
    "FC Augsburg": "Augsburg",
    "Bayer 04 Leverkusen": "Leverkusen",
    "Bayer Leverkusen": "Leverkusen",
    "FC Bayern München": "Bayern Munich",
    "Bayern Munich": "Bayern Munich",
    "FC Bayern Munich": "Bayern Munich",
    "VfL Bochum 1848": "Bochum",
    "VfL Bochum": "Bochum",
    "SV Werder Bremen": "Werder Bremen",
    "Werder Bremen": "Werder Bremen",
    "Borussia Dortmund": "Dortmund",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "SC Freiburg": "Freiburg",
    "1. FC Heidenheim 1846": "Heidenheim",
    "1. FC Heidenheim": "Heidenheim",
    "TSG 1899 Hoffenheim": "Hoffenheim",
    "TSG Hoffenheim": "Hoffenheim",
    "Holstein Kiel": "Holstein Kiel",
    "RB Leipzig": "RB Leipzig",
    "1. FSV Mainz 05": "Mainz",
    "FSV Mainz": "Mainz",
    "Borussia Mönchengladbach": "M'gladbach",
    "Borussia Monchengladbach": "M'gladbach",
    "FC St. Pauli": "St Pauli",
    "St. Pauli": "St Pauli",
    "VfB Stuttgart": "Stuttgart",
    "1. FC Union Berlin": "Union Berlin",
    "Union Berlin": "Union Berlin",
    "VfL Wolfsburg": "Wolfsburg",

    # Ligue 1
    "Angers SCO": "Angers",
    "AJ Auxerre": "Auxerre",
    "Stade Brestois 29": "Brest",
    "Stade Brestois": "Brest",
    "Le Havre AC": "Le Havre",
    "RC Lens": "Lens",
    "Lille OSC": "Lille",
    "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille",
    "AS Monaco FC": "Monaco",
    "AS Monaco": "Monaco",
    "Montpellier HSC": "Montpellier",
    "FC Nantes": "Nantes",
    "OGC Nice": "Nice",
    "Paris Saint-Germain FC": "Paris SG",
    "Paris Saint Germain": "Paris SG",
    "Paris Saint-Germain": "Paris SG",
    "Stade de Reims": "Reims",
    "Stade Rennais FC 1904": "Rennes",
    "Stade Rennais": "Rennes",
    "AS Saint-Étienne": "St Etienne",
    "Saint-Etienne": "St Etienne",
    "RC Strasbourg Alsace": "Strasbourg",
    "Toulouse FC": "Toulouse",

    # Belgium Jupiler Pro League
    "RSC Anderlecht": "Anderlecht",
    "Royal Antwerp FC": "Antwerp",
    "Royal Antwerp": "Antwerp",
    "KRC Genk": "Genk",
    "KAA Gent": "Gent",
    "Club Brugge KV": "Club Brugge",
    "Cercle Brugge KSV": "Cercle Brugge",
    "Royale Union Saint-Gilloise": "Union SG",
    "Union Saint-Gilloise": "Union SG",
    "Royale Union SG": "Union SG",
    "Standard de Liège": "Standard Liege",
    "Standard Liege": "Standard Liege",
    "KV Mechelen": "Mechelen",
    "KVC Westerlo": "Westerlo",
    "Sint-Truidense VV": "St Truiden",
    "Sint-Truiden": "St Truiden",
    "Sporting Charleroi": "Charleroi",
    "Royal Charleroi SC": "Charleroi",
    "KV Kortrijk": "Kortrijk",
    "KAS Eupen": "Eupen",
    "Oud-Heverlee Leuven": "OH Leuven",
    "OH Leuven": "OH Leuven",
    "FCV Dender EH": "Dender",
    "Beerschot": "Beerschot VA",

    # Netherlands Eredivisie
    "AFC Ajax": "Ajax",
    "PSV Eindhoven": "PSV",
    "PSV": "PSV",
    "Feyenoord Rotterdam": "Feyenoord",
    "AZ": "AZ Alkmaar",
    "FC Twente '65": "Twente",
    "FC Twente": "Twente",
    "FC Utrecht": "Utrecht",
    "SC Heerenveen": "Heerenveen",
    "Sparta Rotterdam": "Sparta Rotterdam",
    "Go Ahead Eagles": "Go Ahead Eagles",
    "FC Groningen": "Groningen",
    "NEC Nijmegen": "NEC Nijmegen",
    "N.E.C. Nijmegen": "NEC Nijmegen",
    "Fortuna Sittard": "Fortuna Sittard",
    "PEC Zwolle": "Zwolle",
    "Heracles Almelo": "Heracles",
    "Willem II Tilburg": "Willem II",
    "Willem II": "Willem II",
    "NAC Breda": "NAC Breda",
    "Almere City FC": "Almere City",
    "RKC Waalwijk": "Waalwijk",

    # Portugal Primeira Liga
    "Sporting Clube de Portugal": "Sporting CP",
    "Sporting CP": "Sporting CP",
    "Sporting Lisbon": "Sporting CP",
    "SL Benfica": "Benfica",
    "FC Porto": "Porto",
    "SC Braga": "Braga",
    "Vitória Sport Clube": "Guimaraes",
    "Vitoria Guimaraes": "Guimaraes",
    "Vitoria de Guimaraes": "Guimaraes",
    "Boavista FC": "Boavista",
    "FC Famalicão": "Famalicao",
    "FC Famalicao": "Famalicao",
    "CD Santa Clara": "Santa Clara",
    "Moreirense FC": "Moreirense",
    "Gil Vicente FC": "Gil Vicente",
    "GD Estoril Praia": "Estoril",
    "Estoril Praia": "Estoril",
    "Rio Ave FC": "Rio Ave",
    "FC Arouca": "Arouca",
    "CD Nacional": "Nacional",
    "AVS Futebol SAD": "AVS",
    "SC Farense": "Farense",
    "Casa Pia AC": "Casa Pia",

    # Scotland Premiership
    "Celtic FC": "Celtic",
    "Rangers FC": "Rangers",
    "Aberdeen FC": "Aberdeen",
    "Heart of Midlothian FC": "Hearts",
    "Heart of Midlothian": "Hearts",
    "Hibernian FC": "Hibernian",
    "Kilmarnock FC": "Kilmarnock",
    "St. Mirren FC": "St Mirren",
    "St Mirren": "St Mirren",
    "Dundee FC": "Dundee",
    "Dundee United FC": "Dundee United",
    "Motherwell FC": "Motherwell",
    "Ross County FC": "Ross County",
    "St. Johnstone FC": "St Johnstone",
    "St Johnstone": "St Johnstone",

    # European Cup Clubs
    "FC Shakhtar Donetsk": "Shakhtar Donetsk",
    "GNK Dinamo Zagreb": "Dinamo Zagreb",
    "FK Crvena zvezda": "Red Star Belgrade",
    "Red Star Belgrade": "Red Star Belgrade",
    "BSC Young Boys": "Young Boys",
    "AC Sparta Praha": "Sparta Prague",
    "SK Slavia Praha": "Slavia Prague",
    "Olympiacos FC": "Olympiacos",
    "PAOK FC": "PAOK",
    "Galatasaray SK": "Galatasaray",
    "Fenerbahçe SK": "Fenerbahce",
    "Fenerbahce SK": "Fenerbahce",
    "Besiktas JK": "Besiktas",
    "FK Bodo/Glimt": "Bodo/Glimt",
    "Bodø/Glimt": "Bodo/Glimt",
    "Malmö FF": "Malmo",
    "FC Salzburg": "Salzburg",
    "Red Bull Salzburg": "Salzburg",
    "SK Sturm Graz": "Sturm Graz",
}


def strip_accents(s: str) -> str:
    """Strip diacritics and convert to lower case."""
    if not s or not isinstance(s, str):
        return ""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()


def teams_match(name1: str, name2: str) -> bool:
    """Robust fuzzy matching for team names across data providers and accent variations."""
    if not name1 or not name2:
        return False
    c1 = strip_accents(name1)
    c2 = strip_accents(name2)
    if c1 == c2:
        return True
    
    # Strip noise terms
    for noise in [" cf", " fc", " rc", " rcd", " sc", " as", " ac", " ud", " sd", " cd", " de la", " de"]:
        c1 = c1.replace(noise, " ")
        c2 = c2.replace(noise, " ")
    c1 = " ".join(c1.split())
    c2 = " ".join(c2.split())

    if c1 == c2:
        return True
    if len(c1) >= 4 and len(c2) >= 4 and (c1 in c2 or c2 in c1):
        return True

    w1 = set(c1.split())
    w2 = set(c2.split())
    if w1 and w2:
        overlap = w1.intersection(w2)
        if any(w not in ["real", "club", "atletico", "sporting", "city", "united", "town", "deportivo"] for w in overlap):
            return True
        if len(overlap) >= 2:
            return True
    return False


def normalize_team_name(name: str) -> str:
    """Normalize team name using mapping table and general cleaning."""
    if not name or not isinstance(name, str):
        return ""
    clean = name.strip()
    return TEAM_NAME_MAP.get(clean, clean)


def remove_vig_multiplicative(odds: Tuple[float, ...]) -> Tuple[float, ...]:
    """Remove bookmaker overround (vig) using multiplicative normalization."""
    implied = [1.0 / o if o > 1.0 else 0.0 for o in odds]
    total_implied = sum(implied)
    if total_implied <= 0:
        return tuple(1.0 / len(odds) for _ in odds)
    return tuple(p / total_implied for p in implied)


def calculate_ev(model_prob: float, bookmaker_odds: float) -> float:
    """Expected Value: EV = (P_model * Odds) - 1."""
    if bookmaker_odds <= 1.0 or model_prob <= 0.0:
        return -1.0
    return (model_prob * bookmaker_odds) - 1.0


def calculate_kelly_stake(
    model_prob: float,
    bookmaker_odds: float,
    fraction: float = 0.25,
    max_stake: float = 0.05
) -> float:
    """Fractional Kelly Criterion: f* = fraction * (b*p - q) / b."""
    if bookmaker_odds <= 1.0 or model_prob <= 0.0:
        return 0.0
    b = bookmaker_odds - 1.0
    p = model_prob
    q = 1.0 - p
    kelly_full = (b * p - q) / b
    if kelly_full <= 0:
        return 0.0
    return min(float(fraction * kelly_full), float(max_stake))
