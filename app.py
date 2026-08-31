"""OmniVision Sports AI: Unified Football (PitchVision) & Tennis (CourtVision) Engine."""
import sys
from pathlib import Path

# Add root, Football, and Tennis directories to sys.path
ROOT_DIR = Path(__file__).resolve().parent
FOOTBALL_DIR = ROOT_DIR / "Football"
TENNIS_DIR = ROOT_DIR / "Tennis"

for p in [ROOT_DIR, FOOTBALL_DIR, TENNIS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Unpickling backward compatibility bridge
import compat

import streamlit as st
import pandas as pd

# Football imports
from football_core.models.predictor import FootballPredictor
from football_core.betting.tracker import PredictionTracker as FootballTracker
from football_core.data.odds_api import fetch_odds_api_quota as fetch_football_quota
from football_core.data.api_football import fetch_api_football_status
from football_core.data.auto_update import check_and_auto_update as auto_update_football
from football_app.views.upcoming import render_upcoming_view as render_football_upcoming
from football_app.views.simulator import render_simulator_view as render_football_simulator
from football_app.views.team_view import render_team_view as render_football_team
from football_app.views.performance import render_performance_view as render_football_performance
from football_app.views.tracker_view import render_tracker_view as render_football_tracker

# Tennis imports
from tennis_core.models.predictor import TennisPredictor
from tennis_core.betting.tracker import PredictionTracker as TennisTracker
from tennis_core.data.scraper import fetch_odds_api_quota as fetch_tennis_quota
from tennis_core.data.auto_update import check_and_auto_update as auto_update_tennis, get_update_metadata as get_tennis_metadata
from tennis_app.views.upcoming import render_upcoming_view as render_tennis_upcoming
from tennis_app.views.simulator import render_simulator_view as render_tennis_simulator
from tennis_app.views.tracker_view import render_tracker_view as render_tennis_tracker
from tennis_app.views.player_view import render_player_view as render_tennis_player
from tennis_app.views.performance import render_performance_view as render_tennis_performance

# Page Configuration
st.set_page_config(
    page_title="OmniVision AI | Sports Predictive Engine",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .sport-header {
        font-size: 2.2rem;
        font-weight: 800;
        margin-bottom: 0px;
    }
    .football-title {
        color: #10b981;
    }
    .tennis-title {
        color: #38bdf8;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #94a3b8;
        margin-bottom: 20px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.3rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)


# Resource Caching
@st.cache_resource
def get_football_engine():
    return FootballPredictor()


@st.cache_resource
def get_football_tracker_instance():
    return FootballTracker()


@st.cache_resource
def get_tennis_engine():
    return TennisPredictor()


@st.cache_resource
def get_tennis_tracker_instance():
    return TennisTracker()


@st.cache_data(ttl=60)
def get_cached_tennis_quota():
    return fetch_tennis_quota()


@st.cache_data(ttl=60)
def get_cached_football_quota():
    return fetch_football_quota()


@st.cache_data(ttl=60)
def get_cached_api_football_quota():
    return fetch_api_football_status()


def auto_check_tennis_freshness():
    if "tennis_last_auto_check" not in st.session_state:
        st.session_state["tennis_last_auto_check"] = True
        try:
            auto_update_tennis(force=False)
        except Exception:
            pass


def main():
    # Top-level Sidebar Sport Selector
    st.sidebar.title("🏆 OmniVision AI")
    st.sidebar.caption("Unified Sports Outcome & Value Betting Engine")
    
    selected_sport = st.sidebar.radio(
        "Select Sport Platform",
        options=["⚽ Football (PitchVision)", "🎾 Tennis (CourtVision)"],
        index=0,
        help="Switch between Football (12 European Leagues) and Tennis (ATP & WTA Tours)"
    )
    
    st.sidebar.markdown("---")

    # ==========================================
    # ⚽ FOOTBALL (PitchVision)
    # ==========================================
    if selected_sport == "⚽ Football (PitchVision)":
        st.markdown("<div class='sport-header football-title'>⚽ PitchVision Analytics Engine</div>", unsafe_allow_html=True)
        st.markdown("<div class='sub-header'>Predictive ML, Dixon-Coles Expectancies, Corners & Cards Modeling across 12 European Competitions</div>", unsafe_allow_html=True)

        with st.spinner("Initializing Football Engine..."):
            fb_predictor = get_football_engine()
            fb_tracker = get_football_tracker_instance()

        fb_view = st.sidebar.radio(
            "PitchVision Views",
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

        if st.sidebar.button("🔄 Sync Live Match Data", use_container_width=True, key="fb_sync_btn"):
            with st.sidebar.status("Checking latest league results...", expanded=True) as status:
                res = auto_update_football(force=True)
                get_cached_football_quota.clear()
                count = res.get("total_leagues_updated", 0) if isinstance(res, dict) else 0
                status.update(label=f"Sync Complete! ({count} leagues refreshed)", state="complete")

        quota = get_cached_football_quota()
        api_fb = get_cached_api_football_quota()
        st.sidebar.caption(f"**The Odds API Quota**: `{quota.get('remaining', '?')}` requests remaining")
        st.sidebar.caption(f"**API-Football Quota**: `{api_fb.get('remaining', '?')}/{api_fb.get('requests_limit_day', 100)}` daily requests")

        st.sidebar.markdown("---")
        st.sidebar.caption("⚽ **PitchVision 2.0** • 12 Competitions: Top 5, Belgium, Netherlands, Portugal, Scotland, UCL, UEL, UECL")

        if fb_view == "⚽ Upcoming Fixtures & Value Board":
            render_football_upcoming(fb_predictor, fb_tracker)
        elif fb_view == "🔮 Match & Props Simulator":
            render_football_simulator(fb_predictor)
        elif fb_view == "📊 Team Analytics & Referees":
            render_football_team(fb_predictor)
        elif fb_view == "📈 Model Performance & Validation":
            render_football_performance(fb_predictor)
        elif fb_view == "🔬 Prediction Tracker & Results":
            render_football_tracker(fb_tracker)

    # ==========================================
    # 🎾 TENNIS (CourtVision)
    # ==========================================
    else:
        st.markdown("<div class='sport-header tennis-title'>🎾 CourtVision AI Engine</div>", unsafe_allow_html=True)
        st.markdown("<div class='sub-header'>ATP & WTA Surface-Aware Elo, Serve/Return Modeling, and Quarter-Kelly Value Engine</div>", unsafe_allow_html=True)

        auto_check_tennis_freshness()
        with st.spinner("Initializing Tennis Engine..."):
            tn_predictor = get_tennis_engine()
            tn_tracker = get_tennis_tracker_instance()

        tn_view = st.sidebar.radio(
            "CourtVision Views",
            options=[
                "🎾 Upcoming & Value Bets",
                "⚔️ Match Simulator",
                "📈 Betting Tracker & PnL",
                "👤 Player Explorer",
                "🔬 Model Performance",
            ],
            index=0
        )

        st.sidebar.markdown("---")
        st.sidebar.subheader("📡 Live Odds Feed Status")
        quota = get_cached_tennis_quota()
        if quota.get("ok"):
            q_col1, q_col2 = st.sidebar.columns(2)
            with q_col1:
                st.metric("Quota Left", quota.get("remaining", "?"))
            with q_col2:
                st.metric("Used", quota.get("used", "?"))
            st.sidebar.caption("🟢 **The Odds API Connected**")
        else:
            st.sidebar.caption("ℹ️ **The Odds API (Cached)**")

        meta = get_tennis_metadata()
        with st.sidebar.expander("⏱️ Data Freshness (48h Auto-Sync)", expanded=False):
            st.write(f"📅 **Historical Match Data**: {meta.get('last_historical_update_iso', 'Recent')}")
            st.write(f"🎾 **Live Odds & Fixtures**: {meta.get('last_upcoming_update_iso', 'Recent')}")
            st.caption("Auto-refreshes every 48 hours or when new matches/markets are posted.")

        if st.sidebar.button("🔄 Sync & Auto-Update All Data", use_container_width=True, key="tn_sync_btn"):
            with st.sidebar.status("Checking and updating all datasets (48h sync)..."):
                auto_update_tennis(force=True)
                get_cached_tennis_quota.clear()
                st.sidebar.success("Historical match data, pipelines, and live odds updated!")
                st.rerun()

        st.sidebar.divider()
        st.sidebar.subheader("⚙️ Bankroll Settings")
        bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=100.0, max_value=100000.0, value=1000.0, step=100.0)
        st.session_state["bankroll"] = bankroll
        st.sidebar.caption("💡 Staking Strategy: **Quarter-Kelly (25%)** with 5% maximum safety cap.")

        st.sidebar.markdown("---")
        st.sidebar.caption("🎾 **CourtVision 2.0** • ATP & WTA Surface Predictive ML")

        if tn_view == "🎾 Upcoming & Value Bets":
            render_tennis_upcoming(tn_predictor, tn_tracker)
        elif tn_view == "⚔️ Match Simulator":
            render_tennis_simulator(tn_predictor, tn_tracker)
        elif tn_view == "📈 Betting Tracker & PnL":
            render_tennis_tracker(tn_tracker)
        elif tn_view == "👤 Player Explorer":
            render_tennis_player(tn_predictor)
        elif tn_view == "🔬 Model Performance":
            render_tennis_performance()


if __name__ == "__main__":
    main()

