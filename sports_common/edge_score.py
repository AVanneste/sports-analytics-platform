"""Expected edge of an alert: what its closing value will be, learned from past alerts.

An alert's claimed EV is measured against Pinnacle's price when it fires; its edge is what is left
at Pinnacle's closing price. Over Oct-Nov 2026 closing value was about -1.4% + 0.75 x claimed EV, and
it varied far more with the segment (tennis games +6%, soccer sides -3%), the time to kick-off and the
size of a Pinnacle drop than with the claimed EV. ``fit`` learns that from closed alerts (ridge
regression, a few dozen parameters); ``predict`` scores a new alert; ``validate`` holds out the latest
days so a model that does not rank alerts better than chance is never published.
"""
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

ALPHA = 3.0          # ridge penalty
MIN_SEGMENT = 100    # closed alerts a segment needs before it is "proven" (and may be sent)
HOLDOUT_DAYS = 10
MIN_SPREAD = 0.01    # top half must beat the bottom half by this much closing value on the holdout


# Napoleon's hockey totals/handicaps include overtime but were mapped to regulation time until 10 Nov 2026
# (fixed in 8640155): those rows look like +5% closing value and must never teach the score
HOCKEY_BUG = {"sport": "Hockey", "period": 6, "markets": {"total", "team_total", "spread"}, "before": "2026-11-11"}


def segment(row) -> str:
    units = row.get("units")
    return f"{row['sport']}:{row['market']}:{units if isinstance(units, str) else ''}:{int(row.get('period') or 0)}"


def design(df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Feature matrix of alert rows (sport, market, units, period, ev, hrs to kick-off, drop, limit)."""
    seg = df.apply(segment, axis=1)
    main = (df["units"].fillna("").astype(str) == "") & (df["period"].fillna(0).astype(int) == 0)
    side = (df["sport"] == "Soccer") & main & df["market"].isin(["moneyline", "spread"])
    drop = df["dropped_from"].notna().astype(float)
    hrs = df["hrs"]
    X = pd.get_dummies(seg, prefix="seg").astype(float)
    for sport in ("Soccer", "Tennis", "Basketball", "Hockey", "Volleyball", "Handball",
                  "Darts", "Snooker", "E Sports", "Football", "Rugby Union", "Cricket"):
        X[f"ev:{sport}"] = df["ev"] * (df["sport"] == sport)
    X["last30"] = (hrs <= 0.5).astype(float)
    X["lineup"] = ((hrs > 0.5) & (hrs <= 2)).astype(float)
    X["early"] = (hrs > 12).astype(float)
    X["last30:soccer_side"] = X["last30"] * side
    X["lineup:soccer_side"] = X["lineup"] * side
    X["drop"], X["drop:ev"] = drop, drop * df["ev"]
    X["loglimit"] = np.log(df["limit"].fillna(250).clip(lower=50)) - 6
    return X if columns is None else X.reindex(columns=columns, fill_value=0.0)


def fit(df: pd.DataFrame, alpha: float = ALPHA) -> Dict:
    """Model dict from closed alerts (columns: the alert's fields, ``hrs``, ``ev_at_close``)."""
    X = design(df)
    y = df["ev_at_close"].to_numpy(float)
    A = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    penalty = alpha * np.eye(A.shape[1])
    penalty[0, 0] = 0.0  # the intercept is not shrunk
    w = np.linalg.solve(A.T @ A + penalty, A.T @ y)
    counts = df.apply(segment, axis=1).value_counts()
    return {"columns": list(X.columns), "intercept": float(w[0]), "coef": [float(v) for v in w[1:]],
            "segments": {k: int(v) for k, v in counts.items()}, "trained_on": int(len(df))}


def predict(model: Dict, df: pd.DataFrame) -> pd.Series:
    """Expected closing value of each alert row; NaN for a segment with fewer than MIN_SEGMENT closed
    alerts in the training data (unproven: collected, not sent)."""
    X = design(df, model["columns"])
    out = pd.Series(model["intercept"] + X.to_numpy(float) @ np.array(model["coef"]), index=df.index)
    proven = df.apply(segment, axis=1).map(lambda s: model["segments"].get(s, 0) >= MIN_SEGMENT)
    return out.where(proven)


def validate(df: pd.DataFrame, holdout_days: int = HOLDOUT_DAYS) -> Dict:
    """Train on all but the latest ``holdout_days`` days, score those days: does the top half of
    alerts by score close better than the bottom half, and by how much?"""
    day = pd.to_datetime(df["captured_at"].str[:10])
    cut = day.max() - pd.Timedelta(days=holdout_days)
    train, test = df[day <= cut], df[day > cut]
    if len(train) < 500 or len(test) < 100:
        return {"ok": False, "reason": f"too little data ({len(train)} train, {len(test)} test)"}
    model = fit(train)
    score = predict(model, test)
    scored = test[score.notna()].assign(score=score.dropna())
    if len(scored) < 100:
        return {"ok": False, "reason": "too few scored holdout alerts"}
    half = len(scored) // 2
    top, bottom = scored.nlargest(half, "score"), scored.nsmallest(half, "score")
    spread = float(top["ev_at_close"].mean() - bottom["ev_at_close"].mean())
    return {"ok": spread >= MIN_SPREAD, "spread": spread, "top": float(top["ev_at_close"].mean()),
            "bottom": float(bottom["ev_at_close"].mean()), "n_train": int(len(train)), "n_test": int(len(scored)),
            "above_3": float(scored[scored["score"] >= 0.03]["ev_at_close"].mean()) if (scored["score"] >= 0.03).any() else None}


def closed_frame(rows: Iterable[Dict]) -> pd.DataFrame:
    """Archive rows (dicts of CSV strings) as the numeric frame ``fit`` and ``validate`` read."""
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    for c in ("ev", "ev_at_close", "limit", "price"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["period"] = pd.to_numeric(df["period"], errors="coerce").fillna(0).astype(int)
    df["hrs"] = (pd.to_datetime(df["start"], utc=True) - pd.to_datetime(df["captured_at"], utc=True)).dt.total_seconds() / 3600
    df["units"] = df["units"].where(df["units"].notna(), None)
    df = df[df["ev_at_close"].notna() & (df["hrs"] > 0)]
    bug = ((df["sport"] == HOCKEY_BUG["sport"]) & (df["period"] == HOCKEY_BUG["period"]) & df["market"].isin(HOCKEY_BUG["markets"])
           & (df["captured_at"].str[:10] < HOCKEY_BUG["before"]))
    df = df[~bug]
    if "sent" in df:  # every collected alert teaches the model, whether or not it was sent
        df = df.drop(columns=["sent"])
    return df.reset_index(drop=True)
