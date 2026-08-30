"""Assembles symmetrical feature vectors for model training and live match inference."""
import logging
import math
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from tennis_core.config import PROCESSED_DATA_DIR
from tennis_core.data.preprocessor import clean_match_data, compute_career_best_rankings, load_raw_matches
from tennis_core.data.player_profiles import get_player_age
from tennis_core.features.elo import TennisEloEngine
from tennis_core.features.h2h import TennisH2HEngine
from tennis_core.features.form import TennisFormEngine
from tennis_core.features.serve_return import TennisServeReturnEngine
from tennis_core.utils.helpers import normalize_player_name, normalize_surface, parse_score_details

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "elo_diff",
    "surface_elo_diff",
    "effective_surface_elo_diff",
    "rank_diff",
    "log_rank_ratio",
    "career_high_rank_diff",
    "form_5_diff",
    "form_10_diff",
    "form_20_diff",
    "surface_form_diff",
    "sets_ratio_diff",
    "games_ratio_diff",
    "dominance_ratio_diff",
    "surface_game_ratio_diff",
    "deciding_set_diff",
    "tiebreak_diff",
    "serve_hold_diff",
    "return_break_diff",
    "projected_hold_diff",
    "projected_break_diff",
    "days_rest_diff",
    "fatigue_30d_diff",
    "h2h_win_rate_diff",
    "h2h_surface_win_rate_diff",
    "h2h_matches",
    "h2h_game_diff",
    "h2h_set_diff",
    "surface_exp_diff",
    "age_diff",
    "p1_surface_exp",
    "p2_surface_exp",
]


