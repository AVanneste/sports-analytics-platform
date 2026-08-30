"""CourtVision: Tennis Match Outcome Prediction & Value Engine."""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tennis_core.models.predictor import TennisPredictor
from tennis_core.betting.tracker import PredictionTracker
from tennis_core.data.scraper import fetch_live_upcoming_fixtures, fetch_odds_api_quota
from tennis_core.data.auto_update import check_and_auto_update, get_update_metadata
from tennis_app.views.upcoming import render_upcoming_view
from tennis_app.views.simulator import render_simulator_view
from tennis_app.views.tracker_view import render_tracker_view
from tennis_app.views.player_view import render_player_view
from tennis_app.views.performance import render_performance_view

# Page Config
st.set_page_config(
    page_title="CourtVision | Tennis Outcome & Value Engine",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
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
    return TennisPredictor()


@st.cache_resource
def get_tracker():
    return PredictionTracker()


@st.cache_data(ttl=60)
def get_cached_quota():
    """Fetch and cache Odds API quota for 60 seconds to avoid wasting quota on UI reruns."""
    return fetch_odds_api_quota()


def auto_check_data_freshness():
    """Check if data is older than 48h and automatically update if needed."""
    if "last_auto_check" not in st.session_state:
        st.session_state["last_auto_check"] = True
        try:
            check_and_auto_update(force=False)
        except Exception:
            pass


def main():
    auto_check_data_freshness()
    predictor = get_predictor()
    tracker = get_tracker()

    # Sidebar
    st.sidebar.image("https://images.unsplash.com/photo-1595435934249-5df7ed86e1c0?w=600&auto=format&fit=crop&q=80", width="stretch")
    st.sidebar.title("🎾 CourtVision AI")
    st.sidebar.caption("ATP & WTA Surface-Aware Prediction System")

    # API Connection & Quota Widget (Always Visible)
    st.sidebar.subheader("📡 Live Odds Feed Status")
    quota = get_cached_quota()
    if quota.get("ok"):
        q_col1, q_col2 = st.sidebar.columns(2)
        with q_col1:
            st.metric("API Quota Left", quota.get("remaining", "?"))
        with q_col2:
            st.metric("Used", quota.get("used", "?"))
        st.sidebar.caption("🟢 **The Odds API Connected**")
    else:
        st.sidebar.caption("ℹ️ **The Odds API (Cached)**")

    # 48-Hour Auto-Update Status
    meta = get_update_metadata()
    with st.sidebar.expander("⏱️ Data Freshness (48h Auto-Sync)", expanded=False):
        st.write(f"📅 **Historical Match Data**: {meta.get('last_historical_update_iso', 'Recent')}")
        st.write(f"🎾 **Live Odds & Fixtures**: {meta.get('last_upcoming_update_iso', 'Recent')}")
        st.caption("Auto-refreshes every 48 hours or when new matches/markets are posted.")

    if st.sidebar.button("🔄 Sync & Auto-Update All Data", width="stretch"):
        with st.sidebar.status("Checking and updating all datasets (48h sync)..."):
            res = check_and_auto_update(force=True)
            get_cached_quota.clear()
            st.sidebar.success("All historical match data, pipelines, and live odds updated!")
            st.rerun()


    st.sidebar.divider()

    # Navigation
    nav = st.sidebar.radio(
        "Navigation",
        [
            "🎾 Upcoming & Value Bets",
            "⚔️ Match Simulator",
            "📈 Betting Tracker & PnL",
            "👤 Player Explorer",
            "🔬 Model Performance",
        ]
    )

    st.sidebar.divider()
    st.sidebar.subheader("⚙️ Bankroll Settings")
    bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=100.0, max_value=100000.0, value=1000.0, step=100.0)
    st.session_state["bankroll"] = bankroll
    
    st.sidebar.caption("💡 Staking Strategy: **Quarter-Kelly (25%)** with 5% maximum safety cap per match.")

    # Render selected view
    if nav == "🎾 Upcoming & Value Bets":
        render_upcoming_view(predictor, tracker)
    elif nav == "⚔️ Match Simulator":
        render_simulator_view(predictor, tracker)
    elif nav == "📈 Betting Tracker & PnL":
        render_tracker_view(tracker)
    elif nav == "👤 Player Explorer":
        render_player_view(predictor)
    elif nav == "🔬 Model Performance":
        render_performance_view()


if __name__ == "__main__":
    main()
