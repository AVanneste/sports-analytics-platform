"""Player form, momentum, games and sets dynamics, and fatigue tracking engine."""
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from tennis_core.config import FORM_SHORT_WINDOW, FORM_MEDIUM_WINDOW, FORM_LONG_WINDOW, SURFACE_FORM_DAYS


class TennisFormEngine:
    """Tracks chronological match history for each player to compute form, games, sets, and fatigue metrics."""

    def __init__(self):
        # player_name -> list of match records dicts
        self.player_history: Dict[str, List[Dict]] = {}

    def get_player_form(self, player: str, current_date: pd.Timestamp, surface: str) -> Dict:
        """
        Compute comprehensive pre-match form metrics including match, set, and game dynamics.
        """
        history = self.player_history.get(player, [])
        
        default_metrics = {
            "form_win_rate_5": 0.5,
            "form_win_rate_10": 0.5,
            "form_win_rate_20": 0.5,
            "surface_form_1y": 0.5,
            "sets_win_ratio_10": 0.5,
            "games_win_ratio_10": 0.5,
            "dominance_ratio_10": 1.0,
            "surface_game_ratio_1y": 0.5,
            "deciding_set_win_rate": 0.5,
            "tiebreak_win_rate": 0.5,
            "straight_sets_rate_10": 0.35,
            "days_rest": 14.0,
            "recent_match_count_30d": 0,
        }

        if not history:
            return default_metrics

        # Filter strictly before current_date to avoid lookahead bias
        past_matches = [m for m in history if m["date"] <= current_date]
        if not past_matches:
            return default_metrics

        # Rest days calculation
        last_match_date = past_matches[-1]["date"]
        days_rest = max(1.0, (current_date - last_match_date).total_seconds() / 86400.0)
        days_rest = min(60.0, days_rest)

        # Rolling match win rates
        def calc_win_rate(matches: List[Dict], count: int) -> float:
            sub = matches[-count:]
            if not sub:
                return 0.5
            wins = sum(1 for m in sub if m["won"])
            return wins / len(sub)

        form_5 = calc_win_rate(past_matches, FORM_SHORT_WINDOW)
        form_10 = calc_win_rate(past_matches, FORM_MEDIUM_WINDOW)
        form_20 = calc_win_rate(past_matches, FORM_LONG_WINDOW)

        # Sets and Games over last 10 matches
        last_10 = past_matches[-10:]
        total_sets_won = sum(m.get("sets_won", 1 if m["won"] else 0) for m in last_10)
        total_sets_lost = sum(m.get("sets_lost", 0 if m["won"] else 1) for m in last_10)
        total_sets = total_sets_won + total_sets_lost
        sets_ratio_10 = (total_sets_won / total_sets) if total_sets > 0 else 0.5

        total_games_won = sum(m.get("games_won", 12 if m["won"] else 8) for m in last_10)
        total_games_lost = sum(m.get("games_lost", 8 if m["won"] else 12) for m in last_10)
        total_games = total_games_won + total_games_lost
        games_ratio_10 = (total_games_won / total_games) if total_games > 0 else 0.5
        dominance_ratio_10 = (total_games_won / max(1, total_games_lost)) if total_games_lost > 0 else 1.5

        # Straight sets frequency
        straight_wins = sum(1 for m in last_10 if m.get("straight_sets", False) and m["won"])
        straight_sets_rate_10 = straight_wins / len(last_10) if last_10 else 0.35

        # Deciding sets win rate
        decider_matches = [m for m in past_matches[-20:] if m.get("deciding_set", False)]
        if decider_matches:
            decider_wins = sum(1 for m in decider_matches if m["won"])
            deciding_set_win_rate = decider_wins / len(decider_matches)
        else:
            deciding_set_win_rate = form_10

        # Tiebreak win rate
        tb_matches = [m for m in past_matches[-20:] if m.get("tiebreaks_played", 0) > 0]
        if tb_matches:
            tb_won = sum(m.get("tiebreaks_won", 0) for m in tb_matches)
            tb_tot = sum(m.get("tiebreaks_played", 1) for m in tb_matches)
            tb_rate = tb_won / tb_tot if tb_tot > 0 else 0.5
        else:
            tb_rate = 0.5

        # Surface-specific form & games in the last 365 days
        cutoff_date = current_date - pd.Timedelta(days=SURFACE_FORM_DAYS)
        surf_matches = [
            m for m in past_matches
            if m["surface"] == surface and m["date"] >= cutoff_date
        ]
        
        if surf_matches:
            surf_wins = sum(1 for m in surf_matches if m["won"])
            surf_form_1y = surf_wins / len(surf_matches)
            
            s_gw = sum(m.get("games_won", 12 if m["won"] else 8) for m in surf_matches)
            s_gl = sum(m.get("games_lost", 8 if m["won"] else 12) for m in surf_matches)
            s_tot = s_gw + s_gl
            surface_game_ratio_1y = (s_gw / s_tot) if s_tot > 0 else 0.5
        else:
            surf_form_1y = form_10
            surface_game_ratio_1y = games_ratio_10

        # Matches played in last 30 days (fatigue density)
        recent_30d_cutoff = current_date - pd.Timedelta(days=30)
        matches_30d = sum(1 for m in past_matches if m["date"] >= recent_30d_cutoff)

        return {
            "form_win_rate_5": form_5,
            "form_win_rate_10": form_10,
            "form_win_rate_20": form_20,
            "surface_form_1y": surf_form_1y,
            "sets_win_ratio_10": sets_ratio_10,
            "games_win_ratio_10": games_ratio_10,
            "dominance_ratio_10": dominance_ratio_10,
            "surface_game_ratio_1y": surface_game_ratio_1y,
            "deciding_set_win_rate": deciding_set_win_rate,
            "tiebreak_win_rate": tb_rate,
            "straight_sets_rate_10": straight_sets_rate_10,
            "days_rest": days_rest,
            "recent_match_count_30d": matches_30d,
        }

    def record_match(
        self,
        player: str,
        won: bool,
        surface: str,
        date: pd.Timestamp,
        opponent: str = "Opponent",
        tourney_name: str = "Tournament",
        score: str = "6-4 6-4",
        sets_won: int = 2,
        sets_lost: int = 0,
        games_won: int = 12,
        games_lost: int = 8,
        tiebreaks_won: int = 0,
        tiebreaks_played: int = 0,
        deciding_set: bool = False,
        straight_sets: bool = True,
    ):
        """Append match outcome to player history."""
        if player not in self.player_history:
            self.player_history[player] = []
        
        self.player_history[player].append({
            "date": date,
            "won": won,
            "surface": surface,
            "opponent": opponent,
            "tourney_name": tourney_name,
            "score": score,
            "sets_won": sets_won,
            "sets_lost": sets_lost,
            "games_won": games_won,
            "games_lost": games_lost,
            "tiebreaks_won": tiebreaks_won,
            "tiebreaks_played": tiebreaks_played,
            "deciding_set": deciding_set,
            "straight_sets": straight_sets,
        })

    def get_recent_matches(self, player: str, limit: int = 5) -> List[Dict]:
        """Retrieve recent match log for display."""
        history = self.player_history.get(player, [])
        if not history:
            return []
        
        recent = sorted(history, key=lambda x: x["date"], reverse=True)[:limit]
        formatted = []
        for m in recent:
            date_str = m["date"].strftime("%Y-%m-%d") if hasattr(m["date"], "strftime") else str(m["date"])[:10]
            formatted.append({
                "date": date_str,
                "won": m["won"],
                "result": "W" if m["won"] else "L",
                "opponent": m.get("opponent", "Opponent"),
                "tourney": m.get("tourney_name", "Tourney"),
                "surface": m.get("surface", "Hard"),
                "score": m.get("score", "N/A"),
                "sets": f"{m.get('sets_won', 0)}-{m.get('sets_lost', 0)}",
                "games": f"{m.get('games_won', 0)}-{m.get('games_lost', 0)}",
            })
        return formatted
