"""Master Predictor Engine for Match Outcomes, Goals, Corners, Cards, Referee Analytics & European Cups."""
import logging
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from scipy.stats import poisson

from football_core.config import LEAGUES, MIN_VALUE_THRESHOLD, DEFAULT_KELLY_FRACTION
from football_core.models.train import load_trained_bundle
from football_core.utils.helpers import normalize_team_name, teams_match, calculate_ev, calculate_kelly_stake, remove_vig_multiplicative

logger = logging.getLogger(__name__)


class FootballPredictor:
    """Multi-league inference engine combining Calibrated LightGBM, Dixon-Coles, Elo, Corners, and Cards."""

    def __init__(self):
        self.bundles: Dict[str, Dict[str, Any]] = {}
        self._load_all_bundles()

    def _load_all_bundles(self):
        """Load pre-trained models and state pipelines for all leagues."""
        for league_key in LEAGUES.keys():
            if LEAGUES[league_key].get("is_cup"):
                continue
            bundle = load_trained_bundle(league_key)
            if bundle:
                self.bundles[league_key] = bundle
                logger.info(f"Loaded predictor bundle for {league_key}")
            else:
                logger.debug(f"No trained bundle found for {league_key}")

    def is_league_ready(self, league_key: str) -> bool:
        if LEAGUES.get(league_key, {}).get("is_cup"):
            return len(self.bundles) > 0
        return league_key in self.bundles

    def get_known_teams(self, league_key: str) -> List[str]:
        """Return list of known teams with ratings in the league or across all leagues for cups."""
        if LEAGUES.get(league_key, {}).get("is_cup"):
            all_teams = set()
            for b in self.bundles.values():
                all_teams.update(b["pipeline"].elo_engine.ratings.keys())
            return sorted(list(all_teams))

        bundle = self.bundles.get(league_key)
        if not bundle:
            return []
        pipeline = bundle["pipeline"]
        return sorted(list(pipeline.elo_engine.ratings.keys()))

    def get_known_referees(self, league_key: str) -> List[str]:
        """Return list of known referees for this league."""
        bundle = self.bundles.get(league_key)
        if not bundle:
            return []
        pipeline = bundle["pipeline"]
        return pipeline.referee_engine.get_all_known_referees()

    def _find_team_profile(self, team_name: str) -> Dict[str, Any]:
        """Search across all domestic bundles to find a team's Elo, Attack, Defense, and Form."""
        norm = normalize_team_name(team_name)
        for l_k, bundle in self.bundles.items():
            pipeline = bundle["pipeline"]
            if norm in pipeline.elo_engine.ratings:
                elo = pipeline.elo_engine.get_rating(norm)
                att = pipeline.dixon_coles_engine.attack_strengths.get(norm, 0.0)
                dfn = pipeline.dixon_coles_engine.defense_strengths.get(norm, 0.0)
                form = pipeline.form_tracker.get_team_rolling_features(norm, pd.Timestamp.now(), n_matches=5)
                return {
                    "league": l_k,
                    "elo": elo,
                    "attack": att,
                    "defense": dfn,
                    "form": form,
                    "pipeline": pipeline,
                    "bundle": bundle,
                }

    def _get_settled_tracker_matches(self) -> List[Dict[str, Any]]:
        """Fetch real settled matches from predictions tracker cache."""
        import json
        from pathlib import Path
        p = Path("Football/data/cache/predictions_tracker.json")
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [d for d in data if d.get("status") == "settled" and d.get("actual_score")]
            except Exception:
                pass
        return []

    def get_team_recent_matches(self, league_key: str, team_name: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return the last n matches for a team with score, opponent, venue, and result (merging 2026 real matches)."""
        from datetime import datetime
        norm = normalize_team_name(team_name)
        bundle = self.bundles.get(league_key)
        if not bundle:
            profile = self._find_team_profile(team_name)
            pipeline = profile.get("pipeline")
        else:
            pipeline = bundle.get("pipeline")
        
        results = []
        if pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(norm, [])
            if not hist and norm != team_name:
                hist = pipeline.form_tracker.team_history.get(team_name, [])
            
            for m in hist:
                d_val = m.get("date")
                d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                results.append({
                    "date": d_str,
                    "venue": "Home" if m.get("venue") == "H" else "Away",
                    "opponent": m.get("opponent", ""),
                    "score": f"{m.get('gf', 0)}-{m.get('ga', 0)}",
                    "gf": m.get("gf", 0),
                    "ga": m.get("ga", 0),
                    "res": m.get("res", "D"),
                    "corners": m.get("corners_for", 0),
                    "cards": m.get("cards_for", 0),
                })

        # Merge newly settled 2026/2027 matches from tracker
        tracker_settled = self._get_settled_tracker_matches()
        for sm in tracker_settled:
            h_sm = sm.get("home_team", "")
            a_sm = sm.get("away_team", "")
            if teams_match(team_name, h_sm) or teams_match(team_name, a_sm):
                is_home = teams_match(team_name, h_sm)
                opp = a_sm if is_home else h_sm
                score_str = sm.get("actual_score", "0-0")
                try:
                    score_parts = score_str.split("-")
                    gf = int(score_parts[0]) if is_home else int(score_parts[1])
                    ga = int(score_parts[1]) if is_home else int(score_parts[0])
                except Exception:
                    gf, ga = 0, 0
                res = "W" if gf > ga else ("L" if ga > gf else "D")
                results.append({
                    "date": (sm.get("date") or "")[:10],
                    "venue": "Home" if is_home else "Away",
                    "opponent": opp,
                    "score": score_str,
                    "gf": gf,
                    "ga": ga,
                    "res": res,
                    "corners": int(sm.get("actual_corners", 9)) // 2,
                    "cards": int(sm.get("actual_cards", 4)) // 2,
                })

        # Deduplicate and sort by date descending
        seen_keys = set()
        unique_results = []
        for r in sorted(results, key=lambda x: str(x.get("date", "")), reverse=True):
            key = f"{r.get('date')}_{r.get('opponent')}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(r)

        return unique_results[:n]

    def get_h2h_matches(self, league_key: str, home_team: str, away_team: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return past head-to-head matches between home_team and away_team (merging 2026 matches)."""
        from datetime import datetime
        norm_h = normalize_team_name(home_team)
        norm_a = normalize_team_name(away_team)
        
        bundle = self.bundles.get(league_key)
        if not bundle:
            profile = self._find_team_profile(home_team)
            pipeline = profile.get("pipeline")
        else:
            pipeline = bundle.get("pipeline")
            
        h2h_list = []
        if pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(norm_h, [])
            for m in hist:
                opp_norm = normalize_team_name(m.get("opponent", ""))
                if teams_match(opp_norm, norm_a) or teams_match(m.get("opponent", ""), away_team):
                    d_val = m.get("date")
                    d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                    is_home = (m.get("venue") == "H")
                    h_score = m.get("gf") if is_home else m.get("ga")
                    a_score = m.get("ga") if is_home else m.get("gf")
                    
                    h2h_list.append({
                        "date": d_str,
                        "home_team": home_team if is_home else away_team,
                        "away_team": away_team if is_home else home_team,
                        "score": f"{h_score}-{a_score}",
                        "h_score": h_score,
                        "a_score": a_score,
                        "winner": home_team if m.get("res") == "W" else (away_team if m.get("res") == "L" else "Draw"),
                    })

        # Merge newly settled 2026/2027 matches from tracker
        tracker_settled = self._get_settled_tracker_matches()
        for sm in tracker_settled:
            h_sm = sm.get("home_team", "")
            a_sm = sm.get("away_team", "")
            is_match = (teams_match(home_team, h_sm) and teams_match(away_team, a_sm)) or (teams_match(home_team, a_sm) and teams_match(away_team, h_sm))
            if is_match:
                d_str = (sm.get("date") or "")[:10]
                score_str = sm.get("actual_score", "0-0")
                winner_str = sm.get("actual_winner", "Draw")
                h2h_list.append({
                    "date": d_str,
                    "home_team": h_sm,
                    "away_team": a_sm,
                    "score": score_str,
                    "h_score": int(score_str.split("-")[0]) if "-" in score_str else 0,
                    "a_score": int(score_str.split("-")[1]) if "-" in score_str else 0,
                    "winner": winner_str,
                })

        seen_keys = set()
        unique_h2h = []
        for r in sorted(h2h_list, key=lambda x: str(x.get("date", "")), reverse=True):
            key = f"{r.get('date')}_{r.get('home_team')}_{r.get('away_team')}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_h2h.append(r)

        return unique_h2h[:n]

    def get_team_summary_stats(self, league_key: str, team_name: str) -> Dict[str, Any]:
        """Compute key summary statistics (model Elo, form, avg goals, clean sheets, over 2.5, btts) strictly from real match data."""
        norm = normalize_team_name(team_name)
        bundle = self.bundles.get(league_key)
        if not bundle:
            profile = self._find_team_profile(team_name)
            pipeline = profile.get("pipeline")
            elo = profile.get("elo")
            att = profile.get("attack")
            dfn = profile.get("defense")
        else:
            pipeline = bundle.get("pipeline")
            elo = pipeline.elo_engine.get_rating(norm) if pipeline and hasattr(pipeline, "elo_engine") else None
            att = pipeline.dixon_coles_engine.attack_strengths.get(norm) if pipeline and hasattr(pipeline, "dixon_coles_engine") else None
            dfn = pipeline.dixon_coles_engine.defense_strengths.get(norm) if pipeline and hasattr(pipeline, "dixon_coles_engine") else None

        # Recent matches strictly from real matches (dataset + settled tracker)
        recent = self.get_team_recent_matches(league_key, team_name, n=5)
        form_seq = [m.get("res") for m in reversed(recent) if m.get("res")]

        hist = pipeline.form_tracker.team_history.get(norm, []) if (pipeline and hasattr(pipeline, "form_tracker")) else []
        if not hist and norm != team_name and pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(team_name, [])

        if hist:
            n_m = len(hist)
            avg_gf = sum(m.get("gf", 0) for m in hist) / n_m
            avg_ga = sum(m.get("ga", 0) for m in hist) / n_m
            clean_sheets = sum(1 for m in hist if m.get("ga", 0) == 0) / n_m
            btts_count = sum(1 for m in hist if m.get("gf", 0) > 0 and m.get("ga", 0) > 0) / n_m
            o25_count = sum(1 for m in hist if (m.get("gf", 0) + m.get("ga", 0)) > 2.5) / n_m
            avg_corners = sum(m.get("corners_for", 0) for m in hist if m.get("corners_for") is not None) / max(1, sum(1 for m in hist if m.get("corners_for") is not None))
            avg_cards = sum(m.get("cards_for", 0) for m in hist if m.get("cards_for") is not None) / max(1, sum(1 for m in hist if m.get("cards_for") is not None))
        else:
            avg_gf = None
            avg_ga = None
            clean_sheets = None
            btts_count = None
            o25_count = None
            avg_corners = None
            avg_cards = None

        if recent:
            n5 = len(recent)
            avg_gf_5 = sum(m.get("gf", 0) for m in recent) / n5
            avg_ga_5 = sum(m.get("ga", 0) for m in recent) / n5
        else:
            avg_gf_5 = None
            avg_ga_5 = None

        return {
            "elo": round(float(elo), 0) if elo is not None else None,
            "attack": round(float(att), 2) if att is not None else None,
            "defense": round(float(dfn), 2) if dfn is not None else None,
            "form": form_seq,
            "avg_gf_season": round(avg_gf, 2) if avg_gf is not None else None,
            "avg_ga_season": round(avg_ga, 2) if avg_ga is not None else None,
            "avg_gf_last5": round(avg_gf_5, 2) if avg_gf_5 is not None else None,
            "avg_ga_last5": round(avg_ga_5, 2) if avg_ga_5 is not None else None,
            "clean_sheet_pct": round(clean_sheets * 100, 1) if clean_sheets is not None else None,
            "btts_pct": round(btts_count * 100, 1) if btts_count is not None else None,
            "o25_pct": round(o25_count * 100, 1) if o25_count is not None else None,
            "avg_corners": round(avg_corners, 1) if avg_corners is not None else None,
            "avg_cards": round(avg_cards, 1) if avg_cards is not None else None,
            "matches_analyzed": len(hist) + len([m for m in recent if "2026" in str(m.get("date"))]),
        }

    def predict_match(
        self,
        league_key: str,
        home_team: str,
        away_team: str,
        referee: Optional[str] = None,
        odds_home: Optional[float] = None,
        odds_draw: Optional[float] = None,
        odds_away: Optional[float] = None,
        odds_over25: Optional[float] = None,
        odds_under25: Optional[float] = None,
        odds_btts_yes: Optional[float] = None,
        odds_btts_no: Optional[float] = None,
        odds_corners_over95: Optional[float] = None,
        odds_corners_under95: Optional[float] = None,
        odds_cards_over35: Optional[float] = None,
        odds_cards_under35: Optional[float] = None,
        match_date: Optional[pd.Timestamp] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive match predictions across 1X2, Goals, BTTS, Corners, and Cards (Domestic & European Cups)."""
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        is_cup = LEAGUES.get(league_key, {}).get("is_cup", False)

        # 1. Domestic Match Prediction
        if not is_cup and league_key in self.bundles:
            bundle = self.bundles[league_key]
            pipeline = bundle["pipeline"]
            models = bundle["models"]

            X_infer = pipeline.build_inference_features(
                home_team=home_norm,
                away_team=away_norm,
                match_date=match_date,
                referee=referee,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
            )

            probs_1x2_ml = models["model_1x2"].predict_proba(X_infer)[0]
            prob_over25_ml = float(models["model_over25"].predict_proba(X_infer)[0][1])
            prob_btts_ml = float(models["model_btts"].predict_proba(X_infer)[0][1])

            dc_preds = pipeline.dixon_coles_engine.predict_match_probabilities(home_norm, away_norm)
            probs_1x2_dc = np.array([dc_preds["prob_home"], dc_preds["prob_draw"], dc_preds["prob_away"]])
            prob_over25_dc = dc_preds["prob_over25"]
            prob_btts_dc = dc_preds["prob_btts_yes"]

            p_home = float(0.70 * probs_1x2_ml[0] + 0.30 * probs_1x2_dc[0])
            p_draw = float(0.70 * probs_1x2_ml[1] + 0.30 * probs_1x2_dc[1])
            p_away = float(0.70 * probs_1x2_ml[2] + 0.30 * probs_1x2_dc[2])
            sum_1x2 = p_home + p_draw + p_away
            p_home, p_draw, p_away = p_home / sum_1x2, p_draw / sum_1x2, p_away / sum_1x2

            p_over25 = float(0.65 * prob_over25_ml + 0.35 * prob_over25_dc)
            p_under25 = float(1.0 - p_over25)

            p_btts_yes = float(0.65 * prob_btts_ml + 0.35 * prob_btts_dc)
            p_btts_no = float(1.0 - p_btts_yes)

            prob_corners_o95_ml = float(models["model_corners_o95"].predict_proba(X_infer)[0][1]) if "model_corners_o95" in models else float(X_infer["prob_corners_o95_poisson"].iloc[0])
            prob_corners_o95_pois = float(X_infer["prob_corners_o95_poisson"].iloc[0])
            p_corners_o95 = float(0.60 * prob_corners_o95_ml + 0.40 * prob_corners_o95_pois)
            p_corners_u95 = float(1.0 - p_corners_o95)
            p_corners_o105 = float(X_infer["prob_corners_o105_poisson"].iloc[0])
            exp_corners = float(X_infer["exp_total_corners"].iloc[0])

            ref_profile = pipeline.referee_engine.get_referee_profile(referee, match_date)
            prob_cards_o35_ml = float(models["model_cards_o35"].predict_proba(X_infer)[0][1]) if "model_cards_o35" in models else float(X_infer["prob_cards_o35_poisson"].iloc[0])
            prob_cards_o35_pois = float(X_infer["prob_cards_o35_poisson"].iloc[0])
            p_cards_o35 = float(0.60 * prob_cards_o35_ml + 0.40 * prob_cards_o35_pois)
            p_cards_u35 = float(1.0 - p_cards_o35)

            prob_cards_o45_ml = float(models["model_cards_o45"].predict_proba(X_infer)[0][1]) if "model_cards_o45" in models else float(X_infer["prob_cards_o45_poisson"].iloc[0])
            prob_cards_o45_pois = float(X_infer["prob_cards_o45_poisson"].iloc[0])
            p_cards_o45 = float(0.60 * prob_cards_o45_ml + 0.40 * prob_cards_o45_pois)
            p_cards_u45 = float(1.0 - p_cards_o45)
            exp_cards = float(X_infer["exp_total_cards"].iloc[0])

            home_elo = float(pipeline.elo_engine.get_rating(home_norm)) if pipeline and hasattr(pipeline, "elo_engine") else 1500.0
            away_elo = float(pipeline.elo_engine.get_rating(away_norm)) if pipeline and hasattr(pipeline, "elo_engine") else 1500.0
            h_xg = float(dc_preds["lambda_home"])
            a_xg = float(dc_preds["mu_away"])
            score_mat = dc_preds["score_matrix"]
            most_likely_score = dc_preds["most_likely_score"]
            most_likely_score_prob = float(dc_preds["most_likely_score_prob"])

        # 2. European Cup / Cross-League Match Prediction
        else:
            h_prof = self._find_team_profile(home_norm)
            a_prof = self._find_team_profile(away_norm)

            home_elo = float(h_prof["elo"])
            away_elo = float(a_prof["elo"])

            # Cross-League Dixon-Coles expectancy
            home_adv = 0.20
            h_xg = float(np.exp(home_adv + h_prof["attack"] - a_prof["defense"]))
            a_xg = float(np.exp(a_prof["attack"] - h_prof["defense"]))
            h_xg = max(0.3, min(3.8, h_xg))
            a_xg = max(0.3, min(3.8, a_xg))

            # Joint bivariate Poisson score matrix
            score_mat = np.zeros((8, 8))
            for h_g in range(8):
                for a_g in range(8):
                    score_mat[h_g][a_g] = poisson.pmf(h_g, h_xg) * poisson.pmf(a_g, a_xg)

            # Dixon-Coles tau adjustment for 0-0, 1-0, 0-1, 1-1
            rho = -0.04
            score_mat[0, 0] *= max(0.01, 1.0 - h_xg * a_xg * rho)
            score_mat[0, 1] *= max(0.01, 1.0 + h_xg * rho)
            score_mat[1, 0] *= max(0.01, 1.0 + a_xg * rho)
            score_mat[1, 1] *= max(0.01, 1.0 - rho)
            score_mat = score_mat / np.sum(score_mat)

            p_home = float(np.sum(np.tril(score_mat, -1)))
            p_draw = float(np.sum(np.diag(score_mat)))
            p_away = float(np.sum(np.triu(score_mat, 1)))

            # Over / Under 2.5 & BTTS
            p_over25 = float(sum(score_mat[i, j] for i in range(8) for j in range(8) if i + j > 2.5))
            p_under25 = float(1.0 - p_over25)
            p_btts_yes = float(sum(score_mat[i, j] for i in range(1, 8) for j in range(1, 8)))
            p_btts_no = float(1.0 - p_btts_yes)

            max_idx = np.unravel_index(np.argmax(score_mat), score_mat.shape)
            most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
            most_likely_score_prob = float(score_mat[max_idx])

            # Corners Projections
            h_corn_for = h_prof["form"].get("corners_for_last5", 5.2)
            a_corn_for = a_prof["form"].get("corners_for_last5", 4.8)
            exp_corners = float(h_corn_for + a_corn_for)
            p_corners_o95 = float(1.0 - poisson.cdf(9, exp_corners))
            p_corners_u95 = float(1.0 - p_corners_o95)
            p_corners_o105 = float(1.0 - poisson.cdf(10, exp_corners))

            # Cards Projections
            h_cards = h_prof["form"].get("cards_for_last5", 2.1)
            a_cards = a_prof["form"].get("cards_for_last5", 2.1)
            exp_cards = float((h_cards + a_cards) * 1.05)  # European Cup intensity multiplier
            p_cards_o35 = float(1.0 - poisson.cdf(3, exp_cards))
            p_cards_u35 = float(1.0 - p_cards_o35)
            p_cards_o45 = float(1.0 - poisson.cdf(4, exp_cards))
            p_cards_u45 = float(1.0 - p_cards_o45)

            ref_profile = {
                "referee_name": referee or "UEFA Official",
                "strictness_index": 1.05,
                "strictness_label": "UEFA European Cup",
                "avg_cards": 4.5,
                "avg_fouls": 25.0,
            }

        # 3. Fair Odds
        fair_odds_home = round(1.0 / max(0.01, p_home), 2)
        fair_odds_draw = round(1.0 / max(0.01, p_draw), 2)
        fair_odds_away = round(1.0 / max(0.01, p_away), 2)
        fair_odds_o25 = round(1.0 / max(0.01, p_over25), 2)
        fair_odds_u25 = round(1.0 / max(0.01, p_under25), 2)
        fair_odds_btts_y = round(1.0 / max(0.01, p_btts_yes), 2)
        fair_odds_btts_n = round(1.0 / max(0.01, p_btts_no), 2)
        fair_odds_corn_o95 = round(1.0 / max(0.01, p_corners_o95), 2)
        fair_odds_corn_u95 = round(1.0 / max(0.01, p_corners_u95), 2)
        fair_odds_card_o35 = round(1.0 / max(0.01, p_cards_o35), 2)
        fair_odds_card_u35 = round(1.0 / max(0.01, p_cards_u35), 2)

        # 4. Betting Analysis & EV Across All Markets
        betting_insights = []
        best_pick = None
        max_ev = -1.0

        # Market: 1X2
        for sel, p_sel, o_sel, f_sel in [
            ("Home Win", p_home, odds_home, fair_odds_home),
            ("Draw", p_draw, odds_draw, fair_odds_draw),
            ("Away Win", p_away, odds_away, fair_odds_away)
        ]:
            has_odds = bool(o_sel and o_sel > 1.0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None
            if has_odds and ev > MIN_VALUE_THRESHOLD and ev > max_ev:
                max_ev = ev
                best_pick = {"market": "1X2", "selection": f"{sel}", "odds": o_sel, "prob": p_sel, "ev": ev, "kelly": kelly}
            betting_insights.append({
                "market": "1X2",
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

        # Market: Over/Under 2.5 Goals
        for sel, p_sel, o_sel, f_sel in [
            ("Over 2.5 Goals", p_over25, odds_over25, fair_odds_o25),
            ("Under 2.5 Goals", p_under25, odds_under25, fair_odds_u25)
        ]:
            has_odds = bool(o_sel and o_sel > 1.0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None
            if has_odds and ev > MIN_VALUE_THRESHOLD and ev > max_ev:
                max_ev = ev
                best_pick = {"market": "Goals", "selection": sel, "odds": o_sel, "prob": p_sel, "ev": ev, "kelly": kelly}
            betting_insights.append({
                "market": "Goals",
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

        # Market: Both Teams to Score (BTTS)
        for sel, p_sel, o_sel, f_sel in [
            ("BTTS Yes", p_btts_yes, odds_btts_yes, fair_odds_btts_y),
            ("BTTS No", p_btts_no, odds_btts_no, fair_odds_btts_n)
        ]:
            has_odds = bool(o_sel and o_sel > 1.0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None
            if has_odds and ev > MIN_VALUE_THRESHOLD and ev > max_ev:
                max_ev = ev
                best_pick = {"market": "BTTS", "selection": sel, "odds": o_sel, "prob": p_sel, "ev": ev, "kelly": kelly}
            betting_insights.append({
                "market": "BTTS",
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

        # Market: Corners Over/Under 9.5
        for sel, p_sel, o_sel, f_sel in [
            ("Over 9.5 Corners", p_corners_o95, odds_corners_over95, fair_odds_corn_o95),
            ("Under 9.5 Corners", p_corners_u95, odds_corners_under95, fair_odds_corn_u95)
        ]:
            has_odds = bool(o_sel and o_sel > 1.0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None
            if has_odds and ev > MIN_VALUE_THRESHOLD and ev > max_ev:
                max_ev = ev
                best_pick = {"market": "Corners", "selection": sel, "odds": o_sel, "prob": p_sel, "ev": ev, "kelly": kelly}
            betting_insights.append({
                "market": "Corners",
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

        # Market: Cards Over/Under 3.5
        for sel, p_sel, o_sel, f_sel in [
            ("Over 3.5 Cards", p_cards_o35, odds_cards_over35, fair_odds_card_o35),
            ("Under 3.5 Cards", p_cards_u35, odds_cards_under35, fair_odds_card_u35)
        ]:
            has_odds = bool(o_sel and o_sel > 1.0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None
            if has_odds and ev > MIN_VALUE_THRESHOLD and ev > max_ev:
                max_ev = ev
                best_pick = {"market": "Cards", "selection": sel, "odds": o_sel, "prob": p_sel, "ev": ev, "kelly": kelly}
            betting_insights.append({
                "market": "Cards",
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

        # Fallback default pick
        if not best_pick:
            highest_prob = max(p_home, p_draw, p_away)
            if highest_prob == p_home:
                best_pick = {"market": "1X2", "selection": f"{home_norm} (Fav)", "odds": odds_home, "prob": p_home, "ev": 0.0, "kelly": 0.0}
            elif highest_prob == p_away:
                best_pick = {"market": "1X2", "selection": f"{away_norm} (Fav)", "odds": odds_away, "prob": p_away, "ev": 0.0, "kelly": 0.0}
            else:
                best_pick = {"market": "1X2", "selection": "Draw", "odds": odds_draw, "prob": p_draw, "ev": 0.0, "kelly": 0.0}

        return {
            "league_key": league_key,
            "home_team": home_norm,
            "away_team": away_norm,
            "referee": ref_profile,
            "home_elo": home_elo,
            "away_elo": away_elo,
            "expected_goals_home": h_xg,
            "expected_goals_away": a_xg,
            "expected_total_goals": float(h_xg + a_xg),

            # Probabilities & Fair Odds
            "prob_home": float(p_home),
            "prob_draw": float(p_draw),
            "prob_away": float(p_away),
            "fair_odds_home": fair_odds_home,
            "fair_odds_draw": fair_odds_draw,
            "fair_odds_away": fair_odds_away,

            "prob_over25": float(p_over25),
            "prob_under25": float(p_under25),
            "fair_odds_over25": fair_odds_o25,
            "fair_odds_under25": fair_odds_u25,

            "prob_btts_yes": float(p_btts_yes),
            "prob_btts_no": float(p_btts_no),
            "fair_odds_btts_yes": fair_odds_btts_y,
            "fair_odds_btts_no": fair_odds_btts_n,

            "most_likely_score": most_likely_score,
            "most_likely_score_prob": most_likely_score_prob,
            "score_matrix": score_mat.tolist() if hasattr(score_mat, "tolist") else score_mat,

            # Corners Projections & Fair Odds
            "expected_corners": round(exp_corners, 1),
            "prob_corners_over95": float(p_corners_o95),
            "prob_corners_under95": float(p_corners_u95),
            "fair_odds_corners_over95": fair_odds_corn_o95,
            "fair_odds_corners_under95": fair_odds_corn_u95,
            "prob_corners_over105": float(p_corners_o105),

            # Cards & Referee Projections & Fair Odds
            "expected_cards": round(exp_cards, 1),
            "prob_cards_over35": float(p_cards_o35),
            "prob_cards_under35": float(p_cards_u35),
            "fair_odds_cards_over35": fair_odds_card_o35,
            "fair_odds_cards_under35": fair_odds_card_u35,
            "prob_cards_over45": float(p_cards_o45),
            "prob_cards_under45": float(p_cards_u45),

            # Market Odds passed in
            "odds_home": odds_home,
            "odds_draw": odds_draw,
            "odds_away": odds_away,
            "odds_over25": odds_over25,
            "odds_under25": odds_under25,
            "odds_btts_yes": odds_btts_yes,
            "odds_btts_no": odds_btts_no,
            "odds_corners_over95": odds_corners_over95,
            "odds_corners_under95": odds_corners_under95,
            "odds_cards_over35": odds_cards_over35,
            "odds_cards_under35": odds_cards_under35,

            "best_pick": best_pick,
            "has_value": bool(max_ev >= MIN_VALUE_THRESHOLD),
            "betting_insights": betting_insights,
        }
