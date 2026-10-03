"""Dixon-Coles & Poisson Goal Expectancy Engine for Football Match Outcomes."""
import numpy as np
import pandas as pd
from scipy.stats import poisson
from scipy.optimize import minimize
from typing import Dict, Tuple, Optional, List


def tau_dixon_coles(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Low score correlation adjustment factor for Dixon-Coles."""
    if x == 0 and y == 0:
        return max(1e-6, 1.0 - lam * mu * rho)
    elif x == 0 and y == 1:
        return max(1e-6, 1.0 + lam * rho)
    elif x == 1 and y == 0:
        return max(1e-6, 1.0 + mu * rho)
    elif x == 1 and y == 1:
        return max(1e-6, 1.0 - rho)
    else:
        return 1.0


def fit_team_poisson(home_idx: np.ndarray, away_idx: np.ndarray, x_target: np.ndarray, y_target: np.ndarray,
                     weights: np.ndarray, n_teams: int, ridge: float, intercept: bool = False):
    """Weighted, ridge-regularised Poisson fit of team attack/defence and home advantage.

    log E[home count] = c + h + att[home] - def[away];  log E[away count] = c + att[away] - def[home].
    The ridge penalty applies to att/def only. Without ``intercept`` the overall level is carried by
    the defence parameters (the Dixon-Coles convention, fine for goals); with it, an unpenalised c
    carries the level, which count statistics far from 1 per team (corners, cards) need.
    Returns (att, def, h, c) with mean attack 0, or None if the optimiser fails.
    """
    n_extra = 2 if intercept else 1

    def objective(params):
        att, dfn, h_adv = params[:n_teams], params[n_teams:2 * n_teams], params[2 * n_teams]
        c = params[-1] if intercept else 0.0
        log_lam = np.clip(c + h_adv + att[home_idx] - dfn[away_idx], -10.0, 10.0)
        log_mu = np.clip(c + att[away_idx] - dfn[home_idx], -10.0, 10.0)
        lam, mu = np.exp(log_lam), np.exp(log_mu)
        nll = -np.sum(weights * (x_target * log_lam - lam + y_target * log_mu - mu))
        nll += 0.5 * ridge * (att @ att + dfn @ dfn)
        r_lam = weights * (x_target - lam)
        r_mu = weights * (y_target - mu)
        g_att = -(np.bincount(home_idx, r_lam, n_teams) + np.bincount(away_idx, r_mu, n_teams)) + ridge * att
        g_dfn = (np.bincount(away_idx, r_lam, n_teams) + np.bincount(home_idx, r_mu, n_teams)) + ridge * dfn
        grads = [g_att, g_dfn, [-np.sum(r_lam)]]
        if intercept:
            grads.append([-np.sum(r_lam) - np.sum(r_mu)])
        return nll, np.concatenate(grads)

    x0 = np.zeros(2 * n_teams + n_extra)
    x0[2 * n_teams] = 0.25
    if intercept:
        total = np.sum(weights * (x_target + y_target)) / max(2 * np.sum(weights), 1e-9)
        x0[-1] = float(np.log(max(total, 1e-3)))
    try:
        res = minimize(objective, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
    except (ValueError, FloatingPointError):
        return None
    if not np.all(np.isfinite(res.x)):
        return None
    att, dfn = res.x[:n_teams].copy(), res.x[n_teams:2 * n_teams].copy()
    h_adv = float(res.x[2 * n_teams])
    c = float(res.x[-1]) if intercept else 0.0
    shift = att.mean()  # identifiability: mean attack 0 (expected counts are unchanged)
    return att - shift, dfn - shift, h_adv, c


class DixonColesEngine:
    """
    Fits and calculates Dixon-Coles attack/defense parameters, score matrices,
    and outcome probabilities (1X2, Over/Under 2.5, BTTS).
    """

    def __init__(self, max_goals: int = 9, rho: float = -0.04):
        self.max_goals = max_goals
        self.rho = rho
        self.home_adv = 0.25
        self.mu = 0.0
        self.attack_strengths: Dict[str, float] = {}
        self.defense_strengths: Dict[str, float] = {}
        # Cache of fitted parameters keyed by (year, month) to avoid refitting per match
        self._monthly_cache: Dict[Tuple[int, int], Dict] = {}

    # Fit settings, tuned by walk-forward backtest (scripts/tune_model.py). On the unseen
    # 2024/25+ seasons they beat the old 0.0018 / 1.0 / 0.0 on exact-score, O/U 2.5 and BTTS log
    # loss; 1X2 log loss is unchanged.
    XI = 0.0025          # time decay per day: a match from t days ago weighs exp(-XI * t)
    RIDGE = 8.0          # Gaussian prior on log attack/defence strengths (keeps sparse teams sane)
    SOT_WEIGHT = 0.35    # share of the strength target taken from shots on target instead of goals
    RHO_GRID = np.linspace(-0.20, 0.10, 31)

    def fit_from_matches(self, matches_df: pd.DataFrame, time_decay: bool = True,
                         xi: Optional[float] = None, sot_weight: Optional[float] = None):
        """
        Time-weighted, ridge-regularised Poisson maximum likelihood for attack/defence/home advantage
        (L-BFGS with an analytic gradient), then the Dixon-Coles low-score correlation ``rho`` by a
        one-dimensional likelihood search.

        With ``sot_weight`` w > 0 the strengths are fitted on a blend of goals and shots on target:
        target = (1 - w) * goals + w * k * shots_on_target, where k is the league's goals-per-shot-on-
        target rate. Shots on target are a less noisy signal of chance creation than goals; the
        low-score correlation is still fitted on actual goals.
        """
        if matches_df.empty or len(matches_df) < 20:
            return
        xi = self.XI if xi is None else xi
        sot_weight = self.SOT_WEIGHT if sot_weight is None else sot_weight

        teams = sorted(set(matches_df["HomeTeam"].unique()).union(set(matches_df["AwayTeam"].unique())))
        team_idx = {team: i for i, team in enumerate(teams)}
        n_teams = len(teams)

        h_i = np.array([team_idx[t] for t in matches_df["HomeTeam"]], dtype=int)
        a_j = np.array([team_idx[t] for t in matches_df["AwayTeam"]], dtype=int)
        x_arr = np.asarray(matches_df["FTHG"], dtype=float)
        y_arr = np.asarray(matches_df["FTAG"], dtype=float)
        x_target, y_target = self._strength_targets(matches_df, x_arr, y_arr, sot_weight)

        max_date = matches_df["Date"].max()
        days_diff = (max_date - matches_df["Date"]).dt.total_seconds().values / 86400.0
        weights = np.exp(-xi * days_diff) if time_decay else np.ones(len(matches_df))

        fitted = fit_team_poisson(h_i, a_j, x_target, y_target, weights, n_teams, self.RIDGE)
        if fitted is None:
            self._fit_empirical(matches_df)
            return
        att, dfn, h_adv, _ = fitted

        lam = np.exp(np.clip(h_adv + att[h_i] - dfn[a_j], -10.0, 10.0))
        mu = np.exp(np.clip(att[a_j] - dfn[h_i], -10.0, 10.0))
        low = (x_arr <= 1) & (y_arr <= 1)
        best_rho, best_ll = self.rho, -np.inf
        for r in self.RHO_GRID:
            tau = np.ones(low.sum())
            xl, yl, ll_, ml_ = x_arr[low], y_arr[low], lam[low], mu[low]
            tau = np.where((xl == 0) & (yl == 0), 1.0 - ll_ * ml_ * r, tau)
            tau = np.where((xl == 0) & (yl == 1), 1.0 + ll_ * r, tau)
            tau = np.where((xl == 1) & (yl == 0), 1.0 + ml_ * r, tau)
            tau = np.where((xl == 1) & (yl == 1), 1.0 - r, tau)
            score = float(np.sum(weights[low] * np.log(np.maximum(tau, 1e-6))))
            if score > best_ll:
                best_rho, best_ll = round(float(r), 3), score

        self.home_adv = h_adv
        self.rho = best_rho
        self.attack_strengths = {team: float(att[i]) for team, i in team_idx.items()}
        self.defense_strengths = {team: float(dfn[i]) for team, i in team_idx.items()}

    @staticmethod
    def _strength_targets(matches_df: pd.DataFrame, goals_h: np.ndarray, goals_a: np.ndarray,
                          sot_weight: float):
        """Goals, or a goals / shots-on-target blend, as the Poisson targets for team strengths."""
        if sot_weight <= 0 or not {"HST", "AST"}.issubset(matches_df.columns):
            return goals_h, goals_a
        sot_h = pd.to_numeric(matches_df["HST"], errors="coerce").to_numpy(dtype=float)
        sot_a = pd.to_numeric(matches_df["AST"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(sot_h) & np.isfinite(sot_a)
        if ok.sum() < 20 or (sot_h[ok] + sot_a[ok]).sum() <= 0:
            return goals_h, goals_a
        k = (goals_h[ok] + goals_a[ok]).sum() / (sot_h[ok] + sot_a[ok]).sum()
        target_h = np.where(ok, (1 - sot_weight) * goals_h + sot_weight * k * np.nan_to_num(sot_h), goals_h)
        target_a = np.where(ok, (1 - sot_weight) * goals_a + sot_weight * k * np.nan_to_num(sot_a), goals_a)
        return target_h, target_a

    def _fit_empirical(self, df: pd.DataFrame):
        """Empirical fallback for attack & defense strengths."""
        teams = sorted(list(set(df["HomeTeam"].unique()).union(set(df["AwayTeam"].unique()))))
        avg_home_goals = df["FTHG"].mean()
        avg_away_goals = df["FTAG"].mean()

        for team in teams:
            h_matches = df[df["HomeTeam"] == team]
            a_matches = df[df["AwayTeam"] == team]
            
            scored = h_matches["FTHG"].sum() + a_matches["FTAG"].sum()
            conceded = h_matches["FTAG"].sum() + a_matches["FTHG"].sum()
            total_matches = max(1, len(h_matches) + len(a_matches))

            att = (scored / total_matches) / ((avg_home_goals + avg_away_goals) / 2.0 + 1e-5)
            defense = (conceded / total_matches) / ((avg_home_goals + avg_away_goals) / 2.0 + 1e-5)

            self.attack_strengths[team] = float(np.log(max(0.1, att)))
            self.defense_strengths[team] = float(np.log(max(0.1, defense)))

    def precompute_monthly_snapshots(self, all_matches_df: pd.DataFrame, xi: Optional[float] = None):
        """
        Pre-compute Dixon-Coles parameter snapshots at monthly boundaries.
        
        For each unique (year, month) in the dataset, fit parameters using only
        matches strictly before the 1st of that month. This ensures that when
        features are extracted for a match on date D, only past data is used.
        
        Results are cached in self._monthly_cache for fast lookup.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if all_matches_df.empty:
            return
        
        sorted_df = all_matches_df.sort_values("Date").reset_index(drop=True)
        
        # Collect unique (year, month) boundaries
        sorted_df["_ym"] = sorted_df["Date"].dt.to_period("M")
        unique_months = sorted(sorted_df["_ym"].unique())
        
        self._monthly_cache = {}
        
        for i, period in enumerate(unique_months):
            year, month = period.year, period.month
            cutoff = pd.Timestamp(year=year, month=month, day=1)
            
            # Get all matches BEFORE this month
            past_matches = sorted_df[sorted_df["Date"] < cutoff]
            
            if len(past_matches) < 30:
                # Not enough data — skip (first few months will use empirical fallback)
                continue
            
            # Create a temporary engine to fit parameters without mutating self
            temp_engine = type(self)(max_goals=self.max_goals)
            temp_engine.XI, temp_engine.RIDGE, temp_engine.SOT_WEIGHT = self.XI, self.RIDGE, self.SOT_WEIGHT
            temp_engine.fit_from_matches(past_matches, time_decay=True, xi=xi)
            
            self._monthly_cache[(year, month)] = {
                "attack": dict(temp_engine.attack_strengths),
                "defense": dict(temp_engine.defense_strengths),
                "home_adv": temp_engine.home_adv,
                "rho": temp_engine.rho,
            }
        
        sorted_df.drop(columns=["_ym"], inplace=True, errors="ignore")
        logger.info(f"Pre-computed {len(self._monthly_cache)} monthly Dixon-Coles snapshots")

    def load_snapshot_for_date(self, match_date: pd.Timestamp):
        """
        Load the most recent monthly snapshot into self.attack_strengths etc.
        for a given match date. Uses the snapshot from the month of the match
        (which was fitted on data strictly before that month).
        """
        if not self._monthly_cache:
            return  # No snapshots available, keep current state
        
        year, month = match_date.year, match_date.month
        key = (year, month)
        
        # Try exact month first, then fall back to most recent prior month
        if key not in self._monthly_cache:
            prior_keys = [k for k in sorted(self._monthly_cache.keys()) if k < key]
            if prior_keys:
                key = prior_keys[-1]
            else:
                return  # No prior snapshot, keep current state
        
        snapshot = self._monthly_cache[key]
        self.attack_strengths = dict(snapshot["attack"])
        self.defense_strengths = dict(snapshot["defense"])
        self.home_adv = snapshot["home_adv"]
        self.rho = snapshot["rho"]

    def calculate_expected_goals(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """Compute expected goals lambda (Home) and mu (Away)."""
        att_h = self.attack_strengths.get(home_team, 0.0)
        def_a = self.defense_strengths.get(away_team, 0.0)
        att_a = self.attack_strengths.get(away_team, 0.0)
        def_h = self.defense_strengths.get(home_team, 0.0)

        lam = float(np.exp(np.clip(self.home_adv + att_h - def_a, np.log(0.2), np.log(5.0))))
        mu_g = float(np.exp(np.clip(att_a - def_h, np.log(0.2), np.log(5.0))))
        return lam, mu_g

    def generate_score_matrix(self, home_team: str, away_team: str) -> np.ndarray:
        """Generate (max_goals x max_goals) joint probability matrix of match scorelines."""
        lam, mu_g = self.calculate_expected_goals(home_team, away_team)
        goals = np.arange(self.max_goals)
        matrix = np.outer(poisson.pmf(goals, lam), poisson.pmf(goals, mu_g))
        matrix[0, 0] *= max(1e-6, 1.0 - lam * mu_g * self.rho)
        matrix[0, 1] *= max(1e-6, 1.0 + lam * self.rho)
        matrix[1, 0] *= max(1e-6, 1.0 + mu_g * self.rho)
        matrix[1, 1] *= max(1e-6, 1.0 - self.rho)

        total_p = matrix.sum()
        if total_p > 0:
            matrix = matrix / total_p

        return matrix

    def predict_match_probabilities(self, home_team: str, away_team: str) -> Dict[str, any]:
        """Compute analytical outcome probabilities from joint score matrix."""
        matrix = self.generate_score_matrix(home_team, away_team)
        lam, mu_g = self.calculate_expected_goals(home_team, away_team)

        # 1X2 Probabilities
        prob_home = float(np.sum(np.tril(matrix, -1)))
        prob_draw = float(np.sum(np.diag(matrix)))
        prob_away = float(np.sum(np.triu(matrix, 1)))

        # Over / Under 2.5
        grid_x, grid_y = np.meshgrid(np.arange(self.max_goals), np.arange(self.max_goals), indexing="ij")
        total_goals_grid = grid_x + grid_y
        prob_over25 = float(np.sum(matrix[total_goals_grid > 2.5]))
        prob_under25 = float(1.0 - prob_over25)

        # Both Teams To Score (BTTS)
        prob_btts_yes = float(np.sum(matrix[1:, 1:]))
        prob_btts_no = float(1.0 - prob_btts_yes)

        # Most Likely Score
        max_idx = np.unravel_index(np.argmax(matrix, axis=None), matrix.shape)
        most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
        score_prob = float(matrix[max_idx])

        return {
            "lambda_home": lam,
            "mu_away": mu_g,
            "prob_home": prob_home,
            "prob_draw": prob_draw,
            "prob_away": prob_away,
            "prob_over25": prob_over25,
            "prob_under25": prob_under25,
            "prob_btts_yes": prob_btts_yes,
            "prob_btts_no": prob_btts_no,
            "most_likely_score": most_likely_score,
            "most_likely_score_prob": score_prob,
            "score_matrix": matrix.tolist(),
        }

