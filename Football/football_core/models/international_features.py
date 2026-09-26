"""Feature Engineering Pipeline for International Football (Elo, Rolling Form, H2H, Tournament Weighting)."""
import logging
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson

logger = logging.getLogger(__name__)

# Common national team aliases and name variations
INTERNATIONAL_TEAM_ALIASES = {
    "usa": "United States",
    "united states of america": "United States",
    "us": "United States",
    "south korea": "South Korea",
    "korea republic": "South Korea",
    "korea": "South Korea",
    "north korea": "North Korea",
    "korea dpr": "North Korea",
    "ivory coast": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "cape verde": "Cape Verde",
    "cabo verde": "Cape Verde",
    "dr congo": "DR Congo",
    "congo dr": "DR Congo",
    "democratic republic of the congo": "DR Congo",
    "congo": "Congo",
    "republic of the congo": "Congo",
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
    "bosnia": "Bosnia and Herzegovina",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia & herzegovina": "Bosnia and Herzegovina",
    "trinidad": "Trinidad and Tobago",
    "trinidad & tobago": "Trinidad and Tobago",
    "ireland": "Republic of Ireland",
    "republic of ireland": "Republic of Ireland",
    "northern ireland": "Northern Ireland",
    "china": "China PR",
    "china pr": "China PR",
    "chinese taipei": "Chinese Taipei",
    "taiwan": "Chinese Taipei",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
}

FEATURE_NAMES = [
    "home_elo",
    "away_elo",
    "elo_diff",
    "elo_prob_home",
    "elo_prob_away",
    "is_neutral",
    "tournament_importance",
    "home_ppg_l5",
    "away_ppg_l5",
    "diff_ppg_l5",
    "home_gf_l5",
    "away_gf_l5",
    "home_ga_l5",
    "away_ga_l5",
    "home_gd_l5",
    "away_gd_l5",
    "diff_gd_l5",
    "h2h_matches_count",
    "h2h_home_win_rate",
    "h2h_draw_rate",
    "h2h_away_win_rate",
    "h2h_avg_total_goals",
]


def normalize_intl_team_name(team: str) -> str:
    """Normalize national team name for consistent lookup."""
    if not team or not isinstance(team, str):
        return ""
    t_clean = team.strip()
    t_lower = t_clean.lower()
    if t_lower in INTERNATIONAL_TEAM_ALIASES:
        return INTERNATIONAL_TEAM_ALIASES[t_lower]

    # Check accent-stripped version
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", t_lower)
        if unicodedata.category(c) != "Mn"
    )
    if stripped in INTERNATIONAL_TEAM_ALIASES:
        return INTERNATIONAL_TEAM_ALIASES[stripped]

    return t_clean


def get_tournament_importance(tournament: Optional[str]) -> float:
    """
    Compute competition tier weighting:
    - World Cup finals: 1.00
    - Major Continental finals: 0.85
    - Nations League: 0.70
    - Qualifiers: 0.65
    - Friendlies: 0.40
    - Other regional tournaments: 0.55
    """
    if not tournament or not isinstance(tournament, str):
        return 0.50
    t_lower = tournament.lower()

    # Qualifiers check first (e.g. World Cup qualification is 0.65, not 1.0)
    if "qualification" in t_lower or "qualifier" in t_lower:
        return 0.65

    # World Cup finals
    if "fifa world cup" in t_lower or t_lower == "world cup":
        return 1.00

    # Major Continental Tournaments
    continental_keywords = [
        "uefa euro",
        "copa américa",
        "copa america",
        "african cup of nations",
        "afcon",
        "afc asian cup",
        "gold cup",
        "oceania nations cup",
        "euro",
    ]
    if any(k in t_lower for k in continental_keywords):
        return 0.85

    # Nations League
    if "nations league" in t_lower:
        return 0.70

    # Friendlies & FIFA Series
    if "friendly" in t_lower or "fifa series" in t_lower:
        return 0.40

    return 0.55


