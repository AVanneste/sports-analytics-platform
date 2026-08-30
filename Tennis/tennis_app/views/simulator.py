"""Streamlit view for interactive head-to-head match simulation and what-if analysis."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from typing import Optional
from tennis_core.data.preprocessor import clean_match_data, load_raw_matches
from tennis_core.models.predictor import TennisPredictor
from tennis_core.betting.tracker import PredictionTracker
from tennis_core.utils.helpers import normalize_surface


def render_simulator_view(predictor: TennisPredictor, tracker: Optional[PredictionTracker] = None):
    """Render the Interactive Match Simulator and Custom Scenario Analyzer."""
    st.header("🎮 Match Simulator & Scenario Analyzer")
    st.caption("Simulate custom matchups, compare player demographics & age, analyze serve/return & set/game dynamics, and evaluate live market odds.")

    # Controls Section
    with st.container(border=True):
        col_c1, col_c2, col_c3, col_c4 = st.columns([1, 1, 1.4, 1])
        
        with col_c1:
            circuit = st.selectbox("Circuit", ["ATP", "WTA"], index=0)
        
        with col_c2:
            surface = st.selectbox("Court Surface", ["Hard", "Clay", "Grass"], index=0)
            
        with col_c3:
            format_options = (
                ["Best of 3 Sets (Standard Tour / Masters 1000)", "Best of 5 Sets (Men's Grand Slams: US Open / Wimbledon)"]
                if circuit == "ATP"
                else ["Best of 3 Sets (All WTA Matches)"]
            )
            format_choice = st.selectbox("Match Format (Sets)", format_options, index=0)
            best_of = 5 if "Best of 5" in format_choice else 3
            
        with col_c4:
            bankroll = st.number_input("Active Bankroll ($)", min_value=10.0, max_value=1000000.0, value=1000.0, step=100.0)

        # Player inputs & odds
        col_p1, col_odds, col_p2 = st.columns([3, 2, 3])

        with col_p1:
            st.markdown("#### 👤 Player 1")
            p1_name = st.text_input("Player 1 Name", value="Jannik Sinner" if circuit == "ATP" else "Iga Swiatek")
            p1_odds = st.number_input("P1 Decimal Odds", min_value=1.01, max_value=50.0, value=1.85, step=0.05)

        with col_odds:
            st.write(" ")
            st.write(" ")
            st.markdown("<p style='text-align: center; font-size: 24px; font-weight: bold; color: #94a3b8;'>VS</p>", unsafe_allow_html=True)

        with col_p2:
            st.markdown("#### 👤 Player 2")
            p2_name = st.text_input("Player 2 Name", value="Carlos Alcaraz" if circuit == "ATP" else "Aryna Sabalenka")
            p2_odds = st.number_input("P2 Decimal Odds", min_value=1.01, max_value=50.0, value=2.00, step=0.05)

    if not p1_name or not p2_name:
        st.info("Please enter two player names to run the simulation.")
        return

    # Run Prediction
    pred = predictor.predict_match(
        circuit=circuit,
        p1_name=p1_name,
        p2_name=p2_name,
        surface=surface,
        p1_odds=p1_odds,
        p2_odds=p2_odds,
        best_of=best_of,
        bankroll=bankroll
    )

    betting = pred["betting"]
    ctx = pred["context"]

    # Results Header
    st.subheader(f"🏆 Simulation Result: {pred['predicted_winner']} to Win ({pred['confidence']}%)")

    res_col1, res_col2 = st.columns([1, 1])

    with res_col1:
        # Donut Chart for Win Probabilities
        fig = go.Figure(data=[go.Pie(
            labels=[p1_name, p2_name],
            values=[pred["p1_prob"], pred["p2_prob"]],
            hole=0.55,
            marker_colors=["#3b82f6", "#f59e0b"],
            textinfo="label+percent",
            textfont=dict(size=14, color="white")
        )])
        fig.update_layout(
            title=f"Predicted Win Probability on {surface}",
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20),
            height=320
        )
        st.plotly_chart(fig, use_container_width=True)

    with res_col2:
        st.subheader("💡 Betting & Value Summary")
        if betting["has_value"]:
            st.success(
                f"### 🔥 VALUE FOUND: +{betting['best_ev']}% EV\n\n"
                f"**Recommendation**: Bet on **{betting['recommended_pick']}** @ `{betting['best_odds']}`\n\n"
                f"**Kelly Stake**: ${betting['best_stake']} (Edge: +{betting['best_edge']}%)"
            )
        else:
            st.info("### ⚖️ No Clear Market Edge\n\nMarket odds are aligned with model projections.")

        st.write(f"- **{p1_name}**: Fair Model Odds `{betting['fair_model_odds_p1']}` vs Market `{p1_odds}` (EV: `{betting['ev_p1']}%`)")
        st.write(f"- **{p2_name}**: Fair Model Odds `{betting['fair_model_odds_p2']}` vs Market `{p2_odds}` (EV: `{betting['ev_p2']}%`)")
        st.write(f"- **Bookmaker Vig / Margin**: `{betting['bookmaker_vig_pct']}%`")

    # Sets & Total Games Analytics Section
    sg = pred.get("sets_games", {})
    if sg:
        st.divider()
        st.subheader("🎾 Sets Scoring & Total Games Probability Markets")
        
        sg_col1, sg_col2 = st.columns([1, 1])
        
        with sg_col1:
            st.markdown("##### 🏆 Player Set Scoring Probabilities")
            k1, k2, k3 = st.columns(3)
            with k1:
                st.metric(
                    f"{p1_name} to Win ≥1 Set",
                    f"{sg['p1_win_at_least_1_set_prob']}%",
                    f"Fair: {sg['p1_win_at_least_1_set_odds']}"
                )
            with k2:
                st.metric(
                    f"{p2_name} to Win ≥1 Set",
                    f"{sg['p2_win_at_least_1_set_prob']}%",
                    f"Fair: {sg['p2_win_at_least_1_set_odds']}"
                )
            with k3:
                st.metric(
                    "Deciding Set (Over 2.5 Sets)",
                    f"{sg['prob_deciding_set']}%",
                    f"Fair: {sg['fair_odds_deciding_set']}"
                )
            
            # Scorelines bar chart
            sc_dict = sg.get("scoreline_probabilities", {})
            fig_sc = go.Figure(data=[go.Bar(
                x=list(sc_dict.keys()),
                y=[v * 100 for v in sc_dict.values()],
                marker_color=["#3b82f6", "#60a5fa", "#fbbf24", "#f59e0b"] if len(sc_dict) == 4 else "#3b82f6",
                text=[f"{v*100:.1f}%" for v in sc_dict.values()],
                textposition="auto"
            )])
            fig_sc.update_layout(
                title="Exact Set Scoreline Probability Distribution",
                yaxis_title="Probability (%)",
                margin=dict(t=35, b=20, l=20, r=20),
                height=260
            )
            st.plotly_chart(fig_sc, use_container_width=True)

        with sg_col2:
            st.markdown("##### 🎮 Total Games Over/Under Market Lines")
            st.caption(f"Projected Total Match Games: **{sg['expected_total_games']} games** (Surface: {surface})")
            df_lines = pd.DataFrame(sg.get("games_market_table", []))
            if not df_lines.empty:
                st.dataframe(
                    df_lines[["Line", "P(Over) %", "Fair Odds (Over)", "P(Under) %", "Fair Odds (Under)"]],
                    use_container_width=True,
                    hide_index=True,
                    height=280
                )

    # Metrics comparison table with Age, Sets, Games, Serve/Return
    st.divider()
    st.subheader(f"📊 Detailed Head-to-Head, Serve/Return & Sets/Games Comparison on {surface}")
    
    comp_df = pd.DataFrame({
        "Metric": [
            "Player Age",
            "Current ATP/WTA Rank",
            "Career Best Rank",
            "Overall Elo Rating",
            f"{surface} Elo Rating",
            f"{surface} Effective Elo",
            f"{surface} Serve Hold Rate %",
            f"{surface} Return Break Rate %",
            "Projected Matchup Hold %",
            "Projected Matchup Break %",
            "Sets Won % (Last 10 Matches)",
            "Games Won % (Last 10 Matches)",
            "Game Dominance Ratio (Won/Lost)",
            "Deciding Set Win Rate %",
            "Tiebreak Win Rate %",
            "Recent Match Win % (Last 5)",
            f"{surface} 1-Year Match Win %",
            "Career H2H Matches (Wins)",
            "Career H2H Sets Won",
            "Career H2H Games Won",
        ],
        f"{p1_name}": [
            f"{ctx.get('p1_age', 'N/A')} yrs" if ctx.get('p1_age') != 'N/A' else "N/A",
            f"#{ctx['p1_rank']}" if isinstance(ctx.get('p1_rank'), int) else str(ctx.get('p1_rank', 'N/A')),
            f"#{ctx['p1_career_high']}" if isinstance(ctx.get('p1_career_high'), int) else str(ctx.get('p1_career_high', 'N/A')),
            ctx['p1_elo'],
            ctx['p1_surface_elo'],
            ctx['p1_eff_surface_elo'],
            f"{ctx.get('p1_surface_hold_pct', 'N/A')}%" if ctx.get('p1_surface_hold_pct') != 'N/A' else "N/A",
            f"{ctx.get('p1_surface_break_pct', 'N/A')}%" if ctx.get('p1_surface_break_pct') != 'N/A' else "N/A",
            f"{ctx.get('projected_p1_hold_rate', 'N/A')}%",
            f"{ctx.get('projected_p1_break_rate', 'N/A')}%",
            f"{ctx.get('p1_sets_win_rate', 'N/A')}%" if ctx.get('p1_sets_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p1_games_win_rate', 'N/A')}%" if ctx.get('p1_games_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p1_dominance_ratio', 'N/A')}x" if ctx.get('p1_dominance_ratio') != 'N/A' else "N/A",
            f"{ctx.get('p1_deciding_set_win_rate', 'N/A')}%" if ctx.get('p1_deciding_set_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p1_tiebreak_win_rate', 'N/A')}%" if ctx.get('p1_tiebreak_win_rate') != 'N/A' else "N/A",
            f"{ctx['p1_form_5']}%" if ctx['p1_form_5'] != 'N/A' else "N/A",
            f"{ctx['p1_surface_form']}%" if ctx['p1_surface_form'] != 'N/A' else "N/A",
            f"{ctx['h2h_p1_wins']} / {ctx['h2h_total']}",
            ctx.get('h2h_p1_sets', 0),
            ctx.get('h2h_p1_games', 0),
        ],
        f"{p2_name}": [
            f"{ctx.get('p2_age', 'N/A')} yrs" if ctx.get('p2_age') != 'N/A' else "N/A",
            f"#{ctx['p2_rank']}" if isinstance(ctx.get('p2_rank'), int) else str(ctx.get('p2_rank', 'N/A')),
            f"#{ctx['p2_career_high']}" if isinstance(ctx.get('p2_career_high'), int) else str(ctx.get('p2_career_high', 'N/A')),
            ctx['p2_elo'],
            ctx['p2_surface_elo'],
            ctx['p2_eff_surface_elo'],
            f"{ctx.get('p2_surface_hold_pct', 'N/A')}%" if ctx.get('p2_surface_hold_pct') != 'N/A' else "N/A",
            f"{ctx.get('p2_surface_break_pct', 'N/A')}%" if ctx.get('p2_surface_break_pct') != 'N/A' else "N/A",
            f"{ctx.get('projected_p2_hold_rate', 'N/A')}%",
            f"{ctx.get('projected_p2_break_rate', 'N/A')}%",
            f"{ctx.get('p2_sets_win_rate', 'N/A')}%" if ctx.get('p2_sets_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p2_games_win_rate', 'N/A')}%" if ctx.get('p2_games_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p2_dominance_ratio', 'N/A')}x" if ctx.get('p2_dominance_ratio') != 'N/A' else "N/A",
            f"{ctx.get('p2_deciding_set_win_rate', 'N/A')}%" if ctx.get('p2_deciding_set_win_rate') != 'N/A' else "N/A",
            f"{ctx.get('p2_tiebreak_win_rate', 'N/A')}%" if ctx.get('p2_tiebreak_win_rate') != 'N/A' else "N/A",
            f"{ctx['p2_form_5']}%" if ctx['p2_form_5'] != 'N/A' else "N/A",
            f"{ctx['p2_surface_form']}%" if ctx['p2_surface_form'] != 'N/A' else "N/A",
            f"{ctx['h2h_p2_wins']} / {ctx['h2h_total']}",
            ctx.get('h2h_p2_sets', 0),
            ctx.get('h2h_p2_games', 0),
        ]
    })
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    # Recent Match Logs
    st.divider()
    st.subheader("📅 Recent Match Results & Game/Set Breakdown")
    hist_col1, hist_col2 = st.columns(2)
    with hist_col1:
        st.markdown(f"**Recent Matches for {p1_name}:**")
        p1_hist = ctx.get("p1_recent_matches", [])
        if p1_hist:
            df1 = pd.DataFrame(p1_hist)
            df1["Result"] = df1["won"].apply(lambda w: "✅ Win" if w else "❌ Loss")
            st.dataframe(df1[["date", "Result", "opponent", "score", "sets", "games", "surface", "tourney"]], use_container_width=True, hide_index=True)
        else:
            st.caption("No historical matches found for Player 1.")

    with hist_col2:
        st.markdown(f"**Recent Matches for {p2_name}:**")
        p2_hist = ctx.get("p2_recent_matches", [])
        if p2_hist:
            df2 = pd.DataFrame(p2_hist)
            df2["Result"] = df2["won"].apply(lambda w: "✅ Win" if w else "❌ Loss")
            st.dataframe(df2[["date", "Result", "opponent", "score", "sets", "games", "surface", "tourney"]], use_container_width=True, hide_index=True)
        else:
            st.caption("No historical matches found for Player 2.")
