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

    def fit_from_matches(self, matches_df: pd.DataFrame, time_decay: bool = True, xi: float = 0.0018):
        """
        Fast vectorized Maximum Likelihood Estimation of Dixon-Coles parameters.
        """
        if matches_df.empty or len(matches_df) < 20:
            return

        teams = sorted(list(set(matches_df["HomeTeam"].unique()).union(set(matches_df["AwayTeam"].unique()))))
        team_idx = {team: i for i, team in enumerate(teams)}
        n_teams = len(teams)

        # Precompute match arrays
        h_i = np.array([team_idx[t] for t in matches_df["HomeTeam"]], dtype=int)
        a_j = np.array([team_idx[t] for t in matches_df["AwayTeam"]], dtype=int)
        x_arr = np.array(matches_df["FTHG"], dtype=int)
        y_arr = np.array(matches_df["FTAG"], dtype=int)

        max_date = matches_df["Date"].max()
        days_diff = (max_date - matches_df["Date"]).dt.total_seconds().values / 86400.0
        weights = np.exp(-xi * days_diff) if time_decay else np.ones(len(matches_df))

        mask_00 = (x_arr == 0) & (y_arr == 0)
        mask_01 = (x_arr == 0) & (y_arr == 1)
        mask_10 = (x_arr == 1) & (y_arr == 0)
        mask_11 = (x_arr == 1) & (y_arr == 1)

        init_params = np.zeros(2 * n_teams + 2)
        init_params[-2] = 0.25
        init_params[-1] = -0.04

        def loss_func(params):
            att = params[:n_teams]
            defe = params[n_teams: 2 * n_teams]
            h_adv = params[-2]
            r = params[-1]

            att = att - np.mean(att)

            lam = np.exp(h_adv + att[h_i] - defe[a_j])
            mu_g = np.exp(att[a_j] - defe[h_i])

            tau = np.ones(len(x_arr))
            tau[mask_00] = np.maximum(1e-6, 1.0 - lam[mask_00] * mu_g[mask_00] * r)
            tau[mask_01] = np.maximum(1e-6, 1.0 + lam[mask_01] * r)
            tau[mask_10] = np.maximum(1e-6, 1.0 + mu_g[mask_10] * r)
            tau[mask_11] = np.maximum(1e-6, 1.0 - r)

            px = poisson.pmf(x_arr, lam)
            py = poisson.pmf(y_arr, mu_g)
            pm = np.maximum(1e-9, tau * px * py)

            return -float(np.sum(weights * np.log(pm)))

        try:
            res = minimize(
                loss_func,
                init_params,
                method="SLSQP",
                options={"maxiter": 60, "ftol": 1e-3}
            )
            if res.success or res.fun is not None:
                att_res = res.x[:n_teams] - np.mean(res.x[:n_teams])
                def_res = res.x[n_teams: 2 * n_teams]
                self.home_adv = float(res.x[-2])
                self.rho = float(res.x[-1])

                for team, idx in team_idx.items():
                    self.attack_strengths[team] = float(att_res[idx])
                    self.defense_strengths[team] = float(def_res[idx])
        except Exception:
            self._fit_empirical(matches_df)

    def _fit_empirical(self, df: pd.DataFrame):
        """Empirical fallback for attack & defense strengths."""
        teams = sorted(list(set(df["HomeTeam"].unique()).union(set(df["AwayTeam"].unique()))))
        avg_home_goals = df["FTHG"].mean()
        avg_away_goals = df["FTAG"].mean()

        for team in teams:
            h_matches = df[df["HomeTeam"] == team]
            a_matches = df[df["AwayTeam"] == team]
            
            scored = h_matches["FTHG"].sum() + a_matches["FTAG"].sum()
            conceded = h_matches["FTAG"].sum() + a_matches["HTHG"].sum()
            total_matches = max(1, len(h_matches) + len(a_matches))

            att = (scored / total_matches) / ((avg_home_goals + avg_away_goals) / 2.0 + 1e-5)
            defense = (conceded / total_matches) / ((avg_home_goals + avg_away_goals) / 2.0 + 1e-5)

            self.attack_strengths[team] = float(np.log(max(0.1, att)))
            self.defense_strengths[team] = float(np.log(max(0.1, defense)))

    def calculate_expected_goals(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """Compute expected goals lambda (Home) and mu (Away)."""
        att_h = self.attack_strengths.get(home_team, 0.0)
        def_a = self.defense_strengths.get(away_team, 0.0)
        att_a = self.attack_strengths.get(away_team, 0.0)
        def_h = self.defense_strengths.get(home_team, 0.0)

        lam = float(np.exp(self.home_adv + att_h - def_a))
        mu_g = float(np.exp(att_a - def_h))

        lam = max(0.2, min(5.0, lam))
        mu_g = max(0.2, min(5.0, mu_g))
        return lam, mu_g

    def generate_score_matrix(self, home_team: str, away_team: str) -> np.ndarray:
        """Generate (max_goals x max_goals) joint probability matrix of match scorelines."""
        lam, mu_g = self.calculate_expected_goals(home_team, away_team)
        matrix = np.zeros((self.max_goals, self.max_goals))

        for x in range(self.max_goals):
            for y in range(self.max_goals):
                tau_val = tau_dixon_coles(x, y, lam, mu_g, self.rho)
                p_x = poisson.pmf(x, lam)
                p_y = poisson.pmf(y, mu_g)
                matrix[x, y] = tau_val * p_x * p_y

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

