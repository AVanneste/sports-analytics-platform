"""Dynamic Football Elo Rating Engine with Goal-Difference Multiplier & Home Advantage."""
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
from football_core.config import ELO_BASE, ELO_K, ELO_HOME_ADVANTAGE


class FootballEloEngine:
    """Calculates and updates team Elo ratings chronologically."""

    def __init__(self, base_elo: float = ELO_BASE, k_factor: float = ELO_K, home_adv: float = ELO_HOME_ADVANTAGE):
        self.base_elo = base_elo
        self.k_factor = k_factor
        self.home_adv = home_adv
        self.ratings: Dict[str, float] = {}
        self.match_count: Dict[str, int] = {}
        self.history: Dict[str, list] = {}

    def get_rating(self, team: str) -> float:
        """Return current rating for a team, initializing with base_elo if unseen."""
        return self.ratings.get(team, self.base_elo)

    def get_match_count(self, team: str) -> int:
        """Return number of matches played by team."""
        return self.match_count.get(team, 0)

    def compute_expected_probability(self, home_elo: float, away_elo: float) -> Tuple[float, float]:
        """
        Compute expected probability of home team vs away team including home advantage.
        P(Home) = 1 / (1 + 10^((Away - (Home + Adv)) / 400))
        """
        effective_home = home_elo + self.home_adv
        diff = away_elo - effective_home
        p_home = 1.0 / (1.0 + 10.0 ** (diff / 400.0))
        p_away = 1.0 - p_home
        return p_home, p_away

    def _goal_diff_multiplier(self, goal_diff: int) -> float:
        """Calculate margin-of-victory multiplier (World Football Elo formula)."""
        abs_diff = abs(goal_diff)
        if abs_diff <= 1:
            return 1.0
        elif abs_diff == 2:
            return 1.5
        else:
            return (11.0 + abs_diff) / 8.0

    def update_match(
        self,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        date: Optional[pd.Timestamp] = None
    ) -> Dict[str, float]:
        """
        Process a match result, return pre-match features, and update ratings.
        """
        home_pre = self.get_rating(home_team)
        away_pre = self.get_rating(away_team)
        home_exp, away_exp = self.compute_expected_probability(home_pre, away_pre)

        # Actual outcome score S (1 = Win, 0.5 = Draw, 0 = Loss)
        if fthg > ftag:
            s_home = 1.0
            s_away = 0.0
        elif fthg == ftag:
            s_home = 0.5
            s_away = 0.5
        else:
            s_home = 0.0
            s_away = 1.0

        # Goal difference multiplier
        g_mult = self._goal_diff_multiplier(fthg - ftag)

        # Elo Delta
        delta_home = self.k_factor * g_mult * (s_home - home_exp)
        delta_away = -delta_home

        # Update ratings
        home_post = home_pre + delta_home
        away_post = away_pre + delta_away

        self.ratings[home_team] = home_post
        self.ratings[away_team] = away_post

        self.match_count[home_team] = self.match_count.get(home_team, 0) + 1
        self.match_count[away_team] = self.match_count.get(away_team, 0) + 1

        if date is not None:
            if home_team not in self.history:
                self.history[home_team] = []
            if away_team not in self.history:
                self.history[away_team] = []
            self.history[home_team].append({"date": date, "rating": home_post})
            self.history[away_team].append({"date": date, "rating": away_post})

        return {
            "home_elo_pre": home_pre,
            "away_elo_pre": away_pre,
            "elo_diff": (home_pre + self.home_adv) - away_pre,
            "elo_exp_home_prob": home_exp,
            "elo_exp_away_prob": away_exp,
            "home_elo_post": home_post,
            "away_elo_post": away_post,
        }