class InternationalEloEngine:
    """Dynamic Elo rating engine for national football teams with neutral venue support."""

    def __init__(self, base_elo: float = 1500.0, k_factor: float = 25.0, home_adv: float = 65.0):
        self.base_elo = base_elo
        self.k_factor = k_factor
        self.home_adv = home_adv
        self.ratings: Dict[str, float] = {}
        self.match_count: Dict[str, int] = {}
        self.history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def resolve_team(self, team: str) -> str:
        """Resolve team name to match internal rating keys."""
        norm = normalize_intl_team_name(team)
        if norm in self.ratings:
            return norm
        if team in self.ratings:
            return team

        t_low = team.strip().lower()
        for k in self.ratings:
            if k.lower() == t_low:
                return k
        return norm or team

    def get_rating(self, team: str) -> float:
        """Return current rating for team, default to base_elo if unseen."""
        res = self.resolve_team(team)
        return self.ratings.get(res, self.base_elo)

    def get_match_count(self, team: str) -> int:
        """Return total historical matches tracked for team."""
        res = self.resolve_team(team)
        return self.match_count.get(res, 0)

    def compute_expected_probability(
        self,
        home_elo: float,
        away_elo: float,
        is_neutral: bool = False
    ) -> Tuple[float, float, float]:
        """
        Compute effective Elo diff and expected win probabilities.
        When is_neutral is True, home advantage is 0.0; otherwise self.home_adv (65.0).
        Returns:
            (elo_diff, p_home, p_away)
        """
        adv = 0.0 if is_neutral else self.home_adv
        elo_diff = (home_elo + adv) - away_elo
        p_home = 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))
        p_away = 1.0 - p_home
        return float(elo_diff), float(p_home), float(p_away)

    def _goal_diff_multiplier(self, goal_diff: int) -> float:
        """World Football Elo goal difference multiplier."""
        abs_diff = abs(goal_diff)
        if abs_diff <= 1:
            return 1.0
        elif abs_diff == 2:
            return 1.5
        else:
            return (11.0 + abs_diff) / 8.0

    def update_match(
        self,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        is_neutral: bool = False,
        date: Optional[pd.Timestamp] = None
    ) -> Dict[str, float]:
        """Update ratings after a match in chronological order."""
        home_norm = self.resolve_team(home_team)
        away_norm = self.resolve_team(away_team)
        home_pre = self.get_rating(home_norm)
        away_pre = self.get_rating(away_norm)
        elo_diff, p_home, p_away = self.compute_expected_probability(home_pre, away_pre, is_neutral=is_neutral)

        if fthg > ftag:
            s_home, s_away = 1.0, 0.0
        elif fthg == ftag:
            s_home, s_away = 0.5, 0.5
        else:
            s_home, s_away = 0.0, 1.0

        g_mult = self._goal_diff_multiplier(fthg - ftag)
        delta_home = self.k_factor * g_mult * (s_home - p_home)
        delta_away = -delta_home

        home_post = home_pre + delta_home
        away_post = away_pre + delta_away

        self.ratings[home_norm] = home_post
        self.ratings[away_norm] = away_post
        self.match_count[home_norm] = self.match_count.get(home_norm, 0) + 1
        self.match_count[away_norm] = self.match_count.get(away_norm, 0) + 1

        if date is not None:
            self.history[home_norm].append({"date": date, "rating": home_post})
            self.history[away_norm].append({"date": date, "rating": away_post})

        return {
            "home_elo_pre": home_pre,
            "away_elo_pre": away_pre,
            "elo_diff": elo_diff,
            "elo_exp_home_prob": p_home,
            "elo_exp_away_prob": p_away,
            "home_elo_post": home_post,
            "away_elo_post": away_post,
        }


class InternationalFormTracker:
    """Tracks chronological match logs and rolling form per national team."""

    def __init__(self):
        self.team_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def record_match(
        self,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        date: pd.Timestamp
    ):
        """Record completed match into team history logs."""
        h_norm = normalize_intl_team_name(home_team)
        a_norm = normalize_intl_team_name(away_team)

        pts_h = 3 if fthg > ftag else (1 if fthg == ftag else 0)
        pts_a = 3 if ftag > fthg else (1 if ftag == fthg else 0)

        self.team_history[h_norm].append({
            "date": date,
            "gf": fthg,
            "ga": ftag,
            "pts": pts_h,
            "opponent": a_norm,
            "venue": "H",
        })
        self.team_history[a_norm].append({
            "date": date,
            "gf": ftag,
            "ga": fthg,
            "pts": pts_a,
            "opponent": h_norm,
            "venue": "A",
        })

    def get_team_rolling_features(
        self,
        team: str,
        current_date: pd.Timestamp,
        n_matches: int = 5
    ) -> Dict[str, float]:
        """Compute rolling points, goals scored, goals conceded, and goal difference."""
        norm = normalize_intl_team_name(team)
        history = self.team_history.get(norm)
        if not history and team in self.team_history:
            history = self.team_history[team]

        matches = [m for m in (history or []) if m["date"] < current_date]
        if not matches:
            return {
                "ppg": 1.35,
                "gf": 1.35,
                "ga": 1.35,
                "gd": 0.0,
                f"ppg_last{n_matches}": 1.35,
                f"gf_per_game_last{n_matches}": 1.35,
                f"ga_per_game_last{n_matches}": 1.35,
                f"gd_per_game_last{n_matches}": 0.0,
            }

        recent = matches[-n_matches:]
        k = len(recent)
        pts = sum(m["pts"] for m in recent) / k
        gf = sum(m["gf"] for m in recent) / k
        ga = sum(m["ga"] for m in recent) / k
        gd = gf - ga

        return {
            "ppg": float(pts),
            "gf": float(gf),
            "ga": float(ga),
            "gd": float(gd),
            f"ppg_last{n_matches}": float(pts),
            f"gf_per_game_last{n_matches}": float(gf),
            f"ga_per_game_last{n_matches}": float(ga),
            f"gd_per_game_last{n_matches}": float(gd),
        }


