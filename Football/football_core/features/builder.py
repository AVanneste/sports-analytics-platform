"""Master Feature Engineering Pipeline for Football Matches with Corners, Cards & Referee Analytics."""
import logging
import numpy as np
import pandas as pd
from scipy.stats import poisson
from typing import Dict, Tuple, List, Optional

from football_core.features.elo import FootballEloEngine
from football_core.features.dixon_coles import DixonColesEngine
from football_core.features.form import TeamFormTracker
from football_core.features.h2h import HeadToHeadTracker
from football_core.features.referee import RefereeStatsEngine
from football_core.utils.helpers import remove_vig_multiplicative

logger = logging.getLogger(__name__)


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

    def process_historical_matches(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Process historical matches chronologically.
        Returns:
            X: Feature matrix DataFrame
            y: Target DataFrame (target_1x2, target_over25, target_btts, target_corners_over95, target_cards_over35, target_cards_over45)
        """
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        sorted_df = df.sort_values(by="Date").reset_index(drop=True)
        self.dixon_coles_engine.fit_from_matches(sorted_df)

        feature_rows = []
        target_rows = []

        for idx, row in sorted_df.iterrows():
            date = row["Date"]
            home_team = row["HomeTeam"]
            away_team = row["AwayTeam"]
            fthg = int(row["FTHG"])
            ftag = int(row["FTAG"])
            referee = row.get("Referee")

            # 1. Elo Features
            home_elo = self.elo_engine.get_rating(home_team)
            away_elo = self.elo_engine.get_rating(away_team)
            elo_p_home, elo_p_away = self.elo_engine.compute_expected_probability(home_elo, away_elo)
            elo_diff = (home_elo + self.elo_engine.home_adv) - away_elo

            # 2. Dixon-Coles Expectancy Features
            dc_preds = self.dixon_coles_engine.predict_match_probabilities(home_team, away_team)

            # 3. Rolling Form (5 & 10 Matches)
            h_form_5 = self.form_tracker.get_team_rolling_features(home_team, date, n_matches=5)
            a_form_5 = self.form_tracker.get_team_rolling_features(away_team, date, n_matches=5)
            h_form_10 = self.form_tracker.get_team_rolling_features(home_team, date, n_matches=10)
            a_form_10 = self.form_tracker.get_team_rolling_features(away_team, date, n_matches=10)

            # Venue Specific Form
            h_venue_form = self.form_tracker.get_venue_specific_form(home_team, date, venue="H", n_matches=5)
            a_venue_form = self.form_tracker.get_venue_specific_form(away_team, date, venue="A", n_matches=5)

            # 4. H2H Features
            h2h_feats = self.h2h_tracker.get_h2h_features(home_team, away_team, date)

            # 5. Referee Profile & Disciplinary Factor
            ref_profile = self.referee_engine.get_referee_profile(referee, date)
            ref_strictness = ref_profile["strictness_index"]

            # 6. Corners Projections & Poisson Expectancy
            proj_home_corners = (h_form_5["corners_for_last5"] + a_form_5["corners_against_last5"]) / 2.0
            proj_away_corners = (a_form_5["corners_for_last5"] + h_form_5["corners_against_last5"]) / 2.0
            exp_total_corners = proj_home_corners + proj_away_corners
            prob_corners_o95_poisson = float(1.0 - poisson.cdf(9, max(1.0, exp_total_corners)))
            prob_corners_o105_poisson = float(1.0 - poisson.cdf(10, max(1.0, exp_total_corners)))

            # 7. Cards & Fouls Projections with Referee Strictness
            proj_home_cards = (h_form_5["cards_for_last5"] + a_form_5["cards_against_last5"]) / 2.0
            proj_away_cards = (a_form_5["cards_for_last5"] + h_form_5["cards_against_last5"]) / 2.0
            exp_total_cards = (proj_home_cards + proj_away_cards) * ref_strictness
            prob_cards_o35_poisson = float(1.0 - poisson.cdf(3, max(0.5, exp_total_cards)))
            prob_cards_o45_poisson = float(1.0 - poisson.cdf(4, max(0.5, exp_total_cards)))

            # 8. Market Odds
            o_h = row.get("odds_home")
            o_d = row.get("odds_draw")
            o_a = row.get("odds_away")
            if pd.notna(o_h) and pd.notna(o_d) and pd.notna(o_a) and o_h > 1.0 and o_d > 1.0 and o_a > 1.0:
                vig_free = remove_vig_multiplicative([o_h, o_d, o_a])
                market_p_home, market_p_draw, market_p_away = vig_free[0], vig_free[1], vig_free[2]
            else:
                market_p_home, market_p_draw, market_p_away = elo_p_home * 0.7, 0.25, elo_p_away * 0.7

            feat = {
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
                "exp_total_corners": exp_total_corners,
                "home_corners_avg_l5": h_form_5["corners_for_last5"],
                "away_corners_avg_l5": a_form_5["corners_for_last5"],
                "prob_corners_o95_poisson": prob_corners_o95_poisson,
                "prob_corners_o105_poisson": prob_corners_o105_poisson,

                # Cards & Referee Specific
                "ref_strictness_index": ref_strictness,
                "ref_avg_cards": ref_profile["avg_cards"],
                "exp_total_cards": exp_total_cards,
                "home_cards_avg_l5": h_form_5["cards_for_last5"],
                "away_cards_avg_l5": a_form_5["cards_for_last5"],
                "home_fouls_avg_l5": h_form_5["fouls_for_last5"],
                "away_fouls_avg_l5": a_form_5["fouls_for_last5"],
                "prob_cards_o35_poisson": prob_cards_o35_poisson,
                "prob_cards_o45_poisson": prob_cards_o45_poisson,

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

                # Market Implied Probabilities
                "market_prob_home": market_p_home,
                "market_prob_draw": market_p_draw,
                "market_prob_away": market_p_away,
            }

            feature_rows.append(feat)

            # Targets
            match_hc = row.get("HC", 5.0)
            match_ac = row.get("AC", 4.5)
            match_corners = (match_hc if pd.notna(match_hc) else 5.0) + (match_ac if pd.notna(match_ac) else 4.5)

            match_hy = row.get("HY", 1.8)
            match_ay = row.get("AY", 2.0)
            match_hr = row.get("HR", 0.05)
            match_ar = row.get("AR", 0.08)
            match_cards = (match_hy if pd.notna(match_hy) else 1.8) + \
                          (match_ay if pd.notna(match_ay) else 2.0) + \
                          (match_hr if pd.notna(match_hr) else 0.05) + \
                          (match_ar if pd.notna(match_ar) else 0.08)

            match_hf = row.get("HF", 11.0)
            match_af = row.get("AF", 11.5)
            match_fouls = (match_hf if pd.notna(match_hf) else 11.0) + (match_af if pd.notna(match_af) else 11.5)

            target_rows.append({
                "target_1x2": row["target_1x2"],
                "target_over25": row["target_over25"],
                "target_btts": row["target_btts"],
                "target_corners_over95": int(match_corners > 9.5),
                "target_corners_over105": int(match_corners > 10.5),
                "target_cards_over35": int(match_cards > 3.5),
                "target_cards_over45": int(match_cards > 4.5),
                "Date": date,
                "Season": row.get("Season", ""),
                "HomeTeam": home_team,
                "AwayTeam": away_team,
                "FTHG": fthg,
                "FTAG": ftag,
                "total_corners": match_corners,
                "total_cards": match_cards,
                "odds_home": row.get("odds_home"),
                "odds_draw": row.get("odds_draw"),
                "odds_away": row.get("odds_away"),
            })

            # Post-Match Updates
            self.elo_engine.update_match(home_team, away_team, fthg, ftag, date=date)
            self.form_tracker.record_match(
                date=date,
                home_team=home_team,
                away_team=away_team,
                fthg=fthg,
                ftag=ftag,
                hs=row.get("HS"),
                as_=row.get("AS"),
                hst=row.get("HST"),
                ast=row.get("AST"),
                hc=match_hc,
                ac=match_ac,
                hf=match_hf,
                af=match_af,
                hy=match_hy,
                ay=match_ay,
                hr=match_hr,
                ar=match_ar,
            )
            self.h2h_tracker.record_match(date, home_team, away_team, fthg, ftag)
            self.referee_engine.record_match(
                referee_name=referee,
                date=date,
                yellows=(match_hy if pd.notna(match_hy) else 1.8) + (match_ay if pd.notna(match_ay) else 2.0),
                reds=(match_hr if pd.notna(match_hr) else 0.05) + (match_ar if pd.notna(match_ar) else 0.08),
                fouls=match_fouls,
            )

        X = pd.DataFrame(feature_rows)
        y = pd.DataFrame(target_rows)
        self.feature_names = list(X.columns)

        return X, y

    def build_inference_features(
        self,
        home_team: str,
        away_team: str,
        match_date: Optional[pd.Timestamp] = None,
        referee: Optional[str] = None,
        odds_home: Optional[float] = None,
        odds_draw: Optional[float] = None,
        odds_away: Optional[float] = None,
    ) -> pd.DataFrame:
        """Construct feature vector for an upcoming match using current state."""
        if match_date is None:
            match_date = pd.Timestamp.now()

        # 1. Elo
        home_elo = self.elo_engine.get_rating(home_team)
        away_elo = self.elo_engine.get_rating(away_team)
        elo_p_home, elo_p_away = self.elo_engine.compute_expected_probability(home_elo, away_elo)
        elo_diff = (home_elo + self.elo_engine.home_adv) - away_elo

        # 2. Dixon Coles
        dc_preds = self.dixon_coles_engine.predict_match_probabilities(home_team, away_team)

        # 3. Rolling Form
        h_form_5 = self.form_tracker.get_team_rolling_features(home_team, match_date, n_matches=5)
        a_form_5 = self.form_tracker.get_team_rolling_features(away_team, match_date, n_matches=5)
        h_form_10 = self.form_tracker.get_team_rolling_features(home_team, match_date, n_matches=10)
        a_form_10 = self.form_tracker.get_team_rolling_features(away_team, match_date, n_matches=10)

        h_venue_form = self.form_tracker.get_venue_specific_form(home_team, match_date, venue="H", n_matches=5)
        a_venue_form = self.form_tracker.get_venue_specific_form(away_team, match_date, venue="A", n_matches=5)

        # 4. H2H
        h2h_feats = self.h2h_tracker.get_h2h_features(home_team, away_team, match_date)

        # 5. Referee Profile
        ref_profile = self.referee_engine.get_referee_profile(referee, match_date)
        ref_strictness = ref_profile["strictness_index"]

        # 6. Corners Projections
        proj_home_corners = (h_form_5["corners_for_last5"] + a_form_5["corners_against_last5"]) / 2.0
        proj_away_corners = (a_form_5["corners_for_last5"] + h_form_5["corners_against_last5"]) / 2.0
        exp_total_corners = proj_home_corners + proj_away_corners
        prob_corners_o95_poisson = float(1.0 - poisson.cdf(9, max(1.0, exp_total_corners)))
        prob_corners_o105_poisson = float(1.0 - poisson.cdf(10, max(1.0, exp_total_corners)))

        # 7. Cards Projections
        proj_home_cards = (h_form_5["cards_for_last5"] + a_form_5["cards_against_last5"]) / 2.0
        proj_away_cards = (a_form_5["cards_for_last5"] + h_form_5["cards_against_last5"]) / 2.0
        exp_total_cards = (proj_home_cards + proj_away_cards) * ref_strictness
        prob_cards_o35_poisson = float(1.0 - poisson.cdf(3, max(0.5, exp_total_cards)))
        prob_cards_o45_poisson = float(1.0 - poisson.cdf(4, max(0.5, exp_total_cards)))

        # 8. Market Odds
        if odds_home and odds_draw and odds_away and odds_home > 1.0 and odds_draw > 1.0 and odds_away > 1.0:
            vig_free = remove_vig_multiplicative([odds_home, odds_draw, odds_away])
            market_p_home, market_p_draw, market_p_away = vig_free[0], vig_free[1], vig_free[2]
        else:
            market_p_home, market_p_draw, market_p_away = elo_p_home * 0.7, 0.25, elo_p_away * 0.7

        feat = {
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": elo_diff,
            "elo_prob_home": elo_p_home,
            "elo_prob_away": elo_p_away,

            "dc_lambda_home": dc_preds["lambda_home"],
            "dc_mu_away": dc_preds["mu_away"],
            "dc_expected_total_goals": dc_preds["lambda_home"] + dc_preds["mu_away"],
            "dc_prob_home": dc_preds["prob_home"],
            "dc_prob_draw": dc_preds["prob_draw"],
            "dc_prob_away": dc_preds["prob_away"],
            "dc_prob_over25": dc_preds["prob_over25"],
            "dc_prob_btts": dc_preds["prob_btts_yes"],

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

            "exp_total_corners": exp_total_corners,
            "home_corners_avg_l5": h_form_5["corners_for_last5"],
            "away_corners_avg_l5": a_form_5["corners_for_last5"],
            "prob_corners_o95_poisson": prob_corners_o95_poisson,
            "prob_corners_o105_poisson": prob_corners_o105_poisson,

            "ref_strictness_index": ref_strictness,
            "ref_avg_cards": ref_profile["avg_cards"],
            "exp_total_cards": exp_total_cards,
            "home_cards_avg_l5": h_form_5["cards_for_last5"],
            "away_cards_avg_l5": a_form_5["cards_for_last5"],
            "home_fouls_avg_l5": h_form_5["fouls_for_last5"],
            "away_fouls_avg_l5": a_form_5["fouls_for_last5"],
            "prob_cards_o35_poisson": prob_cards_o35_poisson,
            "prob_cards_o45_poisson": prob_cards_o45_poisson,

            "home_ppg_l10": h_form_10["ppg_last10"],
            "away_ppg_l10": a_form_10["ppg_last10"],
            "diff_ppg_l10": h_form_10["ppg_last10"] - a_form_10["ppg_last10"],
            "home_gd_l10": h_form_10["gd_per_game_last10"],
            "away_gd_l10": a_form_10["gd_per_game_last10"],

            "home_venue_ppg_l5": h_venue_form["home_ppg_last5"],
            "away_venue_ppg_l5": a_venue_form["away_ppg_last5"],
            "diff_venue_ppg": h_venue_form["home_ppg_last5"] - a_venue_form["away_ppg_last5"],

            "home_rest_days": h_form_5["days_rest"],
            "away_rest_days": a_form_5["days_rest"],
            "rest_diff": h_form_5["days_rest"] - a_form_5["days_rest"],
            "home_matches_21d": h_form_5["matches_last_21d"],
            "away_matches_21d": a_form_5["matches_last_21d"],

            "h2h_matches_count": h2h_feats["h2h_matches_count"],
            "h2h_home_win_rate": h2h_feats["h2h_home_win_rate"],
            "h2h_draw_rate": h2h_feats["h2h_draw_rate"],
            "h2h_away_win_rate": h2h_feats["h2h_away_win_rate"],
            "h2h_avg_total_goals": h2h_feats["h2h_avg_total_goals"],

            "market_prob_home": market_p_home,
            "market_prob_draw": market_p_draw,
            "market_prob_away": market_p_away,
        }

        return pd.DataFrame([feat])
