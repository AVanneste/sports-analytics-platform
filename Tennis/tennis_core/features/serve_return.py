"""Dynamic Serve and Return (Hold % & Break %) tracking engine."""
from typing import Dict, List, Optional, Tuple
import pandas as pd


class TennisServeReturnEngine:
    """
    Maintains rolling and surface-specific Serve Hold % and Return Break % for every player.
    Computes expected hold/break matchup probabilities and serve-dominance indexes.
    """

    def __init__(self, baseline_hold: float = 0.78, baseline_break: float = 0.22):
        self.baseline_hold = baseline_hold
        self.baseline_break = baseline_break
        # player -> {'service_games_won': int, 'service_games_total': int, 'return_games_won': int, 'return_games_total': int, 'surfaces': {}}
        self.player_stats: Dict[str, Dict] = {}

    def _init_player(self, player: str):
        if player not in self.player_stats:
            self.player_stats[player] = {
                "service_games_won": 78,
                "service_games_total": 100,
                "return_games_won": 22,
                "return_games_total": 100,
                "surfaces": {},
            }

    def record_match_stats(
        self,
        winner: str,
        loser: str,
        surface: str,
        score_details: Dict
    ):
        """
        Record and update serve hold and return break stats from match score details.
        """
        self._init_player(winner)
        self._init_player(loser)

        w_games = score_details.get("w_games", 12)
        l_games = score_details.get("l_games", 8)
        w_sets = score_details.get("w_sets", 2)
        l_sets = score_details.get("l_sets", 0)

        # Estimate service games: roughly half the games served by each player
        w_serv_games = (w_games + l_games) // 2 + (1 if w_games > l_games else 0)
        l_serv_games = (w_games + l_games) - w_serv_games

        # Breaks estimated from set differentials
        # Winner breaks Loser in at least w_sets times (typically w_sets + extra breaks)
        w_breaks = max(1, w_sets + (w_games - l_games - w_sets) // 2)
        # Loser breaks Winner in at least l_sets times
        l_breaks = max(0, l_sets)

        # Winner holds = w_serv_games - l_breaks
        w_holds = max(1, w_serv_games - l_breaks)
        # Loser holds = l_serv_games - w_breaks
        l_holds = max(0, l_serv_games - w_breaks)

        # Update Winner
        self._update_record(winner, w_holds, w_serv_games, w_breaks, l_serv_games, surface)
        # Update Loser
        self._update_record(loser, l_holds, l_serv_games, l_breaks, w_serv_games, surface)

    def _update_record(
        self,
        player: str,
        holds: int,
        serv_games: int,
        breaks: int,
        ret_games: int,
        surface: str
    ):
        p = self.player_stats[player]
        p["service_games_won"] += holds
        p["service_games_total"] += serv_games
        p["return_games_won"] += breaks
        p["return_games_total"] += ret_games

        if surface not in p["surfaces"]:
            p["surfaces"][surface] = {
                "service_games_won": 39,
                "service_games_total": 50,
                "return_games_won": 11,
                "return_games_total": 50,
            }
        ps = p["surfaces"][surface]
        ps["service_games_won"] += holds
        ps["service_games_total"] += serv_games
        ps["return_games_won"] += breaks
        ps["return_games_total"] += ret_games

    def get_player_serve_return(self, player: str, surface: str = "Hard") -> Dict:
        """
        Retrieve hold rate, break rate, and overall serve/return dominance.
        """
        if player not in self.player_stats:
            return {
                "hold_pct": round(self.baseline_hold * 100, 1),
                "break_pct": round(self.baseline_break * 100, 1),
                "surface_hold_pct": round(self.baseline_hold * 100, 1),
                "surface_break_pct": round(self.baseline_break * 100, 1),
                "dominance_index": 1.0,
            }

        p = self.player_stats[player]
        overall_hold = p["service_games_won"] / max(1, p["service_games_total"])
        overall_break = p["return_games_won"] / max(1, p["return_games_total"])

        surf_data = p["surfaces"].get(surface)
        if surf_data and surf_data["service_games_total"] > 10:
            surf_hold = surf_data["service_games_won"] / surf_data["service_games_total"]
            surf_break = surf_data["return_games_won"] / surf_data["return_games_total"]
        else:
            surf_hold = overall_hold
            surf_break = overall_break

        dominance_index = (overall_hold + overall_break) / (1.0 - overall_hold + 1.0 - overall_break)

        return {
            "hold_pct": round(overall_hold * 100, 1),
            "break_pct": round(overall_break * 100, 1),
            "surface_hold_pct": round(surf_hold * 100, 1),
            "surface_break_pct": round(surf_break * 100, 1),
            "dominance_index": round(dominance_index, 2),
        }

    def compute_matchup_matrix(self, p1: str, p2: str, surface: str = "Hard") -> Dict:
        """
        Matchup interaction:
        Expected P1 Hold Rate = P1 Surface Hold % * (1 - P2 Surface Break %) / Average
        Expected P2 Hold Rate = P2 Surface Hold % * (1 - P1 Surface Break %) / Average
        """
        sr1 = self.get_player_serve_return(p1, surface)
        sr2 = self.get_player_serve_return(p2, surface)

        h1 = sr1["surface_hold_pct"] / 100.0
        b1 = sr1["surface_break_pct"] / 100.0
        h2 = sr2["surface_hold_pct"] / 100.0
        b2 = sr2["surface_break_pct"] / 100.0

        # Projected game hold rates in direct matchup
        exp_p1_hold = min(0.99, max(0.40, (h1 + (1.0 - b2)) / 2.0))
        exp_p2_hold = min(0.99, max(0.40, (h2 + (1.0 - b1)) / 2.0))

        # Expected break rates in direct matchup
        exp_p1_break = 1.0 - exp_p2_hold
        exp_p2_break = 1.0 - exp_p1_hold

        return {
            "p1_hold_pct": sr1["hold_pct"],
            "p1_break_pct": sr1["break_pct"],
            "p2_hold_pct": sr2["hold_pct"],
            "p2_break_pct": sr2["break_pct"],
            "p1_surface_hold_pct": sr1["surface_hold_pct"],
            "p1_surface_break_pct": sr1["surface_break_pct"],
            "p2_surface_hold_pct": sr2["surface_hold_pct"],
            "p2_surface_break_pct": sr2["surface_break_pct"],
            "projected_p1_hold_rate": round(exp_p1_hold * 100, 1),
            "projected_p2_hold_rate": round(exp_p2_hold * 100, 1),
            "projected_p1_break_rate": round(exp_p1_break * 100, 1),
            "projected_p2_break_rate": round(exp_p2_break * 100, 1),
            "serve_advantage_diff": round((exp_p1_hold - exp_p2_hold) * 100, 1),
            "return_advantage_diff": round((exp_p1_break - exp_p2_break) * 100, 1),
        }

