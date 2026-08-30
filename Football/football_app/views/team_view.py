"""Team deep dive, Elo power rankings, and attack/defense quadrant analytics."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from football_core.config import LEAGUES
from football_core.models.predictor import FootballPredictor


def render_team_view(predictor: FootballPredictor):
    st.markdown("<h2 style='color:#10b981;'>📊 Team Analytics & Referee Disciplinary Stats</h2>", unsafe_allow_html=True)
    st.caption("Dynamic team Elo ratings, attacking/defensive efficiencies, team corner averages, disciplinary records, and official referee strictness rankings.")

    league_key = st.selectbox(
        "Select League",
        options=list(LEAGUES.keys()),
        format_func=lambda x: f"{LEAGUES[x]['flag']} {LEAGUES[x]['name']}",
        key="team_view_league"
    )

    if not predictor.is_league_ready(league_key):
        st.warning(f"Data and models for {LEAGUES[league_key]['name']} are not ready yet.")
        return

    bundle = predictor.bundles[league_key]
    pipeline = bundle["pipeline"]
    elo_engine = pipeline.elo_engine
    dc_engine = pipeline.dixon_coles_engine
    form_tracker = pipeline.form_tracker
    ref_engine = pipeline.referee_engine

    teams = sorted(list(elo_engine.ratings.keys()))
    if not teams:
        st.info("No team data found.")
        return

    # Build Team Overview Table
    team_data = []
    for t in teams:
        elo_val = elo_engine.get_rating(t)
        att_val = dc_engine.attack_strengths.get(t, 0.0)
        def_val = dc_engine.defense_strengths.get(t, 0.0)
        form_5 = form_tracker.get_team_rolling_features(t, pd.Timestamp.now(), n_matches=5)

        team_data.append({
            "Team": t,
            "Elo Rating": round(elo_val, 1),
            "Attack (α)": round(att_val, 2),
            "Defense (β)": round(def_val, 2),
            "PPG (L5)": round(form_5["ppg_last5"], 2),
            "GD / Match": round(form_5["gd_per_game_last5"], 2),
            "Corners For / m": round(form_5.get("corners_for_last5", 5.0), 1),
            "Corners Against / m": round(form_5.get("corners_against_last5", 4.8), 1),
            "Cards / Match": round(form_5.get("cards_for_last5", 2.1), 1),
            "Fouls / Match": round(form_5.get("fouls_for_last5", 11.2), 1),
            "Matches": elo_engine.get_match_count(t),
        })

    df_teams = pd.DataFrame(team_data).sort_values(by="Elo Rating", ascending=False).reset_index(drop=True)
    df_teams.index = df_teams.index + 1

    tab1, tab2, tab3, tab4 = st.tabs([
        "🏆 Elo Power Rankings",
        "⚔️ Attack vs Defense Quadrant",
        "🚩 Corners & 🟨 Disciplinary Stats",
        "👮 Referee Strictness Rankings"
    ])

    with tab1:
        st.markdown("#### 🥇 Elo Power Rankings Table")
        st.dataframe(df_teams[["Team", "Elo Rating", "Attack (α)", "Defense (β)", "PPG (L5)", "GD / Match", "Matches"]], use_container_width=True)

        fig_elo = px.bar(
            df_teams.head(15),
            x="Elo Rating",
            y="Team",
            orientation="h",
            color="Elo Rating",
            color_continuous_scale="Viridis",
            title=f"Top 15 Teams by Elo Rating ({LEAGUES[league_key]['name']})"
        )
        fig_elo.update_layout(yaxis=dict(autorange="reversed"), height=450)
        st.plotly_chart(fig_elo, use_container_width=True)

    with tab2:
        st.markdown("#### 🎯 Attack vs Defense Efficiency Quadrant")
        fig_quad = px.scatter(
            df_teams,
            x="Attack (α)",
            y="Defense (β)",
            text="Team",
            color="Elo Rating",
            size="PPG (L5)",
            color_continuous_scale="Turbo",
            title="Offensive Firepower vs Defensive Solidity"
        )
        fig_quad.update_traces(textposition="top center")
        fig_quad.update_layout(
            height=480,
            yaxis=dict(autorange="reversed", title="Defense Weakness (Lower is Better)"),
            xaxis=dict(title="Attack Strength (Higher is Better)")
        )
        fig_quad.add_vline(x=0.0, line_dash="dash", line_color="gray")
        fig_quad.add_hline(y=0.0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_quad, use_container_width=True)

    with tab3:
        st.markdown("#### 🚩 Corners & 🟨 Cards Team Profiles")
        st.dataframe(df_teams[["Team", "Corners For / m", "Corners Against / m", "Cards / Match", "Fouls / Match"]], use_container_width=True)

        c_col1, c_col2 = st.columns(2)
        with c_col1:
            fig_corn = px.bar(
                df_teams.sort_values(by="Corners For / m", ascending=False).head(10),
                x="Corners For / m", y="Team", orientation="h",
                title="Top 10 Teams by Corner Generation",
                color="Corners For / m", color_continuous_scale="Blues"
            )
            fig_corn.update_layout(yaxis=dict(autorange="reversed"), height=350)
            st.plotly_chart(fig_corn, use_container_width=True)

        with c_col2:
            fig_cards = px.bar(
                df_teams.sort_values(by="Cards / Match", ascending=False).head(10),
                x="Cards / Match", y="Team", orientation="h",
                title="Top 10 Most Booked Teams (Cards / Match)",
                color="Cards / Match", color_continuous_scale="Reds"
            )
            fig_cards.update_layout(yaxis=dict(autorange="reversed"), height=350)
            st.plotly_chart(fig_cards, use_container_width=True)

    with tab4:
        st.markdown("#### 👮 Official Referee Strictness Table")
        ref_names = ref_engine.get_all_known_referees()
        if ref_names:
            ref_rows = []
            for r in ref_names:
                prof = ref_engine.get_referee_profile(r)
                ref_rows.append({
                    "Referee": r,
                    "Matches Officiated": prof["matches_officiated"],
                    "Avg Yellows / Match": prof["avg_yellows"],
                    "Avg Reds / Match": prof["avg_reds"],
                    "Avg Total Cards": prof["avg_cards"],
                    "Avg Fouls": prof["avg_fouls"],
                    "Strictness Index": f"{prof['strictness_index']:.2f}x",
                    "Rating": prof["strictness_label"],
                })
            df_refs = pd.DataFrame(ref_rows).sort_values(by="Matches Officiated", ascending=False).reset_index(drop=True)
            df_refs.index = df_refs.index + 1
            st.dataframe(df_refs, use_container_width=True)
        else:
            st.info("Referee match tracking is active for leagues where official names are published (e.g. Premier League).")
