"""Walk-forward evaluation of football prediction models, accuracy first.

Every model is refitted on the matches played before a refit date and predicts the matches up to
the next refit date, so each prediction only uses information available before kickoff. Markets are
scored with proper scoring rules (log loss, Brier, ranked probability score for 1X2) plus accuracy
and calibration error. Bookmaker prices are scored the same way as an external yardstick only;
no model here uses them as an input.
"""
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from functools import partial
from typing import Dict, List, Optional, Protocol, Sequence

import numpy as np
import pandas as pd

from sports_common.betting import devig
from sports_common.evaluation import brier, ece, log_loss, paired_difference, rps

logger = logging.getLogger(__name__)

GOAL_LINES = (1.5, 2.5, 3.5)
PROP_LINES = {"corners": (8.5, 9.5, 10.5), "cards": (2.5, 3.5, 4.5)}
PROP_COLUMNS = {"corners": ("HC", "AC"), "cards": ("HY", "AY", "HR", "AR")}
PRED_1X2 = ["p_home", "p_draw", "p_away"]
BINARY_MARKETS = {
    **{f"p_over{int(line * 10)}": f"over{int(line * 10)}" for line in GOAL_LINES},
    "p_btts": "btts",
    **{f"p_{stat}_over{int(line * 10)}": f"{stat}_over{int(line * 10)}"
       for stat, lines in PROP_LINES.items() for line in lines},
}
EPS = 1e-12


def season_label(dates: pd.Series) -> pd.Series:
    """'2223'-style season labels; a season starts on 1 July."""
    start = dates.dt.year - (dates.dt.month < 7).astype(int)
    return (start % 100).map("{:02d}".format) + ((start + 1) % 100).map("{:02d}".format)


def markets_from_score_matrix(matrix: np.ndarray) -> Dict[str, float]:
    """1X2, BTTS and over/under probabilities implied by a (home goals x away goals) matrix."""
    m = np.asarray(matrix, dtype=float)
    m = m / m.sum()
    h = np.arange(m.shape[0])[:, None]
    a = np.arange(m.shape[1])[None, :]
    out = {
        "p_home": float(m[h > a].sum()),
        "p_draw": float(np.trace(m)),
        "p_away": float(m[h < a].sum()),
        "p_btts": float(m[1:, 1:].sum()),
    }
    for line in GOAL_LINES:
        out[f"p_over{int(line * 10)}"] = float(m[(h + a) > line].sum())
    return out


# Dixon-Coles settings of the currently deployed models (before walk-forward tuning), kept so the
# backtest can compare any candidate against what is live.
DEPLOYED_DC = {"xi": 0.0018, "ridge": 1.0, "sot_weight": 0.0, "xg_weight": 0.0}
FEATURE_VARIANTS = {"default": None, "deployed": DEPLOYED_DC}
# Dixon-Coles setting names (as used by the backtest and tuning scripts) -> engine attributes
DC_SETTINGS = {"xi": "XI", "ridge": "RIDGE", "sot_weight": "SOT_WEIGHT", "xg_weight": "XG_WEIGHT",
               "xg_sot_weight": "XG_SOT_WEIGHT", "xg_ridge": "XG_RIDGE", "newcomer_offset": "NEWCOMER_OFFSET",
               "newcomer_matches": "NEWCOMER_MATCHES"}


@contextmanager
def dc_settings(params: Optional[Dict[str, float]]):
    """Temporarily set the Dixon-Coles engine defaults (used while building a feature matrix)."""
    from football_core.features.dixon_coles import DixonColesEngine
    if not params:
        yield
        return
    old = {attr: getattr(DixonColesEngine, attr) for attr in DC_SETTINGS.values()}
    for k, v in params.items():
        setattr(DixonColesEngine, DC_SETTINGS[k], v)
    try:
        yield
    finally:
        for attr, v in old.items():
            setattr(DixonColesEngine, attr, v)


