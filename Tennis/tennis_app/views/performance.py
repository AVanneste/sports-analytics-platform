"""Model Evaluation, Feature Interpretability, Reliability Calibration, and Surface Diagnostics for CourtVision."""
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from tennis_core.config import METRICS_PATH


def render_performance_view():
    st.markdown("<h2 style='color:#3b82f6;'>🔬 Model Diagnostics & Backtesting Benchmarks</h2>", unsafe_allow_html=True)
    st.caption("Deep-dive into LightGBM feature contributions, out-of-fold cross-validation metrics, probability calibration curves, and surface performance splits.")

    if not METRICS_PATH.exists():
        st.warning("Model metrics not found. Train models via pipeline first.")
        return

    with open(METRICS_PATH, "r") as f:
        metrics = json.load(f)

    circuits = list(metrics.keys())
    selected_circuit = st.selectbox("Select Circuit Metrics", [c.upper() for c in circuits])
    m_data = metrics.get(selected_circuit.lower())

    if not m_data:
        st.info(f"No metrics available for {selected_circuit}")
        return

    # Top Benchmark KPI Cards
    st.markdown("### 🏆 Out-of-Sample Validation Benchmarks")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Out-of-Fold Accuracy", f"{m_data.get('accuracy')}%", help="Correct winner classification rate across 5-fold cross-validation")
    with col2:
        st.metric("ROC-AUC Score", m_data.get("roc_auc"), help="Discriminative ability between winners and losers (>0.70 is strong)")
    with col3:
        st.metric("Brier Calibration Score", m_data.get("brier_score"), help="Probabilistic precision. Lower is better (<0.20 is well calibrated)")
    with col4:
        st.metric("Log Loss", m_data.get("log_loss"), help="Cross-entropy penalty for probabilistic confidence")

    st.markdown("---")

    tab_feat, tab_calib, tab_surf, tab_model_info = st.tabs([
        "🌲 Feature Importances & Drivers",
        "🎯 Reliability & Probability Calibration",
        "🌱 Surface Specialization & Pace",
        "⚙️ Model Architecture & Data Splits"
    ])

    # TAB 1: FEATURE IMPORTANCE
    with tab_feat:
        st.markdown("#### 🌲 LightGBM Feature Importance Breakdown")
        st.caption("Quantifies the mathematical information gain and split frequency of each engineered feature in the machine learning ensemble.")
        
        importances = m_data.get("feature_importances", {})
        if importances:
            label_map = {
                "effective_surface_elo_diff": "Surface-Blended Elo Gap",
                "surface_elo_diff": "Surface Elo Gap",
                "elo_diff": "Overall Elo Gap",
                "projected_hold_diff": "Projected Service Hold Gap",
                "projected_break_diff": "Projected Return Break Gap",
                "serve_hold_diff": "Historical Surface Hold Gap",
                "return_break_diff": "Historical Return Break Gap",
                "rank_diff": "Rank Differential",
                "log_rank_ratio": "Log Rank Ratio",
                "career_high_rank_diff": "Career High Rank Gap",
                "form_5_diff": "Recent Form (5 Matches) Gap",
                "form_10_diff": "Form (10 Matches) Gap",
                "form_20_diff": "Form (20 Matches) Gap",
                "surface_form_diff": "1-Year Surface Win Rate Gap",
                "sets_ratio_diff": "Sets Won Ratio Gap",
                "games_ratio_diff": "Games Won Ratio Gap",
                "dominance_ratio_diff": "Game Dominance Ratio Gap",
                "deciding_set_diff": "Deciding Set Win Rate Gap",
                "tiebreak_diff": "Tiebreak Win Rate Gap",
                "h2h_win_rate_diff": "Head-to-Head Win Rate Gap",
                "h2h_surface_win_rate_diff": "Surface H2H Win Rate Gap",
                "h2h_matches": "H2H Match Experience",
                "days_rest_diff": "Rest Days Differential",
                "fatigue_30d_diff": "Fatigue (30-day match load)",
                "surface_exp_diff": "Surface Experience Gap",
                "age_diff": "Player Age Differential",
            }

            feat_df = pd.DataFrame({
                "Raw_Feature": list(importances.keys()),
                "Feature": [label_map.get(k, k) for k in importances.keys()],
                "Importance": list(importances.values()),
            }).sort_values(by="Importance", ascending=True)

            fig = px.bar(
                feat_df,
                x="Importance",
                y="Feature",
                orientation="h",
                color="Importance",
                color_continuous_scale="Blues",
                text="Importance"
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                height=560,
                margin=dict(t=20, b=20, l=20, r=20),
                coloraxis_showscale=False,
                xaxis_title="Relative Feature Importance (Gain)",
                yaxis_title=""
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("ℹ️ Feature Engineering Insights"):
                st.markdown("""
                - **Surface-Blended Elo Gap**: Dynamically weights surface-specific Elo based on match experience (e.g. Grass sample size).
                - **Projected Hold & Break Gaps**: Bivariate interaction between Player A's serve hold % and Player B's return break %.
                - **Log Rank Ratio**: Captures non-linear rank disparity (gap between #1 and #10 is much greater than #100 and #110).
                - **Fatigue & Rest**: Accounts for 30-day match load and recovery days between tournament rounds.
                """)

    # TAB 2: PROBABILITY CALIBRATION CURVE
    with tab_calib:
        st.markdown("#### 🎯 Reliability Diagram & Calibration Curve")
        st.caption("Validates that when the model predicts an outcome with X% confidence, it actually happens X% of the time.")
        
        # Synthetic calibration buckets for demonstration from validation dataset
        st.info("Reliability diagram requires graded match data")

    # TAB 3: SURFACE SPECIALIZATION
    with tab_surf:
        st.markdown(f"#### 🌱 Surface Performance Splits ({selected_circuit})")
        st.caption("Model accuracy, hold rate dynamics, and game length profiles across surfaces.")
        
        st.info("Surface analysis requires graded match data")

    # TAB 4: ARCHITECTURE & SPLITS
    with tab_model_info:
        st.markdown("#### ⚙️ Pipeline Architecture & Validation Strategy")
        st.markdown(r"""
        - **Model Engine**: LightGBM Gradient Boosted Decision Trees (`LGBMClassifier`) with calibrated sigmoid probability mapping.
        - **Historical Span**: 2020 – 2026 chronological match series.
        - **Validation Strategy**: 5-Fold Time-Series Walk-Forward Cross-Validation (zero future lookahead bias).
        - **Feature Pipeline**: Dynamic Elo Engine (Overall + Surface K-factor decay), Serve/Return matrix, Exponential Form decay ($\lambda = 0.95$), and H2H interaction terms.
        - **Target Variable**: Match Outcome binary flag (`1` for Player 1 win, `0` for Player 2 win).
        """)
