"""Scouting scores for the FotMob player table (football_core/data/fotmob_players.py).

Each regular (``MIN_SHARE`` of his league's most-played minutes) is compared with every scouted
player of his position group across leagues: per-90 percentiles, then a role score, the weighted
mean of the percentiles that matter for that position (``ROLES``). Production is easier against
weaker opponents, so the role score is shifted by the club's Opta Power Ranking (``LEVEL_WEIGHT``
percentile points per rating point from ``REFERENCE_LEVEL``). ``similar`` finds the closest
percentile profiles of the same position anywhere in the table.
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from football_core.data.opta_power import club_rating

MIN_SHARE = 0.5
TOTALS_TO_P90 = ("big_chance_created", "total_att_assist", "_goals_prevented", "expected_goalsontarget")
# weights on percentiles, per position group (FotMob table names: per 90 unless converted above)
ROLES: Dict[str, Dict[str, float]] = {
    "ST": {"expected_goals_per_90": 2, "expected_goalsontarget_p90": 1, "total_scoring_att": 1, "ontarget_scoring_att": 0.5,
           "expected_assists_per_90": 0.5, "won_contest": 0.5, "poss_won_att_3rd": 0.5},
    "W": {"expected_assists_per_90": 1.5, "total_att_assist_p90": 1, "won_contest": 1.5, "expected_goals_per_90": 1,
          "big_chance_created_p90": 1, "lbp_total": 0.5},
    "AM": {"expected_assists_per_90": 1.5, "total_att_assist_p90": 1.5, "lbp_total": 1, "expected_goals_per_90": 1,
           "big_chance_created_p90": 1, "won_contest": 0.5},
    "CM": {"lbp_total": 1.5, "accurate_pass": 1, "accurate_long_balls": 1, "ball_recovery": 1,
           "expected_assists_per_90": 0.5, "defensive_contributions": 0.5},
    "DM": {"ball_recovery": 1.5, "interception": 1, "total_tackle": 1, "defensive_contributions": 1, "lbp_total": 1,
           "accurate_pass": 0.5},
    "CB": {"interception": 1, "ball_recovery": 1, "defensive_contributions": 1, "lbp_total": 1, "accurate_long_balls": 1,
           "effective_clearance": 0.5, "total_tackle": 0.5, "outfielder_block": 0.5, "accurate_pass": 0.5},
    "FB": {"expected_assists_per_90": 1, "total_att_assist_p90": 1, "ball_recovery": 1, "interception": 1,
           "total_tackle": 1, "won_contest": 0.5, "lbp_total": 0.5},
    "GK": {"_goals_prevented_p90": 2, "_save_percentage": 1, "accurate_long_balls": 0.5},
}
# From scripts/backtest_scout.py (2024/25 season, 1,447 players aged <=23 worth <=€5m, 20% doubled
# their value by Oct 2026): AUC 0.63 at weight 3 (0.52 for the role score alone), 43% of the top
# 100 doubled. The club's level carries most of that; within a level band the role score is weak
# (AUC 0.54; best for full-backs and keepers, none for strikers and wingers), so role weights are
# not fitted. Rerun the backtest with more seasons before trusting finer weights.
LEVEL_WEIGHT = 3.0
REFERENCE_LEVEL = 70.0


def prepare(players: pd.DataFrame) -> pd.DataFrame:
    """Regulars only, totals turned into per-90 values, and each club's Opta level (the league's
    median club rating when the club is not found, e.g. reserve sides)."""
    df = players.copy()
    df = df[df["minutes"] >= MIN_SHARE * df.groupby("league_id")["minutes"].transform("max")]
    df = df[df["position"].notna()]
    for stat in TOTALS_TO_P90:
        if stat in df:
            df[f"{stat}_p90"] = df[stat] * 90 / df["minutes"]
    rating = {t: (club_rating(t) or (None,))[0] for t in df["team"].dropna().unique()}
    df["level"] = df["team"].map(rating)
    df["level"] = df["level"].fillna(df.groupby("league_id")["level"].transform("median"))
    return df


def score(players: pd.DataFrame) -> pd.DataFrame:
    """``prepare``d players with ``pct_<stat>`` percentiles (0-100, within position group; a player
    missing from a FotMob table counts as that group's median), ``role_score`` and ``adj_score``."""
    df = prepare(players)
    stats = sorted({s for weights in ROLES.values() for s in weights} & set(df.columns))
    for stat in stats:
        pct = df.groupby("position")[stat].rank(pct=True) * 100
        df[f"pct_{stat}"] = pct.fillna(50.0)
    df["role_score"] = np.nan
    for position, weights in ROLES.items():
        rows = df["position"] == position
        used = {s: w for s, w in weights.items() if s in stats}
        if not used or not rows.any():
            continue
        total = sum(used.values())
        df.loc[rows, "role_score"] = sum(df.loc[rows, f"pct_{s}"] * w for s, w in used.items()) / total
    df["adj_score"] = df["role_score"] + LEVEL_WEIGHT * (df["level"].fillna(REFERENCE_LEVEL) - REFERENCE_LEVEL)
    return df


def similar(scored: pd.DataFrame, player_id: int, n: int = 5, pool: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The ``n`` players of the same position (from ``pool``, default all) with the closest
    percentile profile; ``similarity`` is 100 minus the mean percentile gap (100 = identical)."""
    me = scored[scored["player_id"] == player_id].iloc[0]
    pool = scored if pool is None else pool
    pool = pool[(pool["position"] == me["position"]) & (pool["player_id"] != player_id)]
    cols = [c for c in scored.columns if c.startswith("pct_")]
    gap = np.abs(pool[cols].to_numpy(float) - me[cols].to_numpy(float)).mean(axis=1)
    return pool.assign(similarity=100 - gap).nlargest(n, "similarity")


STAT_LABELS = {
    "expected_goals_per_90": "xG", "expected_goalsontarget_p90": "xGOT", "total_scoring_att": "Shots",
    "ontarget_scoring_att": "Shots on target", "expected_assists_per_90": "xA", "won_contest": "Dribbles",
    "poss_won_att_3rd": "Final-third wins", "total_att_assist_p90": "Chances created", "big_chance_created_p90": "Big chances",
    "lbp_total": "Line-breaking passes", "accurate_pass": "Accurate passes", "accurate_long_balls": "Long balls",
    "ball_recovery": "Recoveries", "defensive_contributions": "Defensive actions", "interception": "Interceptions",
    "total_tackle": "Tackles", "effective_clearance": "Clearances", "outfielder_block": "Blocks",
    "_goals_prevented_p90": "Goals prevented", "_save_percentage": "Save %",
}


def _text(value) -> Optional[str]:
    return None if value is None or pd.isna(value) else str(value)


def _num(value, digits: int = 2):
    return None if value is None or value != value else round(float(value), digits)


def export(scored: pd.DataFrame, max_age: float = 26, limit: int = 1500, n_similar: int = 5) -> Dict:
    """The web payload: the ``limit`` best league-adjusted players aged up to ``max_age`` (filters
    narrow it further in the app), each with his role's stats and closest profiles in the whole pool."""
    young = scored[scored["age"].notna() & (scored["age"] <= max_age) & scored["adj_score"].notna()]
    rows = []
    for _, p in young.nlargest(limit, "adj_score").iterrows():
        stats = [{"label": STAT_LABELS.get(s, s), "value": _num(p.get(s)), "pct": _num(p.get(f"pct_{s}"), 0)}
                 for s in ROLES[p["position"]] if s in scored]
        twins = similar(scored, p["player_id"], n_similar)
        rows.append({"id": int(p["player_id"]), "name": p["name"], "team": _text(p["team"]), "league": _text(p["league"]),
                     "nationality": _text(p.get("nationality")), "age": _num(p["age"], 0), "position": p["position"],
                     "foot": _text(p.get("foot")), "contract_end": _text(p.get("contract_end")), "height_cm": _num(p.get("height_cm"), 0),
                     "minutes": int(p["minutes"]), "matches": int(p["matches"]),
                     "market_value_eur": _num(p.get("market_value_eur"), 0), "level": _num(p.get("level"), 1),
                     "role_score": _num(p["role_score"], 1), "adj_score": _num(p["adj_score"], 1), "stats": stats,
                     "similar": [{"id": int(t["player_id"]), "name": t["name"], "team": _text(t["team"]), "league": _text(t["league"]),
                                  "age": _num(t.get("age"), 0), "similarity": _num(t["similarity"], 0)}
                                 for _, t in twins.iterrows()]})
    return {"players": rows, "pool_size": int(len(scored)), "leagues": sorted(scored["league"].dropna().unique().tolist())}
