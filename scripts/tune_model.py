"""Tune a model's settings by walk-forward backtest, then confirm on unseen seasons.

    python scripts/tune_model.py --target goals [--leagues EPL LaLiga ...] [--json tuning.json]
    python scripts/tune_model.py --target goals --start xi=0.0025,ridge=8,sot_weight=0.35 --stages ridge=8,16,32
    python scripts/tune_model.py --target cards --stages referee_prior=5,15,40

Targets:
- goals: Dixon-Coles settings (backtest.DC_SETTINGS: decay, ridge and shots weight, plus the xG weight,
  shots weight and ridge used where Understat xG exists); the objective is exact-score log loss,
  which scores the whole joint goal distribution. Tune the xG settings on the xG leagues only.
- corners and cards: team count models' xi, ridge, and referee_prior for cards; the objective is
  mean log loss over the three over/under lines.

Settings are searched on the tuning window (2022/23-2023/24, quarterly refits) by pooled
objective. The winner and the current defaults are then compared on the confirmation window
(2024/25 onwards, monthly refits) with paired per-match differences. Only settings that win on the
confirmation window should be adopted.
"""
import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from football_core.config import LEAGUES
from football_core.features.count_model import CARDS_SETTINGS, CORNERS_SETTINGS
from football_core.features.dixon_coles import DixonColesEngine
from football_core.models.backtest import (
    DC_SETTINGS, PROP_LINES, CountPropsModel, DixonColesModel, limit_worker_threads, per_match_losses, prepare_league,
    walk_forward,
)
from sports_common.evaluation import paired_difference

DOMESTIC = [k for k, v in LEAGUES.items() if not v.get("is_cup") and not v.get("is_international")]
TUNE = ("2022-07-01", "2024-07-01")
CONFIRM = ("2024-07-01", None)
XI_GRID = [0.0008, 0.0012, 0.0018, 0.0025, 0.0035, 0.005]
RIDGE_GRID = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]


def _prop_markets(stat):
    return (stat,) + tuple(f"{stat}_over{int(line * 10)}" for line in PROP_LINES[stat])


TARGETS = {
    "goals": {
        "defaults": lambda: {key: getattr(DixonColesEngine, attr) for key, attr in DC_SETTINGS.items()},
        "make": lambda params, refit: DixonColesModel(name="m", refit=refit, **params),
        "markets": ("score", "1x2", "over25", "btts"),
        "stages": [("xi", XI_GRID), ("ridge", RIDGE_GRID), ("sot_weight", [0.0, 0.2, 0.35, 0.5, 0.65, 0.8]),
                   ("xi", XI_GRID)],
    },
    "corners": {
        "defaults": lambda: dict(CORNERS_SETTINGS),
        "make": lambda params, refit: CountPropsModel(name="m", stats=("corners",), refit=refit, **params),
        "markets": _prop_markets("corners"),
        "stages": [("ridge", RIDGE_GRID), ("xi", XI_GRID), ("ridge", RIDGE_GRID)],
    },
    "cards": {
        "defaults": lambda: dict(CARDS_SETTINGS),
        "make": lambda params, refit: CountPropsModel(name="m", stats=("cards",), refit=refit, **params),
        "markets": _prop_markets("cards"),
        "stages": [("ridge", RIDGE_GRID), ("xi", XI_GRID), ("referee_prior", [5.0, 15.0, 40.0, 1e6]),
                   ("ridge", RIDGE_GRID)],
    },
}


def _league_losses(args):
    target, league, params, window, refit = args
    spec = TARGETS[target]
    matches = prepare_league(league)["matches"]
    start, end = pd.Timestamp(window[0]), pd.Timestamp(window[1]) if window[1] else None
    preds = walk_forward(matches, [spec["make"](params, refit)], start, end).get("m")
    if preds is None:
        return {}
    losses = per_match_losses(matches, preds)
    if target in PROP_LINES:  # objective: mean over the stat's lines, per match
        losses[target] = pd.concat([losses[m] for m in spec["markets"][1:]], axis=1).mean(axis=1, skipna=False)
    return {m: losses[m].set_axis(league + "_" + losses[m].index.astype(str)) for m in spec["markets"] if m in losses}


def evaluate(target, leagues, params, window, refit, pool):
    parts = list(pool.map(_league_losses, [(target, lk, params, window, refit) for lk in leagues]))
    return {m: pd.concat([p[m] for p in parts if m in p]) for m in TARGETS[target]["markets"]}


def summary(losses):
    return {m: round(float(s.mean()), 5) for m, s in losses.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=list(TARGETS), default="goals")
    parser.add_argument("--leagues", nargs="+", default=DOMESTIC)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--start", help="starting point, e.g. xi=0.0025,ridge=8,sot_weight=0.35")
    parser.add_argument("--stages", nargs="+", help="coordinate-search stages, e.g. ridge=8,16,32 sot_weight=0,0.35")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    spec = TARGETS[args.target]
    objective = spec["markets"][0]
    default = spec["defaults"]()
    start = dict(default)
    if args.start:
        start.update({k: float(v) for k, v in (kv.split("=") for kv in args.start.split(","))})
    stages = spec["stages"]
    if args.stages:
        stages = [(name, [float(v) for v in values.split(",")])
                  for name, values in (stage.split("=") for stage in args.stages)]

    history, best, best_score = [], dict(start), None
    with ProcessPoolExecutor(initializer=limit_worker_threads) as pool:
        for param, grid in stages:
            for value in grid:
                params = dict(best, **{param: value})
                score = summary(evaluate(args.target, args.leagues, params, TUNE, "QS", pool))
                history.append({"params": params, "tuning": score})
                print(f"tune {param}={value:<7g} -> " + "  ".join(f"{m} {v:.5f}" for m, v in score.items()), flush=True)
                if best_score is None or score[objective] < best_score:
                    best, best_score = params, score[objective]
            print(f"  best after {param}: {best}", flush=True)

        tuned_losses = evaluate(args.target, args.leagues, best, CONFIRM, "MS", pool)
        default_losses = evaluate(args.target, args.leagues, default, CONFIRM, "MS", pool)

    confirmation = {}
    print(f"\nConfirmation window {CONFIRM[0]} onwards (monthly refits): tuned {best} vs default {default}")
    for m in spec["markets"]:
        joined = pd.concat([tuned_losses[m], default_losses[m]], axis=1, join="inner").dropna()
        diff = paired_difference(joined.iloc[:, 0], joined.iloc[:, 1])
        confirmation[m] = {"tuned": round(float(joined.iloc[:, 0].mean()), 5),
                           "default": round(float(joined.iloc[:, 1].mean()), 5), **diff}
        print(f"  {m:<16} tuned {confirmation[m]['tuned']:.5f}  default {confirmation[m]['default']:.5f}  "
              f"diff {diff['mean']:+.5f} ± {diff['se']:.5f}  (n={diff['n']})")
    if args.json:
        args.json.write_text(json.dumps({"target": args.target, "best": best, "default": default,
                                         "search": history, "confirmation": confirmation}, indent=2))


if __name__ == "__main__":
    main()
