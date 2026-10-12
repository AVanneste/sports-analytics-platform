"""Ledger Post-Mortem Diagnostics & Leak Detection Engine.
Audits settled betting records to distinguish between pure variance losses
and structural model flaws, surfaces negative-ROI cohorts, and generates
actionable betting framework guardrails.
"""
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


MIN_COHORT = 30  # fewer bets than this cannot separate a real leak from bad luck at typical odds


def _bet_prob_odds(m: Dict[str, Any]):
    """(model probability, decimal odds) of a settled bet."""
    pick = m.get("best_pick") or {}
    odds = float(pick.get("odds") or m.get("best_odds") or m.get("odds") or m.get("odds_home") or m.get("p1_odds") or 2.0)
    prob = pick.get("prob") or m.get("best_prob") or m.get("prob")
    prob = float(prob) if prob is not None else 1.0 / odds
    prob = prob / 100.0 if prob > 1.0 else prob
    return min(max(prob, 0.001), 0.999), max(odds, 1.001)


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

    # 1. Losses beyond what the model's own probabilities predicted. Expected losses are the sum of
    # (1 - p) over the bets; only the excess over that is evidence of a model flaw, the rest is variance.
    expected_losses = sum(1.0 - _bet_prob_odds(m)[0] for m in settled)
    structural_losses = max(0, round(len(losses) - expected_losses))
    variance_losses = len(losses) - structural_losses
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
                    "expected": 0.0,
                    "variance": 0.0,
                }
            g = groups[label]
            g["count"] += 1
            stake = float(m.get("stake", 100.0))
            pnl = float(m.get("flat_pnl", m.get("pnl", 0.0)))
            if m.get("won") is True or m.get("status") == "WON":
                g["wins"] += 1
            g["staked"] += stake
            g["pnl"] += pnl
            p, o = _bet_prob_odds(m)
            g["expected"] += stake * (p * o - 1.0)
            g["variance"] += stake ** 2 * o ** 2 * p * (1.0 - p)

        results = []
        for g in groups.values():
            cnt = g["count"]
            win_rate = round((g["wins"] / cnt) * 100.0, 1) if cnt > 0 else 0.0
            roi_pct = round((g["pnl"] / g["staked"]) * 100.0, 1) if g["staked"] > 0 else 0.0
            
            # Severity: how many standard deviations the result sits from what the bets' own
            # probabilities predicted, judged only on cohorts big enough to tell skill from luck
            z = (g["pnl"] - g["expected"]) / g["variance"] ** 0.5 if g["variance"] > 0 else 0.0
            if cnt >= MIN_COHORT and z <= -2.5:
                leak_severity = "HIGH_LEAK"
            elif cnt >= MIN_COHORT and z <= -2.0:
                leak_severity = "MODERATE_LEAK"
            elif cnt >= MIN_COHORT and z >= 2.0:
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
                "expected_pnl": round(g["expected"], 2),
                "z_score": round(z, 2),
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

    # 4. Only cohorts clearly worse (or better) than their own predictions count
    active_leaks = [c for c in all_cohorts if c["leak_severity"] in ("HIGH_LEAK", "MODERATE_LEAK")]
    top_performers = [c for c in all_cohorts if c["leak_severity"] == "HIGH_PROFIT"]

    expected = sum(float(m.get("stake") or 100.0) * (_bet_prob_odds(m)[0] * _bet_prob_odds(m)[1] - 1.0) for m in settled)
    actual = sum(float(m.get("flat_pnl", m.get("pnl", 0.0)) or 0.0) for m in settled)
    sd = sum(float(m.get("stake") or 100.0) ** 2 * o ** 2 * p * (1 - p)
             for m in settled for p, o in [_bet_prob_odds(m)]) ** 0.5
    recommendations = [f"Overall: {total_settled} bets, the model expected {expected:+.0f}€ and made {actual:+.0f}€ "
                       f"({(actual - expected) / sd:+.1f} standard deviations)." if sd else f"Overall: {total_settled} bets."]
    for c in sorted(active_leaks, key=lambda c: c["z_score"]):
        recommendations.append(f"{c['cohort']}: {c['net_pnl']:+.0f}€ vs {c['expected_pnl']:+.0f}€ expected over {c['count']} bets "
                               f"({c['z_score']:+.1f} SD), worse than luck explains. Review this segment before betting it.")
    for c in top_performers:
        recommendations.append(f"{c['cohort']}: {c['net_pnl']:+.0f}€ vs {c['expected_pnl']:+.0f}€ expected over {c['count']} bets "
                               f"({c['z_score']:+.1f} SD), better than luck explains.")
    if not active_leaks and not top_performers:
        recommendations.append(f"No segment is significantly off its own predictions yet (needs {MIN_COHORT}+ bets and "
                               f"2+ standard deviations). Small cohorts swing wildly: keep collecting, change nothing.")

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

