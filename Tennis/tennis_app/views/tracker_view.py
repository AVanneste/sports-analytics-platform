"""Post-Match Tracker, Multi-Market Model Accuracy Validator, and PnL/ROI Dashboard for CourtVision."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from typing import Dict, List, Any, Optional

from tennis_core.betting.tracker import PredictionTracker
from tennis_core.data.preprocessor import load_raw_matches, clean_match_data
from tennis_core.models.sets_games import calculate_sets_and_games_probabilities
from tennis_core.utils.helpers import parse_score_details, detect_match_format, strip_accents


def _extract_match_metrics(p: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and compute all market projections and actual results for a prediction record."""
    p1 = p.get("p1_name", "Player 1")
    p2 = p.get("p2_name", "Player 2")
    circuit = p.get("circuit", "ATP")
    surface = p.get("surface", "Hard")
    tourney = p.get("tourney_name", "Tourney")
    
    p1_p = float(p.get("p1_prob", 50.0)) / 100.0
    p2_p = 1.0 - p1_p
    
    fmt = detect_match_format(tourney, circuit)
    
    # Calculate Sets & Games Analytics
    sg = calculate_sets_and_games_probabilities(
        p1_match_prob=p1_p,
        circuit=circuit,
        surface=surface,
        best_of=fmt,
        p1_name=p1,
        p2_name=p2
    )
    
    # Check settlement status
    status = p.get("status", "PENDING")
    winner = p.get("actual_winner")
    score = p.get("score")
    is_settled = bool(winner and status not in ["PENDING", "VOID"])
    
    # Parse scoreline details if completed
    score_info = parse_score_details(score) if (score and is_settled) else {}
    
    actual_games = score_info.get("total_games")
    w_sets = score_info.get("w_sets", 0)
    l_sets = score_info.get("l_sets", 0)
    went_decider = score_info.get("deciding_set")
    
    # Player sets won
    p1_won_match = bool(winner and (strip_accents(p1).lower() in strip_accents(winner).lower() or strip_accents(winner).lower() in strip_accents(p1).lower()))
    p2_won_match = bool(winner and (strip_accents(p2).lower() in strip_accents(winner).lower() or strip_accents(winner).lower() in strip_accents(p2).lower()))
    
    p1_actual_sets = w_sets if p1_won_match else l_sets
    p2_actual_sets = w_sets if p2_won_match else l_sets
    
    p1_took_set = bool(p1_actual_sets >= 1) if is_settled else None
    p2_took_set = bool(p2_actual_sets >= 1) if is_settled else None
    
    # 1. Match Winner Verification
    model_winner_pick = p1 if p1_p >= p2_p else p2
    correct_winner = (winner == model_winner_pick) if is_settled else None
    
    # 2. Sets To Win >= 1 Set Verification
    # Model recommends high probability set win
    p1_set_prob = sg["p1_win_at_least_1_set_prob"]
    p2_set_prob = sg["p2_win_at_least_1_set_prob"]
    
    # 3. Total Games Verification
    main_line_info = sg.get("main_games_line", {})
    main_line = main_line_info.get("line", 22.5 if fmt == 3 else 38.5)
    exp_g = sg.get("expected_total_games", 22.0)
    
    # Strictly align model pick with projected total games vs line
    model_pred_over = bool(exp_g >= main_line)
    model_games_pick = f"Over {main_line}" if model_pred_over else f"Under {main_line}"
    
    if is_settled and actual_games is not None:
        actual_is_over = bool(actual_games > main_line)
        correct_games_ou = (actual_is_over == model_pred_over)
        game_error = abs(exp_g - actual_games)
    else:
        actual_is_over = None
        correct_games_ou = None
        game_error = None
        
    # 4. Deciding Set Verification
    model_pred_decider = bool(sg["prob_deciding_set"] >= 50.0)
    correct_decider = (went_decider == model_pred_decider) if is_settled and went_decider is not None else None
    
    # 5. Exact Scoreline Verification
    score_probs = sg.get("scoreline_probabilities", {})
    top_scoreline = max(score_probs.items(), key=lambda x: x[1])[0] if score_probs else f"{model_winner_pick} {2 if fmt==3 else 3}-0"
    actual_score_str = f"{winner} {w_sets}-{l_sets}" if is_settled and winner else None
    correct_scoreline = bool(actual_score_str and (top_scoreline == actual_score_str or top_scoreline.endswith(f"{w_sets}-{l_sets}"))) if is_settled else None

    # Confidence Tier
    max_p = max(p1_p, p2_p) * 100.0
    if max_p >= 70.0:
        conf_tier = "🔥 High (>70%)"
    elif max_p >= 55.0:
        conf_tier = "⚡ Moderate (55-70%)"
    else:
        conf_tier = "⚖️ Toss-Up (<55%)"

    return {
        "record": p,
        "date": p.get("date", "-"),
        "circuit": circuit,
        "tourney": tourney,
        "surface": surface,
        "format_str": f"Best of {fmt}",
        "best_of": fmt,
        "p1": p1,
        "p2": p2,
        "matchup": f"{p1} vs {p2}",
        "p1_prob": p1_p * 100.0,
        "p2_prob": p2_p * 100.0,
        "conf_tier": conf_tier,
        
        # Winner
        "model_winner_pick": model_winner_pick,
        "winner_confidence": max_p,
        "actual_winner": winner or "-",
        "official_score": score or "-",
        "is_settled": is_settled,
        "correct_winner": correct_winner,
        
        # Sets
        "p1_set_prob": p1_set_prob,
        "p2_set_prob": p2_set_prob,
        "p1_set_odds": sg["p1_win_at_least_1_set_odds"],
        "p2_set_odds": sg["p2_win_at_least_1_set_odds"],
        "p1_actual_sets": p1_actual_sets if is_settled else "-",
        "p2_actual_sets": p2_actual_sets if is_settled else "-",
        "p1_took_set": p1_took_set,
        "p2_took_set": p2_took_set,
        
        # Games
        "expected_games": sg["expected_total_games"],
        "main_line": main_line,
        "main_line_over_prob": main_line_info.get("prob_over", 50.0),
        "main_line_under_prob": main_line_info.get("prob_under", 50.0),
        "model_games_pick": f"Over {main_line}" if model_pred_over else f"Under {main_line}",
        "actual_games": actual_games if is_settled else "-",
        "game_error": round(game_error, 1) if game_error is not None else None,
        "correct_games_ou": correct_games_ou,
        "games_table": sg.get("games_market_table", []),
        
        # Scorelines
        "top_scoreline": top_scoreline,
        "top_scoreline_prob": round(score_probs.get(top_scoreline, 0.0) * 100.0, 1),
        "actual_scoreline": actual_score_str or "-",
        "correct_scoreline": correct_scoreline,
        "score_probs": score_probs,
        
        # Decider
        "prob_deciding_set": sg["prob_deciding_set"],
        "model_decider_pick": "Yes (Decider)" if model_pred_decider else "No (Straight Sets)",
        "actual_went_decider": "Yes" if went_decider else "No" if is_settled else "-",
        "correct_decider": correct_decider,
    }


