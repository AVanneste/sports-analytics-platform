"""Master Predictor Engine for Match Outcomes, Goals, Corners, Cards, Referee Analytics & European Cups."""
import logging
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from scipy.stats import poisson

from football_core.data import opta_power
from football_core.config import LEAGUES, MIN_VALUE_THRESHOLD, MAX_VALUE_ODDS, MIN_VALUE_PROB, DEFAULT_KELLY_FRACTION, MODELS_DIR, TRACKER_FILE
from football_core.features.count_model import nb_prob_over
from football_core.features.props import project_cards, project_corners
from football_core.models.train import load_trained_bundle, outcome_probabilities
from sports_common.betting import DEFAULT_MARKET_MODEL_WEIGHT, MAX_CREDIBLE_EV, blend_with_market
from football_core.utils.helpers import (
    normalize_team_name,
    teams_match,
    calculate_ev,
    calculate_kelly_stake,
    remove_vig_multiplicative,
    strip_accents,
)

logger = logging.getLogger(__name__)

# Ties across leagues priced from Opta Power Rankings: European club competitions average about
# 2.9 goals a game, and home advantage is the 0.20 log-goals used for every cup tie
CUP_GOALS_PER_TEAM = 1.45
CUP_HOME_ADV = 0.20

DOMESTIC_ALIASES = {
    "internazionale": "Inter",
    "inter milan": "Inter",
    "sporting cp": "Sp Lisbon",
    "sporting lisbon": "Sp Lisbon",
    "sporting": "Sp Lisbon",
    "braga": "Sp Braga",
    "sc braga": "Sp Braga",
    "racing genk": "Genk",
    "krc genk": "Genk",
    "standard liege": "Standard",
    "standard de liege": "Standard",
    "sint-truidense": "St Truiden",
    "sint truidense": "St Truiden",
    "st. truiden": "St Truiden",
    "union st.-gilloise": "St. Gilloise",
    "union sg": "St. Gilloise",
    "royale union saint-gilloise": "St. Gilloise",
    "fc cologne": "FC Koln",
    "cologne": "FC Koln",
    "1. fc koln": "FC Koln",
    "koln": "FC Koln",
    "hamburg sv": "Hamburger SV",
    "hamburger": "Hamburger SV",
    "hsv": "Hamburger SV",
    "alavés": "Alaves",
    "deportivo alaves": "Alaves",
    "málaga": "Malaga",
    "malaga cf": "Malaga",
    "deportivo": "Dep La Coruna",
    "deportivo la coruna": "Dep La Coruna",
    "rc deportivo": "Dep La Coruna",
    "vitória de guimaraes": "Guimaraes",
    "vitoria de guimaraes": "Guimaraes",
    "vitoria sc": "Guimaraes",
    "nec nijmegen": "Nijmegen",
    "ajax amsterdam": "Ajax",
    "fortuna sittard": "For Sittard",
    "sc cambuur": "Cambuur",
    "cambuur leeuwarden": "Cambuur",
    "sc paderborn 07": "Paderborn",
    "paderborn 07": "Paderborn",
    "c.d. nacional": "Nacional",
    "cd nacional": "Nacional",
    "espanyol": "Espanol",
    "rcd espanyol": "Espanol",
    "coventry city": "Coventry",
    "hull city": "Hull",
}

