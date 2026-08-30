"""Configuration settings and constants for the Tennis Outcome Prediction System."""
import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
UPCOMING_DATA_DIR = DATA_DIR / "upcoming"
TRACKER_DATA_DIR = DATA_DIR / "tracker"
MODELS_DIR = PROJECT_ROOT / "models_saved"

# Create directories if they don't exist
for directory in [RAW_DATA_DIR, PROCESSED_DATA_DIR, UPCOMING_DATA_DIR, TRACKER_DATA_DIR, MODELS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Historical Data Range (Past 3 Years: 2023-2026)
START_YEAR = 2023
END_YEAR = 2026  # Up through current season 2026
CIRCUITS = ["atp", "wta"]

# Elo Configuration
INITIAL_ELO = 1500.0
BASE_K = 32.0
SURFACE_K = 32.0
# Tournament Level Multipliers for Elo
LEVEL_K_MULTIPLIERS = {
    "G": 1.25,   # Grand Slams (Best of 5 for Men, 2000 pts)
    "M": 1.10,   # Masters 1000 / WTA 1000
    "A": 1.00,   # ATP 500/250, WTA 500/250
    "C": 0.80,   # Challengers
    "F": 1.15,   # Tour Finals
    "D": 0.90,   # Davis Cup / BJK Cup
}

# Supported Surfaces
PRIMARY_SURFACES = ["Hard", "Clay", "Grass"]
SURFACE_MAP = {
    "hard": "Hard",
    "clay": "Clay",
    "grass": "Grass",
    "carpet": "Hard",  # Group indoor carpet with fast hard courts
    "i.hard": "Hard",
    "indoors": "Hard",
}

# Form Calculation Parameters
FORM_SHORT_WINDOW = 5
FORM_MEDIUM_WINDOW = 10
FORM_LONG_WINDOW = 20
SURFACE_FORM_DAYS = 365  # Rolling 1 year on surface

# Betting Value Parameters
DEFAULT_BANKROLL = 1000.00
DEFAULT_FLAT_BET_SIZE = 20.00
KELLY_FRACTION = 0.25     # Quarter-Kelly for risk-managed bankroll sizing
MIN_VALUE_THRESHOLD = 0.03  # Minimum 3% EV to flag as a value opportunity
MAX_KELLY_BET_PCT = 0.05   # Cap single bet at 5% of bankroll

# Model Files
ATP_MODEL_PATH = MODELS_DIR / "atp_model.pkl"
WTA_MODEL_PATH = MODELS_DIR / "wta_model.pkl"
ATP_SCALER_PATH = MODELS_DIR / "atp_scaler.pkl"
WTA_SCALER_PATH = MODELS_DIR / "wta_scaler.pkl"
METRICS_PATH = PROCESSED_DATA_DIR / "model_metrics.json"

# Tracker Files
PREDICTIONS_ARCHIVE_PATH = TRACKER_DATA_DIR / "predictions_archive.json"
GRADED_RESULTS_PATH = TRACKER_DATA_DIR / "graded_results.json"
PNL_HISTORY_PATH = TRACKER_DATA_DIR / "pnl_history.json"