class TennisFeaturePipeline:
    """End-to-end pipeline to compute features from match stream and build inference features."""

    def __init__(self, circuit: str):
        self.circuit = circuit.lower()
        self.elo_engine = TennisEloEngine()
        self.h2h_engine = TennisH2HEngine()
        self.form_engine = TennisFormEngine()
        self.serve_return_engine = TennisServeReturnEngine(
            baseline_hold=0.79 if self.circuit == "atp" else 0.65,
            baseline_break=0.21 if self.circuit == "atp" else 0.35
        )
        self.career_highs: Dict[str, float] = {}
        self.current_ranks: Dict[str, float] = {}
        self.last_known_date: Optional[pd.Timestamp] = None

    def process_historical_matches(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Iterates chronologically through matches, generating pre-match feature vectors
        and updating internal state dynamically. Returns symmetrical (X, y) training dataset.
        """
        logger.info(f"Processing {len(df)} matches for {self.circuit.upper()} feature generation...")
        self.career_highs = compute_career_best_rankings(df)

        feature_rows = []
        labels = []

        for idx, row in df.iterrows():
            w_name = row["winner_name"]
            l_name = row["loser_name"]
            surface = row["surface"]
            date = row["tourney_date"]
            self.last_known_date = date
            level = row.get("tourney_level", "A")
            score = str(row.get("score", "6-4 6-4"))

            w_rank = row.get("winner_rank", 250.0)
            l_rank = row.get("loser_rank", 250.0)
            self.current_ranks[w_name] = w_rank
            self.current_ranks[l_name] = l_rank

            # 1. COMPUTE Pre-Match Metrics for Both Players
            w_elo = self.elo_engine.get_overall_elo(w_name)
            l_elo = self.elo_engine.get_overall_elo(l_name)

            w_surf_elo = self.elo_engine.get_surface_elo(w_name, surface)
            l_surf_elo = self.elo_engine.get_surface_elo(l_name, surface)

            w_eff_surf_elo = self.elo_engine.get_effective_surface_elo(w_name, surface)
            l_eff_surf_elo = self.elo_engine.get_effective_surface_elo(l_name, surface)

            w_surf_exp = self.elo_engine.get_surface_match_count(w_name, surface)
            l_surf_exp = self.elo_engine.get_surface_match_count(l_name, surface)

            w_career_best = self.career_highs.get(w_name, w_rank)
            l_career_best = self.career_highs.get(l_name, l_rank)

            w_form = self.form_engine.get_player_form(w_name, date, surface)
            l_form = self.form_engine.get_player_form(l_name, date, surface)

            sr_matrix = self.serve_return_engine.compute_matchup_matrix(w_name, l_name, surface)

            h2h = self.h2h_engine.get_h2h_stats(w_name, l_name, surface)

            w_age = get_player_age(w_name, date.date() if hasattr(date, "date") else None) or 26
            l_age = get_player_age(l_name, date.date() if hasattr(date, "date") else None) or 26

            # Symmetrical Sample A: P1 = Winner, P2 = Loser (Target = 1)
            row_a = {
                "match_date": date,
                "p1_name": w_name,
                "p2_name": l_name,
                "surface": surface,
                "elo_diff": w_elo - l_elo,
                "surface_elo_diff": w_surf_elo - l_surf_elo,
                "effective_surface_elo_diff": w_eff_surf_elo - l_eff_surf_elo,
                "rank_diff": l_rank - w_rank,
                "log_rank_ratio": math.log(max(1.0, l_rank)) - math.log(max(1.0, w_rank)),
                "career_high_rank_diff": l_career_best - w_career_best,
                "form_5_diff": w_form["form_win_rate_5"] - l_form["form_win_rate_5"],
                "form_10_diff": w_form["form_win_rate_10"] - l_form["form_win_rate_10"],
                "form_20_diff": w_form["form_win_rate_20"] - l_form["form_win_rate_20"],
                "surface_form_diff": w_form["surface_form_1y"] - l_form["surface_form_1y"],
                "sets_ratio_diff": w_form["sets_win_ratio_10"] - l_form["sets_win_ratio_10"],
                "games_ratio_diff": w_form["games_win_ratio_10"] - l_form["games_win_ratio_10"],
                "dominance_ratio_diff": w_form["dominance_ratio_10"] - l_form["dominance_ratio_10"],
                "surface_game_ratio_diff": w_form["surface_game_ratio_1y"] - l_form["surface_game_ratio_1y"],
                "deciding_set_diff": w_form["deciding_set_win_rate"] - l_form["deciding_set_win_rate"],
                "tiebreak_diff": w_form["tiebreak_win_rate"] - l_form["tiebreak_win_rate"],
                "serve_hold_diff": sr_matrix["p1_surface_hold_pct"] - sr_matrix["p2_surface_hold_pct"],
                "return_break_diff": sr_matrix["p1_surface_break_pct"] - sr_matrix["p2_surface_break_pct"],
                "projected_hold_diff": sr_matrix["projected_p1_hold_rate"] - sr_matrix["projected_p2_hold_rate"],
                "projected_break_diff": sr_matrix["projected_p1_break_rate"] - sr_matrix["projected_p2_break_rate"],
                "days_rest_diff": l_form["days_rest"] - w_form["days_rest"],
                "fatigue_30d_diff": l_form["recent_match_count_30d"] - w_form["recent_match_count_30d"],
                "h2h_win_rate_diff": h2h["p1_win_rate"] - (1.0 - h2h["p1_win_rate"]),
                "h2h_surface_win_rate_diff": h2h["p1_surface_win_rate"] - (1.0 - h2h["p1_surface_win_rate"]),
                "h2h_matches": h2h["total_matches"],
                "h2h_game_diff": h2h.get("p1_games", 0) - h2h.get("p2_games", 0),
                "h2h_set_diff": h2h.get("p1_sets", 0) - h2h.get("p2_sets", 0),
                "surface_exp_diff": w_surf_exp - l_surf_exp,
                "age_diff": l_age - w_age,
                "p1_surface_exp": w_surf_exp,
                "p2_surface_exp": l_surf_exp,
            }
            feature_rows.append(row_a)
            labels.append(1)

            # Symmetrical Sample B: P1 = Loser, P2 = Winner (Target = 0)
            row_b = {
                "match_date": date,
                "p1_name": l_name,
                "p2_name": w_name,
                "surface": surface,
                "elo_diff": -(w_elo - l_elo),
                "surface_elo_diff": -(w_surf_elo - l_surf_elo),
                "effective_surface_elo_diff": -(w_eff_surf_elo - l_eff_surf_elo),
                "rank_diff": -(l_rank - w_rank),
                "log_rank_ratio": -(math.log(max(1.0, l_rank)) - math.log(max(1.0, w_rank))),
                "career_high_rank_diff": -(l_career_best - w_career_best),
                "form_5_diff": -(w_form["form_win_rate_5"] - l_form["form_win_rate_5"]),
                "form_10_diff": -(w_form["form_win_rate_10"] - l_form["form_win_rate_10"]),
                "form_20_diff": -(w_form["form_win_rate_20"] - l_form["form_win_rate_20"]),
                "surface_form_diff": -(w_form["surface_form_1y"] - l_form["surface_form_1y"]),
                "sets_ratio_diff": -(w_form["sets_win_ratio_10"] - l_form["sets_win_ratio_10"]),
                "games_ratio_diff": -(w_form["games_win_ratio_10"] - l_form["games_win_ratio_10"]),
                "dominance_ratio_diff": -(w_form["dominance_ratio_10"] - l_form["dominance_ratio_10"]),
                "surface_game_ratio_diff": -(w_form["surface_game_ratio_1y"] - l_form["surface_game_ratio_1y"]),
                "deciding_set_diff": -(w_form["deciding_set_win_rate"] - l_form["deciding_set_win_rate"]),
                "tiebreak_diff": -(w_form["tiebreak_win_rate"] - l_form["tiebreak_win_rate"]),
                "serve_hold_diff": -(sr_matrix["p1_surface_hold_pct"] - sr_matrix["p2_surface_hold_pct"]),
                "return_break_diff": -(sr_matrix["p1_surface_break_pct"] - sr_matrix["p2_surface_break_pct"]),
                "projected_hold_diff": -(sr_matrix["projected_p1_hold_rate"] - sr_matrix["projected_p2_hold_rate"]),
                "projected_break_diff": -(sr_matrix["projected_p1_break_rate"] - sr_matrix["projected_p2_break_rate"]),
                "days_rest_diff": -(l_form["days_rest"] - w_form["days_rest"]),
                "fatigue_30d_diff": -(l_form["recent_match_count_30d"] - w_form["recent_match_count_30d"]),
                "h2h_win_rate_diff": -row_a["h2h_win_rate_diff"],
                "h2h_surface_win_rate_diff": -row_a["h2h_surface_win_rate_diff"],
                "h2h_matches": h2h["total_matches"],
                "h2h_game_diff": -(h2h.get("p1_games", 0) - h2h.get("p2_games", 0)),
                "h2h_set_diff": -(h2h.get("p1_sets", 0) - h2h.get("p2_sets", 0)),
                "surface_exp_diff": -(w_surf_exp - l_surf_exp),
                "age_diff": -(l_age - w_age),
                "p1_surface_exp": l_surf_exp,
                "p2_surface_exp": w_surf_exp,
            }
            feature_rows.append(row_b)
            labels.append(0)

            # 2. UPDATE Internal Engines with Match Outcome & Detailed Score
            score_details = parse_score_details(score)
            tourney = row.get("tourney_name", "Tournament")
            
            self.elo_engine.update_match(winner=w_name, loser=l_name, surface=surface, tourney_level=level, date=date)
            self.serve_return_engine.record_match_stats(winner=w_name, loser=l_name, surface=surface, score_details=score_details)
            self.h2h_engine.record_match(
                winner=w_name, loser=l_name, surface=surface, date=date,
                w_sets=score_details["w_sets"], l_sets=score_details["l_sets"],
                w_games=score_details["w_games"], l_games=score_details["l_games"]
            )
            self.form_engine.record_match(
                player=w_name, won=True, surface=surface, date=date,
                opponent=l_name, tourney_name=tourney, score=score,
                sets_won=score_details["w_sets"], sets_lost=score_details["l_sets"],
                games_won=score_details["w_games"], games_lost=score_details["l_games"],
                tiebreaks_won=score_details["w_tiebreaks_won"], tiebreaks_played=score_details["tiebreaks_played"],
                deciding_set=score_details["deciding_set"], straight_sets=score_details["straight_sets"]
            )
            self.form_engine.record_match(
                player=l_name, won=False, surface=surface, date=date,
                opponent=w_name, tourney_name=tourney, score=score,
                sets_won=score_details["l_sets"], sets_lost=score_details["w_sets"],
                games_won=score_details["l_games"], games_lost=score_details["w_games"],
                tiebreaks_won=score_details["tiebreaks_played"] - score_details["w_tiebreaks_won"],
                tiebreaks_played=score_details["tiebreaks_played"],
                deciding_set=score_details["deciding_set"], straight_sets=False
            )

        X = pd.DataFrame(feature_rows)
        y = pd.Series(labels, name="target")
        logger.info(f"Built symmetrical dataset of shape {X.shape} for {self.circuit.upper()}")
        return X, y

    def build_inference_features(
        self,
        p1_name: str,
        p2_name: str,
        surface: str,
        match_date: Optional[pd.Timestamp] = None,
        p1_rank: Optional[float] = None,
        p2_rank: Optional[float] = None
    ) -> Dict:
        """
        Build feature vector for an upcoming matchup between p1 and p2.
        """
        from tennis_core.utils.helpers import match_player_to_database
        
        p1_display = normalize_player_name(p1_name)
        p2_display = normalize_player_name(p2_name)
        
        # Match against known player identifiers in database
        known_players = list(self.elo_engine.overall_elo.keys())
        p1 = match_player_to_database(p1_name, known_players)
        p2 = match_player_to_database(p2_name, known_players)
        surf = normalize_surface(surface)
        date = match_date if match_date is not None else self.last_known_date

        has_history1 = p1 in self.elo_engine.overall_elo
        has_history2 = p2 in self.elo_engine.overall_elo

        try:
            from tennis_core.data.rankings import get_official_player_rank
        except ImportError:
            try:
                import importlib, sys
                if 'src.data.rankings' in sys.modules:
                    importlib.reload(sys.modules['src.data.rankings'])
                from tennis_core.data.rankings import get_official_player_rank
            except Exception:
                def get_official_player_rank(x): return None, None

        # Check official rankings registry first
        off_rank1, off_ch1 = get_official_player_rank(p1_name)
        if not off_rank1:
            off_rank1, off_ch1 = get_official_player_rank(p1)

        off_rank2, off_ch2 = get_official_player_rank(p2_name)
        if not off_rank2:
            off_rank2, off_ch2 = get_official_player_rank(p2)

        # True known ranks (or None if unranked/unknown)
        p1_true_rank = p1_rank if (p1_rank and p1_rank > 0) else (off_rank1 if off_rank1 is not None else self.current_ranks.get(p1))
        p2_true_rank = p2_rank if (p2_rank and p2_rank > 0) else (off_rank2 if off_rank2 is not None else self.current_ranks.get(p2))

        # Imputed ranks ONLY for internal ML feature mathematical calculation
        r1_imputed = p1_true_rank if p1_true_rank is not None else 350.0
        r2_imputed = p2_true_rank if p2_true_rank is not None else 350.0

        c_best1 = off_ch1 if off_ch1 is not None else self.career_highs.get(p1, p1_true_rank)
        c_best2 = off_ch2 if off_ch2 is not None else self.career_highs.get(p2, p2_true_rank)

        elo1 = self.elo_engine.get_overall_elo(p1)
        elo2 = self.elo_engine.get_overall_elo(p2)
        
        surf_elo1 = self.elo_engine.get_surface_elo(p1, surf)
        surf_elo2 = self.elo_engine.get_surface_elo(p2, surf)
        
        eff_surf_elo1 = self.elo_engine.get_effective_surface_elo(p1, surf)
        eff_surf_elo2 = self.elo_engine.get_effective_surface_elo(p2, surf)
        
        surf_exp1 = self.elo_engine.get_surface_match_count(p1, surf)
        surf_exp2 = self.elo_engine.get_surface_match_count(p2, surf)

        h2h = self.h2h_engine.get_h2h_stats(p1, p2, surf)
        form1 = self.form_engine.get_player_form(p1, date, surf)
        form2 = self.form_engine.get_player_form(p2, date, surf)

        sr_matrix = self.serve_return_engine.compute_matchup_matrix(p1, p2, surf)

        p1_age = get_player_age(p1_name) or get_player_age(p1)
        p2_age = get_player_age(p2_name) or get_player_age(p2)
        age_a = p1_age or 26
        age_b = p2_age or 26

        feat = {
            "elo_diff": elo1 - elo2,
            "surface_elo_diff": surf_elo1 - surf_elo2,
            "effective_surface_elo_diff": eff_surf_elo1 - eff_surf_elo2,
            "rank_diff": r2_imputed - r1_imputed,
            "log_rank_ratio": math.log(max(1.0, r2_imputed)) - math.log(max(1.0, r1_imputed)),
            "career_high_rank_diff": (c_best2 or r2_imputed) - (c_best1 or r1_imputed),
            "form_5_diff": form1["form_win_rate_5"] - form2["form_win_rate_5"],
            "form_10_diff": form1["form_win_rate_10"] - form2["form_win_rate_10"],
            "form_20_diff": form1["form_win_rate_20"] - form2["form_win_rate_20"],
            "surface_form_diff": form1["surface_form_1y"] - form2["surface_form_1y"],
            "sets_ratio_diff": form1["sets_win_ratio_10"] - form2["sets_win_ratio_10"],
            "games_ratio_diff": form1["games_win_ratio_10"] - form2["games_win_ratio_10"],
            "dominance_ratio_diff": form1["dominance_ratio_10"] - form2["dominance_ratio_10"],
            "surface_game_ratio_diff": form1["surface_game_ratio_1y"] - form2["surface_game_ratio_1y"],
            "deciding_set_diff": form1["deciding_set_win_rate"] - form2["deciding_set_win_rate"],
            "tiebreak_diff": form1["tiebreak_win_rate"] - form2["tiebreak_win_rate"],
            "serve_hold_diff": sr_matrix["p1_surface_hold_pct"] - sr_matrix["p2_surface_hold_pct"],
            "return_break_diff": sr_matrix["p1_surface_break_pct"] - sr_matrix["p2_surface_break_pct"],
            "projected_hold_diff": sr_matrix["projected_p1_hold_rate"] - sr_matrix["projected_p2_hold_rate"],
            "projected_break_diff": sr_matrix["projected_p1_break_rate"] - sr_matrix["projected_p2_break_rate"],
            "days_rest_diff": form2["days_rest"] - form1["days_rest"],
            "fatigue_30d_diff": form2["recent_match_count_30d"] - form1["recent_match_count_30d"],
            "h2h_win_rate_diff": h2h["p1_win_rate"] - (1.0 - h2h["p1_win_rate"]),
            "h2h_surface_win_rate_diff": h2h["p1_surface_win_rate"] - (1.0 - h2h["p1_surface_win_rate"]),
            "h2h_matches": h2h["total_matches"],
            "h2h_game_diff": h2h.get("p1_games", 0) - h2h.get("p2_games", 0),
            "h2h_set_diff": h2h.get("p1_sets", 0) - h2h.get("p2_sets", 0),
            "surface_exp_diff": surf_exp1 - surf_exp2,
            "age_diff": age_b - age_a,
            "p1_surface_exp": surf_exp1,
            "p2_surface_exp": surf_exp2,
        }
        
        # Raw stats for UI display — NO invented values
        raw_context = {
            "p1_name": p1_display,
            "p2_name": p2_display,
            "surface": surf,
            "p1_has_history": has_history1,
            "p2_has_history": has_history2,
            "p1_age": p1_age if p1_age is not None else "N/A",
            "p2_age": p2_age if p2_age is not None else "N/A",
            "p1_elo": round(elo1, 1) if has_history1 else "Unrated (No history)",
            "p2_elo": round(elo2, 1) if has_history2 else "Unrated (No history)",
            "p1_surface_elo": round(surf_elo1, 1) if has_history1 else "Unrated",
            "p2_surface_elo": round(surf_elo2, 1) if has_history2 else "Unrated",
            "p1_eff_surface_elo": round(eff_surf_elo1, 1) if has_history1 else "Unrated",
            "p2_eff_surface_elo": round(eff_surf_elo2, 1) if has_history2 else "Unrated",
            "p1_rank": int(p1_true_rank) if p1_true_rank is not None else "Unranked / N/A",
            "p2_rank": int(p2_true_rank) if p2_true_rank is not None else "Unranked / N/A",
            "p1_career_high": int(c_best1) if c_best1 is not None else "N/A",
            "p2_career_high": int(c_best2) if c_best2 is not None else "N/A",
            "p1_form_5": round(form1["form_win_rate_5"] * 100, 1) if has_history1 else "N/A",
            "p2_form_5": round(form2["form_win_rate_5"] * 100, 1) if has_history2 else "N/A",
            "p1_sets_win_rate": round(form1["sets_win_ratio_10"] * 100, 1) if has_history1 else "N/A",
            "p2_sets_win_rate": round(form2["sets_win_ratio_10"] * 100, 1) if has_history2 else "N/A",
            "p1_games_win_rate": round(form1["games_win_ratio_10"] * 100, 1) if has_history1 else "N/A",
            "p2_games_win_rate": round(form2["games_win_ratio_10"] * 100, 1) if has_history2 else "N/A",
            "p1_dominance_ratio": round(form1["dominance_ratio_10"], 2) if has_history1 else "N/A",
            "p2_dominance_ratio": round(form2["dominance_ratio_10"], 2) if has_history2 else "N/A",
            "p1_deciding_set_win_rate": round(form1["deciding_set_win_rate"] * 100, 1) if has_history1 else "N/A",
            "p2_deciding_set_win_rate": round(form2["deciding_set_win_rate"] * 100, 1) if has_history2 else "N/A",
            "p1_tiebreak_win_rate": round(form1["tiebreak_win_rate"] * 100, 1) if has_history1 else "N/A",
            "p2_tiebreak_win_rate": round(form2["tiebreak_win_rate"] * 100, 1) if has_history2 else "N/A",
            "p1_hold_pct": sr_matrix["p1_hold_pct"] if has_history1 else "N/A",
            "p2_hold_pct": sr_matrix["p2_hold_pct"] if has_history2 else "N/A",
            "p1_break_pct": sr_matrix["p1_break_pct"] if has_history1 else "N/A",
            "p2_break_pct": sr_matrix["p2_break_pct"] if has_history2 else "N/A",
            "p1_surface_hold_pct": sr_matrix["p1_surface_hold_pct"] if has_history1 else "N/A",
            "p2_surface_hold_pct": sr_matrix["p2_surface_hold_pct"] if has_history2 else "N/A",
            "p1_surface_break_pct": sr_matrix["p1_surface_break_pct"] if has_history1 else "N/A",
            "p2_surface_break_pct": sr_matrix["p2_surface_break_pct"] if has_history2 else "N/A",
            "projected_p1_hold_rate": sr_matrix["projected_p1_hold_rate"],
            "projected_p2_hold_rate": sr_matrix["projected_p2_hold_rate"],
            "projected_p1_break_rate": sr_matrix["projected_p1_break_rate"],
            "projected_p2_break_rate": sr_matrix["projected_p2_break_rate"],
            "p1_surface_form": round(form1["surface_form_1y"] * 100, 1) if has_history1 else "N/A",
            "p2_surface_form": round(form2["surface_form_1y"] * 100, 1) if has_history2 else "N/A",
            "h2h_p1_wins": h2h["p1_wins"],
            "h2h_p2_wins": h2h["p2_wins"],
            "h2h_p1_sets": h2h.get("p1_sets", 0),
            "h2h_p2_sets": h2h.get("p2_sets", 0),
            "h2h_p1_games": h2h.get("p1_games", 0),
            "h2h_p2_games": h2h.get("p2_games", 0),
            "h2h_total": h2h["total_matches"],
            "h2h_surf_p1_wins": h2h["p1_surface_wins"],
            "h2h_surf_p2_wins": h2h["p2_surface_wins"],
            "p1_recent_matches": self.form_engine.get_recent_matches(p1, limit=5) if has_history1 else [],
            "p2_recent_matches": self.form_engine.get_recent_matches(p2, limit=5) if has_history2 else [],
        }
        
        return {"features": feat, "context": raw_context}
