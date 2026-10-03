"""Rolling momentum, shot efficiency, corners, cards, rest days, and venue-specific form tracker."""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from collections import defaultdict


def _num(value) -> Optional[float]:
    """Float value of a match statistic, or None when it was not reported."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def _mean(matches: List[Dict], key: str, default: float) -> float:
    """Average of ``key`` over matches that reported it; ``default`` (the cold-start prior) if none did."""
    values = [m[key] for m in matches if m.get(key) is not None]
    return sum(values) / len(values) if values else default


def _share(matches: List[Dict], key_for: str, key_against: str, default: float) -> float:
    """for / (for + against) over matches that reported both values."""
    pairs = [(m[key_for], m[key_against]) for m in matches
             if m.get(key_for) is not None and m.get(key_against) is not None]
    if not pairs:
        return default
    total_for = sum(p[0] for p in pairs)
    total_against = sum(p[1] for p in pairs)
    return total_for / (total_for + total_against + 1e-5)


class TeamFormTracker:
    """Maintains chronological match logs and rolling metrics per team."""

    def __init__(self):
        self.team_history = defaultdict(list)
        self.home_history = defaultdict(list)
        self.away_history = defaultdict(list)

    def record_match(
        self,
        date: pd.Timestamp,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        hs: Optional[float] = None,
        as_: Optional[float] = None,
        hst: Optional[float] = None,
        ast: Optional[float] = None,
        hc: Optional[float] = None,
        ac: Optional[float] = None,
        hf: Optional[float] = None,
        af: Optional[float] = None,
        hy: Optional[float] = None,
        ay: Optional[float] = None,
        hr: Optional[float] = None,
        ar: Optional[float] = None,
    ):
        """Record completed match into team match logs."""
        if fthg > ftag:
            home_pts, away_pts = 3, 0
            home_res, away_res = "W", "L"
        elif fthg == ftag:
            home_pts, away_pts = 1, 1
            home_res, away_res = "D", "D"
        else:
            home_pts, away_pts = 0, 3
            home_res, away_res = "L", "W"

        h_s, a_s = _num(hs), _num(as_)
        h_st, a_st = _num(hst), _num(ast)
        h_c, a_c = _num(hc), _num(ac)
        h_f, a_f = _num(hf), _num(af)
        h_y, a_y = _num(hy), _num(ay)
        h_r, a_r = _num(hr), _num(ar)
        # Missing stats stay None; rolling averages below only use matches that reported them.
        h_cards = None if h_y is None else h_y + (h_r or 0.0)
        a_cards = None if a_y is None else a_y + (a_r or 0.0)

        home_record = {
            "date": date,
            "venue": "H",
            "opponent": away_team,
            "gf": fthg,
            "ga": ftag,
            "pts": home_pts,
            "res": home_res,
            "shots_for": h_s,
            "shots_against": a_s,
            "sot_for": h_st,
            "sot_against": a_st,
            "corners_for": h_c,
            "corners_against": a_c,
            "fouls_for": h_f,
            "fouls_against": a_f,
            "cards_for": h_cards,
            "cards_against": a_cards,
        }

        away_record = {
            "date": date,
            "venue": "A",
            "opponent": home_team,
            "gf": ftag,
            "ga": fthg,
            "pts": away_pts,
            "res": away_res,
            "shots_for": a_s,
            "shots_against": h_s,
            "sot_for": a_st,
            "sot_against": h_st,
            "corners_for": a_c,
            "corners_against": h_c,
            "fouls_for": a_f,
            "fouls_against": h_f,
            "cards_for": a_cards,
            "cards_against": h_cards,
        }

        self.team_history[home_team].append(home_record)
        self.team_history[away_team].append(away_record)

        self.home_history[home_team].append(home_record)
        self.away_history[away_team].append(away_record)

    def get_team_rolling_features(self, team: str, current_date: pd.Timestamp, n_matches: int = 5) -> Dict[str, float]:
        """Compute rolling statistics for a team prior to the current match."""
        history = [m for m in self.team_history[team] if m["date"] < current_date]
        if not history:
            return {
                f"ppg_last{n_matches}": 1.35,
                f"win_rate_last{n_matches}": 0.35,
                f"draw_rate_last{n_matches}": 0.25,
                f"loss_rate_last{n_matches}": 0.40,
                f"gf_per_game_last{n_matches}": 1.35,
                f"ga_per_game_last{n_matches}": 1.35,
                f"gd_per_game_last{n_matches}": 0.0,
                f"tsr_last{n_matches}": 0.50,
                f"sotr_last{n_matches}": 0.50,
                f"corners_for_last{n_matches}": 5.0,
                f"corners_against_last{n_matches}": 4.8,
                f"corners_diff_last{n_matches}": 0.2,
                f"fouls_for_last{n_matches}": 11.2,
                f"fouls_against_last{n_matches}": 11.2,
                f"cards_for_last{n_matches}": 2.1,
                f"cards_against_last{n_matches}": 2.1,
                "days_rest": 7.0,
                "matches_last_21d": 3.0,
            }

        recent = history[-n_matches:]
        k = len(recent)

        pts = sum(m["pts"] for m in recent)
        wins = sum(1 for m in recent if m["res"] == "W")
        draws = sum(1 for m in recent if m["res"] == "D")
        losses = sum(1 for m in recent if m["res"] == "L")

        gf = sum(m["gf"] for m in recent)
        ga = sum(m["ga"] for m in recent)

        tsr = _share(recent, "shots_for", "shots_against", default=0.50)
        sotr = _share(recent, "sot_for", "sot_against", default=0.50)

        corners_for = _mean(recent, "corners_for", 5.0)
        corners_against = _mean(recent, "corners_against", 4.8)
        corners_diff = corners_for - corners_against

        fouls_for = _mean(recent, "fouls_for", 11.2)
        fouls_against = _mean(recent, "fouls_against", 11.2)
        cards_for = _mean(recent, "cards_for", 2.1)
        cards_against = _mean(recent, "cards_against", 2.1)

        last_match_date = history[-1]["date"]
        days_rest = max(1.0, (current_date - last_match_date).total_seconds() / 86400.0)
        matches_21d = sum(1 for m in history if (current_date - m["date"]).total_seconds() / 86400.0 <= 21.0)

        return {
            f"ppg_last{n_matches}": pts / k,
            f"win_rate_last{n_matches}": wins / k,
            f"draw_rate_last{n_matches}": draws / k,
            f"loss_rate_last{n_matches}": losses / k,
            f"gf_per_game_last{n_matches}": gf / k,
            f"ga_per_game_last{n_matches}": ga / k,
            f"gd_per_game_last{n_matches}": (gf - ga) / k,
            f"tsr_last{n_matches}": tsr,
            f"sotr_last{n_matches}": sotr,
            f"corners_for_last{n_matches}": corners_for,
            f"corners_against_last{n_matches}": corners_against,
            f"corners_diff_last{n_matches}": corners_diff,
            f"fouls_for_last{n_matches}": fouls_for,
            f"fouls_against_last{n_matches}": fouls_against,
            f"cards_for_last{n_matches}": cards_for,
            f"cards_against_last{n_matches}": cards_against,
            "days_rest": min(30.0, days_rest),
            "matches_last_21d": float(matches_21d),
        }

    def get_venue_specific_form(self, team: str, current_date: pd.Timestamp, venue: str = "H", n_matches: int = 5) -> Dict[str, float]:
        """Compute home-specific or away-specific rolling form."""
        venue_history = self.home_history[team] if venue == "H" else self.away_history[team]
        history = [m for m in venue_history if m["date"] < current_date]
        prefix = "home" if venue == "H" else "away"

        if not history:
            return {
                f"{prefix}_ppg_last{n_matches}": 1.5 if venue == "H" else 1.1,
                f"{prefix}_gf_last{n_matches}": 1.5 if venue == "H" else 1.1,
                f"{prefix}_ga_last{n_matches}": 1.1 if venue == "H" else 1.5,
                f"{prefix}_corners_last{n_matches}": 5.5 if venue == "H" else 4.3,
                f"{prefix}_cards_last{n_matches}": 1.9 if venue == "H" else 2.2,
            }

        recent = history[-n_matches:]
        k = len(recent)
        pts = sum(m["pts"] for m in recent)
        gf = sum(m["gf"] for m in recent)
        ga = sum(m["ga"] for m in recent)
        corners = _mean(recent, "corners_for", 5.5 if venue == "H" else 4.3)
        cards = _mean(recent, "cards_for", 1.9 if venue == "H" else 2.2)

        return {
            f"{prefix}_ppg_last{n_matches}": pts / k,
            f"{prefix}_gf_last{n_matches}": gf / k,
            f"{prefix}_ga_last{n_matches}": ga / k,
            f"{prefix}_corners_last{n_matches}": corners,
            f"{prefix}_cards_last{n_matches}": cards,
        }
