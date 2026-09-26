"""Model evaluation metrics, feature importances, and backtesting performance."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from football_core.config import LEAGUES
from football_core.models.predictor import FootballPredictor


def render_performance_view(predictor: FootballPredictor):
    st.markdown("<h2 style='color:#10b981;'>📈 Model Performance & Validation Analytics</h2>", unsafe_allow_html=True)
    st.caption("Out-of-sample test accuracy and calibration scores for 1X2, Over/Under 2.5 Goals, Corners Over 9.5, and Disciplinary Card lines.")

    league_key = st.selectbox(
        "Select League",
        options=list(LEAGUES.keys()),
        format_func=lambda x: f"{LEAGUES[x]['flag']} {LEAGUES[x]['name']}",
        key="perf_league"
    )

    if not predictor.is_league_ready(league_key):
        st.warning(f"Models for {LEAGUES[league_key]['name']} are not trained yet.")
        return

    bundle = predictor.bundles[league_key]
    metrics = bundle.get("metrics", {})

    # Top KPI Metrics Grid
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("1X2 Accuracy", f"{metrics.get('acc_1x2', 0)*100:.1f}%")
    c2.metric("1X2 Brier", f"{metrics.get('brier_1x2', 0):.4f}")
    c3.metric("O/U 2.5 Goals", f"{metrics.get('acc_over25', 0)*100:.1f}%")
    c4.metric("BTTS Accuracy", f"{metrics.get('acc_btts', 0)*100:.1f}%")
    c5.metric("Corners >9.5", f"{metrics.get('acc_corners_o95', 0.0)*100:.1f}%")
    c6.metric("Cards >3.5", f"{metrics.get('acc_cards_o35', 0.0)*100:.1f}%")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["🌟 Feature Importance", "📊 Statistical Breakdown", "🧪 Backtesting Summary"])

    with tab1:
        st.markdown("#### 🔍 Top Predictive Features (LightGBM)")
        fi_dict = metrics.get("feature_importances", {})
        if fi_dict:
            fi_df = pd.DataFrame({
                "Feature": list(fi_dict.keys()),
                "Importance": list(fi_dict.values())
            }).sort_values(by="Importance", ascending=False).head(20)

            fig_fi = px.bar(
                fi_df,
                x="Importance",
                y="Feature",
                orientation="h",
                color="Importance",
                color_continuous_scale="Viridis",
                title="Top 20 Most Influential Features"
            )
            fig_fi.update_layout(yaxis=dict(autorange="reversed"), height=500)
            st.plotly_chart(fig_fi, use_container_width=True)

    with tab2:
        st.markdown("#### 📐 Model Performance Metrics Table")
        summary_table = pd.DataFrame([
            {"Model": "Match Outcome (1X2)", "Metric": "Multi-class Accuracy", "Value": f"{metrics.get('acc_1x2', 0)*100:.2f}%"},
            {"Model": "Match Outcome (1X2)", "Metric": "Brier Calibration Score", "Value": f"{metrics.get('brier_1x2', 0):.4f}"},
            {"Model": "Total Goals (O/U 2.5)", "Metric": "Accuracy", "Value": f"{metrics.get('acc_over25', 0)*100:.2f}%"},
            {"Model": "Both Teams to Score (BTTS)", "Metric": "Accuracy", "Value": f"{metrics.get('acc_btts', 0)*100:.2f}%"},
            {"Model": "Total Corners (O/U 9.5)", "Metric": "Accuracy", "Value": f"{metrics.get('acc_corners_o95', 0.0)*100:.2f}%"},
            {"Model": "Total Cards (O/U 3.5)", "Metric": "Accuracy", "Value": f"{metrics.get('acc_cards_o35', 0.0)*100:.2f}%"},
            {"Model": "Total Cards (O/U 4.5)", "Metric": "Accuracy", "Value": f"{metrics.get('acc_cards_o45', 0.0)*100:.2f}%"},
        ])
        st.dataframe(summary_table, hide_index=True, use_container_width=True)

    with tab3:
        st.markdown("#### 💰 Out-of-Sample Multi-Market Backtesting Simulation")
        st.info("Insufficient data for backtesting visualization")
