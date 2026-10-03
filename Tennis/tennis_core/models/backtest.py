"""Walk-forward evaluation of tennis match-winner models, accuracy first.

Rating models (ranking, Elo) are sequential: every match is predicted from ratings built on
earlier matches only. Fitted models (logistic calibrations, the production LightGBM) are refitted
on the matches before each cut-off and predict the matches up to the next one. Each match is scored
on the probability that the alphabetically first player wins (fixed before the result): log loss,
Brier score, accuracy and calibration error. Vig-free Pinnacle and Bet365 prices are scored the
same way as a yardstick only; no model uses odds as an input.
"""
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from sports_common.betting import devig
from sports_common.evaluation import ece, paired_difference
from sports_common.parallel import limit_worker_threads
from tennis_core.config import END_YEAR, LEVEL_K_MULTIPLIERS, PRIMARY_SURFACES, START_YEAR

logger = logging.getLogger(__name__)
EPS = 1e-12
MARKETS = {"pinnacle": ("pinnacle_winner_odds", "pinnacle_loser_odds"), "bet365": ("winner_odds", "loser_odds")}


# ------------------------------------------------------------------ scoring
def first_player_view(matches: pd.DataFrame, p_winner: np.ndarray):
    """(p, y): the probability and the outcome for the alphabetically first player of each match."""
    winner_first = (matches["winner_name"].astype(str) <= matches["loser_name"].astype(str)).to_numpy()
    return np.where(winner_first, p_winner, 1.0 - p_winner), winner_first.astype(int)


def score_predictions(matches: pd.DataFrame, p_winner: pd.Series) -> Dict[str, float]:
    """Accuracy metrics for P(actual winner wins) per match."""
    p_winner = p_winner.dropna()
    p_w = np.clip(p_winner.to_numpy(dtype=float), EPS, 1 - EPS)
    if not len(p_w):
        return {}
    p, y = first_player_view(matches.loc[p_winner.index], p_w)
    return {"n": int(len(p_w)), "log_loss": round(float(np.mean(-np.log(p_w))), 4),
            "brier": round(float(np.mean((1.0 - p_w) ** 2)), 4),
            "accuracy": round(float(np.mean(p_w > 0.5) + 0.5 * np.mean(p_w == 0.5)), 4),
            "ece": round(ece(p, y), 4)}


def match_losses(p_winner: pd.Series) -> pd.Series:
    return -np.log(np.clip(p_winner.astype(float), EPS, 1.0))


def compare(preds: Dict[str, pd.Series], reference: str) -> Dict[str, Dict[str, float]]:
    """Mean log-loss difference of each model vs ``reference`` on their common matches."""
    if reference not in preds:
        return {}
    ref = match_losses(preds[reference])
    out = {}
    for name, p in preds.items():
        if name == reference:
            continue
        joined = pd.concat([match_losses(p), ref], axis=1, join="inner").dropna()
        if len(joined):
            diff = paired_difference(joined.iloc[:, 0], joined.iloc[:, 1])
            out[name] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in diff.items()}
    return out


def market_predictions(matches: pd.DataFrame, winner_col: str, loser_col: str) -> pd.Series:
    """Vig-free P(winner) from a bookmaker's prices (NaN where a price is missing)."""
    if not {winner_col, loser_col}.issubset(matches.columns):
        return pd.Series(np.nan, index=matches.index)
    probs = [m[0] if (m := devig([ow, ol])) is not None else np.nan
             for ow, ol in zip(matches[winner_col], matches[loser_col])]
    return pd.Series(probs, index=matches.index, dtype=float)


# ------------------------------------------------------------------ models
class EloRatingModel:
    """Sequential tennis Elo (features.elo.DecayingKElo, the production ratings): every match is
    predicted from ratings built on earlier matches only. ``settings`` override the tuned defaults."""

    kind = "sequential"

    def __init__(self, name: str = "elo", **settings):
        self.name, self.settings = name, settings

    @staticmethod
    def games_share(matches: pd.DataFrame) -> np.ndarray:
        """The winner's share of the games played (NaN when the score is unknown)."""
        won, lost = np.zeros(len(matches)), np.zeros(len(matches))
        for i in range(1, 6):
            for side, col in ((won, f"W{i}"), (lost, f"L{i}")):
                if col in matches.columns:
                    side += pd.to_numeric(matches[col], errors="coerce").fillna(0).to_numpy(dtype=float)
        total = won + lost
        return np.where(total > 0, won / np.maximum(total, 1.0), np.nan)

    def run(self, matches: pd.DataFrame) -> pd.Series:
        from tennis_core.features.elo import DecayingKElo
        elo = DecayingKElo(**self.settings)
        shares = self.games_share(matches)
        out = np.empty(len(matches))
        rows = zip(matches["winner_name"], matches["loser_name"], matches["surface"], matches["tourney_level"], shares)
        for i, (w, l, surface, level, share) in enumerate(rows):
            out[i] = elo.win_probability(w, l, surface)
            elo.update(w, l, surface, level, None if np.isnan(share) else float(share))
        return pd.Series(out, index=matches.index)


