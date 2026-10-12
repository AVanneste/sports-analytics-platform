import numpy as np
from scipy.stats import poisson

from football_core.models.predictor import likely_score


def grid(lam, mu):
    return np.outer(poisson.pmf(range(8), lam), poisson.pmf(range(8), mu))


def test_score_follows_the_favoured_result():
    mat = grid(1.4, 1.1)  # home favoured, yet 1-1 is the single most likely cell
    assert np.unravel_index(mat.argmax(), mat.shape) == (1, 1)
    home = np.tril(mat, -1).sum(); draw = np.trace(mat); away = np.triu(mat, 1).sum()
    assert likely_score(mat, home, draw, away)[0] == "1-0"
    assert likely_score(mat, 0.2, 0.5, 0.3)[0] == "1-1"
    assert likely_score(grid(0.8, 2.0), 0.2, 0.2, 0.6)[0] == "0-1"


def test_top_scores_lists_the_most_likely_cells():
    from football_core.models.predictor import top_scores
    tops = top_scores(grid(1.4, 1.1))
    assert tops[0][0] == "1-1" and len(tops) == 3 and tops[0][1] >= tops[1][1] >= tops[2][1]
