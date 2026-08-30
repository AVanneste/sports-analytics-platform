"""Dynamic Surface-Specific and Overall Elo Rating Engine."""
import logging
import math
from typing import Dict, List, Optional, Tuple
import pandas as pd

from tennis_core.config import INITIAL_ELO, BASE_K, SURFACE_K, LEVEL_K_MULTIPLIERS, PRIMARY_SURFACES

logger = logging.getLogger(__name__)


class TennisEloEngine:
    """
    Maintains and updates dynamic overall and surface-specific Elo ratings
    across historical matches chronologically.
    """

    def __init__(self, initial_elo: float = INITIAL_ELO, base_k: float = BASE_K, surface_k: float = SURFACE_K):
        self.initial_elo = initial_elo
        self.base_k = base_k
        self.surface_k = surface_k
        
        # Ratings dictionaries: player_name -> float
        self.overall_elo: Dict[str, float] = {}
        self.surface_elo: Dict[str, Dict[str, float]] = {s: {} for s in PRIMARY_SURFACES}
        
        # Match counters: player_name -> count
        self.match_counts: Dict[str, int] = {}
        self.surface_match_counts: Dict[str, Dict[str, int]] = {s: {} for s in PRIMARY_SURFACES}
        
        # Historical Elo trajectory logs: player_name -> list of (date, overall_elo, surface, surface_elo)
        self.history: Dict[str, List[Tuple]] = {}

    def get_overall_elo(self, player: str) -> float:
        return self.overall_elo.get(player, self.initial_elo)

    def get_surface_elo(self, player: str, surface: str) -> float:
        s = surface if surface in PRIMARY_SURFACES else "Hard"
        return self.surface_elo[s].get(player, self.initial_elo)

    def get_surface_match_count(self, player: str, surface: str) -> int:
        s = surface if surface in PRIMARY_SURFACES else "Hard"
        return self.surface_match_counts[s].get(player, 0)

    def get_effective_surface_elo(self, player: str, surface: str, min_surface_matches: int = 15) -> float:
        """
        Blends surface-specific Elo with overall Elo based on surface sample size.
        If a player has few matches on Grass (e.g. 2), it relies mostly on overall Elo.
        """
        overall = self.get_overall_elo(player)
        surf = self.get_surface_elo(player, surface)
        count = self.get_surface_match_count(player, surface)
        
        weight = min(1.0, count / float(min_surface_matches))
        return (weight * surf) + ((1.0 - weight) * overall)

    def calculate_expected_outcome(self, elo_a: float, elo_b: float) -> float:
        """Standard Elo expected score formula."""
        return 1.0 / (1.0 + math.pow(10.0, (elo_b - elo_a) / 400.0))

    def update_match(
        self,
        winner: str,
        loser: str,
        surface: str,
        tourney_level: str = "A",
        date: Optional[pd.Timestamp] = None
    ) -> Tuple[float, float, float, float]:
        """
        Record match outcome and update ratings.
        Returns pre-match (w_overall_elo, l_overall_elo, w_surface_elo, l_surface_elo).
        """
        surf = surface if surface in PRIMARY_SURFACES else "Hard"
        level_mult = LEVEL_K_MULTIPLIERS.get(tourney_level, 1.0)
        
        # 1. Capture Pre-Match Ratings
        w_overall_pre = self.get_overall_elo(winner)
        l_overall_pre = self.get_overall_elo(loser)
        w_surf_pre = self.get_surface_elo(winner, surf)
        l_surf_pre = self.get_surface_elo(loser, surf)
        
        # 2. Update Overall Elo
        exp_w_overall = self.calculate_expected_outcome(w_overall_pre, l_overall_pre)
        exp_l_overall = 1.0 - exp_w_overall
        
        # Dynamic K based on match count (higher K for newcomers)
        w_matches = self.match_counts.get(winner, 0)
        l_matches = self.match_counts.get(loser, 0)
        
        k_w = self.base_k * level_mult * (1.5 if w_matches < 20 else 1.0)
        k_l = self.base_k * level_mult * (1.5 if l_matches < 20 else 1.0)
        
        w_overall_post = w_overall_pre + k_w * (1.0 - exp_w_overall)
        l_overall_post = l_overall_pre + k_l * (0.0 - exp_l_overall)
        
        self.overall_elo[winner] = w_overall_post
        self.overall_elo[loser] = l_overall_post
        self.match_counts[winner] = w_matches + 1
        self.match_counts[loser] = l_matches + 1
        
        # 3. Update Surface Elo
        exp_w_surf = self.calculate_expected_outcome(w_surf_pre, l_surf_pre)
        exp_l_surf = 1.0 - exp_w_surf
        
        w_surf_count = self.surface_match_counts[surf].get(winner, 0)
        l_surf_count = self.surface_match_counts[surf].get(loser, 0)
        
        k_w_surf = self.surface_k * level_mult * (1.5 if w_surf_count < 15 else 1.0)
        k_l_surf = self.surface_k * level_mult * (1.5 if l_surf_count < 15 else 1.0)
        
        w_surf_post = w_surf_pre + k_w_surf * (1.0 - exp_w_surf)
        l_surf_post = l_surf_pre + k_l_surf * (0.0 - exp_l_surf)
        
        self.surface_elo[surf][winner] = w_surf_post
        self.surface_elo[surf][loser] = l_surf_post
        self.surface_match_counts[surf][winner] = w_surf_count + 1
        self.surface_match_counts[surf][loser] = l_surf_count + 1
        
        # 4. Record history
        if date is not None:
            if winner not in self.history:
                self.history[winner] = []
            if loser not in self.history:
                self.history[loser] = []
            self.history[winner].append((date, w_overall_post, surf, w_surf_post))
            self.history[loser].append((date, l_overall_post, surf, l_surf_post))
            
        return w_overall_pre, l_overall_pre, w_surf_pre, l_surf_pre

    def get_leaderboard(self, surface: Optional[str] = None, min_matches: int = 10) -> pd.DataFrame:
        """Generate current Elo leaderboard."""
        records = []
        for player, overall in self.overall_elo.items():
            total_m = self.match_counts.get(player, 0)
            if total_m < min_matches:
                continue
            rec = {
                "player": player,
                "overall_elo": round(overall, 1),
                "total_matches": total_m,
            }
            for s in PRIMARY_SURFACES:
                rec[f"{s.lower()}_elo"] = round(self.get_surface_elo(player, s), 1)
                rec[f"{s.lower()}_matches"] = self.get_surface_match_count(player, s)
                rec[f"{s.lower()}_effective_elo"] = round(self.get_effective_surface_elo(player, s), 1)
            records.append(rec)
            
        df = pd.DataFrame(records)
        if df.empty:
            return df
        
        if surface and surface in PRIMARY_SURFACES:
            return df.sort_values(by=f"{surface.lower()}_effective_elo", ascending=False).reset_index(drop=True)
        return df.sort_values(by="overall_elo", ascending=False).reset_index(drop=True)

