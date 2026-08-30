"""PitchVision: Football Match Outcome Prediction & Value Betting Engine."""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_core.models.predictor import FootballPredictor
from football_core.betting.tracker import PredictionTracker
from football_core.data.odds_api import fetch_odds_api_quota
from football_core.data.auto_update import check_and_auto_update
from football_app.views.upcoming import render_upcoming_view
from football_app.views.simulator import render_simulator_view
from football_app.views.team_view import render_team_view
from football_app.views.performance import render_performance_view
from football_app.views.tracker_view import render_tracker_view

# Page Config
st.set_page_config(
    page_title="PitchVision | Football Outcome & Value Engine",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Dark Theme Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #10b981;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #94a3b8;
        margin-bottom: 25px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_predictor():
    return FootballPredictor()


def get_tracker():
    return PredictionTracker()


def main():
    # Header Banner
    st.markdown("<div class='main-header'>⚽ PitchVision Analytics Engine</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-header'>Predictive ML, Dixon-Coles Expectancies, Corners & Cards Modeling, and Results Verification across 12 European Competitions</div>", unsafe_allow_html=True)

    # Initialize Engine & Tracker
    with st.spinner("Initializing models and loading league pipelines..."):
        predictor = get_predictor()
        tracker = get_tracker()

    # Sidebar Navigation & Diagnostics
    st.sidebar.image("https://img.icons8.com/isometric/100/stadium.png", width=80)
    st.sidebar.title("PitchVision Navigation")

    view_mode = st.sidebar.radio(
        "Select Dashboard View",
        options=[
            "⚽ Upcoming Fixtures & Value Board",
            "🔮 Match & Props Simulator",
            "📊 Team Analytics & Referees",
            "📈 Model Performance & Validation",
            "🔬 Prediction Tracker & Results",
        ],
        index=0
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📡 Live Feed & Data Status")
    
    # Auto Update Button
    if st.sidebar.button("🔄 Sync Live Match Data", use_container_width=True):
        with st.sidebar.status("Checking for latest league results...", expanded=True) as status:
            res = check_and_auto_update(force=True)
            if isinstance(res, dict):
                count = res.get("total_leagues_updated", 0)
                status.update(label=f"Sync Complete! ({count} leagues refreshed)", state="complete")
            else:
                status.update(label="Sync Complete!", state="complete")

    # The Odds API Quota Status
    quota = fetch_odds_api_quota()
    st.sidebar.caption(f"**The Odds API Quota**: `{quota.get('remaining', '?')}` requests remaining")

    st.sidebar.markdown("---")
    st.sidebar.caption("⚽ **PitchVision 2.0** • 12 Competitions: Top 5, Belgium, Netherlands, Portugal, Scotland, UCL, UEL, UECL")

    # Render Views
    if view_mode == "⚽ Upcoming Fixtures & Value Board":
        render_upcoming_view(predictor, tracker)
    elif view_mode == "🔮 Match & Props Simulator":
        render_simulator_view(predictor)
    elif view_mode == "📊 Team Analytics & Referees":
        render_team_view(predictor)
    elif view_mode == "📈 Model Performance & Validation":
        render_performance_view(predictor)
    elif view_mode == "🔬 Prediction Tracker & Results":
        render_tracker_view(tracker)


if __name__ == "__main__":
    main()
