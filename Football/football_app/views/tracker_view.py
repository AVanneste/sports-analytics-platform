"""Model verification, prediction accuracy tracking, and real-world results reconciliation view."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from typing import List, Dict, Any

from football_core.betting.tracker import PredictionTracker
from football_core.data.preprocessor import load_processed_league_data
from football_core.config import LEAGUES


def _get_pred_1x2(p: Dict[str, Any]) -> str:
    val = p.get("pred_1x2")
    if val:
        return str(val)
    ph = float(p.get("prob_home", 0.33) or 0.33)
    pd_ = float(p.get("prob_draw", 0.33) or 0.33)
    pa = float(p.get("prob_away", 0.33) or 0.33)
    if ph >= pd_ and ph >= pa:
        return f"{p.get('home_team', 'Home')} Win"
    elif pa >= ph and pa >= pd_:
        return f"{p.get('away_team', 'Away')} Win"
    else:
        return "Draw"


def _get_pred_over25(p: Dict[str, Any]) -> str:
    val = p.get("pred_over25")
    if val:
        return str(val)
    po = float(p.get("prob_over25", 0.5) or 0.5)
    return "Over 2.5" if po >= 0.5 else "Under 2.5"


def _get_pred_btts(p: Dict[str, Any]) -> str:
    val = p.get("pred_btts")
    if val:
        return str(val)
    pb = float(p.get("prob_btts_yes", 0.5) or 0.5)
    return "Yes" if pb >= 0.5 else "No"


def _get_pred_corners(p: Dict[str, Any]) -> str:
    val = p.get("pred_corners_o95")
    if val:
        return str(val)
    pc = float(p.get("prob_corners_over95", 0.5) or 0.5)
    return "Over 9.5" if pc >= 0.5 else "Under 9.5"


def _get_pred_cards(p: Dict[str, Any]) -> str:
    val = p.get("pred_cards_o35")
    if val:
        return str(val)
    pcd = float(p.get("prob_cards_over35", 0.5) or 0.5)
    return "Over 3.5" if pcd >= 0.5 else "Under 3.5"


def _get_pred_score(p: Dict[str, Any]) -> str:
    return str(p.get("pred_score") or p.get("most_likely_score") or "1-1")


def _get_exp_goals(p: Dict[str, Any]) -> float:
    exp_t = p.get("exp_total_goals")
    if exp_t is not None:
        return float(exp_t)
    gh = float(p.get("expected_goals_home", 1.3) or 1.3)
    ga = float(p.get("expected_goals_away", 1.1) or 1.1)
    return gh + ga


def _get_exp_corners(p: Dict[str, Any]) -> float:
    c = p.get("exp_corners") or p.get("expected_corners")
    return float(c) if c is not None else 9.5


def _get_exp_cards(p: Dict[str, Any]) -> float:
    cd = p.get("exp_cards") or p.get("expected_cards")
    return float(cd) if cd is not None else 4.2


def compute_verification_metrics(preds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute purely statistical accuracy and error metrics across settled match predictions."""
    settled = [p for p in preds if p.get("status") == "settled"]
    total = len(settled)
    if total == 0:
        return {
            "total_logged": len(preds),
            "total_settled": 0,
            "acc_1x2": 0.0,
            "acc_o25": 0.0,
            "acc_btts": 0.0,
            "acc_corners": 0.0,
            "acc_cards": 0.0,
            "exact_score_hits": 0,
            "avg_goal_error": 0.0,
            "avg_corner_error": 0.0,
            "avg_card_error": 0.0,
        }

    c_1x2 = sum(1 for p in settled if p.get("correct_1x2") is True)
    c_o25 = sum(1 for p in settled if p.get("correct_over25") is True)
    c_btts = sum(1 for p in settled if p.get("correct_btts") is True)
    c_corn = sum(1 for p in settled if p.get("correct_corners_o95") is True)
    c_cards = sum(1 for p in settled if p.get("correct_cards_o35") is True)
    c_score = sum(1 for p in settled if p.get("correct_score") is True)

    goal_errs = [float(p.get("goal_error", 0.0)) for p in settled if p.get("goal_error") is not None]
    corn_errs = [float(p.get("corner_error", 0.0)) for p in settled if p.get("corner_error") is not None]
    card_errs = [float(p.get("card_error", 0.0)) for p in settled if p.get("card_error") is not None]

    return {
        "total_logged": len(preds),
        "total_settled": total,
        "acc_1x2": (c_1x2 / total) * 100.0,
        "acc_o25": (c_o25 / total) * 100.0,
        "acc_btts": (c_btts / total) * 100.0,
        "acc_corners": (c_corn / total) * 100.0,
        "acc_cards": (c_cards / total) * 100.0,
        "exact_score_hits": c_score,
        "avg_goal_error": float(np.mean(goal_errs)) if goal_errs else 0.0,
        "avg_corner_error": float(np.mean(corn_errs)) if corn_errs else 0.0,
        "avg_card_error": float(np.mean(card_errs)) if card_errs else 0.0,
    }


