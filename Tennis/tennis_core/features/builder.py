"""Assembles symmetrical feature vectors for model training and live match inference."""
import logging
import math
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from tennis_core.config import PROCESSED_DATA_DIR
from tennis_core.data.player_profiles import get_player_age
from tennis_core.data.preprocessor import played_only
from tennis_core.data.sackmann_loader import SackmannRollingStats, load_cached_sackmann
from tennis_core.features.elo import TennisEloEngine
from tennis_core.features.h2h import TennisH2HEngine
from tennis_core.features.form import TennisFormEngine
from tennis_core.features.serve_return import TennisServeReturnEngine
from tennis_core.utils.helpers import normalize_player_name, normalize_surface, parse_score_details, strip_accents

logger = logging.getLogger(__name__)

# Bump whenever feature definitions change; models from an older schema are retrained, not compared.
FEATURE_SCHEMA_VERSION = 3
# Rank used for unranked/unknown players, identical in training (preprocessor) and inference.
UNRANKED_RANK = 250.0

# Sackmann rate -> feature name
_SACK_FEATURES = {
    "ace_rate": "ace_rate_diff",
    "df_rate": "df_rate_diff",
    "first_serve_pct": "first_serve_pct_diff",
    "first_serve_won_pct": "first_serve_won_pct_diff",
    "bp_save_pct": "bp_save_diff",
    "bp_conversion_pct": "bp_conversion_diff",
    "return_points_won_pct": "return_points_won_diff",
}
_MIRROR_SWAPS = (("p1_name", "p2_name"), ("p1_odds", "p2_odds"), ("p1_surface_exp", "p2_surface_exp"))
_MIRROR_SAME = {"match_date", "surface", "h2h_matches"}
_MIRROR_NEGATE = {"log_rank_ratio"}  # antisymmetric features whose names do not end in _diff


def mirror_row(row: Dict) -> Dict:
    """The same match seen from the other player's side: swap p1/p2 fields and negate every *_diff."""
    out = {}
    for key, value in row.items():
        if key in _MIRROR_SAME:
            out[key] = value
        elif key.endswith("_diff") or key in _MIRROR_NEGATE:
            out[key] = -value
        elif not any(key in pair for pair in _MIRROR_SWAPS):
            raise KeyError(f"mirror_row does not know how to mirror feature {key!r}")
    for a, b in _MIRROR_SWAPS:
        if a in row or b in row:
            out[a], out[b] = row.get(b), row.get(a)
    return out


