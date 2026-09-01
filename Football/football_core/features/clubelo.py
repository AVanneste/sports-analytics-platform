"""Authoritative European ClubElo Ratings Engine (clubelo.com benchmark)."""
from typing import Dict, Optional, Any
import logging
from football_core.utils.helpers import normalize_team_name, teams_match, strip_accents

logger = logging.getLogger(__name__)

# Authoritative European ClubElo Ratings Benchmark (clubelo.com)
CLUB_ELO_BENCHMARK: Dict[str, int] = {
    # Premier League (ENG)
    "Man City": 2000,
    "Arsenal": 2011,
    "Liverpool": 1960,
    "Chelsea": 1868,
    "Brighton": 1843,
    "Aston Villa": 1820,
    "Newcastle": 1815,
    "Tottenham": 1810,
    "Man United": 1775,
    "Brentford": 1725,
    "Crystal Palace": 1720,
    "West Ham": 1720,
    "Fulham": 1710,
    "Bournemouth": 1700,
    "Nott'm Forest": 1685,
    "Everton": 1680,
    "Wolves": 1675,
    "Leicester": 1660,
    "Leeds": 1650,
    "Ipswich": 1610,
    "Southampton": 1600,
    "Sunderland": 1590,
    "Burnley": 1630,
    "Sheffield United": 1605,
    "Luton": 1595,

    # La Liga (ESP)
    "Real Madrid": 2045,
    "Barcelona": 1989,
    "Ath Madrid": 1850,
    "Ath Bilbao": 1736,
    "Real Sociedad": 1740,
    "Villarreal": 1735,
    "Betis": 1715,
    "Girona": 1725,
    "Sevilla": 1690,
    "Celta": 1675,
    "Osasuna": 1670,
    "Mallorca": 1660,
    "Valencia": 1665,
    "Getafe": 1655,
    "Alaves": 1640,
    "Rayo Vallecano": 1645,
    "Las Palmas": 1635,
    "Leganes": 1620,
    "Espanyol": 1630,
    "Valladolid": 1610,
    "Deportivo La Coruna": 1590,
    "Deportivo La Coruña": 1590,
    "Malaga": 1585,
    "Málaga": 1585,

    # Serie A (ITA)
    "Inter": 1924,
    "Atalanta": 1855,
    "Juventus": 1835,
    "Milan": 1825,
    "Napoli": 1818,
    "Roma": 1805,
    "Lazio": 1747,
    "Bologna": 1730,
    "Fiorentina": 1725,
    "Torino": 1690,
    "Genoa": 1665,
    "Monza": 1655,
    "Udinese": 1650,
    "Parma": 1640,
    "Cagliari": 1635,
    "Verona": 1630,
    "Como": 1625,
    "Empoli": 1620,
    "Lecce": 1615,
    "Venezia": 1600,

    # Bundesliga (GER)
    "Bayern Munich": 2027,
    "Bayern München": 2027,
    "Dortmund": 1867,
    "Leverkusen": 1843,
    "RB Leipzig": 1818,
    "Stuttgart": 1803,
    "Freiburg": 1761,
    "Hoffenheim": 1732,
    "Frankfurt": 1724,
    "Mainz": 1713,
    "Augsburg": 1690,
    "M'gladbach": 1677,
    "Union Berlin": 1677,
    "Hamburg": 1665,
    "Werder": 1657,
    "Werder Bremen": 1657,
    "Wolfsburg": 1663,
    "Koln": 1647,
    "Heidenheim": 1613,
    "St Pauli": 1587,
    "Bochum": 1583,
    "Holstein Kiel": 1572,
    "Schalke": 1608,
    "FC Schalke 04": 1608,

    # Ligue 1 (FRA)
    "Paris SG": 1905,
    "PSG": 1905,
    "Monaco": 1767,
    "Marseille": 1745,
    "Lille": 1740,
    "Lyon": 1735,
    "Lens": 1720,
    "Nice": 1715,
    "Rennes": 1710,
    "Brest": 1705,
    "Reims": 1670,
    "Strasbourg": 1665,
    "Toulouse": 1655,
    "Montpellier": 1645,
    "Auxerre": 1630,
    "Nantes": 1630,
    "Angers": 1610,
    "St Etienne": 1610,
    "Le Havre": 1605,
    "Paris FC": 1580,
    "Le Mans": 1520,
    "Le Mans FC": 1520,

    # Primeira Liga (POR)
    "Sporting CP": 1840,
    "Benfica": 1823,
    "Porto": 1805,
    "Braga": 1740,
    "Guimaraes": 1670,
    "Vitória SC": 1670,
    "Arouca": 1615,
    "Moreirense": 1610,
    "Famalicão": 1605,
    "Rio Ave": 1595,
    "Gil Vicente": 1590,
    "Estoril": 1585,
    "Farense": 1575,
    "Boavista": 1570,
    "Casa Pia": 1570,
    "Santa Clara": 1565,
    "Nacional": 1550,

    # Eredivisie (NED)
    "PSV": 1767,
    "Feyenoord": 1765,
    "Ajax": 1750,
    "AZ Alkmaar": 1710,
    "Twente": 1700,
    "Utrecht": 1640,
    "Go Ahead Eagles": 1620,
    "NEC Nijmegen": 1615,
    "Heerenveen": 1605,
    "Sparta Rotterdam": 1600,
    "Fortuna Sittard": 1580,
    "Zwolle": 1575,
    "Heracles": 1570,
    "Groningen": 1570,
    "Willem II": 1560,
    "NAC Breda": 1550,
    "Almere City": 1545,
    "Waalwijk": 1530,

    # Belgium Jupiler Pro (BEL)
    "Club Brugge": 1785,
    "Union SG": 1755,
    "Anderlecht": 1730,
    "Genk": 1715,
    "Gent": 1705,
    "Antwerp": 1700,
    "Cercle Brugge": 1650,
    "Mechelen": 1620,
    "Standard Liege": 1610,
    "Charleroi": 1600,
    "Westerlo": 1590,
    "St Truiden": 1580,
    "Leuven": 1570,
    "Kortrijk": 1550,

    # Scottish Premiership (SCO)
    "Celtic": 1668,
    "Rangers": 1655,
    "Hearts": 1550,
    "Aberdeen": 1535,
    "Kilmarnock": 1520,
    "St Mirren": 1515,
    "Dundee": 1505,
    "Hibernian": 1500,
    "Motherwell": 1495,
    "Dundee United": 1490,
    "Ross County": 1475,
    "St Johnstone": 1470,
}


def get_clubelo_rating(team_name: str, fallback_elo: float = 1500.0) -> float:
    """Retrieve official ClubElo benchmark rating for a club."""
    if not team_name:
        return fallback_elo
    norm = normalize_team_name(team_name)
    if norm in CLUB_ELO_BENCHMARK:
        return float(CLUB_ELO_BENCHMARK[norm])
    if team_name in CLUB_ELO_BENCHMARK:
        return float(CLUB_ELO_BENCHMARK[team_name])
    
    # Fuzzy match
    for club_key, rating in CLUB_ELO_BENCHMARK.items():
        if teams_match(team_name, club_key) or teams_match(norm, club_key):
            return float(rating)
            
    return float(fallback_elo)
