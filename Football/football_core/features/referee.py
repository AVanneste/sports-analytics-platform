"""Referee Statistics, Tendencies, and Strictness Engine."""
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd
from collections import defaultdict


class RefereeStatsEngine:
    """Tracks match-by-match referee statistics and computes strictness indices."""

    def __init__(self):
        # referee_name -> list of match records
        self.referee_history = defaultdict(list)
        self.league_card_sum = 0.0
        self.league_foul_sum = 0.0
        self.league_match_count = 0

    def record_match(
        self,
        referee_name: Optional[str],
        date: pd.Timestamp,
        yellows: float,
        reds: float,
        fouls: float,
    ):
        """Record completed match disciplinary stats for the assigned referee."""
        cards = yellows + reds
        self.league_card_sum += cards
        self.league_foul_sum += fouls
        self.league_match_count += 1

        if not referee_name or not isinstance(referee_name, str) or referee_name.strip() == "":
            return

        ref_clean = referee_name.strip()
        self.referee_history[ref_clean].append({
            "date": date,
            "yellows": yellows,
            "reds": reds,
            "total_cards": cards,
            "fouls": fouls,
        })

    def get_league_avg_cards(self) -> float:
        """Return overall league average cards per match."""
        if self.league_match_count == 0:
            return 4.2
        return max(1.0, self.league_card_sum / self.league_match_count)

    def get_league_avg_fouls(self) -> float:
        """Return overall league average fouls per match."""
        if self.league_match_count == 0:
            return 23.5
        return max(1.0, self.league_foul_sum / self.league_match_count)

    def get_referee_profile(self, referee_name: Optional[str], current_date: Optional[pd.Timestamp] = None) -> Dict[str, Any]:
        """
        Compute referee historical averages and strictness multiplier prior to current match.
        """
        league_avg_cards = self.get_league_avg_cards()
        league_avg_fouls = self.get_league_avg_fouls()

        if not referee_name or not isinstance(referee_name, str) or referee_name.strip() == "":
            return {
                "referee_name": "Unassigned / League Average",
                "matches_officiated": 0,
                "avg_yellows": round(league_avg_cards * 0.95, 2),
                "avg_reds": round(league_avg_cards * 0.05, 2),
                "avg_cards": round(league_avg_cards, 2),
                "avg_fouls": round(league_avg_fouls, 2),
                "strictness_index": 1.0,
                "strictness_label": "🟡 Balanced (League Avg)",
            }

        ref_clean = referee_name.strip()
        history = self.referee_history.get(ref_clean, [])
        if current_date is not None:
            history = [m for m in history if m["date"] < current_date]

        k = len(history)
        if k == 0:
            return {
                "referee_name": ref_clean,
                "matches_officiated": 0,
                "avg_yellows": round(league_avg_cards * 0.95, 2),
                "avg_reds": round(league_avg_cards * 0.05, 2),
                "avg_cards": round(league_avg_cards, 2),
                "avg_fouls": round(league_avg_fouls, 2),
                "strictness_index": 1.0,
                "strictness_label": "🟡 Balanced (New/Unseen Ref)",
            }

        total_yellows = sum(m["yellows"] for m in history)
        total_reds = sum(m["reds"] for m in history)
        total_cards = sum(m["total_cards"] for m in history)
        total_fouls = sum(m["fouls"] for m in history)

        avg_y = total_yellows / k
        avg_r = total_reds / k
        avg_c = total_cards / k
        avg_f = total_fouls / k

        # Bayesian shrinkage / smoothing toward league average for small sample sizes
        # Empirical prior weight of 5 matches
        prior_weight = 5.0
        smoothed_avg_cards = (total_cards + prior_weight * league_avg_cards) / (k + prior_weight)
        strictness_index = float(smoothed_avg_cards / league_avg_cards)

        if strictness_index >= 1.15:
            strictness_label = "🔴 Very Strict (High Card Rate)"
        elif strictness_index >= 1.05:
            strictness_label = "🟠 Moderately Strict"
        elif strictness_index <= 0.85:
            strictness_label = "🟢 Very Lenient (Low Card Rate)"
        elif strictness_index <= 0.95:
            strictness_label = "🟢 Moderately Lenient"
        else:
            strictness_label = "🟡 Balanced"

        return {
            "referee_name": ref_clean,
            "matches_officiated": k,
            "avg_yellows": round(avg_y, 2),
            "avg_reds": round(avg_r, 2),
            "avg_cards": round(avg_c, 2),
            "avg_fouls": round(avg_f, 2),
            "strictness_index": round(strictness_index, 3),
            "strictness_label": strictness_label,
        }

    def get_all_known_referees(self) -> List[str]:
        """Return list of all registered referees."""
        return sorted([r for r, hist in self.referee_history.items() if len(hist) >= 1])