class FootballPredictor:
    """Multi-league inference engine combining Calibrated LightGBM, Dixon-Coles, Elo, Corners, and Cards."""

    # Markets whose model-vs-market weight is fitted on historical prices (the default when a
    # bundle does not list its own). A league's BTTS joins once its weight was fitted on
    # OddsPortal's closing prices; corners/cards were never priced, so they cannot be value picks.
    MARKET_VALIDATED_MARKETS = {"1X2", "Goals"}

    def __init__(self):
        self.bundles: Dict[str, Dict[str, Any]] = {}
        self._settled_cache: Optional[tuple] = None
        self._opta: Optional[tuple] = None
        self._load_all_bundles()

    def _load_all_bundles(self):
        """Load pre-trained models and state pipelines for all domestic leagues and internationals."""
        for league_key in LEAGUES.keys():
            if LEAGUES[league_key].get("is_cup"):
                continue
            bundle = load_trained_bundle(league_key)
            if bundle:
                self.bundles[league_key] = bundle
                logger.info(f"Loaded predictor bundle for {league_key}")
            else:
                logger.debug(f"No trained bundle found for {league_key}")

        # Load international model bundle if available
        intl_path = MODELS_DIR / "International_bundle.joblib"
        if intl_path.exists():
            try:
                import joblib
                self.bundles["International"] = joblib.load(intl_path)
                logger.info("Loaded predictor bundle for International")
            except Exception as e:
                logger.warning(f"Could not load International bundle from {intl_path}: {e}")

    def refresh_state(self, league_key: str, cleaned_df: pd.DataFrame) -> bool:
        """Rebuild a league's feature state (ratings, form, Dixon-Coles) from today's data.

        The deployed classifiers are kept; only the inputs they see are brought up to date, so
        daily predictions reflect the latest results between weekly retrains.
        """
        bundle = self.bundles.get(league_key)
        if not bundle or cleaned_df.empty:
            return False
        from football_core.features.builder import FootballFeaturePipeline
        pipeline = FootballFeaturePipeline(league_key=league_key)
        pipeline.process_historical_matches(cleaned_df, state_only=True)
        bundle["pipeline"] = pipeline
        self._opta = None
        return True

    def _opta_calibration(self) -> tuple:
        """(log goals per Opta rating point, our league key -> Opta league id), from the domestic
        Dixon-Coles strengths (computed once)."""
        if getattr(self, "_opta", None) is None:  # also for predictors built without __init__
            strengths = {}
            for league_key, bundle in self.bundles.items():
                dc = getattr(bundle.get("pipeline"), "dixon_coles_engine", None)
                if league_key != "International" and dc is not None:
                    strengths[league_key] = {t: a + dc.defense_strengths.get(t, 0.0) for t, a in dc.attack_strengths.items()}
            self._opta = (opta_power.goal_scale(strengths), opta_power.league_ids(strengths))
        return self._opta

    def _opta_rating(self, team_name: str, profile: Dict[str, Any]) -> Optional[float]:
        """A club's Opta rating, looked up within its domestic league when we model that league."""
        league_id = self._opta_calibration()[1].get(profile["league"])
        for name in dict.fromkeys((team_name, normalize_team_name(team_name))):
            found = opta_power.club_rating(name, league_id)
            if found:
                return found[0]
        return None

    def is_league_ready(self, league_key: str) -> bool:
        if LEAGUES.get(league_key, {}).get("is_international") or league_key == "International":
            return "International" in self.bundles
        if LEAGUES.get(league_key, {}).get("is_cup"):
            return len(self.bundles) > 0
        return league_key in self.bundles

    def get_known_teams(self, league_key: str) -> List[str]:
        """Return list of known teams with ratings in the league or across all leagues for cups."""
        if LEAGUES.get(league_key, {}).get("is_international") or league_key == "International":
            bundle = self.bundles.get("International")
            if bundle and hasattr(bundle.get("pipeline"), "elo_engine"):
                return sorted(list(bundle["pipeline"].elo_engine.ratings.keys()))
            return []

        if LEAGUES.get(league_key, {}).get("is_cup"):
            all_teams = set()
            for b in self.bundles.values():
                if hasattr(b.get("pipeline"), "elo_engine"):
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
        """Find a team's Elo, attack, defence and form in the domestic or international models (else unrated)."""
        norm = normalize_team_name(team_name)
        clean = strip_accents(norm).lower()
        t_clean = strip_accents(team_name).lower()
        alias = DOMESTIC_ALIASES.get(t_clean, DOMESTIC_ALIASES.get(clean))

        # 1. Search across domestic league pipelines
        for l_k, bundle in self.bundles.items():
            if l_k == "International":
                continue
            pipeline = bundle["pipeline"]
            ratings = pipeline.elo_engine.ratings
            target_key = None
            if norm in ratings:
                target_key = norm
            elif alias and alias in ratings:
                target_key = alias
            else:
                for r_name in ratings.keys():
                    if teams_match(norm, r_name) or (alias and teams_match(alias, r_name)):
                        target_key = r_name
                        break

            if target_key:
                elo = pipeline.elo_engine.get_rating(target_key)
                att = pipeline.dixon_coles_engine.attack_strengths.get(target_key, 0.0)
                dfn = pipeline.dixon_coles_engine.defense_strengths.get(target_key, 0.0)
                form = pipeline.form_tracker.get_team_rolling_features(target_key, pd.Timestamp.now(), n_matches=5)
                return {
                    "league": l_k,
                    "elo": float(elo),
                    "attack": float(att),
                    "defense": float(dfn),
                    "form": form or {},
                    "pipeline": pipeline,
                    "bundle": bundle,
                }

        # 2. Search International bundle for national teams
        intl_bundle = self.bundles.get("International")
        if intl_bundle and "pipeline" in intl_bundle:
            intl_pipe = intl_bundle["pipeline"]
            if hasattr(intl_pipe, "elo_engine"):
                res_name = intl_pipe.elo_engine.resolve_team(team_name)
                if res_name in intl_pipe.elo_engine.ratings:
                    elo = intl_pipe.elo_engine.get_rating(res_name)
                    form = intl_pipe.form_tracker.get_team_rolling_features(res_name, pd.Timestamp.now(), n_matches=5) if hasattr(intl_pipe, "form_tracker") else {}
                    return {
                        "league": "International",
                        "elo": float(elo),
                        "attack": 0.0,
                        "defense": 0.0,
                        "form": form or {},
                        "pipeline": intl_pipe,
                        "bundle": intl_bundle,
                    }

        # 3. Not covered by any of our models: unrated
        return {
            "league": "Other",
            "elo": 1500.0,
            "attack": 0.0,
            "defense": 0.0,
            "form": {},
            "pipeline": None,
            "bundle": None,
        }

    def _get_settled_tracker_matches(self) -> List[Dict[str, Any]]:
        """Settled matches from the predictions ledger (cached until the file changes)."""
        import json
        if not TRACKER_FILE.exists():
            return []
        mtime = TRACKER_FILE.stat().st_mtime
        if self._settled_cache and self._settled_cache[0] == mtime:
            return self._settled_cache[1]
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        settled = [d for d in data if isinstance(d, dict) and d.get("status") == "settled" and d.get("actual_score")]
        self._settled_cache = (mtime, settled)
        return settled

    def get_team_recent_matches(self, league_key: str, team_name: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return the last n matches for a team with score, opponent, venue, and result (merging matches settled since the last data refresh)."""
        from datetime import datetime
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm = pipeline.elo_engine.resolve_team(team_name) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(team_name)
        else:
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
                    "res": m.get("res", "D" if m.get("gf", 0) == m.get("ga", 0) else ("W" if m.get("gf", 0) > m.get("ga", 0) else "L")),
                    "corners": m.get("corners_for"),
                    "cards": m.get("cards_for"),
                })

        # Merge matches settled since the last data refresh (from the tracker)
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
                    "corners": None,  # the ledger only records match totals
                    "cards": None,
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
        """Return past head-to-head matches between home_team and away_team (merging matches settled since the last data refresh)."""
        from datetime import datetime
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm_h = pipeline.elo_engine.resolve_team(home_team) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(home_team)
            norm_a = pipeline.elo_engine.resolve_team(away_team) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(away_team)
        else:
            norm_h = normalize_team_name(home_team)
            norm_a = normalize_team_name(away_team)
            bundle = self.bundles.get(league_key)
            if not bundle:
                profile = self._find_team_profile(home_team)
                pipeline = profile.get("pipeline")
            else:
                pipeline = bundle.get("pipeline")
            
        h2h_list = []
        if is_intl and pipeline and hasattr(pipeline, "h2h_tracker"):
            key = pipeline.h2h_tracker._get_key(norm_h, norm_a)
            hist = pipeline.h2h_tracker.matches.get(key, [])
            for m in hist:
                d_val = m.get("date")
                d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                hg = int(m.get("fthg", 0))
                ag = int(m.get("ftag", 0))
                winner = m.get("home_team") if hg > ag else (m.get("away_team") if ag > hg else "Draw")
                h2h_list.append({
                    "date": d_str,
                    "home_team": m.get("home_team"),
                    "away_team": m.get("away_team"),
                    "score": f"{hg}-{ag}",
                    "h_score": hg,
                    "a_score": ag,
                    "winner": winner,
                })
        elif pipeline and hasattr(pipeline, "form_tracker"):
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

        # Merge matches settled since the last data refresh (from the tracker)
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
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm = pipeline.elo_engine.resolve_team(team_name) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(team_name)
            elo = pipeline.elo_engine.get_rating(norm) if (pipeline and hasattr(pipeline, "elo_engine")) else None
            att = None
            dfn = None
        else:
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
            "matches_analyzed": len(hist) + sum(
                1 for m in recent
                if hist and str(m.get("date", "")) > str(hist[-1].get("date", ""))[:10]
            ),
        }

    @staticmethod
    def generate_goal_lines(score_mat: Any, exp_goals: float, lines: Optional[List[float]] = None) -> tuple[List[Dict[str, Any]], float]:
        """
        Compute Over/Under probabilities and fair odds across multiple goal lines.
        Returns: (lines_list, primary_line)
        """
        if lines is None:
            lines = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]

        score_arr = np.asarray(score_mat)
        # Primary line is closest half-goal line to expected total goals
        primary_line = min(lines, key=lambda l: abs(l - exp_goals))
        res = []
        for l in lines:
            p_o = float(sum(score_arr[i, j] for i in range(score_arr.shape[0]) for j in range(score_arr.shape[1]) if (i + j) > l))
            p_o = float(np.clip(p_o, 0.01, 0.99))
            p_u = float(1.0 - p_o)
            res.append({
                "line": float(l),
                "prob_over": round(p_o, 3),
                "prob_under": round(p_u, 3),
                "fair_odds_over": round(1.0 / max(0.01, p_o), 2),
                "fair_odds_under": round(1.0 / max(0.01, p_u), 2),
                "is_primary": bool(l == primary_line),
            })
        return res, primary_line

    @staticmethod
    def _count_lines(expected: float, lines: List[float], phi: float,
                     alpha: Optional[float]) -> tuple[List[Dict[str, Any]], float]:
        """Over/under probabilities and fair odds at each line for a negative-binomial match total.

        ``alpha`` is a fitted count model's dispersion (variance = m + alpha * m^2); without one the
        fixed variance-to-mean ratio ``phi`` is used (alpha = (phi - 1) / m).
        """
        primary_line = min(lines, key=lambda l: abs(l - expected))
        if alpha is None:
            alpha = (phi - 1.0) / max(expected, 1e-6)
        res = []
        for l in lines:
            p_o = float(np.clip(nb_prob_over(expected, l, alpha), 0.02, 0.98))
            p_u = float(1.0 - p_o)
            res.append({
                "line": float(l),
                "prob_over": round(p_o, 3),
                "prob_under": round(p_u, 3),
                "fair_odds_over": round(1.0 / max(0.01, p_o), 2),
                "fair_odds_under": round(1.0 / max(0.01, p_u), 2),
                "is_primary": bool(l == primary_line),
            })
        return res, primary_line

    @staticmethod
    def generate_corner_lines(exp_corners: float, lines: Optional[List[float]] = None,
                              alpha: Optional[float] = None) -> tuple[List[Dict[str, Any]], float]:
        """Corner over/under lines; returns (lines_list, primary_line)."""
        return FootballPredictor._count_lines(exp_corners, lines or [7.5, 8.5, 9.5, 10.5, 11.5, 12.5], 1.20, alpha)

    @staticmethod
    def generate_card_lines(exp_cards: float, lines: Optional[List[float]] = None,
                            alpha: Optional[float] = None) -> tuple[List[Dict[str, Any]], float]:
        """Card over/under lines; returns (lines_list, primary_line)."""
        return FootballPredictor._count_lines(exp_cards, lines or [1.5, 2.5, 3.5, 4.5, 5.5, 6.5], 1.80, alpha)

    @staticmethod
    def _count_projection(pipeline: Any, stat: str, home: str, away: str,
                          referee: Optional[str] = None) -> Optional[Dict[str, float]]:
        """Expected total and the main over/under probabilities from the league's fitted count model."""
        model = (getattr(pipeline, "count_models", None) or {}).get(stat)
        if model is None or not model.fitted:
            return None
        low, high = (9.5, 10.5) if stat == "corners" else (3.5, 4.5)
        p_low, p_high = (model.prob_over(home, away, line, referee) for line in (low, high))
        tag_low, tag_high = int(low * 10), int(high * 10)
        return {"expected": model.expected(home, away, referee), "alpha": model.alpha,
                f"over{tag_low}": p_low, f"under{tag_low}": 1.0 - p_low,
                f"over{tag_high}": p_high, f"under{tag_high}": 1.0 - p_high}

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
        is_neutral: Optional[bool] = None,
        tournament: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate comprehensive match predictions across 1X2, Goals, BTTS, Corners, and Cards (Domestic, International & European Cups)."""
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)
        # Fixture feeds pass ISO strings; every engine compares against pandas Timestamps.
        if match_date is not None:
            match_date = pd.Timestamp(match_date)
            if match_date.tzinfo is not None:
                match_date = match_date.tz_convert(None)

        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        is_cup = LEAGUES.get(league_key, {}).get("is_cup", False)
        bundle = self.bundles.get(league_key)
        low_confidence_reason: Optional[str] = None
        market_weights = {"1x2": DEFAULT_MARKET_MODEL_WEIGHT, "over25": DEFAULT_MARKET_MODEL_WEIGHT,
                          "btts": DEFAULT_MARKET_MODEL_WEIGHT}
        # Value picks are only allowed where the model was validated against historical market
        # prices (domestic leagues). Internationals and cups have no such evidence.
        market_validated = False
        validated_markets = self.MARKET_VALIDATED_MARKETS

        # 1. International Match Prediction (Calibrated LightGBM + Elo Bivariate Poisson)
        if is_intl and ("International" in self.bundles):
            intl_bundle = self.bundles["International"]
            models = intl_bundle["models"]
            pipeline = intl_bundle["pipeline"]

            tourn_name = tournament or LEAGUES.get(league_key, {}).get("name") or league_key
            eff_neutral = bool(is_neutral if is_neutral is not None else kwargs.get("neutral", False))

            home_norm = pipeline.elo_engine.resolve_team(home_team) if hasattr(pipeline, "elo_engine") else normalize_team_name(home_team)
            away_norm = pipeline.elo_engine.resolve_team(away_team) if hasattr(pipeline, "elo_engine") else normalize_team_name(away_team)

            X_infer = pipeline.build_inference_features(
                home_team=home_norm,
                away_team=away_norm,
                date=match_date,
                is_neutral=eff_neutral,
                tournament=tourn_name,
            )

            probs_1x2_ml = models["model_1x2"].predict_proba(X_infer)[0]
            prob_over25_ml = float(models["model_over25"].predict_proba(X_infer)[0][1])
            prob_btts_ml = float(models["model_btts"].predict_proba(X_infer)[0][1])

            # Elo-based bivariate Poisson generator
            home_elo = float(pipeline.elo_engine.get_rating(home_norm)) if hasattr(pipeline, "elo_engine") else 1500.0
            away_elo = float(pipeline.elo_engine.get_rating(away_norm)) if hasattr(pipeline, "elo_engine") else 1500.0
            adv = 0.0 if eff_neutral else 65.0
            elo_diff_val = (home_elo + adv) - away_elo

            home_adv_rate = 0.20 if not eff_neutral else 0.0
            elo_xg_adj = (elo_diff_val / 400.0) * 0.35
            h_xg = max(0.35, min(3.8, float(np.exp(home_adv_rate + elo_xg_adj * 0.5))))
            a_xg = max(0.25, min(3.5, float(np.exp(-elo_xg_adj * 0.5))))

            score_mat = np.zeros((8, 8))
            for h_g in range(8):
                for a_g in range(8):
                    score_mat[h_g, a_g] = poisson.pmf(h_g, h_xg) * poisson.pmf(a_g, a_xg)

            rho = -0.04
            score_mat[0, 0] *= max(0.01, 1.0 - h_xg * a_xg * rho)
            score_mat[0, 1] *= max(0.01, 1.0 + h_xg * rho)
            score_mat[1, 0] *= max(0.01, 1.0 + a_xg * rho)
            score_mat[1, 1] *= max(0.01, 1.0 - rho)
            score_mat /= np.sum(score_mat)

            p_home_pois = float(np.sum(np.tril(score_mat, -1)))
            p_draw_pois = float(np.sum(np.diag(score_mat)))
            p_away_pois = float(np.sum(np.triu(score_mat, 1)))
            sum_pois = p_home_pois + p_draw_pois + p_away_pois
            if sum_pois > 0:
                p_home_pois, p_draw_pois, p_away_pois = p_home_pois / sum_pois, p_draw_pois / sum_pois, p_away_pois / sum_pois

            p_over25_pois = float(np.sum([score_mat[h, a] for h in range(8) for a in range(8) if h + a > 2.5]))
            p_btts_pois = float(np.sum(score_mat[1:, 1:]))

            p_home = float(0.70 * probs_1x2_ml[0] + 0.30 * p_home_pois)
            p_draw = float(0.70 * probs_1x2_ml[1] + 0.30 * p_draw_pois)
            p_away = float(0.70 * probs_1x2_ml[2] + 0.30 * p_away_pois)
            sum_1x2 = p_home + p_draw + p_away
            p_home, p_draw, p_away = p_home / sum_1x2, p_draw / sum_1x2, p_away / sum_1x2

            p_over25 = float(0.65 * prob_over25_ml + 0.35 * p_over25_pois)
            p_under25 = float(1.0 - p_over25)

            p_btts_yes = float(0.65 * prob_btts_ml + 0.35 * p_btts_pois)
            p_btts_no = float(1.0 - p_btts_yes)

            max_idx = np.unravel_index(np.argmax(score_mat), score_mat.shape)
            most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
            most_likely_score_prob = float(score_mat[max_idx])

            # Corners and cards: league baselines adjusted for the strength gap (no team data for national sides)
            corners = project_corners(None, None, None, None, elo_diff=elo_diff_val)
            cards = project_cards(None, None, ref_strictness=1.0, is_cup=True)

            ref_profile = {
                "referee_name": referee or "FIFA Official",
                "strictness_index": 1.0,
                "strictness_label": "International Official",
                "avg_cards": 4.2,
                "avg_fouls": 24.5,
            }

        # 2. Domestic League Match Prediction (Full Multi-Model Stack)
        elif bundle and not is_cup:
            models = bundle["models"]
            pipeline = bundle["pipeline"]

            X_infer = pipeline.build_inference_features(
                home_team=home_norm,
                away_team=away_norm,
                match_date=match_date,
                referee=referee,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
            )

            dc_preds = pipeline.dixon_coles_engine.predict_match_probabilities(home_norm, away_norm)

            # LightGBM blended with Dixon-Coles, weights fitted on each league's validation window;
            # the same function produces the backtested probabilities
            metrics = bundle.get("metrics", {})
            p1x2, p_ou, p_btts = outcome_probabilities(models, metrics, X_infer)
            p_home, p_draw, p_away = (float(v) for v in p1x2[0])
            p_over25, p_btts_yes = float(p_ou[0]), float(p_btts[0])
            p_under25, p_btts_no = 1.0 - p_over25, 1.0 - p_btts_yes

            # Model-vs-market weights, also fitted on the validation window
            fitted_market_weights = metrics.get("market_weights")
            market_weights.update(fitted_market_weights or {})
            market_validated = bool(fitted_market_weights)
            # BTTS joins 1X2 and Goals once its weight was fitted on real prices (OddsPortal)
            validated_markets = set(metrics.get("market_validated_markets") or self.MARKET_VALIDATED_MARKETS)

            home_elo = float(X_infer["home_elo"].iloc[0])
            away_elo = float(X_infer["away_elo"].iloc[0])

            # Corners and cards from the league's fitted team count models (validated walk-forward
            # against the heuristic projections), else the heuristic projections in the features
            feats = X_infer.iloc[0]
            corners = self._count_projection(pipeline, "corners", home_norm, away_norm) or {
                "expected": float(feats["exp_total_corners"]), "over95": float(feats["prob_corners_o95_poisson"]),
                "under95": 1.0 - float(feats["prob_corners_o95_poisson"]), "over105": float(feats["prob_corners_o105_poisson"])}
            cards = self._count_projection(pipeline, "cards", home_norm, away_norm, referee) or {
                "expected": float(feats["exp_total_cards"]), "over35": float(feats["prob_cards_o35_poisson"]),
                "under35": 1.0 - float(feats["prob_cards_o35_poisson"]), "over45": float(feats["prob_cards_o45_poisson"]),
                "under45": 1.0 - float(feats["prob_cards_o45_poisson"])}
            ref_profile = pipeline.referee_engine.get_referee_profile(referee, match_date)
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

            # Ratings from different domestic pools (each starts every team at 1500) are not
            # comparable: such ties are priced from Opta's single rating scale when both clubs are
            # rated. None of these predictions qualify as value bets.
            leagues = {h_prof["league"], a_prof["league"]}
            opta = None
            if len(leagues) > 1 or leagues & {"Other", "International"}:
                scale = self._opta_calibration()[0]
                r_home, r_away = self._opta_rating(home_team, h_prof), self._opta_rating(away_team, a_prof)
                if scale and r_home is not None and r_away is not None:
                    opta = scale * (r_home - r_away)  # log-goal supremacy
            if opta is not None:
                low_confidence_reason = ("cross-league tie priced from Opta Power Rankings "
                                         "(not yet validated on cup results)")
            elif "Other" in leagues:
                # A club none of our models covers has no rating (a hand-kept table of ratings used to
                # stand in, years out of date): show the market's prices as they are when they exist
                low_confidence_reason = "at least one club is not covered by our models; market prices shown as they are"
                market_weights = {market: 0.0 for market in market_weights}
            elif "International" in leagues:
                low_confidence_reason = "a club is rated on the national-team scale"
            elif len(leagues) > 1:
                low_confidence_reason = f"cross-league ratings ({' vs '.join(sorted(leagues))}) are not on a common scale"

            # Cross-League Dixon-Coles expectancy with Elo calibration
            home_adv = 0.20
            elo_diff = home_elo - away_elo
            elo_xg_adj = (elo_diff / 400.0) * 0.35
            h_xg = float(np.exp(home_adv + h_prof["attack"] - a_prof["defense"] + elo_xg_adj * 0.5))
            a_xg = float(np.exp(a_prof["attack"] - h_prof["defense"] - elo_xg_adj * 0.5))
            if opta is not None:
                h_xg = float(CUP_GOALS_PER_TEAM * np.exp((CUP_HOME_ADV + opta) / 2))
                a_xg = float(CUP_GOALS_PER_TEAM * np.exp(-(CUP_HOME_ADV + opta) / 2))
            h_xg = max(0.35, min(3.8, h_xg))
            a_xg = max(0.25, min(3.5, a_xg))

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
            sum_p = p_home + p_draw + p_away
            if sum_p > 0:
                p_home, p_draw, p_away = p_home / sum_p, p_draw / sum_p, p_away / sum_p

            # Over / Under 2.5 & BTTS
            p_over25 = float(sum(score_mat[i, j] for i in range(8) for j in range(8) if i + j > 2.5))
            p_under25 = float(1.0 - p_over25)
            p_btts_yes = float(sum(score_mat[i, j] for i in range(1, 8) for j in range(1, 8)))
            p_btts_no = float(1.0 - p_btts_yes)

            max_idx = np.unravel_index(np.argmax(score_mat), score_mat.shape)
            most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
            most_likely_score_prob = float(score_mat[max_idx])

            # Corners and cards from each club's domestic form when we track it (league baselines otherwise)
            h_form = h_prof.get("form") or {}
            a_form = a_prof.get("form") or {}
            corners = project_corners(h_form.get("corners_for_last5"), h_form.get("corners_against_last5"),
                                      a_form.get("corners_for_last5"), a_form.get("corners_against_last5"),
                                      elo_diff=elo_diff)
            cards = project_cards(h_form.get("cards_for_last5"), a_form.get("cards_for_last5"),
                                  ref_strictness=1.05, is_cup=True)

            ref_profile = {
                "referee_name": referee or "UEFA Official",
                "strictness_index": 1.05,
                "strictness_label": "UEFA European Cup",
                "avg_cards": 4.5,
                "avg_fouls": 25.0,
            }

        # Shrink the model toward the vig-free market price wherever real odds exist.
        model_probs = {"home": p_home, "draw": p_draw, "away": p_away, "over25": p_over25, "btts_yes": p_btts_yes}
        (p_home, p_draw, p_away), mkt_1x2 = blend_with_market((p_home, p_draw, p_away), (odds_home, odds_draw, odds_away), market_weights["1x2"])
        (p_over25, p_under25), mkt_ou = blend_with_market((p_over25, p_under25), (odds_over25, odds_under25), market_weights["over25"])
        (p_btts_yes, p_btts_no), mkt_btts = blend_with_market((p_btts_yes, p_btts_no), (odds_btts_yes, odds_btts_no), market_weights["btts"])

        exp_corners, p_corners_o95, p_corners_u95, p_corners_o105 = (
            round(corners["expected"], 1), corners["over95"], corners["under95"], corners["over105"])
        exp_cards, p_cards_o35, p_cards_u35, p_cards_o45, p_cards_u45 = (
            round(cards["expected"], 1), cards["over35"], cards["under35"], cards["over45"], cards["under45"])

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
        candidates = []

        all_market_selections = [
            # 1X2
            ("1X2", "Home Win", p_home, odds_home, fair_odds_home),
            ("1X2", "Draw", p_draw, odds_draw, fair_odds_draw),
            ("1X2", "Away Win", p_away, odds_away, fair_odds_away),
            # Goals
            ("Goals", "Over 2.5 Goals", p_over25, odds_over25, fair_odds_o25),
            ("Goals", "Under 2.5 Goals", p_under25, odds_under25, fair_odds_u25),
            # BTTS
            ("BTTS", "BTTS Yes", p_btts_yes, odds_btts_yes, fair_odds_btts_y),
            ("BTTS", "BTTS No", p_btts_no, odds_btts_no, fair_odds_btts_n),
            # Corners
            ("Corners", "Over 9.5 Corners", p_corners_o95, odds_corners_over95, fair_odds_corn_o95),
            ("Corners", "Under 9.5 Corners", p_corners_u95, odds_corners_under95, fair_odds_corn_u95),
            # Cards
            ("Cards", "Over 3.5 Cards", p_cards_o35, odds_cards_over35, fair_odds_card_o35),
            ("Cards", "Under 3.5 Cards", p_cards_u35, odds_cards_under35, fair_odds_card_u35),
        ]

        for mkt, sel, p_sel, o_sel, f_sel in all_market_selections:
            has_odds = bool(o_sel and o_sel > 1.0 and p_sel and p_sel > 0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None

            betting_insights.append({
                "market": mkt,
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly,
                "ev_suspect": bool(ev is not None and ev > MAX_CREDIBLE_EV),
            })

            # Bounded Value Bet Qualification (probabilities are already shrunk toward the market):
            # 1. Valid market odds and positive probability
            # 2. Odds within realistic bounds (<= MAX_VALUE_ODDS, e.g. 3.20)
            # 3. Probability >= MIN_VALUE_PROB (e.g. 30%)
            # 4. MIN_VALUE_THRESHOLD <= EV <= MAX_CREDIBLE_EV (larger "edges" are model errors)
            # 5. Not a low-confidence prediction (cross-league or unrated cup ties)
            # 6. The competition's model was validated against historical market prices
            if (has_odds and ev is not None and MIN_VALUE_THRESHOLD <= ev <= MAX_CREDIBLE_EV
                    and o_sel <= MAX_VALUE_ODDS and p_sel >= MIN_VALUE_PROB
                    and low_confidence_reason is None and market_validated
                    and mkt in validated_markets):
                candidates.append({
                    "market": mkt,
                    "selection": sel,
                    "odds": o_sel,
                    "prob": p_sel,
                    "ev": ev,
                    "kelly": kelly or 0.0
                })

        if candidates:
            # Rank candidates primarily by risk-adjusted Quarter-Kelly stake, tie-break by EV
            candidates.sort(key=lambda c: (c["kelly"], c["ev"]), reverse=True)
            best_pick = candidates[0]
            max_ev = best_pick["ev"]
        else:
            max_ev = -1.0
            highest_prob = max(p_home, p_draw, p_away)
            if highest_prob == p_home:
                best_pick = {"market": "1X2", "selection": f"{home_norm} (Fav)", "odds": odds_home, "prob": p_home, "ev": 0.0, "kelly": 0.0}
            elif highest_prob == p_away:
                best_pick = {"market": "1X2", "selection": f"{away_norm} (Fav)", "odds": odds_away, "prob": p_away, "ev": 0.0, "kelly": 0.0}
            else:
                best_pick = {"market": "1X2", "selection": "Draw", "odds": odds_draw, "prob": p_draw, "ev": 0.0, "kelly": 0.0}

        goal_lines, primary_goal_line = self.generate_goal_lines(score_mat, float(h_xg + a_xg))
        corner_lines, primary_corner_line = self.generate_corner_lines(corners["expected"], alpha=corners.get("alpha"))
        card_lines, primary_card_line = self.generate_card_lines(cards["expected"], alpha=cards.get("alpha"))

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
            "primary_goal_line": primary_goal_line,
            "primary_corner_line": primary_corner_line,
            "primary_card_line": primary_card_line,
            "goal_lines": goal_lines,
            "corner_lines": corner_lines,
            "card_lines": card_lines,

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
            "prob_btts": float(p_btts_yes),
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

            # Transparency: raw model view, vig-free market view, and how they were combined
            "model_prob_home": float(model_probs["home"]),
            "model_prob_draw": float(model_probs["draw"]),
            "model_prob_away": float(model_probs["away"]),
            "model_prob_over25": float(model_probs["over25"]),
            "model_prob_btts_yes": float(model_probs["btts_yes"]),
            "market_prob_home": mkt_1x2[0] if mkt_1x2 else None,
            "market_prob_draw": mkt_1x2[1] if mkt_1x2 else None,
            "market_prob_away": mkt_1x2[2] if mkt_1x2 else None,
            "market_prob_over25": mkt_ou[0] if mkt_ou else None,
            "market_prob_btts_yes": mkt_btts[0] if mkt_btts else None,
            "market_weights": market_weights,
            "low_confidence": low_confidence_reason is not None,
            "low_confidence_reason": low_confidence_reason,
            "market_validated": market_validated,
        }