class InternationalHeadToHeadTracker:
    """Tracks historic encounters between pairs of national teams."""

    def __init__(self):
        self.matches: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    def _get_key(self, t1: str, t2: str) -> Tuple[str, str]:
        n1 = normalize_intl_team_name(t1)
        n2 = normalize_intl_team_name(t2)
        return tuple(sorted([n1, n2]))

    def record_match(
        self,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        date: pd.Timestamp
    ):
        """Record completed head-to-head match."""
        h_norm = normalize_intl_team_name(home_team)
        a_norm = normalize_intl_team_name(away_team)
        key = self._get_key(h_norm, a_norm)
        self.matches[key].append({
            "date": date,
            "home_team": h_norm,
            "away_team": a_norm,
            "fthg": fthg,
            "ftag": ftag,
        })

    def get_h2h_features(
        self,
        home_team: str,
        away_team: str,
        current_date: pd.Timestamp,
        max_matches: int = 5
    ) -> Dict[str, float]:
        """Compute pre-match H2H features."""
        h_norm = normalize_intl_team_name(home_team)
        a_norm = normalize_intl_team_name(away_team)
        key = self._get_key(h_norm, a_norm)
        history = [m for m in self.matches.get(key, []) if m["date"] < current_date]

        if not history:
            return {
                "h2h_matches_count": 0.0,
                "h2h_home_win_rate": 0.38,
                "h2h_draw_rate": 0.25,
                "h2h_away_win_rate": 0.37,
                "h2h_avg_total_goals": 2.70,
            }

        recent = history[-max_matches:]
        k = len(recent)
        h_wins = 0
        draws = 0
        a_wins = 0
        total_goals = 0

        for m in recent:
            is_home = (m["home_team"] == h_norm)
            hg = m["fthg"] if is_home else m["ftag"]
            ag = m["ftag"] if is_home else m["fthg"]
            total_goals += (hg + ag)

            if hg > ag:
                h_wins += 1
            elif hg == ag:
                draws += 1
            else:
                a_wins += 1

        return {
            "h2h_matches_count": float(k),
            "h2h_home_win_rate": float(h_wins / k),
            "h2h_draw_rate": float(draws / k),
            "h2h_away_win_rate": float(a_wins / k),
            "h2h_avg_total_goals": float(total_goals / k),
        }


