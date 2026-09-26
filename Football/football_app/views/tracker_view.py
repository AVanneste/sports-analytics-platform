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
            "val_settled_count": 0,
            "val_wins": 0,
            "val_win_rate": 0.0,
            "val_pnl": 0.0,
            "val_staked": 0.0,
            "val_roi": 0.0,
            "val_avg_ev": 0.0,
        }

    c_1x2 = sum(1 for p in settled if p.get("correct_1x2") is True)
    c_o25 = sum(1 for p in settled if p.get("correct_over25") is True)
    c_btts = sum(1 for p in settled if p.get("correct_btts") is True)

    corn_settled = [p for p in settled if p.get("actual_corners") is not None and float(p.get("actual_corners", -1)) >= 0]
    cards_settled = [p for p in settled if p.get("actual_cards") is not None and float(p.get("actual_cards", -1)) >= 0]

    c_corn = sum(1 for p in corn_settled if p.get("correct_corners_o95") is True)
    c_cards = sum(1 for p in cards_settled if p.get("correct_cards_o35") is True)
    c_score = sum(1 for p in settled if p.get("correct_score") is True)

    goal_errs = [float(p.get("goal_error", 0.0)) for p in settled if p.get("goal_error") is not None]
    corn_errs = [float(p.get("corner_error", 0.0)) for p in corn_settled if p.get("corner_error") is not None]
    card_errs = [float(p.get("card_error", 0.0)) for p in cards_settled if p.get("card_error") is not None]

    val_settled = [p for p in settled if p.get("has_value") or (p.get("best_pick") and (p.get("best_pick", {}).get("ev") or 0) > 0)]
    val_wins = sum(1 for p in val_settled if p.get("won"))
    val_pnl = sum(float(p.get("flat_pnl", 0.0)) for p in val_settled)
    val_staked = len(val_settled) * 100.0
    val_roi = (val_pnl / val_staked * 100.0) if val_staked > 0 else 0.0
    val_win_rate = (val_wins / len(val_settled) * 100.0) if val_settled else 0.0
    val_ev_list = [float(p.get("best_pick", {}).get("ev", 0.0) or 0.0) for p in val_settled]
    val_avg_ev = float(np.mean(val_ev_list) * 100.0) if val_ev_list else 0.0

    return {
        "total_logged": len(preds),
        "total_settled": total,
        "acc_1x2": (c_1x2 / total) * 100.0,
        "acc_o25": (c_o25 / total) * 100.0,
        "acc_btts": (c_btts / total) * 100.0,
        "acc_corners": (c_corn / len(corn_settled) * 100.0) if corn_settled else 0.0,
        "acc_cards": (c_cards / len(cards_settled) * 100.0) if cards_settled else 0.0,
        "corn_reported": len(corn_settled),
        "cards_reported": len(cards_settled),
        "exact_score_hits": c_score,
        "avg_goal_error": float(np.mean(goal_errs)) if goal_errs else 0.0,
        "avg_corner_error": float(np.mean(corn_errs)) if corn_errs else 0.0,
        "avg_card_error": float(np.mean(card_errs)) if card_errs else 0.0,
        "val_settled_count": len(val_settled),
        "val_wins": val_wins,
        "val_win_rate": val_win_rate,
        "val_pnl": val_pnl,
        "val_staked": val_staked,
        "val_roi": val_roi,
        "val_avg_ev": val_avg_ev,
    }