def render_tracker_view(tracker: PredictionTracker):
    st.markdown("<h2 style='color:#10b981;'>🔬 Model Verification & Results Accuracy Tracker</h2>", unsafe_allow_html=True)
    st.caption("Purely statistical verification of model predictions against actual match results across 1X2, Goals, BTTS, Corners, Cards, and Scorelines (independent of odds/EV).")

    # Action Toolbar
    act_col1, act_col2 = st.columns([3, 1.5])
    
    with act_col1:
        if st.button("🔄 Auto-Reconcile Real Match Results (API-Football & Web)", type="primary", use_container_width=True):
            with st.spinner("Fetching official completed match scores & statistics from API-Football & data feeds..."):
                from football_core.data.api_football import reconcile_predictions_with_api_football, fetch_api_football_status
                from football_core.data.fetcher import download_league_season
                from football_core.data.preprocessor import load_raw_league_data, clean_match_data, save_processed_data
                
                # 1. Primary: API-Football live query
                api_res = reconcile_predictions_with_api_football(tracker)
                reconciled_api = api_res.get("reconciled", 0)
                
                # 2. Secondary fallback: football-data.co.uk
                reconciled_csv = 0
                download_errors = []
                for l_k, l_info in LEAGUES.items():
                    if l_info.get("is_cup"):
                        continue
                    p = download_league_season(l_k, "2425", force=True)
                    if p:
                        raw_df = load_raw_league_data(l_k)
                        if not raw_df.empty:
                            cleaned = clean_match_data(raw_df, l_k)
                            if not cleaned.empty:
                                save_processed_data(cleaned, l_k)
                                settled = tracker.reconcile_with_completed_matches(cleaned)
                                reconciled_csv += settled
                    else:
                        download_errors.append(l_k)
                
                total_settled = reconciled_api + reconciled_csv
                if total_settled > 0:
                    st.success(f"🎉 Successfully reconciled {total_settled} real matches via API-Football!")
                    if api_res.get("matches"):
                        with st.expander("📋 View Concluded Matches Verified", expanded=True):
                            for m_str in api_res.get("matches", []):
                                st.markdown(f"- ⚽ **{m_str}**")
                else:
                    st.info("ℹ️ Checked API-Football and datasets. No newly finished matches found matching pending fixture dates/teams.")
                st.rerun()

    with act_col2:
        if st.button("🗑️ Reset All to Pending", use_container_width=True):
            for pred in tracker.predictions:
                pred["status"] = "pending"
                pred["actual_score"] = None
                pred["actual_winner"] = None
                pred["actual_goals"] = None
                pred["actual_btts"] = None
                pred["actual_corners"] = None
                pred["actual_cards"] = None
                pred["correct_1x2"] = None
                pred["correct_over25"] = None
                pred["correct_btts"] = None
                pred["correct_corners_o95"] = None
                pred["correct_cards_o35"] = None
                pred["correct_score"] = None
                pred["goal_error"] = None
                pred["corner_error"] = None
                pred["card_error"] = None
            tracker.save()
            st.success("All predictions reset to pending status.")
            st.rerun()

    # Manual Real Result Entry Section
    pending_list = [p for p in tracker.predictions if p.get("status") != "settled"]
    with st.expander("📝 Record Official Real Match Result (Manual Verification)", expanded=False):
        if not pending_list:
            st.info("No pending matches awaiting verification.")
        else:
            m_options = {f"{p.get('date')} | {p.get('league')} | {p.get('home_team')} vs {p.get('away_team')}": p for p in pending_list}
            selected_label = st.selectbox("Select Concluded Match to Verify", list(m_options.keys()))
            selected_p = m_options[selected_label]
            
            s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns([1.5, 1.5, 1.5, 1.5, 1.5])
            with s_col1:
                hg_in = st.number_input(f"{selected_p.get('home_team')} Goals", min_value=0, max_value=15, value=2)
            with s_col2:
                ag_in = st.number_input(f"{selected_p.get('away_team')} Goals", min_value=0, max_value=15, value=1)
            with s_col3:
                hc_in = st.number_input("Home Corners", min_value=0, max_value=25, value=5)
            with s_col4:
                ac_in = st.number_input("Away Corners", min_value=0, max_value=25, value=4)
            with s_col5:
                cd_in = st.number_input("Total Cards", min_value=0, max_value=20, value=4)
                
            if st.button("✅ Verify & Settle Football Match", type="primary", use_container_width=True):
                tracker.grade_single_match(
                    selected_p["match_id"],
                    fthg=int(hg_in),
                    ftag=int(ag_in),
                    hc=int(hc_in),
                    ac=int(ac_in),
                    cards=int(cd_in)
                )
                st.success(f"Recorded verified result for {selected_label} as {hg_in}-{ag_in}!")
                st.rerun()

    preds = getattr(tracker, "predictions", [])
    metrics = compute_verification_metrics(preds)

    # Top Statistical Scorecard
    st.markdown("### 📊 Realized Model Accuracy Scorecard")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Verified", metrics["total_settled"], f"{metrics['total_logged']} Logged")
    k2.metric("1X2 Hit Rate", f"{metrics['acc_1x2']:.1f}%")
    k3.metric("O/U 2.5 Goals", f"{metrics['acc_o25']:.1f}%")
    k4.metric("BTTS Hit Rate", f"{metrics['acc_btts']:.1f}%")
    k5.metric("Corners >9.5", f"{metrics['acc_corners']:.1f}%")
    k6.metric("Cards >3.5", f"{metrics['acc_cards']:.1f}%")

    # Error KPIs
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Avg Goal Error (xG vs Actual)", f"{metrics['avg_goal_error']:.2f} goals")
    e2.metric("Avg Corner Error (λ vs Actual)", f"{metrics['avg_corner_error']:.1f} corners")
    e3.metric("Avg Card Error (λ vs Actual)", f"{metrics['avg_card_error']:.1f} cards")
    e4.metric("Exact Scoreline Hits", f"{metrics['exact_score_hits']} matches")

    st.markdown("---")

    if not preds:
        st.info("No predictions logged for verification yet. Visit the **Upcoming Fixtures** board and click **'⚡ Track All Matches for Verification'** to log match projections!")
        return

    # Dedicated Category Verification Tabs
    tab_1x2, tab_goals, tab_btts, tab_corners, tab_cards, tab_score = st.tabs([
        "🏆 1X2 Match Outcomes",
        "⚽ Goals & xG Accuracy",
        "🥅 Both Teams To Score",
        "🚩 Corners Line Verification",
        "🟨 Cards & Referee Disciplinary",
        "🎯 Exact Scoreline Predictions"
    ])

    # 1. 1X2 Tab
    with tab_1x2:
        st.markdown("#### 🏆 1X2 Outcome Verification (Predicted Winner vs Actual)")
        rows_1x2 = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_1x2")
            icon = ("✅ Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"

            rows_1x2.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Model Pred (1X2)": _get_pred_1x2(p),
                "P(Home)": f"{float(p.get('prob_home', 0.33) or 0.33)*100:.1f}%",
                "P(Draw)": f"{float(p.get('prob_draw', 0.33) or 0.33)*100:.1f}%",
                "P(Away)": f"{float(p.get('prob_away', 0.33) or 0.33)*100:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Actual Winner": p.get("actual_winner") or "-",
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_1x2), use_container_width=True, hide_index=True)

    # 2. Goals Tab
    with tab_goals:
        st.markdown("#### ⚽ Over / Under 2.5 Goals & Expected Goals (xG) Accuracy")
        rows_goals = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_over25")
            icon = ("✅ Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"
            actual_xg_val = p.get("actual_xg")

            rows_goals.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Projected xG": f"{_get_exp_goals(p):.2f}",
                "Actual xG": f"{float(actual_xg_val):.2f}" if (is_settled and actual_xg_val is not None) else "-",
                "Pred O/U 2.5": _get_pred_over25(p),
                "P(Over 2.5)": f"{float(p.get('prob_over25', 0.5) or 0.5)*100:.1f}%",
                "P(Under 2.5)": f"{float(p.get('prob_under25', 0.5) or 0.5)*100:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Actual Total Goals": p.get("actual_goals") if is_settled else "-",
                "Verification": icon,
                "Goal Error": f"{p.get('goal_error', '-')} goals" if is_settled else "-",
            })
        st.dataframe(pd.DataFrame(rows_goals), use_container_width=True, hide_index=True)

    # 3. BTTS Tab
    with tab_btts:
        st.markdown("#### 🥅 Both Teams To Score (BTTS) Verification")
        rows_btts = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_btts")
            icon = ("✅ Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"

            rows_btts.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Model Pred (BTTS)": _get_pred_btts(p),
                "P(BTTS Yes)": f"{float(p.get('prob_btts_yes', 0.5) or 0.5)*100:.1f}%",
                "P(BTTS No)": f"{float(p.get('prob_btts_no', 0.5) or 0.5)*100:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Both Scored?": p.get("actual_btts") or "-",
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_btts), use_container_width=True, hide_index=True)

    # 4. Corners Tab
    with tab_corners:
        st.markdown("#### 🚩 Corners Modeling & Over/Under 9.5 Line Accuracy")
        rows_corn = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_corners_o95")
            icon = ("✅ Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"

            rows_corn.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Exp. Corners (λ)": f"{_get_exp_corners(p):.1f}",
                "Pred O/U 9.5": _get_pred_corners(p),
                "P(Over 9.5)": f"{float(p.get('prob_corners_over95', 0.5) or 0.5)*100:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Actual Corners": p.get("actual_corners") if is_settled else "-",
                "Verification": icon,
                "Corner Error": f"{p.get('corner_error', '-')} corners" if is_settled else "-",
            })
        st.dataframe(pd.DataFrame(rows_corn), use_container_width=True, hide_index=True)

    # 5. Cards & Referee Tab
    with tab_cards:
        st.markdown("#### 🟨 Disciplinary Cards & Official Referee Impact Verification")
        rows_cards = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_cards_o35")
            icon = ("✅ Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"

            rows_cards.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Official Referee": p.get("referee") or "Unassigned",
                "Exp. Cards (λ)": f"{_get_exp_cards(p):.1f}",
                "Pred O/U 3.5": _get_pred_cards(p),
                "P(Over 3.5)": f"{float(p.get('prob_cards_over35', 0.5) or 0.5)*100:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Actual Cards": p.get("actual_cards") if is_settled else "-",
                "Verification": icon,
                "Card Error": f"{p.get('card_error', '-')} cards" if is_settled else "-",
            })
        st.dataframe(pd.DataFrame(rows_cards), use_container_width=True, hide_index=True)

    # 6. Scorelines Tab
    with tab_score:
        st.markdown("#### 🎯 Exact Scoreline Projections Accuracy")
        rows_score = []
        for p in reversed(preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_score")
            icon = ("🎯 Exact Hit" if correct else "❌ Miss") if is_settled else "⏳ Pending"

            rows_score.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Predicted Scoreline": _get_pred_score(p),
                "Actual Scoreline": p.get("actual_score") or "-",
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_score), use_container_width=True, hide_index=True)

