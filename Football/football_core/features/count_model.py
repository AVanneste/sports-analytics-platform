"""Fitted team-rate models for match count statistics (corners, cards).

For a statistic recorded per side (home corners / away corners, home cards / away cards), each team
gets a "for" and an "against" rate from a time-decayed, ridge-regularised Poisson fit (the same fit
as the Dixon-Coles goal model, plus an intercept). The match total is modelled as negative binomial
with a league-level dispersion, and cards can carry a shrunk referee factor where referee names exist.
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from football_core.features.dixon_coles import fit_team_poisson


class TeamCountModel:
    def __init__(self, home_cols, away_cols, xi: float = 0.0018, ridge: float = 1.0,
                 referee_col: Optional[str] = None, referee_prior: float = 15.0):
        # Columns are summed per side, e.g. cards = yellows + reds -> ("HY", "HR"), ("AY", "AR")
        self.home_cols = tuple(home_cols) if not isinstance(home_cols, str) else (home_cols,)
        self.away_cols = tuple(away_cols) if not isinstance(away_cols, str) else (away_cols,)
        self.xi, self.ridge = xi, ridge
        self.referee_col, self.referee_prior = referee_col, referee_prior
        self.fitted = False

    def _side_totals(self, frame: pd.DataFrame, cols) -> np.ndarray:
        values = [pd.to_numeric(frame[c], errors="coerce").to_numpy(dtype=float) if c in frame.columns
                  else np.full(len(frame), np.nan) for c in cols]
        return np.sum(values, axis=0)

    def fit(self, matches: pd.DataFrame) -> "TeamCountModel":
        home = self._side_totals(matches, self.home_cols)
        away = self._side_totals(matches, self.away_cols)
        ok = np.isfinite(home) & np.isfinite(away)
        data = matches[ok]
        if len(data) < 50:
            self.fitted = False
            return self
        home, away = home[ok], away[ok]
        teams = sorted(set(data["HomeTeam"]) | set(data["AwayTeam"]))
        self.team_idx = {t: i for i, t in enumerate(teams)}
        h_i = np.array([self.team_idx[t] for t in data["HomeTeam"]], dtype=int)
        a_j = np.array([self.team_idx[t] for t in data["AwayTeam"]], dtype=int)
        days = (data["Date"].max() - data["Date"]).dt.total_seconds().to_numpy() / 86400.0
        weights = np.exp(-self.xi * days)

        fitted = fit_team_poisson(h_i, a_j, home, away, weights, len(teams), self.ridge, intercept=True)
        if fitted is None:
            self.fitted = False
            return self
        self.att, self.dfn, self.home_adv, self.level = fitted
        self.fitted = True

        lam = np.exp(self.level + self.home_adv + self.att[h_i] - self.dfn[a_j])
        mu = np.exp(self.level + self.att[a_j] - self.dfn[h_i])
        expected, total = lam + mu, home + away

        # Referee factor: weighted observed/expected totals per referee, shrunk toward 1
        self.referee_factor: Dict[str, float] = {}
        if self.referee_col and self.referee_col in data.columns:
            refs = data[self.referee_col].astype(str).str.strip()
            valid = ~refs.str.lower().isin(["", "nan", "none"])
            frame = pd.DataFrame({"ref": refs[valid], "obs": (weights * total)[valid.to_numpy()],
                                  "exp": (weights * expected)[valid.to_numpy()]})
            for ref, grp in frame.groupby("ref"):
                k = self.referee_prior * float(np.mean(expected))  # prior worth ~referee_prior matches
                self.referee_factor[ref] = float((grp["obs"].sum() + k) / (grp["exp"].sum() + k))

        # Negative-binomial dispersion of the match total (NB2: var = m + alpha * m^2), by moments
        resid_var = np.average((total - expected) ** 2, weights=weights)
        mean_m = np.average(expected, weights=weights)
        mean_m2 = np.average(expected ** 2, weights=weights)
        self.alpha = float(max(0.0, (resid_var - mean_m) / mean_m2))
        return self

    def expected(self, home: str, away: str, referee: Optional[str] = None) -> float:
        """Expected match total; unknown teams take league-average rates."""
        hi, ai = self.team_idx.get(home), self.team_idx.get(away)
        att_h = self.att[hi] if hi is not None else 0.0
        att_a = self.att[ai] if ai is not None else 0.0
        def_h = self.dfn[hi] if hi is not None else 0.0
        def_a = self.dfn[ai] if ai is not None else 0.0
        m = np.exp(self.level + self.home_adv + att_h - def_a) + np.exp(self.level + att_a - def_h)
        if referee:
            m *= self.referee_factor.get(str(referee).strip(), 1.0)
        return float(m)

    def prob_over(self, home: str, away: str, line: float, referee: Optional[str] = None) -> float:
        """P(match total > line) under the negative-binomial total."""
        m = self.expected(home, away, referee)
        k = int(np.floor(line))
        if self.alpha <= 1e-6:
            return float(1.0 - poisson.cdf(k, m))
        n = 1.0 / self.alpha
        return float(1.0 - nbinom.cdf(k, n, n / (n + m)))


def corners_model(**kwargs) -> TeamCountModel:
    return TeamCountModel("HC", "AC", **kwargs)


def cards_model(**kwargs) -> TeamCountModel:
    return TeamCountModel(("HY", "HR"), ("AY", "AR"), referee_col="Referee", **kwargs)