class SymmetricLogit:
    """Logistic regression on feature differences, fitted on the mirrored rows without an intercept."""

    kind, needs_features = "fitted", True

    def __init__(self, name: str, columns: Sequence[str], C: float = 1.0, refit: str = "MS"):
        self.name, self.columns, self.C, self.refit = name, list(columns), C, refit

    def fit(self, matches, X_hist, y_hist):
        from sklearn.linear_model import LogisticRegression
        frame = X_hist[self.columns].fillna(0.0)
        self.clf = LogisticRegression(C=self.C, fit_intercept=False, max_iter=2000).fit(frame, y_hist)

    def predict_rows(self, X_rows) -> np.ndarray:
        return self.clf.predict_proba(X_rows[self.columns].fillna(0.0))[:, 1]


class ProductionModel:
    """The deployed calibrated LightGBM (train._fit_calibrated on FEATURE_COLUMNS), refitted quarterly.
    ``drop`` leaves feature columns out; ``train_from`` fits only on matches from that date."""

    kind, needs_features, refit = "fitted", True, "QS"

    def __init__(self, name: str = "production", drop: Sequence[str] = (), train_from: Optional[str] = None):
        self.name, self.drop, self.train_from = name, tuple(drop), train_from

    def fit(self, matches, X_hist, y_hist):
        from tennis_core.features.builder import FEATURE_COLUMNS
        from tennis_core.models.train import _fit_calibrated
        self.columns = [c for c in FEATURE_COLUMNS if c in X_hist.columns and c not in self.drop]
        if self.train_from:
            keep = (X_hist["match_date"] >= pd.Timestamp(self.train_from)).to_numpy()
            X_hist, y_hist = X_hist[keep], y_hist[keep]
        self.model = _fit_calibrated(X_hist[self.columns], y_hist)

    def predict_rows(self, X_rows) -> np.ndarray:
        return self.model.predict_proba(X_rows[self.columns])[:, 1]


def baseline_models() -> list:
    return [
        SymmetricLogit("rank", ["log_rank_ratio"]),
        SymmetricLogit("elo_features", ["elo_diff", "effective_surface_elo_diff"]),
        EloRatingModel("elo"),
        ProductionModel(),
    ]


# ------------------------------------------------------------------ walk-forward
def prepare_circuit(circuit: str, start_year: int = START_YEAR, features: bool = True) -> Dict[str, object]:
    """Cleaned matches (sorted by date, RangeIndex) and, optionally, the mirrored feature rows:
    rows 2i and 2i+1 of X describe match i (winner as player 1, then the mirror)."""
    from tennis_core.data.preprocessor import clean_match_data, load_raw_matches, played_only
    matches = played_only(clean_match_data(load_raw_matches(circuit, start_year, END_YEAR), circuit,
                                           start_year=start_year))
    matches = matches.sort_values("tourney_date", kind="mergesort").reset_index(drop=True)
    X = y = None
    if features:
        from tennis_core.features.builder import TennisFeaturePipeline
        X, y = TennisFeaturePipeline(circuit).process_historical_matches(matches)
        assert len(X) == 2 * len(matches), "feature rows must come in mirrored pairs, one pair per match"
    return {"matches": matches, "X": X, "y": y}


