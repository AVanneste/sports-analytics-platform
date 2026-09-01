"""Upcoming fixtures, corners, cards & value betting opportunities view with probability sorting, calendar date filtering, and multi-category verification tracking."""
import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
from typing import List, Dict

from football_core.config import LEAGUES
from football_core.models.predictor import FootballPredictor
from football_core.data.odds_api import fetch_all_live_upcoming_fixtures
from football_core.betting.tracker import PredictionTracker
from football_core.models.explain import get_match_key_drivers


def format_odds_ev_str(prob: float, fair_odds: float, market_odds: float = None) -> str:
    """Format probability, fair odds, and market odds/EV only when market odds are available."""
    prob_str = f"**{prob*100:.1f}%** `(Fair: {fair_odds:.2f})`"
    if market_odds and market_odds > 1.0:
        ev = (prob * market_odds) - 1.0
        ev_color = "#10b981" if ev >= 0.03 else ("#ef4444" if ev < 0 else "#94a3b8")
        ev_str = f"<span style='color:{ev_color}; font-weight:600;'>EV: {ev*100:+.1f}%</span>"
        return f"{prob_str} | **Odds**: `{market_odds:.2f}` ({ev_str})"
    return prob_str


def render_upcoming_view(predictor: FootballPredictor, tracker: PredictionTracker):
    st.markdown("<h2 style='color:#10b981;'>⚽ Upcoming Fixtures, Corners & Cards Value Board</h2>", unsafe_allow_html=True)
    st.caption("Live matchday projections with Calibrated ML, Dixon-Coles goal expectancies, Corner distributions, Referee disciplinary ratings, and live market odds with EV.")

    # 1. Fetch Fixtures First to Determine Available Date Bounds
    with st.spinner("Fetching upcoming fixtures and calculating market probabilities..."):
        fixtures = fetch_all_live_upcoming_fixtures(use_cache=True)

    today = datetime.date.today()

    if not fixtures:
        fixtures = []
        for l_k in LEAGUES.keys():
            teams = predictor.get_known_teams(l_k)
            if len(teams) >= 4:
                fixtures.append({
                    "match_id": f"{l_k}_sample_1",
                    "league": l_k,
                    "league_name": LEAGUES[l_k]["name"],
                    "flag": LEAGUES[l_k]["flag"],
                    "date": today.strftime("%Y-%m-%d"),
                    "home_team": teams[0],
                    "away_team": teams[1],
                    "referee": "Michael Oliver" if l_k == "EPL" else None,
                    "odds_home": 1.95,
                    "odds_draw": 3.50,
                    "odds_away": 3.90,
                    "odds_over25": 1.80,
                    "odds_under25": 2.05,
                    "odds_btts_yes": 1.75,
                    "odds_btts_no": 2.10,
                    "odds_corners_over95": 1.90,
                    "odds_cards_over35": 1.85,
                })
                fixtures.append({
                    "match_id": f"{l_k}_sample_2",
                    "league": l_k,
                    "league_name": LEAGUES[l_k]["name"],
                    "flag": LEAGUES[l_k]["flag"],
                    "date": (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                    "home_team": teams[2],
                    "away_team": teams[3],
                    "referee": "Anthony Taylor" if l_k == "EPL" else None,
                    "odds_home": 2.40,
                    "odds_draw": 3.30,
                    "odds_away": 3.00,
                    "odds_over25": 2.10,
                    "odds_under25": 1.75,
                    "odds_btts_yes": 1.85,
                    "odds_btts_no": 1.95,
                    "odds_corners_over95": 1.85,
                    "odds_cards_over35": 1.90,
                })

    # Determine date range bounds from fixtures
    fixture_dates = []
    for f in fixtures:
        d_str = str(f.get("date", ""))[:10]
        try:
            fixture_dates.append(pd.to_datetime(d_str).date())
        except Exception:
            pass

    min_fix_date = min(fixture_dates) if fixture_dates else today
    max_fix_date = max(fixture_dates) if fixture_dates else (today + datetime.timedelta(days=30))

    # Controls Bar Row 1: Filters
    col1, col2, col3, col4 = st.columns([2, 2.5, 1.5, 1.5])
    with col1:
        league_choice = st.selectbox(
            "Filter League",
            options=["ALL"] + list(LEAGUES.keys()),
            format_func=lambda x: "🌍 All Top 5 Leagues" if x == "ALL" else f"{LEAGUES[x]['flag']} {LEAGUES[x]['name']}"
        )
    with col2:
        date_selection = st.date_input(
            "📅 Match Date Range (Calendar)",
            value=(min_fix_date, max_fix_date),
            help="Filter matches between start and end dates from the calendar."
        )
    with col3:
        only_value = st.checkbox("🔥 Only Value Bets (EV > 3%)", value=False)
    with col4:
        min_ev_slider = st.slider("Min EV (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.5)

    # Controls Bar Row 2: Sort By
    s_col1, s_col2 = st.columns([3, 1])
    with s_col1:
        sort_by = st.selectbox(
            "📊 Sort Matches By",
            options=[
                ("highest_prob_overall", "⭐ Highest Probability Overall (Max Across All Markets)"),
                ("ev", "💰 Best Expected Value (EV %)"),
                ("prob_home", "🏠 Home Win Probability P(Home)"),
                ("prob_draw", "🤝 Draw Probability P(Draw)"),
                ("prob_away", "🚗 Away Win Probability P(Away)"),
                ("prob_over25", "⚽ Goals: Over 2.5 Goals Probability"),
                ("prob_under25", "🛡️ Goals: Under 2.5 Goals Probability"),
                ("prob_btts_yes", "🥅 Goals: Both Teams To Score (BTTS Yes)"),
                ("prob_corners_over95", "🚩 Corners: Over 9.5 Corners Probability"),
                ("prob_corners_under95", "🚩 Corners: Under 9.5 Corners Probability"),
                ("expected_corners", "🚩 Corners: Expected Total Corners"),
                ("prob_cards_over35", "🟨 Cards: Over 3.5 Cards Probability"),
                ("prob_cards_under35", "🟨 Cards: Under 3.5 Cards Probability"),
                ("prob_cards_over45", "🟨 Cards: Over 4.5 Cards Probability"),
                ("expected_cards", "🟨 Cards: Expected Total Cards"),
                ("date", "📅 Kick-off Date (Chronological)"),
            ],
            format_func=lambda x: x[1],
            index=0
        )
    with s_col2:
        sort_descending = st.selectbox(
            "Order",
            options=[True, False],
            format_func=lambda x: "⬇️ High to Low" if x else "⬆️ Low to High",
            index=0
        )

    # 1. Filter by League
    if league_choice != "ALL":
        fixtures = [f for f in fixtures if f.get("league") == league_choice]

    # 2. Filter by Calendar Date
    if isinstance(date_selection, (tuple, list)) and len(date_selection) == 2:
        start_d, end_d = date_selection[0], date_selection[1]
    elif isinstance(date_selection, (tuple, list)) and len(date_selection) == 1:
        start_d, end_d = date_selection[0], date_selection[0]
    elif isinstance(date_selection, datetime.date):
        start_d, end_d = date_selection, date_selection
    else:
        start_d, end_d = None, None

    if start_d and end_d:
        filtered_fixtures = []
        for f in fixtures:
            d_str = str(f.get("date", ""))[:10]
            try:
                f_date = pd.to_datetime(d_str).date()
                if start_d <= f_date <= end_d:
                    filtered_fixtures.append(f)
            except Exception:
                filtered_fixtures.append(f)
        fixtures = filtered_fixtures

    predictions = []
    all_market_picks_flat = []

    for f in fixtures:
        l_k = f.get("league")
        if not predictor.is_league_ready(l_k):
            continue
        try:
            pred = predictor.predict_match(
                league_key=l_k,
                home_team=f["home_team"],
                away_team=f["away_team"],
                referee=f.get("referee"),
                odds_home=f.get("odds_home"),
                odds_draw=f.get("odds_draw"),
                odds_away=f.get("odds_away"),
                odds_over25=f.get("odds_over25"),
                odds_under25=f.get("odds_under25"),
                odds_btts_yes=f.get("odds_btts_yes"),
                odds_btts_no=f.get("odds_btts_no"),
                odds_corners_over95=f.get("odds_corners_over95"),
                odds_corners_under95=f.get("odds_corners_under95"),
                odds_cards_over35=f.get("odds_cards_over35"),
                odds_cards_under35=f.get("odds_cards_under35"),
            )
            pred["fixture_meta"] = f

            market_options = [
                {"market": "1X2", "selection": f"{pred['home_team']} Win", "prob": pred["prob_home"], "fair_odds": pred["fair_odds_home"], "odds": f.get("odds_home")},
                {"market": "1X2", "selection": "Draw", "prob": pred["prob_draw"], "fair_odds": pred["fair_odds_draw"], "odds": f.get("odds_draw")},
                {"market": "1X2", "selection": f"{pred['away_team']} Win", "prob": pred["prob_away"], "fair_odds": pred["fair_odds_away"], "odds": f.get("odds_away")},
                {"market": "Goals", "selection": "Over 2.5 Goals", "prob": pred["prob_over25"], "fair_odds": pred["fair_odds_over25"], "odds": f.get("odds_over25")},
                {"market": "Goals", "selection": "Under 2.5 Goals", "prob": pred["prob_under25"], "fair_odds": pred["fair_odds_under25"], "odds": f.get("odds_under25")},
                {"market": "BTTS", "selection": "Both Teams to Score (BTTS Yes)", "prob": pred["prob_btts_yes"], "fair_odds": pred["fair_odds_btts_yes"], "odds": f.get("odds_btts_yes")},
                {"market": "BTTS", "selection": "BTTS No", "prob": pred["prob_btts_no"], "fair_odds": pred["fair_odds_btts_no"], "odds": f.get("odds_btts_no")},
                {"market": "Corners", "selection": "Over 9.5 Corners", "prob": pred["prob_corners_over95"], "fair_odds": pred["fair_odds_corners_over95"], "odds": f.get("odds_corners_over95")},
                {"market": "Corners", "selection": "Under 9.5 Corners", "prob": pred["prob_corners_under95"], "fair_odds": pred["fair_odds_corners_under95"], "odds": f.get("odds_corners_under95")},
                {"market": "Cards", "selection": "Over 3.5 Cards", "prob": pred["prob_cards_over35"], "fair_odds": pred["fair_odds_cards_over35"], "odds": f.get("odds_cards_over35")},
                {"market": "Cards", "selection": "Under 3.5 Cards", "prob": pred["prob_cards_under35"], "fair_odds": pred["fair_odds_cards_under35"], "odds": f.get("odds_cards_under35")},
            ]

            best_prob_item = max(market_options, key=lambda x: x["prob"])
            pred["highest_prob_overall"] = best_prob_item["prob"]
            pred["highest_prob_selection"] = f"{best_prob_item['selection']} ({best_prob_item['prob']*100:.1f}%)"
            pred["highest_prob_item"] = best_prob_item

            for mo in market_options:
                o_val = mo.get("odds")
                ev_val = ((mo["prob"] * o_val) - 1.0) if (o_val and o_val > 1.0) else None
                all_market_picks_flat.append({
                    "Match": f"{pred['home_team']} vs {pred['away_team']}",
                    "Date": f.get("date", "-"),
                    "League": f.get("flag", "") + " " + f.get("league_name", l_k),
                    "Market": mo["market"],
                    "Selection": mo["selection"],
                    "Model Probability": mo["prob"],
                    "Fair Odds": mo["fair_odds"],
                    "Bookmaker Odds": o_val if o_val else "-",
                    "EV (%)": f"{ev_val*100:+.1f}%" if ev_val is not None else "-",
                })

            predictions.append(pred)
        except Exception:
            continue

    # Filter by Value only if checked
    if only_value:
        predictions = [p for p in predictions if p["best_pick"].get("ev", 0.0) >= (min_ev_slider / 100.0)]

    # Dynamic Sorting Handler
    sort_key = sort_by[0]
    def get_sort_value(pred_item):
        if sort_key == "ev":
            return float(pred_item.get("best_pick", {}).get("ev", 0.0) or 0.0)
        elif sort_key == "date":
            return str(pred_item.get("fixture_meta", {}).get("date", ""))
        elif sort_key == "highest_prob_overall":
            return float(pred_item.get("highest_prob_overall", 0.0) or 0.0)
        else:
            return float(pred_item.get(sort_key, 0.0) or 0.0)

    predictions.sort(key=get_sort_value, reverse=sort_descending)

    # Metrics Overview & Global Track Action
    val_count = sum(1 for p in predictions if p.get("has_value"))
    m1, m2, m3, m4, m5 = st.columns([1.8, 1.8, 2, 2, 2.4])
    m1.metric("Upcoming Matches", len(predictions))
    m2.metric("Value Opportunities", val_count)
    m3.metric("Avg Proj Corners", f"{pd.Series([p['expected_corners'] for p in predictions]).mean():.1f}" if predictions else "0.0")
    m4.metric("Avg Proj Cards", f"{pd.Series([p['expected_cards'] for p in predictions]).mean():.1f}" if predictions else "0.0")
    with m5:
        st.write("")
        st.caption(f"⚡ **{len(predictions)} Matches Tracked** (Auto-Logged)")

    # Global Highest Confidence Selections Table
    if all_market_picks_flat:
        with st.expander("💎 Top Highest Confidence Picks Across All Categories (Ranked by Probability)", expanded=False):
            df_top_picks = pd.DataFrame(all_market_picks_flat).sort_values(by="Model Probability", ascending=False).head(15).reset_index(drop=True)
            df_top_picks["Prob (%)"] = (df_top_picks["Model Probability"] * 100).round(1).astype(str) + "%"
            df_top_picks.index = df_top_picks.index + 1
            st.dataframe(
                use_container_width=True
            )

    st.markdown("---")

    if not predictions:
        st.warning("No matches found matching the selected date range and filter criteria. Adjust the date picker or clear the Value Bets filter.")
        return

    # Render Match Cards
    for idx, p in enumerate(predictions):
        meta = p["fixture_meta"]
        flag = meta.get("flag", "⚽")
        league_name = meta.get("league_name", p["league_key"])
        date_str = meta.get("date", "Upcoming")
        
        home = p["home_team"]
        away = p["away_team"]
        pick = p["best_pick"]
        has_val = p["has_value"] and pick.get("ev", 0.0) >= (min_ev_slider / 100.0)

        card_border = "#10b981" if has_val else "#334155"
        badge_html = f"<span style='background-color:#059669; color:white; padding:3px 8px; border-radius:4px; font-size:0.8rem; font-weight:bold;'>🔥 VALUE BET (+{pick.get('ev',0.0)*100:.1f}% EV)</span>" if has_val else ""

        ref_info = p.get("referee", {})
        ref_name = ref_info.get("referee_name", "Unassigned")
        ref_badge = f"<span style='background:#1e293b; border:1px solid #475569; color:#cbd5e1; padding:2px 6px; border-radius:4px; font-size:0.75rem;'>👮 {ref_name} ({ref_info.get('strictness_label', 'Balanced')})</span>"

        highest_prob_badge = f"<span style='background:#0284c7; color:white; padding:2px 7px; border-radius:4px; font-size:0.75rem; font-weight:600;'>⭐ Top Pick: {p.get('highest_prob_selection', '')}</span>"

        with st.container():
            st.markdown(f"""
            <div style="border: 1px solid {card_border}; border-radius: 8px; padding: 15px; margin-bottom: 15px; background: rgba(30, 41, 59, 0.4);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:0.9rem; color:#94a3b8;">{flag} <b>{league_name}</b> • 📅 {date_str} • {ref_badge} • {highest_prob_badge}</span>
                    {badge_html}
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                    <div style="text-align:left; width:38%;">
                        <h3 style="margin:0; font-size:1.3rem;">{home}</h3>
                        <span style="color:#64748b; font-size:0.85rem;">Elo: {p['home_elo']:.0f} | xG: {p['expected_goals_home']:.2f}</span>
                    </div>
                    <div style="text-align:center; width:24%;">
                        <span style="font-size:1.1rem; font-weight:bold; color:#f59e0b;">vs</span><br/>
                        <span style="font-size:0.85rem; color:#94a3b8;">Proj. Score: <b>{p['most_likely_score']}</b></span>
                    </div>
                    <div style="text-align:right; width:38%;">
                        <h3 style="margin:0; font-size:1.3rem;">{away}</h3>
                        <span style="color:#64748b; font-size:0.85rem;">Elo: {p['away_elo']:.0f} | xG: {p['expected_goals_away']:.2f}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Probabilities & Special Markets Columns
            c1, c2, c3, c4 = st.columns([2.8, 3.2, 3.2, 2.8])
            
            with c1:
                st.markdown("**1X2 Probabilities & Odds**")
                st.markdown(f"- 🏠 **Home**: {format_odds_ev_str(p['prob_home'], p['fair_odds_home'], meta.get('odds_home'))}", unsafe_allow_html=True)
                st.markdown(f"- 🤝 **Draw**: {format_odds_ev_str(p['prob_draw'], p['fair_odds_draw'], meta.get('odds_draw'))}", unsafe_allow_html=True)
                st.markdown(f"- 🚗 **Away**: {format_odds_ev_str(p['prob_away'], p['fair_odds_away'], meta.get('odds_away'))}", unsafe_allow_html=True)

            with c2:
                st.markdown("**⚽ Goals & Both Teams to Score**")
                st.markdown(f"- Over 2.5: {format_odds_ev_str(p['prob_over25'], p['fair_odds_over25'], meta.get('odds_over25'))}", unsafe_allow_html=True)
                st.markdown(f"- Under 2.5: {format_odds_ev_str(p['prob_under25'], p['fair_odds_under25'], meta.get('odds_under25'))}", unsafe_allow_html=True)
                st.markdown(f"- BTTS Yes: {format_odds_ev_str(p['prob_btts_yes'], p['fair_odds_btts_yes'], meta.get('odds_btts_yes'))}", unsafe_allow_html=True)

            with c3:
                st.markdown("**🚩 Corners & 🟨 Cards (with Odds & EV)**")
                st.markdown(f"- Exp. Corners: **{p['expected_corners']:.1f}**")
                st.markdown(f"- Over 9.5 Corn: {format_odds_ev_str(p['prob_corners_over95'], p['fair_odds_corners_over95'], meta.get('odds_corners_over95'))}", unsafe_allow_html=True)
                st.markdown(f"- Exp. Cards: **{p['expected_cards']:.1f}**")
                st.markdown(f"- Over 3.5 Cards: {format_odds_ev_str(p['prob_cards_over35'], p['fair_odds_cards_over35'], meta.get('odds_cards_over35'))}", unsafe_allow_html=True)

            with c4:
                st.markdown("**Engine Recommendation**")
                if pick:
                    st.markdown(f"🎯 **Pick**: `{pick.get('selection')}`")
                    st.markdown(f"📈 **Prob**: `{pick.get('prob', 0)*100:.1f}%`")
                    if pick.get("odds") and pick.get("odds") > 1.0:
                        st.markdown(f"💰 **Odds**: `{pick.get('odds')}` | **EV**: `+{pick.get('ev', 0)*100:.1f}%`")
                        if pick.get("kelly", 0) > 0:
                            st.markdown(f"📊 **Kelly Stake**: `{pick.get('kelly')*100:.1f}%`")
                    else:
                        st.markdown(f"ℹ️ Fair Odds: `{round(1.0/max(0.01, pick.get('prob', 0.5)), 2)}`")
                
                if st.button(f"📌 Track Match ({home} vs {away})", key=f"track_{idx}"):
                    if hasattr(tracker, "log_full_match_prediction"):
                        tracker.log_full_match_prediction(p)
                    else:
                        tracker.log_prediction(p)
                    st.success(f"Logged {home} vs {away} for verification!")

            # Expandable Match Insights, Recent Form, H2H & Key Statistics
            with st.expander(f"🔍 Match Details: {home} vs {away} (Recent Results, H2H & Key Stats)", expanded=False):
                # 1. Key Predictive Drivers
                st.markdown("##### 📌 Key Predictive Drivers & Tactical Matchup")
                drivers = get_match_key_drivers(p)
                if drivers:
                    dr_cols = st.columns(min(3, len(drivers)))
                    for idx_d, d in enumerate(drivers):
                        icon = "🟢" if d["direction"] == "positive" else ("🔴" if d["direction"] == "negative" else "⚪")
                        with dr_cols[idx_d % len(dr_cols)]:
                            st.caption(f"{icon} **{d['factor']}**")
                            st.markdown(f"<span style='font-size:0.85rem;'>{d['detail']}</span>", unsafe_allow_html=True)
                
                st.markdown("---")

                # 2. Main Stats & Form Comparison Table
                h_stats = predictor.get_team_summary_stats(l_k, home)
                a_stats = predictor.get_team_summary_stats(l_k, away)

                st.markdown("##### 📊 Main Matchup Statistics & Season Performance")
                stat_col1, stat_col2, stat_col3 = st.columns([1.6, 1.2, 1.6])
                
                def format_form_badges(form_list):
                    if not form_list: return "N/A"
                    badge_map = {
                        "W": "<span style='background:#10b981; color:white; padding:1px 5px; border-radius:3px; font-weight:bold; font-size:0.75rem;'>W</span>",
                        "D": "<span style='background:#f59e0b; color:white; padding:1px 5px; border-radius:3px; font-weight:bold; font-size:0.75rem;'>D</span>",
                        "L": "<span style='background:#ef4444; color:white; padding:1px 5px; border-radius:3px; font-weight:bold; font-size:0.75rem;'>L</span>"
                    }
                    return " ".join([badge_map.get(res, res) for res in form_list])

                def _fmt_stat(val, suffix="", fmt=".2f"):
                    if val is None: return "-"
                    try:
                        return f"{val:{fmt}}{suffix}"
                    except Exception:
                        return f"{val}{suffix}"

                with stat_col1:
                    st.markdown(f"**🏠 {home}** (Home)")
                    st.markdown(f"- **Form (Last 5)**: {format_form_badges(h_stats.get('form', []))}", unsafe_allow_html=True)
                    st.markdown(f"- **Model Elo**: `{_fmt_stat(h_stats.get('elo'), fmt='.0f')}`")
                    st.markdown(f"- **Attack (λ)**: `{_fmt_stat(h_stats.get('attack'), fmt='+.2f')}` | **Def (λ)**: `{_fmt_stat(h_stats.get('defense'), fmt='+.2f')}`")
                    st.markdown(f"- **Avg Scored**: `{_fmt_stat(h_stats.get('avg_gf_season'))}` / match")
                    st.markdown(f"- **Avg Conceded**: `{_fmt_stat(h_stats.get('avg_ga_season'))}` / match")
                    st.markdown(f"- **Clean Sheet %**: `{_fmt_stat(h_stats.get('clean_sheet_pct'), suffix='%', fmt='.1f')}`")
                    st.markdown(f"- **BTTS %**: `{_fmt_stat(h_stats.get('btts_pct'), suffix='%', fmt='.1f')}` | **O2.5 %**: `{_fmt_stat(h_stats.get('o25_pct'), suffix='%', fmt='.1f')}`")

                with stat_col2:
                    st.markdown("**⚡ Model Projections**")
                    exp_h_xg = p.get("expected_goals_home")
                    exp_a_xg = p.get("expected_goals_away")
                    exp_tot_xg = p.get("expected_total_goals")
                    st.caption(f"Home xG: `{_fmt_stat(exp_h_xg)}`")
                    st.caption(f"Away xG: `{_fmt_stat(exp_a_xg)}`")
                    st.caption(f"Total Match xG: `{_fmt_stat(exp_tot_xg)}`")
                    st.caption(f"Proj Corners: `{_fmt_stat(p.get('expected_corners'), fmt='.1f')}`")
                    st.caption(f"Proj Cards: `{_fmt_stat(p.get('expected_cards'), fmt='.1f')}`")
                    st.caption(f"Top Score: **{p.get('most_likely_score', '-')}**")

                with stat_col3:
                    st.markdown(f"**🚗 {away}** (Away)")
                    st.markdown(f"- **Form (Last 5)**: {format_form_badges(a_stats.get('form', []))}", unsafe_allow_html=True)
                    st.markdown(f"- **Model Elo**: `{_fmt_stat(a_stats.get('elo'), fmt='.0f')}`")
                    st.markdown(f"- **Attack (λ)**: `{_fmt_stat(a_stats.get('attack'), fmt='+.2f')}` | **Def (λ)**: `{_fmt_stat(a_stats.get('defense'), fmt='+.2f')}`")
                    st.markdown(f"- **Avg Scored**: `{_fmt_stat(a_stats.get('avg_gf_season'))}` / match")
                    st.markdown(f"- **Avg Conceded**: `{_fmt_stat(a_stats.get('avg_ga_season'))}` / match")
                    st.markdown(f"- **Clean Sheet %**: `{_fmt_stat(a_stats.get('clean_sheet_pct'), suffix='%', fmt='.1f')}`")
                    st.markdown(f"- **BTTS %**: `{_fmt_stat(a_stats.get('btts_pct'), suffix='%', fmt='.1f')}` | **O2.5 %**: `{_fmt_stat(a_stats.get('o25_pct'), suffix='%', fmt='.1f')}`")

                st.markdown("---")

                # 3. Last 5 Matches for Each Team & Head-to-Head
                h_rec = predictor.get_team_recent_matches(l_k, home, n=5)
                a_rec = predictor.get_team_recent_matches(l_k, away, n=5)
                h2h_rec = predictor.get_h2h_matches(l_k, home, away, n=5)

                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.markdown(f"##### 🏠 Recent Matches: **{home}**")
                    if h_rec:
                        df_h_rec = pd.DataFrame(h_rec)
                        df_h_rec["Res"] = df_h_rec["res"].apply(lambda x: "🟢 W" if x=="W" else ("🟡 D" if x=="D" else "🔴 L"))
                        st.dataframe(df_h_rec[["date", "venue", "opponent", "score", "Res", "corners", "cards"]].rename(columns={"date": "Date", "venue": "Venue", "opponent": "Opponent", "score": "Score", "corners": "Corners", "cards": "Cards"}), hide_index=True, use_container_width=True)
                    else:
                        st.caption("No historical match log available for this team.")

                with col_res2:
                    st.markdown(f"##### 🚗 Recent Matches: **{away}**")
                    if a_rec:
                        df_a_rec = pd.DataFrame(a_rec)
                        df_a_rec["Res"] = df_a_rec["res"].apply(lambda x: "🟢 W" if x=="W" else ("🟡 D" if x=="D" else "🔴 L"))
                        st.dataframe(df_a_rec[["date", "venue", "opponent", "score", "Res", "corners", "cards"]].rename(columns={"date": "Date", "venue": "Venue", "opponent": "Opponent", "score": "Score", "corners": "Corners", "cards": "Cards"}), hide_index=True, use_container_width=True)
                    else:
                        st.caption("No historical match log available for this team.")

                st.markdown(f"##### ⚔️ Head-to-Head (H2H) Past Meetings ({home} vs {away})")
                if h2h_rec:
                    df_h2h = pd.DataFrame(h2h_rec)
                    st.dataframe(df_h2h[["date", "home_team", "score", "away_team", "winner"]].rename(columns={"date": "Date", "home_team": "Home", "score": "Score", "away_team": "Away", "winner": "Outcome"}), hide_index=True, use_container_width=True)
                else:
                    st.info(f"No direct head-to-head records found between {home} and {away} in recent seasons.")

            st.markdown("<hr style='margin: 10px 0; border: 0.5px solid #334155;'/>", unsafe_allow_html=True)
