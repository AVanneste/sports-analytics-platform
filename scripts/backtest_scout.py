"""Does the scout find gems? Score a past season and check whose market value doubled since.

    python scripts/backtest_scout.py [--max-age 23] [--max-value 5e6]

Base seasons: 2024/2025 and 2023/2024 (2024, 2023 in calendar-year leagues), every scouting league FotMob has
tables for, scored exactly like today (football_core/scouting.py). Pool: regulars aged up to
``--max-age`` worth at most ``--max-value`` at the base date. Hit: market value (FotMob's monthly
history) at least doubled by now. Each ranking (league-adjusted score for several level weights,
raw role score, and two naive baselines: goals+assists per 90 and FotMob's match rating) is
judged by ROC AUC and by the hit rate of its top 100. Data is cached in data/processed/scout/backtest/.

Caveat: club levels are today's Opta ratings, a little hindsight for clubs that rose or fell.
"""
import argparse
import logging
import time
from typing import Dict, Optional

import numpy as np
import pandas as pd
import requests
from sklearn.metrics import roc_auc_score

from football_core import scouting
from football_core.data.fotmob_players import BASE_URL, PAUSE, SCOUT_DIR, SCOUT_LEAGUES, _get, fetch_league

CACHE = SCOUT_DIR / "backtest"
# base seasons: (European name, calendar-year name) -> date their values are read at
BASES = {("2024/2025", "2024"): "2025-06-01", ("2023/2024", "2023"): "2024-06-01"}
WEIGHTS = (0.0, 1.0, 2.0, 3.0, 4.0)


def base_players() -> pd.DataFrame:
    """Every base season's players (cached per season), each with the date its values are read at."""
    frames = []
    for names, date in BASES.items():
        path = CACHE / f"base_{names[0].replace('/', '-')}.parquet"
        if not path.exists():
            season_frames = []
            for league_id in SCOUT_LEAGUES:
                for season in names:
                    try:
                        df = fetch_league(league_id, season)
                    except (requests.RequestException, ValueError, KeyError) as e:
                        logging.warning(f"{league_id} {season}: {e}")
                        continue
                    if not df.empty:
                        season_frames.append(df)
                        logging.info(f"{SCOUT_LEAGUES[league_id]} {season}: {len(df)} players")
                        break
            CACHE.mkdir(parents=True, exist_ok=True)
            pd.concat(season_frames, ignore_index=True).to_parquet(path, index=False)
        frames.append(pd.read_parquet(path).assign(base_date=date))
    return pd.concat(frames, ignore_index=True)


def parse_history(data: Dict) -> Dict:
    values = sorted(((v["date"][:10], v["value"]) for v in (data.get("marketValues") or {}).get("values") or [] if v.get("value")))
    return {"player_id": data.get("id"), "birth_date": ((data.get("birthDate") or {}).get("utcTime") or "")[:10] or None,
            "values": values}


def value_at(values, date: str) -> Optional[float]:
    """The last value on or before ``date``."""
    before = [v for d, v in values if d <= date]
    return float(before[-1]) if before else None


def histories(player_ids) -> pd.DataFrame:
    path = CACHE / "histories.pkl"
    known = pd.read_pickle(path) if path.exists() else pd.DataFrame(columns=["player_id", "birth_date", "values"])
    todo = sorted(set(int(p) for p in player_ids) - set(known["player_id"]))
    rows = []
    for i, pid in enumerate(todo):
        time.sleep(PAUSE)
        try:
            rows.append(parse_history(_get(f"{BASE_URL}/api/data/playerData", {"id": pid}).json()))
        except (requests.RequestException, ValueError) as e:
            logging.warning(f"player {pid}: {e}")
        if rows and (i % 250 == 249 or i == len(todo) - 1):
            known = pd.concat([known, pd.DataFrame(rows)], ignore_index=True)
            known.to_pickle(path)
            rows = []
            logging.info(f"{i + 1}/{len(todo)} profiles")
    return known


def evaluate(pool: pd.DataFrame, rankings: Dict[str, pd.Series], top: int = 100) -> pd.DataFrame:
    """AUC and top-``top`` hit rate of each ranking (higher = more likely to double)."""
    out = []
    for name, score in rankings.items():
        score = score.replace([np.inf, -np.inf], np.nan)
        ok = score.notna()
        out.append({"ranking": name, "auc": roc_auc_score(pool.loc[ok, "hit"], score[ok]),
                    f"hit_rate_top{top}_%": 100 * pool.loc[score.nlargest(top).index, "hit"].mean()})
    return pd.DataFrame(out).set_index("ranking").round(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-age", type=float, default=23)
    parser.add_argument("--max-value", type=float, default=5e6)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    scored = pd.concat([scouting.score(g) for _, g in base_players().groupby("base_date")], ignore_index=True)
    current = pd.read_parquet(SCOUT_DIR / "players.parquet")[["player_id", "birth_date"]].dropna().drop_duplicates("player_id")
    scored = scored.merge(current.rename(columns={"birth_date": "known_birth"}), on="player_id", how="left")
    age = lambda birth, at: (pd.to_datetime(at) - pd.to_datetime(birth)).dt.days / 365.25
    # players still in our leagues and clearly too old now are skipped; everyone else needs a profile
    maybe = scored[scored["known_birth"].isna() | (age(scored["known_birth"], scored["base_date"]) <= args.max_age + 0.5)]
    hist = histories(maybe["player_id"])
    pool = maybe.merge(hist, on="player_id", how="inner")
    pool["age_base"] = age(pool["birth_date"], pool["base_date"])
    pool["value_base"] = [value_at(v, d) for v, d in zip(pool["values"], pool["base_date"])]
    pool["value_now"] = [float(v[-1][1]) if len(v) else None for v in pool["values"]]
    pool = pool[(pool["age_base"] <= args.max_age) & pool["value_base"].between(1, args.max_value) & pool["value_now"].notna()]
    pool = pool.reset_index(drop=True)
    pool["hit"] = pool["value_now"] >= 2 * pool["value_base"]
    logging.info(f"pool {len(pool)} players, {pool['hit'].mean():.1%} doubled their value")

    ga90 = (pool.get("goals", 0).fillna(0) + pool.get("goal_assist", 0).fillna(0)) * 90 / pool["minutes"]
    rankings = {f"adj_score w={w}": pool["role_score"] + w * (pool["level"] - scouting.REFERENCE_LEVEL) for w in WEIGHTS}
    rankings.update({"role_score": pool["role_score"], "baseline: G+A per 90": ga90,
                     # FotMob only rates its top players: the rest count as median, or the AUC flatters it
                     "baseline: FotMob rating": pool["rating"].fillna(pool["rating"].median()),
                     "baseline: youngest": -pool["age_base"]})
    print(f"\nPool: {len(pool)} regulars aged <= {args.max_age:g}, worth <= €{args.max_value / 1e6:g}m in 2024/25; "
          f"{pool['hit'].mean():.1%} doubled their value since.\n")
    print(evaluate(pool, rankings).to_string())
    best = max(WEIGHTS, key=lambda w: evaluate(pool, {"x": rankings[f"adj_score w={w}"]}).loc["x", "auc"])
    print(f"\nBest level weight: {best}. AUC by position at that weight:")
    by_pos = {pos: roc_auc_score(g["hit"], rankings[f"adj_score w={best}"][g.index])
              for pos, g in pool.groupby("position") if g["hit"].nunique() == 2}
    print(pd.Series(by_pos).round(3).to_string())


if __name__ == "__main__":
    main()
