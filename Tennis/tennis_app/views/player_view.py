"""Player Explorer and Surface Elo Profile View."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from tennis_core.models.predictor import TennisPredictor


def render_player_view(predictor: TennisPredictor):
    st.header("👤 Player Explorer & Surface Performance")
    st.caption("Deep-dive into player ratings, surface-specific Elo curves, and career form metrics.")

    circuit = st.selectbox("Tour", ["ATP", "WTA"], key="player_tour")
    pipeline = predictor.pipelines.get(circuit.lower())
    
    if not pipeline:
        st.warning(f"No trained dataset found for {circuit}. Please run the pipeline first.")
        return

    # Leaderboard dataframe
    leaderboard = pipeline.elo_engine.get_leaderboard()
    
    if leaderboard.empty:
        st.info("No player data available.")
        return

    # Player search
    player_names = sorted(leaderboard["player"].tolist())
    selected_player = st.selectbox("Select or Search Player", player_names, index=0)

    player_row = leaderboard[leaderboard["player"] == selected_player].iloc[0]

    # Metrics top cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Overall Elo", player_row["overall_elo"], f"Matches: {player_row['total_matches']}")
    with col2:
        st.metric("Hard Court Elo", player_row["hard_elo"], f"{player_row['hard_matches']} matches")
    with col3:
        st.metric("Clay Court Elo", player_row["clay_elo"], f"{player_row['clay_matches']} matches")
    with col4:
        st.metric("Grass Court Elo", player_row["grass_elo"], f"{player_row['grass_matches']} matches")

    st.divider()

    # Surface Elo Bar Comparison
    chart_col1, chart_col2 = st.columns([1, 1])
    
    with chart_col1:
        st.subheader("🏟️ Surface Elo Breakdown")
        surface_df = pd.DataFrame({
            "Surface": ["Hard", "Clay", "Grass"],
            "Elo Rating": [player_row["hard_elo"], player_row["clay_elo"], player_row["grass_elo"]],
            "Effective Rating": [player_row["hard_effective_elo"], player_row["clay_effective_elo"], player_row["grass_effective_elo"]],
        })
        fig = px.bar(
            surface_df,
            x="Surface",
            y="Elo Rating",
            color="Surface",
            color_discrete_map={"Hard": "#3b82f6", "Clay": "#ea580c", "Grass": "#16a34a"},
            text="Elo Rating",
        )
        fig.update_layout(yaxis_range=[1200, 2400], height=320, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        st.subheader("🏆 Tour Elo Leaderboard")
        surface_sort = st.selectbox("Sort Leaderboard By", ["Overall", "Hard", "Clay", "Grass"])
        sort_col = "overall_elo" if surface_sort == "Overall" else f"{surface_sort.lower()}_effective_elo"
        
        display_leaderboard = leaderboard.sort_values(by=sort_col, ascending=False).head(20).reset_index(drop=True)
        display_leaderboard.index = display_leaderboard.index + 1
        st.dataframe(
            display_leaderboard[["player", "overall_elo", "hard_elo", "clay_elo", "grass_elo", "total_matches"]],
            use_container_width=True
        )

