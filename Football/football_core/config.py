"""Configuration settings, constants, and paths for PitchVision Football Engine."""
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"
MODELS_DIR = PROJECT_ROOT / "models_saved"
TRACKER_FILE = CACHE_DIR / "predictions_tracker.json"
ODDS_API_CACHE_FILE = CACHE_DIR / "odds_api_cache.json"

# Create directories if they don't exist
for d in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, CACHE_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Top European National Leagues & European Cups
LEAGUES = {
    # 1. Top 5 European Leagues
    "EPL": {
        "name": "Premier League",
        "country": "England",
        "code": "E0",
        "odds_key": "soccer_epl",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "is_cup": False,
    },
    "LaLiga": {
        "name": "La Liga",
        "country": "Spain",
        "code": "SP1",
        "odds_key": "soccer_spain_la_liga",
        "flag": "🇪🇸",
        "is_cup": False,
    },
    "SerieA": {
        "name": "Serie A",
        "country": "Italy",
        "code": "I1",
        "odds_key": "soccer_italy_serie_a",
        "flag": "🇮🇹",
        "is_cup": False,
    },
    "Bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "code": "D1",
        "odds_key": "soccer_germany_bundesliga",
        "flag": "🇩🇪",
        "is_cup": False,
    },
    "Ligue1": {
        "name": "Ligue 1",
        "country": "France",
        "code": "F1",
        "odds_key": "soccer_france_ligue_one",
        "flag": "🇫🇷",
        "is_cup": False,
    },

    # 2. National Top Leagues (Belgium, Netherlands, Portugal, Scotland)
    "Belgium": {
        "name": "Jupiler Pro League",
        "country": "Belgium",
        "code": "B1",
        "odds_key": "soccer_belgium_first_div",
        "flag": "🇧🇪",
        "is_cup": False,
    },
    "Eredivisie": {
        "name": "Eredivisie",
        "country": "Netherlands",
        "code": "N1",
        "odds_key": "soccer_netherlands_eredivisie",
        "flag": "🇳🇱",
        "is_cup": False,
    },
    "PrimeiraLiga": {
        "name": "Primeira Liga",
        "country": "Portugal",
        "code": "P1",
        "odds_key": "soccer_portugal_primeira_liga",
        "flag": "🇵🇹",
        "is_cup": False,
    },
    "ScottishPrem": {
        "name": "Premiership",
        "country": "Scotland",
        "code": "SC0",
        "odds_key": "soccer_spl",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "is_cup": False,
    },

    # 3. European Cups
    "UCL": {
        "name": "UEFA Champions League",
        "country": "Europe",
        "code": "UCL",
        "odds_key": "soccer_uefa_champs_league",
        "flag": "🏆",
        "is_cup": True,
    },
    "UEL": {
        "name": "UEFA Europa League",
        "country": "Europe",
        "code": "UEL",
        "odds_key": "soccer_uefa_europa_league",
        "flag": "🥈",
        "is_cup": True,
    },
    "UECL": {
        "name": "UEFA Conference League",
        "country": "Europe",
        "code": "UECL",
        "odds_key": "soccer_uefa_europa_conference_league",
        "flag": "🥉",
        "is_cup": True,
    },
}

# Historical Seasons (from 2018-2019 to current)
SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425"]

# Football Data Base URL
FOOTBALL_DATA_BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"

# Elo Hyperparameters
ELO_BASE = 1500.0
ELO_BASE_RATING = 1500.0
ELO_K = 25.0
ELO_K_FACTOR = 25.0
ELO_HOME_ADVANTAGE = 65.0

# Betting Value Strategy
MIN_VALUE_THRESHOLD = 0.03  # 3.0% Minimum EV to flag value bet
DEFAULT_KELLY_FRACTION = 0.25  # Quarter-Kelly staking
MAX_KELLY_STAKE = 0.05  # Maximum 5% bankroll allocation per match
DEFAULT_STARTING_BANKROLL = 1000.0

# Referee Disciplinary Modeling
DEFAULT_LEAGUE_AVG_CARDS = 4.20
DEFAULT_LEAGUE_AVG_FOULS = 24.50
REFEREE_PRIOR_WEIGHT = 5.0
