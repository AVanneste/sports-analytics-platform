"""Tune the tennis Elo ratings by walk-forward backtest, then confirm on unseen seasons.

    python scripts/tune_tennis_elo.py [--start-year 2014] [--json tuning.json]
    python scripts/tune_tennis_elo.py --start k0=300,margin=1 --stages scale=0.9,1,1.1

The ratings are sequential (each match is predicted from earlier matches only), so a setting needs
a single pass over the match stream. Settings are searched on 2021 to June 2024 (both tours pooled,
log loss), then the winner and the defaults are compared on July 2024 onwards with paired
per-match differences. Only settings that win on that unseen window should be adopted.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from sports_common.evaluation import paired_difference
from tennis_core.models.backtest import EloRatingModel, match_losses, prepare_circuit

TUNE = ("2021-01-01", "2024-07-01")
CONFIRM = ("2024-07-01", None)
DEFAULT = {"k0": 250.0, "offset": 5.0, "shape": 0.4, "surface_weight": 0.5, "level_k": 1.0, "margin": 0.0,
           "scale": 1.0}
STAGES = [
    ("k0", [150, 200, 250, 300, 350, 450]),
    ("shape", [0.2, 0.3, 0.4, 0.5, 0.6]),
    ("offset", [1, 3, 5, 10, 20]),
    ("surface_weight", [0.0, 0.25, 0.5, 0.75, 1.0]),
    ("margin", [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]),
    ("level_k", [0.0, 1.0]),
    ("k0", [150, 200, 250, 300, 350, 450, 600]),
    ("scale", [0.8, 0.9, 1.0, 1.1, 1.2]),
]


def window_losses(data, params, window) -> pd.Series:
    model = EloRatingModel(**{**params, "level_k": bool(params["level_k"])})
    parts = []
    for circuit, matches in data.items():
        dates = matches["tourney_date"]
        mask = (dates >= window[0]) & ((dates < window[1]) if window[1] else True)
        p = model.run(matches)[mask]
        parts.append(match_losses(p).set_axis(circuit + "_" + p.index.astype(str)))
    return pd.concat(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-year", type=int, default=2014)
    parser.add_argument("--circuits", nargs="+", default=["atp", "wta"])
    parser.add_argument("--start", help="starting point, e.g. k0=300,margin=1")
    parser.add_argument("--stages", nargs="+", help="coordinate-search stages, e.g. margin=0,1,2 scale=0.9,1")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = {c: prepare_circuit(c, args.start_year, features=False)["matches"] for c in args.circuits}
    best = dict(DEFAULT)
    if args.start:
        best.update({k: float(v) for k, v in (kv.split("=") for kv in args.start.split(","))})
    stages = STAGES if not args.stages else [
        (name, [float(v) for v in values.split(",")]) for name, values in (s.split("=") for s in args.stages)]

    history, best_score = [], None
    for param, grid in stages:
        for value in grid:
            params = dict(best, **{param: float(value)})
            score = round(float(window_losses(data, params, TUNE).mean()), 5)
            history.append({"params": params, "tuning_log_loss": score})
            print(f"tune {param}={value:<6g} -> log loss {score:.5f}", flush=True)
            if best_score is None or score < best_score:
                best, best_score = params, score
        print(f"  best after {param}: {best}", flush=True)

    tuned, default = window_losses(data, best, CONFIRM), window_losses(data, DEFAULT, CONFIRM)
    joined = pd.concat([tuned, default], axis=1, join="inner").dropna()
    diff = paired_difference(joined.iloc[:, 0], joined.iloc[:, 1])
    print(f"\nConfirmation window {CONFIRM[0]} onwards: tuned {best} vs default {DEFAULT}")
    print(f"  log loss tuned {joined.iloc[:, 0].mean():.5f}  default {joined.iloc[:, 1].mean():.5f}  "
          f"diff {diff['mean']:+.5f} ± {diff['se']:.5f}  (n={diff['n']})")
    for circuit in args.circuits:
        part = joined[joined.index.str.startswith(circuit + "_")]
        d = paired_difference(part.iloc[:, 0], part.iloc[:, 1])
        print(f"  {circuit}: tuned {part.iloc[:, 0].mean():.5f}  diff {d['mean']:+.5f} ± {d['se']:.5f}  (n={d['n']})")
    if args.json:
        args.json.write_text(json.dumps({"best": best, "default": DEFAULT, "search": history,
                                         "confirmation": diff}, indent=2))


if __name__ == "__main__":
    main()