class InternationalDixonColesEngine:
    """Calibrated bivariate Poisson score generator for international football."""

    def __init__(self, elo_engine: InternationalEloEngine):
        self.elo_engine = elo_engine
        self.attack_strengths: Dict[str, float] = {}
        self.defense_strengths: Dict[str, float] = {}

    def predict_match_probabilities(
        self,
        home_team: str,
        away_team: str,
        is_neutral: bool = False
    ) -> Dict[str, float]:
        """Generate score probability distribution using Elo-adjusted Poisson formulation."""
        h_elo = self.elo_engine.get_rating(home_team)
        a_elo = self.elo_engine.get_rating(away_team)
        adv = 0.0 if is_neutral else 65.0
        elo_diff = (h_elo + adv) - a_elo

        home_adv_rate = 0.20 if not is_neutral else 0.0
        elo_xg_adj = (elo_diff / 400.0) * 0.35
        h_xg = max(0.35, min(3.8, float(np.exp(home_adv_rate + elo_xg_adj * 0.5))))
        a_xg = max(0.25, min(3.5, float(np.exp(-elo_xg_adj * 0.5))))

        score_mat = np.zeros((8, 8))
        for h_g in range(8):
            for a_g in range(8):
                score_mat[h_g, a_g] = poisson.pmf(h_g, h_xg) * poisson.pmf(a_g, a_xg)

        # Dixon-Coles tau adjustment for low scores
        rho = -0.04
        score_mat[0, 0] *= max(0.01, 1.0 - h_xg * a_xg * rho)
        score_mat[0, 1] *= max(0.01, 1.0 + h_xg * rho)
        score_mat[1, 0] *= max(0.01, 1.0 + a_xg * rho)
        score_mat[1, 1] *= max(0.01, 1.0 - rho)
        score_mat /= np.sum(score_mat)

        p_home = float(np.sum(np.tril(score_mat, -1)))
        p_draw = float(np.sum(np.diag(score_mat)))
        p_away = float(np.sum(np.triu(score_mat, 1)))
        sum_p = p_home + p_draw + p_away
        if sum_p > 0:
            p_home, p_draw, p_away = p_home / sum_p, p_draw / sum_p, p_away / sum_p

        p_over25 = float(np.sum([score_mat[h, a] for h in range(8) for a in range(8) if h + a > 2.5]))
        p_btts = float(np.sum(score_mat[1:, 1:]))

        return {
            "lambda_home": float(h_xg),
            "mu_away": float(a_xg),
            "prob_home": p_home,
            "prob_draw": p_draw,
            "prob_away": p_away,
            "prob_over25": p_over25,
            "prob_btts_yes": p_btts,
        }


