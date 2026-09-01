"""Streamlit view for real-time upcoming tournament match predictions and betting signals."""
import logging
from datetime import date, datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import streamlit as st

from tennis_core.data.scraper import (
    load_upcoming_matches,
    save_upcoming_matches,
    fetch_live_upcoming_fixtures,
    filter_past_matches
)
from tennis_core.models.predictor import TennisPredictor
from tennis_core.betting.tracker import PredictionTracker
from tennis_core.utils.helpers import normalize_surface, odds_to_implied_prob, detect_match_format

logger = logging.getLogger(__name__)


def render_upcoming_view(predictor: TennisPredictor, tracker: PredictionTracker):
    """Render the Live Upcoming Match Predictions & Value Bets interface."""
    st.header("⚡ Live Upcoming Fixtures & Predictions")
    st.caption("Real-time tournament schedules, calibrated model predictions, player age, sets & games analytics, and Kelly staking suggestions.")

    # Refresh data controls
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([2, 2, 2])
    with col_ctrl1:
        if st.button("🔄 Sync Live Feed & Odds", use_container_width=True, type="primary"):
            with st.spinner("Querying live tournament schedules and market odds..."):
                try:
                    updated = fetch_live_upcoming_fixtures()
                    st.success(f"Synced {len(updated)} active tournament fixtures!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error syncing fixtures: {e}")

    # Load fixtures
    all_fixtures = load_upcoming_matches()
    # Filter out games from past days
    fixtures = filter_past_matches(all_fixtures)

    if not fixtures:
        st.info("No upcoming fixtures scheduled for today or future dates. Click 'Sync Live Feed & Odds' above or add a custom fixture below.")
        _render_add_fixture_form()
        return

    # Extract available unique dates
    available_dates = sorted(list(set(m.get("date", "Upcoming") for m in fixtures if m.get("date") and m.get("date") != "Upcoming")))

    # Filters Toolbar
    st.markdown("### 🔍 Filters & Sorting")
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)

    with f_col1:
        date_filter_options = ["All Dates"] + available_dates + ["📅 Custom Date Range..."]
        date_choice = st.selectbox("Match Date", date_filter_options, index=0)

    with f_col2:
        circuits = ["All Circuits", "ATP", "WTA"]
        circuit_filter = st.selectbox("Circuit Filter", circuits, index=0)

    with f_col3:
        surfaces = ["All Surfaces", "Hard", "Clay", "Grass"]
        surface_filter = st.selectbox("Surface Filter", surfaces, index=0)

    with f_col4:
        sort_by = st.selectbox(
            "Sort Matches By",
            ["Highest Expected Value (EV)", "Highest Model Confidence", "Chronological Date"],
            index=0
        )

    # Handle Custom Date Range
    custom_start_date = None
    custom_end_date = None
    if date_choice == "📅 Custom Date Range...":
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            custom_start_date = st.date_input("Start Date", value=date.today())
        with d_col2:
            custom_end_date = st.date_input("End Date", value=date.today())

    # Filter Fixtures
    filtered_fixtures = []
    for m in fixtures:
        m_date_str = m.get("date", "")
        
        # 1. Date filter
        if date_choice == "📅 Custom Date Range..." and custom_start_date and custom_end_date:
            try:
                m_dt = datetime.strptime(m_date_str, "%Y-%m-%d").date()
                if not (custom_start_date <= m_dt <= custom_end_date):
                    continue
            except Exception:
                continue
        elif date_choice != "All Dates" and date_choice != "📅 Custom Date Range...":
            if m_date_str != date_choice:
                continue

        # 2. Circuit filter
        if circuit_filter != "All Circuits" and m.get("circuit", "ATP") != circuit_filter:
            continue

        # 3. Surface filter
        if surface_filter != "All Surfaces" and m.get("surface", "Hard") != surface_filter:
            continue

        filtered_fixtures.append(m)

    if not filtered_fixtures:
        st.warning(f"No scheduled matches found matching your active filters (Date: `{date_choice}`, Circuit: `{circuit_filter}`, Surface: `{surface_filter}`).")
        return

    # Analyze & Predict Matches
    analyzed_matches = []
    with st.spinner(f"Analyzing {len(filtered_fixtures)} matches with ML & Game/Set dynamics..."):
        for m in filtered_fixtures:
            m_format = detect_match_format(m.get("tourney_name"), m.get("circuit", "ATP"))
            pred = predictor.predict_match(
                circuit=m.get("circuit", "ATP"),
                p1_name=m["p1_name"],
                p2_name=m["p2_name"],
                surface=m.get("surface", "Hard"),
                p1_odds=m.get("p1_odds"),
                p2_odds=m.get("p2_odds"),
                p1_rank=m.get("p1_rank"),
                p2_rank=m.get("p2_rank"),
                best_of=m_format,
                bankroll=st.session_state.get("bankroll", 1000.0),
            )
            analyzed_matches.append((m, pred))

    # Apply Sorting
    if "Highest Expected Value" in sort_by:
        analyzed_matches.sort(
            key=lambda item: (
                item[1]["betting"].get("best_ev") is not None,
                item[1]["betting"].get("best_ev") or -999.0
            ),
            reverse=True
        )
    elif "Highest Model Confidence" in sort_by:
        analyzed_matches.sort(key=lambda item: item[1]["confidence"], reverse=True)
    elif "Chronological" in sort_by:
        analyzed_matches.sort(key=lambda item: str(item[0].get("date", "9999")))

    # Collect all flat market picks for ranking
    all_market_picks_flat = []
    for m, pred in analyzed_matches:
        sg = pred.get("sets_games", {})
        p1 = pred["p1_name"]
        p2 = pred["p2_name"]
        main_l = sg.get("main_games_line", {})
        
        # 1. Match Winner
        all_market_picks_flat.append({
            "Match": f"{p1} vs {p2}",
            "Date": m.get("date", "-"),
            "Circuit": pred["circuit"],
            "Market": "Match Winner",
            "Selection": f"{pred['predicted_winner']} to Win",
            "Model Probability": max(pred["p1_prob"], pred["p2_prob"]) / 100.0,
            "Fair Odds": round(100.0 / max(pred["p1_prob"], pred["p2_prob"]), 2),
        })
        
        # 2. Sets To Win >= 1 Set
        if sg:
            top_set_p = p1 if sg["p1_win_at_least_1_set_prob"] >= sg["p2_win_at_least_1_set_prob"] else p2
            top_set_val = max(sg["p1_win_at_least_1_set_prob"], sg["p2_win_at_least_1_set_prob"])
            all_market_picks_flat.append({
                "Match": f"{p1} vs {p2}",
                "Date": m.get("date", "-"),
                "Circuit": pred["circuit"],
                "Market": "Set Scoring",
                "Selection": f"{top_set_p} to Win ≥1 Set",
                "Model Probability": top_set_val / 100.0,
                "Fair Odds": round(100.0 / max(0.1, top_set_val), 2),
            })
            
            # 3. Total Games
            if main_l:
                best_ou = "Over" if main_l.get("prob_over", 50) >= main_l.get("prob_under", 50) else "Under"
                best_ou_p = max(main_l.get("prob_over", 50), main_l.get("prob_under", 50))
                all_market_picks_flat.append({
                    "Match": f"{p1} vs {p2}",
                    "Date": m.get("date", "-"),
                    "Circuit": pred["circuit"],
                    "Market": "Total Games",
                    "Selection": f"{best_ou} {main_l.get('line')} Games",
                    "Model Probability": best_ou_p / 100.0,
                    "Fair Odds": round(100.0 / max(0.1, best_ou_p), 2),
                })

    # Always automatically track all analyzed matches in the verification tracker
    if analyzed_matches:
        for m, p in analyzed_matches:
            betting = p["betting"]
            tracker_payload = {
                "match_id": m.get("match_id"),
                "circuit": p["circuit"],
                "tourney_name": m.get("tourney_name"),
                "surface": p["surface"],
                "date": m.get("date"),
                "round": m.get("round"),
                "p1_name": p["p1_name"],
                "p2_name": p["p2_name"],
                "p1_prob": p["p1_prob"],
                "p2_prob": p["p2_prob"],
                "p1_odds": betting.get("p1_odds"),
                "p2_odds": betting.get("p2_odds"),
                "recommended_pick": betting.get("recommended_pick") or p["predicted_winner"],
                "best_ev": betting.get("best_ev"),
                "best_edge": betting.get("best_edge"),
                "best_stake": betting.get("best_stake"),
                "best_odds": betting.get("best_odds"),
            }
            tracker.log_prediction(tracker_payload)

    # Summary Metrics Toolbar
    val_count = sum(1 for m, p in analyzed_matches if p["betting"].get("has_value"))
    avg_exp_games = float(np.mean([p.get("sets_games", {}).get("expected_total_games", 22.0) for m, p in analyzed_matches])) if analyzed_matches else 0.0

    st.markdown("---")
    m1, m2, m3, m4 = st.columns([2, 2, 2, 2.5])
    m1.metric("Scheduled Matches", len(analyzed_matches))
    m2.metric("Value Bet Edges", val_count)
    m3.metric("Avg Projected Games", f"{avg_exp_games:.1f} games")
    with m4:
        st.write("")
        st.caption(f"⚡ **{len(analyzed_matches)} Matches Tracked** (Auto-Logged)")

    # Global Highest Confidence Selections Table
    if all_market_picks_flat:
        with st.expander("💎 Top Highest Confidence Picks Across All Categories (Ranked by Probability)", expanded=False):
            df_top_picks = pd.DataFrame(all_market_picks_flat).sort_values(by="Model Probability", ascending=False).head(15).reset_index(drop=True)
            df_top_picks["Prob (%)"] = (df_top_picks["Model Probability"] * 100).round(1).astype(str) + "%"
            df_top_picks.index = df_top_picks.index + 1
            st.dataframe(
                df_top_picks[["Match", "Date", "Circuit", "Market", "Selection", "Prob (%)", "Fair Odds"]],
                use_container_width=True
            )

    st.markdown("---")
    st.subheader(f"Scheduled Fixtures ({len(analyzed_matches)} Matches · Filter: `{date_choice}`)")

    # Render Match Cards
    for m, pred in analyzed_matches:
        betting = pred["betting"]
        ctx = pred["context"]
        has_odds = betting.get("has_odds", False)
        has_val = has_odds and betting.get("has_value", False)
        match_best_of = pred.get("sets_games", {}).get("best_of", 3)
        format_badge = "🏆 Best of 5 Sets (Grand Slam)" if match_best_of == 5 else "🎾 Best of 3 Sets"
        
        with st.container(border=True):
            header_col1, header_col2, header_col3 = st.columns([4, 2, 2])
            with header_col1:
                circuit_badge = "🔵 ATP" if pred["circuit"] == "ATP" else "🟣 WTA"
                surf_color = "🟢" if pred["surface"] == "Grass" else ("🟠" if pred["surface"] == "Clay" else "🔵")
                st.markdown(f"### {circuit_badge} | {m.get('tourney_name', 'Tourney')} - `{m.get('round', 'Match')}`")
                st.caption(f"🗓️ Date: **{m.get('date', 'Upcoming')}** | {surf_color} Surface: **{pred['surface']}** | ⚖️ **{format_badge}** | 🎯 Model Pick: **{pred['predicted_winner']}** ({pred['confidence']}%)")
            
            with header_col2:
                if has_val:
                    st.success(f"🔥 **VALUE: +{betting['best_ev']}% EV**\n\nPick: **{betting['recommended_pick']}** @ {betting['best_odds']}")
                elif not has_odds:
                    st.info(f"⚡ **No bookmaker odds yet**\n\nModel pick: **{pred['predicted_winner']}** ({pred['confidence']}%)")
                else:
                    st.info(f"⚖️ Fair Market Price\n\nPick: **{pred['predicted_winner']}** ({pred['confidence']}%)")
            
            with header_col3:
                if has_odds:
                    if st.button("📝 Log Bet", key=f"log_{m.get('match_id', pred['p1_name']+'_'+pred['p2_name'])}"):
                        tracker_payload = {
                            "match_id": m.get("match_id"),
                            "circuit": pred["circuit"],
                            "tourney_name": m.get("tourney_name"),
                            "surface": pred["surface"],
                            "date": m.get("date"),
                            "round": m.get("round"),
                            "p1_name": pred["p1_name"],
                            "p2_name": pred["p2_name"],
                            "p1_prob": pred["p1_prob"],
                            "p2_prob": pred["p2_prob"],
                            "p1_odds": betting["p1_odds"],
                            "p2_odds": betting["p2_odds"],
                            "recommended_pick": betting["recommended_pick"] or pred["predicted_winner"],
                            "best_ev": betting["best_ev"],
                            "best_edge": betting["best_edge"],
                            "best_stake": betting["best_stake"],
                            "best_odds": betting["best_odds"],
                        }
                        tracker.log_prediction(tracker_payload)
                        st.toast(f"Bet logged for {pred['p1_name']} vs {pred['p2_name']}!")

            st.divider()

            # Player comparison columns
            p1_col, gauge_col, p2_col = st.columns([3, 4, 3])
            
            with p1_col:
                p1_age_str = f" · 🎂 Age: `{ctx.get('p1_age')}`" if ctx.get("p1_age") != "N/A" else ""
                st.markdown(f"#### {pred['p1_name']}{p1_age_str}")
                p1_r = f"#{ctx['p1_rank']}" if isinstance(ctx.get('p1_rank'), int) else str(ctx.get('p1_rank', 'Unranked'))
                p1_ch = f"#{ctx['p1_career_high']}" if isinstance(ctx.get('p1_career_high'), int) else str(ctx.get('p1_career_high', 'N/A'))
                st.write(f"🏆 Rank: `{p1_r}`  |  Career High: `{p1_ch}`")
                st.write(f"📈 Overall Elo: **{ctx['p1_elo']}** | {pred['surface']} Elo: **{ctx['p1_surface_elo']}**")
                
                # Games & Sets & Serve/Return Stats
                if ctx.get("p1_sets_win_rate") != "N/A":
                    st.write(f"🚀 **Hold %**: `{ctx.get('p1_surface_hold_pct')}%` | 🎯 **Break %**: `{ctx.get('p1_surface_break_pct')}%`")
                    st.write(f"🎾 **Sets Won (L10)**: `{ctx['p1_sets_win_rate']}%` | 🎮 **Games Won**: `{ctx['p1_games_win_rate']}%`")
                else:
                    st.write("🔥 Form: _No tour matches in DB_")
                    
                st.metric("Model Win Probability", f"{pred['p1_prob']}%", f"Market: {betting['raw_implied_p1']}%" if has_odds else None)
                if has_odds:
                    st.write(f"Bookmaker Odds: **{betting['p1_odds']}** (Model Fair: `{betting['fair_model_odds_p1']}`)")
                else:
                    st.caption("📉 No odds available")

            with gauge_col:
                st.write(" ")
                st.write(" ")
                st.markdown("<p style='text-align: center; font-weight: bold;'>MODEL WIN PROBABILITY</p>", unsafe_allow_html=True)
                st.progress(pred["p1_prob"] / 100.0)
                st.caption(f"<div style='display:flex; justify-content:space-between;'><span>{pred['p1_name']}: {pred['p1_prob']}%</span><span>{pred['p2_name']}: {pred['p2_prob']}%</span></div>", unsafe_allow_html=True)
                
                if has_val:
                    st.markdown(
                        f"""
                        <div style='background-color: rgba(34, 197, 94, 0.15); border-left: 4px solid #22c55e; padding: 10px; border-radius: 6px; margin-top: 15px;'>
                            <b>💡 Kelly Staking Suggestion:</b><br/>
                            Bet <b>${betting['best_stake']}</b> ({betting['p1_kelly_pct'] if betting['recommended_pick']==pred['p1_name'] else betting['p2_kelly_pct']}% bankroll) on <b>{betting['recommended_pick']}</b>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                elif has_odds:
                    st.markdown(
                        f"""
                        <div style='background-color: rgba(148, 163, 184, 0.1); border-left: 4px solid #94a3b8; padding: 10px; border-radius: 6px; margin-top: 15px;'>
                            📊 Vig: <b>{betting['bookmaker_vig_pct']}%</b> · Market is efficiently priced.
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        """
                        <div style='background-color: rgba(234, 179, 8, 0.1); border-left: 4px solid #eab308; padding: 10px; border-radius: 6px; margin-top: 15px;'>
                            📭 Prediction based on Elo, Serve/Return & Sets/Games. Add odds below for EV analysis.
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            with p2_col:
                p2_age_str = f" · 🎂 Age: `{ctx.get('p2_age')}`" if ctx.get("p2_age") != "N/A" else ""
                st.markdown(f"#### {pred['p2_name']}{p2_age_str}")
                p2_r = f"#{ctx['p2_rank']}" if isinstance(ctx.get('p2_rank'), int) else str(ctx.get('p2_rank', 'Unranked'))
                p2_ch = f"#{ctx['p2_career_high']}" if isinstance(ctx.get('p2_career_high'), int) else str(ctx.get('p2_career_high', 'N/A'))
                st.write(f"🏆 Rank: `{p2_r}`  |  Career High: `{p2_ch}`")
                st.write(f"📈 Overall Elo: **{ctx['p2_elo']}** | {pred['surface']} Elo: **{ctx['p2_surface_elo']}**")
                
                # Games & Sets & Serve/Return Stats
                if ctx.get("p2_sets_win_rate") != "N/A":
                    st.write(f"🚀 **Hold %**: `{ctx.get('p2_surface_hold_pct')}%` | 🎯 **Break %**: `{ctx.get('p2_surface_break_pct')}%`")
                    st.write(f"🎾 **Sets Won (L10)**: `{ctx['p2_sets_win_rate']}%` | 🎮 **Games Won**: `{ctx['p2_games_win_rate']}%`")
                else:
                    st.write("🔥 Form: _No tour matches in DB_")
                    
                st.metric("Model Win Probability", f"{pred['p2_prob']}%", f"Market: {betting['raw_implied_p2']}%" if has_odds else None)
                if has_odds:
                    st.write(f"Bookmaker Odds: **{betting['p2_odds']}** (Model Fair: `{betting['fair_model_odds_p2']}`)")
                else:
                    st.caption("📉 No odds available")

            # Sets & Total Games Analytics Banner
            sg = pred.get("sets_games", {})
            if sg:
                main_line = sg.get("main_games_line", {})
                line_val = main_line.get("line", 21.5)
                
                st.markdown(
                    f"""
                    <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-top: 10px; margin-bottom: 10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
                            <div>
                                <span style="color:#94a3b8; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.5px;">🎾 <b>To Win at Least 1 Set</b></span><br/>
                                <span style="font-size:0.95rem;"><b>{pred['p1_name']}</b>: <span style="color:#38bdf8; font-weight:bold;">{sg['p1_win_at_least_1_set_prob']}%</span> (Fair: `{sg['p1_win_at_least_1_set_odds']}`) &nbsp;•&nbsp; <b>{pred['p2_name']}</b>: <span style="color:#f59e0b; font-weight:bold;">{sg['p2_win_at_least_1_set_prob']}%</span> (Fair: `{sg['p2_win_at_least_1_set_odds']}`)</span>
                            </div>
                            <div>
                                <span style="color:#94a3b8; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.5px;">🎮 <b>Total Games Line</b> (Exp: <b>{sg['expected_total_games']}</b>)</span><br/>
                                <span style="font-size:0.95rem;">Line <b>O/U {line_val}</b>: <b>Over</b> <span style="color:#10b981; font-weight:bold;">{main_line.get('prob_over', 50)}%</span> (Fair: `{main_line.get('fair_odds_over', 2.0)}`) &nbsp;•&nbsp; <b>Under</b> <span style="color:#ef4444; font-weight:bold;">{main_line.get('prob_under', 50)}%</span> (Fair: `{main_line.get('fair_odds_under', 2.0)}`)</span>
                            </div>
                            <div>
                                <span style="color:#94a3b8; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.5px;">⚡ <b>Deciding Set</b></span><br/>
                                <span style="font-size:0.95rem;"><b>{sg.get('prob_deciding_set')}%</b> (Fair: `{sg.get('fair_odds_deciding_set')}`)</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # Recent Match History & Prediction Factors Expander
            with st.expander("📊 Sets & Games Markets, Serve/Return & Factor Analysis", expanded=False):
                # Total Games Over/Under Line Table & Set Scorelines
                if sg:
                    st.markdown("##### 🎾 Sets Scoring & Total Games Probability Markets")
                    sg_tab1, sg_tab2 = st.tabs(["🎮 Total Games (Over/Under Lines)", "🎯 Set Scorelines Breakdown"])
                    
                    with sg_tab1:
                        st.caption(f"Expected match total games: **{sg['expected_total_games']} games**. Evaluated across standard bookmaker handicap lines.")
                        df_lines = pd.DataFrame(sg.get("games_market_table", []))
                        if not df_lines.empty:
                            st.dataframe(
                                df_lines[["Line", "P(Over) %", "Fair Odds (Over)", "P(Under) %", "Fair Odds (Under)"]],
                                use_container_width=True,
                                hide_index=True
                            )
                            
                    with sg_tab2:
                        sc_cols = st.columns(len(sg.get("scoreline_probabilities", {})))
                        for idx, (sc_name, sc_prob) in enumerate(sg.get("scoreline_probabilities", {}).items()):
                            with sc_cols[idx]:
                                st.metric(sc_name, f"{sc_prob*100:.1f}%", f"Fair: {round(1.0/max(0.01, sc_prob), 2)}")

                st.divider()
                # Serve & Return Matchup Projection
                st.markdown("##### 🚀 Serve & Return Matchup Breakdown")
                sr_col1, sr_col2, sr_col3, sr_col4 = st.columns(4)
                with sr_col1:
                    st.metric(f"{pred['p1_name']} Projected Hold", f"{ctx.get('projected_p1_hold_rate')}%")
                with sr_col2:
                    st.metric(f"{pred['p1_name']} Projected Break", f"{ctx.get('projected_p1_break_rate')}%")
                with sr_col3:
                    st.metric(f"{pred['p2_name']} Projected Hold", f"{ctx.get('projected_p2_hold_rate')}%")
                with sr_col4:
                    st.metric(f"{pred['p2_name']} Projected Break", f"{ctx.get('projected_p2_break_rate')}%")

                st.divider()
                # Games & Sets Breakdown Table
                st.markdown("##### 🎾 Games & Sets Performance Breakdown")
                gs_col1, gs_col2, gs_col3, gs_col4 = st.columns(4)
                with gs_col1:
                    st.metric("Sets Won % (L10)", f"{ctx.get('p1_sets_win_rate')}%", delta=f"{round(ctx.get('p1_sets_win_rate', 50) - ctx.get('p2_sets_win_rate', 50), 1)}% vs P2" if isinstance(ctx.get('p1_sets_win_rate'), (int, float)) and isinstance(ctx.get('p2_sets_win_rate'), (int, float)) else None)
                with gs_col2:
                    st.metric("Games Won % (L10)", f"{ctx.get('p1_games_win_rate')}%", delta=f"{round(ctx.get('p1_games_win_rate', 50) - ctx.get('p2_games_win_rate', 50), 1)}% vs P2" if isinstance(ctx.get('p1_games_win_rate'), (int, float)) and isinstance(ctx.get('p2_games_win_rate'), (int, float)) else None)
                with gs_col3:
                    st.metric("Deciding Set Win %", f"{ctx.get('p1_deciding_set_win_rate')}%" if ctx.get('p1_deciding_set_win_rate') != "N/A" else "N/A")
                with gs_col4:
                    st.metric("Dominance Ratio (W/L)", f"{ctx.get('p1_dominance_ratio')}x" if ctx.get('p1_dominance_ratio') != "N/A" else "N/A")

                st.divider()
                hist_col1, hist_col2 = st.columns(2)
                
                with hist_col1:
                    st.markdown(f"**Recent Matches for {pred['p1_name']}:**")
                    p1_matches = ctx.get("p1_recent_matches", [])
                    if p1_matches:
                        p1_df = pd.DataFrame(p1_matches)
                        p1_df["Outcome"] = p1_df["won"].apply(lambda w: "✅ W" if w else "❌ L")
                        display_cols = ["date", "Outcome", "opponent", "score", "sets", "games", "surface", "tourney"]
                        st.dataframe(p1_df[[c for c in display_cols if c in p1_df.columns]], width="stretch", hide_index=True)
                    else:
                        st.caption("No recent matches found in historical database.")

                with hist_col2:
                    st.markdown(f"**Recent Matches for {pred['p2_name']}:**")
                    p2_matches = ctx.get("p2_recent_matches", [])
                    if p2_matches:
                        p2_df = pd.DataFrame(p2_matches)
                        p2_df["Outcome"] = p2_df["won"].apply(lambda w: "✅ W" if w else "❌ L")
                        display_cols = ["date", "Outcome", "opponent", "score", "sets", "games", "surface", "tourney"]
                        st.dataframe(p2_df[[c for c in display_cols if c in p2_df.columns]], width="stretch", hide_index=True)
                    else:
                        st.caption("No recent matches found in historical database.")

                st.divider()
                st.markdown("**Key Prediction Factors:**")
                factors = pred.get("factors", [])
                if factors:
                    factor_cols = st.columns(len(factors))
                    for idx, factor in enumerate(factors):
                        with factor_cols[idx]:
                            st.markdown(f"**{factor['title']}**")
                            st.write(f"Favors **{factor['favors']}** (`{factor['impact']}` impact)")
                            st.caption(factor["detail"])
                
                st.caption(f"📊 Head-to-Head Record: **{ctx['h2h_p1_wins']} - {ctx['h2h_p2_wins']}** (Sets: `{ctx.get('h2h_p1_sets', 0)}-{ctx.get('h2h_p2_sets', 0)}`, Games: `{ctx.get('h2h_p1_games', 0)}-{ctx.get('h2h_p2_games', 0)}`) across {ctx['h2h_total']} career meetings")

    # Add Custom Match Form at bottom
    _render_add_fixture_form()


def _render_add_fixture_form():
    """Render manual matchup submission form."""
    with st.expander("➕ Add Custom Match / Upcoming Fixture", expanded=False):
        st.markdown("Create a customized fixture to evaluate model win probabilities and Kelly staking.")
        with st.form("custom_match_form", clear_on_submit=True):
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                circuit = st.selectbox("Circuit", ["ATP", "WTA"], index=0)
                p1 = st.text_input("Player 1 Name", placeholder="e.g. Carlos Alcaraz")
                p1_odds = st.number_input("Player 1 Decimal Odds", min_value=1.01, max_value=50.0, value=1.75, step=0.05)
            with f_col2:
                surface = st.selectbox("Surface", ["Hard", "Clay", "Grass"], index=0)
                p2 = st.text_input("Player 2 Name", placeholder="e.g. Jannik Sinner")
                p2_odds = st.number_input("Player 2 Decimal Odds", min_value=1.01, max_value=50.0, value=2.15, step=0.05)
            with f_col3:
                tourney = st.text_input("Tournament", value="US Open")
                match_round = st.selectbox("Round", ["Main Draw", "Round 1", "Round 2", "Quarterfinal", "Semifinal", "The Final"], index=0)
                match_date = st.date_input("Match Date", value=date.today())

            submit_btn = st.form_submit_button("Save & Predict Matchup", use_container_width=True, type="primary")
            if submit_btn:
                if not p1 or not p2:
                    st.error("Please enter both player names.")
                else:
                    new_item = {
                        "match_id": f"custom_{int(datetime.now().timestamp())}",
                        "circuit": circuit,
                        "tourney_name": tourney,
                        "surface": surface,
                        "round": match_round,
                        "date": str(match_date),
                        "p1_name": p1,
                        "p2_name": p2,
                        "p1_odds": float(p1_odds),
                        "p2_odds": float(p2_odds),
                    }
                    existing = load_upcoming_matches()
                    existing.append(new_item)
                    save_upcoming_matches(existing)
                    st.success(f"Added matchup: {p1} vs {p2}!")
                    st.rerun()
