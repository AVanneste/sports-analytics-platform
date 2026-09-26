"""Ledger Post-Mortem Diagnostics & Leak Detection Engine.
Audits settled betting records to distinguish between pure variance losses
and structural model flaws, surfaces negative-ROI cohorts, and generates
actionable betting framework guardrails.
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


def run_ledger_diagnostics(tracker_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute complete post-mortem audit across settled ledger bets."""
    settled = [
        m for m in tracker_entries
        if (m.get("status") in ("settled", "WON", "LOST", "SETTLED") or m.get("actual_winner") or m.get("actual_score"))
        and (
            float(m.get("stake", 0.0)) > 0
            or m.get("has_value") is True
            or m.get("is_value_bet") is True
            or m.get("won") in (True, False)
            or m.get("status") in ("WON", "LOST")
        )
    ]
    
    if not settled:
        return {
            "total_audited": 0,
            "wins_count": 0,
            "losses_count": 0,
            "loss_breakdown": {"variance_losses": 0, "structural_losses": 0, "variance_ratio_pct": 0.0},
            "active_leaks_count": 0,
            "active_leaks": [],
            "top_performers": [],
            "cohorts": {},
            "recommendations": ["No settled bets available for diagnostic auditing yet."]
        }

    total_settled = len(settled)
    wins = [m for m in settled if m.get("won") is True or m.get("status") == "WON"]
    losses = [m for m in settled if m.get("won") is False or m.get("status") == "LOST" or float(m.get("flat_pnl", 0.0)) < 0]

    # 1. Loss Classification (Variance vs Structural Model Flaw)
    variance_losses = 0
    structural_losses = 0

    for m in losses:
        pick = m.get("best_pick") or {}
        odds = float(pick.get("odds") or m.get("best_odds") or m.get("odds_home") or m.get("odds") or 2.0)
        prob = float(pick.get("prob") or (m.get("confidence", 50.0) / 100.0) or m.get("prob_home") or m.get("prob") or 0.5)
        goal_err = float(m.get("goal_error", m.get("game_error", 99.0)))
        actual_score = str(m.get("actual_score", m.get("score", "")))
        
        # Criteria for Variance Loss:
        # - High model probability (>= 50%) or short odds (<= 2.10)
        # - Low goal/game error (<= 1.2 goals or <= 3.0 games) indicating game state was close to expectation
        # - Close scoreline (e.g. 1-1 draw on 1X2 favorite, or 3-set decider in tennis)
        is_variance = False
        if prob >= 0.50 or odds <= 2.10:
            is_variance = True
        elif goal_err <= 1.2 or (m.get("circuit") and goal_err <= 3.0):
            is_variance = True
        elif actual_score in ["1-1", "0-0", "2-2"] and pick.get("market") == "1X2":
            # Draw variance when backing winner
            is_variance = True
        elif m.get("correct_deciding_set") is True:
            is_variance = True

        if is_variance:
            variance_losses += 1
        else:
            structural_losses += 1

    var_ratio = round((variance_losses / len(losses) * 100.0), 1) if losses else 0.0

    # 2. Helper for Cohort Aggregation
    def analyze_cohort_group(group_fn, group_name: str) -> List[Dict[str, Any]]:
        groups = {}
        for m in settled:
            label = group_fn(m)
            if not label:
                continue
            if label not in groups:
                groups[label] = {
                    "cohort": label,
                    "dimension": group_name,
                    "count": 0,
                    "wins": 0,
                    "staked": 0.0,
                    "pnl": 0.0,
                }
            g = groups[label]
            g["count"] += 1
            stake = float(m.get("stake", 100.0))
            pnl = float(m.get("flat_pnl", m.get("pnl", 0.0)))
            if m.get("won") is True or m.get("status") == "WON":
                g["wins"] += 1
            g["staked"] += stake
            g["pnl"] += pnl

        results = []
        for g in groups.values():
            cnt = g["count"]
            win_rate = round((g["wins"] / cnt) * 100.0, 1) if cnt > 0 else 0.0
            roi_pct = round((g["pnl"] / g["staked"]) * 100.0, 1) if g["staked"] > 0 else 0.0
            
            # Severity detection
            if cnt >= 4 and roi_pct <= -15.0:
                leak_severity = "HIGH_LEAK"
            elif cnt >= 3 and roi_pct <= -5.0:
                leak_severity = "MODERATE_LEAK"
            elif roi_pct >= 10.0 and cnt >= 3:
                leak_severity = "HIGH_PROFIT"
            else:
                leak_severity = "NEUTRAL"

            results.append({
                "cohort": g["cohort"],
                "dimension": g["dimension"],
                "count": cnt,
                "wins": g["wins"],
                "win_rate_pct": win_rate,
                "total_staked": round(g["staked"], 2),
                "net_pnl": round(g["pnl"], 2),
                "roi_pct": roi_pct,
                "leak_severity": leak_severity
            })
        return sorted(results, key=lambda x: x["roi_pct"])

    # 3. Dimension Extractors
    def odds_bracket_fn(m):
        pick = m.get("best_pick") or {}
        o = float(
            pick.get("odds")
            or m.get("best_odds")
            or m.get("odds")
            or m.get("odds_home")
            or m.get("p1_odds")
            or 2.0
        )
        if o < 1.60:
            return "Odds: Favorites [1.10 - 1.60]"
        elif o <= 2.20:
            return "Odds: Balanced [1.61 - 2.20]"
        elif o <= 3.20:
            return "Odds: Value Underdogs [2.21 - 3.20]"
        else:
            return "Odds: Longshots [> 3.20]"

    def league_fn(m):
        return m.get("league") or m.get("league_name") or m.get("circuit") or "Other"

    def market_fn(m):
        pick = m.get("best_pick") or {}
        return pick.get("market") or m.get("market_category") or m.get("market") or "1X2 / Match Winner"

    def venue_or_surface_fn(m):
        if m.get("surface"):
            return f"Surface: {m.get('surface')} Court"
        pick = m.get("best_pick") or {}
        sel = (pick.get("selection") or m.get("selection") or "").lower()
        if "away" in sel:
            return "Venue: Away Picks"
        elif "home" in sel:
            return "Venue: Home Picks"
        elif "draw" in sel:
            return "Venue: Draw Picks"
        return "Venue: Neutral / Totals"

    cohorts_by_odds = analyze_cohort_group(odds_bracket_fn, "Odds Bracket")
    cohorts_by_league = analyze_cohort_group(league_fn, "Competition / Circuit")
    cohorts_by_market = analyze_cohort_group(market_fn, "Market Type")
    cohorts_by_venue = analyze_cohort_group(venue_or_surface_fn, "Venue / Surface")

    all_cohorts = cohorts_by_odds + cohorts_by_league + cohorts_by_market + cohorts_by_venue

    # 4. Filter Specific High & Moderate Leaks (requiring min 3 bets to prevent single-match noise)
    active_leaks = [c for c in all_cohorts if c["leak_severity"] in ("HIGH_LEAK", "MODERATE_LEAK") and c["count"] >= 3]
    top_performers = [c for c in all_cohorts if c["leak_severity"] == "HIGH_PROFIT" and c["count"] >= 2]

    # 5. Synthesize Concrete Guardrail Recommendations
    recommendations = []
    
    # Check longshot leak
    longshot_cohort = next((c for c in cohorts_by_odds if "> 3.20" in c["cohort"]), None)
    if longshot_cohort and longshot_cohort["count"] >= 3 and longshot_cohort["roi_pct"] < 0:
        recommendations.append(
            f"Cap or exclude Longshots (> 3.20 odds): currently yielding {longshot_cohort['roi_pct']}% ROI across {longshot_cohort['count']} bets."
        )

    # Check underdog leak
    underdog_cohort = next((c for c in cohorts_by_odds if "2.21 - 3.20" in c["cohort"]), None)
    if underdog_cohort and underdog_cohort["count"] >= 5 and underdog_cohort["roi_pct"] <= -10.0:
        recommendations.append(
            f"Tighten edge cutoff on Value Underdogs [2.21 - 3.20]: producing {underdog_cohort['roi_pct']}% ROI across {underdog_cohort['count']} bets ({underdog_cohort['win_rate_pct']}% win rate). Require min EV +5.0%."
        )

    # Check league / circuit specific leaks
    for l_c in cohorts_by_league:
        if l_c["leak_severity"] == "HIGH_LEAK" and l_c["count"] >= 3:
            recommendations.append(
                f"Increase minimum EV margin threshold on {l_c['cohort']} from +3.0% to +6.0% (historical ROI: {l_c['roi_pct']}% across {l_c['count']} bets)."
            )
        elif l_c["leak_severity"] == "MODERATE_LEAK" and l_c["count"] >= 5:
            recommendations.append(
                f"Monitor {l_c['cohort']}: moderate drag of {l_c['roi_pct']}% ROI across {l_c['count']} bets. Consider fractional Kelly reduction."
            )

    # Check market leaks
    for m_c in cohorts_by_market:
        if m_c["leak_severity"] == "HIGH_LEAK" and m_c["count"] >= 3:
            recommendations.append(
                f"Review {m_c['cohort']} model calibration: underperforming with {m_c['win_rate_pct']}% hit rate across {m_c['count']} bets."
            )

    # Highlight top profitable framework strengths
    if top_performers:
        best = max(top_performers, key=lambda x: x["roi_pct"])
        recommendations.append(
            f"Core strength: {best['cohort']} is your highest-alpha bucket (+{best['roi_pct']}% ROI across {best['count']} bets). Maintain full Kelly allocation."
        )

    if not recommendations:
        recommendations.append("All audited cohorts are operating within normal statistical variance boundaries.")

    return {
        "total_audited": total_settled,
        "wins_count": len(wins),
        "losses_count": len(losses),
        "loss_breakdown": {
            "variance_losses": variance_losses,
            "structural_losses": structural_losses,
            "variance_ratio_pct": var_ratio,
        },
        "active_leaks_count": len(active_leaks),
        "active_leaks": active_leaks,
        "top_performers": top_performers,
        "cohorts": {
            "by_odds": cohorts_by_odds,
            "by_league": cohorts_by_league,
            "by_market": cohorts_by_market,
            "by_venue": cohorts_by_venue,
        },
        "recommendations": recommendations,
    }

