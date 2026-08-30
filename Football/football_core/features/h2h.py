"""Head-to-head (H2H) historic matchup analytics."""
from typing import Dict, Tuple
import pandas as pd
from collections import defaultdict


class HeadToHeadTracker:
    """Tracks historic encounters between pairs of football clubs."""

    def __init__(self):
        self.h2h_matches = defaultdict(list)

    def _get_key(self, team1: str, team2: str) -> Tuple[str, str]:
        """Canonical alphabetical key for matchup pair."""
        return tuple(sorted([team1, team2]))

    def record_match(self, date: pd.Timestamp, home_team: str, away_team: str, fthg: int, ftag: int):
        """Record completed head-to-head match."""
        key = self._get_key(home_team, away_team)
        self.h2h_matches[key].append({
            "date": date,
            "home_team": home_team,
            "away_team": away_team,
            "fthg": fthg,
            "ftag": ftag,
        })

    def get_h2h_features(self, home_team: str, away_team: str, current_date: pd.Timestamp, max_matches: int = 5) -> Dict[str, float]:
        """Compute pre-match H2H features."""
        key = self._get_key(home_team, away_team)
        history = [m for m in self.h2h_matches[key] if m["date"] < current_date]

        if not history:
            return {
                "h2h_matches_count": 0.0,
                "h2h_home_win_rate": 0.38,
                "h2h_draw_rate": 0.25,
                "h2h_away_win_rate": 0.37,
                "h2h_avg_total_goals": 2.7,
                "h2h_home_goals_avg": 1.4,
                "h2h_away_goals_avg": 1.3,
            }

        recent = history[-max_matches:]
        k = len(recent)

        home_wins = 0
        draws = 0
        away_wins = 0
        total_goals = 0
        home_goals = 0
        away_goals = 0

        for m in recent:
            is_h = (m["home_team"] == home_team)
            h_g = m["fthg"] if is_h else m["ftag"]
            a_g = m["ftag"] if is_h else m["fthg"]

            total_goals += (h_g + a_g)
            home_goals += h_g
            away_goals += a_g

            if h_g > a_g:
                home_wins += 1
            elif h_g == a_g:
                draws += 1
            else:
                away_wins += 1

        return {
            "h2h_matches_count": float(k),
            "h2h_home_win_rate": home_wins / k,
            "h2h_draw_rate": draws / k,
            "h2h_away_win_rate": away_wins / k,
            "h2h_avg_total_goals": total_goals / k,
            "h2h_home_goals_avg": home_goals / k,
            "h2h_away_goals_avg": away_goals / k,
        }