def _sack_diffs(s1: Optional[Dict], s2: Optional[Dict]) -> Dict[str, float]:
    """Serve/return differences; NaN when either player has no Sackmann history (LightGBM treats it as missing)."""
    return {feat: (s1[stat] - s2[stat]) if (s1 and s2) else float("nan") for stat, feat in _SACK_FEATURES.items()}


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
    # Real serve/return stats from Jeff Sackmann data
    "ace_rate_diff",
    "df_rate_diff",
    "first_serve_pct_diff",
    "first_serve_won_pct_diff",
    "bp_save_diff",
    "bp_conversion_diff",
    "return_points_won_diff",
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
        self.schema_version = FEATURE_SCHEMA_VERSION

        # Jeff Sackmann serve/return stats: built leak-free during training, then reduced to the
        # latest per-(player, surface) averages that inference needs.
        self.sackmann_latest: Dict[Tuple[str, str], Dict[str, float]] = {}
        self._sackmann_name_map: Dict[str, str] = {}  # short_name -> sackmann_full_name

    def _build_sackmann_name_map(self, sackmann_df: pd.DataFrame):
        """Build mapping from 'Lastname F.' format to Sackmann full names."""
        all_names = set(sackmann_df["winner_name"].unique()) | set(sackmann_df["loser_name"].unique())
        for full_name in all_names:
            if not isinstance(full_name, str) or not full_name.strip():
                continue
            parts = full_name.strip().split()
            if len(parts) >= 2:
                # "Carlos Alcaraz" -> "Alcaraz C."
                short = f"{' '.join(parts[1:])} {parts[0][0]}."
                self._sackmann_name_map[strip_accents(short).lower()] = full_name
                self._sackmann_name_map[strip_accents(full_name).lower()] = full_name

    def _resolve_sackmann_name(self, player_name: str) -> str:
        """Resolve a player name from tennis-data format to Sackmann format."""
        if not player_name:
            return player_name
        key = strip_accents(player_name).lower().strip()
        return getattr(self, "_sackmann_name_map", {}).get(key, player_name)

    def _sackmann_stats(self, player_name: str, surface: str,
                        rolling: Optional[SackmannRollingStats] = None) -> Optional[Dict[str, float]]:
        """Serve/return averages known before the current match (training) or now (inference)."""
        name = self._resolve_sackmann_name(player_name)
        if rolling is not None:
            return rolling.get(name, surface)
        return getattr(self, "sackmann_latest", {}).get((name, str(surface).lower()))

    def process_historical_matches(self, df: pd.DataFrame, state_only: bool = False) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Iterates chronologically through matches, generating pre-match feature vectors
        and updating internal state dynamically. Returns symmetrical (X, y) training dataset.
        Every feature uses only information available before the match.
        With ``state_only=True`` only the engines are updated (fast daily refresh); X/y are empty.
        """
        logger.info(f"Processing {len(df)} matches for {self.circuit.upper()} feature generation...")
        df = played_only(df).sort_values(by="tourney_date", kind="mergesort").reset_index(drop=True)

        rolling = None
        sackmann_df = load_cached_sackmann(self.circuit)
        if sackmann_df is not None and not sackmann_df.empty:
            self._build_sackmann_name_map(sackmann_df)
            rolling = SackmannRollingStats(sackmann_df)
            logger.info(f"Using {len(sackmann_df)} Sackmann {self.circuit.upper()} matches for serve/return stats")
        self.career_highs = {}

        feature_rows = []
        labels = []

        for _, row in df.iterrows():
            w_name = row["winner_name"]
            l_name = row["loser_name"]
            surface = row["surface"]
            date = row["tourney_date"]
            self.last_known_date = date
            level = row.get("tourney_level", "A")

            w_rank = float(row.get("winner_rank", UNRANKED_RANK))
            l_rank = float(row.get("loser_rank", UNRANKED_RANK))
            self.current_ranks[w_name] = w_rank
            self.current_ranks[l_name] = l_rank
            # Career-best ranking so far (the ranking at match time is published before the match)
            for name, rank in ((w_name, w_rank), (l_name, l_rank)):
                if rank > 0:
                    self.career_highs[name] = min(self.career_highs.get(name, rank), rank)
            w_career_best = self.career_highs.get(w_name, w_rank)
            l_career_best = self.career_highs.get(l_name, l_rank)

            if not state_only:
                # 1. COMPUTE Pre-Match Metrics for Both Players
                w_elo = self.elo_engine.get_overall_elo(w_name)
                l_elo = self.elo_engine.get_overall_elo(l_name)
                w_surf_elo = self.elo_engine.get_surface_elo(w_name, surface)
                l_surf_elo = self.elo_engine.get_surface_elo(l_name, surface)
                w_eff_surf_elo = self.elo_engine.get_effective_surface_elo(w_name, surface)
                l_eff_surf_elo = self.elo_engine.get_effective_surface_elo(l_name, surface)
                w_surf_exp = self.elo_engine.get_surface_match_count(w_name, surface)
                l_surf_exp = self.elo_engine.get_surface_match_count(l_name, surface)

                w_form = self.form_engine.get_player_form(w_name, date, surface)
                l_form = self.form_engine.get_player_form(l_name, date, surface)
                sr_matrix = self.serve_return_engine.compute_matchup_matrix(w_name, l_name, surface)
                h2h = self.h2h_engine.get_h2h_stats(w_name, l_name, surface)

                w_age = get_player_age(w_name, date.date() if hasattr(date, "date") else None) or 26
                l_age = get_player_age(l_name, date.date() if hasattr(date, "date") else None) or 26

                if rolling is not None:
                    rolling.advance_to(date)
                w_sack = self._sackmann_stats(w_name, surface, rolling)
                l_sack = self._sackmann_stats(l_name, surface, rolling)

                # Pre-match prices (Bet365, else Pinnacle): evaluation baseline only, never a model feature
                w_odds, l_odds = row.get("winner_odds"), row.get("loser_odds")
                if not (pd.notna(w_odds) and pd.notna(l_odds)):
                    w_odds, l_odds = row.get("pinnacle_winner_odds"), row.get("pinnacle_loser_odds")

                # Symmetrical Sample A: P1 = Winner, P2 = Loser (Target = 1); sample B is its mirror image
                row_a = {
                    "match_date": date,
                    "p1_name": w_name,
                    "p2_name": l_name,
                    "p1_odds": w_odds,
                    "p2_odds": l_odds,
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
                    **_sack_diffs(w_sack, l_sack),
                }
                feature_rows.append(row_a)
                labels.append(1)
                feature_rows.append(mirror_row(row_a))
                labels.append(0)

            # 2. UPDATE Internal Engines with Match Outcome & Detailed Score
            score = row.get("score")
            details = parse_score_details(score) if isinstance(score, str) and score.strip() else None
            tourney = row.get("tourney_name", "Tournament")

            self.elo_engine.update_match(winner=w_name, loser=l_name, surface=surface, tourney_level=level, date=date)
            if details is not None:
                self.serve_return_engine.record_match_stats(winner=w_name, loser=l_name, surface=surface, score_details=details)
            self.h2h_engine.record_match(
                winner=w_name, loser=l_name, surface=surface, date=date,
                w_sets=details["w_sets"] if details else 0, l_sets=details["l_sets"] if details else 0,
                w_games=details["w_games"] if details else 0, l_games=details["l_games"] if details else 0,
            )
            for player, opponent, won in ((w_name, l_name, True), (l_name, w_name, False)):
                if details is None:
                    self.form_engine.record_match(player=player, won=won, surface=surface, date=date,
                                                  opponent=opponent, tourney_name=tourney)
                    continue
                self.form_engine.record_match(
                    player=player, won=won, surface=surface, date=date,
                    opponent=opponent, tourney_name=tourney, score=score,
                    sets_won=details["w_sets"] if won else details["l_sets"],
                    sets_lost=details["l_sets"] if won else details["w_sets"],
                    games_won=details["w_games"] if won else details["l_games"],
                    games_lost=details["l_games"] if won else details["w_games"],
                    tiebreaks_won=details["w_tiebreaks_won"] if won else details["tiebreaks_played"] - details["w_tiebreaks_won"],
                    tiebreaks_played=details["tiebreaks_played"],
                    deciding_set=details["deciding_set"],
                    straight_sets=details["straight_sets"] if won else False,
                )

        if rolling is not None:
            rolling.ingest_all()
            self.sackmann_latest = rolling.snapshot()

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

        # Rankings as the data knows them (the ranking at the player's latest match, from tennis-data or
        # carried forward through ESPN results): the same source as in training. A hand-kept table of
        # "official" rankings used to take precedence here; it was years out of date (Sakkari #10 and
        # Svitolina #28 in October 2026, against #33 and #9) and manufactured fake value.
        p1_true_rank = p1_rank if (p1_rank and p1_rank > 0) else self.current_ranks.get(p1)
        p2_true_rank = p2_rank if (p2_rank and p2_rank > 0) else self.current_ranks.get(p2)

        # Imputed ranks ONLY for internal ML feature calculation (same constant as training)
        r1_imputed = p1_true_rank if p1_true_rank is not None else UNRANKED_RANK
        r2_imputed = p2_true_rank if p2_true_rank is not None else UNRANKED_RANK

        c_best1 = self.career_highs.get(p1, p1_true_rank)
        c_best2 = self.career_highs.get(p2, p2_true_rank)

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

        # Real serve/return stats from Jeff Sackmann data (None when the player has no history)
        p1_sack = self._sackmann_stats(p1, surf)
        p2_sack = self._sackmann_stats(p2, surf)

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
            # Real serve/return stats diffs
            **_sack_diffs(p1_sack, p2_sack),
        }
        
        # Rank-anchored prior for unestablished players (< 15 matches on tour)
        def get_rank_prior(rank):
            if rank and rank > 0:
                return round(2100.0 - 250.0 * math.log10(max(1.0, float(rank))), 1)
            return 1250.0

        p1_matches = self.elo_engine.match_counts.get(p1, 0)
        p2_matches = self.elo_engine.match_counts.get(p2, 0)
        p1_provisional = p1_matches < 15
        p2_provisional = p2_matches < 15

        w1 = min(1.0, p1_matches / 15.0)
        w2 = min(1.0, p2_matches / 15.0)
        prior1 = get_rank_prior(p1_true_rank)
        prior2 = get_rank_prior(p2_true_rank)

        cal_elo1 = (w1 * elo1) + ((1.0 - w1) * prior1) if has_history1 else prior1
        cal_elo2 = (w2 * elo2) + ((1.0 - w2) * prior2) if has_history2 else prior2
        cal_surf_elo1 = (w1 * surf_elo1) + ((1.0 - w1) * prior1) if has_history1 else prior1
        cal_surf_elo2 = (w2 * surf_elo2) + ((1.0 - w2) * prior2) if has_history2 else prior2

        # Raw stats for UI display — calibrated against tour baselines
        raw_context = {
            "p1_name": p1_display,
            "p2_name": p2_display,
            "surface": surf,
            "p1_has_history": has_history1,
            "p2_has_history": has_history2,
            "p1_provisional": p1_provisional,
            "p2_provisional": p2_provisional,
            "p1_match_count": p1_matches,
            "p2_match_count": p2_matches,
            "p1_age": p1_age if p1_age is not None else None,
            "p2_age": p2_age if p2_age is not None else None,
            "p1_elo": round(cal_elo1, 1),
            "p2_elo": round(cal_elo2, 1),
            "p1_surface_elo": round(cal_surf_elo1, 1),
            "p2_surface_elo": round(cal_surf_elo2, 1),
            "p1_eff_surface_elo": round(eff_surf_elo1, 1) if has_history1 else None,
            "p2_eff_surface_elo": round(eff_surf_elo2, 1) if has_history2 else None,
            "p1_rank": int(p1_true_rank) if p1_true_rank is not None else None,
            "p2_rank": int(p2_true_rank) if p2_true_rank is not None else None,
            "p1_career_high": int(c_best1) if c_best1 is not None else None,
            "p2_career_high": int(c_best2) if c_best2 is not None else None,
            "p1_form_5": round(form1["form_win_rate_5"] * 100, 1) if has_history1 else None,
            "p2_form_5": round(form2["form_win_rate_5"] * 100, 1) if has_history2 else None,
            "p1_sets_win_rate": round(form1["sets_win_ratio_10"] * 100, 1) if has_history1 else None,
            "p2_sets_win_rate": round(form2["sets_win_ratio_10"] * 100, 1) if has_history2 else None,
            "p1_games_win_rate": round(form1["games_win_ratio_10"] * 100, 1) if has_history1 else None,
            "p2_games_win_rate": round(form2["games_win_ratio_10"] * 100, 1) if has_history2 else None,
            "p1_dominance_ratio": round(form1["dominance_ratio_10"], 2) if has_history1 else None,
            "p2_dominance_ratio": round(form2["dominance_ratio_10"], 2) if has_history2 else None,
            "p1_deciding_set_win_rate": round(form1["deciding_set_win_rate"] * 100, 1) if has_history1 else None,
            "p2_deciding_set_win_rate": round(form2["deciding_set_win_rate"] * 100, 1) if has_history2 else None,
            "p1_tiebreak_win_rate": round(form1["tiebreak_win_rate"] * 100, 1) if has_history1 else None,
            "p2_tiebreak_win_rate": round(form2["tiebreak_win_rate"] * 100, 1) if has_history2 else None,
            "p1_hold_pct": sr_matrix["p1_hold_pct"] if has_history1 else None,
            "p2_hold_pct": sr_matrix["p2_hold_pct"] if has_history2 else None,
            "p1_break_pct": sr_matrix["p1_break_pct"] if has_history1 else None,
            "p2_break_pct": sr_matrix["p2_break_pct"] if has_history2 else None,
            "p1_surface_hold_pct": sr_matrix["p1_surface_hold_pct"] if has_history1 else None,
            "p2_surface_hold_pct": sr_matrix["p2_surface_hold_pct"] if has_history2 else None,
            "p1_surface_break_pct": sr_matrix["p1_surface_break_pct"] if has_history1 else None,
            "p2_surface_break_pct": sr_matrix["p2_surface_break_pct"] if has_history2 else None,
            "projected_p1_hold_rate": sr_matrix["projected_p1_hold_rate"],
            "projected_p2_hold_rate": sr_matrix["projected_p2_hold_rate"],
            "projected_p1_break_rate": sr_matrix["projected_p1_break_rate"],
            "projected_p2_break_rate": sr_matrix["projected_p2_break_rate"],
            "p1_surface_form": round(form1["surface_form_1y"] * 100, 1) if has_history1 else None,
            "p2_surface_form": round(form2["surface_form_1y"] * 100, 1) if has_history2 else None,
            "h2h_p1_wins": h2h["p1_wins"],
            "h2h_p2_wins": h2h["p2_wins"],
            "h2h_p1_sets": h2h.get("p1_sets", 0),
            "h2h_p2_sets": h2h.get("p2_sets", 0),
            "h2h_p1_games": h2h.get("p1_games", 0),
            "h2h_p2_games": h2h.get("p2_games", 0),
            "h2h_total": h2h["total_matches"],
            "h2h_surf_p1_wins": h2h["p1_surface_wins"],
            "p1_recent_matches": self.form_engine.get_recent_matches(p1, limit=5) if has_history1 else [],
            "p2_recent_matches": self.form_engine.get_recent_matches(p2, limit=5) if has_history2 else [],
            "p1_ace_rate": round(p1_sack["ace_rate"] * 100, 1) if (p1_sack and (p1_sack or {}).get("ace_rate", 0) > 0) else None,
            "p2_ace_rate": round(p2_sack["ace_rate"] * 100, 1) if (p2_sack and (p2_sack or {}).get("ace_rate", 0) > 0) else None,
            "p1_df_rate": round(p1_sack["df_rate"] * 100, 1) if (p1_sack and (p1_sack or {}).get("df_rate", 0) > 0) else None,
            "p2_df_rate": round(p2_sack["df_rate"] * 100, 1) if (p2_sack and (p2_sack or {}).get("df_rate", 0) > 0) else None,
            "p1_first_serve_pct": round(p1_sack["first_serve_pct"] * 100, 1) if (p1_sack and (p1_sack or {}).get("first_serve_pct", 0) > 0) else None,
            "p2_first_serve_pct": round(p2_sack["first_serve_pct"] * 100, 1) if (p2_sack and (p2_sack or {}).get("first_serve_pct", 0) > 0) else None,
            "p1_first_serve_won_pct": round(p1_sack["first_serve_won_pct"] * 100, 1) if (p1_sack and (p1_sack or {}).get("first_serve_won_pct", 0) > 0) else None,
            "p2_first_serve_won_pct": round(p2_sack["first_serve_won_pct"] * 100, 1) if (p2_sack and (p2_sack or {}).get("first_serve_won_pct", 0) > 0) else None,
            "p1_bp_save_pct": round(p1_sack["bp_save_pct"] * 100, 1) if (p1_sack and (p1_sack or {}).get("bp_save_pct", 0) > 0) else None,
            "p2_bp_save_pct": round(p2_sack["bp_save_pct"] * 100, 1) if (p2_sack and (p2_sack or {}).get("bp_save_pct", 0) > 0) else None,
            "p1_bp_conversion_pct": round(p1_sack["bp_conversion_pct"] * 100, 1) if (p1_sack and (p1_sack or {}).get("bp_conversion_pct", 0) > 0) else None,
            "p2_bp_conversion_pct": round(p2_sack["bp_conversion_pct"] * 100, 1) if (p2_sack and (p2_sack or {}).get("bp_conversion_pct", 0) > 0) else None,
            "p1_return_points_won_pct": round(p1_sack["return_points_won_pct"] * 100, 1) if (p1_sack and (p1_sack or {}).get("return_points_won_pct", 0) > 0) else None,
            "p2_return_points_won_pct": round(p2_sack["return_points_won_pct"] * 100, 1) if (p2_sack and (p2_sack or {}).get("return_points_won_pct", 0) > 0) else None,
        }
        
        return {"features": feat, "context": raw_context}
