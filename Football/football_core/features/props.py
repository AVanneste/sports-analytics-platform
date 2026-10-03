"""Corners and cards projections, shared by the training features and live predictions.

Both paths call these functions, so the expectations a model was trained on are the ones it
is served. They are heuristics (league baselines, shrinkage, negative binomial), not fitted
models; ``train_league_models`` reports their holdout log loss against the base rate.
"""
from typing import Dict, Optional

import numpy as np
from scipy.stats import nbinom

HOME_CORNERS_BASE, AWAY_CORNERS_BASE = 5.50, 4.52
HOME_CARDS_BASE, AWAY_CARDS_BASE = 2.10, 2.39
SAMPLE_WEIGHT = 0.35  # weight on a team's rolling 5-match average vs the league baseline
CORNERS_PHI, CARDS_PHI = 1.20, 1.80  # negative binomial overdispersion


def _shrink(sample: Optional[float], base: float) -> float:
    value = base if sample is None or not np.isfinite(sample) else float(sample)
    return SAMPLE_WEIGHT * value + (1.0 - SAMPLE_WEIGHT) * base


def _nb_prob_over(line_floor: int, mean: float, phi: float) -> float:
    p = 1.0 / phi
    n = mean * p / (1.0 - p)
    return float(1.0 - nbinom.cdf(line_floor, n, p))


def project_corners(h_for: Optional[float], h_against: Optional[float], a_for: Optional[float],
                    a_against: Optional[float], elo_diff: float = 0.0) -> Dict[str, float]:
    """Expected total corners and P(over 9.5 / 10.5). ``elo_diff`` includes home advantage."""
    h_att = _shrink(h_for, HOME_CORNERS_BASE)
    a_def = _shrink(a_against, HOME_CORNERS_BASE)
    a_att = _shrink(a_for, AWAY_CORNERS_BASE)
    h_def = _shrink(h_against, AWAY_CORNERS_BASE)

    elo_adj = float(np.clip(elo_diff / 400.0, -1.0, 1.0))
    proj_h = float(np.clip((h_att + a_def) / 2.0 + elo_adj * 0.55, 3.2, 7.2))
    proj_a = float(np.clip((a_att + h_def) / 2.0 - elo_adj * 0.45, 2.2, 5.8))
    expected = float(np.clip(proj_h + proj_a, 8.2, 11.8))

    over95 = float(np.clip(_nb_prob_over(9, expected, CORNERS_PHI), 0.15, 0.72))
    over105 = float(np.clip(_nb_prob_over(10, expected, CORNERS_PHI), 0.10, 0.63))
    return {"expected": expected, "over95": over95, "under95": 1.0 - over95, "over105": over105}


def project_cards(h_cards_for: Optional[float], a_cards_for: Optional[float],
                  ref_strictness: Optional[float] = 1.0, is_cup: bool = False) -> Dict[str, float]:
    """Expected total cards and P(over 3.5 / 4.5), scaled by the referee's strictness index."""
    base = _shrink(h_cards_for, HOME_CARDS_BASE) + _shrink(a_cards_for, AWAY_CARDS_BASE)
    ref_factor = float(np.clip(ref_strictness or 1.0, 0.85, 1.25))
    cup_factor = 1.05 if is_cup else 1.0
    expected = float(np.clip(base * ref_factor * cup_factor, 2.8, 5.8))

    over35 = float(np.clip(_nb_prob_over(3, expected, CARDS_PHI), 0.25, 0.75))
    over45 = float(np.clip(_nb_prob_over(4, expected, CARDS_PHI), 0.15, 0.62))
    return {"expected": expected, "over35": over35, "under35": 1.0 - over35,
            "over45": over45, "under45": 1.0 - over45}
