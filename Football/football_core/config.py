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
        "espn_code": "eng.1",
        "odds_key": "soccer_epl",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "is_cup": False,
        "is_international": False,
    },
    "LaLiga": {
        "name": "La Liga",
        "country": "Spain",
        "code": "SP1",
        "espn_code": "esp.1",
        "odds_key": "soccer_spain_la_liga",
        "flag": "🇪🇸",
        "is_cup": False,
        "is_international": False,
    },
    "SerieA": {
        "name": "Serie A",
        "country": "Italy",
        "code": "I1",
        "espn_code": "ita.1",
        "odds_key": "soccer_italy_serie_a",
        "flag": "🇮🇹",
        "is_cup": False,
        "is_international": False,
    },
    "Bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "code": "D1",
        "espn_code": "ger.1",
        "odds_key": "soccer_germany_bundesliga",
        "flag": "🇩🇪",
        "is_cup": False,
        "is_international": False,
    },
    "Ligue1": {
        "name": "Ligue 1",
        "country": "France",
        "code": "F1",
        "espn_code": "fra.1",
        "odds_key": "soccer_france_ligue_one",
        "flag": "🇫🇷",
        "is_cup": False,
        "is_international": False,
    },

    # 2. National Top Leagues (Belgium, Netherlands, Portugal, Scotland)
    "Belgium": {
        "name": "Jupiler Pro League",
        "country": "Belgium",
        "code": "B1",
        "espn_code": "bel.1",
        "odds_key": "soccer_belgium_first_div",
        "flag": "🇧🇪",
        "is_cup": False,
        "is_international": False,
    },
    "Eredivisie": {
        "name": "Eredivisie",
        "country": "Netherlands",
        "code": "N1",
        "espn_code": "ned.1",
        "odds_key": "soccer_netherlands_eredivisie",
        "flag": "🇳🇱",
        "is_cup": False,
        "is_international": False,
    },
    "PrimeiraLiga": {
        "name": "Primeira Liga",
        "country": "Portugal",
        "code": "P1",
        "espn_code": "por.1",
        "odds_key": "soccer_portugal_primeira_liga",
        "flag": "🇵🇹",
        "is_cup": False,
        "is_international": False,
    },
    "ScottishPrem": {
        "name": "Premiership",
        "country": "Scotland",
        "code": "SC0",
        "espn_code": "sco.1",
        "odds_key": "soccer_spl",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "is_cup": False,
        "is_international": False,
    },

    # 3. European Cups
    "UCL": {
        "name": "UEFA Champions League",
        "country": "Europe",
        "code": "UCL",
        "espn_code": "uefa.champions",
        "odds_key": "soccer_uefa_champs_league",
        "flag": "🏆",
        "is_cup": True,
        "is_international": False,
    },
    "UEL": {
        "name": "UEFA Europa League",
        "country": "Europe",
        "code": "UEL",
        "espn_code": "uefa.europa",
        "odds_key": "soccer_uefa_europa_league",
        "flag": "🥈",
        "is_cup": True,
        "is_international": False,
    },
    "UECL": {
        "name": "UEFA Conference League",
        "country": "Europe",
        "code": "UECL",
        "espn_code": "uefa.europa.conf",
        "odds_key": "soccer_uefa_europa_conference_league",
        "flag": "🥉",
        "is_cup": True,
        "is_international": False,
    },

    # 4. International Competitions (Must-Have)
    "NationsLeague": {
        "name": "UEFA Nations League",
        "country": "Europe",
        "code": "UNL",
        "espn_code": "uefa.nations",
        "odds_key": None,
        "flag": "🇪🇺",
        "is_cup": True,
        "is_international": True,
    },
    "WorldCup": {
        "name": "FIFA World Cup",
        "country": "World",
        "code": "WC",
        "espn_code": "fifa.world",
        "odds_key": None,
        "flag": "🏆",
        "is_cup": True,
        "is_international": True,
    },
    "WCQ_UEFA": {
        "name": "FIFA World Cup Qualifiers - UEFA",
        "country": "Europe",
        "code": "WCQ_UEFA",
        "espn_code": "fifa.worldq.uefa",
        "odds_key": None,
        "flag": "🇪🇺",
        "is_cup": True,
        "is_international": True,
    },
    "WCQ_CONMEBOL": {
        "name": "FIFA World Cup Qualifiers - CONMEBOL",
        "country": "South America",
        "code": "WCQ_CONMEBOL",
        "espn_code": "fifa.worldq.conmebol",
        "odds_key": None,
        "flag": "🌎",
        "is_cup": True,
        "is_international": True,
    },
    "WCQ_CAF": {
        "name": "FIFA World Cup Qualifiers - CAF",
        "country": "Africa",
        "code": "WCQ_CAF",
        "espn_code": "fifa.worldq.caf",
        "odds_key": None,
        "flag": "🌍",
        "is_cup": True,
        "is_international": True,
    },
    "Euro": {
        "name": "UEFA European Championship",
        "country": "Europe",
        "code": "EURO",
        "espn_code": "uefa.euro",
        "odds_key": None,
        "flag": "🇪🇺",
        "is_cup": True,
        "is_international": True,
    },
    "CopaAmerica": {
        "name": "Copa América",
        "country": "South America",
        "code": "COPA",
        "espn_code": "conmebol.america",
        "odds_key": None,
        "flag": "🌎",
        "is_cup": True,
        "is_international": True,
    },
    "AFCON": {
        "name": "Africa Cup of Nations",
        "country": "Africa",
        "code": "AFCON",
        "espn_code": "caf.nations",
        "odds_key": None,
        "flag": "🌍",
        "is_cup": True,
        "is_international": True,
    },

    # 5. International Competitions (Nice-to-Have)
    "Friendlies": {
        "name": "International Friendlies",
        "country": "World",
        "code": "FRIENDLY",
        "espn_code": "fifa.friendly",
        "odds_key": None,
        "flag": "🤝",
        "is_cup": True,
        "is_international": True,
    },
    "GoldCup": {
        "name": "CONCACAF Gold Cup",
        "country": "North America",
        "code": "GOLDCUP",
        "espn_code": "concacaf.gold",
        "odds_key": None,
        "flag": "🏆",
        "is_cup": True,
        "is_international": True,
    },
}

# Historical Seasons (from 2018-2019 to current 2026-2027)
SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"]

# Football Data Base URL (use direct domain without www to prevent Cloudflare 403)
FOOTBALL_DATA_BASE_URL = "https://football-data.co.uk/mmz4281/{season}/{code}.csv"

# Elo Hyperparameters
ELO_BASE = 1500.0
ELO_BASE_RATING = 1500.0
ELO_K = 25.0
ELO_K_FACTOR = 25.0
ELO_HOME_ADVANTAGE = 65.0

# Betting Value Strategy
MIN_VALUE_THRESHOLD = 0.03  # 3.0% Minimum EV to flag value bet
MAX_VALUE_ODDS = 3.20  # Strict cap to prevent the longshot variance trap
MIN_VALUE_PROB = 0.30  # Minimum 30% model probability required for value candidates
DEFAULT_KELLY_FRACTION = 0.25  # Quarter-Kelly staking
MAX_KELLY_STAKE = 0.05  # Maximum 5% bankroll allocation per match
DEFAULT_STARTING_BANKROLL = 1000.0

# Referee Disciplinary Modeling
DEFAULT_LEAGUE_AVG_CARDS = 4.20
DEFAULT_LEAGUE_AVG_FOULS = 24.50
REFEREE_PRIOR_WEIGHT = 5.0