def render_tracker_view(tracker: PredictionTracker):
    # Daily background auto-reconciliation
    if "fb_last_auto_reconcile" not in st.session_state:
        st.session_state["fb_last_auto_reconcile"] = True
        try:
            from football_core.data.api_football import auto_check_daily_reconciliation
            auto_check_daily_reconciliation(tracker, force=False)
        except Exception:
            pass

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

    all_preds = getattr(tracker, "predictions", [])

    if not all_preds:
        st.info("No predictions logged for verification yet. Visit the **Upcoming Fixtures** board and match projections will be automatically logged!")
        return

    # Dynamic Filter Controls
    st.markdown("### 🔍 Filter Verification Ledger")
    f_col1, f_col2, f_col3, f_col4 = st.columns([2.2, 3.2, 1.8, 1.8])

    # 1. Parse unique dates
    parsed_dates = []
    for p in all_preds:
        d_raw = p.get("date")
        if d_raw and len(d_raw) >= 10:
            try:
                parsed_dates.append(pd.to_datetime(d_raw[:10]).date())
            except Exception:
                pass
    min_date = min(parsed_dates) if parsed_dates else datetime.now().date()
    max_date = max(parsed_dates) if parsed_dates else datetime.now().date()

    with f_col1:
        date_sel = st.date_input(
            "📅 Match Date Range",
            value=(min_date, max_date),
            help="Filter tracker tables and scorecards by fixture date range"
        )
        if isinstance(date_sel, (tuple, list)) and len(date_sel) == 2:
            start_date, end_date = date_sel[0], date_sel[1]
        elif isinstance(date_sel, (tuple, list)) and len(date_sel) == 1:
            start_date, end_date = date_sel[0], date_sel[0]
        else:
            start_date, end_date = None, None

    # 2. Parse unique leagues
    unique_leagues = sorted(list({p.get("league", "Other") for p in all_preds if p.get("league")}))
    with f_col2:
        selected_leagues = st.multiselect(
            "🏆 Filter by Competition / League",
            options=unique_leagues,
            default=unique_leagues,
            help="Select one or multiple leagues to narrow down verification scorecard"
        )

    # 3. Status filter
    with f_col3:
        status_filter = st.selectbox(
            "📌 Status Filter",
            options=["All Statuses", "Settled Only", "Pending Only"],
            index=0
        )

    # 4. Cohort filter
    with f_col4:
        cohort_filter = st.selectbox(
            "⭐ Strategy Cohort",
            options=["All Evaluated Fixtures", "+EV Value Bets Only"],
            index=0
        )

    # Apply Filters
    filtered_preds = []
    for p in all_preds:
        # Cohort check
        if cohort_filter == "+EV Value Bets Only":
            if not (p.get("has_value") or (p.get("best_pick") and (p.get("best_pick", {}).get("ev") or 0) > 0)):
                continue

        # League check
        l_name = p.get("league", "Other")
        if selected_leagues and l_name not in selected_leagues:
            continue

        # Status check
        p_status = p.get("status", "pending")
        if status_filter == "Settled Only" and p_status != "settled":
            continue
        if status_filter == "Pending Only" and p_status == "settled":
            continue

        # Date check
        if start_date and end_date:
            d_raw = p.get("date", "")
            if d_raw and len(d_raw) >= 10:
                try:
                    p_d = pd.to_datetime(d_raw[:10]).date()
                    if not (start_date <= p_d <= end_date):
                        continue
                except Exception:
                    pass

        filtered_preds.append(p)

    metrics = compute_verification_metrics(filtered_preds)

    # Financial Accounting Banner
    st.markdown("### 💰 Financial Performance & Realized PnL Ledger")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Settled Value Bets", f"{metrics['val_settled_count']}", f"Win Rate: {metrics['val_win_rate']:.1f}% ({metrics['val_wins']}W)")
    b2.metric("Total Staked (100€/bet)", f"{metrics['val_staked']:,.0f}€", f"Avg Edge: +{metrics['val_avg_ev']:.1f}% EV")
    b3.metric("Realized Net Profit", f"{metrics['val_pnl']:+,.2f}€", f"{metrics['val_roi']:+.1f}% ROI", delta_color="normal")
    b4.metric("Bankroll Multiplier", f"{(10000 + metrics['val_pnl'])/10000:.2f}x", "Based on 10k€ bankroll")

    # Top Statistical Scorecard
    st.markdown("### 📊 Realized Model Accuracy Scorecard")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Verified Matches", metrics["total_settled"], f"{metrics['total_logged']} in Filter")
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

    def _render_table_footer(df_rows, cat_name):
        n_shown = len(df_rows)
        n_settled = sum(1 for r in df_rows if "✅" in str(r.get("Verification", "")) or "🎯" in str(r.get("Verification", "")) or "❌" in str(r.get("Verification", "")) or "WON" in str(r.get("Outcome", "")))
        n_pending = n_shown - n_settled
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 6px; padding: 8px 12px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #94a3b8;">
            <div>
                📊 <b>Table Size:</b> Showing <b style="color:#38bdf8;">{n_shown}</b> matches ({n_settled} Settled, {n_pending} Pending) • Filtered from <b>{len(all_preds)}</b> total logged predictions
            </div>
            <div>
                ⚡ <b>Category:</b> {cat_name} • <b>Engine:</b> PitchVision 2.0
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Dedicated Category Verification Tabs
    tab_value, tab_1x2, tab_goals, tab_btts, tab_corners, tab_cards, tab_score = st.tabs([
        "💰 +EV Value Bets & PnL",
        "🏆 1X2 Match Outcomes",
        "⚽ Goals & xG Accuracy",
        "🥅 Both Teams To Score",
        "🚩 Corners Line Verification",
        "🟨 Cards & Referee Disciplinary",
        "🎯 Exact Scoreline Predictions"
    ])

    # 0. Value Bets Tab
    with tab_value:
        st.markdown("#### 💰 Realized +EV Value Betting Ledger & Profit/Loss Breakdown")
        val_rows = []
        for p in reversed(filtered_preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            pick = p.get("best_pick") or {}
            market = pick.get("market") or "1X2"
            selection = pick.get("selection") or _get_pred_1x2(p)
            odds = float(pick.get("odds", 2.0) or 2.0)
            prob = float(pick.get("prob", 0.5) or 0.5)
            ev = float(pick.get("ev", 0.0) or 0.0)
            ev_pct = ev if ev > 1 else ev * 100
            won = p.get("won")
            flat_pnl = p.get("flat_pnl")
            if flat_pnl is None and is_settled:
                flat_pnl = (odds - 1.0) * 100.0 if won else -100.0

            pnl_str = f"{flat_pnl:+.2f}€" if (is_settled and flat_pnl is not None) else "-"
            outcome_icon = ("✅ WON" if won else "❌ LOST") if is_settled else "⏳ PENDING"

            val_rows.append({
                "Date": p.get("date", "-"),
                "League": p.get("league", "-"),
                "Match": f"{p.get('home_team')} vs {p.get('away_team')}",
                "Market": market,
                "Selection": selection,
                "Odds": f"@{odds:.2f}",
                "Model Prob": f"{prob*100:.1f}%",
                "Edge (EV)": f"+{ev_pct:.1f}%" if ev_pct > 0 else f"{ev_pct:.1f}%",
                "Actual Score": p.get("actual_score") or "-",
                "Outcome": outcome_icon,
                "Unit Stake": "100.00€",
                "Net PnL": pnl_str,
            })
        st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)
        _render_table_footer(val_rows, "Value Bets & Realized PnL")

    # 1. 1X2 Tab
    with tab_1x2:
        st.markdown("#### 🏆 1X2 Outcome Verification (Predicted Winner vs Actual)")
        rows_1x2 = []
        for p in reversed(filtered_preds):
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
        _render_table_footer(rows_1x2, "1X2 Outcomes")

    # 2. Goals Tab
    with tab_goals:
        st.markdown("#### ⚽ Over / Under 2.5 Goals & Expected Goals (xG) Accuracy")
        rows_goals = []
        for p in reversed(filtered_preds):
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
        _render_table_footer(rows_goals, "Goals & Expected Goals (xG)")

    # 3. BTTS Tab
    with tab_btts:
        st.markdown("#### 🥅 Both Teams To Score (BTTS) Verification")
        rows_btts = []
        for p in reversed(filtered_preds):
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
        _render_table_footer(rows_btts, "Both Teams To Score")

    # 4. Corners Tab
    with tab_corners:
        st.markdown("#### 🚩 Corners Modeling & Over/Under 9.5 Line Accuracy")
        rows_corn = []
        for p in reversed(filtered_preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_corners_o95")
            has_corn = (p.get("actual_corners") is not None)
            icon = ("✅ Hit" if correct else "❌ Miss") if (is_settled and has_corn) else ("⚪ Unreported" if is_settled else "⏳ Pending")

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
        _render_table_footer(rows_corn, "Corners Modeling")

    # 5. Cards & Referee Tab
    with tab_cards:
        st.markdown("#### 🟨 Disciplinary Cards & Official Referee Impact Verification")
        rows_cards = []
        for p in reversed(filtered_preds):
            status = p.get("status", "pending")
            is_settled = (status == "settled")
            correct = p.get("correct_cards_o35")
            has_cards = (p.get("actual_cards") is not None)
            icon = ("✅ Hit" if correct else "❌ Miss") if (is_settled and has_cards) else ("⚪ Unreported" if is_settled else "⏳ Pending")

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
        _render_table_footer(rows_cards, "Cards & Referee Disciplinary")

    # 6. Scorelines Tab
    with tab_score:
        st.markdown("#### 🎯 Exact Scoreline Projections Accuracy")
        rows_score = []
        for p in reversed(filtered_preds):
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
        _render_table_footer(rows_score, "Exact Scorelines")

