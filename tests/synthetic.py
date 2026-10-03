"""Deterministic synthetic football and tennis data for tests (no network, no real files)."""
import math

import numpy as np
import pandas as pd


def make_football_matches(seasons: int = 4, teams: int = 10, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = [f"Team{i:02d}" for i in range(teams)]
    strength = np.linspace(0.45, -0.45, teams)
    rows, day = [], pd.Timestamp("2019-08-01")
    for _ in range(seasons):
        fixtures = [(h, a) for h in range(teams) for a in range(teams) if h != a]
        rng.shuffle(fixtures)
        for h, a in fixtures:
            day += pd.Timedelta(days=1)
            lam = math.exp(0.25 + strength[h] - strength[a] * 0.8)
            mu = math.exp(strength[a] - strength[h] * 0.8)
            hg, ag = int(rng.poisson(lam)), int(rng.poisson(mu))
            p = np.array([lam, 0.8, mu]); p = p / p.sum()
            rows.append({
                "Date": day, "HomeTeam": names[h], "AwayTeam": names[a], "FTHG": hg, "FTAG": ag,
                "FTR": "H" if hg > ag else ("A" if ag > hg else "D"),
                "HC": float(rng.poisson(5)), "AC": float(rng.poisson(4)),
                "HY": float(rng.poisson(2)), "AY": float(rng.poisson(2)), "HR": 0.0, "AR": 0.0,
                "HF": float(rng.poisson(11)), "AF": float(rng.poisson(11)),
                "HS": float(rng.poisson(12)), "AS": float(rng.poisson(10)),
                "HST": float(rng.poisson(4)), "AST": float(rng.poisson(3)),
                "Referee": f"Ref{int(rng.integers(0, 6))}",
                "odds_home": round(1.05 / p[0], 2), "odds_draw": round(1.05 / p[1], 2), "odds_away": round(1.05 / p[2], 2),
                "odds_over25": 1.9, "odds_under25": 1.9,
            })
    df = pd.DataFrame(rows)
    df["target_1x2"] = df["FTR"].map({"H": 0, "D": 1, "A": 2})
    df["target_over25"] = ((df["FTHG"] + df["FTAG"]) > 2.5).astype(int)
    df["target_btts"] = ((df["FTHG"] > 0) & (df["FTAG"] > 0)).astype(int)
    return df


def make_tennis_matches(n: int = 500, players: int = 24, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = [f"Player{i:02d} X." for i in range(players)]
    skill = np.linspace(1.5, -1.5, players)

    def rank_at(player: int, progress: float) -> float:
        base = 10 + 5 * player
        return float(round(base * ((1.5 - progress) if player % 2 else (0.5 + progress))))

    rows, day = [], pd.Timestamp("2023-01-02")
    for i in range(n):
        day += pd.Timedelta(days=int(rng.integers(0, 2)))
        a, b = rng.choice(players, size=2, replace=False)
        a_wins = rng.uniform() < 1.0 / (1.0 + math.exp(-(skill[a] - skill[b])))
        w, l = (a, b) if a_wins else (b, a)
        rows.append({
            "winner_name": names[w], "loser_name": names[l],
            "surface": ["Hard", "Clay", "Grass"][i % 3], "tourney_date": day, "tourney_level": "A",
            "tourney_name": f"Event{i // 30}",
            # Rankings drift over the period (half the field improves, half declines), so a
            # career-best computed over the whole dataset would differ from the one known so far.
            "winner_rank": rank_at(w, i / n), "loser_rank": rank_at(l, i / n),
            "score": None if i % 50 == 7 else "6-4 3-6 6-3",
            "winner_odds": 1.6, "loser_odds": 2.3,
        })
    return pd.DataFrame(rows)


def make_sackmann(tennis_df: pd.DataFrame) -> pd.DataFrame:
    """Sackmann-style rows (dated by tournament start) for the same synthetic players."""
    rows = []
    for i, r in tennis_df.iterrows():
        start = r["tourney_date"] - pd.Timedelta(days=i % 5)
        rows.append({
            "tourney_date": int(start.strftime("%Y%m%d")), "surface": r["surface"],
            "winner_name": r["winner_name"], "loser_name": r["loser_name"],
            **{f"w_{c}": v for c, v in zip(("ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "bpSaved", "bpFaced"),
                                            (5 + i % 7, 2, 70, 42, 32, 15, 3, 5))},
            **{f"l_{c}": v for c, v in zip(("ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "bpSaved", "bpFaced"),
                                            (3, 4, 75, 40, 26, 14, 4, 9))},
        })
    return pd.DataFrame(rows)
