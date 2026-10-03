"""Master Feature Engineering Pipeline for Football Matches with Corners, Cards & Referee Analytics."""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from football_core.features.elo import FootballEloEngine
from football_core.features.dixon_coles import DixonColesEngine
from football_core.features.form import TeamFormTracker
from football_core.features.h2h import HeadToHeadTracker
from football_core.features.referee import RefereeStatsEngine
from football_core.features.props import project_cards, project_corners

logger = logging.getLogger(__name__)

# Bump whenever feature definitions change; bundles from an older schema are retrained, not compared.
FEATURE_SCHEMA_VERSION = 2


def _stat(row: Any, col: str) -> Optional[float]:
    """Numeric match statistic, or None when it is missing from the source data."""
    value = row.get(col)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _total(*values: Optional[float]) -> Optional[float]:
    return None if any(v is None for v in values) else float(sum(values))


def _clean_referee(value: Any) -> Optional[str]:
    if not isinstance(value, str) or value.strip().lower() in ("", "nan", "none"):
        return None
    return value.strip()


class FootballFeaturePipeline:
    """End-to-end feature pipeline processing matches in strict chronological order."""

    def __init__(self, league_key: str):
        self.league_key = league_key
        self.elo_engine = FootballEloEngine()
        self.dixon_coles_engine = DixonColesEngine()
        self.form_tracker = TeamFormTracker()
        self.h2h_tracker = HeadToHeadTracker()
        self.referee_engine = RefereeStatsEngine()
        self.feature_names: List[str] = []
        self.schema_version = FEATURE_SCHEMA_VERSION

    def _match_features(self, home_team: str, away_team: str, date: pd.Timestamp,
                        referee: Optional[str]) -> Dict[str, float]:
        """Pre-match feature vector from the current engine state (used for training and inference)."""
        # 1. Elo
        home_elo = self.elo_engine.get_rating(home_team)
        away_elo = self.elo_engine.get_rating(away_team)
        elo_p_home, elo_p_away = self.elo_engine.compute_expected_probability(home_elo, away_elo)
        elo_diff = (home_elo + self.elo_engine.home_adv) - away_elo

        # 2. Dixon-Coles expectancies (training loads the snapshot fitted before this match's month)
        dc_preds = self.dixon_coles_engine.predict_match_probabilities(home_team, away_team)

        # 3. Rolling form (5 & 10 matches) and venue-specific form
        h_form_5 = self.form_tracker.get_team_rolling_features(home_team, date, n_matches=5)
        a_form_5 = self.form_tracker.get_team_rolling_features(away_team, date, n_matches=5)
        h_form_10 = self.form_tracker.get_team_rolling_features(home_team, date, n_matches=10)
        a_form_10 = self.form_tracker.get_team_rolling_features(away_team, date, n_matches=10)
        h_venue_form = self.form_tracker.get_venue_specific_form(home_team, date, venue="H", n_matches=5)
        a_venue_form = self.form_tracker.get_venue_specific_form(away_team, date, venue="A", n_matches=5)

        # 4. Head to head
        h2h_feats = self.h2h_tracker.get_h2h_features(home_team, away_team, date)

        # 5. Referee profile
        ref_profile = self.referee_engine.get_referee_profile(referee, date)
        ref_strictness = ref_profile["strictness_index"]

        # 6./7. Corners and cards projections (shared with the live predictor)
        corners = project_corners(
            h_form_5.get("corners_for_last5"), h_form_5.get("corners_against_last5"),
            a_form_5.get("corners_for_last5"), a_form_5.get("corners_against_last5"),
            elo_diff=elo_diff,
        )
        cards = project_cards(h_form_5.get("cards_for_last5"), a_form_5.get("cards_for_last5"),
                              ref_strictness=ref_strictness)

        return {
            # Elo
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": elo_diff,
            "elo_prob_home": elo_p_home,
            "elo_prob_away": elo_p_away,

            # Goals Dixon Coles
            "dc_lambda_home": dc_preds["lambda_home"],
            "dc_mu_away": dc_preds["mu_away"],
            "dc_expected_total_goals": dc_preds["lambda_home"] + dc_preds["mu_away"],
            "dc_prob_home": dc_preds["prob_home"],
            "dc_prob_draw": dc_preds["prob_draw"],
            "dc_prob_away": dc_preds["prob_away"],
            "dc_prob_over25": dc_preds["prob_over25"],
            "dc_prob_btts": dc_preds["prob_btts_yes"],

            # Rolling Form (5 Matches)
            "home_ppg_l5": h_form_5["ppg_last5"],
            "away_ppg_l5": a_form_5["ppg_last5"],
            "diff_ppg_l5": h_form_5["ppg_last5"] - a_form_5["ppg_last5"],
            "home_gd_l5": h_form_5["gd_per_game_last5"],
            "away_gd_l5": a_form_5["gd_per_game_last5"],
            "home_tsr_l5": h_form_5["tsr_last5"],
            "away_tsr_l5": a_form_5["tsr_last5"],
            "home_sotr_l5": h_form_5["sotr_last5"],
            "away_sotr_l5": a_form_5["sotr_last5"],
            "home_corners_diff_l5": h_form_5["corners_diff_last5"],
            "away_corners_diff_l5": a_form_5["corners_diff_last5"],

            # Corners Specific
            "exp_total_corners": corners["expected"],
            "home_corners_avg_l5": h_form_5["corners_for_last5"],
            "away_corners_avg_l5": a_form_5["corners_for_last5"],
            "prob_corners_o95_poisson": corners["over95"],
            "prob_corners_o105_poisson": corners["over105"],

            # Cards & Referee Specific
            "ref_strictness_index": ref_strictness,
            "ref_avg_cards": ref_profile["avg_cards"],
            "exp_total_cards": cards["expected"],
            "home_cards_avg_l5": h_form_5["cards_for_last5"],
            "away_cards_avg_l5": a_form_5["cards_for_last5"],
            "home_fouls_avg_l5": h_form_5["fouls_for_last5"],
            "away_fouls_avg_l5": a_form_5["fouls_for_last5"],
            "prob_cards_o35_poisson": cards["over35"],
            "prob_cards_o45_poisson": cards["over45"],

            # Rolling Form (10 Matches)
            "home_ppg_l10": h_form_10["ppg_last10"],
            "away_ppg_l10": a_form_10["ppg_last10"],
            "diff_ppg_l10": h_form_10["ppg_last10"] - a_form_10["ppg_last10"],
            "home_gd_l10": h_form_10["gd_per_game_last10"],
            "away_gd_l10": a_form_10["gd_per_game_last10"],

            # Venue Form
            "home_venue_ppg_l5": h_venue_form["home_ppg_last5"],
            "away_venue_ppg_l5": a_venue_form["away_ppg_last5"],
            "diff_venue_ppg": h_venue_form["home_ppg_last5"] - a_venue_form["away_ppg_last5"],

            # Rest & Congestion
            "home_rest_days": h_form_5["days_rest"],
            "away_rest_days": a_form_5["days_rest"],
            "rest_diff": h_form_5["days_rest"] - a_form_5["days_rest"],
            "home_matches_21d": h_form_5["matches_last_21d"],
            "away_matches_21d": a_form_5["matches_last_21d"],

            # Head to Head
            "h2h_matches_count": h2h_feats["h2h_matches_count"],
            "h2h_home_win_rate": h2h_feats["h2h_home_win_rate"],
            "h2h_draw_rate": h2h_feats["h2h_draw_rate"],
            "h2h_away_win_rate": h2h_feats["h2h_away_win_rate"],
            "h2h_avg_total_goals": h2h_feats["h2h_avg_total_goals"],
        }

    def process_historical_matches(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Process historical matches chronologically.
        Returns:
            X: Feature matrix DataFrame
            y: Targets and metadata (corner/card targets are NaN when the source lacks those stats)
        """
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        sorted_df = df.sort_values(by="Date", kind="mergesort").reset_index(drop=True)

        # Pre-compute Dixon-Coles at monthly boundaries (no lookahead bias)
        logger.info(f"[{self.league_key}] Pre-computing monthly Dixon-Coles snapshots...")
        self.dixon_coles_engine.precompute_monthly_snapshots(sorted_df)

        feature_rows = []
        target_rows = []

        for _, row in sorted_df.iterrows():
            date = row["Date"]
            home_team = row["HomeTeam"]
            away_team = row["AwayTeam"]
            fthg = int(row["FTHG"])
            ftag = int(row["FTAG"])
            referee = _clean_referee(row.get("Referee"))

            self.dixon_coles_engine.load_snapshot_for_date(date)
            feature_rows.append(self._match_features(home_team, away_team, date, referee))

            hc, ac = _stat(row, "HC"), _stat(row, "AC")
            hy, ay, hr, ar = (_stat(row, c) for c in ("HY", "AY", "HR", "AR"))
            hf, af = _stat(row, "HF"), _stat(row, "AF")
            total_corners = _total(hc, ac)
            total_cards = _total(hy, ay, hr, ar)

            target_rows.append({
                "target_1x2": row["target_1x2"],
                "target_over25": row["target_over25"],
                "target_btts": row["target_btts"],
                "target_corners_over95": np.nan if total_corners is None else int(total_corners > 9.5),
                "target_corners_over105": np.nan if total_corners is None else int(total_corners > 10.5),
                "target_cards_over35": np.nan if total_cards is None else int(total_cards > 3.5),
                "target_cards_over45": np.nan if total_cards is None else int(total_cards > 4.5),
                "Date": date,
                "Season": row.get("Season", ""),
                "HomeTeam": home_team,
                "AwayTeam": away_team,
                "FTHG": fthg,
                "FTAG": ftag,
                "total_corners": np.nan if total_corners is None else total_corners,
                "total_cards": np.nan if total_cards is None else total_cards,
                "odds_home": row.get("odds_home"),
                "odds_draw": row.get("odds_draw"),
                "odds_away": row.get("odds_away"),
                "odds_over25": row.get("odds_over25"),
                "odds_under25": row.get("odds_under25"),
            })

            # Post-match updates (missing statistics are passed through as missing)
            self.elo_engine.update_match(home_team, away_team, fthg, ftag, date=date)
            self.form_tracker.record_match(
                date=date, home_team=home_team, away_team=away_team, fthg=fthg, ftag=ftag,
                hs=_stat(row, "HS"), as_=_stat(row, "AS"), hst=_stat(row, "HST"), ast=_stat(row, "AST"),
                hc=hc, ac=ac, hf=hf, af=af, hy=hy, ay=ay, hr=hr, ar=ar,
            )
            self.h2h_tracker.record_match(date, home_team, away_team, fthg, ftag)
            self.referee_engine.record_match(
                referee_name=referee,
                date=date,
                yellows=_total(hy, ay),
                reds=_total(hr, ar),
                fouls=_total(hf, af),
            )

        X = pd.DataFrame(feature_rows)
        y = pd.DataFrame(target_rows)
        self.feature_names = list(X.columns)

        # Fit Dixon-Coles on ALL data for inference (upcoming match predictions)
        self.dixon_coles_engine.fit_from_matches(sorted_df)

        return X, y

    def build_inference_features(
        self,
        home_team: str,
        away_team: str,
        match_date: Optional[pd.Timestamp] = None,
        referee: Optional[str] = None,
        **_unused_market_odds: Any,
    ) -> pd.DataFrame:
        """Feature vector for an upcoming match from the current state (market odds are never features)."""
        date = pd.Timestamp(match_date) if match_date is not None else pd.Timestamp.now()
        if date.tzinfo is not None:
            date = date.tz_convert(None)
        return pd.DataFrame([self._match_features(home_team, away_team, date, _clean_referee(referee))])