class InternationalFeaturePipeline:
    """
    End-to-end feature pipeline for International Football.
    Maintains historical Elo ratings, rolling form, and H2H statistics across all international matches.
    """

    def __init__(self, data_path: Optional[str] = None):
        self.league_key = "International"
        self.data_path = data_path
        self.elo_engine = InternationalEloEngine()
        self.form_tracker = InternationalFormTracker()
        self.h2h_tracker = InternationalHeadToHeadTracker()
        self.dixon_coles_engine = InternationalDixonColesEngine(self.elo_engine)
        self.feature_names = list(FEATURE_NAMES)
        self.is_fitted = False

    def initialize_from_history(self, df_pre_2018: pd.DataFrame):
        """
        Replay all historical matches (1872-2017, ~41,300 matches) chronologically
        so national teams enter 2018 with authentic historical priors.
        """
        logger.info(f"Initializing international historical priors across {len(df_pre_2018)} pre-2018 matches...")
        sorted_pre = df_pre_2018.sort_values(by="date").reset_index(drop=True)
        for _, row in sorted_pre.iterrows():
            h = str(row["home_team"])
            a = str(row["away_team"])
            hg = int(row["home_score"])
            ag = int(row["away_score"])
            dt = pd.to_datetime(row["date"])
            neutral = bool(row["neutral"])
            self.elo_engine.update_match(h, a, hg, ag, is_neutral=neutral, date=dt)
            self.form_tracker.record_match(h, a, hg, ag, date=dt)
            self.h2h_tracker.record_match(h, a, hg, ag, date=dt)
        self.is_fitted = True
        logger.info(f"Historical priors successfully initialized for {len(self.elo_engine.ratings)} national teams.")

    def process_historical_matches(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Process international matches chronologically:
        1. Pre-2018: used to initialize priors.
        2. 2018-2026: compute pre-match feature vectors X and targets y.
        Returns:
            X: DataFrame with 22 features
            y: DataFrame with target_1x2, target_over25, target_btts, total_goals
        """
        df_clean = df.copy()
        df_clean["date"] = pd.to_datetime(df_clean["date"])
        df_clean = df_clean.sort_values(by="date").reset_index(drop=True)

        pre_2018 = df_clean[df_clean["date"] < "2018-01-01"]
        if not self.is_fitted and len(pre_2018) > 0:
            self.initialize_from_history(pre_2018)

        modern = df_clean[df_clean["date"] >= "2018-01-01"].reset_index(drop=True)
        logger.info(f"Processing features for {len(modern)} modern international matches (2018-2026)...")

        X_rows: List[Dict[str, float]] = []
        y_rows: List[Dict[str, Any]] = []

        for _, row in modern.iterrows():
            h = str(row["home_team"])
            a = str(row["away_team"])
            hg = int(row["home_score"])
            ag = int(row["away_score"])
            dt = row["date"]
            neutral = bool(row["neutral"])
            tourn = str(row.get("tournament", "Friendly"))

            # Build pre-match features (strictly before updating state for this match)
            x_feat = self.build_inference_features(
                home_team=h,
                away_team=a,
                date=dt,
                is_neutral=neutral,
                tournament=tourn,
            ).iloc[0].to_dict()

            # Target outcomes
            if hg > ag:
                t_1x2 = 0
            elif hg == ag:
                t_1x2 = 1
            else:
                t_1x2 = 2

            t_ou25 = 1 if (hg + ag) > 2.5 else 0
            t_btts = 1 if (hg > 0 and ag > 0) else 0

            X_rows.append(x_feat)
            y_rows.append({
                "target_1x2": t_1x2,
                "target_over25": t_ou25,
                "target_btts": t_btts,
                "total_goals": hg + ag,
            })

            # Update engine states after feature calculation
            self.elo_engine.update_match(h, a, hg, ag, is_neutral=neutral, date=dt)
            self.form_tracker.record_match(h, a, hg, ag, date=dt)
            self.h2h_tracker.record_match(h, a, hg, ag, date=dt)

        X = pd.DataFrame(X_rows)[self.feature_names]
        y = pd.DataFrame(y_rows)
        return X, y

    def build_inference_features(
        self,
        home_team: str,
        away_team: str,
        date: Optional[Any] = None,
        is_neutral: bool = False,
        tournament: Optional[str] = None,
        match_date: Optional[Any] = None,
        **kwargs: Any
    ) -> pd.DataFrame:
        """
        Build pre-match inference feature DataFrame for an upcoming match.
        Ensures exact column alignment with trained LightGBM models.
        """
        eff_date = date if date is not None else match_date
        if eff_date is None:
            eff_date = pd.Timestamp.now()
        elif not isinstance(eff_date, pd.Timestamp):
            eff_date = pd.to_datetime(eff_date)

        eff_neutral = bool(is_neutral if is_neutral is not None else kwargs.get("neutral", False))
        eff_tournament = tournament or kwargs.get("tournament_name")

        h_norm = self.elo_engine.resolve_team(home_team)
        a_norm = self.elo_engine.resolve_team(away_team)

        home_elo = self.elo_engine.get_rating(h_norm)
        away_elo = self.elo_engine.get_rating(a_norm)
        elo_diff, elo_prob_home, elo_prob_away = self.elo_engine.compute_expected_probability(
            home_elo, away_elo, is_neutral=eff_neutral
        )

        tourn_imp = get_tournament_importance(eff_tournament)
        neutral_indicator = 1.0 if eff_neutral else 0.0

        h_form = self.form_tracker.get_team_rolling_features(h_norm, eff_date, n_matches=5)
        a_form = self.form_tracker.get_team_rolling_features(a_norm, eff_date, n_matches=5)

        h_ppg = h_form["ppg"]
        a_ppg = a_form["ppg"]
        diff_ppg = h_ppg - a_ppg

        h_gf = h_form["gf"]
        a_gf = a_form["gf"]
        h_ga = h_form["ga"]
        a_ga = a_form["ga"]
        h_gd = h_form["gd"]
        a_gd = a_form["gd"]
        diff_gd = h_gd - a_gd

        h2h = self.h2h_tracker.get_h2h_features(h_norm, a_norm, eff_date, max_matches=5)

        row = {
            "home_elo": float(home_elo),
            "away_elo": float(away_elo),
            "elo_diff": float(elo_diff),
            "elo_prob_home": float(elo_prob_home),
            "elo_prob_away": float(elo_prob_away),
            "is_neutral": float(neutral_indicator),
            "tournament_importance": float(tourn_imp),
            "home_ppg_l5": float(h_ppg),
            "away_ppg_l5": float(a_ppg),
            "diff_ppg_l5": float(diff_ppg),
            "home_gf_l5": float(h_gf),
            "away_gf_l5": float(a_gf),
            "home_ga_l5": float(h_ga),
            "away_ga_l5": float(a_ga),
            "home_gd_l5": float(h_gd),
            "away_gd_l5": float(a_gd),
            "diff_gd_l5": float(diff_gd),
            "h2h_matches_count": float(h2h["h2h_matches_count"]),
            "h2h_home_win_rate": float(h2h["h2h_home_win_rate"]),
            "h2h_draw_rate": float(h2h["h2h_draw_rate"]),
            "h2h_away_win_rate": float(h2h["h2h_away_win_rate"]),
            "h2h_avg_total_goals": float(h2h["h2h_avg_total_goals"]),
        }

        return pd.DataFrame([row])[self.feature_names]
