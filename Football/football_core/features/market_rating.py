"""Team ratings learned from how bookmakers priced each team's previous matches.

Each team carries a strength rating, updated after every match from the vig-free closing price of that
match (never from the match being predicted): the rating gap says how the market has priced the team
against its opponents recently, which squad strength, injuries and form all feed into. A second rating
per team does the same for the goals total (over/under 2.5). A multinomial logistic fitted on the
replayed history turns a rating gap into 1X2 probabilities. Walk-forward on 21,500 matches in 19 leagues
(2022-2026) this sits 0.008 log loss behind the market's own closing price, against 0.023 for the
deployed model that does not read prices.

The current match's price is never an input; past closing prices are, by decision of 12 Nov 2026
(earlier "bookmaker prices are only a yardstick" rule). The model therefore cannot beat the market it
learns from: it is information for the match cards, not a source of value picks.
"""
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from sports_common.betting import devig

CLOSE_1X2 = [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365H", "B365D", "B365A")]
CLOSE_OU = [("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5"), ("B365>2.5", "B365<2.5")]
MIN_SEEN = 5  # a team needs this many priced matches before its rating is trusted


def closing_probs(df: pd.DataFrame, candidates, width: int) -> np.ndarray:
    """Vig-free closing probabilities per row (NaN where no listed bookmaker has a price), trying the
    column groups in order: Pinnacle, then the market average, then Bet365."""
    out = np.full((len(df), width), np.nan)
    for cols in candidates:
        if not all(c in df.columns for c in cols):
            continue
        prices = df[list(cols)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
        for i in np.flatnonzero(np.isnan(out[:, 0])):
            p = devig(prices[i])
            if p is not None:
                out[i] = p
    return out


def _features(s: np.ndarray) -> np.ndarray:
    return np.column_stack([s, np.abs(s), s ** 2])


class MarketRatingEngine:
    """Online ratings from closing prices; ``fit`` replays a results table (sorted by date)."""

    def __init__(self, k: float = 0.22, k_total: float = 0.12, k_home: float = 0.01, new_team_boost: float = 2.5):
        self.k, self.k_total, self.k_home, self.boost = k, k_total, k_home, new_team_boost
        self.rating: Dict[str, float] = {}
        self.total: Dict[str, float] = {}
        self.count: Dict[str, int] = {}
        self.home_adv, self.total_base = 0.35, 0.0
        self.clf_1x2: Optional[LogisticRegression] = None
        self.clf_ou: Optional[LogisticRegression] = None

    def _gap(self, home: str, away: str) -> Tuple[float, float]:
        return (self.home_adv + self.rating.get(home, 0.0) - self.rating.get(away, 0.0),
                self.total_base + self.total.get(home, 0.0) + self.total.get(away, 0.0))

    def fit(self, matches: pd.DataFrame) -> "MarketRatingEngine":
        """Replay ``matches`` (Date, HomeTeam, AwayTeam, FTHG, FTAG and the closing-price columns)."""
        m = matches.sort_values("Date", kind="mergesort")
        p1x2 = closing_probs(m, CLOSE_1X2, 3)
        pou = closing_probs(m, CLOSE_OU, 2)
        goals = (m["FTHG"].to_numpy(float) + m["FTAG"].to_numpy(float))
        result = np.where(m["FTHG"] > m["FTAG"], 0, np.where(m["FTHG"] == m["FTAG"], 1, 2))
        s_rows, t_rows, ys, yo, ts = [], [], [], [], []
        for i, (home, away) in enumerate(zip(m["HomeTeam"], m["AwayTeam"])):
            s_pred, t_pred = self._gap(home, away)
            seen = min(self.count.get(home, 0), self.count.get(away, 0))
            if seen >= MIN_SEEN and not np.isnan(p1x2[i, 0]):
                s_rows.append(s_pred); ys.append(result[i])
            if seen >= MIN_SEEN and not np.isnan(pou[i, 0]) and goals[i] == goals[i]:
                t_rows.append(t_pred); yo.append(int(goals[i] > 2.5))
            boost = self.boost if seen < MIN_SEEN else 1.0
            if not np.isnan(p1x2[i, 0]):
                err = np.log(p1x2[i, 0] / p1x2[i, 2]) - s_pred
                self.rating[home] = self.rating.get(home, 0.0) + self.k * boost * err
                self.rating[away] = self.rating.get(away, 0.0) - self.k * boost * err
                self.home_adv += self.k_home * err
            if not np.isnan(pou[i, 0]):
                err_t = np.log(pou[i, 0] / pou[i, 1]) - t_pred
                self.total[home] = self.total.get(home, 0.0) + self.k_total * boost * err_t / 2
                self.total[away] = self.total.get(away, 0.0) + self.k_total * boost * err_t / 2
                self.total_base += 0.002 * err_t
            self.count[home] = self.count.get(home, 0) + 1
            self.count[away] = self.count.get(away, 0) + 1
        if len(ys) >= 200 and len(set(ys)) == 3:
            self.clf_1x2 = LogisticRegression(max_iter=2000, C=10).fit(_features(np.array(s_rows)), ys)
        if len(yo) >= 200 and len(set(yo)) == 2:
            self.clf_ou = LogisticRegression(max_iter=2000, C=10).fit(np.array(t_rows)[:, None], yo)
        return self

    def predict(self, home: str, away: str) -> Optional[Dict[str, float]]:
        """{p_home, p_draw, p_away, p_over25, seen} for a fixture, None before the engine is fitted;
        ``seen`` is the fewer priced matches either team has (under MIN_SEEN the rating is thin)."""
        if self.clf_1x2 is None:
            return None
        s, t = self._gap(home, away)
        p = self.clf_1x2.predict_proba(_features(np.array([s])))[0]
        out = {"p_home": float(p[0]), "p_draw": float(p[1]), "p_away": float(p[2]),
               "seen": min(self.count.get(home, 0), self.count.get(away, 0))}
        if self.clf_ou is not None:
            out["p_over25"] = float(self.clf_ou.predict_proba(np.array([[t]]))[0][1])
        return out
