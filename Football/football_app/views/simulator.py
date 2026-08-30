"""Interactive Football Match Simulator with Score, Corner, Card & Referee Modeling."""
import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import poisson
import plotly.express as px
import plotly.graph_objects as go

from football_core.config import LEAGUES
from football_core.models.predictor import FootballPredictor
from football_core.models.explain import get_match_key_drivers


def render_simulator_view(predictor: FootballPredictor):
    st.markdown("<h2 style='color:#10b981;'>🔮 Custom Match & Props Simulator</h2>", unsafe_allow_html=True)
    st.caption("Simulate 1X2 outcomes, exact scorelines, Corners Over/Under distributions, and Cards & Referee disciplinary tendencies.")

    # 1. Selection Header
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        league_key = st.selectbox(
            "Select Competition",
            options=list(LEAGUES.keys()),
            format_func=lambda x: f"{LEAGUES[x]['flag']} {LEAGUES[x]['name']}"
        )

    if not predictor.is_league_ready(league_key):
        st.warning(f"Models for {LEAGUES[league_key]['name']} are not trained yet.")
        return

    teams = predictor.get_known_teams(league_key)
    referees = ["None / League Average"] + predictor.get_known_referees(league_key)

    if len(teams) < 2:
        st.error("Not enough teams loaded for this league.")
        return

    with col2:
        home_team = st.selectbox("🏠 Home Team", options=teams, index=0)
    with col3:
        away_team = st.selectbox("🚗 Away Team", options=[t for t in teams if t != home_team], index=0)
    with col4:
        selected_ref = st.selectbox("👮 Assigned Referee", options=referees, index=0)
        referee_arg = None if "None" in selected_ref else selected_ref

    # 2. Market Odds Inputs
    st.markdown("##### 💰 Optional: Test Market Odds")
    o1, o2, o3, o4, o5, o6, o7 = st.columns(7)
    with o1:
        odds_h = st.number_input("Home (1)", min_value=1.01, max_value=50.0, value=2.10, step=0.05)
    with o2:
        odds_d = st.number_input("Draw (X)", min_value=1.01, max_value=50.0, value=3.40, step=0.05)
    with o3:
        odds_a = st.number_input("Away (2)", min_value=1.01, max_value=50.0, value=3.50, step=0.05)
    with o4:
        odds_o25 = st.number_input("Over 2.5 G", min_value=1.01, max_value=20.0, value=1.85, step=0.05)
    with o5:
        odds_u25 = st.number_input("Under 2.5 G", min_value=1.01, max_value=20.0, value=1.95, step=0.05)
    with o6:
        odds_corn_o95 = st.number_input("Corners >9.5", min_value=1.01, max_value=20.0, value=1.90, step=0.05)
    with o7:
        odds_card_o35 = st.number_input("Cards >3.5", min_value=1.01, max_value=20.0, value=1.85, step=0.05)

    # Run Prediction
    try:
        pred = predictor.predict_match(
            league_key=league_key,
            home_team=home_team,
            away_team=away_team,
            referee=referee_arg,
            odds_home=odds_h,
            odds_draw=odds_d,
            odds_away=odds_a,
            odds_over25=odds_o25,
            odds_under25=odds_u25,
            odds_corners_over95=odds_corn_o95,
            odds_cards_over35=odds_card_o35,
        )
    except Exception as e:
        st.error(f"Simulation error: {e}")
        return

    st.markdown("---")

    # Matchup Summary Box
    h_elo = pred["home_elo"]
    a_elo = pred["away_elo"]
    h_xg = pred["expected_goals_home"]
    a_xg = pred["expected_goals_away"]
    ref_info = pred["referee"]

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e293b, #0f172a); border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 25px;">
        <div style="display: flex; justify-content: space-around; align-items: center; text-align: center;">
            <div style="width: 35%;">
                <h2 style="color: #38bdf8; margin: 0;">{home_team}</h2>
                <p style="margin: 5px 0; color: #94a3b8;">Elo: <b>{h_elo:.0f}</b> | xG: <b>{h_xg:.2f}</b></p>
                <h3 style="color: #f1f5f9; margin: 0;">{pred['prob_home']*100:.1f}%</h3>
                <span style="font-size: 0.85rem; color: #64748b;">Fair Odds: {pred['fair_odds_home']}</span>
            </div>
            <div style="width: 30%;">
                <div style="background: #334155; padding: 8px 15px; border-radius: 20px; font-weight: bold; color: #fbbf24; display: inline-block;">
                    DRAW {pred['prob_draw']*100:.1f}%
                </div>
                <div style="margin-top: 8px; font-size: 0.85rem; color: #cbd5e1;">Score: <b>{pred['most_likely_score']}</b></div>
                <div style="margin-top: 4px; font-size: 0.8rem; color: #94a3b8;">👮 <b>{ref_info.get('referee_name')}</b> ({ref_info.get('strictness_label')})</div>
            </div>
            <div style="width: 35%;">
                <h2 style="color: #f87171; margin: 0;">{away_team}</h2>
                <p style="margin: 5px 0; color: #94a3b8;">Elo: <b>{a_elo:.0f}</b> | xG: <b>{a_xg:.2f}</b></p>
                <h3 style="color: #f1f5f9; margin: 0;">{pred['prob_away']*100:.1f}%</h3>
                <span style="font-size: 0.85rem; color: #64748b;">Fair Odds: {pred['fair_odds_away']}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "⚽ Match & Goals Heatmap",
        "🚩 Corners Distribution",
        "🟨 Cards & Referee Stats",
        "💰 Value Betting Analysis",
        "🔍 Key Match Drivers"
    ])

    with tab1:
        st.markdown("#### 🎯 Scoreline Probability Matrix")
        matrix = np.array(pred["score_matrix"])[:6, :6]
        matrix_pct = matrix * 100

        fig_heat = px.imshow(
            matrix_pct,
            labels=dict(x=f"{away_team} Goals", y=f"{home_team} Goals", color="Probability (%)"),
            x=[str(i) for i in range(6)],
            y=[str(i) for i in range(6)],
            text_auto=".1f",
            color_continuous_scale="Blues",
            aspect="auto"
        )
        fig_heat.update_layout(height=420, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_heat, use_container_width=True)

        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Over 2.5 Goals", f"{pred['prob_over25']*100:.1f}%")
        g2.metric("Under 2.5 Goals", f"{pred['prob_under25']*100:.1f}%")
        g3.metric("BTTS (Yes)", f"{pred['prob_btts_yes']*100:.1f}%")
        g4.metric("BTTS (No)", f"{pred['prob_btts_no']*100:.1f}%")

    with tab2:
        st.markdown("#### 🚩 Corners Modeling & Probability Lines")
        exp_c = pred["expected_corners"]
        
        c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
        c_kpi1.metric("Expected Total Corners", f"{exp_c:.1f}")
        c_kpi2.metric("Over 9.5 Corners Prob", f"{pred['prob_corners_over95']*100:.1f}%")
        c_kpi3.metric("Under 9.5 Corners Prob", f"{pred['prob_corners_under95']*100:.1f}%")

        # Corner Poisson distribution
        corner_x = list(range(4, 18))
        corner_probs = [poisson.pmf(k, exp_c) * 100 for k in corner_x]
        
        fig_corners = px.bar(
            x=corner_x, y=corner_probs,
            labels={"x": "Exact Total Corners", "y": "Probability (%)"},
            title=f"Corner Count Probability Distribution (λ = {exp_c:.1f})"
        )
        fig_corners.update_layout(height=350)
        st.plotly_chart(fig_corners, use_container_width=True)

        st.markdown("##### 📊 Full Corner Lines Probabilities")
        lines_df = pd.DataFrame([
            {"Line": "Over 8.5 Corners", "Prob": f"{(1 - poisson.cdf(8, exp_c))*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, 1 - poisson.cdf(8, exp_c)), 2)},
            {"Line": "Over 9.5 Corners", "Prob": f"{pred['prob_corners_over95']*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, pred['prob_corners_over95']), 2)},
            {"Line": "Over 10.5 Corners", "Prob": f"{(1 - poisson.cdf(10, exp_c))*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, 1 - poisson.cdf(10, exp_c)), 2)},
            {"Line": "Over 11.5 Corners", "Prob": f"{(1 - poisson.cdf(11, exp_c))*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, 1 - poisson.cdf(11, exp_c)), 2)},
        ])
        st.dataframe(lines_df, hide_index=True, use_container_width=True)

    with tab3:
        st.markdown("#### 🟨 Cards & Referee Disciplinary Tendencies")
        exp_cd = pred["expected_cards"]

        # Referee Summary Card
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Official", ref_info.get("referee_name"))
        r2.metric("Ref Strictness Index", f"{ref_info.get('strictness_index'):.2f}x")
        r3.metric("Ref Career Avg Cards", f"{ref_info.get('avg_cards', 4.2):.1f}")
        r4.metric("Exp. Match Cards", f"{exp_cd:.1f}")

        # Card distribution
        cards_x = list(range(0, 10))
        card_probs = [poisson.pmf(k, exp_cd) * 100 for k in cards_x]
        
        fig_cards = px.bar(
            x=cards_x, y=card_probs,
            labels={"x": "Total Match Cards (Yellows + Reds)", "y": "Probability (%)"},
            title=f"Total Match Cards Distribution (λ = {exp_cd:.1f})",
            color_discrete_sequence=["#f59e0b"]
        )
        fig_cards.update_layout(height=350)
        st.plotly_chart(fig_cards, use_container_width=True)

        st.markdown("##### 📊 Card Market Lines Probabilities")
        card_lines_df = pd.DataFrame([
            {"Line": "Over 2.5 Cards", "Prob": f"{(1 - poisson.cdf(2, exp_cd))*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, 1 - poisson.cdf(2, exp_cd)), 2)},
            {"Line": "Over 3.5 Cards", "Prob": f"{pred['prob_cards_over35']*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, pred['prob_cards_over35']), 2)},
            {"Line": "Over 4.5 Cards", "Prob": f"{pred['prob_cards_over45']*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, pred['prob_cards_over45']), 2)},
            {"Line": "Over 5.5 Cards", "Prob": f"{(1 - poisson.cdf(5, exp_cd))*100:.1f}%", "Fair Odds": round(1.0 / max(0.01, 1 - poisson.cdf(5, exp_cd)), 2)},
        ])
        st.dataframe(card_lines_df, hide_index=True, use_container_width=True)

    with tab4:
        st.markdown("#### 💰 Value Betting & Staking Evaluation Across All Markets")
        insights = pred["betting_insights"]
        if insights:
            insights_df = pd.DataFrame(insights)
            insights_df["Model Prob"] = (insights_df["model_prob"] * 100).round(1).astype(str) + "%"
            insights_df["EV (%)"] = (insights_df["ev"] * 100).round(1).astype(str) + "%"
            insights_df["Kelly Stake (%)"] = (insights_df["kelly"] * 100).round(1).astype(str) + "%"
            st.dataframe(
                insights_df[["market", "selection", "odds", "Model Prob", "fair_odds", "EV (%)", "Kelly Stake (%)"]],
                hide_index=True,
                use_container_width=True
            )
        
        pick = pred["best_pick"]
        if pick and pick.get("ev", 0) > 0:
            st.success(f"🔥 **Recommended Value Selection**: `{pick['selection']}` @ `{pick.get('odds')}` | **EV**: `+{pick.get('ev')*100:.1f}%` | **Kelly Stake**: `{pick.get('kelly')*100:.1f}%`")
        else:
            st.info("No positive Expected Value (EV > 3%) identified for the selected market odds.")

    with tab5:
        st.markdown("#### 📌 Key Match Drivers")
        drivers = get_match_key_drivers(pred)
        for d in drivers:
            icon = "🟢" if d["direction"] == "positive" else ("🔴" if d["direction"] == "negative" else "⚪")
            st.markdown(f"{icon} **{d['factor']}**: {d['detail']}")