def walk_forward_fitted(matches: pd.DataFrame, X: pd.DataFrame, y: pd.Series, model, eval_from: pd.Timestamp,
                        eval_to: Optional[pd.Timestamp] = None, min_history: int = 1000) -> pd.Series:
    """P(winner) for every match in [eval_from, eval_to), refitting ``model`` at each cut-off."""
    dates = matches["tourney_date"]
    in_eval = (dates >= eval_from) & ((dates < eval_to) if eval_to is not None else True)
    if not in_eval.any():
        return pd.Series(dtype=float)
    last = dates[in_eval].max()
    cuts = [eval_from] + [d for d in pd.date_range(eval_from, last, freq=model.refit) if d > eval_from]
    cuts.append(last + pd.Timedelta(days=1))
    parts = []
    for start, end in zip(cuts[:-1], cuts[1:]):
        window = np.flatnonzero(in_eval & (dates >= start) & (dates < end))
        n_hist = int((dates < start).sum())  # matches are sorted by date: the history is a prefix
        if not len(window) or n_hist < min_history:
            continue
        model.fit(matches.iloc[:n_hist], X.iloc[:2 * n_hist], y.iloc[:2 * n_hist])
        p1 = model.predict_rows(X.iloc[np.ravel(np.column_stack([2 * window, 2 * window + 1]))])
        # antisymmetric average of the two views, as the live predictor does
        parts.append(pd.Series((p1[0::2] + 1.0 - p1[1::2]) / 2.0, index=matches.index[window]))
    return pd.concat(parts) if parts else pd.Series(dtype=float)


def circuit_predictions(args) -> Dict[str, object]:
    circuit, models, eval_from, eval_to, start_year = args
    started = time.time()
    need_features = any(getattr(m, "needs_features", False) for m in models)
    data = prepare_circuit(circuit, start_year, features=need_features)
    matches, X, y = data["matches"], data["X"], data["y"]
    logger.info(f"[tennis backtest] {circuit}: {len(matches)} matches ready ({time.time() - started:.0f}s)")
    dates = matches["tourney_date"]
    in_eval = (dates >= eval_from) & ((dates < eval_to) if eval_to is not None else True)
    preds: Dict[str, pd.Series] = {}
    for model in models:
        t0 = time.time()
        if model.kind == "sequential":
            preds[model.name] = model.run(matches)[in_eval]
        else:
            preds[model.name] = walk_forward_fitted(matches, X, y, model, eval_from, eval_to)
        logger.info(f"[tennis backtest] {circuit}: {model.name} done ({time.time() - t0:.0f}s)")
    evaluated = matches[in_eval]
    for name, (wcol, lcol) in MARKETS.items():
        preds[f"market_{name}"] = market_predictions(evaluated, wcol, lcol)
    return {"circuit": circuit, "matches": evaluated, "preds": preds}


def run_backtest(circuits: List[str], models_factory, eval_from: str, eval_to: Optional[str] = None,
                 start_year: int = START_YEAR, reference: str = "elo") -> Dict[str, object]:
    """Walk-forward every circuit (in parallel), then score per circuit and pooled."""
    eval_from_ts, eval_to_ts = pd.Timestamp(eval_from), pd.Timestamp(eval_to) if eval_to else None
    jobs = [(c, models_factory(), eval_from_ts, eval_to_ts, start_year) for c in circuits]
    if len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=len(jobs), initializer=limit_worker_threads) as pool:
            futures = [pool.submit(circuit_predictions, job) for job in jobs]
            for f in as_completed(futures):
                logger.info(f"[tennis backtest] {f.result()['circuit']}: finished")
            results = [f.result() for f in futures]
    else:
        results = [circuit_predictions(job) for job in jobs]

    report: Dict[str, object] = {"eval_from": eval_from, "eval_to": eval_to, "start_year": start_year,
                                 "reference": reference, "circuits": {}}
    pooled_matches, pooled_preds = [], {}
    for res in results:
        c, matches, preds = res["circuit"], res["matches"], res["preds"]
        report["circuits"][c] = {"matches": int(len(matches)),
                                 "models": {n: score_predictions(matches, p) for n, p in preds.items()},
                                 "vs_reference": compare(preds, reference)}
        pooled_matches.append(matches.set_axis(c + "_" + matches.index.astype(str)))
        for n, p in preds.items():
            pooled_preds.setdefault(n, []).append(p.set_axis(c + "_" + p.index.astype(str)))
    all_matches = pd.concat(pooled_matches)
    all_preds = {n: pd.concat(parts) for n, parts in pooled_preds.items()}
    report["pooled"] = {"matches": int(len(all_matches)),
                        "models": {n: score_predictions(all_matches, p) for n, p in all_preds.items()},
                        "vs_reference": compare(all_preds, reference)}
    return report