class Model(Protocol):
    name: str
    refit: str  # pandas offset alias for the refit cadence, e.g. "MS" (monthly) or "QS" (quarterly)
    needs_features: bool
    # Which feature matrix the model reads (FEATURE_VARIANTS key); absent means "default"

    def fit(self, history: pd.DataFrame, X_hist: Optional[pd.DataFrame], y_hist: Optional[pd.DataFrame]) -> None:
        ...

    def predict(self, upcoming: pd.DataFrame, X_up: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Columns among PRED_1X2 and BINARY_MARKETS, plus optional object column 'score_matrix'."""
        ...


def walk_forward(matches: pd.DataFrame, models: Sequence[Model], eval_from: pd.Timestamp,
                 eval_to: Optional[pd.Timestamp] = None, X: Optional[pd.DataFrame] = None,
                 y: Optional[pd.DataFrame] = None, min_history: int = 300) -> Dict[str, pd.DataFrame]:
    """Expanding-window predictions for every match in [eval_from, eval_to).

    ``matches`` must be sorted by Date with a RangeIndex aligned with the rows of ``X``/``y``.
    """
    dates = matches["Date"]
    in_eval = dates >= eval_from
    if eval_to is not None:
        in_eval &= dates < eval_to
    if not in_eval.any():
        return {}
    last = dates[in_eval].max()
    out: Dict[str, pd.DataFrame] = {}
    for model in models:
        if model.needs_features and X is None:
            raise ValueError(f"{model.name} needs the feature matrix")
        cuts = [eval_from] + [d for d in pd.date_range(eval_from, last, freq=model.refit) if d > eval_from]
        cuts.append(last + pd.Timedelta(days=1))
        parts = []
        for start, end in zip(cuts[:-1], cuts[1:]):
            window = in_eval & (dates >= start) & (dates < end)
            history = dates < start
            if not window.any() or history.sum() < min_history:
                continue
            model.fit(matches[history], X[history] if X is not None else None,
                      y[history] if y is not None else None)
            parts.append(model.predict(matches[window], X[window] if X is not None else None))
        if parts:
            out[model.name] = pd.concat(parts)
    return out


def market_predictions(matches: pd.DataFrame, when: str = "open") -> pd.DataFrame:
    """Vig-free bookmaker probabilities (yardstick only). ``when``: 'open' (Bet365/average) or 'close'."""
    if when == "open":
        cols_1x2 = [("odds_home", "odds_draw", "odds_away")]
        cols_ou = [("odds_over25", "odds_under25")]
    else:  # Pinnacle closing where football-data still has it, else the market-average close
        cols_1x2 = [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA")]
        cols_ou = [("PC>2.5", "PC<2.5"), ("AvgC>2.5", "AvgC<2.5")]

    def _first_available(row, candidates):
        for cols in candidates:
            if all(c in row.index for c in cols):
                probs = devig([row[c] for c in cols])
                if probs is not None:
                    return probs
        return None

    records = []
    for idx, row in matches.iterrows():
        rec = {"index": idx}
        p = _first_available(row, cols_1x2)
        if p is not None:
            rec.update(dict(zip(PRED_1X2, p)))
        p = _first_available(row, cols_ou)
        if p is not None:
            rec["p_over25"] = p[0]
        records.append(rec)
    return pd.DataFrame(records).set_index("index").reindex(matches.index)


def _outcomes(matches: pd.DataFrame) -> Dict[str, np.ndarray]:
    hg = matches["FTHG"].to_numpy(dtype=int)
    ag = matches["FTAG"].to_numpy(dtype=int)
    out = {"1x2": np.where(hg > ag, 0, np.where(hg == ag, 1, 2)), "btts": ((hg > 0) & (ag > 0)).astype(int),
           "hg": hg, "ag": ag}
    for line in GOAL_LINES:
        out[f"over{int(line * 10)}"] = ((hg + ag) > line).astype(int)
    for stat, cols in PROP_COLUMNS.items():
        total = _stat_total(matches, cols)
        for line in PROP_LINES[stat]:
            out[f"{stat}_over{int(line * 10)}"] = np.where(np.isfinite(total), (total > line).astype(float), np.nan)
    return out


def _stat_total(matches: pd.DataFrame, cols) -> np.ndarray:
    """Match total of a count statistic; NaN when any component is missing."""
    if not set(cols).issubset(matches.columns):
        return np.full(len(matches), np.nan)
    return np.sum([pd.to_numeric(matches[c], errors="coerce").to_numpy(dtype=float) for c in cols], axis=0)


def per_match_losses(matches: pd.DataFrame, preds: pd.DataFrame) -> Dict[str, pd.Series]:
    """Per-match log loss for each market a model predicts (indexed like ``preds``)."""
    m = matches.loc[preds.index]
    y = _outcomes(m)
    losses: Dict[str, pd.Series] = {}
    if set(PRED_1X2).issubset(preds.columns):
        P = preds[PRED_1X2].to_numpy(dtype=float)
        ok = np.all(np.isfinite(P), axis=1)
        P = P / P.sum(axis=1, keepdims=True)
        picked = P[np.arange(len(P)), y["1x2"]]
        losses["1x2"] = pd.Series(np.where(ok, -np.log(np.clip(picked, EPS, 1)), np.nan), index=preds.index)
    for col, market in BINARY_MARKETS.items():
        if col in preds.columns:
            p = np.clip(preds[col].to_numpy(dtype=float), EPS, 1 - EPS)
            yy = np.asarray(y[market], dtype=float)  # NaN where the statistic was not recorded
            losses[market] = pd.Series(-(yy * np.log(p) + (1 - yy) * np.log(1 - p)), index=preds.index)
    if "score_matrix" in preds.columns:
        vals = []
        for mat, h, a in zip(preds["score_matrix"], y["hg"], y["ag"]):
            if mat is None or (isinstance(mat, float) and np.isnan(mat)):
                vals.append(np.nan)
                continue
            mat = np.asarray(mat, dtype=float)
            vals.append(-np.log(max(mat[min(h, mat.shape[0] - 1), min(a, mat.shape[1] - 1)] / mat.sum(), EPS)))
        losses["score"] = pd.Series(vals, index=preds.index)
    return losses


def score_predictions(matches: pd.DataFrame, preds: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Accuracy metrics per market for one model's predictions."""
    m = matches.loc[preds.index]
    y = _outcomes(m)
    report: Dict[str, Dict[str, float]] = {}
    if set(PRED_1X2).issubset(preds.columns):
        P = preds[PRED_1X2].to_numpy(dtype=float)
        ok = np.all(np.isfinite(P), axis=1)
        if ok.any():
            P = P[ok] / P[ok].sum(axis=1, keepdims=True)
            yy = y["1x2"][ok]
            onehot = np.eye(3)[yy]
            report["1x2"] = {
                "n": int(ok.sum()),
                "log_loss": round(log_loss(P, yy), 4),
                "brier": round(brier(P, yy), 4),
                "rps": round(rps(P, yy), 4),
                "accuracy": round(float(np.mean(P.argmax(axis=1) == yy)), 4),
                "ece": round(ece(P.ravel(), onehot.ravel()), 4),
            }
    for col, market in BINARY_MARKETS.items():
        if col in preds.columns:
            p = preds[col].to_numpy(dtype=float)
            outcome = np.asarray(y[market], dtype=float)
            ok = np.isfinite(p) & np.isfinite(outcome)
            if ok.any():
                yy = outcome[ok].astype(int)
                report[market] = {
                    "n": int(ok.sum()),
                    "log_loss": round(log_loss(p[ok], yy), 4),
                    "brier": round(brier(p[ok], yy), 4),
                    "accuracy": round(float(np.mean((p[ok] >= 0.5) == yy)), 4),
                    "ece": round(ece(p[ok], yy), 4),
                }
    if "score_matrix" in preds.columns:
        s = per_match_losses(matches, preds[["score_matrix"]])["score"].dropna()
        if len(s):
            report["score"] = {"n": int(len(s)), "log_loss": round(float(s.mean()), 4)}
    return report


def compare(matches: pd.DataFrame, preds_by_model: Dict[str, pd.DataFrame], reference: str) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Per market, mean log-loss difference of each model vs ``reference`` on their common matches."""
    if reference not in preds_by_model:
        return {}
    ref = per_match_losses(matches, preds_by_model[reference])
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for name, preds in preds_by_model.items():
        if name == reference:
            continue
        mine = per_match_losses(matches, preds)
        out[name] = {}
        for market, series in mine.items():
            if market in ref:
                joined = pd.concat([series, ref[market]], axis=1, join="inner").dropna()
                if len(joined):
                    diff = paired_difference(joined.iloc[:, 0], joined.iloc[:, 1])
                    out[name][market] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in diff.items()}
    return out


# ------------------------------------------------------------------ baseline models
class BaseRateModel:
    """Outcome frequencies over the last three years of the league (the no-skill reference)."""

    name, refit, needs_features = "base_rate", "MS", False

    def fit(self, history, X_hist=None, y_hist=None):
        recent = history[history["Date"] >= history["Date"].max() - pd.Timedelta(days=3 * 365)]
        hg = recent["FTHG"].clip(upper=9).to_numpy(dtype=int)
        ag = recent["FTAG"].clip(upper=9).to_numpy(dtype=int)
        counts = np.ones((10, 10)) * 0.5  # light smoothing so unseen scores keep some probability
        np.add.at(counts, (hg, ag), 1.0)
        self.matrix = counts / counts.sum()
        self.probs = {
            "p_home": float(np.mean(hg > ag)), "p_draw": float(np.mean(hg == ag)), "p_away": float(np.mean(hg < ag)),
            "p_btts": float(np.mean((hg > 0) & (ag > 0))),
            **{f"p_over{int(line * 10)}": float(np.mean((hg + ag) > line)) for line in GOAL_LINES},
        }
        for stat, cols in PROP_COLUMNS.items():
            total = _stat_total(recent, cols)
            total = total[np.isfinite(total)]
            for line in PROP_LINES[stat]:
                self.probs[f"p_{stat}_over{int(line * 10)}"] = float(np.mean(total > line)) if total.size else np.nan

    def predict(self, upcoming, X_up=None):
        frame = pd.DataFrame([self.probs] * len(upcoming), index=upcoming.index)
        frame["score_matrix"] = [self.matrix] * len(upcoming)
        return frame


class EloLogitModel:
    """Multinomial logistic regression of the 1X2 outcome on the pre-match Elo difference."""

    name, refit, needs_features = "elo", "MS", True

    def fit(self, history, X_hist, y_hist=None):
        from sklearn.linear_model import LogisticRegression
        y = _outcomes(history)["1x2"]
        self.clf = LogisticRegression(max_iter=1000).fit(X_hist[["elo_diff"]].to_numpy() / 400.0, y)

    def predict(self, upcoming, X_up):
        P = self.clf.predict_proba(X_up[["elo_diff"]].to_numpy() / 400.0)
        return pd.DataFrame(P, columns=PRED_1X2, index=upcoming.index)


class DixonColesModel:
    """Time-decayed, ridge-regularised Dixon-Coles refitted at every cut; prices every goal market."""

    needs_features = False

    def __init__(self, name: str = "dixon_coles", history_days: int = 1500, refit: str = "MS", **settings):
        # ``settings`` (DC_SETTINGS keys) override the engine's defaults, i.e. the production settings
        unknown = set(settings) - set(DC_SETTINGS)
        if unknown:
            raise ValueError(f"unknown Dixon-Coles settings: {sorted(unknown)}")
        self.name, self.history_days, self.refit, self.settings = name, history_days, refit, settings

    def _engine(self):
        from football_core.features.dixon_coles import DixonColesEngine
        engine = DixonColesEngine()
        for key, value in self.settings.items():
            setattr(engine, DC_SETTINGS[key], value)
        return engine

    def fit(self, history, X_hist=None, y_hist=None):
        recent = history[history["Date"] >= history["Date"].max() - pd.Timedelta(days=self.history_days)]
        self.engine = self._engine()
        self.engine.fit_from_matches(recent, time_decay=True)

    def predict(self, upcoming, X_up=None):
        rows, mats = [], []
        for home, away in zip(upcoming["HomeTeam"], upcoming["AwayTeam"]):
            mat = self.engine.generate_score_matrix(home, away)
            rows.append(markets_from_score_matrix(mat))
            mats.append(mat)
        frame = pd.DataFrame(rows, index=upcoming.index)
        frame["score_matrix"] = mats
        return frame


class ProductionStackModel:
    """The production pipeline: train_league_models (LightGBM + Dixon-Coles blend), refitted quarterly."""

    refit, needs_features = "QS", True

    def __init__(self, name: str = "production", feature_variant: str = "default"):
        self.name, self.feature_variant = name, feature_variant

    def fit(self, history, X_hist, y_hist):
        from football_core.models.train import train_league_models
        previous = logging.getLogger("football_core.models.train").level
        logging.getLogger("football_core.models.train").setLevel(logging.WARNING)
        try:
            self.models, self.metrics = train_league_models(X_hist, y_hist, league_key="backtest")
        finally:
            logging.getLogger("football_core.models.train").setLevel(previous)

    def predict(self, upcoming, X_up):
        from sports_common.evaluation import blend
        w = self.metrics["blend_weights"]
        dc = X_up[["dc_prob_home", "dc_prob_draw", "dc_prob_away"]].to_numpy(dtype=float)
        dc = dc / dc.sum(axis=1, keepdims=True)
        p1x2 = blend(self.models["model_1x2"].predict_proba(X_up), dc, w["ml_1x2"])
        frame = pd.DataFrame(p1x2 / p1x2.sum(axis=1, keepdims=True), columns=PRED_1X2, index=upcoming.index)
        frame["p_over25"] = blend(self.models["model_over25"].predict_proba(X_up)[:, 1],
                                  X_up["dc_prob_over25"].to_numpy(dtype=float), w["ml_over25"])
        frame["p_btts"] = blend(self.models["model_btts"].predict_proba(X_up)[:, 1],
                                X_up["dc_prob_btts"].to_numpy(dtype=float), w["ml_btts"])
        return frame


def outcome_stack_features(X: pd.DataFrame, extra: Sequence[str] = ()) -> np.ndarray:
    """Dixon-Coles log-odds (home/draw, away/draw) and the Elo difference, plus optional extra columns."""
    dc = np.clip(X[["dc_prob_home", "dc_prob_draw", "dc_prob_away"]].to_numpy(dtype=float), 1e-6, 1.0)
    cols = [np.log(dc[:, 0] / dc[:, 1]), np.log(dc[:, 2] / dc[:, 1]), X["elo_diff"].to_numpy(dtype=float) / 400.0]
    cols += [X[c].to_numpy(dtype=float) for c in extra]
    return np.column_stack(cols)


class StackedOutcomeModel:
    """1X2 from a multinomial logistic regression on Dixon-Coles log-odds and Elo (out-of-sample inputs).

    The Dixon-Coles probabilities in the feature matrix come from monthly snapshots fitted only on
    earlier matches, so the stacker is trained on genuinely out-of-sample inputs.
    """

    needs_features = True

    def __init__(self, name: str = "stacked", extra: Sequence[str] = (), C: float = 1.0,
                 history_days: int = 1500, refit: str = "MS", feature_variant: str = "default"):
        self.name, self.extra, self.C, self.history_days, self.refit = name, tuple(extra), C, history_days, refit
        self.feature_variant = feature_variant

    def fit(self, history, X_hist, y_hist=None):
        from sklearn.linear_model import LogisticRegression
        recent = (history["Date"] >= history["Date"].max() - pd.Timedelta(days=self.history_days)).to_numpy()
        y = _outcomes(history[recent])["1x2"]
        self.clf = LogisticRegression(C=self.C, max_iter=2000).fit(
            outcome_stack_features(X_hist[recent], self.extra), y)

    def predict(self, upcoming, X_up):
        P = self.clf.predict_proba(outcome_stack_features(X_up, self.extra))
        return pd.DataFrame(P, columns=PRED_1X2, index=upcoming.index)


class HeuristicPropsModel:
    """The deployed corners/cards projections (features/props.py), read from the feature matrix."""

    name, refit, needs_features = "props_heuristic", "MS", True
    COLUMNS = {"p_corners_over95": "prob_corners_o95_poisson", "p_corners_over105": "prob_corners_o105_poisson",
               "p_cards_over35": "prob_cards_o35_poisson", "p_cards_over45": "prob_cards_o45_poisson"}

    def fit(self, history, X_hist, y_hist=None):
        pass

    def predict(self, upcoming, X_up):
        return pd.DataFrame({ours: X_up[theirs].to_numpy(dtype=float) for ours, theirs in self.COLUMNS.items()},
                            index=upcoming.index)


class CountPropsModel:
    """Fitted team-rate count models (features/count_model.py) for corners and cards."""

    needs_features = False

    def __init__(self, name: str = "props_count", stats: Sequence[str] = ("corners", "cards"),
                 refit: str = "MS", **settings):
        # ``settings`` (xi, ridge, referee_prior, history_days) override the tuned per-statistic defaults
        self.name, self.stats, self.refit, self.settings = name, tuple(stats), refit, settings

    def fit(self, history, X_hist=None, y_hist=None):
        from football_core.features.count_model import COUNT_MODELS
        self.models = {stat: COUNT_MODELS[stat](**self.settings).fit(history) for stat in self.stats}

    def predict(self, upcoming, X_up=None):
        rows = []
        refs = upcoming["Referee"] if "Referee" in upcoming.columns else pd.Series([None] * len(upcoming), index=upcoming.index)
        for home, away, ref in zip(upcoming["HomeTeam"], upcoming["AwayTeam"], refs):
            row = {}
            for stat, model in self.models.items():
                for line in PROP_LINES[stat]:
                    row[f"p_{stat}_over{int(line * 10)}"] = (
                        model.prob_over(home, away, line, referee=ref if stat == "cards" else None)
                        if model.fitted else np.nan)
            rows.append(row)
        return pd.DataFrame(rows, index=upcoming.index)


BASELINES = {
    "base_rate": BaseRateModel,
    "elo": EloLogitModel,
    "dixon_coles": DixonColesModel,
    "dixon_coles_deployed": partial(DixonColesModel, "dixon_coles_deployed", **DEPLOYED_DC),
    "production": ProductionStackModel,
    "production_deployed": partial(ProductionStackModel, "production_deployed", "deployed"),
    "stacked": StackedOutcomeModel,
    "props_heuristic": HeuristicPropsModel,
    "props_count": CountPropsModel,
}


def prepare_league(league_key: str, variants: Sequence[str] = ()) -> Dict[str, object]:
    """Cleaned matches sorted by date (RangeIndex) plus an aligned feature matrix per requested variant."""
    from football_core.data.preprocessor import clean_match_data, load_raw_league_data
    matches = clean_match_data(load_raw_league_data(league_key), league_key=league_key)
    matches = matches.sort_values("Date", kind="mergesort").reset_index(drop=True)
    features = {}
    if variants:
        from football_core.features.builder import FootballFeaturePipeline
        for variant in variants:
            with dc_settings(FEATURE_VARIANTS[variant]):
                features[variant] = FootballFeaturePipeline(league_key).process_historical_matches(matches)
    return {"matches": matches, "features": features}


def limit_worker_threads() -> None:
    """One BLAS/OpenMP thread per worker process. Idle BLAS and OpenMP threads spin, so a pool of
    workers that each keep full-size thread pools runs many times slower than single-threaded."""
    from threadpoolctl import threadpool_limits
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"  # read by libraries loaded later in the worker (LightGBM's OpenMP)
    threadpool_limits(1)  # libraries already loaded (numpy/scipy OpenBLAS)


def _init_worker(level: int) -> None:
    limit_worker_threads()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    logger.setLevel(level)


def _league_predictions(args) -> Dict[str, object]:
    league_key, models, eval_from, eval_to = args
    started = time.time()
    variants = sorted({getattr(m, "feature_variant", "default") for m in models if m.needs_features})
    data = prepare_league(league_key, variants)
    matches = data["matches"]
    logger.info(f"[backtest] {league_key}: data and features ready ({time.time() - started:.0f}s)")
    preds: Dict[str, pd.DataFrame] = {}
    for model in models:
        variant = getattr(model, "feature_variant", "default") if model.needs_features else None
        X, y = data["features"][variant] if variant else (None, None)
        t0 = time.time()
        preds.update(walk_forward(matches, [model], eval_from, eval_to, X, y))
        logger.info(f"[backtest] {league_key}: {model.name} done ({time.time() - t0:.0f}s)")
    evaluated = matches[(matches["Date"] >= eval_from) & ((matches["Date"] < eval_to) if eval_to is not None else True)]
    preds["market_open"] = market_predictions(evaluated, "open")
    preds["market_close"] = market_predictions(evaluated, "close")
    return {"league": league_key, "matches": matches.loc[evaluated.index], "preds": preds}


def run_backtest(leagues: List[str], models_factory, eval_from: str, eval_to: Optional[str] = None,
                 reference: str = "dixon_coles", workers: Optional[int] = None) -> Dict[str, object]:
    """Walk-forward every league (in parallel), then score per league and pooled across leagues.

    ``models_factory`` is a zero-argument callable returning fresh model instances.
    """
    eval_from_ts = pd.Timestamp(eval_from)
    eval_to_ts = pd.Timestamp(eval_to) if eval_to else None
    jobs = [(lk, models_factory(), eval_from_ts, eval_to_ts) for lk in leagues]
    workers = workers or len(jobs)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(logger.getEffectiveLevel(),)) as pool:
            futures = [pool.submit(_league_predictions, job) for job in jobs]
            for future in as_completed(futures):
                logger.info(f"[backtest] {future.result()['league']}: finished")
            results = [f.result() for f in futures]
    else:
        results = [_league_predictions(job) for job in jobs]

    per_league: Dict[str, object] = {}
    pooled_matches, pooled_preds = [], {}
    for res in results:
        lk, matches, preds = res["league"], res["matches"], res["preds"]
        per_league[lk] = {
            "matches": int(len(matches)),
            "models": {name: score_predictions(matches, p) for name, p in preds.items()},
            "vs_reference": compare(matches, preds, reference),
        }
        pooled_matches.append(matches.set_axis(lk + "_" + matches.index.astype(str)))
        for name, p in preds.items():
            pooled_preds.setdefault(name, []).append(p.set_axis(lk + "_" + p.index.astype(str)))
        logger.info(f"[backtest] {lk}: {len(matches)} matches evaluated")
    all_matches = pd.concat(pooled_matches)
    all_preds = {name: pd.concat(parts) for name, parts in pooled_preds.items()}
    return {
        "eval_from": eval_from, "eval_to": eval_to, "reference": reference,
        "leagues": per_league,
        "pooled": {
            "matches": int(len(all_matches)),
            "models": {name: score_predictions(all_matches, p) for name, p in all_preds.items()},
            "vs_reference": compare(all_matches, all_preds, reference),
        },
    }
