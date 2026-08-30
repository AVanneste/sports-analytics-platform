"""Head-to-Head (H2H) record tracking engine with games and sets dynamics."""
from typing import Dict, List, Optional, Tuple
import pandas as pd


class TennisH2HEngine:
    """Maintains career and surface-specific Head-to-Head match, set, and game records."""

    def __init__(self):
        # Key: (player_a, player_b) sorted alphabetically -> dict of stats
        self.h2h_records: Dict[Tuple[str, str], Dict] = {}

    def _get_key(self, p1: str, p2: str) -> Tuple[str, str]:
        return (min(p1, p2), max(p1, p2))

    def get_h2h_stats(self, p1: str, p2: str, surface: Optional[str] = None) -> Dict:
        """
        Get pre-match H2H statistics from p1's perspective.
        """
        key = self._get_key(p1, p2)
        record = self.h2h_records.get(key)
        
        if not record:
            return {
                "total_matches": 0,
                "p1_wins": 0,
                "p2_wins": 0,
                "p1_win_rate": 0.5,
                "p1_sets": 0,
                "p2_sets": 0,
                "p1_games": 0,
                "p2_games": 0,
                "surface_matches": 0,
                "p1_surface_wins": 0,
                "p2_surface_wins": 0,
                "p1_surface_win_rate": 0.5,
            }

        total = record["total"]
        p1_w = record["wins"].get(p1, 0)
        p2_w = record["wins"].get(p2, 0)
        p1_rate = p1_w / total if total > 0 else 0.5

        p1_sets = record["sets"].get(p1, 0)
        p2_sets = record["sets"].get(p2, 0)
        p1_games = record["games"].get(p1, 0)
        p2_games = record["games"].get(p2, 0)

        surf = surface if surface else "Hard"
        surf_data = record["surfaces"].get(surf, {"total": 0, "wins": {}, "sets": {}, "games": {}})
        s_total = surf_data["total"]
        p1_s_w = surf_data["wins"].get(p1, 0)
        p2_s_w = surf_data["wins"].get(p2, 0)
        p1_s_rate = p1_s_w / s_total if s_total > 0 else 0.5

        return {
            "total_matches": total,
            "p1_wins": p1_w,
            "p2_wins": p2_w,
            "p1_win_rate": p1_rate,
            "p1_sets": p1_sets,
            "p2_sets": p2_sets,
            "p1_games": p1_games,
            "p2_games": p2_games,
            "surface_matches": s_total,
            "p1_surface_wins": p1_s_w,
            "p2_surface_wins": p2_s_w,
            "p1_surface_win_rate": p1_s_rate,
        }

    def record_match(
        self,
        winner: str,
        loser: str,
        surface: str,
        date: Optional[pd.Timestamp] = None,
        w_sets: int = 2,
        l_sets: int = 0,
        w_games: int = 12,
        l_games: int = 8
    ):
        """Update H2H record after match concludes."""
        key = self._get_key(winner, loser)
        if key not in self.h2h_records:
            self.h2h_records[key] = {
                "total": 0,
                "wins": {winner: 0, loser: 0},
                "sets": {winner: 0, loser: 0},
                "games": {winner: 0, loser: 0},
                "surfaces": {},
            }

        rec = self.h2h_records[key]
        rec["total"] += 1
        rec["wins"][winner] = rec["wins"].get(winner, 0) + 1
        rec["wins"][loser] = rec["wins"].get(loser, 0)
        
        rec["sets"][winner] = rec["sets"].get(winner, 0) + w_sets
        rec["sets"][loser] = rec["sets"].get(loser, 0) + l_sets
        
        rec["games"][winner] = rec["games"].get(winner, 0) + w_games
        rec["games"][loser] = rec["games"].get(loser, 0) + l_games

        if surface not in rec["surfaces"]:
            rec["surfaces"][surface] = {
                "total": 0,
                "wins": {winner: 0, loser: 0},
                "sets": {winner: 0, loser: 0},
                "games": {winner: 0, loser: 0},
            }

        s_rec = rec["surfaces"][surface]
        s_rec["total"] += 1
        s_rec["wins"][winner] = s_rec["wins"].get(winner, 0) + 1
        s_rec["wins"][loser] = s_rec["wins"].get(loser, 0)
        s_rec["sets"][winner] = s_rec["sets"].get(winner, 0) + w_sets
        s_rec["sets"][loser] = s_rec["sets"].get(loser, 0) + l_sets
        s_rec["games"][winner] = s_rec["games"].get(winner, 0) + w_games
        s_rec["games"][loser] = s_rec["games"].get(loser, 0) + l_games