def compute_tennis_metrics(data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate accuracy and statistical metrics across all settled predictions."""
    settled = [d for d in data_list if d["is_settled"]]
    total = len(settled)
    if total == 0:
        return {
            "total_logged": len(data_list),
            "total_settled": 0,
            "acc_winner": 0.0,
            "acc_set_p1": 0.0,
            "acc_games_ou": 0.0,
            "acc_decider": 0.0,
            "exact_score_hits": 0,
            "avg_game_error": 0.0,
        }

    c_win = sum(1 for d in settled if d["correct_winner"] is True)
    c_set = sum(1 for d in settled if (d["p1_took_set"] is True if d["p1_set_prob"] >= d["p2_set_prob"] else d["p2_took_set"] is True))
    c_games = sum(1 for d in settled if d["correct_games_ou"] is True)
    c_decider = sum(1 for d in settled if d["correct_decider"] is True)
    c_score = sum(1 for d in settled if d["correct_scoreline"] is True)
    
    game_errs = [d["game_error"] for d in settled if d["game_error"] is not None]

    return {
        "total_logged": len(data_list),
        "total_settled": total,
        "acc_winner": (c_win / total) * 100.0,
        "acc_set_p1": (c_set / total) * 100.0,
        "acc_games_ou": (c_games / total) * 100.0,
        "acc_decider": (c_decider / total) * 100.0,
        "exact_score_hits": c_score,
        "avg_game_error": float(np.mean(game_errs)) if game_errs else 0.0,
    }


def render_tracker_view(tracker):
    # Daily background auto-reconciliation
    if "tn_last_auto_reconcile" not in st.session_state:
        st.session_state["tn_last_auto_reconcile"] = True
        try:
            from tennis_core.data.fetcher import download_current_year_data
            from tennis_core.data.preprocessor import load_raw_tennis_data, clean_match_data, save_processed_data
            for c_key in ["atp", "wta"]:
                p = download_current_year_data(c_key, force=False)
                if p:
                    raw_df = load_raw_tennis_data(c_key)
                    if not raw_df.empty:
                        cleaned = clean_match_data(raw_df, c_key)
                        if not cleaned.empty:
                            save_processed_data(cleaned, c_key)
                            tracker.auto_reconcile(cleaned)
        except Exception:
            pass

    st.markdown("<h2 style='color:#3b82f6;'>📈 Model Verification & Match Results Ledger</h2>", unsafe_allow_html=True)
    st.caption("Comprehensive statistical verification of model predictions against actual results across Match Outcomes, Set Scoring, Total Games O/U, Exact Scorelines, Deciding Sets & PnL.")

    # Action Toolbar
    act_col1, act_col2 = st.columns([3, 1.5])
    
    with act_col1:
        if st.button("🔄 Auto-Download Online Results & Reconcile", type="primary", use_container_width=True):
            with st.spinner("Downloading newest match results from tennis-data.co.uk & reconciling..."):
                try:
                    from tennis_core.data.fetcher import download_tennis_data_year
                    download_tennis_data_year("atp", 2026, force=True)
                    download_tennis_data_year("wta", 2026, force=True)
                    df_atp = clean_match_data(load_raw_matches("atp"), "atp")
                    df_wta = clean_match_data(load_raw_matches("wta"), "wta")
                    df_combined = pd.concat([df_atp, df_wta], ignore_index=True)
                    reconciled = tracker.auto_reconcile(df_combined)
                    if reconciled > 0:
                        st.success(f"Successfully reconciled {reconciled} completed matches!")
                    else:
                        st.info("Checked latest tournament datasets. No newly published official scores found for pending fixtures.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during online reconciliation: {e}")

    with act_col2:
        if st.button("🗑️ Reset All to Pending", use_container_width=True):
            for pred in tracker.predictions:
                pred["status"] = "PENDING"
                pred["actual_winner"] = None
                pred["score"] = None
                pred["pnl"] = 0.0
                pred["flat_pnl"] = 0.0
                pred["model_correct"] = None
            tracker._save_predictions()
            st.success("All predictions reset to PENDING status.")
            st.rerun()

    # Interactive Manual Settlement Section
    pending_list = [p for p in tracker.predictions if p.get("status") == "PENDING"]
    with st.expander("⚡ Quick Manual Settlement (Enter Actual Scores for Any Match)", expanded=False):
        if not pending_list:
            st.info("No pending matches to settle.")
        else:
            m_options = {f"{p.get('date')} | {p.get('circuit')} | {p.get('p1_name')} vs {p.get('p2_name')} ({p.get('tourney_name')})": p for p in pending_list}
            selected_label = st.selectbox("Select Pending Match to Settle", list(m_options.keys()))
            selected_p = m_options[selected_label]
            
            p1_n = selected_p.get("p1_name")
            p2_n = selected_p.get("p2_name")
            
            s_col1, s_col2, s_col3 = st.columns([2, 2, 1])
            with s_col1:
                winner_choice = st.selectbox("Actual Match Winner", [p1_n, p2_n])
            with s_col2:
                score_input = st.text_input("Official Set Score (e.g. 6-4 3-6 7-6)", value="6-4 6-3")
            with s_col3:
                st.write("")
                st.write("")
                if st.button("✅ Settle Match", type="primary", use_container_width=True):
                    tracker.grade_match(selected_p["match_id"], actual_winner=winner_choice, score=score_input)
                    st.success(f"Settled {selected_label} as {winner_choice} ({score_input})!")
                    st.rerun()

    # Process all predictions
    raw_preds = getattr(tracker, "predictions", [])
    extracted_data = [_extract_match_metrics(p) for p in raw_preds]
    metrics = compute_tennis_metrics(extracted_data)

    # Realized Model Accuracy Scorecard
    st.markdown("### 📊 Realized Model Accuracy Scorecard")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Verified", metrics["total_settled"], f"{metrics['total_logged']} Logged")
    k2.metric("Match Winner", f"{metrics['acc_winner']:.1f}%")
    k3.metric("Win ≥1 Set Hit", f"{metrics['acc_set_p1']:.1f}%")
    k4.metric("Total Games O/U", f"{metrics['acc_games_ou']:.1f}%")
    k5.metric("Deciding Set Hit", f"{metrics['acc_decider']:.1f}%")
    k6.metric("Exact Scoreline", f"{metrics['exact_score_hits']} hits")

    e1, e2 = st.columns(2)
    e1.metric("Avg Total Games Error (|Projected vs Actual|)", f"{metrics['avg_game_error']:.1f} games")

    st.markdown("---")

    if not extracted_data:
        st.info("No match predictions logged yet. Visit the **Upcoming Fixtures** board and click **'⚡ Track All Matches for Verification'** to log tournament projections!")
        return

    # Dedicated Category Verification Tabs
    tab_winner, tab_sets, tab_games, tab_score, tab_decider, tab_betting = st.tabs([
        "🏆 Match Winner (Moneyline)",
        "🎾 Set Scoring (Win ≥ 1 Set)",
        "🎮 Total Games & O/U Lines",
        "🎯 Exact Set Scorelines",
        "⚡ Deciding Sets (Over Sets)",
        "💰 Betting Value & Kelly PnL"
    ])

    # 1. MATCH WINNER TAB
    with tab_winner:
        st.markdown("#### 🏆 Match Outcomes Verification (Predicted Winner vs Actual)")
        rows_win = []
        for d in reversed(extracted_data):
            is_settled = d["is_settled"]
            icon = ("✅ Hit" if d["correct_winner"] else "❌ Miss") if is_settled else "⏳ Pending"
            rows_win.append({
                "Date": d["date"],
                "Circuit": d["circuit"],
                "Tournament": d["tourney"],
                "Surface": d["surface"],
                "Format": d["format_str"],
                "Matchup": d["matchup"],
                "Model Pick": d["model_winner_pick"],
                "P(P1 Win)": f"{d['p1_prob']:.1f}%",
                "P(P2 Win)": f"{d['p2_prob']:.1f}%",
                "Confidence": d["conf_tier"],
                "Actual Winner": d["actual_winner"],
                "Official Score": d["official_score"],
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_win), use_container_width=True, hide_index=True)

    # 2. SET SCORING TAB
    with tab_sets:
        st.markdown("#### 🎾 Set Scoring Verification (To Win at Least 1 Set / Set Handicap)")
        st.info("💡 **Market Explanation**: The **'To Win at Least 1 Set'** market (+1.5 Set Handicap in Best-of-3 / +2.5 Set Handicap in Best-of-5) evaluates each player's probability of taking 1 or more sets in the match. The **'Recommended Set Pick'** indicates the highest-confidence player selection.")
        rows_sets = []
        for d in reversed(extracted_data):
            is_settled = d["is_settled"]
            # Check highest probability set winner
            fav_set_p = d["p1"] if d["p1_set_prob"] >= d["p2_set_prob"] else d["p2"]
            fav_set_prob = max(d["p1_set_prob"], d["p2_set_prob"])
            fav_set_took = d["p1_took_set"] if d["p1_set_prob"] >= d["p2_set_prob"] else d["p2_took_set"]
            icon = ("✅ Hit" if fav_set_took else "❌ Miss") if is_settled else "⏳ Pending"
            
            rows_sets.append({
                "Date": d["date"],
                "Circuit": d["circuit"],
                "Tournament": d["tourney"],
                "Player 1 (P1)": d["p1"],
                "Player 2 (P2)": d["p2"],
                "Format": d["format_str"],
                "P1 Win ≥1 Set (%)": f"{d['p1_set_prob']:.1f}%",
                "P1 Set Fair Odds": f"{d['p1_set_odds']:.2f}",
                "P2 Win ≥1 Set (%)": f"{d['p2_set_prob']:.1f}%",
                "P2 Set Fair Odds": f"{d['p2_set_odds']:.2f}",
                "Recommended Set Pick": f"{fav_set_p} ({fav_set_prob:.1f}%)",
                "P1 Actual Sets": d["p1_actual_sets"],
                "P2 Actual Sets": d["p2_actual_sets"],
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_sets), use_container_width=True, hide_index=True)

    # 3. TOTAL GAMES TAB
    with tab_games:
        st.markdown("#### 🎮 Total Match Games & Over/Under Line Accuracy")
        rows_games = []
        for d in reversed(extracted_data):
            is_settled = d["is_settled"]
            icon = ("✅ Hit" if d["correct_games_ou"] else "❌ Miss") if is_settled else "⏳ Pending"
            
            rows_games.append({
                "Date": d["date"],
                "Circuit": d["circuit"],
                "Tournament": d["tourney"],
                "Matchup": d["matchup"],
                "Format": d["format_str"],
                "Projected Total Games": f"{d['expected_games']:.1f}",
                "Main O/U Line": f"O/U {d['main_line']}",
                "Model Pick": d["model_games_pick"],
                "P(Over)": f"{d['main_line_over_prob']:.1f}%",
                "P(Under)": f"{d['main_line_under_prob']:.1f}%",
                "Actual Total Games": d["actual_games"],
                "Error": f"{d['game_error']} games" if d["game_error"] is not None else "-",
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_games), use_container_width=True, hide_index=True)

    # 4. EXACT SCORELINE TAB
    with tab_score:
        st.markdown("#### 🎯 Exact Set Scoreline Projections (2-0, 2-1, 3-0, 3-1, 3-2)")
        rows_score = []
        for d in reversed(extracted_data):
            is_settled = d["is_settled"]
            icon = ("🎯 Exact Hit" if d["correct_scoreline"] else "❌ Miss") if is_settled else "⏳ Pending"
            
            rows_score.append({
                "Date": d["date"],
                "Circuit": d["circuit"],
                "Tournament": d["tourney"],
                "Matchup": d["matchup"],
                "Format": d["format_str"],
                "Predicted Scoreline": d["top_scoreline"],
                "Scoreline Prob": f"{d['top_scoreline_prob']:.1f}%",
                "Actual Sets": d["actual_scoreline"],
                "Official Score": d["official_score"],
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_score), use_container_width=True, hide_index=True)

    # 5. DECIDING SET TAB
    with tab_decider:
        st.markdown("#### ⚡ Deciding Set Projections (Over 2.5 / Over 3.5 Sets)")
        rows_dec = []
        for d in reversed(extracted_data):
            is_settled = d["is_settled"]
            icon = ("✅ Hit" if d["correct_decider"] else "❌ Miss") if is_settled else "⏳ Pending"
            
            rows_dec.append({
                "Date": d["date"],
                "Circuit": d["circuit"],
                "Tournament": d["tourney"],
                "Matchup": d["matchup"],
                "Format": d["format_str"],
                "P(Deciding Set)": f"{d['prob_deciding_set']:.1f}%",
                "Model Pick": d["model_decider_pick"],
                "Went to Decider?": d["actual_went_decider"],
                "Official Score": d["official_score"],
                "Verification": icon,
            })
        st.dataframe(pd.DataFrame(rows_dec), use_container_width=True, hide_index=True)

    # 6. BETTING PERFORMANCE TAB
    with tab_betting:
        st.markdown("#### 💰 Betting Value & Kelly PnL Dashboard")
        summary = tracker.get_performance_summary()
        
        bk1, bk2, bk3, bk4 = st.columns(4)
        with bk1:
            st.metric("Total Value Bets", summary["total_bets"], f"Graded: {summary['total_graded']}")
        with bk2:
            st.metric("Value Bet Win Rate", f"{summary['bet_win_rate']}%", f"Won: {summary['bets_won']}/{summary['total_bets']}")
        with bk3:
            st.metric("Kelly Net PnL", f"${summary['total_pnl']:+,.2f}", f"Staked: ${summary['total_staked']:,.2f}")
        with bk4:
            st.metric("Realized ROI", f"{summary['roi']:+,.1f}%", f"Flat ROI: {summary['flat_roi']:+,.1f}%")

        st.divider()

        # Cumulative PnL Curve
        history_df = summary["history_df"]
        if not history_df.empty and "cum_pnl" in history_df.columns:
            st.subheader("📊 Cumulative Profit & Loss Evolution ($)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(range(1, len(history_df) + 1)),
                y=history_df["cum_pnl"],
                mode="lines+markers",
                name="Kelly Staking PnL ($)",
                line=dict(color="#22c55e", width=3),
                marker=dict(size=6)
            ))
            if "cum_flat_pnl" in history_df.columns:
                fig.add_trace(go.Scatter(
                    x=list(range(1, len(history_df) + 1)),
                    y=history_df["cum_flat_pnl"],
                    mode="lines",
                    name="Flat $20 Staking PnL ($)",
                    line=dict(color="#3b82f6", width=2, dash="dash")
                ))
            fig.update_layout(
                xaxis_title="Completed Bet Number",
                yaxis_title="Cumulative Profit / Loss ($)",
                margin=dict(t=20, b=20, l=20, r=20),
                height=320,
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader(f"📋 Graded Betting Archive ({len(tracker.predictions)} Total Matches)")
        if tracker.predictions:
            df_all = pd.DataFrame(tracker.predictions)
            display_cols = [
                c for c in ["date", "circuit", "tourney_name", "surface", "p1_name", "p2_name", "p1_prob", "p2_prob", "recommended_pick", "best_odds", "best_ev", "best_stake", "status", "actual_winner", "score", "pnl"]
                if c in df_all.columns
            ]
            st.dataframe(
                df_all[display_cols].sort_values(by="date", ascending=False),
                use_container_width=True,
                hide_index=True
            )
