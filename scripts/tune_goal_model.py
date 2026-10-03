"""Tune the Dixon-Coles goal model by walk-forward backtest, then confirm on unseen seasons.

    python scripts/tune_goal_model.py [--leagues EPL LaLiga ...] [--json tuning.json]
    python scripts/tune_goal_model.py --start xi=0.0025,ridge=8,sot_weight=0.35 --stages ridge=8,16,32

Settings are searched on the tuning window (2022/23-2023/24, quarterly refits) by pooled
exact-score log loss, which scores the whole joint goal distribution. The winner and the current
defaults are then compared on the confirmation window (2024/25 onwards, monthly refits) with paired
per-match differences. Only settings that win on the confirmation window should be adopted.
"""
import argparse
import itertools
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from football_core.config import LEAGUES
from football_core.features.dixon_coles import DixonColesEngine
from football_core.models.backtest import DixonColesModel, per_match_losses, prepare_league, walk_forward
from sports_common.evaluation import paired_difference

DOMESTIC = [k for k, v in LEAGUES.items() if not v.get("is_cup") and not v.get("is_international")]
TUNE = ("2022-07-01", "2024-07-01")
CONFIRM = ("2024-07-01", None)
MARKETS = ("score", "1x2", "over25", "btts")


def _league_losses(args):
    league, params, window, refit = args
    matches = prepare_league(league)["matches"]
    model = DixonColesModel(name="dc", refit=refit, **params)
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1]) if window[1] else None
    preds = walk_forward(matches, [model], start, end).get("dc")
    if preds is None:
        return {}
    losses = per_match_losses(matches, preds)
    return {m: losses[m].set_axis(league + "_" + losses[m].index.astype(str)) for m in MARKETS if m in losses}


def evaluate(leagues, params, window, refit, pool):
    parts = list(pool.map(_league_losses, [(lk, params, window, refit) for lk in leagues]))
    return {m: pd.concat([p[m] for p in parts if m in p]) for m in MARKETS}


def summary(losses):
    return {m: round(float(s.mean()), 5) for m, s in losses.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leagues", nargs="+", default=DOMESTIC)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--start", help="starting point, e.g. xi=0.0025,ridge=8,sot_weight=0.35")
    parser.add_argument("--stages", nargs="+", help="coordinate-search stages, e.g. ridge=8,16,32 sot_weight=0,0.35")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    default = {"xi": DixonColesEngine.XI, "ridge": DixonColesEngine.RIDGE, "sot_weight": DixonColesEngine.SOT_WEIGHT}
    start = dict(default)
    if args.start:
        start.update({k: float(v) for k, v in (kv.split("=") for kv in args.start.split(","))})
    history, best, best_score = [], dict(start), None
    stages = [
        ("xi", [0.0008, 0.0012, 0.0018, 0.0025, 0.0035, 0.005]),
        ("ridge", [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]),
        ("sot_weight", [0.0, 0.2, 0.35, 0.5, 0.65, 0.8]),
        ("xi", [0.0008, 0.0012, 0.0018, 0.0025, 0.0035, 0.005]),
    ]
    if args.stages:
        stages = [(name, [float(v) for v in values.split(",")])
                  for name, values in (stage.split("=") for stage in args.stages)]
    with ProcessPoolExecutor() as pool:
        for param, grid in stages:
            for value in grid:
                params = dict(best, **{param: value})
                score = summary(evaluate(args.leagues, params, TUNE, "QS", pool))
                history.append({"params": params, "tuning": score})
                print(f"tune {param}={value:<7} -> score LL {score['score']:.5f}  1X2 {score['1x2']:.5f}  "
                      f"O2.5 {score['over25']:.5f}  BTTS {score['btts']:.5f}", flush=True)
                if best_score is None or score["score"] < best_score:
                    best, best_score = params, score["score"]
            print(f"  best after {param}: {best}", flush=True)

        tuned_losses = evaluate(args.leagues, best, CONFIRM, "MS", pool)
        default_losses = evaluate(args.leagues, default, CONFIRM, "MS", pool)

    confirmation = {}
    print(f"\nConfirmation window {CONFIRM[0]} onwards (monthly refits): tuned {best} vs default {default}")
    for m in MARKETS:
        joined = pd.concat([tuned_losses[m], default_losses[m]], axis=1, join="inner").dropna()
        diff = paired_difference(joined.iloc[:, 0], joined.iloc[:, 1])
        confirmation[m] = {"tuned": round(float(joined.iloc[:, 0].mean()), 5),
                           "default": round(float(joined.iloc[:, 1].mean()), 5), **diff}
        print(f"  {m:<7} tuned {confirmation[m]['tuned']:.5f}  default {confirmation[m]['default']:.5f}  "
              f"diff {diff['mean']:+.5f} ± {diff['se']:.5f}  (n={diff['n']})")
    if args.json:
        args.json.write_text(json.dumps({"best": best, "default": default, "search": history,
                                         "confirmation": confirmation}, indent=2))


if __name__ == "__main__":
    main()
